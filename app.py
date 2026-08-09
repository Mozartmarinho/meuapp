from flask import Flask
from routes import main
from routes_nutricao import nutricao
from routes_pesagem import pesagem
from models import db, Usuario
from db_config import SQLALCHEMY_DATABASE_URI
import models_nutricao  # noqa: F401 — registra tabelas de nutrição
import models_pesagem  # noqa: F401 — registra tabelas de pesagem
import os


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'saogeraldo2025')
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    app.register_blueprint(main)
    app.register_blueprint(nutricao)
    app.register_blueprint(pesagem)

    return app


if __name__ == '__main__':
    from werkzeug.security import generate_password_hash

    app = create_app()
    with app.app_context():
        db.create_all()
        from nutricao_service import seed_nutricao
        from routes_pesagem import seed_pesagem
        seed_nutricao()
        seed_pesagem()
        if not Usuario.query.first():
            admin = Usuario(
                nome='Admin',
                email='admin@example.com',
                senha=generate_password_hash('admin'),
                tipo='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: email=admin@example.com, password=admin")

    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '80'))
    print(f"Servidor em http://{host}:{port}/ (acesse http://localhost/ )")
    app.run(host=host, port=port, debug=True)
