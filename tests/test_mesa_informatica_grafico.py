#!/usr/bin/env python3
"""Mesa Suporte vira Informática; gráfico de finalizados no dashboard."""
import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app  # noqa: E402
from models import (  # noqa: E402
    Chamado,
    ChamadoTecnico,
    ChamadoTecnicoMesa,
    Cliente,
    MesaServico,
    Usuario,
    db,
    migrar_mesa_suporte_para_informatica,
)
from password_utils import generate_password_hash  # noqa: E402
from routes import _grafico_finalizados_dashboard  # noqa: E402


class MesaInformaticaGraficoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
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
        Chamado.query.delete()
        ChamadoTecnicoMesa.query.delete()
        ChamadoTecnico.query.delete()
        MesaServico.query.delete()
        Usuario.query.delete()
        Cliente.query.delete()
        db.session.commit()

    def test_suporte_passa_vinculos_para_informatica_existente(self):
        info = MesaServico(nome='Informatica', ativa=True)
        suporte = MesaServico(nome='Suporte', ativa=True)
        cli = Cliente(nome='Hospital', ativo=True, habilitado_chamados=True)
        user = Usuario(
            nome='Ana',
            email='ana-mesa@example.com',
            senha=generate_password_hash('x'),
            ativo=True,
        )
        db.session.add_all([info, suporte, cli, user])
        db.session.flush()
        tec = ChamadoTecnico(nome='Ana', email=user.email, usuario_id=user.id, funcao='tecnico', ativo=True)
        db.session.add(tec)
        db.session.flush()
        tec.mesas = [suporte]
        chamado = Chamado(
            numero_chamado='OS900',
            cliente_id=cli.id,
            tipo_servico='Manutenção',
            descricao='Tela',
            status='Pendente',
            tecnico_id=user.id,
            mesa_id=suporte.id,
        )
        db.session.add(chamado)
        db.session.commit()
        migrar_mesa_suporte_para_informatica()
        db.session.expire_all()
        self.assertIsNone(MesaServico.query.filter_by(nome='Suporte').first())
        destino = MesaServico.query.filter_by(nome='Informatica').one()
        self.assertEqual(Chamado.query.get(chamado.id).mesa_id, destino.id)
        self.assertEqual(
            [m.id for m in ChamadoTecnico.query.get(tec.id).mesas],
            [destino.id],
        )

    def test_grafico_filtra_periodo_e_tecnico(self):
        info = MesaServico(nome='Informática', ativa=True)
        cli = Cliente(nome='Hospital', ativo=True, habilitado_chamados=True)
        ana = Usuario(nome='Ana Silva', email='ana-g@example.com', senha=generate_password_hash('x'), ativo=True)
        bia = Usuario(nome='Bia Souza', email='bia-g@example.com', senha=generate_password_hash('x'), ativo=True)
        db.session.add_all([info, cli, ana, bia])
        db.session.flush()
        agora = datetime.now().replace(microsecond=0)
        antigo = agora - timedelta(days=40)
        db.session.add(Chamado(
            numero_chamado='OS901', cliente_id=cli.id, tipo_servico='Manutenção',
            descricao='A', status='Atendido', tecnico_id=ana.id, mesa_id=info.id,
            atendente_id=ana.id, data_conclusao=agora,
        ))
        db.session.add(Chamado(
            numero_chamado='OS902', cliente_id=cli.id, tipo_servico='Manutenção',
            descricao='B', status='Concluído', tecnico_id=ana.id, mesa_id=info.id,
            atendente_id=bia.id, data_conclusao=agora,
        ))
        db.session.add(Chamado(
            numero_chamado='OS903', cliente_id=cli.id, tipo_servico='Manutenção',
            descricao='C', status='Atendido', tecnico_id=ana.id, mesa_id=info.id,
            atendente_id=ana.id, data_conclusao=antigo,
        ))
        db.session.commit()

        class Args(dict):
            def get(self, key, default=None, type=None):
                val = dict.get(self, key, default)
                if type and val not in (None, ''):
                    return type(val)
                return val

        de = (agora - timedelta(days=29)).date().isoformat()
        ate = agora.date().isoformat()
        graf, _opcoes = _grafico_finalizados_dashboard(Args(de=de, ate=ate), None)
        self.assertEqual(graf['total'], 2)
        graf_ana, _ = _grafico_finalizados_dashboard(Args(de=de, ate=ate, tecnico=str(ana.id)), None)
        self.assertEqual(graf_ana['total'], 1)
        self.assertEqual(graf_ana['tecnicos'][0]['label'], 'Ana Silva')
        self.assertEqual(graf_ana['tecnicos'][0]['count'], 1)
        todos, _ = _grafico_finalizados_dashboard(Args(), None)
        self.assertEqual(todos['total'], 3)
        self.assertIn('OS903', [item['numero'] for item in todos['lista']])
        nutri = MesaServico(nome='Manutenção Nutrição', ativa=True)
        db.session.add(nutri)
        db.session.commit()
        so_info, _ = _grafico_finalizados_dashboard(Args(de='2020-01-01', ate=ate), info.id)
        self.assertEqual(so_info['total'], 3)
        so_nutri, _ = _grafico_finalizados_dashboard(Args(de='2020-01-01', ate=ate), nutri.id)
        self.assertEqual(so_nutri['total'], 0)


if __name__ == '__main__':
    unittest.main()
