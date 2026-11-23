#!/usr/bin/env python3
"""Cadastros de nutrição não vazam de um hospital para outro."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import Cliente, Usuario, db  # noqa: E402
from models_nutricao import NutClinica, NutDieta  # noqa: E402


class IsolamentoClienteNutricaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cls.client = cls.app.test_client()

        cls.hfb = Cliente(nome='HOSPITAL FEDERAL DE BONSUCESSO', ativo=True, habilitado_nutricao=True)
        cls.ipanema = Cliente(nome='HOSPITAL FEDERAL DE IPANEMA', ativo=True, habilitado_nutricao=True)
        db.session.add_all([cls.hfb, cls.ipanema])
        db.session.flush()
        db.session.add(NutClinica(
            nome='CLINICA SO BONSUCESSO', ativo=True, cliente_id=cls.hfb.id,
        ))
        db.session.add(NutDieta(
            nome='DIETA SO BONSUCESSO', categoria='basica', grupo='', ativo=True, cliente_id=cls.hfb.id,
        ))
        cls.user = Usuario(
            nome='Mario Ipanema',
            email='mario.ipanema.isolamento@test.local',
            senha='x',
            ativo=True,
            is_master=False,
            tipo='operador',
            cliente_id=cls.ipanema.id,
            cliente_todos=False,
            perm_nutricao=True,
        )
        db.session.add(cls.user)
        db.session.commit()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_clinicas_do_outro_hospital_nao_aparecem(self):
        resp = self.client.get('/nutricao/clinicas')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn('Clínica Médica', html)
        self.assertNotIn('Centro Cirúrgico', html)
        self.assertNotIn('CLINICA SO BONSUCESSO', html)
        self.assertNotIn('CABEÇA E PESCOÇO', html)
        self.assertIn('HOSPITAL FEDERAL DE IPANEMA', html)

        api = self.client.get('/nutricao/api/clinicas')
        self.assertEqual(api.status_code, 200)
        nomes = [c.get('nome') for c in api.get_json()]
        self.assertNotIn('CLINICA SO BONSUCESSO', nomes)
        self.assertNotIn('Clínica Médica', nomes)
        self.assertNotIn('Centro Cirúrgico', nomes)

    def test_dietas_e_novo_lancamento_ficam_no_cliente(self):
        dietas = self.client.get('/nutricao/api/dietas')
        self.assertEqual(dietas.status_code, 200)
        nomes = [d.get('nome') for d in dietas.get_json()]
        self.assertNotIn('DIETA SO BONSUCESSO', nomes)

        criado = self.client.post('/nutricao/api/clinicas', json={
            'nome': 'CLINICA IPANEMA',
            'ativo': True,
        })
        self.assertEqual(criado.status_code, 200)
        self.assertTrue(criado.get_json().get('ok'))
        row = NutClinica.query.filter_by(nome='CLINICA IPANEMA').one()
        self.assertEqual(row.cliente_id, self.ipanema.id)

        mesmo_nome = self.client.post('/nutricao/api/clinicas', json={
            'nome': 'CLINICA SO BONSUCESSO',
            'ativo': True,
        })
        self.assertEqual(mesmo_nome.status_code, 200)
        self.assertTrue(mesmo_nome.get_json().get('ok'))
        do_ipanema = NutClinica.query.filter_by(
            nome='CLINICA SO BONSUCESSO', cliente_id=self.ipanema.id,
        ).one()
        self.assertNotEqual(do_ipanema.id, NutClinica.query.filter_by(
            nome='CLINICA SO BONSUCESSO', cliente_id=self.hfb.id,
        ).one().id)
