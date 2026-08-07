from flask import Flask
from routes import main
from routes_nutricao import nutricao
from models import db, Usuario
from db_config import SQLALCHEMY_DATABASE_URI
import models_nutricao  # noqa: F401 — registra tabelas de nutrição


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'saogeraldo2025'
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    app.register_blueprint(main)
    app.register_blueprint(nutricao)

    return app

if __name__ == '__main__':
    import os

    app = create_app()
    with app.app_context():
        db.create_all()
        from nutricao_service import seed_nutricao
        seed_nutricao()
        if not Usuario.query.first():
            from werkzeug.security import generate_password_hash
            admin = Usuario(
                nome='Admin',
                email='admin@example.com',
                senha=generate_password_hash('admin')
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: email=admin@example.com, password=admin")

    # Porta 80 (padrão HTTP). No Windows, rode como Administrador.
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '80'))
    print(f"Servidor em http://{host}:{port}/ (acesse http://localhost/ )")
    app.run(host=host, port=port, debug=True)
