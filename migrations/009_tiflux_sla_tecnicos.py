"""Cria tabelas de Tiflux: setores de técnicos, SLA, mesas, contratos, mensagens,
automações, base de conhecimento e colunas adicionais em chamados."""


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
        ensure_tecnicos_schema()
        ensure_operacao_chamados_schema()
    print('Migration 009 (Tiflux/SLA/Técnicos) OK')
