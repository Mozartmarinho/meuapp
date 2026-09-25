#!/usr/bin/env python3
"""Cadastro de cardápio: texto livre, Salada, exclusão da dieta com cardápio."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models_nutricao import NutDieta, NutCardapio  # noqa: E402
from models import db  # noqa: E402
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
        self.assertIn('id="abasHorario"', html)
        self.assertIn('trocarHorario(\'desjejum\')', html)
        self.assertIn('trocarHorario(\'almoco\')', html)
        self.assertIn('data-horario="merenda"', html)
        self.assertIn('data-horario="ceia"', html)
        self.assertNotIn('id="hr_desjejum"', html)
        self.assertNotIn('Grandes refeições', html)
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
        self.assertIn('btn-bolinha-mais', html)
        self.assertIn('id="itemExtraOverlay"', html)
        self.assertIn('data-campo="acompanhamento"', html)
        self.assertIn('data-campo="prato_base"', html)
        self.assertIn('data-campo="p-bebida"', html)
        self.assertIn('data-campo="p-prato1"', html)
        self.assertIn('data-campo="l-principal"', html)
        self.assertIn('data-campo="l-gelado"', html)
        self.assertIn('Cadastrar mais acompanhamento', html)
        self.assertIn('Cadastrar mais bebida', html)
        self.assertIn('Cadastrar mais principal', html)
        self.assertIn('/nutricao/api/cardapio-produtos', html)
        self.assertIn('abrirSugestoes', html)
        self.assertIn('filtrarNomesProdutos', html)
        self.assertIn("input: 'p-prato1', tipo: 'pequenas', grupo: 'PRATO'", html)
        self.assertIn("input: 'p-prato7', tipo: 'pequenas', grupo: 'PRATO'", html)
        self.assertIn("input: 'l-gelado', tipo: 'liquidas', grupo: 'GELADO'", html)

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
        self.assertIsNone(NutDieta.query.get(did))
        self.assertIsNone(NutCardapio.query.get(cid))

    def test_excluir_dieta_nao_volta_no_seed(self):
        from nutricao_service import seed_nutricao, dieta_foi_excluida  # noqa: E402
        seed_nutricao(force=True)
        dieta = NutDieta.query.filter(db.func.upper(NutDieta.nome) == 'BRANDA COM SAL').first()
        self.assertIsNotNone(dieta)
        did = dieta.id

        resp = self.client.delete(f'/nutricao/api/dietas/{did}')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(dieta_foi_excluida('BRANDA COM SAL'))

        seed_nutricao(force=True)
        db.session.expire_all()
        self.assertIsNone(
            NutDieta.query.filter(db.func.upper(NutDieta.nome) == 'BRANDA COM SAL').first()
        )

    def test_helper_por_nome(self):
        dieta = NutDieta(nome='LIQUIDA TESTE', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.flush()
        card = NutCardapio(tipo='liquidas', dieta='LIQUIDA TESTE', dieta_id=None, ativo=True)
        db.session.add(card)
        db.session.commit()
        did, cid = dieta.id, card.id
        qtd = excluir_dieta_e_cardapios(dieta)
        db.session.commit()
        self.assertGreaterEqual(qtd, 1)
        db.session.expire_all()
        self.assertIsNone(NutDieta.query.get(did))
        self.assertIsNone(NutCardapio.query.get(cid))

    def test_salva_extras_do_campo_e_lista_como_pratos(self):
        from nutricao_service import pratos_from_itens  # noqa: E402
        dieta = NutDieta(nome='BRANDA EXTRAS', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.commit()
        resp = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'grandes',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'hr_almoco': True,
            'itens': {
                'acompanhamento': 'ARROZ C/ SAL',
                'acompanhamento_extras': ['FEIJÃO', 'MACARRÃO'],
                'prato_base': 'BIFE ACEBOLADO',
                'prato_base_extras': ['FRANGO GRELHADO'],
                'modo_prato': 'selecao',
            },
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        itens = data['cardapio']['itens']
        self.assertEqual(itens['acompanhamento_extras'], ['FEIJÃO', 'MACARRÃO'])
        self.assertEqual(itens['prato_base_extras'], ['FRANGO GRELHADO'])
        pratos = pratos_from_itens(itens, 'grandes')
        self.assertEqual(pratos[:4], ['ARROZ C/ SAL', 'FEIJÃO', 'MACARRÃO', 'BIFE ACEBOLADO'])
        self.assertIn('FRANGO GRELHADO', pratos)
        self.assertNotIn('selecao', pratos)

    def test_salva_extras_pequenas_e_liquidas(self):
        from nutricao_service import pratos_from_itens  # noqa: E402
        dieta = NutDieta(nome='LIQUIDA EXTRAS', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.commit()

        resp_p = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'pequenas',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'hr_desjejum': True,
            'itens': {
                'bebida': 'CAFÉ',
                'bebida_extras': ['CHÁ'],
                'prato1': 'PÃO FRANCÊS',
                'prato1_extras': ['BROA'],
            },
        })
        self.assertEqual(resp_p.status_code, 200)
        itens_p = resp_p.get_json()['cardapio']['itens']
        self.assertEqual(itens_p['bebida_extras'], ['CHÁ'])
        self.assertEqual(itens_p['prato1_extras'], ['BROA'])
        pratos_p = pratos_from_itens(itens_p, 'pequenas')
        self.assertEqual(pratos_p[:4], ['CAFÉ', 'CHÁ', 'PÃO FRANCÊS', 'BROA'])

        resp_l = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'liquidas',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'hr_almoco': True,
            'itens': {
                'principal': 'SOPA CREME',
                'principal_extras': ['CALDO DE CARNE'],
                'gelado': 'GELATINA',
                'gelado_extras': ['PICOLÉ'],
            },
        })
        self.assertEqual(resp_l.status_code, 200)
        itens_l = resp_l.get_json()['cardapio']['itens']
        self.assertEqual(itens_l['principal_extras'], ['CALDO DE CARNE'])
        self.assertEqual(itens_l['gelado_extras'], ['PICOLÉ'])
        pratos_l = pratos_from_itens(itens_l, 'liquidas')
        self.assertIn('SOPA CREME', pratos_l)
        self.assertIn('CALDO DE CARNE', pratos_l)
        self.assertIn('PICOLÉ', pratos_l)

    def test_mais_do_cardapio_grava_produto_no_grupo_do_tema(self):
        from models_nutricao import NutGrupoProduto, NutProduto  # noqa: E402
        from nutricao_service import seed_nutricao  # noqa: E402
        seed_nutricao(force=True)

        resp = self.client.post('/nutricao/api/cardapio-produtos', json={
            'nome': 'FEIJÃO TUTU',
            'grupo': 'Acompanhamento',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['produto']['nome'], 'FEIJÃO TUTU')
        grupo_nome = (data['produto']['grupo'] or '').upper()
        self.assertIn(grupo_nome, {'ACOMPANHAMENTO', 'ACOMPANHAMENTOS'})

        grupo = NutGrupoProduto.query.filter(
            db.func.upper(NutGrupoProduto.nome).in_(['ACOMPANHAMENTO', 'ACOMPANHAMENTOS'])
        ).first()
        self.assertIsNotNone(grupo)
        prod = NutProduto.query.filter_by(id=data['id']).first()
        self.assertIsNotNone(prod)
        self.assertEqual(prod.grupo_id, grupo.id)
        self.assertEqual((prod.descricao or '').upper(), 'FEIJÃO TUTU')

        lista = self.client.get('/nutricao/api/cardapio-produtos?grupo=acompanhamento').get_json()
        nomes = [p['nome'].upper() for p in lista]
        self.assertIn('FEIJÃO TUTU', nomes)

        dup = self.client.post('/nutricao/api/cardapio-produtos', json={
            'nome': 'feijão tutu',
            'grupo': 'ACOMPANHAMENTO',
        })
        self.assertEqual(dup.status_code, 200)
        self.assertEqual(dup.get_json()['id'], data['id'])

    def test_lista_bebidas_no_campo_bebida(self):
        from nutricao_service import seed_nutricao  # noqa: E402
        seed_nutricao(force=True)
        lista = self.client.get('/nutricao/api/cardapio-produtos?grupo=BEBIDA').get_json()
        self.assertIsInstance(lista, list)
        self.assertGreater(len(lista), 0)
        nomes = ' '.join(p['nome'].upper() for p in lista)
        self.assertTrue('AGUA' in nomes or 'SUCO' in nomes or 'COCA' in nomes)

    def test_pratos_pequenas_usam_grupo_prato(self):
        from nutricao_service import seed_nutricao  # noqa: E402
        seed_nutricao(force=True)
        resp = self.client.post('/nutricao/api/cardapio-produtos', json={
            'nome': 'PÃO FRANCÊS',
            'grupo': 'PRATO',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        self.assertIn((data['produto']['grupo'] or '').upper(), {'PRATO', 'PRATOS'})
        lista = self.client.get('/nutricao/api/cardapio-produtos?grupo=PRATO').get_json()
        nomes = [p['nome'].upper() for p in lista]
        self.assertIn('PÃO FRANCÊS', nomes)
        por_numero = self.client.get('/nutricao/api/cardapio-produtos?grupo=PRATO%201').get_json()
        nomes_n = [p['nome'].upper() for p in por_numero]
        self.assertIn('PÃO FRANCÊS', nomes_n)


if __name__ == '__main__':
    unittest.main()
