"""Colunas do backup geral diário na configuração de e-mail."""


def run(engine):
    from app import create_app
    from backup_service import ensure_backup_schema

    app = create_app()
    with app.app_context():
        ensure_backup_schema()
    print('Colunas de backup diário OK')
