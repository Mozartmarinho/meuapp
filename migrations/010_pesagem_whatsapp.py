"""Cria tabelas de configuração e envio WhatsApp da pesagem."""


def run(engine):
    from app import create_app, ensure_pesagem_schema
    from models import db
    import models_pesagem  # noqa: F401

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_pesagem_schema()
    print("Tabelas pesagem_whatsapp_destinos e pesagem_whatsapp_envios OK")
