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

    def test_cadastro_aceita_dia_31_independente_do_mes(self):
        html = self.client.get('/nutricao/cardapios').get_data(as_text=True)
        self.assertIn('const DIAS_CADASTRO_CARDAPIO = 31', html)
        self.assertIn('input.max = DIAS_CADASTRO_CARDAPIO', html)
        self.assertNotIn('if (n > max) n = max', html)
        resp = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'pequenas',
            'dieta': 'DIA 31 TESTE',
            'hr_desjejum': True,
            'dia_mes': 31,
            'itens': {'bebida': 'CAFÉ'},
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['cardapio']['dia_mes'], 31)
        resp_alto = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'pequenas',
            'dieta': 'DIA 31 TESTE',
            'hr_desjejum': True,
            'dia_mes': 40,
            'itens': {'bebida': 'LEITE'},
        })
        self.assertEqual(resp_alto.get_json()['cardapio']['dia_mes'], 31)

    def test_formulario_texto_livre_sem_amarelos(self):
        html = self.client.get('/nutricao/cardapios').get_data(as_text=True)
        self.assertIn('oninput="aoMudarDiaMes()"', html)
        self.assertIn('aoMudarDiaSemana()', html)
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
        self.assertIn('>Item 1</label>', html)
        self.assertIn('>Item 10</label>', html)
        self.assertIn('id="p-prato8"', html)
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
        self.assertIn('Cadastrar mais item 1', html)
        self.assertIn('Cadastrar mais bebida', html)
        self.assertIn('Cadastrar mais principal', html)
        self.assertIn('/nutricao/api/cardapio-produtos', html)
        self.assertIn('abrirSugestoes', html)
        self.assertIn('filtrarNomesProdutos', html)
        self.assertIn("input: 'p-prato1', tipo: 'pequenas', grupo: 'PRATO'", html)
        self.assertIn("input: 'p-prato7', tipo: 'pequenas', grupo: 'PRATO'", html)
        self.assertIn("input: 'p-prato8', tipo: 'pequenas', grupo: 'PRATO'", html)
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
        self.assertEqual(data['cardapio']['item_1'], 'ARROZ C/ SAL')
        self.assertEqual(data['cardapio']['item_2'], 'BIFE ACEBOLADO')
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
        self.assertEqual(resp_p.get_json()['cardapio']['item_1'], 'CAFÉ')
        self.assertEqual(resp_p.get_json()['cardapio']['item_2'], 'PÃO FRANCÊS')
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

    def test_itens_do_mesmo_horario_ficam_em_colunas_diferentes(self):
        dieta = NutDieta(nome='BRANDA COLUNAS', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.commit()
        base = {
            'tipo': 'pequenas',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'hr_desjejum': True,
            'dia_mes': 25,
        }
        r1 = self.client.post('/nutricao/api/cardapios', json=dict(base, itens={
            'bebida': 'MATE QUENTE',
        }, item_1='MATE QUENTE', item_2=''))
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post('/nutricao/api/cardapios', json=dict(base, itens={
            'bebida': 'MATE QUENTE',
            'prato1': 'AÇÚCAR IND',
        }, item_1='MATE QUENTE', item_2='AÇÚCAR IND', item_3='PÃO'))
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.get_json()['id'], r2.get_json()['id'])
        card = r2.get_json()['cardapio']
        self.assertEqual(card['item_1'], 'MATE QUENTE')
        self.assertEqual(card['item_2'], 'AÇÚCAR IND')
        self.assertEqual(card['item_3'], 'PÃO')
        row = NutCardapio.query.get(card['id'])
        self.assertEqual(row.item_1, 'MATE QUENTE')
        self.assertEqual(row.item_2, 'AÇÚCAR IND')
        self.assertEqual(row.item_3, 'PÃO')
        ativos = NutCardapio.query.filter_by(dieta_id=dieta.id, ativo=True, dia_mes=25).count()
        self.assertEqual(ativos, 1)

    def test_cada_refeicao_salva_cardapio_proprio(self):
        dieta = NutDieta(nome='BRANDA HORARIOS', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.commit()
        horas = (
            ('desjejum', 'pequenas', 'CAFÉ'),
            ('colacao', 'pequenas', 'FRUTA'),
            ('almoco', 'grandes', 'ARROZ'),
            ('merenda', 'pequenas', 'BOLO'),
            ('jantar', 'grandes', 'SOPA'),
            ('ceia', 'pequenas', 'CHÁ'),
        )
        ids = {}
        for hora, tipo, item in horas:
            flags = {f'hr_{nome}': nome == hora for nome, _t, _i in horas}
            resp = self.client.post('/nutricao/api/cardapios', json=dict(flags, tipo=tipo, dieta_id=dieta.id, dieta=dieta.nome, dia_mes=28, item_1=item, itens={'bebida': item, 'acompanhamento': item}))
            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
            ids[hora] = resp.get_json()['id']
        self.assertEqual(len(set(ids.values())), 6)
        for hora, _tipo, item in horas:
            row = NutCardapio.query.get(ids[hora])
            self.assertEqual(row.item_1, item)
            self.assertTrue(getattr(row, f'hr_{hora}'))
            for outra, _t, _i in horas:
                if outra != hora:
                    self.assertFalse(getattr(row, f'hr_{outra}'))
        de_novo = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'pequenas',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'dia_mes': 28,
            'hr_desjejum': True,
            'item_1': 'LEITE',
            'itens': {'bebida': 'LEITE'},
        })
        self.assertEqual(de_novo.get_json()['id'], ids['desjejum'])
        self.assertEqual(NutCardapio.query.get(ids['colacao']).item_1, 'FRUTA')
        self.assertEqual(NutCardapio.query.get(ids['desjejum']).item_1, 'LEITE')

    def test_item_de_refeicao_pequena_nao_apaga_os_outros(self):
        dieta = NutDieta(nome='BRANDA ITENS', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.commit()
        base = {
            'tipo': 'pequenas',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'dia_mes': 28,
            'hr_desjejum': True,
        }
        r1 = self.client.post('/nutricao/api/cardapios', json=dict(
            base, somente_item=1, item_1='CAFÉ',
        ))
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post('/nutricao/api/cardapios', json=dict(
            base, somente_item=2, item_2='PÃO', item_1='',
        ))
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.get_json()['id'], r2.get_json()['id'])
        row = NutCardapio.query.get(r2.get_json()['id'])
        self.assertEqual(row.item_1, 'CAFÉ')
        self.assertEqual(row.item_2, 'PÃO')
        colacao = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'pequenas',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'dia_mes': 28,
            'hr_colacao': True,
            'somente_item': 1,
            'item_1': 'FRUTA',
        })
        self.assertNotEqual(colacao.get_json()['id'], row.id)
        self.assertEqual(NutCardapio.query.get(row.id).item_1, 'CAFÉ')
        self.assertEqual(NutCardapio.query.get(colacao.get_json()['id']).item_1, 'FRUTA')

    def test_item_de_almoco_nao_apaga_jantar_nem_os_outros(self):
        dieta = NutDieta(nome='BRANDA GRANDES', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.commit()
        base = {
            'tipo': 'grandes',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'dia_mes': 28,
            'hr_almoco': True,
        }
        r1 = self.client.post('/nutricao/api/cardapios', json=dict(
            base, somente_item=1, item_1='ARROZ',
        ))
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post('/nutricao/api/cardapios', json=dict(
            base, somente_item=2, item_2='FEIJÃO', item_1='',
        ))
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.get_json()['id'], r2.get_json()['id'])
        row = NutCardapio.query.get(r2.get_json()['id'])
        self.assertEqual(row.item_1, 'ARROZ')
        self.assertEqual(row.item_2, 'FEIJÃO')
        self.assertTrue(row.hr_almoco)
        self.assertFalse(row.hr_jantar)
        jantar = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'grandes',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'dia_mes': 28,
            'hr_jantar': True,
            'somente_item': 1,
            'item_1': 'SOPA',
        })
        self.assertNotEqual(jantar.get_json()['id'], row.id)
        self.assertEqual(NutCardapio.query.get(row.id).item_1, 'ARROZ')
        self.assertEqual(NutCardapio.query.get(row.id).item_2, 'FEIJÃO')
        outro = NutCardapio.query.get(jantar.get_json()['id'])
        self.assertEqual(outro.item_1, 'SOPA')
        self.assertIsNone(outro.item_2)
        self.assertTrue(outro.hr_jantar)
        self.assertFalse(outro.hr_almoco)

    def test_salva_cardapio_quando_dieta_id_nao_existe(self):
        resp = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'pequenas',
            'dieta_id': 99999,
            'dieta': 'BRANDA SALVA',
            'hr_desjejum': True,
            'dia_mes': 25,
            'itens': {'bebida': 'CAFÉ', 'prato1': 'PÃO'},
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        dieta_id = data['cardapio']['dieta_id']
        self.assertTrue(dieta_id)
        self.assertEqual(data['cardapio']['item_1'], 'CAFÉ')
        row = NutCardapio.query.get(data['cardapio']['id'])
        self.assertEqual(row.dieta_id, dieta_id)
        self.assertEqual(row.item_1, 'CAFÉ')
        dieta = NutDieta.query.get(dieta_id)
        self.assertEqual(dieta.nome, 'BRANDA SALVA')
        lista = self.client.get(f'/nutricao/api/cardapios?dieta_id={dieta_id}').get_json()
        self.assertTrue(any(c['id'] == row.id and c['itens']['bebida'] == 'CAFÉ' for c in lista))

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


    def test_opcoes_de_adicao_respeitam_refeicao_e_dieta(self):
        from datetime import date
        from models_nutricao import NutMapaRefeicao  # noqa: E402
        from nutricao_service import invalidar_cache_cardapios  # noqa: E402

        dieta = NutDieta(nome='DI-PASTOSA TESTE ABAS', categoria='basica', ativo=True)
        db.session.add(dieta)
        db.session.commit()
        dia = date.today().day
        r_desj = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'pequenas',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'hr_desjejum': True,
            'dia_mes': dia,
            'itens': {
                'bebida': 'CAFE DA MANHA ABA',
                'prato1': 'PAO DO DIA ABA',
                'bebida_extras': ['LEITE QUENTE ABA'],
            },
        })
        self.assertEqual(r_desj.status_code, 200, r_desj.get_data(as_text=True))
        r_alm = self.client.post('/nutricao/api/cardapios', json={
            'tipo': 'grandes',
            'dieta_id': dieta.id,
            'dieta': dieta.nome,
            'hr_almoco': True,
            'dia_mes': dia,
            'itens': {
                'acompanhamento': 'ARROZ PAPA ABA',
                'prato_base': 'ISCA DE PEIXE ABA',
            },
        })
        self.assertEqual(r_alm.status_code, 200, r_alm.get_data(as_text=True))
        bebida = self.client.post('/nutricao/api/cardapio-produtos', json={
            'nome': 'SUCO LARANJA SETOR ABA',
            'grupo': 'BEBIDA',
        })
        self.assertEqual(bebida.status_code, 200, bebida.get_data(as_text=True))
        acomp = self.client.post('/nutricao/api/cardapio-produtos', json={
            'nome': 'FEIJAO SETOR ABA',
            'grupo': 'ACOMPANHAMENTO',
        })
        self.assertEqual(acomp.status_code, 200, acomp.get_data(as_text=True))
        mapa = NutMapaRefeicao(
            data_refeicao=date.today(),
            nome='YURI TESTE ABAS',
            dieta=dieta.nome,
            dieta_id=dieta.id,
            ativo=True,
        )
        db.session.add(mapa)
        db.session.commit()
        invalidar_cache_cardapios()

        def nomes(payload):
            out = []
            for setor in payload.get('setores') or []:
                out.extend((item.get('nome') or '').upper() for item in setor.get('itens') or [])
            return out

        desj = self.client.get(f'/nutricao/api/mapa/{mapa.id}/substituicoes/opcoes?meal=desjejum')
        alm = self.client.get(f'/nutricao/api/mapa/{mapa.id}/substituicoes/opcoes?meal=almoco')
        self.assertEqual(desj.status_code, 200, desj.get_data(as_text=True))
        self.assertEqual(alm.status_code, 200, alm.get_data(as_text=True))
        nomes_desj = nomes(desj.get_json())
        nomes_alm = nomes(alm.get_json())
        self.assertIn('CAFE DA MANHA ABA', nomes_desj)
        self.assertIn('PAO DO DIA ABA', nomes_desj)
        self.assertIn('LEITE QUENTE ABA', nomes_desj)
        self.assertIn('SUCO LARANJA SETOR ABA', nomes_desj)
        self.assertNotIn('ARROZ PAPA ABA', nomes_desj)
        self.assertNotIn('ISCA DE PEIXE ABA', nomes_desj)
        self.assertNotIn('FEIJAO SETOR ABA', nomes_desj)
        self.assertIn('ARROZ PAPA ABA', nomes_alm)
        self.assertIn('ISCA DE PEIXE ABA', nomes_alm)
        self.assertIn('FEIJAO SETOR ABA', nomes_alm)
        self.assertNotIn('CAFE DA MANHA ABA', nomes_alm)
        self.assertNotIn('PAO DO DIA ABA', nomes_alm)
        self.assertNotIn('SUCO LARANJA SETOR ABA', nomes_alm)
        self.assertEqual(desj.get_json()['meal'], 'desjejum')
        self.assertEqual(alm.get_json()['meal'], 'almoco')

        pagina = self.client.get('/nutricao').get_data(as_text=True)
        self.assertIn('substAbrirAdicionar()', pagina)
        self.assertIn('id="substAddOverlay"', pagina)
        self.assertIn('Remover substituição', pagina)
        self.assertIn('Substituir item', pagina)
        self.assertIn('filtrado-fora', pagina)

        invalido = self.client.get(f'/nutricao/api/mapa/{mapa.id}/substituicoes/opcoes?meal=liquidas')
        self.assertEqual(invalido.status_code, 400)


if __name__ == '__main__':
    unittest.main()
