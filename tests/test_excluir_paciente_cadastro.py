#!/usr/bin/env python3
"""Apagar paciente some do cadastro e do mapa de hoje, sem apagar o dia anterior."""
import os
import sys
import unittest
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutMapaRefeicao, NutPaciente, NutRefeicaoAcompanhante  # noqa: E402
from nutricao_service import excluir_paciente_cadastro  # noqa: E402
from routes_nutricao import _list_pacientes_db  # noqa: E402


class ExcluirPacienteCadastroTest(unittest.TestCase):
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
        NutRefeicaoAcompanhante.query.delete()
        NutMapaRefeicao.query.delete()
        NutPaciente.query.delete()
        db.session.commit()

    def test_apagar_some_da_lista_e_mantem_quem_teve_alta(self):
        hoje = date.today()
        ontem = hoje - timedelta(days=1)
        pac = NutPaciente(nome='João da Silva', prontuario='101', ativo=True, cliente_id=1)
        alta = NutPaciente(
            nome='Maria Alta', prontuario='202', ativo=False,
            motivo_saida='Alta médica', data_saida=ontem, cliente_id=1,
        )
        db.session.add_all([pac, alta])
        db.session.flush()
        ontem_linha = NutMapaRefeicao(
            data_refeicao=ontem, paciente_id=pac.id, nome=pac.nome,
            prontuario=pac.prontuario, leito='1', dieta='BRANDA', ativo=True,
            lancamento_grupo_id=None,
        )
        db.session.add(ontem_linha)
        db.session.flush()
        ontem_linha.lancamento_grupo_id = ontem_linha.id
        db.session.add(NutRefeicaoAcompanhante(
            nome_acompanhante='Mãe', paciente_id=pac.id, ativo=True, data_refeicao=hoje,
        ))
        db.session.commit()
        pid = pac.id
        grupo = ontem_linha.lancamento_grupo_id

        excluir_paciente_cadastro(pac, usuario='teste')
        db.session.commit()

        nomes = [p['nome'] for p in _list_pacientes_db(False, limit=30)]
        self.assertNotIn('João da Silva', nomes)
        self.assertIn('Maria Alta', nomes)
        self.assertTrue(NutPaciente.query.get(pid).excluido)

        passado = NutMapaRefeicao.query.filter_by(paciente_id=pid, data_refeicao=ontem).one()
        self.assertTrue(passado.ativo)
        self.assertFalse((passado.motivo_saida or '').strip())

        hoje_linha = NutMapaRefeicao.query.filter_by(lancamento_grupo_id=grupo, data_refeicao=hoje).one()
        self.assertFalse(hoje_linha.ativo)
        self.assertEqual(hoje_linha.motivo_saida, 'Exclusão cadastro')

        acomp = NutRefeicaoAcompanhante.query.filter_by(paciente_id=pid).one()
        self.assertFalse(acomp.ativo)

    def test_api_delete_apaga_do_cadastro(self):
        pac = NutPaciente(nome='Carlos Apagar', prontuario='303', ativo=True, cliente_id=1)
        db.session.add(pac)
        db.session.commit()
        client = self.app.test_client()
        resp = client.delete(f'/nutricao/api/pacientes/{pac.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])
        nomes = [p['nome'] for p in _list_pacientes_db(False, limit=30)]
        self.assertNotIn('Carlos Apagar', nomes)


if __name__ == '__main__':
    unittest.main()
