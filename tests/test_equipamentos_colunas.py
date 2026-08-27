#!/usr/bin/env python3
"""Ordem das colunas e endereço na coluna Local do cadastro de equipamentos."""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATE = os.path.join(ROOT, 'templates', 'equipamentos.html')
MODELS = os.path.join(ROOT, 'models.py')


class EquipamentosColunasTest(unittest.TestCase):
    def test_ordem_colunas_e_endereco_no_local(self):
        with open(TEMPLATE, encoding='utf-8') as fh:
            html = fh.read()
        thead = re.search(r'<thead>\s*<tr>(.*?)</tr>\s*</thead>', html, re.S)
        self.assertIsNotNone(thead)
        ths = [
            re.sub(r'<[^>]+>', '', t).strip()
            for t in re.findall(r'<th[^>]*>(.*?)</th>', thead.group(1), re.S)
        ]
        self.assertEqual(
            ths[:8],
            ['Código', 'Nome', 'Marca', 'Modelo', 'Cliente', 'Local', 'Setor', 'Data da compra'],
        )
        self.assertEqual(ths[8], 'Ações')
        self.assertIn("eq.cliente.endereco", html)
        self.assertIn("eq.cliente.nome if eq.cliente else '—'", html)
        tbody_start = html.find('<tbody>')
        tbody = html[tbody_start:html.find('</tbody>', tbody_start)]
        cliente_td = tbody.find("eq.cliente.nome if eq.cliente else '—'")
        endereco_td = tbody.find("endereco or '—'")
        self.assertGreater(cliente_td, 0)
        self.assertGreater(endereco_td, cliente_td)

    def test_to_dict_inclui_endereco_do_cliente(self):
        with open(MODELS, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn("'cliente_endereco': (self.cliente.endereco or '') if self.cliente else ''", src)


if __name__ == '__main__':
    unittest.main()
