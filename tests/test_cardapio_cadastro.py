#!/usr/bin/env python3
"""Cadastro de cardápio: texto livre, Salada, exclusão da dieta com cardápio."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutDieta, NutCardapio  # noqa: E402
from nutricao_service import excluir_dieta_e_cardapios  # noqa: E402


class CardapioCadastroTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_formulario_texto_livre_sem_amarelos(self):
        html = self.client.get('/nutricao/cardapios').get_data(as_text=True)
        self.assertIn('id="g-acompanhamento"', html)
        self.assertIn('id="g-prato_base"', html)
        self.assertIn('id="g-proteina_opcional"', html)
        self.assertIn('id="g-guarnicao"', html)
        self.assertIn('id="g-docinho_salada"', html)
        self.assertIn('>Salada</label>', html)
        self.assertNotIn('Docinho / Salada', html)
        self.assertIn('type="text"', html)
        self.assertNotIn('name="entrada_tipo"', html)
        self.assertNotIn('name="proteina_tipo"', html)
        self.assertNotIn('V.N.T.', html)
        self.assertNotIn('Organizar por', html)
        self.assertNotIn('id="f-vet"', html)
        self.assertNotIn('id="f-custo"', html)
        self.assertIn('id="p-bebida"', html)
        self.assertIn('id="l-principal"', html)
        self.assertIn('<input class="form-control" id="p-bebida" type="text"', html)
        self.assertIn('<input class="form-control" id="l-principal" type="text"', html)
        self.assertIn('excluirDietaECardapio', html)

    def test_excluir_dieta_apaga_cardapio_vinculado(self):
        dieta = NutDieta(nome='BRANDA TESTE EXCLUIR', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.flush()
        card = NutCardapio(
            tipo='grandes',
            dieta=dieta.nome,
            dieta_id=dieta.id,
            ativo=True,
        )
        card.set_itens({'acompanhamento': 'arroz', 'salada': 'alface'})
        db.session.add(card)
        db.session.commit()
        did, cid = dieta.id, card.id

        resp = self.client.delete(f'/nutricao/api/dietas/{did}')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        self.assertGreaterEqual(data.get('cardapios'), 1)

        db.session.expire_all()
        self.assertFalse(NutDieta.query.get(did).ativo)
        self.assertFalse(NutCardapio.query.get(cid).ativo)

    def test_helper_por_nome(self):
        dieta = NutDieta(nome='LIQUIDA TESTE', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.flush()
        card = NutCardapio(tipo='liquidas', dieta='LIQUIDA TESTE', dieta_id=None, ativo=True)
        db.session.add(card)
        db.session.commit()
        qtd = excluir_dieta_e_cardapios(dieta)
        db.session.commit()
        self.assertGreaterEqual(qtd, 1)
        self.assertFalse(NutCardapio.query.get(card.id).ativo)


if __name__ == '__main__':
    unittest.main()
