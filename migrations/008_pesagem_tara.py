"""Adiciona tara, peso_bruto e peso_liquido em pesagem_leituras."""


def run(engine):
    from app import create_app, ensure_pesagem_schema
    from models import db
    import models_pesagem  # noqa: F401

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_pesagem_schema()
    print("Colunas tara/peso_bruto/peso_liquido OK")
