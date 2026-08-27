#!/usr/bin/env python3
"""Exclusão de lançamento no dashboard de pesagem."""
import os
import sys
import unittest
from datetime import datetime

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

    def _criar_leitura(self, peso=10.0, cliente='ANGRA POOL'):
        cli = PesagemCliente(nome=cliente)
        bal = PesagemBalanca.query.filter_by(codigo='BAL-01').first()
        if not bal:
            bal = PesagemBalanca(codigo='BAL-01', nome='Principal', local='Recepção', ativo=True)
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
            data_leitura=datetime(2026, 8, 24, 16, 53, 48),
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


if __name__ == '__main__':
    unittest.main()
