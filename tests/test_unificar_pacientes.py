#!/usr/bin/env python3
"""Unificar paciente leva o histórico ao principal e esconde os demais."""
import os
import sys
import unittest
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import (  # noqa: E402
    NutAvaliacaoNutricional, NutEvolucaoPaciente, NutMapaRefeicao,
    NutPaciente, NutRefeicaoAcompanhante,
)
from nutricao_clinico import contexto_paciente  # noqa: E402
from nutricao_service import (  # noqa: E402
    aplicar_unificacao_duplicados, chave_nome_unificacao,
    escolher_principal_unificacao, listar_grupos_duplicados_nascimento,
    unificar_pacientes,
)
from routes_nutricao import _list_pacientes_db  # noqa: E402


class _Pac:
    def __init__(self, pid, ativo=True, excluido=False, prontuario=None):
        self.id = pid
        self.ativo = ativo
        self.excluido = excluido
        self.prontuario = prontuario


class UnificarPacienteTest(unittest.TestCase):
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
        NutEvolucaoPaciente.query.delete()
        NutAvaliacaoNutricional.query.delete()
        NutRefeicaoAcompanhante.query.delete()
        NutMapaRefeicao.query.delete()
        NutPaciente.query.delete()
        db.session.commit()

    def test_chave_nome_ignora_caixa_acento_e_espaco(self):
        self.assertEqual(
            chave_nome_unificacao('  José   da SILVA '),
            chave_nome_unificacao('jose da silva'),
        )
        self.assertNotEqual(chave_nome_unificacao('Ana'), chave_nome_unificacao('Ana Maria'))

    def test_escolha_do_principal(self):
        internado = _Pac(8, ativo=True, prontuario='')
        alta = _Pac(1, ativo=False, prontuario='999')
        self.assertEqual(
            escolher_principal_unificacao([alta, internado], {1: 20, 8: 0}).id,
            8,
        )
        com_prontuario = _Pac(5, prontuario='10')
        sem = _Pac(2, prontuario='  ')
        self.assertEqual(
            escolher_principal_unificacao([sem, com_prontuario], {2: 9, 5: 1}).id,
            5,
        )
        a = _Pac(4, prontuario='1')
        b = _Pac(3, prontuario='2')
        self.assertEqual(escolher_principal_unificacao([a, b], {4: 1, 3: 4}).id, 3)
        self.assertEqual(escolher_principal_unificacao([a, b], {4: 2, 3: 2}).id, 3)

    def test_unificar_leva_dados_e_esconde_os_outros(self):
        hoje = date.today()
        ontem = hoje - timedelta(days=1)
        principal = NutPaciente(
            nome='José da Silva', prontuario=None, nascimento=date(1980, 5, 1),
            diagnostico='Diabetes', ativo=True, cliente_id=1,
        )
        outro = NutPaciente(
            nome='jose  da silva', prontuario='440', nascimento=date(1980, 5, 1),
            diagnostico='Hipertensão', clinica='CTI', enfermaria='A', leito='12',
            dieta='BRANDA', ativo=False, data_saida=ontem, cliente_id=1,
        )
        db.session.add_all([principal, outro])
        db.session.flush()
        linha = NutMapaRefeicao(
            data_refeicao=ontem, paciente_id=outro.id, nome=outro.nome,
            prontuario=outro.prontuario, leito='12', dieta='BRANDA', ativo=True,
        )
        db.session.add(linha)
        db.session.add(NutRefeicaoAcompanhante(
            nome_acompanhante='Mãe', paciente_id=outro.id, ativo=True, data_refeicao=hoje,
        ))
        db.session.add(NutAvaliacaoNutricional(
            paciente_id=outro.id, data_avaliacao=ontem, peso_atual=70,
        ))
        db.session.add(NutEvolucaoPaciente(
            paciente_id=outro.id, data_registro=ontem, tipo='oral', conduta='Manter',
        ))
        db.session.commit()

        unificar_pacientes(principal, [outro], usuario='teste')
        db.session.commit()

        self.assertEqual(principal.prontuario, '440')
        self.assertIn('Diabetes', principal.diagnostico)
        self.assertIn('Hipertensão', principal.diagnostico)
        self.assertFalse(outro.ativo)
        self.assertTrue(outro.excluido)
        self.assertEqual(outro.unificado_em_id, principal.id)
        self.assertEqual(outro.motivo_saida, 'Unificação')

        nomes = [p['nome'] for p in _list_pacientes_db(False, q='silva', limit=30)]
        self.assertIn('José da Silva', nomes)
        self.assertNotIn('jose  da silva', nomes)

        linha = NutMapaRefeicao.query.filter_by(id=linha.id).one()
        self.assertEqual(linha.paciente_id, principal.id)
        self.assertEqual(linha.nome, principal.nome)
        self.assertEqual(linha.prontuario, '440')
        self.assertEqual(
            NutRefeicaoAcompanhante.query.filter_by(paciente_id=principal.id).count(), 1,
        )
        self.assertEqual(
            NutAvaliacaoNutricional.query.filter_by(paciente_id=principal.id).count(), 1,
        )
        self.assertEqual(
            NutEvolucaoPaciente.query.filter_by(paciente_id=principal.id).count(), 1,
        )
        self.assertEqual(NutMapaRefeicao.query.filter_by(paciente_id=outro.id).count(), 0)
        ctx = contexto_paciente(paciente_id=outro.id)
        self.assertEqual(ctx['paciente_id'], principal.id)

    def test_grupos_so_com_mesmo_nascimento_e_hospital(self):
        nasc = date(1975, 1, 2)
        db.session.add_all([
            NutPaciente(nome='José da Silva', nascimento=nasc, ativo=True, cliente_id=1, prontuario='1'),
            NutPaciente(nome='jose  da silva', nascimento=nasc, ativo=False, cliente_id=1),
            NutPaciente(nome='José da Silva', nascimento=date(1975, 1, 3), ativo=True, cliente_id=1),
            NutPaciente(nome='José da Silva', nascimento=nasc, ativo=True, cliente_id=2),
            NutPaciente(nome='Maria Sem Data', nascimento=None, ativo=True, cliente_id=1),
            NutPaciente(nome='Maria Sem Data', nascimento=None, ativo=True, cliente_id=1),
            NutPaciente(
                nome='José da Silva', nascimento=nasc, ativo=False, excluido=True, cliente_id=1,
            ),
        ])
        db.session.commit()
        grupos = listar_grupos_duplicados_nascimento()
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]['cliente_id'], 1)
        self.assertEqual(len(grupos[0]['outros']), 1)
        self.assertEqual(grupos[0]['principal'].prontuario, '1')

        resumo = aplicar_unificacao_duplicados()
        db.session.commit()
        self.assertEqual(resumo, {'grupos': 1, 'desativados': 1})
        visiveis = [p['nome'] for p in _list_pacientes_db(False, q='José', limit=30)]
        self.assertEqual(visiveis.count('José da Silva') + visiveis.count('jose  da silva'), 3)

    def test_api_unifica(self):
        a = NutPaciente(nome='Ana Costa', nascimento=date(1990, 2, 2), ativo=True, cliente_id=1)
        b = NutPaciente(nome='Ana Costa', nascimento=date(1990, 2, 2), ativo=True, cliente_id=1, prontuario='77')
        db.session.add_all([a, b])
        db.session.commit()
        client = self.app.test_client()
        pagina = client.get('/nutricao/unificar-pacientes')
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('Unificar paciente', pagina.get_data(as_text=True))
        resp = client.post('/nutricao/api/unificar-pacientes', json={
            'principal_id': a.id,
            'ids': [a.id, b.id],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])
        self.assertTrue(NutPaciente.query.get(b.id).excluido)
        self.assertEqual(NutPaciente.query.get(a.id).prontuario, '77')


if __name__ == '__main__':
    unittest.main()
