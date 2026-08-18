"""Catálogo de funções/setores (chamados e nutrição) e coluna usuarios.setor_nutricao."""


def run(engine):
    from app import create_app, ensure_usuarios_schema, ensure_setores_funcao_schema
    from models import db

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_usuarios_schema()
        ensure_setores_funcao_schema()
    print("setores_funcao + usuarios.setor_nutricao OK")
