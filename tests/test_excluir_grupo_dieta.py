#!/usr/bin/env python3
"""A lixeira apaga o grupo de dieta e o seed não recria o nome."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutDieta, NutGrupoDieta, NutGrupoDietaExcluido  # noqa: E402
from nutricao_service import _seed_grupos_dieta  # noqa: E402
from nutricao_tenant import ensure_cliente_hfb  # noqa: E402


class ExcluirGrupoDietaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_lixeira_apaga_grupo_e_seed_nao_recria(self):
        cid = ensure_cliente_hfb().id
        row = NutGrupoDieta(cliente_id=cid, nome='LACTÁRIO', ordem=10, ativo=True)
        dieta = NutDieta(
            cliente_id=cid,
            nome='LEITE TESTE GRUPO',
            categoria='basica',
            grupo='LACTÁRIO',
            ativo=True,
        )
        db.session.add_all([row, dieta])
        db.session.commit()
        gid = row.id

        resp = self.client.delete('/nutricao/api/grupos-dietas/%s' % gid)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        self.assertTrue(resp.get_json().get('ok'))
        self.assertIsNone(NutGrupoDieta.query.get(gid))
        self.assertIsNotNone(
            NutGrupoDietaExcluido.query.filter(
                db.func.upper(NutGrupoDietaExcluido.nome) == 'LACTÁRIO'
            ).first()
        )

        _seed_grupos_dieta()
        db.session.commit()
        self.assertIsNone(
            NutGrupoDieta.query.filter(db.func.upper(NutGrupoDieta.nome) == 'LACTÁRIO').first()
        )

        de_novo = self.client.post('/nutricao/api/grupos-dietas', json={
            'nome': 'LACTÁRIO',
            'ordem': 10,
            'ativo': True,
        })
        self.assertEqual(de_novo.status_code, 200, de_novo.get_data(as_text=True))
        self.assertTrue(de_novo.get_json().get('ok'))
        self.assertIsNotNone(
            NutGrupoDieta.query.filter(db.func.upper(NutGrupoDieta.nome) == 'LACTÁRIO').first()
        )
        self.assertIsNone(
            NutGrupoDietaExcluido.query.filter(
                db.func.upper(NutGrupoDietaExcluido.nome) == 'LACTÁRIO'
            ).first()
        )

    def test_pagina_chama_a_lixeira_de_excluir(self):
        html = self.client.get('/nutricao/grupos-dietas').get_data(as_text=True)
        self.assertIn('Excluir este grupo de dieta?', html)
        self.assertIn('title="Excluir"', html)
        self.assertNotIn('Desativar este grupo de dieta?', html)
