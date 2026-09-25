#!/usr/bin/env python3
"""Preventiva automática e termo de responsabilidade de equipamentos."""
import os
import sys
import unittest
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['PESAGEM_WA_DISABLE'] = '1'
os.environ['EQ_PREVENTIVA_DISABLE'] = '1'

from app import create_app, ensure_equipamentos_schema  # noqa: E402
from models import (  # noqa: E402
    Chamado,
    Cliente,
    Equipamento,
    EquipamentoPreventiva,
    EquipamentoTermo,
    MesaServico,
    Usuario,
    db,
)
from password_utils import generate_password_hash  # noqa: E402
from equipamento_service import (  # noqa: E402
    avancar_data,
    criar_ou_reenviar_termo,
    processar_preventivas,
    salvar_preventiva,
    salvar_termo,
    assinar_termo,
)

PNG_B64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM'
    'IQAAAABJRU5ErkJggg=='
)


class EquipamentoPreventivaTermoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        ensure_equipamentos_schema()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def setUp(self):
        Chamado.query.delete()
        EquipamentoTermo.query.delete()
        EquipamentoPreventiva.query.delete()
        Equipamento.query.delete()
        MesaServico.query.delete()
        Cliente.query.delete()
        Usuario.query.delete()
        db.session.commit()
        self.user = Usuario(
            nome='Admin TI',
            email='ti-eq@test.local',
            senha=generate_password_hash('admin'),
            tipo='admin',
            is_master=True,
            perm_chamados=True,
            ativo=True,
        )
        self.cli = Cliente(nome='São Geraldo', ativo=True, habilitado_chamados=True)
        self.mesa = MesaServico(nome='Suporte', ativa=True)
        db.session.add_all([self.user, self.cli, self.mesa])
        db.session.commit()
        self.eq = Equipamento(
            nome_equipamento='Desktop',
            patrimonio='0078',
            marca='Pichau',
            modelo='Gamer',
            numero_serie='SN-1',
            cliente_id=self.cli.id,
            setor='Informática',
            ativo=True,
        )
        db.session.add(self.eq)
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id

    def test_avancar_mensal(self):
        self.assertEqual(avancar_data(date(2026, 1, 31), 'mensal'), date(2026, 2, 28))

    def test_preventiva_abre_chamado_quando_vencida(self):
        prev, chamado = salvar_preventiva(self.eq, {
            'ativa': True,
            'frequencia': 'mensal',
            'proxima_data': date.today().isoformat(),
            'duracao_dias': 3,
        }, self.user)
        self.assertTrue(prev.ativa)
        self.assertIsNotNone(chamado)
        self.assertTrue(chamado.descricao.startswith('Preventiva:'))
        self.assertEqual(chamado.equipamento_id, self.eq.id)
        self.assertGreater(prev.proxima_data, date.today())

    def test_preventiva_usa_mesa_do_tipo(self):
        info = MesaServico(nome='Informatica', ativa=True)
        nutri = MesaServico(nome='Manutenção Nutrição', ativa=True)
        db.session.add_all([info, nutri])
        db.session.commit()
        self.eq.tipo_equipamento = 'ti'
        _, chamado_ti = salvar_preventiva(self.eq, {
            'ativa': True,
            'frequencia': 'mensal',
            'proxima_data': date.today().isoformat(),
        }, self.user)
        self.assertEqual(chamado_ti.mesa_id, info.id)
        eq_nutri = Equipamento(
            nome_equipamento='Forno',
            patrimonio='N-1',
            cliente_id=self.cli.id,
            tipo_equipamento='nutricao',
            ativo=True,
        )
        db.session.add(eq_nutri)
        db.session.commit()
        _, chamado_nutri = salvar_preventiva(eq_nutri, {
            'ativa': True,
            'frequencia': 'mensal',
            'proxima_data': date.today().isoformat(),
        }, self.user)
        self.assertEqual(chamado_nutri.mesa_id, nutri.id)

    def test_processar_nao_duplica_ticket_aberto(self):
        salvar_preventiva(self.eq, {
            'ativa': True,
            'frequencia': 'semanal',
            'proxima_data': date.today().isoformat(),
        }, self.user)
        n1 = Chamado.query.count()
        criados = processar_preventivas(hoje=date.today())
        self.assertEqual(criados, 0)
        self.assertEqual(Chamado.query.count(), n1)

    def test_termo_envio_e_assinatura(self):
        termo, link, canais, _erros = criar_ou_reenviar_termo(
            self.eq,
            {
                'responsavel_nome': 'Maria Silva',
                'responsavel_email': '',
                'enviar_email': False,
            },
            self.user,
            lambda token: 'http://test/termo/' + token,
        )
        self.assertEqual(termo.status, 'enviado')
        self.assertIn('/termo/', link)
        self.assertEqual(self.eq.termo_atual().id, termo.id)

        assinar_termo(termo, {
            'responsavel_nome': 'Maria Silva',
            'responsavel_setor': 'Cozinha',
            'assinatura': 'data:image/png;base64,' + PNG_B64,
        })
        self.assertEqual(termo.status, 'assinado')
        self.assertTrue(termo.assinatura_path)
        d = self.eq.to_dict()
        self.assertEqual(d['termo_status'], 'assinado')
        self.assertEqual(d['termo_responsavel'], 'Maria Silva')

    def test_api_preventiva_e_pagina_publica(self):
        r = self.client.post('/api/equipamentos/%s/preventiva' % self.eq.id, json={
            'ativa': True,
            'frequencia': 'mensal',
            'proxima_data': (date.today() + timedelta(days=10)).isoformat(),
            'duracao_dias': 1,
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get('ok'))

        env = self.client.post('/api/equipamentos/%s/termo/enviar' % self.eq.id, json={
            'responsavel_nome': 'João',
            'enviar_email': False,
            'acessorios': [
                {'nome': 'Equipamento', 'qtd': '01', 'obs': ''},
                {'nome': 'Mouse', 'qtd': '01', 'obs': 'sem fio'},
            ],
        })
        self.assertEqual(env.status_code, 200)
        data = env.get_json()
        token = data['termo']['token']
        self.assertEqual(len(data['termo']['acessorios']), 2)
        page = self.client.get('/termo/' + token)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'TERMO DE RESPONSABILIDADE', page.data)
        self.assertIn(b'EQUIPAMENTO DE TI', page.data)
        self.assertIn(b'Mouse', page.data)
        self.assertNotIn(b'Teclado', page.data)

        signed = self.client.post('/termo/' + token, json={
            'responsavel_nome': 'João',
            'assinatura': 'data:image/png;base64,' + PNG_B64,
        })
        self.assertEqual(signed.status_code, 200)
        lista = self.client.get('/equipamentos')
        self.assertEqual(lista.status_code, 200)
        self.assertIn(b'is-assinado', lista.data)
        pr = self.client.get('/equipamentos/%s/termo/imprimir' % self.eq.id)
        self.assertEqual(pr.status_code, 200)
        self.assertIn(b'Mouse', pr.data)
        self.assertIn(b'@page', pr.data)

    def test_termo_nutricao_usa_titulo_e_acessorios(self):
        self.eq.tipo_equipamento = 'nutricao'
        db.session.commit()
        r = self.client.post('/api/equipamentos/%s/termo/enviar' % self.eq.id, json={
            'responsavel_nome': 'Ana',
            'enviar_email': False,
            'acessorios': [
                {'nome': 'Equipamento', 'qtd': '01'},
                {'nome': 'Manual do equipamento', 'qtd': '01'},
            ],
        })
        self.assertEqual(r.status_code, 200)
        token = r.get_json()['termo']['token']
        page = self.client.get('/termo/' + token)
        html = page.get_data(as_text=True)
        self.assertIn('EQUIPAMENTO DE MANUTENÇÃO DE NUTRIÇÃO', html)
        self.assertIn('Manual do equipamento', html)
        self.assertIn('equipe de Manutenção de Nutrição', html)
        self.assertNotIn('equipe de Tecnologia da Informação', html)

    def test_salvar_termo_guarda_acessorios_sem_enviar(self):
        r = self.client.post('/api/equipamentos/%s/termo/salvar' % self.eq.id, json={
            'responsavel_nome': 'Yuri Jaciel',
            'responsavel_setor': 'Manutenção Nutrição',
            'acessorios': [
                {'nome': 'Teclado', 'qtd': '01', 'obs': ''},
                {'nome': 'Mouse', 'qtd': '01', 'obs': 'sem fio'},
            ],
        })
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['termo']['status'], 'pendente')
        nomes = [i['nome'] for i in data['termo']['acessorios']]
        self.assertEqual(nomes, ['Teclado', 'Mouse'])
        termo = EquipamentoTermo.query.filter_by(equipamento_id=self.eq.id).first()
        self.assertEqual(termo.responsavel_setor, 'Manutenção Nutrição')
        self.assertIsNone(termo.enviado_em)
        salvo = salvar_termo(self.eq, {
            'responsavel_nome': 'Yuri Jaciel',
            'acessorios': [{'nome': 'Monitor', 'qtd': '01'}],
        }, self.user)
        self.assertEqual([i['nome'] for i in salvo.acessorios()], ['Monitor'])

    def test_cadastro_grava_tipo_equipamento(self):
        r = self.client.post('/api/equipamentos', json={
            'codigo': 'N-10',
            'nome': 'Batedeira industrial',
            'cliente_id': self.cli.id,
            'tipo_equipamento': 'nutricao',
        })
        self.assertEqual(r.status_code, 200)
        eq = Equipamento.query.filter_by(patrimonio='N-10').first()
        self.assertIsNotNone(eq)
        self.assertEqual(eq.tipo_equipamento_norm(), 'nutricao')
        self.assertEqual(eq.to_dict()['tipo_equipamento_label'], 'Equipamento da manutenção de nutrição')

    def test_acoes_template_tem_preventiva_e_termo(self):
        html_path = os.path.join(ROOT, 'templates', 'equipamentos.html')
        with open(html_path, encoding='utf-8') as fh:
            html = fh.read()
        self.assertIn('btn-prev-eq', html)
        self.assertIn('btn-termo-eq', html)
        self.assertIn('Cronograma preventiva', html)
        self.assertIn('eq-acc-list', html)
        self.assertIn('tipo_equipamento', html)
        self.assertIn('btnAddAcc', html)
        self.assertIn('btnSalvarTermo', html)


if __name__ == '__main__':
    unittest.main()
