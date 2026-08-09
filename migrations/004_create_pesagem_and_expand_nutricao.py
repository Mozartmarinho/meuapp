"""Garante tabelas expandidas de Nutrição e módulo de Pesagem."""


def run(engine):
    from app import create_app
    from models import db
    import models_nutricao  # noqa: F401
    import models_pesagem  # noqa: F401
    from nutricao_service import seed_nutricao
    from routes_pesagem import seed_pesagem

    app = create_app()
    with app.app_context():
        db.create_all()
        seed_nutricao()
        seed_pesagem()
    print("Tabelas Nutrição/Pesagem OK + seed")
