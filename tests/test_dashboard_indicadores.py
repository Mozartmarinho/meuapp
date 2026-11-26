#!/usr/bin/env python3
"""Indicadores do dashboard: filtros, evolução, mediana e execução."""
import os
import sys
import unittest
import json
import re
from datetime import date, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from chamados_indicadores import calcular_indicadores  # noqa: E402
from models import Chamado, ChamadoTecnico, Cliente, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402
from routes import _query_chamados_usuario  # noqa: E402


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
        self.assertEqual(dados['tempos'][0]['total'], 3)
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

    def test_prazo_vs_inicio_respeita_o_mesmo_filtro(self):
        itens = [
            _item(
                id=1,
                prazo_horas=4,
                criacao=datetime(2026, 11, 1, 8, 0),
                inicio=datetime(2026, 11, 1, 10, 0),
            ),
            _item(
                id=2, numero='OS2', tipo='Hardware', prazo_horas=24,
                criacao=datetime(2026, 11, 1, 8, 0),
                inicio=datetime(2026, 11, 1, 20, 0),
            ),
            _item(
                id=3, numero='OS3', prazo_horas=4, tipo='Estação',
                inicio=None,
            ),
        ]
        dados = calcular_indicadores(itens, date(2026, 11, 1), date(2026, 11, 30), tipo='Estação')
        por_prazo = {linha['prazo']: linha for linha in dados['prazo_atendimento']}
        self.assertEqual(set(por_prazo), {4})
        self.assertEqual(por_prazo[4]['com_inicio'], 1)
        self.assertEqual(por_prazo[4]['sem_inicio'], 1)
        self.assertEqual(por_prazo[4]['dentro'], 1)
        self.assertEqual(por_prazo[4]['mediana'], 2.0)
        self.assertEqual(por_prazo[4]['pct_dentro'], 100.0)
        tudo = calcular_indicadores(itens, date(2026, 11, 1), date(2026, 11, 30))
        prazos = {linha['prazo'] for linha in tudo['prazo_atendimento']}
        self.assertEqual(prazos, {4, 24})

    def test_sem_chamados(self):
        dados = calcular_indicadores([], date(2026, 11, 1), date(2026, 11, 3))
        self.assertEqual(dados['total'], 0)
        self.assertEqual(dados['ranking_unidades'], [])
        self.assertEqual(dados['tempos'], [])
        self.assertEqual(len(dados['evolucao']['labels']), 3)
        self.assertEqual(sum(dados['evolucao']['abertos']), 0)


class IndicadoresIncluemOutrosTecnicosTest(unittest.TestCase):
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
        Chamado.query.delete()
        ChamadoTecnico.query.delete()
        Usuario.query.delete()
        Cliente.query.delete()
        db.session.commit()

    def _usuario(self, nome, email):
        user = Usuario(
            nome=nome,
            email=email,
            senha=generate_password_hash('x'),
            ativo=True,
            tipo='admin',
            is_master=True,
        )
        db.session.add(user)
        db.session.flush()
        return user

    def test_execucao_mostra_tecnico_atribuido_fora_da_fila(self):
        cli = Cliente(nome='Hospital', ativo=True, habilitado_chamados=True)
        db.session.add(cli)
        db.session.flush()
        eu = self._usuario('Informática São Geraldo', 'eu@example.com')
        joilson = self._usuario('Joilson Feliciano', 'joilson@example.com')
        abre = self._usuario('Christian Rodrigues', 'christian@example.com')
        db.session.add(ChamadoTecnico(
            nome='Mozart Marinho', email=eu.email, usuario_id=eu.id,
            funcao='tecnico', ativo=True,
        ))
        quando = datetime(2026, 11, 25, 11, 0)
        db.session.add(Chamado(
            numero_chamado='OS1', cliente_id=cli.id, tipo_servico='Manutenção',
            descricao='Meu', status='Atendido', tecnico_id=eu.id,
            atendente_id=eu.id, data_criacao=quando, data_conclusao=quando,
        ))
        db.session.add(Chamado(
            numero_chamado='OS2', cliente_id=cli.id, tipo_servico='Manutenção',
            descricao='Nutri', status='Concluído', tecnico_id=abre.id,
            atendente_id=joilson.id, atribuido_usuario_id=joilson.id,
            data_criacao=quando, data_conclusao=quando,
        ))
        db.session.commit()
        visiveis = {c.numero_chamado for c in _query_chamados_usuario(eu).all()}
        self.assertNotIn('OS2', visiveis)

        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = eu.id
        resp = client.get('/dashboard?ind_de=2026-11-25&ind_ate=2026-11-25')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        bloco = re.search(r'id="mdkIndMantenedor">(.*?)</script>', html)
        self.assertIsNotNone(bloco)
        dados = json.loads(bloco.group(1))
        nomes = [linha['nome'] for linha in dados['execucao']]
        self.assertIn('Joilson Feliciano', nomes)
        self.assertIn('Informática São Geraldo', nomes)


if __name__ == '__main__':
    unittest.main()
