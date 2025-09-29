from app import create_app
from models import db, Usuario

app = create_app()
with app.app_context():
    db.create_all()
    users = Usuario.query.all()
    print("Users found:")
    for user in users:
        print(f"ID: {user.id}, Email: {user.email}, Senha: {user.senha}, Nome: {user.nome}")
    if not users:
        print("No users found. Attempting to create default admin...")
        admin = Usuario(
            nome='Admin',
            email='admin@example.com',
            senha='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print("Default admin created.")
    else:
        print("Tables and users verified.")
