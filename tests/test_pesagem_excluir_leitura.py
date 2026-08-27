#!/usr/bin/env python3
"""Exclusão de lançamento no dashboard de pesagem."""
import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db, Usuario  # noqa: E402
from models_pesagem import PesagemBalanca, PesagemCliente, PesagemLeitura  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402


class ExcluirLancamentoPesagemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cls.client = cls.app.test_client()
        user = Usuario(
            nome='Admin Pesagem',
            email='pesagem-admin@test.local',
            senha=generate_password_hash('admin'),
            tipo='admin',
            is_master=True,
            perm_pesagem=True,
            ativo=True,
        )
        db.session.add(user)
        db.session.commit()
        cls.user_id = user.id

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id

    def _criar_leitura(self, peso=10.0, cliente='ANGRA POOL', quando=None, balanca_codigo='BAL-01'):
        cli = PesagemCliente(nome=cliente)
        bal = PesagemBalanca.query.filter_by(codigo=balanca_codigo).first()
        if not bal:
            bal = PesagemBalanca(codigo=balanca_codigo, nome='Principal', local='Recepção', ativo=True)
            db.session.add(bal)
            db.session.flush()
        db.session.add(cli)
        db.session.flush()
        leitura = PesagemLeitura(
            balanca_id=bal.id,
            balanca_codigo=bal.codigo,
            peso=peso,
            unidade='kg',
            tara=0.0,
            peso_bruto=peso,
            peso_liquido=peso,
            estavel=True,
            origem='agente',
            cliente_id=cli.id,
            cliente_nome=cli.nome,
            data_leitura=quando or datetime(2026, 8, 24, 16, 53, 48),
        )
        db.session.add(leitura)
        db.session.commit()
        return leitura

    def test_dashboard_tem_botao_excluir(self):
        leitura = self._criar_leitura()
        html = self.client.get('/pesagem').get_data(as_text=True)
        self.assertIn('>Excluir</th>', html)
        self.assertIn('excluirLeitura(', html)
        self.assertIn(f'excluirLeitura({leitura.id}', html)
        self.assertIn('/api/pesagem/leituras/', html)

    def test_excluir_remove_lancamento(self):
        leitura = self._criar_leitura(peso=0.5)
        lid = leitura.id
        resp = self.client.delete(f'/api/pesagem/leituras/{lid}')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('id'), lid)
        db.session.expire_all()
        self.assertIsNone(PesagemLeitura.query.get(lid))

    def test_excluir_inexistente_404(self):
        resp = self.client.delete('/api/pesagem/leituras/999999')
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertFalse(data.get('ok'))

    def test_excluir_sem_login_redireciona(self):
        leitura = self._criar_leitura(peso=1.0)
        with self.client.session_transaction() as sess:
            sess.clear()
        resp = self.client.delete(f'/api/pesagem/leituras/{leitura.id}')
        self.assertIn(resp.status_code, (302, 401))
        db.session.expire_all()
        self.assertIsNotNone(PesagemLeitura.query.get(leitura.id))

    def test_agente_lista_envios_do_dia_com_api_key(self):
        hoje = datetime.now()
        ontem = hoje - timedelta(days=1)
        de_hoje = self._criar_leitura(peso=3.5, cliente='HMLJ', quando=hoje)
        de_ontem = self._criar_leitura(peso=9.0, cliente='OUTRO', quando=ontem)
        outra = self._criar_leitura(
            peso=1.1, cliente='OUTRA BAL', quando=hoje, balanca_codigo='BAL-99'
        )
        with self.client.session_transaction() as sess:
            sess.clear()
        hoje_iso = hoje.strftime('%Y-%m-%d')
        resp = self.client.get(
            '/api/pesagem/leituras',
            query_string={
                'data_de': hoje_iso,
                'data_ate': hoje_iso,
                'balanca': 'BAL-01',
                'limit': 200,
            },
            headers={'X-API-Key': 'saogeraldo-pesagem-2025'},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        ids = {row['id'] for row in data.get('leituras') or []}
        self.assertIn(de_hoje.id, ids)
        self.assertNotIn(de_ontem.id, ids)
        self.assertNotIn(outra.id, ids)
        row = next(r for r in data['leituras'] if r['id'] == de_hoje.id)
        self.assertEqual(row['cliente_nome'], 'HMLJ')
        self.assertEqual(row['peso_bruto'], 3.5)
        self.assertEqual(row['tara'], 0.0)
        self.assertEqual(row['peso_liquido'], 3.5)

    def test_agente_excluir_com_api_key(self):
        leitura = self._criar_leitura(peso=2.25, cliente='HMLJ', quando=datetime.now())
        lid = leitura.id
        with self.client.session_transaction() as sess:
            sess.clear()
        resp = self.client.delete(
            f'/api/pesagem/leituras/{lid}',
            headers={'X-API-Key': 'saogeraldo-pesagem-2025'},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('id'), lid)
        db.session.expire_all()
        self.assertIsNone(PesagemLeitura.query.get(lid))

    def test_lista_sem_auth_401(self):
        with self.client.session_transaction() as sess:
            sess.clear()
        resp = self.client.get('/api/pesagem/leituras')
        self.assertIn(resp.status_code, (302, 401))
        if resp.status_code == 401:
            data = resp.get_json()
            self.assertFalse(data.get('ok'))


if __name__ == '__main__':
    unittest.main()
