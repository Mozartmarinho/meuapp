"""Colunas de lançamento de dieta no mapa (tipo, dieta_id, grupo)."""


def run(engine):
    from app import create_app
    from models import db
    import models_nutricao  # noqa: F401
    from nutricao_service import seed_nutricao

    app = create_app()
    with app.app_context():
        db.create_all()
        seed_nutricao(force=True)
    print("Colunas tipo_lancamento/dieta_id/lancamento_grupo_id no mapa OK")
