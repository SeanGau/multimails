import flask
import json
from flask_sqlalchemy import SQLAlchemy
app = flask.Flask(__name__)
app.config.from_object('config')
db = SQLAlchemy(app)

with open('./static/merged.json', newline='') as jsonfile:
    geojson = json.load(jsonfile)
    for feature in geojson['features']:
        temp = {
            "founder": feature['properties']['founder_id'],
            "data": feature['properties'],
            "geom": feature['geometry']['coordinates']
        }
        print(temp)
        db.session.execute(f"INSERT INTO public.monsters (founder,data,geom) VALUES({temp['founder']},'{json.dumps(temp['data'],ensure_ascii=True)}',ST_MakePoint({temp['geom'][0]},{temp['geom'][1]}))")
        db.session.commit()