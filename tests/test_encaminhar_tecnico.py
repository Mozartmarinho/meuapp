#!/usr/bin/env python3
"""Encaminhar ativo atribui o chamado a um técnico e tira da fila dos outros."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import Chamado, ChamadoConfig, ChamadoTecnico, Cliente, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402
from routes import (  # noqa: E402
    _pendencias_chamados,
    _query_chamados_usuario,
    _usuario_toca_mesa,
    encaminhar_tecnico_ativo,
)


class EncaminharTecnicoTest(unittest.TestCase):
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
        ChamadoConfig.query.delete()
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
        user = self._usuario(nome, email)
        dados = dict(nome=nome, email=email, usuario_id=user.id, ativo=True, funcao='tecnico')
        dados.update(kwargs)
        db.session.add(ChamadoTecnico(**dados))
        db.session.commit()
        return user

    def _chamado(self, opener, numero='OS000010'):
        chamado = Chamado(
            numero_chamado=numero,
            cliente_id=self.cli.id,
            tipo_servico='Manutenção',
            descricao='Não liga',
            status='Pendente',
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

    def _ligar_encaminhar(self):
        db.session.add(ChamadoConfig(encaminhar_ativo=True))
        db.session.commit()

    def test_atribuido_some_da_fila_dos_outros(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        ana = self._tecnico('Ana Técnica', 'ana@example.com')
        bruno = self._tecnico('Bruno Técnico', 'bruno@example.com')
        chamado = self._chamado(opener)
        chamado.atribuido_usuario_id = ana.id
        chamado.atendente_id = ana.id
        db.session.commit()

        ids_ana = {c.id for c in _query_chamados_usuario(ana).all()}
        ids_bruno = {c.id for c in _query_chamados_usuario(bruno).all()}
        ids_abre = {c.id for c in _query_chamados_usuario(opener).all()}
        self.assertIn(chamado.id, ids_ana)
        self.assertNotIn(chamado.id, ids_bruno)
        self.assertIn(chamado.id, ids_abre)
        self.assertFalse(_usuario_toca_mesa(bruno, None, chamado))
        self.assertTrue(_usuario_toca_mesa(ana, None, chamado))
        with self.app.test_request_context('/'):
            pend_ana = {i['id'] for i in _pendencias_chamados(ana)}
            pend_bruno = {i['id'] for i in _pendencias_chamados(bruno)}
        self.assertIn(chamado.id, pend_ana)
        self.assertNotIn(chamado.id, pend_bruno)

    def test_supervisor_continua_vendo(self):
        opener = self._usuario('Solicitante', 'abre2@example.com')
        ana = self._tecnico('Ana Técnica', 'ana2@example.com')
        sup = self._usuario('Supervisora', 'sup@example.com')
        db.session.add(ChamadoTecnico(
            nome='Supervisora', email='sup@example.com', usuario_id=sup.id,
            ativo=True, funcao='supervisor',
        ))
        db.session.commit()
        chamado = self._chamado(opener, 'OS000011')
        chamado.atribuido_usuario_id = ana.id
        db.session.commit()
        ids = {c.id for c in _query_chamados_usuario(sup).all()}
        self.assertIn(chamado.id, ids)
        detalhe = self._login(sup).get('/chamados/%s' % chamado.id)
        self.assertEqual(detalhe.status_code, 200)
        self.assertIn('OS000011', detalhe.get_data(as_text=True))

    def test_outro_tecnico_nao_abre_o_detalhe(self):
        opener = self._usuario('Solicitante', 'abre3@example.com')
        ana = self._tecnico('Ana Técnica', 'ana3@example.com')
        bruno = self._tecnico('Bruno Técnico', 'bruno3@example.com')
        chamado = self._chamado(opener, 'OS000012')
        chamado.atribuido_usuario_id = ana.id
        chamado.atendente_id = ana.id
        db.session.commit()
        resp = self._login(bruno).get('/chamados/%s' % chamado.id, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        bloqueio = self._login(bruno).get('/api/chamados/%s/atender' % chamado.id)
        self.assertEqual(bloqueio.status_code, 409)

    def test_toggle_e_atribuicao_pelo_atendimento(self):
        self.assertFalse(encaminhar_tecnico_ativo())
        admin = self._usuario('Admin', 'admin@example.com', tipo='admin', is_master=True)
        opener = self._usuario('Solicitante', 'abre4@example.com')
        ana = self._tecnico('Ana Técnica', 'ana4@example.com')
        bruno = self._tecnico('Bruno Técnico', 'bruno4@example.com')
        tec_bruno = ChamadoTecnico.query.filter_by(usuario_id=bruno.id).one()
        chamado = self._chamado(opener, 'OS000013')

        pagina = self._login(admin).get('/tecnicos')
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('Encaminhar:', pagina.get_data(as_text=True))
        off = self._login(ana).post(
            '/api/chamados/%s/atender' % chamado.id,
            data={
                'acao': 'encaminhar',
                'tecnico_destino_id': str(tec_bruno.id),
                'instrucoes': 'Ver no local',
            },
        )
        self.assertEqual(off.status_code, 400)
        self.assertIn('desativado', (off.get_json() or {}).get('message', ''))

        ligado = self._login(admin).post('/tecnicos/encaminhar/toggle')
        self.assertEqual(ligado.status_code, 200)
        self.assertTrue(ligado.get_json()['ativo'])
        self.assertTrue(encaminhar_tecnico_ativo())

        lista = self._login(ana).get('/chamados')
        html = lista.get_data(as_text=True)
        self.assertIn('at_tecnico', html)
        self.assertIn('Bruno Técnico', html)

        ok = self._login(ana).post(
            '/api/chamados/%s/atender' % chamado.id,
            data={
                'acao': 'encaminhar',
                'tecnico_destino_id': str(tec_bruno.id),
                'instrucoes': 'Ver no local',
            },
        )
        self.assertEqual(ok.status_code, 200, ok.get_json())
        db.session.refresh(chamado)
        self.assertEqual(chamado.atribuido_usuario_id, bruno.id)
        self.assertEqual(chamado.atendente_id, bruno.id)
        ids_ana = {c.id for c in _query_chamados_usuario(ana).all()}
        ids_bruno = {c.id for c in _query_chamados_usuario(bruno).all()}
        self.assertNotIn(chamado.id, ids_ana)
        self.assertIn(chamado.id, ids_bruno)


if __name__ == '__main__':
    unittest.main()
