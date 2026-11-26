#!/usr/bin/env python3
"""Lançamento manual de peso pela web no Controle de Pesagem."""
import os
import sys
import unittest
import zipfile
from datetime import datetime
from io import BytesIO

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import db, Usuario  # noqa: E402
from models_pesagem import PesagemBalanca, PesagemCliente, PesagemLeitura  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402


class LancamentoManualPesagemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cls.client = cls.app.test_client()
        user = Usuario(
            nome='Admin Pesagem',
            email='pesagem-manual@test.local',
            senha=generate_password_hash('admin'),
            tipo='admin',
            is_master=True,
            perm_pesagem=True,
            ativo=True,
        )
        db.session.add(user)
        db.session.commit()
        cls.user_id = user.id

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id
        PesagemLeitura.query.delete()
        db.session.commit()

    def _cliente_balanca(self):
        cli = PesagemCliente.query.filter_by(nome='HOTEL SOL').first()
        if not cli:
            cli = PesagemCliente(nome='HOTEL SOL')
            db.session.add(cli)
        bal = PesagemBalanca.query.filter_by(codigo='BAL-01').first()
        if not bal:
            bal = PesagemBalanca(codigo='BAL-01', nome='Principal', local='Recepção', ativo=True)
            db.session.add(bal)
        db.session.commit()
        return cli, bal

    def test_lancamento_avulso_saiu_do_dashboard(self):
        self._cliente_balanca()
        html = self.client.get('/pesagem/lancamento').get_data(as_text=True)
        self.assertIn('Lançamento avulso', html)
        self.assertIn('Lançar peso manualmente', html)
        self.assertIn('id="formLancamentoManual"', html)
        self.assertIn('/api/pesagem/leituras/manual', html)
        self.assertIn('HOTEL SOL', html)
        self.assertIn('BAL-01', html)
        painel = self.client.get('/pesagem').get_data(as_text=True)
        self.assertNotIn('id="formLancamentoManual"', painel)
        self.assertNotIn('Agente local', painel)
        self.assertIn('Evolução pesagem', painel)
        self.assertIn('Imprimir dados filtro', painel)
        self.assertIn('Gerar PDF do filtro', painel)
        self.assertIn('Gerar Excel', painel)
        self.assertIn('Agente pesagem (exe)', painel)
        self.assertLess(
            painel.find('Cadastro de Cliente'),
            painel.find('Lançamento avulso'),
        )
        self.assertLess(
            painel.find('Agente pesagem (exe)'),
            painel.find('>Auditoria<'),
        )

    def test_lanca_peso_manual(self):
        cli, bal = self._cliente_balanca()
        resp = self.client.post(
            '/api/pesagem/leituras/manual',
            json={
                'cliente_id': cli.id,
                'balanca_codigo': bal.codigo,
                'peso': '12,5',
                'tara': '1,5',
                'data_hora': '2026-11-04T14:30',
                'observacao': 'Entrada pela recepção',
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        leitura = PesagemLeitura.query.get(data['id'])
        self.assertEqual(leitura.origem, 'manual')
        self.assertEqual(leitura.cliente_id, cli.id)
        self.assertEqual(leitura.balanca_codigo, 'BAL-01')
        self.assertAlmostEqual(leitura.peso_liquido, 12.5)
        self.assertAlmostEqual(leitura.peso, 12.5)
        self.assertAlmostEqual(leitura.tara, 1.5)
        self.assertAlmostEqual(leitura.peso_bruto, 14.0)
        self.assertEqual(leitura.computador, 'Admin Pesagem')
        self.assertEqual(leitura.observacao, 'Entrada pela recepção')
        self.assertEqual(leitura.data_leitura, datetime(2026, 11, 4, 14, 30))
        html = self.client.get('/pesagem?data_de=2026-11-04&data_ate=2026-11-04').get_data(as_text=True)
        self.assertIn('>Manual<', html)
        self.assertIn('Entrada pela recepção', html)

    def test_rejeita_peso_invalido_e_sem_cliente(self):
        cli, bal = self._cliente_balanca()
        resp = self.client.post(
            '/api/pesagem/leituras/manual',
            json={'cliente_id': cli.id, 'balanca_codigo': bal.codigo, 'peso': '0'},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.get_json().get('ok'))
        resp = self.client.post(
            '/api/pesagem/leituras/manual',
            json={'balanca_codigo': bal.codigo, 'peso': '3'},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(PesagemLeitura.query.count(), 0)

    def test_api_key_nao_lanca_sem_login(self):
        cli, bal = self._cliente_balanca()
        with self.client.session_transaction() as sess:
            sess.clear()
        resp = self.client.post(
            '/api/pesagem/leituras/manual',
            headers={'X-API-Key': 'saogeraldo-pesagem-2025'},
            json={'cliente_id': cli.id, 'balanca_codigo': bal.codigo, 'peso': '4'},
        )
        self.assertIn(resp.status_code, (302, 401))
        self.assertEqual(PesagemLeitura.query.count(), 0)

    def test_evolucao_pdf_e_excel_do_filtro(self):
        cli, bal = self._cliente_balanca()
        outra = PesagemBalanca(codigo='BAL-02', nome='Secundária', ativo=True)
        db.session.add(outra)
        db.session.flush()
        for quando, codigo, peso in (
            (datetime(2026, 11, 1, 8, 0), 'BAL-01', 10.0),
            (datetime(2026, 11, 1, 9, 0), 'BAL-01', 5.0),
            (datetime(2026, 11, 2, 8, 0), 'BAL-01', 2.0),
            (datetime(2026, 11, 1, 10, 0), 'BAL-02', 99.0),
        ):
            db.session.add(PesagemLeitura(
                balanca_id=bal.id if codigo == 'BAL-01' else outra.id,
                balanca_codigo=codigo,
                peso=peso,
                peso_liquido=peso,
                peso_bruto=peso,
                tara=0,
                unidade='kg',
                estavel=True,
                origem='agente',
                cliente_id=cli.id,
                cliente_nome=cli.nome,
                data_leitura=quando,
            ))
        db.session.commit()
        html = self.client.get('/pesagem', query_string={
            'evo_de': '2026-11-01',
            'evo_ate': '2026-11-03',
            'evo_balanca': 'BAL-01',
            'data_de': '2026-11-01',
            'data_ate': '2026-11-01',
            'balanca': 'BAL-01',
        }).get_data(as_text=True)
        self.assertIn('"itens":[2,1,0]', html.replace(' ', ''))
        self.assertIn('chartEvolucaoPesagem', html)

        pdf = self.client.get('/pesagem/filtro.pdf', query_string={
            'data_de': '2026-11-01',
            'data_ate': '2026-11-01',
            'balanca': 'BAL-01',
        })
        self.assertEqual(pdf.status_code, 200)
        self.assertIn('pdf', pdf.mimetype)
        self.assertTrue(pdf.data.startswith(b'%PDF'))
        self.assertIn('HOTEL SOL'.encode('latin-1'), pdf.data)

        xlsx = self.client.get('/pesagem/filtro.xlsx', query_string={
            'data_de': '2026-11-01',
            'data_ate': '2026-11-02',
            'cliente_id': cli.id,
        })
        self.assertEqual(xlsx.status_code, 200)
        self.assertTrue(xlsx.data.startswith(b'PK'))
        with zipfile.ZipFile(BytesIO(xlsx.data)) as pacote:
            planilha = pacote.read('xl/worksheets/sheet1.xml').decode('utf-8')
        self.assertIn('HOTEL SOL', planilha)
        self.assertEqual(planilha.count('<row '), 5)

        agente = self.client.get('/pesagem/agente')
        self.assertEqual(agente.status_code, 200)
        self.assertIn('Baixar AgentePesagem.exe', agente.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
