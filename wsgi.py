from app import create_app, ensure_pesagem_schema
from models import db
from whatsapp_pesagem import start_background

app = create_app()
application = app
with app.app_context():
    try:
        db.create_all()
    except Exception as exc:
        print(f"Aviso create_all: {exc}")
    try:
        ensure_pesagem_schema()
    except Exception as exc:
        print(f"Aviso schema pesagem: {exc}")
    try:
        from nutricao_tenant import ensure_nutricao_cliente_schema
        ensure_nutricao_cliente_schema()
    except Exception as exc:
        print(f"Aviso schema nutricao: {exc}")
    try:
        from nutricao_service import seed_nutricao
        seed_nutricao()
    except Exception as exc:
        print(f"Aviso seed nutricao: {exc}")
start_background(app)
