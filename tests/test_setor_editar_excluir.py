#!/usr/bin/env python3
"""Cadastro de setores: ações Editar e Excluir em todos os modais de chamados."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import ChamadoSetor, ChamadoTecnico, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402

TEMPLATES = (
    'templates/tecnicos.html',
    'templates/equipamentos.html',
    'templates/cameras.html',
    'templates/portoes.html',
    'templates/telefones_ramais.html',
)


class SetorAcoesTemplateTest(unittest.TestCase):
    def test_todos_os_cadastros_tem_editar_e_excluir(self):
        for rel in TEMPLATES:
            path = os.path.join(ROOT, rel)
            with open(path, encoding='utf-8') as fh:
                html = fh.read()
            self.assertIn('ChamadoSetorCadastro.editar', html, rel)
            self.assertIn('ChamadoSetorCadastro.excluir', html, rel)
            self.assertIn('> Editar', html, rel)
            self.assertIn('> Excluir', html, rel)
            self.assertNotIn('Alternar', html, rel)
            self.assertIn('chamado-setores.js', html, rel)


class SetorEditarExcluirApiTest(unittest.TestCase):
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
        ChamadoTecnico.query.delete()
        ChamadoSetor.query.delete()
        Usuario.query.delete()
        db.session.commit()
        self.user = Usuario(
            nome='Mozart Marinho',
            email='mozart@example.com',
            senha=generate_password_hash('x'),
            is_master=True,
            perm_chamados=True,
            ativo=True,
        )
        db.session.add(self.user)
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['user_name'] = self.user.nome

    def test_editar_renomeia_setor(self):
        s = ChamadoSetor(nome='Informática', ativo=True)
        db.session.add(s)
        db.session.commit()
        resp = self.client.post(f'/chamados/setores/{s.id}/editar', data={'nome': 'TI Hospital'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['nome'], 'TI Hospital')
        self.assertEqual(ChamadoSetor.query.get(s.id).nome, 'TI Hospital')

    def test_excluir_setor_livre(self):
        s = ChamadoSetor(nome='Obra', ativo=True)
        db.session.add(s)
        db.session.commit()
        sid = s.id
        resp = self.client.post(f'/chamados/setores/{sid}/excluir')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])
        self.assertIsNone(ChamadoSetor.query.get(sid))

    def test_nao_exclui_setor_com_tecnico(self):
        s = ChamadoSetor(nome='Elétrica', ativo=True)
        db.session.add(s)
        db.session.flush()
        db.session.add(ChamadoTecnico(nome='João', setor_id=s.id, ativo=True))
        db.session.commit()
        resp = self.client.post(f'/chamados/setores/{s.id}/excluir')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['ok'])
        self.assertIn('técnicos', data['error'])
        self.assertIsNotNone(ChamadoSetor.query.get(s.id))


if __name__ == '__main__':
    unittest.main()
