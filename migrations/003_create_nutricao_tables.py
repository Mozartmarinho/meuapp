"""Garante tabelas do módulo Nutrição e dados iniciais."""


def run(engine):
    # Usa o app Flask para registrar metadados e create_all
    from app import create_app
    from models import db
    import models_nutricao  # noqa: F401
    from nutricao_service import seed_nutricao

    app = create_app()
    with app.app_context():
        db.create_all()
        seed_nutricao()
    print("Tabelas de nutrição OK + seed")
