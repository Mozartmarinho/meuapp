#!/usr/bin/env python3
"""Dashboard: cumprimento usa o nome do técnico, não o setor."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import ChamadoTecnico, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402
from routes import _primeiro_nome  # noqa: E402


class DashboardPrimeiroNomeTest(unittest.TestCase):
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

    def tearDown(self):
        ChamadoTecnico.query.delete()
        Usuario.query.delete()
        db.session.commit()

    def _usuario(self, nome, email, setor=None):
        user = Usuario(
            nome=nome,
            email=email,
            senha=generate_password_hash('x'),
            setor=setor,
            ativo=True,
        )
        db.session.add(user)
        db.session.commit()
        return user

    def test_usa_primeiro_nome_do_tecnico_vinculado(self):
        user = self._usuario('Informática', 'tec@example.com', setor='Informática')
        db.session.add(ChamadoTecnico(
            nome='Mozart Marinho',
            email='tec@example.com',
            usuario_id=user.id,
            ativo=True,
        ))
        db.session.commit()
        self.assertEqual(_primeiro_nome(user), 'Mozart')

    def test_sem_email_no_tecnico_usa_nome_de_acessos(self):
        user = self._usuario('João da Silva', 'joao@example.com', setor='Informática')
        db.session.add(ChamadoTecnico(
            nome='Mozart Marinho',
            email=None,
            usuario_id=user.id,
            ativo=True,
        ))
        db.session.commit()
        self.assertEqual(_primeiro_nome(user), 'João')

    def test_sem_tecnico_usa_nome_cadastrado_em_acessos(self):
        user = self._usuario('Informática São Geraldo', 'master@example.com', setor='Informática')
        self.assertEqual(_primeiro_nome(user), 'Informática')

    def test_pessoa_sem_setor_no_nome_mantem_primeiro_nome(self):
        user = self._usuario('João da Silva', 'joao@example.com', setor='Informática')
        self.assertEqual(_primeiro_nome(user), 'João')

    def test_sem_usuario_retorna_ola(self):
        self.assertEqual(_primeiro_nome(None), 'olá')

    def test_dashboard_html_mostra_nome_do_tecnico(self):
        user = self._usuario('Informática', 'dash@example.com', setor='Informática')
        user.is_master = True
        user.perm_chamados = True
        db.session.add(ChamadoTecnico(
            nome='Mozart Marinho',
            email='dash@example.com',
            usuario_id=user.id,
            ativo=True,
        ))
        db.session.commit()
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['user_name'] = user.nome
        resp = client.get('/dashboard')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Bom te ver de volta', html)
        self.assertIn('<span>Mozart</span>', html)
        self.assertNotIn('<span>Informática</span>', html)


if __name__ == '__main__':
    unittest.main()
