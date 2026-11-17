#!/usr/bin/env python3
"""Mapa da U.M.A.: filtros do SCN e totais por horário, sistema e grupo."""
import os
import sys
import unittest
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import (  # noqa: E402
    NutClinica, NutDieta, NutGrupoClinica, NutMapaRefeicao,
)
from nutricao_service import totalizar_mapa_uma  # noqa: E402


class MapaUmaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cti = NutClinica(nome='CETIP-200', ativo=True)
        ped = NutClinica(nome='PEDIATRIA', ativo=True)
        g_cti = NutGrupoClinica(nome='CTI', ativo=True)
        g_inf = NutGrupoClinica(nome='INFANTIL', ativo=True)
        db.session.add_all([cti, ped, g_cti, g_inf, NutDieta(nome='NEONATAL', grupo='LACTARIO', ativo=True)])
        db.session.flush()
        g_cti.clinicas.append(cti)
        g_inf.clinicas.append(ped)
        db.session.commit()
        cls.cti_id = cti.id
        cls.ped_id = ped.id
        cls.g_cti_id = g_cti.id

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
            nome='NATHAN GAEL',
            clinica='CETIP-200',
            leito='04',
            prontuario='8381572',
            idade=2,
            diagnostico='BRONQUIOLITE / GASTROQUISE',
            dieta='ENTERAL',
            enteral='FREBINI ORIGINAL 500 ML D: 2 / 6 / 10 / 14 / 18 / 22 / 280ML',
            ativo=True,
        ))
        db.session.add(NutMapaRefeicao(
            data_refeicao=hoje,
            nome='PACIENTE FECHADO',
            clinica='CETIP-200',
            leito='05',
            prontuario='111',
            diagnostico='SEPSE',
            dieta='ENTERAL',
            enteral='FRESUBIN FECHADO 500 ML D: 2 / 8 / 14 / 20 /',
            ativo=True,
        ))
        db.session.add(NutMapaRefeicao(
            data_refeicao=hoje,
            nome='MARCIA CRISTINA',
            clinica='PEDIATRIA',
            enfermaria='MATERNIDADE',
            leito='15',
            idade=36,
            diagnostico='DMG',
            dieta='NEONATAL',
            formula_infantil='NAN COMFORT 1 40ML 2 / 6 / 10 / 14 / 18 / 20 / 22 / 24 / CHUCA',
            ativo=True,
        ))
        db.session.add(NutMapaRefeicao(
            data_refeicao=hoje,
            nome='ANTONIO CARLOS',
            clinica='PEDIATRIA',
            leito='01',
            prontuario='8455419',
            diagnostico='DISFAGIA',
            suplementos='NOVASOURCE PROLINE MORANGO 200 ML 15 /',
            ativo=True,
        ))
        db.session.commit()

    def test_grade_json_entra_no_mapa(self):
        import json
        db.session.add(NutMapaRefeicao(
            data_refeicao=date.today(),
            nome='JSON PAC',
            clinica='PEDIATRIA',
            enfermaria='ALA A',
            leito='09',
            suplementos=json.dumps({'uma_itens': [{
                'enfermaria': 'ALA A',
                'leito': '09',
                'suplemento': 'ENSURE',
                'volume': '200',
                'unid': 'ML',
                'h8': True,
                'h20': True,
                'embalagem': 'LATA',
            }]}),
            ativo=True,
        ))
        db.session.commit()
        rel = totalizar_mapa_uma(
            date.today(),
            categoria='suplementos',
            sistema='ambos',
            selecionar_horarios=False,
        )
        ln = next(x for x in rel['grupos'][0]['linhas'] if x['nome'] == 'JSON PAC')
        self.assertIn('ENSURE', ln['produto'])
        self.assertEqual(ln['horas'], [8, 20])
        self.assertEqual(ln['volume'], '200ML')

    def test_enteral_cobranca_volume_e_horarios(self):
        rel = totalizar_mapa_uma(
            date.today(),
            categoria='enteral',
            tipo_mapa='cobranca',
            sistema='aberto',
            selecionar_horarios=False,
        )
        self.assertEqual(rel['titulo'], 'MAPA DE ENTERAL')
        self.assertIn('COBRANÇA', rel['subtitulo'])
        self.assertEqual(rel['sistema_label'], 'Aberto')
        nomes = [ln['nome'] for ln in rel['grupos'][0]['linhas']]
        self.assertEqual(nomes, ['NATHAN GAEL'])
        ln = rel['grupos'][0]['linhas'][0]
        self.assertEqual(ln['produto'], 'FREBINI ORIGINAL 500 ML 280ML')
        self.assertEqual(ln['horas'], [2, 6, 10, 14, 18, 22])
        self.assertEqual(ln['etapas'], 6)
        self.assertEqual(ln['volume'], '280ML')
        self.assertEqual(ln['total'], '1680,0 ML')
        self.assertEqual(ln['sis'], 'A')
        self.assertEqual(ln['extra'], 'BRONQUIOLITE / GASTROQUISE')
        self.assertEqual(ln['horas_enteral'], 'D: 2 / 6 / 10 / 14 / 18 / 22 /')

    def test_sistema_fechado_e_horario(self):
        rel = totalizar_mapa_uma(
            date.today(),
            categoria='enteral',
            sistema='fechado',
            selecionar_horarios=True,
            horarios=[8, 20],
        )
        linhas = rel['grupos'][0]['linhas']
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]['nome'], 'PACIENTE FECHADO')
        self.assertEqual(linhas[0]['sis'], 'F')
        self.assertEqual(linhas[0]['horas'], [8, 20])
        self.assertEqual(linhas[0]['etapas'], 2)
        self.assertEqual(rel['horarios'], [8, 20])

    def test_formula_grupo_dieta_e_via(self):
        rel = totalizar_mapa_uma(
            date.today(),
            categoria='formula_infantil',
            tipo_mapa='trabalho',
            coluna_extra='grupo_dieta',
            selecionar_horarios=False,
            linhas_em_branco=3,
            nao_imprimir_produto=False,
        )
        ln = rel['grupos'][0]['linhas'][0]
        self.assertEqual(ln['nome'], 'MARCIA CRISTINA')
        self.assertEqual(ln['extra'], 'LACTARIO')
        self.assertEqual(ln['via'], 'CHUCA')
        self.assertEqual(ln['vol_infantil'], '40')
        self.assertEqual(ln['etapas'], 8)
        self.assertEqual(ln['total_infantil'], '320')
        self.assertEqual(ln['idade'], '36A')
        self.assertIn('NAN COMFORT 1', ln['produto'])
        self.assertEqual(rel['linhas_em_branco'], 3)
        self.assertEqual(rel['layout'], 'grade')
        bloco = rel['grupos'][0]['secoes'][0]['blocos'][0]['produto']
        self.assertIn('NAN COMFORT', bloco)
        from flask import render_template
        with self.app.test_request_context():
            html = render_template('nutricao_relatorio_mapa_uma_print.html', r=rel)
        self.assertIn('MAPA DE FÓRMULAS INFANTIS', html)
        self.assertIn('CHUCA', html)
        self.assertIn('>2</th>', html)
        self.assertIn('LACTARIO', html)

    def test_separa_grupo_e_oculta_produto(self):
        rel = totalizar_mapa_uma(
            date.today(),
            categoria='suplementos',
            sistema='fechado',
            separar_grupo=True,
            nao_imprimir_produto=True,
            selecionar_horarios=True,
            horarios=[15],
            grupo_clinica_id=None,
        )
        self.assertEqual(len(rel['grupos']), 1)
        self.assertEqual(rel['grupos'][0]['nome'], 'INFANTIL')
        ln = rel['grupos'][0]['linhas'][0]
        self.assertEqual(ln['nome'], 'ANTONIO CARLOS')
        self.assertEqual(ln['produto'], '')
        self.assertEqual(ln['horas'], [15])
        self.assertEqual(ln['volume'], '200ML')
        self.assertEqual(rel['layout'], 'lista')
        from flask import render_template
        with self.app.test_request_context():
            html = render_template('nutricao_relatorio_mapa_uma_print.html', r=rel)
        self.assertIn('MAPA DE SUPLEMENTOS', html)
        self.assertIn('ANTONIO CARLOS', html)
        self.assertNotIn('NOVASOURCE', html)

    def test_filtra_grupo_clinica(self):
        rel = totalizar_mapa_uma(
            date.today(),
            categoria='enteral',
            sistema='ambos',
            grupo_clinica_id=self.g_cti_id,
            selecionar_horarios=False,
        )
        nomes = sorted(ln['nome'] for ln in rel['grupos'][0]['linhas'])
        self.assertEqual(nomes, ['NATHAN GAEL', 'PACIENTE FECHADO'])
        self.assertEqual(rel['grupo_nome'], 'CTI')

    def test_impressao_renderiza(self):
        from flask import render_template
        rel = totalizar_mapa_uma(
            date.today(),
            categoria='enteral',
            tipo_mapa='cobranca',
            sistema='aberto',
            selecionar_horarios=False,
            linhas_em_branco=1,
        )
        with self.app.test_request_context():
            html = render_template('nutricao_relatorio_mapa_uma_print.html', r=rel)
        self.assertIn('MAPA DE ENTERAL', html)
        self.assertIn('PEDIDO / COBRANÇA DE DIETAS ENTERAIS', html)
        self.assertIn('NATHAN GAEL', html)
        self.assertIn('1680,0 ML', html)
        self.assertNotIn('PACIENTE FECHADO', html)
        self.assertIn('Sis.', html)


if __name__ == '__main__':
    unittest.main()
