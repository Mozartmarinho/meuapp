#!/usr/bin/env python3
"""Conversa WhatsApp da Gestão de Chamados."""
import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['PESAGEM_WA_DISABLE'] = '1'

from app import create_app, ensure_whatsapp_chamado_schema  # noqa: E402
from models import (  # noqa: E402
    db,
    Usuario,
    Cliente,
    ChamadoSetor,
    Equipamento,
    Chamado,
    ChamadoMensagem,
    WhatsAppChamadoUsuario,
    WhatsAppChamadoLog,
)
from password_utils import generate_password_hash  # noqa: E402
from whatsapp_chamados import process_inbound, saudacao  # noqa: E402


class WhatsAppChamadoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        ensure_whatsapp_chamado_schema()
        cls.client = cls.app.test_client()
        user = Usuario(
            nome='Admin Chamado',
            email='wa-chamado@test.local',
            senha=generate_password_hash('admin'),
            tipo='admin',
            is_master=True,
            perm_chamados=True,
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
        ChamadoMensagem.query.delete()
        Chamado.query.delete()
        Equipamento.query.delete()
        WhatsAppChamadoLog.query.delete()
        WhatsAppChamadoUsuario.query.delete()
        ChamadoSetor.query.delete()
        Cliente.query.delete()
        db.session.commit()
        self.cli = Cliente(nome='Hospital CCD', ativo=True, habilitado_chamados=True)
        self.setor = ChamadoSetor(nome='Enfermaria', ativo=True)
        db.session.add_all([self.cli, self.setor])
        db.session.flush()
        self.eq = Equipamento(
            nome_equipamento='Bomba infusão',
            patrimonio='PAT-100',
            cliente_id=self.cli.id,
            setor=self.setor.nome,
            ativo=True,
        )
        db.session.add(self.eq)
        db.session.commit()
        self.replies = []

    def _send(self, telefone, texto):
        def fake(to, msg):
            self.replies.append(msg)
            return {'ok': True}
        self.replies = []
        return process_inbound(telefone, texto, sender=fake, agora=datetime(2026, 9, 16, 9, 0))

    def test_saudacao_manha(self):
        self.assertEqual(saudacao(datetime(2026, 1, 1, 8, 0)), 'Bom dia')
        self.assertEqual(saudacao(datetime(2026, 1, 1, 15, 0)), 'Boa tarde')
        self.assertEqual(saudacao(datetime(2026, 1, 1, 21, 0)), 'Boa noite')

    def test_pagina_menu(self):
        r = self.client.get('/chamados/whatsapp-mensagem')
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        html = r.get_data(as_text=True)
        self.assertIn('Conf. Mensagem WhatsApp', html)
        self.assertIn('Cadastro de usuário WhatsApp', html)

    def test_fluxo_novo_abre_ticket(self):
        phone = '21988880000'
        r1 = self._send(phone, 'Oi')
        self.assertTrue(any('não está cadastrado' in m for m in r1['replies']))
        r2 = self._send(phone, 'Maria Silva')
        self.assertTrue(any('unidade' in m.lower() for m in r2['replies']))
        self.assertTrue(any('1 - Hospital CCD' in m for m in r2['replies']))
        r3 = self._send(phone, '1')
        self.assertTrue(any('setor' in m.lower() for m in r3['replies']))
        self.assertTrue(any('1 - Enfermaria' in m for m in r3['replies']))
        r4 = self._send(phone, '1')
        self.assertTrue(any('Cadastro salvo' in m for m in r4['replies']))
        self.assertTrue(any('patrimônio' in m.lower() for m in r4['replies']))
        r5 = self._send(phone, 'PAT-100')
        self.assertTrue(any('Ticket' in m and 'aberto' in m for m in r5['replies']))
        chamado = Chamado.query.order_by(Chamado.id.desc()).first()
        self.assertIsNotNone(chamado)
        self.assertEqual(chamado.cliente_id, self.cli.id)
        self.assertEqual(chamado.setor_tecnico_id, self.setor.id)
        self.assertEqual(chamado.patrimonio, 'PAT-100')
        self.assertEqual(chamado.tipo_servico, 'Manutenção')

    def test_usuario_cadastrado_confirma_e_edita(self):
        phone = '21977770000'
        self._send(phone, 'Oi')
        self._send(phone, 'João Souza')
        self._send(phone, '1')
        self._send(phone, '1')
        self._send(phone, 'PAT-100')
        r = self._send(phone, 'Oi de novo')
        self.assertTrue(any('João' in m and 'Hospital CCD' in m for m in r['replies']))
        self.assertTrue(any('envie 1' in m.lower() for m in r['replies']))
        r2 = self._send(phone, '2')
        self.assertTrue(any('1 - Unidade' in m for m in r2['replies']))
        r3 = self._send(phone, '0')
        self.assertTrue(any('ainda continua' in m for m in r3['replies']))
        r4 = self._send(phone, '1')
        self.assertTrue(any('patrimônio' in m.lower() for m in r4['replies']))

    def test_inbound_sem_token(self):
        r = self.client.post('/api/chamados/whatsapp/inbound', json={'from': '2199', 'text': 'Oi'})
        self.assertEqual(r.status_code, 403)


if __name__ == '__main__':
    unittest.main()
