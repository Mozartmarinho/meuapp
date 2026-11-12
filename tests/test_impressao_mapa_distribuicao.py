#!/usr/bin/env python3
"""Impressão do mapa de distribuição: clínica, período e tipo de refeição."""
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
from nutricao_service import (  # noqa: E402
    gerar_impressao_mapa_distribuicao,
    tipo_refeicao_para_meal,
)


class ImpressaoMapaDistribuicaoTest(unittest.TestCase):
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
            nome='Ana Dist',
            clinica='3º CM + VASCULAR',
            leito='01',
            prontuario='100',
            dieta='BRANDA COM SAL',
            observacoes='jejum',
            adm=hoje - timedelta(days=2),
            fl_desjejum=True,
            fl_colacao=False,
            fl_almoco=True,
            fl_merenda=False,
            fl_jantar=False,
            fl_ceia=False,
            ativo=True,
        ))
        db.session.add(NutMapaRefeicao(
            data_refeicao=hoje,
            nome='Bruno Dist',
            clinica='ONCO',
            leito='02',
            prontuario='200',
            dieta='LIQUIDA SEM SAL',
            observacoes='',
            fl_desjejum=True,
            fl_almoco=False,
            fl_jantar=True,
            ativo=True,
        ))
        db.session.commit()

    def test_tipo_refeicao_para_meal(self):
        self.assertEqual(tipo_refeicao_para_meal('ALM'), 'almoco')
        self.assertEqual(tipo_refeicao_para_meal('Almoço'), 'almoco')
        self.assertEqual(tipo_refeicao_para_meal('almoco'), 'almoco')

    def test_filtra_almoco_e_agrupa_clinica(self):
        rel = gerar_impressao_mapa_distribuicao(
            date.today(), date.today(), tipo_refeicao='almoco',
        )
        self.assertEqual(rel['titulo'], 'MAPA DISTRIBUIÇÃO')
        self.assertEqual(rel['tipo_label'], 'ALMOÇO')
        self.assertEqual(rel['total'], 1)
        self.assertEqual(len(rel['grupos']), 1)
        self.assertEqual(rel['grupos'][0]['clinica'], '3º CM + VASCULAR')
        linha = rel['grupos'][0]['linhas'][0]
        self.assertEqual(linha['nome'], 'Ana Dist')
        self.assertEqual(linha['prontuario'], '100')
        self.assertEqual(linha['leito'], '01')
        self.assertEqual(linha['dieta'], 'BRANDA COM SAL')
        self.assertEqual(linha['obs'], 'jejum')

    def test_filtro_clinica_e_desjejum(self):
        rel = gerar_impressao_mapa_distribuicao(
            date.today(),
            date.today(),
            clinica_nomes=['ONCO'],
            tipo_refeicao='DESJ',
        )
        self.assertEqual(rel['total'], 1)
        self.assertEqual(rel['grupos'][0]['linhas'][0]['nome'], 'Bruno Dist')
        self.assertEqual(rel['tipo'], 'desjejum')


if __name__ == '__main__':
    unittest.main()
