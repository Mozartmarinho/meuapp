#!/usr/bin/env python3
"""Catálogo e texto do cadastro de extras, suplementos, enteral e fórmulas."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models_nutricao import NutDieta, NutPratoLiquido, NutUmaItem, NutViaAdministracao  # noqa: E402
from nutricao_seed_uma import itens_uma_seed  # noqa: E402
from nutricao_service import _linha_legivel_uma, seed_nutricao  # noqa: E402


class UmaCatalogoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        seed_nutricao()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_nomes_cabem_no_cadastro(self):
        for item in itens_uma_seed():
            self.assertLessEqual(len(item['nome']), 200, item['nome'])
            self.assertTrue(item['nome'].strip())

    def test_linha_legivel_leva_via_sistema_e_gotejo(self):
        texto = _linha_legivel_uma({
            'dieta': 'FREBINI ORIGINAL 500 ML',
            'vol_dieta': '280',
            'volume': '280',
            'unidade': 'ML',
            'unid': 'ML',
            'h2': True,
            'h6': True,
            'via_dieta': 'SNE',
            'sistema': 'fechado',
            'gotejamento': '80',
            'vol_agua': '50',
        })
        self.assertIn('FREBINI ORIGINAL 500 ML', texto)
        self.assertIn('SNE', texto)
        self.assertIn('FECHADO', texto)
        self.assertIn('80 ML/H', texto)
        self.assertIn('AGUA: 50', texto)
        self.assertEqual(texto.count('280'), 1)

    def test_seed_cadastra_vias_pratos_e_dietas(self):
        chuca = NutViaAdministracao.query.filter_by(nome='CHUCA').first()
        self.assertIsNotNone(chuca)
        self.assertTrue(chuca.via_oral)
        sne = NutViaAdministracao.query.filter_by(nome='SNE').first()
        self.assertIsNotNone(sne)
        self.assertFalse(sne.via_oral)

        prato = NutPratoLiquido.query.filter_by(nome='BISCOITO POLVILHO (SEM GLÚTEN)').first()
        self.assertIsNotNone(prato)
        self.assertTrue(prato.grupo_extra)

        manip = NutUmaItem.query.filter_by(nome='SIMBIOFLORA', tipo='suplemento').first()
        self.assertIsNotNone(manip)
        self.assertTrue(manip.manipulado)

        aberto = NutUmaItem.query.filter_by(
            nome='FREBINI ORIGINAL 500 ML - FREBINI ORIGINAL 500 ML',
            sistema='aberto',
        ).first()
        fechado = NutUmaItem.query.filter_by(
            nome='FREBINI ORIGINAL 500 ML - FREBINI ORIGINAL 500 ML',
            sistema='fechado',
        ).first()
        self.assertIsNotNone(aberto)
        self.assertIsNotNone(fechado)

        formula = NutDieta.query.filter_by(nome='HIDROLISADA 1:30 - ALFARE').first()
        self.assertIsNotNone(formula)
        self.assertEqual(formula.categoria, 'formula')
        self.assertEqual(formula.grupo, 'FORMULAS INFANTIS')

        enteral = NutDieta.query.filter_by(nome='PEPTAMEN HN 500 ML - PEPTAMEN HN FLEX 500 ML').first()
        self.assertIsNotNone(enteral)
        self.assertEqual(enteral.categoria, 'enteral')
        self.assertEqual(enteral.grupo, 'ENTERAL SISTEMA FECHADO')

    def test_cadastro_grava_campos_da_foto_e_some_do_lancamento(self):
        from nutricao_service import list_uma_itens, salvar_cadastro_uma

        base = NutUmaItem.query.filter_by(tipo='formula').first()
        self.assertIsNotNone(base)
        row = salvar_cadastro_uma(base.cliente_id, {
            'tipo': 'formula',
            'nome': 'FORMULA TESTE 1:30',
            'diluicao': '1:30',
            'unidade': 'ML',
            'produto_disponivel': False,
            'produto_principal': 'ALFARE',
            'coluna_faturamento': 'FORMULAS INFANTIS',
            'sistema_fechado': True,
            'calorias': '67,5',
            'ptn': '2',
            'componentes': [{
                'componente': 'PO',
                'formula': 'ALFARE',
                'und': True,
                'vol': False,
                'codigo': '123',
                'un': 'G',
            }],
        })
        db.session.commit()
        data = row.to_dict()
        self.assertEqual(data['diluicao'], '1:30')
        self.assertEqual(data['unidade'], 'ML')
        self.assertTrue(data['sistema_fechado'])
        self.assertEqual(data['calorias'], 67.5)
        self.assertEqual(data['componentes'][0]['codigo'], '123')
        self.assertEqual(data['componentes'][0]['und'], True)

        visiveis = list_uma_itens(tipo='formula', somente_disponiveis=True)
        self.assertFalse(any(i['nome'] == 'FORMULA TESTE 1:30' for i in visiveis))
        todos = list_uma_itens(tipo='formula', somente_ativos=False)
        self.assertTrue(any(i['nome'] == 'FORMULA TESTE 1:30' for i in todos))

        dieta = NutDieta.query.filter_by(nome='FORMULA TESTE 1:30').first()
        self.assertIsNotNone(dieta)
        self.assertEqual(dieta.categoria, 'formula')
        self.assertEqual(dieta.grupo, 'FORMULAS INFANTIS')

        texto = _linha_legivel_uma({
            'formula': 'FORMULA TESTE 1:30',
            'diluicao': '1:30',
            'volume': '90',
            'unid': 'ML',
            'uma_item_id': row.id,
        })
        self.assertIn('FORMULA TESTE 1:30', texto)
        self.assertIn('DIL 1:30', texto)
        self.assertIn('ML', texto)

    def test_pagina_de_cadastro_lista_os_quatro_tipos(self):
        client = self.app.test_client()
        resp = client.get('/nutricao/cadastro-uma?tipo=formula')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Cadastro de Fórmula Infantil', html)
        self.assertIn('Diluição', html)
        self.assertIn('Componentes e fórmulas', html)
        self.assertIn('HIDROLISADA 1:30 - ALFARE', html)
        self.assertIn('tipo=enteral', html)
        self.assertIn('tipo=suplemento', html)
        self.assertIn('tipo=lve', html)
        enteral = client.get('/nutricao/cadastro-uma?tipo=enteral')
        self.assertIn('Sistema fechado', enteral.get_data(as_text=True))
        suplemento = client.get('/nutricao/cadastro-uma?tipo=suplemento')
        self.assertIn('Suplemento manipulado', suplemento.get_data(as_text=True))
        lve = client.get('/nutricao/cadastro-uma?tipo=lve')
        pagina = lve.get_data(as_text=True)
        self.assertIn('Cobrança relatório', pagina)
        self.assertIn('Espelho 1', pagina)
        self.assertIn('MISTURA NUTRITIVA S/LACTOSE', pagina)
        self.assertIn('SEM LACTOSE', pagina)
        self.assertIn('LACTENTES 0 A 6 MESES', pagina)
        self.assertIn('ISENTAS DE LACTOSE', pagina)
        self.assertIn('PREMATUROS E RECEM - NATOS DE BAIXO PESO', pagina)
        self.assertNotIn('BÁSICAS', pagina)
        self.assertNotIn('LACTÁRIO', pagina)
        self.assertIn('btnAddGrupo', pagina)
        self.assertIn('btnAddColuna', pagina)
        self.assertIn('Grupo para totalização', pagina)

    def test_mais_adiciona_grupo_e_coluna_nos_quatro_cadastros(self):
        client = self.app.test_client()
        casos = (
            ('suplemento', 'grupo', 'GRUPO TOTAL TESTE'),
            ('suplemento', 'coluna', 'COLUNA TOTAL TESTE'),
            ('lve', 'grupo', 'GRUPO LVE TESTE'),
            ('lve', 'coluna', 'COLUNA LVE TESTE'),
            ('formula', 'grupo', 'GRUPO FORMULA TESTE'),
            ('enteral', 'coluna', 'COLUNA ENTERAL TESTE'),
        )
        for tipo, campo, nome in casos:
            resp = client.post(
                '/nutricao/api/cadastro-uma/opcao',
                json={'tipo': tipo, 'campo': campo, 'nome': nome.lower()},
            )
            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
            self.assertEqual(resp.get_json()['nome'], nome)

        suplemento = client.get('/nutricao/cadastro-uma?tipo=suplemento').get_data(as_text=True)
        enteral = client.get('/nutricao/cadastro-uma?tipo=enteral').get_data(as_text=True)
        formula = client.get('/nutricao/cadastro-uma?tipo=formula').get_data(as_text=True)
        lve = client.get('/nutricao/cadastro-uma?tipo=lve').get_data(as_text=True)
        for pagina in (suplemento, enteral, formula):
            self.assertIn('btnAddGrupo', pagina)
            self.assertIn('btnAddColuna', pagina)
            self.assertIn('GRUPO TOTAL TESTE', pagina)
            self.assertIn('GRUPO FORMULA TESTE', pagina)
            self.assertIn('COLUNA TOTAL TESTE', pagina)
            self.assertIn('COLUNA ENTERAL TESTE', pagina)
            self.assertNotIn('GRUPO LVE TESTE', pagina)
            self.assertNotIn('COLUNA LVE TESTE', pagina)
        self.assertIn('GRUPO LVE TESTE', lve)
        self.assertIn('COLUNA LVE TESTE', lve)
        self.assertIn('MISTURA NUTRITIVA S/LACTOSE', lve)
        self.assertNotIn('COLUNA TOTAL TESTE', lve)
        self.assertNotIn('GRUPO TOTAL TESTE', lve)

        vazio = client.post(
            '/nutricao/api/cadastro-uma/opcao',
            json={'tipo': 'suplemento', 'campo': 'coluna', 'nome': '   '},
        )
        self.assertEqual(vazio.status_code, 400)

    def test_popup_edita_remove_e_lista_em_ordem(self):
        import json
        import re
        import unicodedata

        def ordem(nome):
            base = unicodedata.normalize('NFD', nome or '')
            return ''.join(ch for ch in base if unicodedata.category(ch) != 'Mn').casefold()

        client = self.app.test_client()
        pagina = client.get('/nutricao/cadastro-uma?tipo=lve').get_data(as_text=True)
        self.assertIn('modalOpcao', pagina)
        self.assertIn('Digite para filtrar', pagina)
        self.assertIn('opcaoAdicionar', pagina)
        grupos = json.loads(re.search(r'const GRUPOS = (\[.*?\]);', pagina).group(1))
        colunas = json.loads(re.search(r'const COLUNAS = (\[.*?\]);', pagina).group(1))
        self.assertEqual(grupos, sorted(grupos, key=ordem))
        self.assertEqual(colunas, sorted(colunas, key=ordem))
        self.assertGreater(len(grupos), 1)

        novo_grupo = client.post('/nutricao/api/cadastro-uma/opcao', json={
            'tipo': 'suplemento',
            'campo': 'grupo',
            'nome': 'grupo popup zz',
        })
        self.assertEqual(novo_grupo.status_code, 200, novo_grupo.get_data(as_text=True))

        criado = client.post('/nutricao/api/cadastro-uma', json={
            'tipo': 'suplemento',
            'nome': 'ITEM OPCAO POPUP',
            'grupo': 'GRUPO POPUP ZZ',
            'coluna_faturamento': 'COLUNA TOTAL TESTE',
        })
        self.assertEqual(criado.status_code, 200, criado.get_data(as_text=True))

        editado = client.put('/nutricao/api/cadastro-uma/opcao', json={
            'tipo': 'suplemento',
            'campo': 'grupo',
            'nome': 'GRUPO POPUP ZZ',
            'nome_novo': 'grupo total editado',
        })
        self.assertEqual(editado.status_code, 200, editado.get_data(as_text=True))
        corpo = editado.get_json()
        self.assertEqual(corpo['nome'], 'GRUPO TOTAL EDITADO')
        self.assertIn('GRUPO TOTAL EDITADO', corpo['nomes'])
        self.assertNotIn('GRUPO POPUP ZZ', corpo['nomes'])
        self.assertEqual(corpo['nomes'], sorted(corpo['nomes'], key=ordem))

        from models_nutricao import NutUmaItem
        item = NutUmaItem.query.filter_by(nome='ITEM OPCAO POPUP', tipo='suplemento').one()
        self.assertEqual(item.grupo, 'GRUPO TOTAL EDITADO')

        removido = client.delete('/nutricao/api/cadastro-uma/opcao', json={
            'tipo': 'lve',
            'campo': 'grupo',
            'nome': 'SEM LACTOSE',
        })
        self.assertEqual(removido.status_code, 200, removido.get_data(as_text=True))
        self.assertNotIn('SEM LACTOSE', removido.get_json()['nomes'])
        lve = client.get('/nutricao/cadastro-uma?tipo=lve').get_data(as_text=True)
        self.assertNotIn('SEM LACTOSE', lve)
        self.assertIn('MISTURA NUTRITIVA S/LACTOSE', lve)
        restaurado = client.post('/nutricao/api/cadastro-uma/opcao', json={
            'tipo': 'lve',
            'campo': 'grupo',
            'nome': 'SEM LACTOSE',
        })
        self.assertEqual(restaurado.status_code, 200, restaurado.get_data(as_text=True))
        self.assertIn('SEM LACTOSE', restaurado.get_json()['nomes'])


if __name__ == '__main__':
    unittest.main()
