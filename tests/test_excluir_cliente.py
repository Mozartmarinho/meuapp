#!/usr/bin/env python3
"""Exclusão de clientes no cadastro do portal."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import Chamado, Cliente, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402


class ExcluirClienteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def setUp(self):
        Chamado.query.delete()
        Usuario.query.delete()
        Cliente.query.delete()
        db.session.commit()
        self.admin = Usuario(
            nome='Mozart Admin',
            email='admin@example.com',
            senha=generate_password_hash('x'),
            is_master=True,
            perm_acesso=True,
            ativo=True,
        )
        db.session.add(self.admin)
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['user_name'] = self.admin.nome

    def _cliente(self, nome='Cliente Teste'):
        cli = Cliente(nome=nome, endereco='Rua Teste', ativo=True)
        db.session.add(cli)
        db.session.commit()
        return cli

    def test_lista_tem_icone_lixeira(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('data-excluir-cliente', html)
        self.assertIn('fa-trash', html)
        self.assertIn('/clientes/0/excluir', html)

    def test_exclui_cliente_sem_vinculos(self):
        cli = self._cliente()
        cid = cli.id
        self.admin.cliente_id = cid
        db.session.commit()
        resp = self.client.post(
            f'/clientes/{cid}/excluir',
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertIsNone(Cliente.query.get(cid))
        db.session.refresh(self.admin)
        self.assertIsNone(self.admin.cliente_id)

    def test_nao_exclui_cliente_com_chamado(self):
        cli = self._cliente()
        db.session.add(Chamado(
            numero_chamado='CH-1',
            cliente_id=cli.id,
            tipo_servico='Manutenção',
            tecnico_id=self.admin.id,
        ))
        db.session.commit()
        cid = cli.id
        resp = self.client.post(
            f'/clientes/{cid}/excluir',
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['ok'])
        self.assertIn('chamados', data.get('message') or '')
        self.assertIsNotNone(Cliente.query.get(cid))


if __name__ == '__main__':
    unittest.main()
