"""Linux: marca/modelo equipamentos + tabelas refeicao acompanhante/funcionarios."""


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
        ensure_cameras_schema,
        ensure_portoes_schema,
        ensure_estoque_schema,
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
        ensure_cameras_schema()
        ensure_portoes_schema()
        ensure_estoque_schema()
        ensure_operacao_chamados_schema()
        from nutricao_tenant import ensure_nutricao_cliente_schema
        ensure_nutricao_cliente_schema()
    print('Migration 013 (marca/nutricao refeicoes) OK')
