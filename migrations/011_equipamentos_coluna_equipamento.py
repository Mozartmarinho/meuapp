"""Cria equipamentos.equipamento se o MySQL legado não tiver a coluna."""


def run(engine):
    from app import create_app, ensure_equipamentos_schema

    app = create_app()
    with app.app_context():
        ensure_equipamentos_schema()
    print('equipamentos.equipamento OK (criada se faltava; listagem nao depende dela)')
