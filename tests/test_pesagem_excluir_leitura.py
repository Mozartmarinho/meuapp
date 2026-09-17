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

    def _criar_leitura(self, peso=10.0, cliente='ANGRA POOL', quando=None):
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
            data_leitura=quando or datetime.now(),
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

    def test_agente_lista_enviados_do_dia_com_api_key(self):
        hoje = self._criar_leitura(peso=12.5, cliente='HOTEL SOL', quando=datetime.now())
        ontem = self._criar_leitura(peso=3.0, cliente='OUTRO DIA', quando=datetime(2026, 8, 24, 10, 0, 0))
        with self.client.session_transaction() as sess:
            sess.clear()
        hoje_iso = datetime.now().strftime('%Y-%m-%d')
        resp = self.client.get(
            '/api/pesagem/leituras',
            headers={'X-API-Key': 'saogeraldo-pesagem-2025'},
            query_string={'data_de': hoje_iso, 'data_ate': hoje_iso, 'balanca': 'BAL-01'},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        ids = [row['id'] for row in (data.get('leituras') or [])]
        self.assertIn(hoje.id, ids)
        self.assertNotIn(ontem.id, ids)
        row = next(r for r in data['leituras'] if r['id'] == hoje.id)
        self.assertEqual(row.get('cliente_nome'), 'HOTEL SOL')
        self.assertAlmostEqual(float(row.get('peso_bruto')), 12.5)

    def test_agente_exclui_enviado_com_api_key(self):
        leitura = self._criar_leitura(peso=8.0)
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
        db.session.expire_all()
        self.assertIsNone(PesagemLeitura.query.get(lid))

    def test_agente_lista_sem_filtro_data_ainda_traz_hoje(self):
        hoje = self._criar_leitura(peso=9.0, cliente='CCD', quando=datetime.now())
        with self.client.session_transaction() as sess:
            sess.clear()
        resp = self.client.get(
            '/api/pesagem/leituras',
            headers={'X-API-Key': 'saogeraldo-pesagem-2025'},
            query_string={'limit': 200},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        ids = [row['id'] for row in (data.get('leituras') or [])]
        self.assertIn(hoje.id, ids)
        with self.client.session_transaction() as sess:
            sess.clear()
        resp = self.client.get('/api/pesagem/leituras')
        self.assertEqual(resp.status_code, 401)

    def test_agente_edita_pesado_com_api_key(self):
        leitura = self._criar_leitura(peso=8.0, cliente='ANGRA POOL')
        outro = PesagemCliente(nome='CCD')
        db.session.add(outro)
        db.session.commit()
        lid = leitura.id
        with self.client.session_transaction() as sess:
            sess.clear()
        resp = self.client.put(
            f'/api/pesagem/leituras/{lid}',
            headers={'X-API-Key': 'saogeraldo-pesagem-2025'},
            json={
                'cliente_id': outro.id,
                'cliente_nome': 'CCD',
                'peso_liquido': 65.0,
                'tara': 0.0,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        db.session.expire_all()
        atual = PesagemLeitura.query.get(lid)
        self.assertEqual(atual.cliente_id, outro.id)
        self.assertEqual(atual.cliente_nome, 'CCD')
        self.assertAlmostEqual(atual.peso_liquido, 65.0)
        self.assertAlmostEqual(atual.peso, 65.0)


if __name__ == '__main__':
    unittest.main()
