#!/usr/bin/env python3
"""Sistema de Controle de Logística: permissões, dashboard e cadastro de frota."""
import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from logistica_service import geocodificar_endereco, rotear_coordenadas  # noqa: E402
from models import Cliente, db, Usuario  # noqa: E402
from models_logistica import (  # noqa: E402
    LogisticaChecklist,
    LogisticaColeta,
    LogisticaEntrega,
    LogisticaHigiene,
    LogisticaLancamento,
    LogisticaManutencao,
    LogisticaOciosidade,
    LogisticaRota,
    LogisticaVeiculo,
)
from password_utils import generate_password_hash  # noqa: E402
from permissions_sistemas import SISTEMAS  # noqa: E402


class LogisticaModuloTest(unittest.TestCase):
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

    def tearDown(self):
        LogisticaChecklist.query.delete()
        LogisticaHigiene.query.delete()
        LogisticaColeta.query.delete()
        LogisticaLancamento.query.delete()
        LogisticaManutencao.query.delete()
        LogisticaOciosidade.query.delete()
        LogisticaRota.query.delete()
        LogisticaEntrega.query.delete()
        LogisticaVeiculo.query.delete()
        Cliente.query.delete()
        Usuario.query.delete()
        db.session.commit()

    def _login(self, **kwargs):
        dados = dict(
            nome='Operador Logística',
            email='logistica@test.local',
            senha=generate_password_hash('x'),
            tipo='operador',
            ativo=True,
            perm_logistica=True,
        )
        dados.update(kwargs)
        user = Usuario(**dados)
        db.session.add(user)
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
        return user

    def test_sistema_registrado_nas_permissoes(self):
        self.assertIn('logistica', SISTEMAS)
        menus = [m[0] for m in SISTEMAS['logistica']['menus']]
        self.assertIn('dashboard', menus)
        self.assertIn('frota', menus)
        self.assertIn('dp', menus)
        self.assertIn('operacao', menus)
        self.assertIn('checklist', menus)
        self.assertIn('higiene', menus)
        self.assertIn('coletas', menus)

    def test_dashboard_exige_permissao(self):
        self._login(perm_logistica=False, email='sem@test.local')
        resp = self.client.get('/logistica', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_master_ok(self):
        self._login(is_master=True, tipo='admin', email='master-log@test.local')
        resp = self.client.get('/logistica')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Custo operacional', html)
        self.assertIn('Controle de Logística', html)

    def test_criar_veiculo_e_lancamento(self):
        self._login(is_master=True, tipo='admin', email='frota@test.local')
        resp = self.client.post(
            '/api/logistica/veiculos',
            json={'placa': 'ABC1D23', 'modelo': 'Sprinter'},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        veiculo_id = data['row']['id']
        resp = self.client.post(
            '/api/logistica/lancamentos',
            json={
                'data': date.today().isoformat(),
                'veiculo_id': veiculo_id,
                'categoria': 'Abastecimento',
                'valor': 250.5,
                'km': 120,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])
        dash = self.client.get('/logistica')
        self.assertEqual(dash.status_code, 200)
        self.assertIn('ABC1D23', dash.get_data(as_text=True))

    def test_paginas_operacao_e_peso(self):
        self._login(is_master=True, tipo='admin', email='op@test.local')
        for path in ('/logistica/operacao', '/logistica/checklist', '/logistica/higiene', '/logistica/coletas'):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)

    def test_criar_checklist_e_coleta(self):
        self._login(is_master=True, tipo='admin', email='peso@test.local')
        veic = self.client.post(
            '/api/logistica/veiculos',
            json={'placa': 'XYZ9A00', 'modelo': 'VW Delivery'},
        ).get_json()['row']
        chk = self.client.post(
            '/api/logistica/checklists',
            json={
                'data': date.today().isoformat(),
                'veiculo_id': veic['id'],
                'tipo': 'Saída',
                'motorista': 'João',
            },
        )
        self.assertEqual(chk.status_code, 200)
        self.assertTrue(chk.get_json()['ok'])
        col = self.client.post(
            '/api/logistica/coletas',
            json={
                'data': date.today().isoformat(),
                'cliente': 'Hospital',
                'peso_sujo': 120.5,
                'peso_limpo': 110.0,
                'valor_kg': 2.5,
            },
        )
        self.assertEqual(col.status_code, 200)
        data = col.get_json()
        self.assertTrue(data['ok'])
        self.assertAlmostEqual(data['row']['diferenca'], 10.5, places=2)
        self.assertAlmostEqual(data['row']['valor_recebido'], 275.0, places=2)

    def test_dashboard_graficos_respeitam_filtro(self):
        from logistica_service import evolucao_custos

        self._login(is_master=True, tipo='admin', email='grafico@test.local')
        veic = self.client.post(
            '/api/logistica/veiculos',
            json={'placa': 'GRA1F00', 'modelo': 'Accelo'},
        ).get_json()['row']
        self.client.post(
            '/api/logistica/lancamentos',
            json={
                'data': '2026-08-06',
                'veiculo_id': veic['id'],
                'placa': 'GRA1F00',
                'categoria': 'Combustível',
                'valor': 200,
                'km': 80,
            },
        )
        self.client.post(
            '/api/logistica/lancamentos',
            json={
                'data': '2026-08-07',
                'veiculo_id': veic['id'],
                'placa': 'GRA1F00',
                'categoria': 'Pedágio',
                'valor': 50,
            },
        )
        outro = self.client.post(
            '/api/logistica/veiculos',
            json={'placa': 'OUT9Z99', 'modelo': 'HR'},
        ).get_json()['row']
        self.client.post(
            '/api/logistica/lancamentos',
            json={
                'data': '2026-08-06',
                'veiculo_id': outro['id'],
                'placa': 'OUT9Z99',
                'categoria': 'Combustível',
                'valor': 999,
            },
        )
        serie = evolucao_custos(date(2026, 8, 6), date(2026, 8, 7), 'GRA1F00')
        self.assertEqual(serie['labels'], ['06/08', '07/08'])
        self.assertEqual(serie['abastecimento'], [200.0, 0.0])
        self.assertEqual(serie['pedagio'], [0.0, 50.0])
        self.assertAlmostEqual(serie['total'], 250.0)
        self.assertEqual(serie['maior_label'], 'Abastecimento')
        self.assertAlmostEqual(serie['maior_pct'], 80.0)

        html = self.client.get(
            '/logistica?data_de=2026-08-06&data_ate=2026-08-07&placa=GRA1F00'
        ).get_data(as_text=True)
        self.assertIn('Evolução dos custos', html)
        self.assertIn('Composição dos custos', html)
        self.assertIn('chartEvolucaoCustos', html)
        self.assertIn('"labels": ["06/08", "07/08"]', html)
        self.assertIn('"abastecimento": [200.0, 0.0]', html)
        self.assertIn('"maior_pct": 80.0', html)
        self.assertIn('"total": 250.0', html)

    def test_geocodificar_endereco_usa_nominatim(self):
        def fake_search(params):
            self.assertIn('Estrada da Conceicao, 834', params['q'])
            return [{'lat': '-22.8211', 'lon': '-43.0512', 'display_name': 'Mutuaguaçu'}]

        hit = geocodificar_endereco('  Estrada da Conceicao, 834  ', search=fake_search)
        self.assertAlmostEqual(hit['lat'], -22.8211)
        self.assertAlmostEqual(hit['lng'], -43.0512)
        self.assertEqual(hit['display_name'], 'Mutuaguaçu')
        self.assertIsNone(geocodificar_endereco('abc'))

    def test_geocodificar_endereco_com_cep_faz_fallback(self):
        def fake_search(params):
            return []

        def fake_cep(cep):
            self.assertEqual(cep, '24461840')
            return {'lat': -22.82694, 'lng': -43.05389, 'display_name': 'Estrada Conceição'}

        hit = geocodificar_endereco(
            'Estrada da Conceição, 834 - Mutuaguaçu, São Gonçalo - RJ, CEP 24461-840',
            search=fake_search,
            cep_lookup=fake_cep,
        )
        self.assertAlmostEqual(hit['lat'], -22.82694)
        self.assertAlmostEqual(hit['lng'], -43.05389)

    def test_api_geocode_e_entrega_preenche_coordenadas(self):
        self._login(is_master=True, tipo='admin', email='geo@test.local')
        fake = {'lat': -22.8211, 'lng': -43.0512, 'display_name': 'Matriz'}
        with patch('routes_logistica.geocodificar_endereco', return_value=fake) as mocked:
            geo = self.client.get('/api/logistica/geocode?q=Estrada da Conceicao, 834')
            self.assertEqual(geo.status_code, 200)
            self.assertTrue(geo.get_json()['ok'])
            self.assertAlmostEqual(geo.get_json()['lat'], -22.8211)
            created = self.client.post(
                '/api/logistica/entregas',
                json={'nome': 'Matriz', 'endereco': 'Estrada da Conceicao, 834'},
            )
            self.assertEqual(created.status_code, 200)
            row = created.get_json()['row']
            self.assertAlmostEqual(row['lat'], -22.8211)
            self.assertAlmostEqual(row['lng'], -43.0512)
            self.assertGreaterEqual(mocked.call_count, 2)
        page = self.client.get('/logistica/entregas')
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('/api/logistica/geocode', html)
        self.assertIn('mapaPonto', html)
        self.assertIn('ponto-label', html)
        self.assertIn('L.polyline', html)
        self.assertIn('origem_ponto_id', html)
        self.assertIn('mapa/preparar', html)
        self.assertIn('Processando', html)
        self.assertIn('mapaProcessando', html)
        self.assertIn('routing.openstreetmap.de', html)

    def test_rotear_coordenadas_usa_osrm_e_cai_para_linha(self):
        def fake_osrm(url):
            self.assertIn('router.project-osrm.org', url)
            return {
                'code': 'Ok',
                'routes': [{
                    'distance': 15200,
                    'geometry': {
                        'coordinates': [
                            [-43.1729, -22.9068],
                            [-43.1800, -22.9100],
                            [-43.1900, -22.9200],
                        ]
                    },
                }],
            }

        hit = rotear_coordenadas(-22.9068, -43.1729, -22.9200, -43.1900, fetch=fake_osrm)
        self.assertEqual(hit['fonte'], 'osrm')
        self.assertAlmostEqual(hit['km'], 15.2)
        self.assertEqual(hit['polyline'][0], [-22.9068, -43.1729])
        self.assertEqual(hit['polyline'][-1], [-22.9200, -43.1900])

        def boom(_url):
            raise TimeoutError('offline')

        fallback = rotear_coordenadas(-22.9, -43.1, -22.91, -43.2, fetch=boom)
        self.assertEqual(fallback['fonte'], 'linha')
        self.assertEqual(len(fallback['polyline']), 2)

    def test_rotear_usa_servidor_reserva_quando_o_primeiro_falha(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if 'project-osrm.org' in url:
                raise TimeoutError('offline')
            self.assertIn('routing.openstreetmap.de', url)
            return {
                'code': 'Ok',
                'routes': [{
                    'distance': 22100,
                    'geometry': {
                        'coordinates': [
                            [-43.1729, -22.9068],
                            [-43.1800, -22.9100],
                            [-43.2000, -22.9300],
                        ]
                    },
                }],
            }

        hit = rotear_coordenadas(-22.9068, -43.1729, -22.9300, -43.2000, fetch=fetch)
        self.assertEqual(hit['fonte'], 'osrm')
        self.assertEqual(len(hit['polyline']), 3)
        self.assertEqual(len(calls), 2)

    def test_importa_cliente_como_ponto_e_rota_entre_dois_pontos(self):
        self._login(is_master=True, tipo='admin', email='mapa@test.local')
        origem = Cliente(nome='Matriz SG', endereco='Estrada da Conceicao, 834', ativo=True)
        destino = Cliente(nome='Hospital Central', endereco='Rua da Praia, 100', ativo=True)
        db.session.add_all([origem, destino])
        db.session.commit()

        def fake_geo(endereco, **_kwargs):
            if 'Conceicao' in (endereco or ''):
                return {'lat': -22.8211, 'lng': -43.0512, 'display_name': 'Matriz'}
            return {'lat': -22.9068, 'lng': -43.1729, 'display_name': 'Hospital'}

        fake_trace = {
            'polyline': [[-22.8211, -43.0512], [-22.8500, -43.1000], [-22.9068, -43.1729]],
            'km': 18.4,
            'fonte': 'osrm',
        }
        with patch('logistica_service.geocodificar_endereco', side_effect=fake_geo):
            sync = self.client.post('/api/logistica/entregas/sincronizar-clientes')
        self.assertEqual(sync.status_code, 200)
        self.assertTrue(sync.get_json()['ok'])
        self.assertEqual(sync.get_json()['criados'], 2)

        pontos = self.client.get('/api/logistica/entregas').get_json()['rows']
        self.assertEqual(len(pontos), 2)
        nomes = sorted(p['nome'] for p in pontos)
        self.assertEqual(nomes, ['Hospital Central', 'Matriz SG'])
        ids = {p['nome']: p['id'] for p in pontos}

        with patch('routes_logistica.polyline_entre_pontos', return_value=fake_trace):
            created = self.client.post(
                '/api/logistica/rotas',
                json={
                    'origem_ponto_id': ids['Matriz SG'],
                    'destino_ponto_id': ids['Hospital Central'],
                    'status': 'Em rota',
                },
            )
        self.assertEqual(created.status_code, 200)
        row = created.get_json()['row']
        self.assertTrue(created.get_json()['ok'])
        self.assertEqual(row['status'], 'Em rota')
        self.assertEqual(row['origem'], 'Matriz SG')
        self.assertEqual(row['destino'], 'Hospital Central')
        self.assertIn('->', row['nome'])
        self.assertEqual(len(row['polyline']), 3)
        self.assertAlmostEqual(row['km'], 18.4)

        sem_pontos = self.client.post('/api/logistica/rotas', json={'nome': 'Vazia', 'status': 'Pendente'})
        self.assertEqual(sem_pontos.status_code, 400)

        mapa = self.client.get('/api/logistica/mapa').get_json()
        self.assertTrue(mapa['ok'])
        self.assertEqual(len(mapa['pontos']), 2)
        self.assertEqual(len(mapa['rotas']), 1)
        self.assertEqual(len(mapa['rotas'][0]['polyline']), 3)

        with patch('logistica_service.geocodificar_endereco', side_effect=fake_geo), \
                patch('logistica_service.rotear_coordenadas', return_value=fake_trace):
            reta = LogisticaRota(
                nome='Linha reta',
                origem_ponto_id=ids['Matriz SG'],
                destino_ponto_id=ids['Hospital Central'],
                origem='Matriz SG',
                destino='Hospital Central',
                status='Pendente',
                polyline='[[-22.8211, -43.0512], [-22.9068, -43.1729]]',
                km=12.0,
                ativa=True,
            )
            db.session.add(reta)
            db.session.commit()
            prep = self.client.post('/api/logistica/mapa/preparar')
        self.assertEqual(prep.status_code, 200)
        body = prep.get_json()
        self.assertTrue(body['ok'])
        self.assertGreaterEqual(body.get('rotas_retracadas') or 0, 1)
        retracada = [r for r in body['rotas'] if r['nome'] == 'Linha reta'][0]
        self.assertEqual(len(retracada['polyline']), 3)


if __name__ == '__main__':
    unittest.main()
