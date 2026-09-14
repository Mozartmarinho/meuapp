#!/usr/bin/env python3
"""GET /nutricao must serve the latest nutrition UI without HTML cache."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db  # noqa: E402


class NutricaoPaginaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cls.client = cls.app.test_client()

    def tearDown(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_dashboard_tem_impressoes_novas_e_sem_cache(self):
        resp = self.client.get('/nutricao')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('MAPA DE PRODUÇÃO', html)
        self.assertIn('Impressão mapa da nutrição', html)
        self.assertIn('Impressão mapa distribuição', html)
        self.assertIn('/nutricao/impressao-mapa-distribuicao', html)
        self.assertIn('Selecione o grupo de clínicas para ver o mapa', html)
        self.assertIn('filtroGrupoClinica', html)
        self.assertIn('Grupo de clínicas:', html)
        self.assertNotIn('filtroEnfermaria', html)
        self.assertIn('São Geraldo Service ·', html)
        self.assertIn('projeto-versao-bar', html)
        self.assertNotIn(' · rev ', html)
        self.assertNotIn('module-revision', html)
        cache = (resp.headers.get('Cache-Control') or '').lower()
        self.assertIn('no-store', cache)
        self.assertIn('text/html', resp.headers.get('Content-Type', ''))

    def test_faixa_mostra_nome_do_usuario_logado(self):
        from models import Usuario
        from password_utils import generate_password_hash

        user = Usuario(
            nome='Mozart Marinho',
            email='mozart.barra@test.local',
            senha=generate_password_hash('x'),
            ativo=True,
            is_master=True,
            tipo='admin',
        )
        db.session.add(user)
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['user_name'] = user.nome
        html = self.client.get('/nutricao').get_data(as_text=True)
        self.assertIn('São Geraldo Service · Mozart Marinho', html)
        self.assertNotIn('São Geraldo Service · meuapp', html)
        self.assertIn('const USUARIO_ATUAL = "Mozart Marinho"', html)

    def test_rota_versao_nao_e_404(self):
        resp = self.client.get('/nutricao/versao')
        self.assertEqual(resp.status_code, 200)
        texto = resp.get_data(as_text=True)
        self.assertIn('meuapp', texto)
        self.assertIn('pasta', texto)

    def test_rotas_de_impressao_existem(self):
        mapa = self.client.get('/nutricao/impressao-mapa')
        dist = self.client.get('/nutricao/impressao-mapa-distribuicao')
        self.assertEqual(mapa.status_code, 200)
        self.assertEqual(dist.status_code, 200)
        self.assertIn('Impressão mapa da nutrição', mapa.get_data(as_text=True))
        self.assertIn('MAPA DISTRIBUIÇÃO', dist.get_data(as_text=True).upper())

    def test_menu_e_pagina_grupo_de_clinicas(self):
        resp = self.client.get('/nutricao')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Grupo de Clínicas', html)
        self.assertIn('/nutricao/grupos-clinicas', html)
        self.assertIn('filtroGrupoClinica', html)

        pagina = self.client.get('/nutricao/grupos-clinicas')
        self.assertEqual(pagina.status_code, 200)
        corpo = pagina.get_data(as_text=True)
        self.assertIn('Cadastro de Grupo de Clínicas', corpo)
        self.assertIn('Novo Grupo', corpo)
        self.assertIn('Vínculo Grupo', corpo)

    def test_api_grupo_clinicas_cria_e_vincula(self):
        from models_nutricao import NutClinica
        from nutricao_tenant import ensure_cliente_hfb

        cid = ensure_cliente_hfb().id
        clinica = NutClinica(nome='CTI GRUPO TESTE', ativo=True, cliente_id=cid)
        db.session.add(clinica)
        db.session.commit()

        criado = self.client.post(
            '/nutricao/api/grupos-clinicas',
            json={'nome': 'GRUPO CTI TESTE', 'ativo': True},
        )
        self.assertEqual(criado.status_code, 200)
        data = criado.get_json()
        self.assertTrue(data.get('ok'))
        gid = data['id']

        vinculo = self.client.put(
            f'/nutricao/api/grupos-clinicas/{gid}/clinicas',
            json={'clinica_ids': [clinica.id]},
        )
        self.assertEqual(vinculo.status_code, 200)
        grupo = vinculo.get_json().get('grupo') or {}
        self.assertEqual(grupo.get('num_clinicas'), 1)
        self.assertEqual(grupo['clinicas'][0]['id'], clinica.id)

    def test_excluir_clinica_exige_sem_enfermaria(self):
        from models_nutricao import NutClinica, NutEnfermaria
        from nutricao_tenant import ensure_cliente_hfb

        cid = ensure_cliente_hfb().id
        clinica = NutClinica(nome='CLINICA EXCLUIR TESTE', ativo=True, cliente_id=cid)
        enf = NutEnfermaria(nome='ENF EXCLUIR TESTE', ativo=True, cliente_id=cid)
        db.session.add_all([clinica, enf])
        db.session.flush()
        clinica.enfermarias.append(enf)
        db.session.commit()

        bloqueado = self.client.delete(f'/nutricao/api/clinicas/{clinica.id}')
        self.assertEqual(bloqueado.status_code, 409)
        self.assertFalse(bloqueado.get_json().get('ok'))
        self.assertIn('enfermaria', (bloqueado.get_json().get('error') or '').lower())
        self.assertIsNotNone(NutClinica.query.get(clinica.id))

        clinica.enfermarias = []
        db.session.commit()
        ok = self.client.delete(f'/nutricao/api/clinicas/{clinica.id}')
        self.assertEqual(ok.status_code, 200)
        self.assertIsNone(NutClinica.query.get(clinica.id))

    def test_excluir_enfermaria_exige_sem_leito(self):
        from models_nutricao import NutEnfermaria, NutLeito
        from nutricao_tenant import ensure_cliente_hfb

        cid = ensure_cliente_hfb().id
        enf = NutEnfermaria(nome='ENF LEITO EXCLUIR', ativo=True, cliente_id=cid)
        db.session.add(enf)
        db.session.flush()
        db.session.add(NutLeito(enfermaria_id=enf.id, numero=1, nome='01', ativo=True))
        db.session.commit()

        bloqueado = self.client.delete(f'/nutricao/api/enfermarias/{enf.id}')
        self.assertEqual(bloqueado.status_code, 409)
        self.assertIn('leito', (bloqueado.get_json().get('error') or '').lower())
        self.assertIsNotNone(NutEnfermaria.query.get(enf.id))

        NutLeito.query.filter_by(enfermaria_id=enf.id).delete()
        db.session.commit()
        ok = self.client.delete(f'/nutricao/api/enfermarias/{enf.id}')
        self.assertEqual(ok.status_code, 200)
        self.assertIsNone(NutEnfermaria.query.get(enf.id))

    def test_menu_categoria_acima_de_dietas(self):
        html = self.client.get('/nutricao').get_data(as_text=True)
        self.assertIn('Categoria', html)
        self.assertIn('/nutricao/categorias', html)
        self.assertIn('/nutricao/grupos-dietas', html)
        self.assertIn('/nutricao/dietas', html)
        i_leitos = html.find('/nutricao/leitos')
        i_cat = html.find('/nutricao/categorias')
        i_grupos = html.find('/nutricao/grupos-dietas')
        i_dietas = html.find('/nutricao/dietas')
        self.assertGreater(i_leitos, 0)
        self.assertGreater(i_cat, i_leitos)
        self.assertGreater(i_grupos, i_cat)
        self.assertGreater(i_dietas, i_grupos)

        pagina = self.client.get('/nutricao/categorias')
        self.assertEqual(pagina.status_code, 200)
        corpo = pagina.get_data(as_text=True)
        self.assertIn('Cadastro de Categoria', corpo)
        self.assertIn('Nova Categoria', corpo)
        self.assertIn('Básica / Oral', corpo)

    def test_api_categoria_cria_e_aparece_nas_dietas(self):
        criado = self.client.post(
            '/nutricao/api/categorias',
            json={'nome': 'Dieta Teste Cat', 'ativo': True},
        )
        self.assertEqual(criado.status_code, 200)
        data = criado.get_json()
        self.assertTrue(data.get('ok'))
        cat = data.get('categoria') or {}
        self.assertEqual(cat.get('nome'), 'Dieta Teste Cat')
        self.assertTrue(cat.get('codigo'))

        dietas = self.client.get('/nutricao/dietas')
        self.assertEqual(dietas.status_code, 200)
        html = dietas.get_data(as_text=True)
        self.assertIn('Dieta Teste Cat', html)
        self.assertIn('CATEGORIAS_DIETA', html)


if __name__ == '__main__':
    unittest.main()
