#!/usr/bin/env python3
"""Cria a coluna equipamentos.equipamento no MySQL. Rode: python scripts/forcar_coluna_equipamento.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from db_config import forcar_coluna_equipamento  # noqa: E402

if __name__ == '__main__':
    ok = forcar_coluna_equipamento()
    print('OK: equipamentos.equipamento' if ok else 'Pulou ou falhou (veja o aviso acima).')
    sys.exit(0)
