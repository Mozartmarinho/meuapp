#!/usr/bin/env python3
"""Aviso de finalização no mesmo canal em que o chamado foi aberto."""
import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['PESAGEM_WA_DISABLE'] = '1'

from app import create_app  # noqa: E402
from models import (  # noqa: E402
    Chamado,
    ChamadoMensagem,
    ChamadoTecnico,
    Cliente,
    Usuario,
    WhatsAppChamadoLog,
    db,
)
from password_utils import generate_password_hash  # noqa: E402
from routes import (  # noqa: E402
    _avisar_finalizacao_ticket,
    montar_texto_finalizacao,
)


class FinalizacaoAvisoTest(unittest.TestCase):
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
        ChamadoMensagem.query.delete()
        WhatsAppChamadoLog.query.delete()
        Chamado.query.delete()
        ChamadoTecnico.query.delete()
        Usuario.query.delete()
        Cliente.query.delete()
        db.session.commit()
        self.cli = Cliente(nome='Hospital Teste', ativo=True, habilitado_chamados=True)
        db.session.add(self.cli)
        db.session.commit()
        self.opener = Usuario(
            nome='Ana Abre',
            email='ana@example.com',
            senha=generate_password_hash('x'),
            ativo=True,
            perm_chamados=True,
        )
        self.tec_user = Usuario(
            nome='Carlos Acesso',
            email='carlos@example.com',
            senha=generate_password_hash('x'),
            ativo=True,
            perm_chamados=True,
        )
        db.session.add_all([self.opener, self.tec_user])
        db.session.commit()
        db.session.add(ChamadoTecnico(
            nome='Carlos Técnico',
            email='carlos@example.com',
            usuario_id=self.tec_user.id,
            funcao='tecnico',
            ativo=True,
        ))
        db.session.commit()

    def _chamado(self, **kwargs):
        dados = dict(
            numero_chamado='OS900001',
            cliente_id=self.cli.id,
            tipo_servico='Manutenção',
            descricao='Não liga',
            status='Pendente',
            tecnico_id=self.opener.id,
            canal_abertura='E-mail',
            contato_abertura=self.opener.email,
        )
        dados.update(kwargs)
        row = Chamado(**dados)
        db.session.add(row)
        db.session.commit()
        return row

    def test_texto_tem_tecnico_hora_e_servico(self):
        chamado = self._chamado()
        texto = montar_texto_finalizacao(
            chamado, 'Carlos Técnico', '18/09/2026 15:42', 'Troca da fonte',
        )
        self.assertIn('OS900001', texto)
        self.assertIn('Carlos Técnico', texto)
        self.assertIn('18/09/2026 15:42', texto)
        self.assertIn('Troca da fonte', texto)

    def test_web_envia_email_para_quem_abriu(self):
        chamado = self._chamado()
        enviados = []

        def fake_mail(dest, assunto, texto, html=None):
            enviados.append((dest, assunto, texto, html))

        r = _avisar_finalizacao_ticket(
            chamado,
            self.tec_user,
            'Troca da fonte',
            enviar_mail=fake_mail,
            agora=datetime(2026, 9, 18, 15, 42),
        )
        self.assertTrue(r['ok'])
        self.assertEqual(r['canal'], 'E-mail')
        self.assertEqual(enviados[0][0], 'ana@example.com')
        self.assertIn('finalizado', enviados[0][1].lower())
        self.assertIn('Carlos Técnico', enviados[0][2])
        self.assertIn('Troca da fonte', enviados[0][2])
        msg = ChamadoMensagem.query.filter_by(chamado_id=chamado.id).first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.canal, 'E-mail')
        self.assertTrue(msg.enviada)

    def test_whatsapp_envia_para_telefone_da_abertura(self):
        chamado = self._chamado(
            canal_abertura='WhatsApp',
            contato_abertura='21988880000',
            observacoes='Origem: WhatsApp',
            descricao='Solicitante: Maria\nTelefone: 21988880000\nDefeito: Não liga',
            tecnico_id=self.tec_user.id,
        )
        enviados = []

        def fake_wa(telefone, texto):
            enviados.append((telefone, texto))
            return {'ok': True}

        r = _avisar_finalizacao_ticket(
            chamado,
            self.tec_user,
            'Ajustei o cabo',
            enviar_wa=fake_wa,
            agora=datetime(2026, 9, 18, 16, 5),
        )
        self.assertTrue(r['ok'])
        self.assertEqual(r['canal'], 'WhatsApp')
        self.assertEqual(enviados[0][0], '21988880000')
        self.assertIn('Ajustei o cabo', enviados[0][1])
        self.assertIn('Carlos Técnico', enviados[0][1])
        self.assertIn('16:05', enviados[0][1])
        msg = ChamadoMensagem.query.filter_by(chamado_id=chamado.id).first()
        self.assertEqual(msg.canal, 'WhatsApp')
        self.assertTrue(msg.enviada)

    def test_ticket_antigo_whatsapp_infere_telefone_da_descricao(self):
        chamado = self._chamado(
            canal_abertura=None,
            contato_abertura=None,
            observacoes='Origem: WhatsApp',
            descricao='Solicitante: Maria\nTelefone: 21977770000',
            tecnico_id=self.tec_user.id,
        )
        enviados = []

        def fake_wa(telefone, texto):
            enviados.append(telefone)
            return {'ok': True}

        r = _avisar_finalizacao_ticket(
            chamado, self.tec_user, 'OK', enviar_wa=fake_wa,
        )
        self.assertTrue(r['ok'])
        self.assertEqual(r['canal'], 'WhatsApp')
        self.assertEqual(enviados[0], '21977770000')

    def test_atender_finalizar_dispara_aviso(self):
        chamado = self._chamado()
        enviados = []

        def fake_mail(dest, assunto, texto, html=None):
            enviados.append(dest)

        from unittest.mock import patch
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = self.tec_user.id
            sess['user_name'] = self.tec_user.nome
        with patch('email_service.smtp_configurado', return_value=True), \
             patch('email_service.enviar_email', side_effect=fake_mail):
            r = client.post(
                '/api/chamados/%s/atender' % chamado.id,
                data={'acao': 'finalizar', 'atendimento_notas': 'Trocada a placa'},
            )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(enviados, ['ana@example.com'])
        db.session.refresh(chamado)
        self.assertEqual(chamado.status, 'Atendido')


if __name__ == '__main__':
    unittest.main()
