"""Adequa MySQL legado ao GitHub: hops, setores, pesagem clientes, fotos e status TCP."""


def run(engine):
    from app import create_app
    from models import db

    app = create_app()
    with app.app_context():
        db.create_all()
        from app import (
            ensure_usuarios_schema,
            ensure_clientes_schema,
            ensure_chamados_schema,
            ensure_equipamentos_schema,
            ensure_pesagem_schema,
            ensure_setores_funcao_schema,
            ensure_acesso_equipamentos_schema,
        )
        ensure_usuarios_schema()
        ensure_clientes_schema()
        ensure_chamados_schema()
        ensure_equipamentos_schema()
        ensure_pesagem_schema()
        ensure_setores_funcao_schema()
        ensure_acesso_equipamentos_schema()
    print('Schema Linux (chamados/hops/setores/pesagem/acesso) OK')
