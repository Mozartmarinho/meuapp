#!/usr/bin/env python3
"""Acesso remoto São Geraldo: número, senha e sessão."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402
from acesso_remoto import formatar_numero, normalizar_numero  # noqa: E402


class AcessoRemotoTest(unittest.TestCase):
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
        from acesso_remoto import AcessoRemotoEquipamento, AcessoRemotoSessao, _filas, _frames, _monitores
        AcessoRemotoSessao.query.delete()
        AcessoRemotoEquipamento.query.delete()
        db.session.commit()
        _filas.clear()
        _frames.clear()
        _monitores.clear()
        Usuario.query.delete()
        db.session.commit()
        self.user = Usuario(
            nome='Ana',
            email='ana-ar@example.com',
            senha=generate_password_hash('x'),
            ativo=True,
            perm_chamados=True,
        )
        db.session.add(self.user)
        db.session.commit()

    def _login(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['user_name'] = self.user.nome
        return client

    def test_numero_formatado(self):
        self.assertEqual(formatar_numero('123456789'), '123 456 789')
        self.assertEqual(normalizar_numero('123 456 789'), '123456789')
        self.assertEqual(normalizar_numero('12'), '')

    def test_pagina_e_menu(self):
        html = self._login().get('/acesso-remoto').get_data(as_text=True)
        self.assertIn('Acesso remoto São Geraldo', html)
        self.assertIn('Programa do equipamento', html)
        self.assertIn('>Acesso remoto<', html)
        self.assertIn('Ativo', html)
        self.assertIn('Excluir', html)

    def test_fluxo_senha_tela_e_comando(self):
        agente = self.app.test_client()
        reg = agente.post('/api/acesso-remoto/agente/registrar', json={'nome': 'Recepcao-01'})
        self.assertEqual(reg.status_code, 200)
        data = reg.get_json()
        token = data['token']
        self.assertEqual(len(data['numero']), 9)
        self.assertIn(' ', data['numero_formatado'])
        ruim = agente.post(
            '/api/acesso-remoto/agente/senha',
            json={'senha': '12'},
            headers={'X-Agente-Token': token},
        )
        self.assertEqual(ruim.status_code, 400)
        ok = agente.post(
            '/api/acesso-remoto/agente/senha',
            json={'senha': 'segredo'},
            headers={'X-Agente-Token': token},
        )
        self.assertEqual(ok.status_code, 200)
        web = self._login()
        negado = web.post('/acesso-remoto/conectar', json={'numero': data['numero_formatado'], 'senha': 'errada'})
        self.assertEqual(negado.status_code, 400)
        entrou = web.post('/acesso-remoto/conectar', json={'numero': data['numero'], 'senha': 'segredo'})
        self.assertEqual(entrou.status_code, 200, entrou.get_json())
        sessao_id = entrou.get_json()['sessao_id']
        self.assertEqual(web.get('/acesso-remoto/sessao/%s/tela' % sessao_id).status_code, 204)
        jpeg = b'\xff\xd8\xff\xd9'
        tela = agente.post(
            '/api/acesso-remoto/agente/tela?sessao_id=%s' % sessao_id,
            data=jpeg,
            headers={'X-Agente-Token': token, 'Content-Type': 'image/jpeg'},
        )
        self.assertTrue(tela.get_json()['ok'])
        vista = web.get('/acesso-remoto/sessao/%s/tela' % sessao_id)
        self.assertEqual(vista.status_code, 200)
        self.assertEqual(vista.data, jpeg)
        cmd = web.post('/acesso-remoto/sessao/%s/comando' % sessao_id, json={
            'tipo': 'mouse', 'acao': 'move', 'x': 0.5, 'y': 0.25,
        })
        self.assertEqual(cmd.status_code, 200)
        invalido = web.post('/acesso-remoto/sessao/%s/comando' % sessao_id, json={'tipo': 'exec'})
        self.assertEqual(invalido.status_code, 400)
        pulso = agente.post('/api/acesso-remoto/agente/pulso', headers={'X-Agente-Token': token})
        comandos = pulso.get_json()['comandos']
        self.assertEqual(len(comandos), 1)
        self.assertEqual(comandos[0]['acao'], 'move')
        de_novo = agente.post('/api/acesso-remoto/agente/pulso', headers={'X-Agente-Token': token})
        self.assertEqual(de_novo.get_json()['comandos'], [])
        self.assertEqual(web.post('/acesso-remoto/sessao/%s/encerrar' % sessao_id).status_code, 200)

    def test_renomear_excluir_e_escolher_tela(self):
        agente = self.app.test_client()
        reg = agente.post('/api/acesso-remoto/agente/registrar', json={'nome': 'Recepcao-01'})
        token = reg.get_json()['token']
        numero = reg.get_json()['numero']
        agente.post(
            '/api/acesso-remoto/agente/senha',
            json={'senha': 'segredo'},
            headers={'X-Agente-Token': token},
        )
        web = self._login()
        lista = web.get('/api/acesso-remoto/equipamentos').get_json()['equipamentos']
        eq_id = lista[0]['id']
        self.assertTrue(lista[0]['online'])
        html = web.get('/acesso-remoto').get_data(as_text=True)
        self.assertIn('ar-estado ativo', html)
        self.assertIn('Ativo', html)
        self.assertIn('segredo', html)
        self.assertIn('data-senha="segredo"', html)
        self.assertIn('Clique duas vezes para conectar', html)
        vazio = web.post('/api/acesso-remoto/equipamentos/%s/nome' % eq_id, json={'nome': '  '})
        self.assertEqual(vazio.status_code, 400)
        novo = web.post('/api/acesso-remoto/equipamentos/%s/nome' % eq_id, json={'nome': 'Recepção'})
        self.assertEqual(novo.status_code, 200)
        self.assertEqual(novo.get_json()['nome'], 'Recepção')
        de_novo = agente.post(
            '/api/acesso-remoto/agente/registrar',
            json={'nome': 'OUTRO-PC'},
            headers={'X-Agente-Token': token},
        )
        self.assertEqual(de_novo.get_json()['numero'], numero)
        nomes = web.get('/api/acesso-remoto/equipamentos').get_json()['equipamentos']
        self.assertEqual(nomes[0]['nome'], 'Recepção')
        entrou = web.post('/acesso-remoto/conectar', json={'numero': numero, 'senha': 'segredo'})
        sessao_id = entrou.get_json()['sessao_id']
        pagina = web.get('/acesso-remoto/sessao/%s' % sessao_id).get_data(as_text=True)
        self.assertIn('Tela cheia', pagina)
        self.assertIn('id="arTelas"', pagina)
        jpeg = b'\xff\xd8\xff\xd9'
        agente.post(
            '/api/acesso-remoto/agente/tela?sessao_id=%s&monitores=2&monitor=0' % sessao_id,
            data=jpeg,
            headers={'X-Agente-Token': token, 'Content-Type': 'image/jpeg'},
        )
        vista = web.get('/acesso-remoto/sessao/%s/tela' % sessao_id)
        self.assertEqual(vista.headers.get('X-Ar-Monitores'), '2')
        self.assertEqual(vista.headers.get('X-Ar-Monitor'), '0')
        troca = web.post('/acesso-remoto/sessao/%s/comando' % sessao_id, json={'tipo': 'monitor', 'indice': 1})
        self.assertEqual(troca.status_code, 200)
        self.assertEqual(web.get('/acesso-remoto/sessao/%s/tela' % sessao_id).headers.get('X-Ar-Monitor'), '1')
        pulso = agente.post('/api/acesso-remoto/agente/pulso', headers={'X-Agente-Token': token})
        self.assertEqual(pulso.get_json()['comandos'][0]['indice'], 1)
        fora = web.post('/api/acesso-remoto/equipamentos/%s/excluir' % eq_id)
        self.assertEqual(fora.status_code, 200)
        self.assertEqual(web.get('/api/acesso-remoto/equipamentos').get_json()['equipamentos'], [])
        sumiu = agente.post('/api/acesso-remoto/agente/pulso', headers={'X-Agente-Token': token})
        self.assertEqual(sumiu.status_code, 401)

    def test_token_invalido(self):
        r = self.app.test_client().post('/api/acesso-remoto/agente/pulso', headers={'X-Agente-Token': 'nao'})
        self.assertEqual(r.status_code, 401)


if __name__ == '__main__':
    unittest.main()
