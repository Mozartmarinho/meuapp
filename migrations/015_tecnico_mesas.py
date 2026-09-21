"""Vínculo de técnico/gestor com uma ou mais mesas de serviço."""


def run(engine):
    from app import create_app, ensure_tecnicos_schema

    app = create_app()
    with app.app_context():
        ensure_tecnicos_schema()
    print('Tabela chamado_tecnico_mesas OK')
