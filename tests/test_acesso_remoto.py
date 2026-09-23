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
        from acesso_remoto import AcessoRemotoEquipamento, AcessoRemotoSessao, _filas, _frames
        AcessoRemotoSessao.query.delete()
        AcessoRemotoEquipamento.query.delete()
        db.session.commit()
        _filas.clear()
        _frames.clear()
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

    def test_token_invalido(self):
        r = self.app.test_client().post('/api/acesso-remoto/agente/pulso', headers={'X-Agente-Token': 'nao'})
        self.assertEqual(r.status_code, 401)


if __name__ == '__main__':
    unittest.main()
