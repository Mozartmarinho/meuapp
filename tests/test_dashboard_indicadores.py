#!/usr/bin/env python3
"""Indicadores do dashboard: filtros, evolução, mediana e execução."""
import os
import sys
import unittest
from datetime import date, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from chamados_indicadores import calcular_indicadores  # noqa: E402


def _item(**kwargs):
    base = {
        'id': 1,
        'numero': 'OS1',
        'cliente': 'Hospital',
        'servico': 'Manutenção',
        'unidade': 'ti',
        'tipo': 'Estação',
        'status': 'Concluído',
        'fechado': True,
        'criacao': datetime(2026, 11, 1, 8, 0),
        'inicio': datetime(2026, 11, 1, 10, 0),
        'conclusao': datetime(2026, 11, 1, 12, 0),
        'mantenedor': 'Ana',
        'venc_solucao': datetime(2026, 11, 2, 8, 0),
    }
    base.update(kwargs)
    return base


class IndicadoresDashboardTest(unittest.TestCase):
    def test_mediana_prazo_e_indice(self):
        itens = [
            _item(id=1, numero='OS1', inicio=datetime(2026, 11, 1, 10, 0), conclusao=datetime(2026, 11, 1, 12, 0)),
            _item(
                id=2, numero='OS2',
                inicio=datetime(2026, 11, 1, 12, 0),
                conclusao=datetime(2026, 11, 1, 18, 0),
                venc_solucao=datetime(2026, 11, 1, 9, 0),
            ),
            _item(
                id=3, numero='OS3', status='Pendente', fechado=False,
                inicio=None, conclusao=None, mantenedor='Ana', tipo='Hardware',
            ),
        ]
        dados = calcular_indicadores(itens, date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(dados['total'], 3)
        self.assertEqual(dados['tempos'][0]['mediana_resposta_txt'], '3 h')
        self.assertEqual(dados['tempos'][0]['mediana_conclusao_txt'], '7 h')
        self.assertEqual(dados['execucao'][0]['pct_prazo'], 50.0)
        self.assertEqual(dados['execucao'][0]['indice'], 66.7)
        por_tipo = {t['tipo']: t['mediana_txt'] for t in dados['execucao'][0]['tipos']}
        self.assertEqual(por_tipo['Estação'], '7 h')
        self.assertEqual(por_tipo['Hardware'], '—')

    def test_filtro_vale_para_evolucao_e_rankings(self):
        itens = [
            _item(id=1, cliente='A', unidade='ti', servico='Manutenção'),
            _item(id=2, numero='OS2', cliente='B', unidade='nutricao', servico='Reparo', tipo='Hardware'),
            _item(id=3, numero='OS3', criacao=datetime(2026, 10, 1, 8, 0)),
        ]
        dados = calcular_indicadores(
            itens, date(2026, 11, 1), date(2026, 11, 2), unidade='ti', servico='Manutenção',
        )
        self.assertEqual(dados['total'], 1)
        self.assertEqual(dados['ranking_unidades'][0]['nome'], 'A')
        self.assertEqual(dados['ranking_servicos'][0]['nome'], 'Manutenção corretiva')
        self.assertEqual(dados['ranking_servicos'][1]['nome'], 'Manutenção preventiva')
        self.assertEqual(dados['ranking_servicos'][1]['total'], 0)
        self.assertEqual(sum(dados['evolucao']['abertos']), 1)
        self.assertEqual(sum(dados['evolucao']['concluidos']), 1)
        self.assertEqual(dados['ranking_unidades'][0]['detalhe'][0]['numero'], 'OS1')
        self.assertEqual(dados['ranking_unidades'][0]['detalhe'][0]['prazo'], 'Sim')

    def test_ranking_separa_corretiva_preventiva_e_mesa(self):
        itens = [
            _item(id=1, numero='OS1', mesa_id=1),
            _item(id=2, numero='OS2', mesa_id=2, preventiva=True),
            _item(id=3, numero='OS3', mesa_id=1, preventiva=True),
        ]
        dados = calcular_indicadores(itens, date(2026, 11, 1), date(2026, 11, 30), mesa=1)
        por = {linha['nome']: linha['total'] for linha in dados['ranking_servicos']}
        self.assertEqual(por['Manutenção corretiva'], 1)
        self.assertEqual(por['Manutenção preventiva'], 1)
        self.assertEqual(dados['ranking_servicos'][1]['detalhe'][0]['servico'], 'Manutenção preventiva')
        self.assertEqual(dados['total'], 2)
        self.assertEqual(dados['ranking_unidades'][0]['total'], 2)
        self.assertEqual(sum(dados['evolucao']['abertos']), 2)
        self.assertEqual([linha['nome'] for linha in dados['tempos']], ['Ana'])
        self.assertEqual(dados['tempos'][0]['mediana_resposta'], 2.0)
        self.assertEqual([linha['nome'] for linha in dados['execucao']], ['Ana'])
        self.assertEqual(dados['execucao'][0]['total'], 2)
        self.assertEqual(dados['filtros']['mesa'], '1')

    def test_sem_chamados(self):
        dados = calcular_indicadores([], date(2026, 11, 1), date(2026, 11, 3))
        self.assertEqual(dados['total'], 0)
        self.assertEqual(dados['ranking_unidades'], [])
        self.assertEqual(dados['tempos'], [])
        self.assertEqual(len(dados['evolucao']['labels']), 3)
        self.assertEqual(sum(dados['evolucao']['abertos']), 0)


if __name__ == '__main__':
    unittest.main()
