"""Cria tabelas novas da nutrição (grupo de clínicas, categorias, exclusões)."""


def run(engine):
    from app import create_app
    from models import db
    import models_nutricao  # noqa: F401
    from nutricao_tenant import ensure_nutricao_cliente_schema
    from nutricao_service import seed_nutricao

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_nutricao_cliente_schema()
        seed_nutricao(force=True)
    print("Grupo de clínicas, categorias de dieta e dietas excluídas OK")
