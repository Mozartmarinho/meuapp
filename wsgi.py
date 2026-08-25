from app import create_app, ensure_pesagem_schema

app = create_app()
application = app
with app.app_context():
    ensure_pesagem_schema()
