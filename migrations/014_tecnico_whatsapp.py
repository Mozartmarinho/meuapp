"""WhatsApp no cadastro de técnico para avisos de chamado."""


def run(engine):
    from app import create_app, ensure_tecnicos_schema

    app = create_app()
    with app.app_context():
        ensure_tecnicos_schema()
    print('Coluna chamado_tecnicos.whatsapp OK')
