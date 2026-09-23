"""Linux: ramais, coluna local em equipamentos, schema de boot do Gunicorn."""


def run(engine):
    from app import create_app
    from app import (
        ensure_usuarios_schema,
        ensure_clientes_schema,
        ensure_chamados_schema,
        ensure_equipamentos_schema,
        ensure_pesagem_schema,
        ensure_setores_funcao_schema,
        ensure_acesso_equipamentos_schema,
        ensure_ramais_schema,
        ensure_tecnicos_schema,
        ensure_operacao_chamados_schema,
    )
    from models import db

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_usuarios_schema()
        ensure_clientes_schema()
        ensure_chamados_schema()
        ensure_equipamentos_schema()
        ensure_pesagem_schema()
        ensure_setores_funcao_schema()
        ensure_acesso_equipamentos_schema()
        ensure_ramais_schema()
        ensure_tecnicos_schema()
        ensure_operacao_chamados_schema()
    print('Migration 010 (ramais/local) OK')
