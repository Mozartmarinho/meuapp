from app import create_app
from models import db, Usuario
from password_utils import generate_password_hash

app = create_app()
with app.app_context():
    admin = Usuario.query.filter_by(email='admin@example.com').first()
    if admin and not admin.senha.startswith('pbkdf2:sha256'):
        admin.senha = generate_password_hash('admin')
        db.session.commit()
        print("Admin password hashed successfully")
    else:
        print("Admin password already hashed or not found")
