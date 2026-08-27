"""Cria no MySQL as colunas do model Equipamento que a tabela ainda não tem.

  python scripts/alinhar_tabela_equipamentos.py

Ou no MySQL Workbench: rode scripts/alinhar_tabela_equipamentos.sql
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from db_config import forcar_colunas_equipamentos  # noqa: E402

if __name__ == '__main__':
    ok = forcar_colunas_equipamentos()
    if ok:
        print('OK: tabela equipamentos alinhada ao model (colunas faltantes criadas).')
        sys.exit(0)
    print('Não conectou no MySQL ou a tabela equipamentos não existe.')
    sys.exit(1)
