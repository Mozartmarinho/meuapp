#!/usr/bin/env python3
"""Exclusão de usuários no cadastro de Acessos."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import ChamadoTecnico, PermissaoMenu, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402


class ExcluirAcessoTest(unittest.TestCase):
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
        PermissaoMenu.query.delete()
        ChamadoTecnico.query.delete()
        Usuario.query.delete()
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

    def _operador(self, email='op@example.com'):
        user = Usuario(
            nome='Operador Teste',
            email=email,
            senha=generate_password_hash('x'),
            is_master=False,
            tipo='operador',
            ativo=True,
        )
        db.session.add(user)
        db.session.commit()
        return user

    def test_lista_tem_icone_lixeira(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('data-excluir-acesso', html)
        self.assertIn('fa-trash', html)
        self.assertIn('/acessos/0/excluir', html)

    def test_exclui_usuario_e_desvincula_tecnico(self):
        alvo = self._operador()
        db.session.add(ChamadoTecnico(
            nome='Operador Teste',
            email=alvo.email,
            usuario_id=alvo.id,
            ativo=True,
        ))
        db.session.add(PermissaoMenu(
            usuario_id=alvo.id,
            sistema='chamados',
            menu_key='dashboard',
            permitido=True,
        ))
        db.session.commit()
        tid = ChamadoTecnico.query.filter_by(email=alvo.email).first().id
        uid = alvo.id
        resp = self.client.post(
            f'/acessos/{uid}/excluir',
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertIsNone(Usuario.query.get(uid))
        tec = ChamadoTecnico.query.get(tid)
        self.assertIsNotNone(tec)
        self.assertIsNone(tec.usuario_id)
        self.assertEqual(PermissaoMenu.query.filter_by(usuario_id=uid).count(), 0)

    def test_nao_exclui_master(self):
        resp = self.client.post(
            f'/acessos/{self.admin.id}/excluir',
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['ok'])
        self.assertIsNotNone(Usuario.query.get(self.admin.id))

    def test_nao_exclui_a_si_mesmo(self):
        op = self._operador()
        op.perm_acesso = True
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['user_id'] = op.id
            sess['user_name'] = op.nome
        resp = self.client.post(
            f'/acessos/{op.id}/excluir',
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.get_json()['ok'])
        self.assertIsNotNone(Usuario.query.get(op.id))


if __name__ == '__main__':
    unittest.main()
