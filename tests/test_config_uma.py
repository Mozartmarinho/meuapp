#!/usr/bin/env python3
"""Configuração da U.M.A.: via padrão, gotejamento, estoque e validade."""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutMapaRefeicao  # noqa: E402
from nutricao_service import (  # noqa: E402
    calcular_gotejamento_uma,
    config_uma_dict,
    layout_etiqueta_impressao,
    relatorio_faturamento,
    salvar_config_uma,
    seed_nutricao,
)
from datetime import date  # noqa: E402


class ConfigUmaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        seed_nutricao()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_continuo_divide_por_15(self):
        self.assertEqual(calcular_gotejamento_uma(300, {'gotejamento_metodo': 'continuo'}), 20)
        self.assertEqual(
            calcular_gotejamento_uma('280', {'gotejamento_metodo': 'calculado', 'gotejamento_horas': 3.5}),
            80,
        )

    def test_grava_via_agua_e_validade(self):
        cfg = salvar_config_uma({
            'via_enteral': 'sne',
            'via_suplemento': 'chuca',
            'via_formula': 'lve',
            'via_agua': 'vo',
            'volume_agua': '50,0',
            'gotejamento_metodo': 'calculado',
            'gotejamento_horas': '3,5',
            'validades': [
                {'horario': '6:00', 'valido_ate': '10:00'},
                {'horario': '99:00', 'valido_ate': '10:00'},
            ],
        })
        self.assertEqual(cfg['via_enteral'], 'SNE')
        self.assertEqual(cfg['via_formula'], 'LVE')
        self.assertEqual(cfg['volume_agua'], 50)
        self.assertEqual(cfg['gotejamento_metodo'], 'calculado')
        self.assertEqual(cfg['gotejamento_horas'], 3.5)
        self.assertEqual(cfg['horas_divisao'], 3.5)
        self.assertEqual(cfg['validades'], [{'horario': '06:00', 'valido_ate': '10:00'}])
        de_novo = config_uma_dict()
        self.assertEqual(de_novo['via_enteral'], 'SNE')

    def test_calculado_sem_hora_recusa(self):
        with self.assertRaises(ValueError):
            salvar_config_uma({
                'gotejamento_metodo': 'calculado',
                'gotejamento_horas': '0',
            })

    def test_pagina_e_api(self):
        pagina = self.client.get('/nutricao/configuracoes')
        self.assertEqual(pagina.status_code, 200)
        html = pagina.get_data(as_text=True)
        self.assertIn('Definir via padrão', html)
        self.assertIn('Água para lavagem dos frascos', html)
        self.assertIn('Método de gotejamento', html)
        self.assertIn('Validade das etiquetas', html)
        self.assertIn('Configuração da etiqueta', html)
        self.assertIn('Tachado duplo', html)
        self.assertIn('Pimaco 6080', html)
        self.assertIn('Contínuo (vol/15)', html)
        api = self.client.get('/nutricao/api/config-uma')
        self.assertEqual(api.status_code, 200)
        corpo = api.get_json()
        self.assertIn(corpo['gotejamento_metodo'], ('continuo', 'calculado'))

    def test_agua_de_lavagem_entra_no_faturamento(self):
        salvar_config_uma({
            'agua_coluna': 'ÁGUA MINERAL (COPO - 200ML)',
            'gotejamento_metodo': 'continuo',
            'gotejamento_horas': '3,5',
        })
        hoje = date.today()
        linha = NutMapaRefeicao(
            data_refeicao=hoje,
            clinica='CTI',
            enfermaria='A',
            leito='1',
            nome='PACIENTE AGUA',
            ativo=True,
            enteral=json.dumps({'uma_itens': [{
                'dieta': 'DIETA TESTE',
                'vol_dieta': '280',
                'vol_agua': '40',
            }]}),
        )
        db.session.add(linha)
        db.session.commit()
        rel = relatorio_faturamento(hoje, hoje, tipo='total_formulas')
        itens = {item['item']: item['qtd'] for item in rel['formulas']}
        self.assertGreaterEqual(itens.get('ÁGUA MINERAL (COPO - 200ML)', 0), 1)
        db.session.delete(linha)
        db.session.commit()

    def test_layout_etiqueta_grava_fonte(self):
        cfg = salvar_config_uma({
            'layout_etiquetas': {
                'pimaco_6080': {
                    'campos': [{
                        'campo': 'nome',
                        'prefixo': 'Paciente ',
                        'x': 4,
                        'y': 10,
                        'w': 80,
                        'fonte': 'Aptos',
                        'estilo': 'negrito_italico',
                        'tamanho': 12,
                        'cor': '#112233',
                        'sublinhado': 'duplo',
                        'cor_sublinhado': '#ff0000',
                        'maiusculas': True,
                        'tachado': True,
                    }, {
                        'campo': 'NAO_EXISTE',
                        'prefixo': 'sumir',
                    }],
                },
                'ruim id': {'campos': []},
            },
        })
        bloco = cfg['layout_etiquetas']['pimaco_6080']['campos']
        self.assertEqual(len(bloco), 1)
        self.assertEqual(bloco[0]['fonte'], 'Aptos')
        self.assertEqual(bloco[0]['estilo'], 'negrito_italico')
        self.assertTrue(bloco[0]['maiusculas'])
        self.assertNotIn('ruim id', cfg['layout_etiquetas'])
        impresso = layout_etiqueta_impressao('pimaco_6080')
        self.assertEqual(len(impresso), 1)
        css = impresso[0]['estilo_css']
        self.assertIn('font-weight:700', css)
        self.assertIn('font-style:italic', css)
        self.assertIn('text-transform:uppercase', css)
        self.assertIn('text-decoration-line:underline line-through', css)
        self.assertIn('Aptos', css)
        self.assertIsNone(layout_etiqueta_impressao('pimaco_6180'))
        de_novo = config_uma_dict()
        self.assertEqual(de_novo['layout_etiquetas']['pimaco_6080']['campos'][0]['fonte'], 'Aptos')


if __name__ == '__main__':
    unittest.main()
