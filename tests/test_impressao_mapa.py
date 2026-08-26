#!/usr/bin/env python3
"""Impressão do mapa da nutrição: totais de dietas e refeições no período."""
import os
import sys
import unittest
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutMapaRefeicao  # noqa: E402
from nutricao_service import gerar_impressao_mapa  # noqa: E402


class ImpressaoMapaTest(unittest.TestCase):
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
        db.session.query(NutMapaRefeicao).delete()
        db.session.commit()
        hoje = date.today()
        db.session.add(NutMapaRefeicao(
            data_refeicao=hoje,
            nome='Ana Teste',
            clinica='3º CM + VASCULAR',
            leito='01',
            prontuario='100',
            idade=40,
            diagnostico='ISOLAMENTO contato',
            dieta='BRANDA COM SAL',
            observacoes='jejum à noite',
            adm=hoje - timedelta(days=2),
            fl_desjejum=True,
            fl_colacao=False,
            fl_almoco=True,
            fl_merenda=True,
            fl_jantar=True,
            fl_ceia=False,
            ativo=True,
        ))
        db.session.add(NutMapaRefeicao(
            data_refeicao=hoje,
            nome='Bruno Teste',
            clinica='ONCO',
            leito='02',
            dieta='LIQUIDA SEM SAL',
            fl_desjejum=True,
            fl_almoco=True,
            fl_jantar=False,
            ativo=True,
        ))
        db.session.commit()

    def test_totais_e_isolamento(self):
        rel = gerar_impressao_mapa(date.today(), date.today(), clinica_nome='3º CM + VASCULAR')
        self.assertEqual(rel['total_dietas'], 1)
        self.assertEqual(rel['totais_refeicao']['desjejum'], 1)
        self.assertEqual(rel['totais_refeicao']['almoco'], 1)
        self.assertEqual(rel['totais_refeicao']['ceia'], 0)
        self.assertEqual(rel['linhas'][0]['d'], 'X')
        self.assertEqual(rel['linhas'][0]['c'], '')
        self.assertEqual(rel['linhas'][0]['isolamento'], 'X')
        self.assertEqual(rel['soma_dietas'][0]['qtd'], 1)

    def test_todas_clinicas(self):
        rel = gerar_impressao_mapa(date.today(), date.today())
        self.assertEqual(rel['total_dietas'], 2)
        self.assertEqual(rel['totais_refeicao']['desjejum'], 2)
        self.assertEqual(rel['totais_refeicao']['jantar'], 1)


if __name__ == '__main__':
    unittest.main()
