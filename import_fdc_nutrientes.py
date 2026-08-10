#!/usr/bin/env python
"""CLI: importa FoodData Central Foundation Foods (JSON ou ZIP) para MySQL.

Exemplos:
  python import_fdc_nutrientes.py --zip "c:\\Users\\Mozart\\Downloads\\FoodData_Central_foundation_food_json_2026-04-30.zip"
  python import_fdc_nutrientes.py --json caminho\\foundation.json
"""
from __future__ import annotations

import argparse
import sys

from app import create_app
from nutricao_fdc_import import DEFAULT_TABELA_NOME, import_fdc_foundation_foods


def main(argv=None):
    p = argparse.ArgumentParser(description='Importa tabela FDC Foundation Foods')
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument('--zip', dest='zip_path', help='Caminho do ZIP FoodData Central')
    src.add_argument('--json', dest='json_path', help='Caminho do JSON FoundationFoods')
    p.add_argument(
        '--tabela',
        default=DEFAULT_TABELA_NOME,
        help=f'Nome da tabela nutricional (default: {DEFAULT_TABELA_NOME})',
    )
    p.add_argument(
        '--keep-other-tables',
        action='store_true',
        help='Não desativa outras tabelas de nutrientes',
    )
    p.add_argument(
        '--keep-missing',
        action='store_true',
        help='Não desativa alimentos ausentes no arquivo',
    )
    p.add_argument('--batch-size', type=int, default=25, help='Commit a cada N alimentos')
    args = p.parse_args(argv)

    path = args.zip_path or args.json_path
    app = create_app()
    with app.app_context():
        from models import db
        db.create_all()
        result = import_fdc_foundation_foods(
            path,
            tabela_nome=args.tabela,
            set_official=not args.keep_other_tables,
            deactivate_missing=not args.keep_missing,
            batch_size=max(1, args.batch_size),
        )
    print('Importação concluída:')
    for k, v in result.items():
        print(f'  {k}: {v}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
