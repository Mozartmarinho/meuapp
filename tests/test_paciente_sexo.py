#!/usr/bin/env python3
"""Sexo do paciente: masculino, feminino e outros."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from nutricao_service import normalizar_sexo, sexo_label, paciente_from_payload  # noqa: E402
from app import create_app  # noqa: E402
from models import db  # noqa: E402


class SexoPacienteTest(unittest.TestCase):
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

    def test_normaliza_nomes_e_siglas(self):
        self.assertEqual(normalizar_sexo('masculino'), 'M')
        self.assertEqual(normalizar_sexo('Feminino'), 'F')
        self.assertEqual(normalizar_sexo('outros'), 'O')
        self.assertEqual(normalizar_sexo('M'), 'M')
        self.assertEqual(normalizar_sexo('F'), 'F')
        self.assertEqual(normalizar_sexo('O'), 'O')
        self.assertIsNone(normalizar_sexo(''))
        self.assertIsNone(normalizar_sexo(None))

    def test_labels(self):
        self.assertEqual(sexo_label('M'), 'Masculino')
        self.assertEqual(sexo_label('feminino'), 'Feminino')
        self.assertEqual(sexo_label('O'), 'Outros')

    def test_payload_grava_outros(self):
        p = paciente_from_payload({'nome': 'Mariano', 'sexo': 'outros'})
        self.assertEqual(p.sexo, 'O')
        self.assertEqual(p.to_dict()['sexo_label'], 'Outros')

    def test_dashboard_tem_tres_opcoes(self):
        client = self.app.test_client()
        html = client.get('/nutricao').get_data(as_text=True)
        self.assertIn('id="modal-pac-sexo"', html)
        self.assertIn('>Masculino</option>', html)
        self.assertIn('>Feminino</option>', html)
        self.assertIn('>Outros</option>', html)
        self.assertIn('value="O"', html)


if __name__ == '__main__':
    unittest.main()
