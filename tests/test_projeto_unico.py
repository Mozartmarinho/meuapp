#!/usr/bin/env python3
"""Garante um único app.py e o atalho que puxa a main do GitHub."""
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class ProjetoUnicoTest(unittest.TestCase):
    def test_nao_existem_copias_updated(self):
        for nome in (
            'app_updated.py',
            'routes_updated.py',
            'models_updated.py',
            'init_db_updated.py',
            'config.py',
            'migrar_sistema.py',
            'README_UPDATED.md',
        ):
            self.assertFalse(
                os.path.exists(os.path.join(ROOT, nome)),
                'cópia antiga ainda no repo: ' + nome,
            )

    def test_atalho_mata_app_antigo_e_puxa_main(self):
        bat = os.path.join(ROOT, 'iniciar_meuapp.bat')
        with open(bat, encoding='utf-8', errors='replace') as fh:
            texto = fh.read()
        self.assertNotIn('MeuApp - Inicializacao', texto)
        self.assertIn('Encerrando app.py antigo', texto)
        self.assertIn('origin/main', texto)
        self.assertIn('reset --hard origin/main', texto)
        self.assertIn('http://127.0.0.1/nutricao', texto)
        self.assertIn('MEUAPP_BOOTSTRAPPED', texto)
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'app.py')))
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'scripts', 'desktop_sao_geraldo.ps1')))


if __name__ == '__main__':
    unittest.main()
