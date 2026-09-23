#!/usr/bin/env python3
"""Conf. WhatsApp da pesagem: totais por cadastro, destinos e envio diário."""
import os
import sys
import unittest
from datetime import date, datetime, time as dt_time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['PESAGEM_WA_DISABLE'] = '1'

from app import create_app, ensure_pesagem_schema  # noqa: E402
from models import db, Usuario  # noqa: E402
from models_pesagem import (  # noqa: E402
    PesagemBalanca,
    PesagemCliente,
    PesagemLeitura,
    PesagemWhatsAppDestino,
    PesagemWhatsAppEnvio,
)
from password_utils import generate_password_hash  # noqa: E402
from whatsapp_pesagem import (  # noqa: E402
    formatar_kg,
    montar_mensagem,
    normalizar_telefone,
    process_scheduled_sends,
    totais_liquido_do_dia,
)


class PesagemWhatsAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        ensure_pesagem_schema()
        cls.client = cls.app.test_client()
        user = Usuario(
            nome='Admin Pesagem',
            email='pesagem-wa@test.local',
            senha=generate_password_hash('admin'),
            tipo='admin',
            is_master=True,
            perm_pesagem=True,
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
        PesagemLeitura.query.delete()
        PesagemWhatsAppEnvio.query.delete()
        PesagemWhatsAppDestino.query.delete()
        PesagemCliente.query.delete()
        PesagemBalanca.query.delete()
        db.session.commit()

    def _criar_leitura(self, cliente, peso_bruto, quando, peso=None):
        cli = PesagemCliente.query.filter_by(nome=cliente).first()
        if not cli:
            cli = PesagemCliente(nome=cliente)
            db.session.add(cli)
            db.session.flush()
        bal = PesagemBalanca.query.filter_by(codigo='BAL-01').first()
        if not bal:
            bal = PesagemBalanca(codigo='BAL-01', nome='Principal', ativo=True)
            db.session.add(bal)
            db.session.flush()
        liquido = peso if peso is not None else peso_bruto
        leitura = PesagemLeitura(
            balanca_id=bal.id,
            balanca_codigo=bal.codigo,
            peso=liquido,
            unidade='kg',
            tara=0.0,
            peso_bruto=peso_bruto,
            peso_liquido=liquido,
            estavel=True,
            origem='agente',
            cliente_id=cli.id,
            cliente_nome=cli.nome,
            data_leitura=quando,
        )
        db.session.add(leitura)
        db.session.commit()
        return leitura

    def test_normalizar_telefone_br(self):
        self.assertEqual(normalizar_telefone('(21) 99999-1234'), '5521999991234')
        self.assertEqual(normalizar_telefone('21999991234'), '5521999991234')
        self.assertEqual(normalizar_telefone('5521999991234'), '5521999991234')

    def test_soma_liquido_por_cadastro(self):
        hoje = date.today()
        base = datetime.combine(hoje, dt_time(8, 0))
        for i in range(10):
            self._criar_leitura('CCD', 12.5, base.replace(hour=8, minute=i), peso=10.0)
        self._criar_leitura('OUTRO', 4.0, base.replace(hour=10), peso=3.0)
        totais = {t['nome']: t for t in totais_liquido_do_dia(hoje)}
        self.assertEqual(totais['CCD']['quantidade'], 10)
        self.assertAlmostEqual(totais['CCD']['total'], 100.0, places=3)
        self.assertAlmostEqual(totais['OUTRO']['total'], 3.0, places=3)

    def test_mensagem_totais_usa_liquido(self):
        hoje = date.today()
        self._criar_leitura('CCD', 12.0, datetime.combine(hoje, dt_time(9, 0)), peso=10.0)
        self._criar_leitura('CCD', 7.5, datetime.combine(hoje, dt_time(10, 0)), peso=5.5)
        corpo = montar_mensagem('Resumo da pesagem de hoje:', totais_liquido_do_dia(hoje), hoje)
        self.assertIn('Resumo da pesagem de hoje:', corpo)
        self.assertIn('CCD --- total 15,500 kg', corpo)
        self.assertNotIn('19,500 kg', corpo)

    def test_formatar_kg(self):
        self.assertEqual(formatar_kg(125.5), '125,500 kg')

    def test_pagina_menu_e_enviar_para(self):
        r = self.client.get('/pesagem/whatsapp')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('Conf. WhatsApp', html)
        self.assertIn('Enviar para', html)
        self.assertIn('QR Code', html)
        self.assertIn('Desconectar', html)
        self.assertIn('btnWaLogout', html)
        self.assertIn('/api/pesagem/whatsapp/logout', html)
        self.assertIn('WhatsApp Web interno', html)
        self.assertIn('waConnected', html)
        self.assertNotIn('id="btnWaLogout" hidden', html)
        self.assertIn('d-nome', html)
        self.assertIn('d-telefone', html)
        self.assertIn('d-hora', html)
        self.assertIn('d-mensagem', html)
        self.assertIn('Total líquido', html)

    def test_logout_desabilitado_no_ambiente_de_teste(self):
        from whatsapp_pesagem import logout_whatsapp
        result = logout_whatsapp()
        self.assertFalse(result.get('ok'))
        self.assertIn('desabilitado', (result.get('error') or '').lower())

    def test_crud_destino(self):
        r = self.client.post('/api/pesagem/whatsapp/destinos', json={
            'nome': 'Supervisor',
            'telefone': '21988887777',
            'hora': '20:30',
            'mensagem': 'Totais do dia',
            'ativo': True,
        })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertTrue(data['ok'])
        dest = data['destino']
        self.assertEqual(dest['telefone'], '5521988887777')
        self.assertEqual(dest['hora'], '20:30')
        did = dest['id']

        r = self.client.put('/api/pesagem/whatsapp/destinos/%s' % did, json={
            'nome': 'Supervisor Noite',
            'telefone': '21988887777',
            'hora': '21:00',
            'mensagem': 'Fechamento',
            'ativo': True,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['destino']['nome'], 'Supervisor Noite')

        r = self.client.delete('/api/pesagem/whatsapp/destinos/%s' % did)
        self.assertEqual(r.status_code, 200)
        r = self.client.get('/api/pesagem/whatsapp/destinos')
        self.assertEqual(r.get_json()['destinos'], [])

    def test_preview_api(self):
        hoje = date.today()
        self._criar_leitura('CCD', 8.0, datetime.combine(hoje, dt_time(11, 0)))
        r = self.client.get('/api/pesagem/whatsapp/preview', query_string={
            'mensagem': 'Bom dia',
            'data': hoje.isoformat(),
        })
        self.assertEqual(r.status_code, 200)
        corpo = r.get_json()['corpo']
        self.assertIn('Bom dia', corpo)
        self.assertIn('CCD --- total 8,000 kg', corpo)

    def test_agendador_envia_uma_vez_no_horario(self):
        hoje = date.today()
        self._criar_leitura('CCD', 4.0, datetime.combine(hoje, dt_time(7, 0)))
        dest = PesagemWhatsAppDestino(
            nome='Operador',
            telefone='5521999990000',
            hora=dt_time(18, 0),
            mensagem='Fechamento',
            ativo=True,
        )
        db.session.add(dest)
        db.session.commit()
        enviados = []

        def fake_send(telefone, texto):
            enviados.append((telefone, texto))
            return {'ok': True}

        agora = datetime.combine(hoje, dt_time(18, 0, 10))
        first = process_scheduled_sends(now=agora, sender=fake_send)
        second = process_scheduled_sends(now=agora, sender=fake_send)
        self.assertEqual(len(first), 1)
        self.assertTrue(first[0]['ok'])
        self.assertEqual(second, [])
        self.assertEqual(len(enviados), 1)
        self.assertIn('CCD --- total 4,000 kg', enviados[0][1])
        self.assertIn('Fechamento', enviados[0][1])

    def test_agendador_ignora_horario_diferente(self):
        dest = PesagemWhatsAppDestino(
            nome='Operador',
            telefone='5521999990000',
            hora=dt_time(7, 0),
            mensagem='Manhã',
            ativo=True,
        )
        db.session.add(dest)
        db.session.commit()
        enviados = []
        agora = datetime.combine(date.today(), dt_time(18, 0))
        result = process_scheduled_sends(now=agora, sender=lambda t, m: enviados.append(1) or {'ok': True})
        self.assertEqual(result, [])
        self.assertEqual(enviados, [])


if __name__ == '__main__':
    unittest.main()
