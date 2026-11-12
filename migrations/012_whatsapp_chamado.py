"""Cadastro WhatsApp da Gestão de Chamados."""


def run(engine):
    from app import create_app, ensure_whatsapp_chamado_schema

    app = create_app()
    with app.app_context():
        ensure_whatsapp_chamado_schema()
    print('Tabelas whatsapp_chamado_config / usuarios / logs OK')
