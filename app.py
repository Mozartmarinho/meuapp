from flask import Flask
from routes import main
from models import db, Usuario

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'saogeraldo2025'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///meuapp.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    app.register_blueprint(main)

    return app

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
        if not Usuario.query.first():
            from werkzeug.security import generate_password_hash
            admin = Usuario(
                nome='Admin',
                email='admin@example.com',
                senha=generate_password_hash('admin')  # Hashed password for security
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: email=admin@example.com, password=admin")
    app.run(debug=True)

