#!/usr/bin/env python3
"""Conversa WhatsApp da Gestão de Chamados."""
import json
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
    ChamadoCamera,
    ChamadoPortao,
    ChamadoRamal,
    Equipamento,
    Chamado,
    ChamadoMensagem,
    MesaServico,
    ChamadoTecnicoMesa,
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
        ChamadoCamera.query.delete()
        ChamadoPortao.query.delete()
        ChamadoRamal.query.delete()
        WhatsAppChamadoLog.query.delete()
        WhatsAppChamadoUsuario.query.delete()
        ChamadoTecnicoMesa.query.delete()
        ChamadoTecnico.query.delete()
        ChamadoSetor.query.delete()
        MesaServico.query.delete()
        Cliente.query.delete()
        db.session.commit()
        self.cli = Cliente(nome='Hospital CCD', ativo=True, habilitado_chamados=True)
        self.setor = ChamadoSetor(nome='Enfermaria', ativo=True)
        self.mesa = MesaServico(nome='Informática', ativa=True)
        self.mesa_eletrica = MesaServico(nome='Elétrica', ativa=True)
        db.session.add_all([self.cli, self.setor, self.mesa, self.mesa_eletrica])
        db.session.flush()
        self.eq = Equipamento(
            nome_equipamento='Bomba infusão',
            patrimonio='PAT-100',
            cliente_id=self.cli.id,
            setor=self.setor.nome,
            ativo=True,
        )
        db.session.add(self.eq)
        self.camera = ChamadoCamera(
            nome='Hall entrada', dvr='DVR-1', setor_id=self.setor.id, ativo=True,
        )
        self.portao = ChamadoPortao(local='Portão principal', setor_id=self.setor.id)
        self.ramal = ChamadoRamal(
            nome_pessoa='Recepção', numero_ramal='201', setor_id=self.setor.id, ativo=True,
        )
        db.session.add_all([self.camera, self.portao, self.ramal])
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
        self.assertIn('defeito', html.lower())

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
        self.assertTrue(any('tipo de chamado' in m.lower() for m in r4['replies']))
        self.assertTrue(any('Equipamento' in m for m in r4['replies']))
        self.assertTrue(any('câmera' in m.lower() for m in r4['replies']))
        self.assertTrue(any('portão' in m.lower() for m in r4['replies']))
        self.assertTrue(any('telefone/ramal' in m.lower() for m in r4['replies']))
        r5 = self._send(phone, '1')
        self.assertTrue(any('patrimônio' in m.lower() for m in r5['replies']))
        r6 = self._send(phone, 'PAT-100')
        self.assertTrue(any('mesa de serviço' in m.lower() for m in r6['replies']))
        self.assertTrue(any('Informática' in m for m in r6['replies']))
        r7 = self._send(phone, '2')
        self.assertTrue(any('Ticket' in m and 'aberto' in m for m in r7['replies']))
        chamado = Chamado.query.order_by(Chamado.id.desc()).first()
        self.assertIsNotNone(chamado)
        self.assertEqual(chamado.cliente_id, self.cli.id)
        self.assertEqual(chamado.setor_tecnico_id, self.setor.id)
        self.assertEqual(chamado.mesa_id, self.mesa.id)
        self.assertEqual(chamado.patrimonio, 'PAT-100')
        self.assertEqual(chamado.tipo_servico, 'Manutenção')
        self.assertEqual(chamado.canal_abertura, 'WhatsApp')
        self.assertTrue((chamado.contato_abertura or '').endswith('21988880000'))

    def test_usuario_cadastrado_confirma_e_edita(self):
        phone = '21977770000'
        self._send(phone, 'Oi')
        self._send(phone, 'João Souza')
        self._send(phone, '1')
        self._send(phone, '1')
        self._send(phone, '1')
        self._send(phone, 'PAT-100')
        self._send(phone, '1')
        r = self._send(phone, 'Oi de novo')
        self.assertTrue(any('João' in m and 'Hospital CCD' in m for m in r['replies']))
        self.assertTrue(any('envie 1' in m.lower() for m in r['replies']))
        self.assertTrue(any('cliente (local)' in m.lower() for m in r['replies']))
        self.assertTrue(any(m.startswith('Bom dia') or m.startswith('Boa tarde') or m.startswith('Boa noite') for m in r['replies']))
        r2 = self._send(phone, '2')
        self.assertTrue(any('1 - Cliente (local)' in m for m in r2['replies']))
        r3 = self._send(phone, '0')
        self.assertTrue(any('ainda continua' in m for m in r3['replies']))
        r4 = self._send(phone, '1')
        self.assertTrue(any('tipo de chamado' in m.lower() for m in r4['replies']))
        r5 = self._send(phone, '1')
        self.assertTrue(any('patrimônio' in m.lower() for m in r5['replies']))

    def test_inbound_sem_token(self):
        r = self.client.post('/api/chamados/whatsapp/inbound', json={'from': '2199', 'text': 'Oi'})
        self.assertEqual(r.status_code, 403)

    def test_cadastro_tecnico_whatsapp(self):
        r = self.client.get('/tecnicos')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('tecWhatsapp', html)
        self.assertIn('Número para notificações do sistema', html)
        self.assertIn('tecMesa', html)
        self.assertIn('Mesa de serviço', html)
        r = self.client.post('/tecnicos/tecnico/adicionar', json={
            'nome': 'Ana Supervisor',
            'funcao': 'supervisor',
            'whatsapp': '21988881111',
            'setor_id': str(self.setor.id),
            'mesa_ids': [self.mesa.id, self.mesa_eletrica.id],
        })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['whatsapp'], '5521988881111')
        tec = ChamadoTecnico.query.get(data['id'])
        self.assertEqual(tec.whatsapp, '5521988881111')
        self.assertEqual({m.id for m in tec.mesas}, {self.mesa.id, self.mesa_eletrica.id})
        r2 = self.client.post('/tecnicos/tecnico/%s/editar' % tec.id, json={
            'nome': 'Ana Supervisor',
            'funcao': 'gestor',
            'whatsapp': '21977772222',
            'setor_id': str(self.setor.id),
            'mesa_ids': [self.mesa_eletrica.id],
        })
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()['whatsapp'], '5521977772222')
        self.assertEqual(r2.get_json()['mesa_ids'], [self.mesa_eletrica.id])
        r3 = self.client.post('/tecnicos/tecnico/adicionar', json={
            'nome': 'Sem Whats',
            'funcao': 'tecnico',
            'whatsapp': '123',
        })
        self.assertEqual(r3.status_code, 400)
        r4 = self.client.post('/tecnicos/tecnico/adicionar', json={
            'nome': 'Técnico João',
            'funcao': 'tecnico',
            'whatsapp': '21966660000',
            'mesa_ids': [self.mesa.id, self.mesa_eletrica.id],
        })
        self.assertEqual(r4.status_code, 200, r4.get_data(as_text=True))
        self.assertEqual(r4.get_json()['mesa_ids'], [self.mesa.id])
        r5 = self.client.post('/tecnicos/tecnico/adicionar', json={
            'nome': 'Yuri Assistente',
            'funcao': 'assistente',
            'whatsapp': '21966661111',
            'mesa_ids': [self.mesa_eletrica.id],
        })
        self.assertEqual(r5.status_code, 200, r5.get_data(as_text=True))
        self.assertEqual(r5.get_json()['mesa_ids'], [self.mesa_eletrica.id])
        aid = r5.get_json()['id']
        r6 = self.client.post('/tecnicos/tecnico/%s/editar' % aid, json={
            'nome': 'Yuri Assistente',
            'funcao': 'assistente',
            'whatsapp': '21966661111',
            'mesa_ids': [self.mesa.id],
        })
        self.assertEqual(r6.status_code, 200, r6.get_data(as_text=True))
        self.assertEqual(r6.get_json()['mesa_ids'], [self.mesa.id])
        html = self.client.get('/tecnicos').get_data(as_text=True)
        self.assertIn('.tec-mesas-multi[hidden]', html)
        self.assertIn('_aoMudarMesaCheck', html)
        r_get = self.client.get('/tecnicos')
        self.assertEqual(r_get.status_code, 200, r_get.get_data(as_text=True))
        html = r_get.get_data(as_text=True)
        self.assertIn('data-tec=', html)
        self.assertIn('mesa_ids', html)
        self.assertIn('abrirEditarTecnico(%s)' % tec.id, html)
        self.assertNotIn('abrirEditarTecnico(%s, ' % tec.id, html)
        payload = tec.dados_edicao()
        self.assertTrue(isinstance(payload['mesa_ids'], list))
        json.dumps(payload)
        json.dumps(ChamadoTecnico(nome='X', email=None, whatsapp=None, funcao=None).dados_edicao())

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

    def test_aviso_abertura_filtra_por_mesa(self):
        sup_info = ChamadoTecnico(
            nome='Sup Informática', funcao='supervisor', whatsapp='21910100000', ativo=True,
        )
        sup_ele = ChamadoTecnico(
            nome='Sup Elétrica', funcao='supervisor', whatsapp='21920200000', ativo=True,
        )
        ges_ambos = ChamadoTecnico(
            nome='Gestor Duas Mesas', funcao='gestor', whatsapp='21930300000', ativo=True,
        )
        db.session.add_all([sup_info, sup_ele, ges_ambos])
        db.session.flush()
        sup_info.mesas = [self.mesa]
        sup_ele.mesas = [self.mesa_eletrica]
        ges_ambos.mesas = [self.mesa, self.mesa_eletrica]
        chamado = Chamado(
            numero_chamado='OS888001',
            cliente_id=self.cli.id,
            tipo_servico='Manutenção',
            descricao='PC não liga',
            status='Pendente',
            tecnico_id=self.user_id,
            setor_tecnico_id=self.setor.id,
            mesa_id=self.mesa.id,
            patrimonio='PAT-100',
        )
        db.session.add(chamado)
        db.session.commit()
        nomes = {d.nome for d in destinos_aviso_abertura(chamado)}
        self.assertIn('Sup Informática', nomes)
        self.assertIn('Gestor Duas Mesas', nomes)
        self.assertNotIn('Sup Elétrica', nomes)
        self.assertIn('Informática', montar_mensagem_abertura(chamado))

    def test_adicionar_mesa_pelo_cadastro(self):
        html = self.client.get('/tecnicos').get_data(as_text=True)
        self.assertIn('tabMesas', html)
        self.assertIn('editarMesa(', html)
        self.assertIn('excluirMesa(', html)
        r = self.client.post('/tecnicos/mesa/adicionar', json={'nome': 'Máquinas'})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['nome'], 'Máquinas')
        mid = data['id']
        r2 = self.client.post('/tecnicos/mesa/adicionar', json={'nome': 'Máquinas'})
        self.assertEqual(r2.status_code, 400)
        r3 = self.client.post('/tecnicos/mesa/%s/editar' % mid, json={'nome': 'Máquinas pesadas'})
        self.assertEqual(r3.status_code, 200, r3.get_data(as_text=True))
        self.assertEqual(r3.get_json()['nome'], 'Máquinas pesadas')
        r4 = self.client.post('/tecnicos/mesa/%s/excluir' % mid)
        self.assertEqual(r4.status_code, 200, r4.get_data(as_text=True))
        r5 = self.client.post('/tecnicos/tecnico/adicionar', json={
            'nome': 'Tec Mesa',
            'funcao': 'tecnico',
            'whatsapp': '21988880001',
            'mesa_ids': [self.mesa.id],
        })
        self.assertEqual(r5.status_code, 200, r5.get_data(as_text=True))
        r6 = self.client.post('/tecnicos/mesa/%s/excluir' % self.mesa.id)
        self.assertEqual(r6.status_code, 400)

    def _ate_tipo(self, phone, nome='Maria Silva'):
        self._send(phone, 'Oi')
        self._send(phone, nome)
        self._send(phone, '1')
        self._send(phone, '1')

    def test_abre_ticket_camera(self):
        phone = '21980001111'
        self._ate_tipo(phone)
        r = self._send(phone, '2')
        self.assertTrue(any('câmera' in m.lower() for m in r['replies']))
        self.assertTrue(any('Hall entrada' in m for m in r['replies']))
        self.assertFalse(any('DVR-1' in m for m in r['replies']))
        r2 = self._send(phone, '1')
        self.assertTrue(any('mesa de serviço' in m.lower() for m in r2['replies']))
        r3 = self._send(phone, '2')
        self.assertTrue(any('Ticket' in m and 'aberto' in m for m in r3['replies']))
        chamado = Chamado.query.order_by(Chamado.id.desc()).first()
        self.assertEqual(chamado.tipo_servico, 'Reparo de câmera')
        self.assertIn('Hall entrada', chamado.equipamento)
        self.assertEqual(chamado.mesa_id, self.mesa.id)

    def test_abre_ticket_portao(self):
        phone = '21980002222'
        self._ate_tipo(phone)
        r = self._send(phone, '3')
        self.assertTrue(any('portão' in m.lower() for m in r['replies']))
        self.assertTrue(any('Portão principal' in m for m in r['replies']))
        r2 = self._send(phone, '1')
        self.assertTrue(any('mesa de serviço' in m.lower() for m in r2['replies']))
        r3 = self._send(phone, '2')
        self.assertTrue(any('Ticket' in m and 'aberto' in m for m in r3['replies']))
        chamado = Chamado.query.order_by(Chamado.id.desc()).first()
        self.assertEqual(chamado.tipo_servico, 'Reparo de portão')
        self.assertIn('Portão principal', chamado.equipamento)

    def test_abre_ticket_ramal(self):
        phone = '21980003333'
        self._ate_tipo(phone)
        r = self._send(phone, '4')
        self.assertTrue(any('telefone/ramal' in m.lower() or 'ramal' in m.lower() for m in r['replies']))
        self.assertTrue(any('1 - 201' in m for m in r['replies']))
        self.assertFalse(any('Recepção' in m for m in r['replies']))
        r2 = self._send(phone, '1')
        self.assertTrue(any('mesa de serviço' in m.lower() for m in r2['replies']))
        r3 = self._send(phone, '2')
        self.assertTrue(any('Ticket' in m and 'aberto' in m for m in r3['replies']))
        chamado = Chamado.query.order_by(Chamado.id.desc()).first()
        self.assertEqual(chamado.tipo_servico, 'Reparo de telefone/ramal')
        self.assertEqual(chamado.patrimonio, '201')
        self.assertIn('Recepção', chamado.equipamento)

    def test_abre_ticket_camera_sem_cadastro(self):
        ChamadoCamera.query.delete()
        db.session.commit()
        phone = '21980004444'
        self._ate_tipo(phone)
        r = self._send(phone, '2')
        self.assertTrue(any('Não há câmeras' in m for m in r['replies']))
        r2 = self._send(phone, 'Câmera do corredor 3')
        self.assertTrue(any('mesa de serviço' in m.lower() for m in r2['replies']))
        r3 = self._send(phone, '2')
        self.assertTrue(any('Ticket' in m and 'aberto' in m for m in r3['replies']))
        chamado = Chamado.query.order_by(Chamado.id.desc()).first()
        self.assertEqual(chamado.tipo_servico, 'Reparo de câmera')
        self.assertEqual(chamado.equipamento, 'Câmera do corredor 3')

    def test_inbound_com_token_inicia_cadastro(self):
        from whatsapp_pesagem import inbound_token
        token = inbound_token()
        r = self.client.post(
            '/api/chamados/whatsapp/inbound',
            json={'from': '21988880001', 'text': 'Oi', 'jid': '21988880001@c.us'},
            headers={'X-WA-Token': token},
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertTrue(data.get('ok'))
        self.assertTrue(any('não está cadastrado' in m for m in (data.get('replies') or [])))


if __name__ == '__main__':
    unittest.main()
