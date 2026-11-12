#!/usr/bin/env python
"""Importa TACO (Tabela Brasileira de Composição de Alimentos, 4ª edição)."""
from __future__ import annotations

import argparse
import sys

from app import create_app
from nutricao_taco_import import DEFAULT_TABELA_NOME, import_taco_table


def main(argv=None):
    p = argparse.ArgumentParser(description='Importa tabela TACO (alimentos brasileiros)')
    p.add_argument('--csv', dest='csv_path', help='Caminho do CSV taco_composicao.csv')
    p.add_argument('--tabela', default=DEFAULT_TABELA_NOME)
    p.add_argument('--official', action='store_true', help='Desativa as outras tabelas')
    args = p.parse_args(argv)
    app = create_app()
    with app.app_context():
        from models import db
        db.create_all()
        result = import_taco_table(
            args.csv_path,
            tabela_nome=args.tabela,
            set_official=args.official,
        )
    print('Importação TACO concluída:')
    for k, v in result.items():
        print('  {}: {}'.format(k, v))
    return 0


if __name__ == '__main__':
    sys.exit(main())
