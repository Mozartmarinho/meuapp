"""Importa TACO 4ª edição (alimentos brasileiros) para nut_*."""


def run(engine):
    from app import create_app
    from nutricao_taco_import import import_taco_table

    app = create_app()
    with app.app_context():
        result = import_taco_table(tabela_nome='TACO', set_official=False)
    print('TACO OK:', result.get('ativos'), 'alimentos')
