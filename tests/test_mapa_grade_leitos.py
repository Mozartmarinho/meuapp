#!/usr/bin/env python3
"""Grade do mapa: uma linha por leito cadastrado, matching com número inteiro."""
import os
import sys
import unittest
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutClinica, NutEnfermaria, NutLeito, NutMapaRefeicao  # noqa: E402
from nutricao_service import _chaves_ocupacao_leito, montar_grade_leitos_mapa  # noqa: E402


class GradeLeitosMapaTest(unittest.TestCase):
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
        db.session.query(NutLeito).delete()
        NutClinica.query.delete()
        NutEnfermaria.query.delete()
        db.session.commit()

        self.clinica = NutClinica(nome='3º CM + VASCULAR', ativo=True)
        self.enf_a = NutEnfermaria(nome='Enf A', ativo=True)
        self.enf_b = NutEnfermaria(nome='Enf B', ativo=True)
        db.session.add_all([self.clinica, self.enf_a, self.enf_b])
        db.session.flush()
        self.clinica.enfermarias.extend([self.enf_a, self.enf_b])
        for enf in (self.enf_a, self.enf_b):
            for n in (1, 2):
                db.session.add(NutLeito(
                    enfermaria_id=enf.id,
                    numero=n,
                    nome=str(n).zfill(2),
                    ativo=True,
                ))
        db.session.commit()

    def test_chaves_aceitam_numero_inteiro(self):
        self.assertIn('1', _chaves_ocupacao_leito(1))
        self.assertIn('01', _chaves_ocupacao_leito(1))
        self.assertTrue(_chaves_ocupacao_leito(1) & _chaves_ocupacao_leito('01'))
        self.assertEqual(_chaves_ocupacao_leito(None), set())

    def test_grade_tem_uma_linha_por_leito(self):
        db.session.add(NutMapaRefeicao(
            data_refeicao=date.today(),
            nome='Paciente Ocupado',
            clinica=self.clinica.nome,
            enfermaria='Enf A',
            leito='01',
            ativo=True,
        ))
        db.session.commit()

        grade = montar_grade_leitos_mapa(date.today(), self.clinica.nome)
        self.assertEqual(len(grade), 4)
        self.assertEqual({s['enfermaria'] for s in grade}, {'Enf A', 'Enf B'})
        ocupados = [s for s in grade if not s['vago']]
        vagos = [s for s in grade if s['vago']]
        self.assertEqual(len(ocupados), 1)
        self.assertEqual(ocupados[0]['linha']['nome'], 'Paciente Ocupado')
        self.assertEqual(len(vagos), 3)

    def test_sem_clinica_nao_filtra_vazio_no_servico(self):
        grade = montar_grade_leitos_mapa(date.today(), '__todas__')
        self.assertEqual(len(grade), 4)


if __name__ == '__main__':
    unittest.main()
