"""Garante tabela pesagem_clientes e colunas de cliente nas leituras."""


def run(engine):
    from app import create_app, ensure_pesagem_schema
    from models import db
    import models_pesagem  # noqa: F401

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_pesagem_schema()
    print("Tabela pesagem_clientes + colunas cliente nas leituras OK")
