#!/usr/bin/env python3
"""Campanha de novo chamado para técnico, supervisor e gestor logados."""
import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import Chamado, ChamadoMensagem, ChamadoTecnico, ChamadoTecnicoMesa, Cliente, Equipamento, MesaServico, Usuario, db, now_brasilia  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402
from routes import _recebe_campanha_ticket  # noqa: E402


class CampanhaTicketTest(unittest.TestCase):
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
        ChamadoMensagem.query.delete()
        Chamado.query.delete()
        ChamadoTecnicoMesa.query.delete()
        ChamadoTecnico.query.delete()
        MesaServico.query.delete()
        Usuario.query.delete()
        Equipamento.query.delete()
        Cliente.query.delete()
        db.session.commit()
        self.cli = Cliente(nome='Hospital Teste', ativo=True, habilitado_chamados=True)
        self.mesa = MesaServico(nome='Informática', ativa=True)
        self.mesa_outra = MesaServico(nome='Elétrica', ativa=True)
        db.session.add(self.cli)
        db.session.add(self.mesa)
        db.session.add(self.mesa_outra)
        db.session.commit()

    def _usuario(self, nome, email, **kwargs):
        dados = dict(
            nome=nome,
            email=email,
            senha=generate_password_hash('x'),
            ativo=True,
            perm_chamados=True,
        )
        dados.update(kwargs)
        user = Usuario(**dados)
        db.session.add(user)
        db.session.commit()
        return user

    def _tecnico(self, nome, email, funcao='tecnico', mesa=None, **kwargs):
        user = self._usuario(nome, email, **kwargs)
        tec = ChamadoTecnico(
            nome=nome,
            email=email,
            usuario_id=user.id,
            funcao=funcao,
            ativo=True,
        )
        db.session.add(tec)
        db.session.flush()
        if mesa is not False:
            tec.mesas = [mesa or self.mesa]
        db.session.commit()
        return user

    def _chamado(self, opener, numero='OS000001', status='Pendente', mesa=None):
        chamado = Chamado(
            numero_chamado=numero,
            cliente_id=self.cli.id,
            tipo_servico='Manutenção',
            descricao='Não liga',
            status=status,
            tecnico_id=opener.id,
            mesa_id=(mesa or self.mesa).id,
        )
        db.session.add(chamado)
        db.session.commit()
        return chamado

    def _login(self, user):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['user_name'] = user.nome
        return client

    def test_recebe_tecnico_supervisor_gestor(self):
        tec = self._tecnico('Ana', 'ana@example.com', 'tecnico')
        sup = self._tecnico('Bia', 'bia@example.com', 'supervisor')
        ges = self._tecnico('Cris', 'cris@example.com', 'gestor')
        ass = self._tecnico('Duda', 'duda@example.com', 'assistente')
        admin = self._usuario('Admin', 'admin@example.com', tipo='admin')
        op = self._usuario('Op', 'op@example.com')
        self.assertTrue(_recebe_campanha_ticket(tec))
        self.assertTrue(_recebe_campanha_ticket(sup))
        self.assertTrue(_recebe_campanha_ticket(ges))
        self.assertTrue(_recebe_campanha_ticket(ass))
        self.assertFalse(_recebe_campanha_ticket(admin))
        self.assertFalse(_recebe_campanha_ticket(op))

    def test_api_sem_login(self):
        r = self.app.test_client().get('/api/chamados/campanha')
        self.assertEqual(r.status_code, 401)

    def test_assistente_so_ouve_preventiva_da_propria_mesa(self):
        opener = self._usuario('Solicitante', 'abre-ass@example.com')
        ass = self._tecnico('Duda', 'duda@example.com', 'assistente')
        ass_outra = self._tecnico('Eva', 'eva-ass@example.com', 'assistente', mesa=self.mesa_outra)
        comum = self._chamado(opener, 'OS100')
        preventiva = self._chamado(opener, 'OS101')
        preventiva.descricao = 'Preventiva: manutenção do equipamento'
        db.session.commit()
        client = self._login(ass)
        data = client.get('/api/chamados/campanha?after_id=0').get_json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['enabled'])
        ids = [c['id'] for c in data['campanhas']]
        self.assertIn(preventiva.id, ids)
        self.assertNotIn(comum.id, ids)
        outra = self._login(ass_outra).get('/api/chamados/campanha?after_id=0').get_json()
        self.assertNotIn(preventiva.id, [c['id'] for c in outra['campanhas']])

    def test_primeira_consulta_nao_lista_antigos(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana', 'ana@example.com')
        chamado = self._chamado(opener)
        chamado.data_criacao = datetime.utcnow() - timedelta(hours=3)
        db.session.commit()
        client = self._login(tec)
        r = client.get('/api/chamados/campanha?after_id=0')
        data = r.get_json()
        self.assertTrue(data['enabled'])
        self.assertEqual(data['campanhas'], [])
        self.assertEqual(data['latest_id'], chamado.id)

    def test_primeira_consulta_lista_recente(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana', 'ana@example.com')
        chamado = self._chamado(opener)
        client = self._login(tec)
        r = client.get('/api/chamados/campanha?after_id=0')
        data = r.get_json()
        self.assertIn(chamado.id, [c['id'] for c in data['campanhas']])

    def test_tecnico_recebe_chamado_novo(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana', 'ana@example.com')
        velho = self._chamado(opener, 'OS111')
        novo = self._chamado(opener, 'OS222')
        client = self._login(tec)
        r = client.get('/api/chamados/campanha?after_id=%s' % velho.id)
        data = r.get_json()
        ids = [c['id'] for c in data['campanhas']]
        self.assertIn(novo.id, ids)
        self.assertNotIn(velho.id, ids)
        self.assertEqual(data['campanhas'][0]['numero_chamado'], 'OS222')
        self.assertIn('atender=', data['campanhas'][0]['url'])

    def test_quem_abriu_tecnico_tambem_recebe(self):
        opener = self._tecnico('Ana', 'ana@example.com')
        outro = self._usuario('Outro', 'outro@example.com')
        velho = self._chamado(opener, 'OS300')
        chamado = self._chamado(opener, 'OS333')
        client = self._login(opener)
        r = client.get('/api/chamados/campanha?after_id=%s' % velho.id)
        ids = [c['id'] for c in r.get_json()['campanhas']]
        self.assertIn(chamado.id, ids)
        client_outro = self._login(outro)
        self.assertFalse(client_outro.get('/api/chamados/campanha').get_json()['enabled'])

    def test_supervisor_e_gestor_recebem(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        sup = self._tecnico('Bia', 'bia@example.com', 'supervisor')
        ges = self._tecnico('Cris', 'cris@example.com', 'gestor')
        velho = self._chamado(opener, 'OS400')
        chamado = self._chamado(opener, 'OS444')
        for user in (sup, ges):
            data = self._login(user).get(
                '/api/chamados/campanha?after_id=%s' % velho.id
            ).get_json()
            self.assertIn(chamado.id, [c['id'] for c in data['campanhas']])


    def test_pendente_continua_na_lista_ate_atender(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        tec = self._tecnico('Ana', 'ana@example.com')
        velho = self._chamado(opener, 'OS500')
        novo = self._chamado(opener, 'OS555')
        client = self._login(tec)
        r = client.get('/api/chamados/campanha?after_id=%s&ids=%s' % (novo.id, novo.id))
        data = r.get_json()
        self.assertIn(novo.id, [c['id'] for c in data['pendentes']])
        self.assertNotIn(velho.id, [c['id'] for c in data['pendentes']])
        novo.status = 'Em Andamento'
        db.session.commit()
        r2 = client.get('/api/chamados/campanha?after_id=%s&ids=%s' % (novo.id, novo.id))
        self.assertNotIn(novo.id, [c['id'] for c in r2.get_json()['pendentes']])

    def test_atender_atribui_e_bloqueia_outro(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        ana = self._tecnico('Ana', 'ana@example.com')
        bia = self._tecnico('Bia', 'bia@example.com')
        chamado = self._chamado(opener, 'OS777')
        r = self._login(ana).get('/api/chamados/%s/atender' % chamado.id)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['chamado']['atendente_id'], ana.id)
        self.assertEqual(data['chamado']['status'], 'Em Andamento')
        r2 = self._login(bia).get('/api/chamados/%s/atender' % chamado.id)
        self.assertEqual(r2.status_code, 409)
        self.assertIn('Ana', r2.get_json()['message'])
        db.session.refresh(chamado)
        self.assertEqual(chamado.atendente_id, ana.id)

    def test_liberar_volta_pendente_e_retoma_toque(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        ana = self._tecnico('Ana', 'ana@example.com')
        bia = self._tecnico('Bia', 'bia@example.com')
        chamado = self._chamado(opener, 'OS778')
        client_ana = self._login(ana)
        client_ana.get('/api/chamados/%s/atender' % chamado.id)
        r = client_ana.post('/api/chamados/%s/liberar-atendimento' % chamado.id)
        self.assertEqual(r.status_code, 200)
        db.session.refresh(chamado)
        self.assertEqual(chamado.status, 'Pendente')
        self.assertEqual(chamado.atendente_id, ana.id)
        self.assertIsNone(chamado.atendendo_em)
        camp = self._login(bia).get('/api/chamados/campanha?after_id=0').get_json()
        self.assertIn(chamado.id, [c['id'] for c in camp.get('retomados', [])])
        r2 = self._login(bia).get('/api/chamados/%s/atender' % chamado.id)
        self.assertEqual(r2.status_code, 409)

    def test_admin_pode_assumir_de_outro(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        ana = self._tecnico('Ana', 'ana@example.com')
        admin = self._usuario('Admin', 'admin2@example.com', tipo='admin', is_master=True)
        chamado = self._chamado(opener, 'OS779')
        self._login(ana).get('/api/chamados/%s/atender' % chamado.id)
        r = self._login(admin).get('/api/chamados/%s/atender' % chamado.id)
        self.assertEqual(r.status_code, 200)
        db.session.refresh(chamado)
        self.assertEqual(chamado.atendente_id, admin.id)
        self.assertIsNotNone(chamado.data_inicio_atendimento)

    def test_toque_so_da_mesa_do_ticket(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        da_mesa = self._tecnico('Ana', 'ana@example.com')
        outra = self._tecnico('Bia', 'bia@example.com', mesa=self.mesa_outra)
        sem_mesa = self._tecnico('Caio', 'caio@example.com', mesa=False)
        sup = self._tecnico('Duda', 'duda@example.com', 'supervisor')
        ges = self._tecnico('Eva', 'eva@example.com', 'gestor', mesa=self.mesa_outra)
        velho = self._chamado(opener, 'OS879')
        chamado = self._chamado(opener, 'OS880')
        for user, espera in (
            (da_mesa, True),
            (sup, True),
            (outra, False),
            (sem_mesa, False),
            (ges, False),
        ):
            data = self._login(user).get(
                '/api/chamados/campanha?after_id=%s' % velho.id
            ).get_json()
            ids = [c['id'] for c in data.get('campanhas') or []]
            if espera:
                self.assertTrue(data.get('enabled'), user.nome)
                self.assertIn(chamado.id, ids, user.nome)
            else:
                self.assertNotIn(chamado.id, ids, user.nome)

    def test_preventiva_nutricao_nao_toca_na_informatica(self):
        opener = self._usuario('Solicitante', 'abre-nutri@example.com')
        nutri = MesaServico(nome='Manutenção Nutrição', ativa=True)
        db.session.add(nutri)
        db.session.commit()
        ti = self._tecnico('Mozart', 'mozart@example.com')
        da_nutri = self._tecnico('Joilson', 'joilson@example.com', mesa=nutri)
        eq = Equipamento(
            nome_equipamento='Rampa',
            patrimonio='7238',
            cliente_id=self.cli.id,
            tipo_equipamento='nutricao',
            ativo=True,
        )
        db.session.add(eq)
        db.session.commit()
        velho = self._chamado(opener, 'OS200')
        chamado = self._chamado(opener, 'OS201', mesa=self.mesa)
        chamado.descricao = 'Preventiva: manutenção preventiva do equipamento Rampa'
        chamado.equipamento_id = eq.id
        db.session.commit()
        ti_ids = [
            c['id'] for c in self._login(ti).get(
                '/api/chamados/campanha?after_id=%s' % velho.id
            ).get_json()['campanhas']
        ]
        nutri_ids = [
            c['id'] for c in self._login(da_nutri).get(
                '/api/chamados/campanha?after_id=%s' % velho.id
            ).get_json()['campanhas']
        ]
        self.assertNotIn(chamado.id, ti_ids)
        self.assertIn(chamado.id, nutri_ids)

    def test_atender_mostra_problema_e_troca_patrimonio_do_estoque(self):
        opener = self._usuario('Solicitante', 'abre-pat@example.com')
        ana = self._tecnico('Ana', 'ana-pat@example.com')
        ruim = Equipamento(
            nome_equipamento='Monitor ruim',
            patrimonio='PAT-RUIM',
            numero_serie='SER-RUIM',
            setor='DP',
            localizacao='DP',
            usuario_equipamento='Maria',
            cliente_id=self.cli.id,
            ativo=True,
        )
        novo = Equipamento(
            nome_equipamento='Monitor novo',
            patrimonio='PAT-NOVO',
            numero_serie='SER-NOVO',
            setor='Estoque',
            localizacao='Estoque',
            cliente_id=self.cli.id,
            ativo=True,
        )
        db.session.add(ruim)
        db.session.add(novo)
        db.session.commit()
        chamado = self._chamado(opener, 'OS990')
        chamado.descricao = 'A tela pisca e apaga'
        chamado.equipamento_id = ruim.id
        chamado.patrimonio = ruim.patrimonio
        chamado.equipamento = ruim.nome_equipamento
        db.session.commit()
        client = self._login(ana)
        aberto = client.get('/api/chamados/%s/atender' % chamado.id)
        self.assertEqual(aberto.status_code, 200)
        payload = aberto.get_json()['chamado']
        self.assertEqual(payload['descricao'], 'A tela pisca e apaga')
        self.assertTrue(payload['pode_transferir'])
        self.assertEqual([item['patrimonio'] for item in payload['estoque_opcoes']], ['PAT-NOVO'])
        salvo = client.post('/api/chamados/%s/atender' % chamado.id, data={
            'acao': 'salvar',
            'status': 'Em Andamento',
            'equipamento_estoque_id': str(novo.id),
            'atendimento_notas': 'Troca de monitor',
        })
        self.assertEqual(salvo.status_code, 200, salvo.get_json())
        db.session.refresh(chamado)
        db.session.refresh(ruim)
        db.session.refresh(novo)
        self.assertEqual(chamado.equipamento_id, novo.id)
        self.assertEqual(chamado.patrimonio, 'PAT-NOVO')
        self.assertEqual(novo.setor, 'DP')
        self.assertEqual(novo.usuario_equipamento, 'Maria')
        self.assertEqual(ruim.setor, 'Estoque')
        self.assertIsNone(ruim.usuario_equipamento)
        self.assertIn('PAT-RUIM', salvo.get_json()['message'])
        self.assertIn('PAT-NOVO', salvo.get_json()['message'])

    def test_atender_grava_inicio_e_finalizar_grava_fim(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        ana = self._tecnico('Ana', 'ana@example.com')
        chamado = self._chamado(opener, 'OS881')
        client = self._login(ana)
        r = client.get('/api/chamados/%s/atender' % chamado.id)
        self.assertEqual(r.status_code, 200)
        db.session.refresh(chamado)
        inicio = chamado.data_inicio_atendimento
        self.assertIsNotNone(inicio)
        self.assertIn('data_inicio_atendimento', r.get_json()['chamado'])
        client.post('/api/chamados/%s/liberar-atendimento' % chamado.id)
        db.session.refresh(chamado)
        self.assertEqual(chamado.data_inicio_atendimento, inicio)
        r2 = client.post(
            '/api/chamados/%s/atender' % chamado.id,
            data={'acao': 'finalizar', 'atendimento_notas': 'Trocou a fonte'},
        )
        self.assertEqual(r2.status_code, 200)
        db.session.refresh(chamado)
        self.assertEqual(chamado.status, 'Atendido')
        self.assertIsNotNone(chamado.data_conclusao)
        self.assertGreaterEqual(chamado.data_conclusao, inicio)

    def _ids(self, payload, chave):
        return [c['id'] for c in payload.get(chave) or []]

    def test_gravar_aguardar_peca_ou_encaminhado_sai_do_toque(self):
        opener = self._usuario('Solicitante', 'abre@example.com')
        ana = self._tecnico('Ana', 'ana@example.com')
        for numero, status in (('OS910', 'Aguardar peça'), ('OS911', 'Encaminhado')):
            chamado = self._chamado(opener, numero)
            client = self._login(ana)
            self.assertEqual(client.get('/api/chamados/%s/atender' % chamado.id).status_code, 200)
            r = client.post('/api/chamados/%s/atender' % chamado.id, data={
                'acao': 'salvar',
                'status': status,
            })
            self.assertEqual(r.status_code, 200, r.get_json())
            db.session.refresh(chamado)
            self.assertEqual(chamado.status, status)
            self.assertIsNone(chamado.atendendo_em)
            camp = client.get('/api/chamados/campanha?after_id=0&ids=%s' % chamado.id).get_json()
            self.assertNotIn(chamado.id, self._ids(camp, 'pendentes'))
            self.assertNotIn(chamado.id, self._ids(camp, 'retomados'))

    def test_reagendar_avisa_solicitante_e_para_toque(self):
        opener = self._usuario('Solicitante', 'abre-reag@example.com')
        ana = self._tecnico('Ana', 'ana-reag@example.com')
        chamado = self._chamado(opener, 'OS912')
        chamado.canal_abertura = 'E-mail'
        chamado.contato_abertura = opener.email
        db.session.commit()
        dia = now_brasilia().date() + timedelta(days=3)
        client = self._login(ana)
        client.get('/api/chamados/%s/atender' % chamado.id)
        r = client.post('/api/chamados/%s/atender' % chamado.id, data={
            'acao': 'salvar',
            'status': 'Reagendado',
            'data_reagendamento': dia.isoformat(),
            'atendimento_notas': 'Peça chega na sexta',
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        db.session.refresh(chamado)
        self.assertEqual(chamado.status, 'Reagendado')
        self.assertEqual(chamado.data_reagendamento, dia)
        self.assertIsNone(chamado.atendendo_em)
        self.assertIn('reagendado', (r.get_json().get('message') or '').lower())
        textos = [m.texto or '' for m in ChamadoMensagem.query.filter_by(chamado_id=chamado.id).all()]
        self.assertTrue(any('reagendado' in t.lower() and dia.strftime('%d/%m/%Y') in t for t in textos))
        camp = client.get('/api/chamados/campanha?after_id=0&ids=%s' % chamado.id).get_json()
        self.assertNotIn(chamado.id, self._ids(camp, 'pendentes'))
        self.assertNotIn(chamado.id, self._ids(camp, 'retomados'))
        self.assertEqual(chamado.status, 'Reagendado')

    def test_reagendar_sem_dia_futuro_recusa(self):
        opener = self._usuario('Solicitante', 'abre-dia@example.com')
        ana = self._tecnico('Ana', 'ana-dia@example.com')
        chamado = self._chamado(opener, 'OS913')
        client = self._login(ana)
        client.get('/api/chamados/%s/atender' % chamado.id)
        r = client.post('/api/chamados/%s/atender' % chamado.id, data={
            'acao': 'salvar',
            'status': 'Reagendado',
            'data_reagendamento': now_brasilia().date().isoformat(),
        })
        self.assertEqual(r.status_code, 400)
        db.session.refresh(chamado)
        self.assertEqual(chamado.status, 'Em Andamento')

    def test_no_dia_reagendado_volta_pendente_e_toca(self):
        opener = self._usuario('Solicitante', 'abre-volta@example.com')
        ana = self._tecnico('Ana', 'ana-volta@example.com')
        chamado = self._chamado(opener, 'OS914', status='Reagendado')
        chamado.data_reagendamento = now_brasilia().date()
        chamado.atendente_id = ana.id
        chamado.atendendo_em = None
        db.session.commit()
        camp = self._login(ana).get('/api/chamados/campanha?after_id=0').get_json()
        db.session.refresh(chamado)
        self.assertEqual(chamado.status, 'Pendente')
        self.assertIn(chamado.id, self._ids(camp, 'retomados'))

    def test_lista_renderiza_reagendado(self):
        opener = self._usuario('Solicitante', 'abre-lista@example.com')
        ana = self._tecnico('Ana', 'ana-lista@example.com')
        chamado = self._chamado(opener, 'OS915', status='Reagendado')
        chamado.data_reagendamento = now_brasilia().date() + timedelta(days=2)
        db.session.commit()
        r = self._login(ana).get('/chamados')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('Reagendado', html)
        self.assertIn('at_data_reagendamento', html)
        self.assertIn(chamado.data_reagendamento.strftime('%d/%m/%Y'), html)


if __name__ == '__main__':
    unittest.main()
