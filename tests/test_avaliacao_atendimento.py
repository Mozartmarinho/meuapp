#!/usr/bin/env python3
"""Atendimento do dia e avaliação do chamado."""
import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['PESAGEM_WA_DISABLE'] = '1'

from app import create_app  # noqa: E402
from chamados_avaliacao import (  # noqa: E402
    montar_atendimento_dia,
    montar_calendario,
    parse_nota_avaliacao,
    relatorio_avaliacoes,
)
from models import (  # noqa: E402
    Chamado,
    ChamadoAvaliacao,
    Cliente,
    Usuario,
    WhatsAppChamadoUsuario,
    db,
)
from password_utils import generate_password_hash  # noqa: E402
from routes import _avisar_finalizacao_ticket  # noqa: E402
from whatsapp_chamados import process_inbound  # noqa: E402


class _Item:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.numero_chamado = kwargs.get('numero', 'OS1')
        self.tipo_servico = kwargs.get('tipo', 'Manutenção')
        self.status = kwargs.get('status', 'Pendente')
        self.data_criacao = kwargs.get('abertura')
        self.data_inicio_atendimento = kwargs.get('atendimento')
        self.data_conclusao = kwargs.get('finalizacao')
        self.data_reagendamento = kwargs.get('reagendamento')
        self.cliente = kwargs.get('cliente')
        self.atendente = kwargs.get('tecnico')


class _Nome:
    def __init__(self, nome):
        self.nome = nome


class AtendimentoDiaTest(unittest.TestCase):
    def test_notas_aceitas(self):
        self.assertEqual(parse_nota_avaliacao('1')[1], 'Péssimo')
        self.assertEqual(parse_nota_avaliacao('Muito bom')[0], 4)
        self.assertEqual(parse_nota_avaliacao('excelente')[1], 'Excelente')
        self.assertIsNone(parse_nota_avaliacao('quero abrir um chamado'))

    def test_dia_separa_horarios_e_clique_no_calendario(self):
        dia = datetime(2026, 11, 24).date()
        itens = [
            _Item(
                id=1, numero='OS1', status='Atendido',
                abertura=datetime(2026, 11, 24, 8, 10),
                atendimento=datetime(2026, 11, 24, 9, 0),
                finalizacao=datetime(2026, 11, 24, 11, 30),
                cliente=_Nome('Hospital'), tecnico=_Nome('Ana'),
            ),
            _Item(
                id=2, numero='OS2', status='Pendente',
                abertura=datetime(2026, 11, 23, 18, 0),
                cliente=_Nome('Clínica'),
            ),
        ]
        painel = montar_atendimento_dia(itens, dia)
        self.assertEqual(painel['abertos'], 1)
        self.assertEqual(painel['em_atendimento'], 1)
        self.assertEqual(painel['finalizados'], 1)
        self.assertEqual(painel['pendentes'], 0)
        self.assertEqual(painel['linhas'][0]['abertura'], '24/11 08:10')
        self.assertEqual(painel['linhas'][0]['atendimento'], '24/11 09:00')
        self.assertEqual(painel['linhas'][0]['finalizacao'], '24/11 11:30')
        self.assertEqual(painel['chart']['abertos'][7], 0)
        self.assertEqual(painel['chart']['abertos'][8], 1)
        self.assertEqual(painel['chart']['finalizados'][11], 1)
        cal = montar_calendario(dia, itens, hoje=dia)
        marcado = [cell for semana in cal['semanas'] for cell in semana if cell['sel']]
        self.assertEqual(marcado[0]['iso'], '2026-11-24')
        self.assertEqual(marcado[0]['qtd'], 1)


class AvaliacaoIntegracaoTest(unittest.TestCase):
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
        from models import ChamadoMensagem, WhatsAppChamadoLog
        WhatsAppChamadoLog.query.delete()
        ChamadoMensagem.query.delete()
        ChamadoAvaliacao.query.delete()
        Chamado.query.delete()
        WhatsAppChamadoUsuario.query.delete()
        Usuario.query.delete()
        Cliente.query.delete()
        db.session.commit()
        self.cli = Cliente(nome='Hospital Sul', ativo=True, habilitado_chamados=True)
        self.outro = Cliente(nome='Clínica Norte', ativo=True, habilitado_chamados=True)
        db.session.add_all([self.cli, self.outro])
        db.session.commit()
        self.opener = Usuario(
            nome='Maria Abre', email='maria@example.com',
            senha=generate_password_hash('x'), ativo=True, perm_chamados=True,
            telefone='21988880000',
        )
        self.tec = Usuario(
            nome='Carlos Técnico', email='carlos@example.com',
            senha=generate_password_hash('x'), ativo=True, tipo='admin', is_master=True,
        )
        self.outro_tec = Usuario(
            nome='Paula Técnica', email='paula@example.com',
            senha=generate_password_hash('x'), ativo=True, perm_chamados=True,
        )
        db.session.add_all([self.opener, self.tec, self.outro_tec])
        db.session.commit()

    def _chamado(self, numero, cliente, atendente, status='Atendido'):
        row = Chamado(
            numero_chamado=numero,
            cliente_id=cliente.id,
            tipo_servico='Manutenção',
            descricao='Não liga',
            status=status,
            tecnico_id=self.opener.id,
            atendente_id=atendente.id,
            canal_abertura='WhatsApp',
            contato_abertura='21988880000',
            data_criacao=datetime(2026, 11, 24, 8, 0),
            data_inicio_atendimento=datetime(2026, 11, 24, 9, 0),
            data_conclusao=datetime(2026, 11, 24, 11, 0),
        )
        db.session.add(row)
        db.session.commit()
        return row

    def test_finalizacao_pede_avaliacao_e_whatsapp_grava_nota(self):
        chamado = self._chamado('OS910001', self.cli, self.tec, status='Pendente')
        enviados = []

        def fake_wa(telefone, texto):
            enviados.append((telefone, texto))
            return {'ok': True}

        r = _avisar_finalizacao_ticket(
            chamado, self.tec, 'Troca da fonte', enviar_wa=fake_wa,
            agora=datetime(2026, 11, 24, 11, 5),
        )
        self.assertTrue(r['ok'])
        self.assertIn('Péssimo', enviados[0][1])
        self.assertIn('Excelente', enviados[0][1])
        self.assertIn('/avaliar/', enviados[0][1])
        avaliacao = ChamadoAvaliacao.query.filter_by(chamado_id=chamado.id).one()
        self.assertIsNone(avaliacao.nota)
        self.assertEqual(avaliacao.tecnico_id, self.tec.id)
        usuario = WhatsAppChamadoUsuario(telefone='5521988880000', nome='Maria', etapa='avaliacao')
        db.session.add(usuario)
        db.session.commit()
        resp = process_inbound('21988880000', '4', sender=fake_wa)
        self.assertTrue(resp.get('avaliacao'))
        self.assertIn('Muito bom', resp['replies'][-1])
        db.session.refresh(avaliacao)
        self.assertEqual(avaliacao.nota, 4)
        self.assertEqual(avaliacao.rotulo, 'Muito bom')

    def test_link_publico_e_filtro_do_relatorio(self):
        a = self._chamado('OS910002', self.cli, self.tec)
        b = self._chamado('OS910003', self.outro, self.outro_tec)
        db.session.add(ChamadoAvaliacao(
            chamado_id=a.id, nota=5, rotulo='Excelente', tecnico_id=self.tec.id,
            cliente_id=self.cli.id, telefone='5521988880000', token='tok-a',
            criada_em=datetime(2026, 11, 24, 11, 0), avaliada_em=datetime(2026, 11, 24, 12, 0),
        ))
        db.session.add(ChamadoAvaliacao(
            chamado_id=b.id, nota=1, rotulo='Péssimo', tecnico_id=self.outro_tec.id,
            cliente_id=self.outro.id, telefone='5521977770000', token='tok-b',
            criada_em=datetime(2026, 11, 20, 11, 0), avaliada_em=datetime(2026, 11, 20, 12, 0),
        ))
        db.session.commit()
        client = self.app.test_client()
        pagina = client.get('/avaliar/tok-a')
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('Excelente', pagina.get_data(as_text=True))
        rel = relatorio_avaliacoes(
            [a.id, b.id], datetime(2026, 11, 1).date(), datetime(2026, 11, 30).date(),
            tecnico_id=self.tec.id, cliente_id=self.cli.id,
        )
        self.assertEqual(rel['total'], 1)
        self.assertEqual(rel['linhas'][0]['rotulo'], 'Excelente')
        self.assertEqual(rel['linhas'][0]['unidade'], 'Hospital Sul')
        vazio = relatorio_avaliacoes(
            [a.id, b.id], datetime(2026, 11, 1).date(), datetime(2026, 11, 30).date(),
            tecnico_id=self.tec.id, cliente_id=self.outro.id,
        )
        self.assertEqual(vazio['total'], 0)

    def test_dashboard_mostra_abas(self):
        self._chamado('OS910004', self.cli, self.tec)
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = self.opener.id
            sess['user_name'] = self.opener.nome
        resp = client.get('/dashboard?dia=2026-11-24')
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200, html[:500])
        self.assertIn('Atendimento do dia', html)
        self.assertIn('Avaliações', html)
        self.assertIn('OS910004', html)
        self.assertIn('Hora de abertura', html)


if __name__ == '__main__':
    unittest.main()
