from flask import Flask
from routes import main
from models import db

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'saogeraldo2025'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:saogeraldo2025@127.0.0.1/meuappdb'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    app.register_blueprint(main)

    return app

