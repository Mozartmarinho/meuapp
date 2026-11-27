#!/usr/bin/env python3
"""Busca no cadastro de paciente inclui quem já foi registrado, mesmo após alta."""
import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutPaciente  # noqa: E402
from routes_nutricao import (
    _busca_rapida_pacientes, _list_pacientes_db, _pacientes_somente_ativos,
)  # noqa: E402


class BuscaPacienteCadastroTest(unittest.TestCase):
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
        NutPaciente.query.delete()
        db.session.add(NutPaciente(
            nome='Yuri Andrade', prontuario='555', ativo=False,
            motivo_saida='Alta médica', data_saida=date(2026, 11, 10),
            cliente_id=1,
        ))
        db.session.add(NutPaciente(
            nome='Alessandra Silva', prontuario='777', ativo=True, cliente_id=1,
        ))
        db.session.commit()

    def test_termo_de_busca_inclui_inativos(self):
        self.assertFalse(_pacientes_somente_ativos('yuri'))
        self.assertTrue(_pacientes_somente_ativos(''))
        self.assertFalse(_pacientes_somente_ativos('', incluir_inativos=True))

    def test_lista_encontra_paciente_com_alta(self):
        nomes = [p['nome'] for p in _list_pacientes_db(False, q='yuri', limit=30)]
        self.assertEqual(nomes, ['Yuri Andrade'])
        so_ativos = [p['nome'] for p in _list_pacientes_db(True, q='yuri', limit=30)]
        self.assertEqual(so_ativos, [])

    def test_api_de_busca_devolve_cadastro_anterior(self):
        client = self.app.test_client()
        with patch('routes_nutricao.seed_nutricao'):
            resp = client.get('/nutricao/api/pacientes?q=yuri&limit=30')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual([p['nome'] for p in data['pacientes']], ['Yuri Andrade'])
        self.assertFalse(data['pacientes'][0]['ativo'])

    def test_busca_rapida_inclui_alta_e_ignora_excluido(self):
        db.session.add(NutPaciente(
            nome='YURI EXCLUIDO', prontuario='1', ativo=False,
            excluido=True, cliente_id=1,
        ))
        db.session.commit()
        nomes = [p['nome'] for p in _busca_rapida_pacientes('yuri', limit=30)]
        self.assertEqual(nomes, ['Yuri Andrade'])

    def test_busca_rapida_por_prefixo_de_nome_e_prontuario(self):
        db.session.add(NutPaciente(
            nome='MARIA ALICE SOUZA', prontuario='256918',
            admissao=date(2026, 3, 15), ativo=True, cliente_id=1,
        ))
        db.session.add(NutPaciente(
            nome='JOSE MARIA', prontuario='999', ativo=True, cliente_id=1,
        ))
        db.session.commit()
        por_nome = _busca_rapida_pacientes('maria alice', limit=30)
        self.assertEqual([p['nome'] for p in por_nome], ['MARIA ALICE SOUZA'])
        self.assertEqual(por_nome[0]['admissao'], '2026-03-15')
        por_pront = [p['nome'] for p in _busca_rapida_pacientes('2569', limit=30)]
        self.assertEqual(por_pront, ['MARIA ALICE SOUZA'])

    def test_busca_rapida_acha_sobrenome_sem_prefixo(self):
        db.session.add(NutPaciente(
            nome='MARIA ALICE SOUZA', prontuario='10', ativo=True, cliente_id=1,
        ))
        db.session.commit()
        nomes = [p['nome'] for p in _busca_rapida_pacientes('alice', limit=30)]
        self.assertEqual(nomes, ['MARIA ALICE SOUZA'])

    def test_api_rapida_devolve_admissao_sem_paginar(self):
        db.session.add(NutPaciente(
            nome='MARIA ALICE', prontuario='256918',
            admissao=date(2026, 3, 15), ativo=True, cliente_id=1,
        ))
        db.session.commit()
        client = self.app.test_client()
        with patch('routes_nutricao.seed_nutricao'):
            resp = client.get('/nutricao/api/pacientes?q=maria%20alice&limit=30&rapida=1')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertNotIn('total', data)
        self.assertEqual(data['pacientes'][0]['nome'], 'MARIA ALICE')
        self.assertEqual(data['pacientes'][0]['admissao'], '2026-03-15')


if __name__ == '__main__':
    unittest.main()
