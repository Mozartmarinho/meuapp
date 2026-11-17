#!/usr/bin/env python3
"""Análise, evolução e totalização direta ligadas ao paciente e à clínica."""
import os
import sys
import unittest
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutClinica, NutMapaRefeicao, NutPaciente  # noqa: E402
from nutricao_clinico import (  # noqa: E402
    calcular_avaliacao, listar_evolucoes, listar_totalizacao_direta,
    salvar_avaliacao, salvar_evolucao, salvar_totalizacao_direta,
)


class NutricaoClinicoTest(unittest.TestCase):
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
        db.session.query(NutPaciente).delete()
        db.session.query(NutClinica).delete()
        from models_nutricao import NutAvaliacaoNutricional, NutEvolucaoPaciente, NutTotalizacaoDireta
        db.session.query(NutAvaliacaoNutricional).delete()
        db.session.query(NutEvolucaoPaciente).delete()
        db.session.query(NutTotalizacaoDireta).delete()
        db.session.commit()

    def test_calculos_harris_benedict(self):
        calc = calcular_avaliacao({
            'peso_atual': 70,
            'estatura_cm': 170,
            'peso_habitual': 80,
            'sexo': 'M',
            'idade': 40,
            'fator_atividade': 1.2,
            'fator_injuria': 1,
            'fator_termico': 1,
            'prega_biceps': 10,
            'prega_triceps': 12,
            'prega_subescapular': 14,
            'prega_suprailiaca': 16,
            'circ_braco': 30,
        })
        self.assertEqual(calc['imc'], 24.22)
        self.assertEqual(calc['peso_teorico'], 63.6)
        self.assertEqual(calc['perda_peso'], 12.5)
        self.assertEqual(calc['geb'], 1609.4)
        self.assertEqual(calc['get'], 1931.3)
        self.assertEqual(calc['get_kg'], 27.6)
        self.assertEqual(calc['gordura'], 13.7)
        self.assertEqual(calc['cmb'], 26.2)

    def test_avaliacao_atualiza_peso_do_paciente(self):
        pac = NutPaciente(nome='Ana', sexo='F', peso_kg=60, altura_cm=160, ativo=True)
        db.session.add(pac)
        db.session.flush()
        linha = NutMapaRefeicao(
            data_refeicao=date.today(), paciente_id=pac.id, nome='Ana',
            leito='01', clinica='CTI', dieta='BRANDA', idade=30, ativo=True,
        )
        db.session.add(linha)
        db.session.commit()
        ctx = {'paciente_id': pac.id, 'mapa_id': linha.id, 'dieta': 'BRANDA'}
        salvar_avaliacao({'peso_atual': 58.5, 'estatura_cm': 161, 'sexo': 'F', 'idade': 30}, date.today(), ctx)
        db.session.refresh(pac)
        self.assertEqual(pac.peso_kg, 58.5)
        self.assertEqual(pac.altura_cm, 161)

    def test_evolucao_ligada_ao_paciente(self):
        ctx = {'paciente_id': None, 'mapa_id': None, 'dieta': 'ENTERAL', 'clinica': 'CTI', 'leito': '04'}
        pac = NutPaciente(nome='Nathan', sexo='M', ativo=True)
        db.session.add(pac)
        db.session.commit()
        ctx['paciente_id'] = pac.id
        salvar_evolucao({'tipo': 'tne', 'alteracoes': 'estável', 'conduta': 'manter'}, date.today(), ctx)
        itens = listar_evolucoes(pac.id)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]['tipo'], 'tne')
        self.assertEqual(itens[0]['conduta'], 'manter')
        self.assertEqual(itens[0]['clinica'], 'CTI')

    def test_totalizacao_direta_soma_refeicao(self):
        cli = NutClinica(nome='CETIP-200', ativo=True)
        db.session.add(cli)
        db.session.commit()
        salvar_totalizacao_direta({
            'clinica': 'CETIP-200', 'clinica_id': cli.id, 'tipo': 'dieta',
            'item': 'BRANDA', 'quantidades': {'almoco': 4, 'jantar': 3},
        }, date.today())
        salvar_totalizacao_direta({
            'clinica': 'CETIP-200', 'tipo': 'dieta', 'dieta': 'BRANDA',
            'horario': 'Almoço', 'quantidade': 6,
        }, date.today())
        linhas = listar_totalizacao_direta(date.today(), 'CETIP-200')
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]['quantidades']['almoco'], 6)
        self.assertEqual(linhas[0]['quantidades']['jantar'], 3)
        self.assertEqual(linhas[0]['total'], 9)
        self.assertEqual(linhas[0]['clinica_id'], cli.id)


if __name__ == '__main__':
    unittest.main()
