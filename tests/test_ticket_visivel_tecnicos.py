#!/usr/bin/env python3
"""Ticket aberto entra na fila de todos os técnicos do sistema."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import Chamado, ChamadoTecnico, Cliente, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402
from routes import _pendencias_chamados, _query_chamados_usuario  # noqa: E402


class TicketVisivelTecnicosTest(unittest.TestCase):
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
        ChamadoTecnico.query.delete()
        Usuario.query.delete()
        Cliente.query.delete()
        db.session.commit()
        self.cli = Cliente(nome='Hospital Teste', ativo=True, habilitado_chamados=True)
        db.session.add(self.cli)
        db.session.commit()

    def _usuario(self, nome, email, **kwargs):
        dados = dict(
            nome=nome,
            email=email,
            senha=generate_password_hash('x'),
            ativo=True,
            perm_chamados=True,
        )
        dados.update(kwargs)
        user = Usuario(**dados)
        db.session.add(user)
        db.session.commit()
        return user

    def _tecnico(self, nome, email, **kwargs):
        user = self._usuario(nome, email, **kwargs)
        db.session.add(ChamadoTecnico(
            nome=nome,
            email=email,
            usuario_id=user.id,
            ativo=True,
        ))
        db.session.commit()
        return user

    def _chamado(self, opener, numero='OS000001', status='Pendente'):
        chamado = Chamado(
            numero_chamado=numero,
            cliente_id=self.cli.id,
            tipo_servico='Manutenção',
            descricao='Não liga',
            status=status,
            tecnico_id=opener.id,
        )
        db.session.add(chamado)
        db.session.commit()
        return chamado

    def _login(self, user):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['user_name'] = user.nome
        return client

    def test_tecnico_ve_ticket_aberto_por_outro(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec_a = self._tecnico('Ana Técnica', 'ana@example.com')
        tec_b = self._tecnico('Bruno Técnico', 'bruno@example.com')
        chamado = self._chamado(opener)

        ids_a = {c.id for c in _query_chamados_usuario(tec_a).all()}
        ids_b = {c.id for c in _query_chamados_usuario(tec_b).all()}
        self.assertIn(chamado.id, ids_a)
        self.assertIn(chamado.id, ids_b)

    def test_nao_tecnico_nao_ve_ticket_de_outro(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        outro = self._usuario('Operador', 'op@example.com')
        chamado = self._chamado(opener)
        ids = {c.id for c in _query_chamados_usuario(outro).all()}
        self.assertNotIn(chamado.id, ids)

    def test_tecnico_nao_ve_ticket_fechado_de_outro(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana Técnica', 'ana@example.com')
        chamado = self._chamado(opener, status='Concluído')
        ids = {c.id for c in _query_chamados_usuario(tec).all()}
        self.assertNotIn(chamado.id, ids)

    def test_lista_e_detalhe_para_tecnico(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana Técnica', 'ana@example.com')
        chamado = self._chamado(opener, numero='OS999111')
        client = self._login(tec)
        lista = client.get('/chamados')
        self.assertEqual(lista.status_code, 200)
        html = lista.get_data(as_text=True)
        self.assertIn('OS999111', html)
        detalhe = client.get(f'/chamados/{chamado.id}')
        self.assertEqual(detalhe.status_code, 200)
        self.assertIn('OS999111', detalhe.get_data(as_text=True))

    def test_pendencia_ticket_aberto_para_tecnico(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana Técnica', 'ana@example.com')
        chamado = self._chamado(opener)
        with self.app.test_request_context('/'):
            itens = _pendencias_chamados(tec)
        ids = {i['id'] for i in itens}
        self.assertIn(chamado.id, ids)
        tipos = {i['tipo'] for i in itens if i['id'] == chamado.id}
        self.assertIn('Ticket aberto', tipos)


if __name__ == '__main__':
    unittest.main()
