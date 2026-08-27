#!/usr/bin/env python3
"""GET /nutricao must serve the latest nutrition UI without HTML cache."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402


class NutricaoPaginaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_dashboard_tem_impressoes_novas_e_sem_cache(self):
        resp = self.client.get('/nutricao')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('MAPA DE PRODUÇÃO', html)
        self.assertIn('Impressão mapa da nutrição', html)
        self.assertIn('Impressão mapa distribuição', html)
        self.assertIn('/nutricao/impressao-mapa-distribuicao', html)
        self.assertIn('Selecione a clínica para ver o mapa', html)
        self.assertNotIn('filtroEnfermaria', html)
        self.assertIn('São Geraldo Service · meuapp', html)
        self.assertIn('projeto-versao-bar', html)
        cache = (resp.headers.get('Cache-Control') or '').lower()
        self.assertIn('no-store', cache)
        self.assertIn('text/html', resp.headers.get('Content-Type', ''))

    def test_rota_versao_nao_e_404(self):
        resp = self.client.get('/nutricao/versao')
        self.assertEqual(resp.status_code, 200)
        texto = resp.get_data(as_text=True)
        self.assertIn('meuapp', texto)
        self.assertIn('pasta', texto)

    def test_rotas_de_impressao_existem(self):
        mapa = self.client.get('/nutricao/impressao-mapa')
        dist = self.client.get('/nutricao/impressao-mapa-distribuicao')
        self.assertEqual(mapa.status_code, 200)
        self.assertEqual(dist.status_code, 200)
        self.assertIn('Impressão mapa da nutrição', mapa.get_data(as_text=True))
        self.assertIn('MAPA DISTRIBUIÇÃO', dist.get_data(as_text=True).upper())


if __name__ == '__main__':
    unittest.main()
