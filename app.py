import flask
import os
import csv
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

app = flask.Flask(__name__)
app.config.from_object('config')
mail = Mail()

path = os.getcwd()
ALLOWED_EXTENSIONS = set(['csv', 'pdf'])
DB_PATH = os.path.join(path, 'presets.db')

DEFAULT_TEMPLATE = "Dear $name,\nThanks for using this service."
DEFAULT_PRESET = {
    'from': '',
    'smtp_server': '',
    'smtp_port': 587,
    'smtp_use_tls': True,
    'template': DEFAULT_TEMPLATE,
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS presets (
                token TEXT PRIMARY KEY,
                from_addr TEXT,
                smtp_server TEXT,
                smtp_port INTEGER,
                smtp_use_tls INTEGER,
                template TEXT,
                created_at TEXT
            )
        ''')


init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/', methods=['GET', 'POST'])
def index():
    @flask.copy_current_request_context
    def send_mail(recevier_array, subject, html_content, upload_folder, attachment):
        try:
            msg = Message(subject=subject, recipients=recevier_array, html=html_content)

            if attachment is not None:
                if ".pdf" not in attachment:
                    attachment += ".pdf"
                with app.open_resource(os.path.join(upload_folder, attachment)) as fp:
                    msg.attach(attachment, "application/pdf", fp.read())
            print(msg)
            mail.send(msg)
            success.append({"recevier": recevier_array[0], "subject": subject})
        except:
            error.append({"recevier": recevier_array[0], "subject": subject})
    error = []
    success = []
    threads = []
    if flask.request.method == 'POST':
        UPLOAD_FOLDER: str = os.path.join(path, 'uploads'+str(datetime.now().timestamp()))
        if not os.path.isdir(UPLOAD_FOLDER):
            os.mkdir(UPLOAD_FOLDER)
        _data = flask.request.form.to_dict()

        # Configure SMTP settings from user input
        app.config['MAIL_SERVER'] = _data.get('smtp_server')
        app.config['MAIL_PORT'] = int(_data.get('smtp_port', 587))
        app.config['MAIL_USE_TLS'] = _data.get('smtp_use_tls') == 'on'
        app.config['MAIL_USE_SSL'] = False  # Set to True if using port 465
        app.config['MAIL_USERNAME'] = _data.get('email')
        app.config['MAIL_PASSWORD'] = _data.get('apppw')
        app.config['MAIL_DEFAULT_SENDER'] = _data.get('from')
        mail.init_app(app)
        csvfile = flask.request.files['csv']
        if 'files[]' in flask.request.files:
            files = flask.request.files.getlist('files[]')
            for file in files:
                if file and allowed_file(file.filename):
                    filename = file.filename
                    file.save(os.path.join(UPLOAD_FOLDER, filename)) # type: ignore
        if csvfile and allowed_file(csvfile.filename):
            filename = csvfile.filename
            csvfile.save(os.path.join(UPLOAD_FOLDER, filename)) # type: ignore
            with open(os.path.join(UPLOAD_FOLDER, csvfile.filename), encoding='utf-8', newline='') as csvfile_saved: # type: ignore
                reader = csv.DictReader(csvfile_saved)
                _data['template'] = markdown(_data['template'].replace("\r\n","<br>"))
                rows = list(reader)
                total = len(rows)
                for i, row in enumerate(rows):
                    content_tmpl = Template(_data['template'])
                    attachment = row.get('attachment', None)
                    t = threading.Thread(target = send_mail,args=([row['email']], row['subject'], content_tmpl.substitute(row), UPLOAD_FOLDER, attachment))
                    t.start()
                    threads.append(t)
                    if (i + 1) % BATCH_SIZE == 0 and (i + 1) < total:
                        for bt in threads[-BATCH_SIZE:]:
                            bt.join()
                        time.sleep(BATCH_SLEEP_SECONDS)
        for t in threads:
            t.join()
        try:
            shutil.rmtree(UPLOAD_FOLDER)
        except OSError as e:
            print("Error: %s : %s" % (UPLOAD_FOLDER, e.strerror))
        return flask.render_template('finish.html', success = success, error = error)
    else:
        return flask.render_template('index.html', preset=DEFAULT_PRESET)


@app.route('/preset/save', methods=['POST'])
def save_preset():
    data = flask.request.form
    token = secrets.token_urlsafe(6)
    with get_db() as conn:
        conn.execute(
            'INSERT INTO presets (token, from_addr, smtp_server, smtp_port, smtp_use_tls, template, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                token,
                data.get('from', ''),
                data.get('smtp_server', ''),
                int(data.get('smtp_port') or 587),
                1 if data.get('smtp_use_tls') == 'on' else 0,
                data.get('template', ''),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    share_url = flask.url_for('load_preset', token=token, _external=True)
    return flask.jsonify({'token': token, 'url': share_url})


@app.route('/p/<token>')
def load_preset(token):
    with get_db() as conn:
        row = conn.execute(
            'SELECT from_addr, smtp_server, smtp_port, smtp_use_tls, template '
            'FROM presets WHERE token = ?',
            (token,),
        ).fetchone()
    if row is None:
        flask.abort(404)
    preset = {
        'from': row['from_addr'],
        'smtp_server': row['smtp_server'],
        'smtp_port': row['smtp_port'],
        'smtp_use_tls': bool(row['smtp_use_tls']),
        'template': row['template'],
    }
    return flask.render_template('index.html', preset=preset)


if __name__ == '__main__':
    app.run(threaded=True, port=5000, debug=True)
