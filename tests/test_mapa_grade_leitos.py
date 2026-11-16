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
from models_nutricao import NutClinica, NutGrupoClinica, NutEnfermaria, NutLeito, NutMapaRefeicao  # noqa: E402
from nutricao_service import (  # noqa: E402
    _chaves_ocupacao_leito,
    montar_grade_leitos_mapa,
    listar_linhas_mapa_uma,
)  # noqa: E402


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
        NutGrupoClinica.query.delete()
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

    def test_grade_filtra_por_nomes_do_grupo(self):
        outra = NutClinica(nome='ONCO', ativo=True)
        db.session.add(outra)
        db.session.flush()
        outra.enfermarias.append(self.enf_b)
        db.session.commit()

        grade_grupo = montar_grade_leitos_mapa(
            date.today(), clinica_nomes=[self.clinica.nome]
        )
        self.assertTrue(grade_grupo)
        self.assertTrue(all(s['clinica'] == self.clinica.nome for s in grade_grupo))
        self.assertEqual(montar_grade_leitos_mapa(date.today(), clinica_nomes=[]), [])

    def test_uma_lista_qualquer_clinica_so_com_campo_preenchido(self):
        hoje = date.today()
        db.session.add_all([
            NutMapaRefeicao(
                data_refeicao=hoje, nome='Com Enteral', clinica='OUTRA CLINICA',
                enfermaria='Sala 9', leito='99', enteral='Dieta 1.5', ativo=True,
            ),
            NutMapaRefeicao(
                data_refeicao=hoje, nome='Sem Uma', clinica=self.clinica.nome,
                enfermaria='Enf A', leito='01', ativo=True,
            ),
            NutMapaRefeicao(
                data_refeicao=hoje, nome='So Espaco', clinica='Z', extras='   ', ativo=True,
            ),
            NutMapaRefeicao(
                data_refeicao=hoje, nome='Inativo', suplementos='modulo', ativo=False,
            ),
        ])
        db.session.commit()
        nomes = [linha['nome'] for linha in listar_linhas_mapa_uma(hoje)]
        self.assertEqual(nomes, ['Com Enteral'])

    def test_cardapio_da_refeicao_sai_do_indice(self):
        from models_nutricao import NutCardapio
        from nutricao_service import find_cardapio_for_meal, invalidar_cache_cardapios
        branda = NutCardapio(tipo='grandes', dieta='BRANDA COM SAL', hr_desjejum=True, ativo=True, dia_mes=1)
        branda.set_itens({'pao': 'PAO CARECA'})
        outra = NutCardapio(tipo='grandes', dieta='LIQUIDA', hr_desjejum=True, ativo=True, dia_mes=1)
        outra.set_itens({'suco': 'SUCO'})
        db.session.add_all([branda, outra])
        db.session.commit()
        invalidar_cache_cardapios()
        hit = find_cardapio_for_meal('BRANDA COM SAL', 'desjejum', date.today())
        self.assertIsNotNone(hit)
        self.assertEqual(hit.dieta, 'BRANDA COM SAL')
        self.assertIn('PAO CARECA', hit.pratos)
        de_novo = find_cardapio_for_meal('BRANDA COM SAL', 'desjejum', date.today())
        self.assertEqual(de_novo.id, hit.id)


if __name__ == '__main__':
    unittest.main()
