"""Cria tabelas do Sistema de Controle de Logística e coluna perm_logistica."""


def run(engine):
    from app import create_app, ensure_logistica_schema
    from models import db
    import models_logistica  # noqa: F401
    from logistica_service import seed_logistica

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_logistica_schema()
        seed_logistica()
    print("Tabelas logística OK")
