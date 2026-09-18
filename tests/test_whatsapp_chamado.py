#!/usr/bin/env python3
"""Conversa WhatsApp da Gestão de Chamados."""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['PESAGEM_WA_DISABLE'] = '1'

from app import create_app, ensure_whatsapp_chamado_schema, ensure_tecnicos_schema  # noqa: E402
from models import (  # noqa: E402
    db,
    Usuario,
    Cliente,
    ChamadoSetor,
    ChamadoTecnico,
    Equipamento,
    Chamado,
    ChamadoMensagem,
    WhatsAppChamadoUsuario,
    WhatsAppChamadoLog,
)
from password_utils import generate_password_hash  # noqa: E402
from whatsapp_chamados import (  # noqa: E402
    destinos_aviso_abertura,
    montar_mensagem_abertura,
    notificar_abertura_chamado,
    process_inbound,
    saudacao,
)


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
        ensure_tecnicos_schema()
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
        ChamadoTecnico.query.delete()
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

    def test_cadastro_tecnico_whatsapp(self):
        r = self.client.get('/tecnicos')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('tecWhatsapp', html)
        self.assertIn('Número para notificações do sistema', html)
        r = self.client.post('/tecnicos/tecnico/adicionar', json={
            'nome': 'Ana Supervisor',
            'funcao': 'supervisor',
            'whatsapp': '21988881111',
            'setor_id': str(self.setor.id),
        })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['whatsapp'], '5521988881111')
        tec = ChamadoTecnico.query.get(data['id'])
        self.assertEqual(tec.whatsapp, '5521988881111')
        r2 = self.client.post('/tecnicos/tecnico/%s/editar' % tec.id, json={
            'nome': 'Ana Supervisor',
            'funcao': 'gestor',
            'whatsapp': '21977772222',
            'setor_id': str(self.setor.id),
        })
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()['whatsapp'], '5521977772222')
        r3 = self.client.post('/tecnicos/tecnico/adicionar', json={
            'nome': 'Sem Whats',
            'funcao': 'tecnico',
            'whatsapp': '123',
        })
        self.assertEqual(r3.status_code, 400)

    def test_aviso_abertura_so_supervisor_gestor(self):
        ChamadoTecnico.query.delete()
        db.session.add_all([
            ChamadoTecnico(
                nome='Técnico João', funcao='tecnico', whatsapp='21911110000',
                setor_id=self.setor.id, ativo=True,
            ),
            ChamadoTecnico(
                nome='Supervisora Ana', funcao='supervisor', whatsapp='21922220000',
                setor_id=self.setor.id, ativo=True,
            ),
            ChamadoTecnico(
                nome='Gestor Carlos', funcao='gestor', whatsapp='21933330000',
                ativo=True,
            ),
            ChamadoTecnico(
                nome='Supervisor outro setor', funcao='supervisor', whatsapp='21944440000',
                setor_id=None, ativo=True,
            ),
        ])
        outro = ChamadoSetor(nome='Elétrica', ativo=True)
        db.session.add(outro)
        db.session.flush()
        db.session.add(ChamadoTecnico(
            nome='Supervisor elétrica', funcao='supervisor', whatsapp='21955550000',
            setor_id=outro.id, ativo=True,
        ))
        db.session.commit()
        chamado = Chamado(
            numero_chamado='OS999001',
            cliente_id=self.cli.id,
            tipo_servico='Manutenção',
            descricao='Bomba não liga',
            status='Pendente',
            tecnico_id=self.user_id,
            setor_tecnico_id=self.setor.id,
            patrimonio='PAT-100',
        )
        db.session.add(chamado)
        db.session.commit()
        msg = montar_mensagem_abertura(chamado)
        self.assertIn('OS999001', msg)
        self.assertIn('Hospital CCD', msg)
        self.assertIn('Enfermaria', msg)
        self.assertIn('PAT-100', msg)
        self.assertIn('Bomba não liga', msg)
        destinos = destinos_aviso_abertura(chamado)
        nomes = {d.nome for d in destinos}
        self.assertIn('Supervisora Ana', nomes)
        self.assertIn('Gestor Carlos', nomes)
        self.assertIn('Supervisor outro setor', nomes)
        self.assertNotIn('Técnico João', nomes)
        self.assertNotIn('Supervisor elétrica', nomes)
        enviados = []

        def fake(to, texto):
            enviados.append((to, texto))
            return {'ok': True}

        phones = notificar_abertura_chamado(chamado, sender=fake)
        self.assertEqual(len(phones), 3)
        self.assertTrue(all('OS999001' in texto for _, texto in enviados))

    def test_novo_chamado_envia_whatsapp_gestor(self):
        db.session.add(ChamadoTecnico(
            nome='Gestor WA', funcao='gestor', whatsapp='21966660000', ativo=True,
        ))
        db.session.commit()
        enviados = []

        def fake(to, texto):
            enviados.append((to, texto))
            return {'ok': True}

        with patch('whatsapp_pesagem.send_whatsapp', fake):
            r = self.client.post('/novo_chamado', data={
                'cliente_id': str(self.cli.id),
                'tipo_servico': 'Reparo',
                'descricao': 'Vazamento no motor',
                'patrimonio': 'PAT-100',
                'setor_tecnico_id': str(self.setor.id),
                'prioridade': 'Alta',
            }, follow_redirects=True)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(enviados)
        self.assertTrue(any('Vazamento no motor' in t for _, t in enviados))
        self.assertTrue(any('Abertura de chamado' in t for _, t in enviados))
        self.assertTrue(any('PAT-100' in t for _, t in enviados))
        self.assertTrue(any('Hospital CCD' in t for _, t in enviados))


if __name__ == '__main__':
    unittest.main()
