import flask
import os
import csv
import json
import shutil
import sqlite3
import secrets
import threading
import time
from string import Template
from datetime import datetime, timezone
from flask_mail import Mail, Message
from markdown import markdown

BATCH_SIZE = 100
BATCH_SLEEP_SECONDS = 10
JOB_RETENTION_SECONDS = 300
STREAM_KEEPALIVE_SECONDS = 15

app = flask.Flask(__name__)
app.config.from_object('config')
mail = Mail()

path = os.getcwd()
ALLOWED_EXTENSIONS = set(['csv', 'pdf'])
DB_PATH = os.path.join(path, 'presets.db')

DEFAULT_TEMPLATE = "Dear $name,\nThanks for using this service."
DEFAULT_PRESET = {
    'from': '',
    'reply_to': '',
    'smtp_server': '',
    'smtp_port': 587,
    'smtp_use_tls': True,
    'template': DEFAULT_TEMPLATE,
}

JOBS = {}
JOBS_LOCK = threading.Lock()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS presets (
                token TEXT PRIMARY KEY,
                created_at TEXT
            )
        ''')
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(presets)').fetchall()}
        if 'data' not in cols:
            conn.execute('ALTER TABLE presets ADD COLUMN data TEXT')
        legacy_cols = {'from_addr', 'smtp_server', 'smtp_port', 'smtp_use_tls', 'template'}
        if legacy_cols.issubset(cols):
            rows = conn.execute(
                'SELECT token, from_addr, smtp_server, smtp_port, smtp_use_tls, template '
                'FROM presets WHERE data IS NULL OR data = ""'
            ).fetchall()
            for r in rows:
                payload = json.dumps({
                    'from': r['from_addr'] or '',
                    'reply_to': '',
                    'smtp_server': r['smtp_server'] or '',
                    'smtp_port': r['smtp_port'] or 587,
                    'smtp_use_tls': bool(r['smtp_use_tls']),
                    'template': r['template'] or '',
                })
                conn.execute('UPDATE presets SET data = ? WHERE token = ?', (payload, r['token']))


init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def schedule_job_cleanup(job_id, delay=JOB_RETENTION_SECONDS):
    def _cleanup():
        time.sleep(delay)
        with JOBS_LOCK:
            JOBS.pop(job_id, None)
    threading.Thread(target=_cleanup, daemon=True).start()


def run_job(job_id, rows, template_html, upload_folder, reply_to):
    job = JOBS[job_id]
    cond = job['cond']
    events = job['events']
    threads = []
    total = len(rows)

    def push(event):
        with cond:
            events.append(event)
            cond.notify_all()

    def send_one(row):
        recipient = row['email']
        subject = row['subject']
        try:
            with app.app_context():
                content = Template(template_html).substitute(row)
                msg = Message(subject=subject, recipients=[recipient], html=content,
                              reply_to=reply_to)
                attachment = row.get('attachment')
                if attachment:
                    if '.pdf' not in attachment:
                        attachment += '.pdf'
                    with app.open_resource(os.path.join(upload_folder, attachment)) as fp:
                        msg.attach(attachment, 'application/pdf', fp.read())
                mail.send(msg)
            push({'type': 'success', 'recevier': recipient, 'subject': subject})
        except Exception as e:
            push({'type': 'error', 'recevier': recipient, 'subject': subject, 'error': str(e)})

    try:
        for i, row in enumerate(rows):
            if not row.get('email') or not row.get('subject') or not row.get('name'):
                push({
                    'type': 'error',
                    'recevier': row.get('email'),
                    'subject': row.get('subject'),
                    'error': 'Missing email, subject or name',
                })
                continue
            t = threading.Thread(target=send_one, args=(row,))
            t.start()
            threads.append(t)
            if (i + 1) % BATCH_SIZE == 0 and (i + 1) < total:
                for bt in threads[-BATCH_SIZE:]:
                    bt.join()
                push({'type': 'pause', 'seconds': BATCH_SLEEP_SECONDS})
                time.sleep(BATCH_SLEEP_SECONDS)

        for t in threads:
            t.join()

        try:
            shutil.rmtree(upload_folder)
        except OSError as e:
            print("Error: %s : %s" % (upload_folder, e.strerror))

        push({'type': 'done'})
    except Exception as e:
        push({'type': 'done', 'error': str(e)})
    finally:
        with cond:
            job['done'] = True
            cond.notify_all()
        schedule_job_cleanup(job_id)


@app.route('/', methods=['GET', 'POST'])
def index():
    if flask.request.method != 'POST':
        return flask.render_template('index.html', preset=DEFAULT_PRESET, preset_token=None)

    UPLOAD_FOLDER: str = os.path.join(path, 'uploads' + str(datetime.now().timestamp()))
    if not os.path.isdir(UPLOAD_FOLDER):
        os.mkdir(UPLOAD_FOLDER)
    _data = flask.request.form.to_dict()

    app.config['MAIL_SERVER'] = _data.get('smtp_server')
    app.config['MAIL_PORT'] = int(_data.get('smtp_port', 587))
    app.config['MAIL_USE_TLS'] = _data.get('smtp_use_tls') == 'on'
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_USERNAME'] = _data.get('email')
    app.config['MAIL_PASSWORD'] = _data.get('apppw')
    app.config['MAIL_DEFAULT_SENDER'] = _data.get('from')
    reply_to = (_data.get('reply_to') or '').strip() or None
    preset_token = (_data.get('preset_token') or '').strip() or None
    mail.init_app(app)

    if 'files[]' in flask.request.files:
        for file in flask.request.files.getlist('files[]'):
            if file and allowed_file(file.filename):
                file.save(os.path.join(UPLOAD_FOLDER, file.filename))  # type: ignore

    csvfile = flask.request.files['csv']
    rows = []
    if csvfile and allowed_file(csvfile.filename):
        csvfile.save(os.path.join(UPLOAD_FOLDER, csvfile.filename))  # type: ignore
        with open(os.path.join(UPLOAD_FOLDER, csvfile.filename), encoding='utf-8-sig', newline='') as f:  # type: ignore
            rows = list(csv.DictReader(f))

    template_html = markdown(_data['template'].replace('\r\n', '<br>'))

    job_id = secrets.token_urlsafe(8)
    with JOBS_LOCK:
        JOBS[job_id] = {
            'events': [],
            'done': False,
            'cond': threading.Condition(),
            'total': len(rows),
        }

    worker = threading.Thread(
        target=run_job,
        args=(job_id, rows, template_html, UPLOAD_FOLDER, reply_to),
        daemon=True,
    )
    worker.start()

    return flask.render_template('finish.html', job_id=job_id, total=len(rows), preset_token=preset_token)


@app.route('/stream/<job_id>')
def stream(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        flask.abort(404)
    cond = job['cond']
    events = job['events']

    last_id_raw = (
        flask.request.headers.get('Last-Event-ID')
        or flask.request.args.get('lastEventId')
    )
    try:
        cursor = int(last_id_raw) + 1 if last_id_raw is not None else 0
    except (TypeError, ValueError):
        cursor = 0
    if cursor < 0:
        cursor = 0

    def gen():
        nonlocal cursor
        yield 'retry: 3000\n\n'
        while True:
            evt = None
            event_id = None
            with cond:
                if cursor >= len(events) and not job['done']:
                    cond.wait(timeout=STREAM_KEEPALIVE_SECONDS)
                if cursor < len(events):
                    event_id = cursor
                    evt = events[cursor]
                    cursor += 1
            if evt is None:
                if job['done']:
                    return
                yield ': keepalive\n\n'
                continue
            yield f'id: {event_id}\ndata: {json.dumps(evt)}\n\n'
            if evt.get('type') == 'done':
                return

    headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
    }
    return flask.Response(gen(), mimetype='text/event-stream', headers=headers)


@app.route('/preset/save', methods=['POST'])
def save_preset():
    data = flask.request.form
    token = secrets.token_urlsafe(6)
    payload = json.dumps({
        'from': data.get('from', ''),
        'reply_to': data.get('reply_to', ''),
        'smtp_server': data.get('smtp_server', ''),
        'smtp_port': int(data.get('smtp_port') or 587),
        'smtp_use_tls': data.get('smtp_use_tls') == 'on',
        'template': data.get('template', ''),
    })
    with get_db() as conn:
        conn.execute(
            'INSERT INTO presets (token, data, created_at) VALUES (?, ?, ?)',
            (token, payload, datetime.now(timezone.utc).isoformat()),
        )
    share_url = flask.url_for('load_preset', token=token, _external=True)
    return flask.jsonify({'token': token, 'url': share_url})


@app.route('/p/<token>')
def load_preset(token):
    with get_db() as conn:
        row = conn.execute('SELECT data FROM presets WHERE token = ?', (token,)).fetchone()
    if row is None or not row['data']:
        flask.abort(404)
    preset = {**DEFAULT_PRESET, **json.loads(row['data'])}
    return flask.render_template('index.html', preset=preset, preset_token=token)


if __name__ == '__main__':
    app.run(threaded=True, port=5000, debug=True)
