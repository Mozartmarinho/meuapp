#!/usr/bin/env python3
"""Vários lançamentos de dieta no mesmo paciente/leito, sem duplicar cadastro."""
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
    NutClinica, NutEnfermaria, NutLeito, NutPaciente, NutMapaRefeicao, NutDieta,
)
from nutricao_service import (  # noqa: E402
    montar_grade_leitos_mapa,
    leito_ocupado_no_mapa,
    mapa_from_paciente,
    criar_lancamento_dieta_desde_linha,
    garantir_grupo_lancamento,
    garantir_mapa_do_dia,
    normalizar_tipo_lancamento,
)


class MapaMultiDietaTest(unittest.TestCase):
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
        db.session.query(NutPaciente).delete()
        db.session.query(NutLeito).delete()
        db.session.query(NutDieta).delete()
        NutClinica.query.delete()
        NutEnfermaria.query.delete()
        db.session.commit()

        self.clinica = NutClinica(nome='3º CM + VASCULAR', ativo=True)
        self.enf = NutEnfermaria(nome='Enf A', ativo=True)
        db.session.add_all([self.clinica, self.enf])
        db.session.flush()
        self.clinica.enfermarias.append(self.enf)
        db.session.add(NutLeito(enfermaria_id=self.enf.id, numero=101, nome='101', ativo=True))
        db.session.add(NutLeito(enfermaria_id=self.enf.id, numero=102, nome='102', ativo=True))
        self.dieta_normal = NutDieta(nome='Dieta normal', categoria='basica', ativo=True)
        self.dieta_pastosa = NutDieta(nome='Dieta pastosa', categoria='basica', ativo=True)
        self.pac = NutPaciente(
            nome='João da Silva',
            prontuario='123456',
            diagnostico='Diabetes',
            admissao=date.today(),
            ativo=True,
        )
        db.session.add_all([self.dieta_normal, self.dieta_pastosa, self.pac])
        db.session.commit()

    def _inserir_principal(self, flags=None):
        flags = flags or {'fl_desjejum': True}
        linha = mapa_from_paciente(
            self.pac,
            date.today(),
            flags=flags,
            extras={
                'adm': self.pac.admissao,
                'leito': '101',
                'prontuario': self.pac.prontuario,
                'diagnostico': self.pac.diagnostico,
                'dieta': self.dieta_normal.nome,
                'dieta_id': self.dieta_normal.id,
                'clinica': self.clinica.nome,
                'enfermaria': self.enf.nome,
            },
            usuario='teste',
        )
        db.session.add(linha)
        db.session.flush()
        garantir_grupo_lancamento(linha)
        db.session.commit()
        return linha

    def test_normalizar_tipo(self):
        self.assertEqual(normalizar_tipo_lancamento('substituição'), 'substituicao')
        self.assertEqual(normalizar_tipo_lancamento('nova_dieta'), 'adicional')
        self.assertEqual(normalizar_tipo_lancamento(None), 'principal')

    def test_leito_permite_mesmo_paciente(self):
        self._inserir_principal()
        self.assertFalse(leito_ocupado_no_mapa(
            date.today(), self.clinica.nome, self.enf.nome, '101', paciente_id=self.pac.id,
        ))
        outro = NutPaciente(nome='Maria', prontuario='999', ativo=True)
        db.session.add(outro)
        db.session.commit()
        self.assertTrue(leito_ocupado_no_mapa(
            date.today(), self.clinica.nome, self.enf.nome, '101', paciente_id=outro.id,
        ))

    def test_grade_duas_linhas_mesmo_leito(self):
        src = self._inserir_principal()
        extra = criar_lancamento_dieta_desde_linha(
            src,
            flags={'fl_colacao': True},
            extras={'dieta': self.dieta_pastosa.nome, 'dieta_id': self.dieta_pastosa.id},
            usuario='teste',
            tipo_lancamento='substituicao',
        )
        db.session.add(extra)
        db.session.flush()
        garantir_grupo_lancamento(extra)
        db.session.commit()

        self.assertEqual(NutPaciente.query.count(), 1)
        self.assertEqual(
            NutMapaRefeicao.query.filter_by(paciente_id=self.pac.id, ativo=True).count(),
            2,
        )
        self.assertTrue(src.ativo)
        self.assertEqual(extra.tipo_lancamento, 'substituicao')
        self.assertEqual(extra.nome, src.nome)
        self.assertEqual(extra.prontuario, src.prontuario)
        self.assertEqual(extra.leito, src.leito)
        self.assertNotEqual(extra.id, src.id)
        self.assertNotEqual(extra.lancamento_grupo_id, src.lancamento_grupo_id)

        grade = montar_grade_leitos_mapa(date.today(), self.clinica.nome)
        ocupados = [s for s in grade if not s['vago']]
        self.assertEqual(len(ocupados), 2)
        self.assertEqual({s['linha']['dieta'] for s in ocupados}, {'Dieta normal', 'Dieta pastosa'})
        self.assertEqual({s['leito_valor'] for s in ocupados} | {s['leito'] for s in ocupados}, {'101'})
        tipos = [s['linha']['tipo_lancamento'] for s in ocupados]
        self.assertEqual(tipos[0], 'principal')
        self.assertEqual(tipos[1], 'substituicao')

    def test_persistencia_copia_ambos_lancamentos(self):
        src = self._inserir_principal()
        extra = criar_lancamento_dieta_desde_linha(
            src,
            flags={'fl_almoco': True},
            extras={'dieta': self.dieta_pastosa.nome},
            usuario='teste',
            tipo_lancamento='adicional',
        )
        db.session.add(extra)
        db.session.flush()
        garantir_grupo_lancamento(extra)
        db.session.commit()

        amanha = date.today() + timedelta(days=1)
        garantir_mapa_do_dia(amanha)
        db.session.commit()
        linhas = NutMapaRefeicao.query.filter_by(
            data_refeicao=amanha, paciente_id=self.pac.id, ativo=True,
        ).all()
        self.assertEqual(len(linhas), 2)
        self.assertEqual({(r.dieta, r.tipo_lancamento) for r in linhas}, {
            ('Dieta normal', 'principal'),
            ('Dieta pastosa', 'adicional'),
        })
        self.assertEqual(NutPaciente.query.count(), 1)


if __name__ == '__main__':
    unittest.main()
