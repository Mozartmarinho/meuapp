#!/usr/bin/env python3
"""Campanha de novo chamado para técnico, supervisor e gestor logados."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import Chamado, ChamadoTecnico, Cliente, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402
from routes import _recebe_campanha_ticket  # noqa: E402


class CampanhaTicketTest(unittest.TestCase):
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

    def _tecnico(self, nome, email, funcao='tecnico', **kwargs):
        user = self._usuario(nome, email, **kwargs)
        db.session.add(ChamadoTecnico(
            nome=nome,
            email=email,
            usuario_id=user.id,
            funcao=funcao,
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

    def test_recebe_tecnico_supervisor_gestor(self):
        tec = self._tecnico('Ana', 'ana@example.com', 'tecnico')
        sup = self._tecnico('Bia', 'bia@example.com', 'supervisor')
        ges = self._tecnico('Cris', 'cris@example.com', 'gestor')
        ass = self._tecnico('Duda', 'duda@example.com', 'assistente')
        admin = self._usuario('Admin', 'admin@example.com', tipo='admin')
        op = self._usuario('Op', 'op@example.com')
        self.assertTrue(_recebe_campanha_ticket(tec))
        self.assertTrue(_recebe_campanha_ticket(sup))
        self.assertTrue(_recebe_campanha_ticket(ges))
        self.assertTrue(_recebe_campanha_ticket(admin))
        self.assertFalse(_recebe_campanha_ticket(ass))
        self.assertFalse(_recebe_campanha_ticket(op))

    def test_api_sem_login(self):
        r = self.app.test_client().get('/api/chamados/campanha')
        self.assertEqual(r.status_code, 401)

    def test_api_assistente_desligada(self):
        ass = self._tecnico('Duda', 'duda@example.com', 'assistente')
        client = self._login(ass)
        r = client.get('/api/chamados/campanha?after_id=0')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['ok'])
        self.assertFalse(data['enabled'])

    def test_primeira_consulta_nao_lista_antigos(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana', 'ana@example.com')
        chamado = self._chamado(opener)
        client = self._login(tec)
        r = client.get('/api/chamados/campanha?after_id=0')
        data = r.get_json()
        self.assertTrue(data['enabled'])
        self.assertEqual(data['campanhas'], [])
        self.assertEqual(data['latest_id'], chamado.id)

    def test_tecnico_recebe_chamado_novo(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana', 'ana@example.com')
        velho = self._chamado(opener, 'OS111')
        novo = self._chamado(opener, 'OS222')
        client = self._login(tec)
        r = client.get('/api/chamados/campanha?after_id=%s' % velho.id)
        data = r.get_json()
        ids = [c['id'] for c in data['campanhas']]
        self.assertIn(novo.id, ids)
        self.assertNotIn(velho.id, ids)
        self.assertEqual(data['campanhas'][0]['numero_chamado'], 'OS222')
        self.assertIn('atender=', data['campanhas'][0]['url'])

    def test_quem_abriu_nao_recebe(self):
        opener = self._tecnico('Ana', 'ana@example.com')
        outro = self._usuario('Outro', 'outro@example.com')
        velho = self._chamado(opener, 'OS300')
        chamado = self._chamado(opener, 'OS333')
        client = self._login(opener)
        r = client.get('/api/chamados/campanha?after_id=%s' % velho.id)
        ids = [c['id'] for c in r.get_json()['campanhas']]
        self.assertNotIn(chamado.id, ids)
        client_outro = self._login(outro)
        self.assertFalse(client_outro.get('/api/chamados/campanha').get_json()['enabled'])

    def test_supervisor_e_gestor_recebem(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        sup = self._tecnico('Bia', 'bia@example.com', 'supervisor')
        ges = self._tecnico('Cris', 'cris@example.com', 'gestor')
        velho = self._chamado(opener, 'OS400')
        chamado = self._chamado(opener, 'OS444')
        for user in (sup, ges):
            data = self._login(user).get(
                '/api/chamados/campanha?after_id=%s' % velho.id
            ).get_json()
            self.assertIn(chamado.id, [c['id'] for c in data['campanhas']])


if __name__ == '__main__':
    unittest.main()
