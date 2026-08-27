#!/usr/bin/env python3
"""Ordem das colunas e endereço na coluna Local do cadastro de equipamentos."""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATE = os.path.join(ROOT, 'templates', 'equipamentos.html')
MODELS = os.path.join(ROOT, 'models.py')


class EquipamentosColunasTest(unittest.TestCase):
    def test_ordem_colunas_e_endereco_no_local(self):
        with open(TEMPLATE, encoding='utf-8') as fh:
            html = fh.read()
        thead = re.search(r'<thead>\s*<tr>(.*?)</tr>\s*</thead>', html, re.S)
        self.assertIsNotNone(thead)
        ths = [
            re.sub(r'<[^>]+>', '', t).strip()
            for t in re.findall(r'<th[^>]*>(.*?)</th>', thead.group(1), re.S)
        ]
        self.assertEqual(
            ths[:8],
            ['Código', 'Nome', 'Marca', 'Modelo', 'Cliente', 'Local', 'Setor', 'Data da compra'],
        )
        self.assertEqual(ths[8], 'Ações')
        self.assertIn("eq.cliente.endereco", html)
        self.assertIn("eq.cliente.nome if eq.cliente else '—'", html)
        tbody_start = html.find('<tbody>')
        tbody = html[tbody_start:html.find('</tbody>', tbody_start)]
        cliente_td = tbody.find("eq.cliente.nome if eq.cliente else '—'")
        endereco_td = tbody.find("endereco or '—'")
        self.assertGreater(cliente_td, 0)
        self.assertGreater(endereco_td, cliente_td)

    def test_to_dict_inclui_endereco_do_cliente(self):
        with open(MODELS, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn("'cliente_endereco': (self.cliente.endereco or '') if self.cliente else ''", src)

    def test_modelo_nao_seleciona_coluna_legado_equipamento(self):
        from models import Equipamento
        colunas = {c.name for c in Equipamento.__table__.columns}
        self.assertNotIn('equipamento', colunas)
        self.assertIn('nome_equipamento', colunas)

    def test_consulta_funciona_sem_coluna_legado(self):
        from sqlalchemy import text
        from app import create_app
        from models import Equipamento, db

        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        app = create_app()
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        with app.app_context():
            db.session.execute(text('DROP TABLE IF EXISTS equipamentos'))
            db.session.execute(text(
                'CREATE TABLE equipamentos ('
                'id INTEGER PRIMARY KEY,'
                'nome_equipamento VARCHAR(100) NOT NULL,'
                'marca VARCHAR(100),'
                'modelo VARCHAR(100),'
                'numero_serie VARCHAR(50),'
                'patrimonio VARCHAR(50),'
                'localizacao VARCHAR(100),'
                'setor VARCHAR(100),'
                'local VARCHAR(200),'
                'ativo INTEGER DEFAULT 1,'
                'data_compra DATE,'
                'data_manutencao DATE,'
                'data_criacao DATETIME,'
                'atualizado_em DATETIME,'
                'cliente_id INTEGER NOT NULL,'
                'tipo_recurso VARCHAR(40),'
                'grupo_id INTEGER,'
                'usuario_equipamento VARCHAR(120),'
                'ip VARCHAR(45),'
                'is_agente INTEGER DEFAULT 0'
                ')'
            ))
            db.session.execute(text(
                "INSERT INTO equipamentos (nome_equipamento, patrimonio, cliente_id) "
                "VALUES ('PC Recepção', 'EQ-1', 1)"
            ))
            db.session.commit()
            itens = Equipamento.query.all()
            self.assertEqual(len(itens), 1)
            self.assertEqual(itens[0].nome_equipamento, 'PC Recepção')
            self.assertEqual(itens[0].equipamento, 'PC Recepção')

    def test_ensure_adiciona_coluna_equipamento_ausente(self):
        from sqlalchemy import inspect, text
        from app import create_app, ensure_equipamentos_schema
        from models import Equipamento, db

        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        app = create_app()
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        with app.app_context():
            db.session.execute(text('DROP TABLE IF EXISTS equipamentos'))
            db.session.execute(text(
                'CREATE TABLE equipamentos ('
                'id INTEGER PRIMARY KEY,'
                'nome_equipamento VARCHAR(100) NOT NULL,'
                'patrimonio VARCHAR(50),'
                'cliente_id INTEGER NOT NULL,'
                'ativo INTEGER DEFAULT 1,'
                'is_agente INTEGER DEFAULT 0'
                ')'
            ))
            db.session.execute(text(
                "INSERT INTO equipamentos (nome_equipamento, patrimonio, cliente_id) "
                "VALUES ('PC Recepção', 'EQ-1', 1)"
            ))
            db.session.commit()
            cols = {c['name'] for c in inspect(db.engine).get_columns('equipamentos')}
            self.assertNotIn('equipamento', cols)
            ensure_equipamentos_schema()
            cols = {c['name'] for c in inspect(db.engine).get_columns('equipamentos')}
            self.assertIn('equipamento', cols)
            eq = Equipamento.query.first()
            self.assertIsNotNone(eq)
            self.assertEqual(eq.nome_equipamento, 'PC Recepção')
            self.assertEqual(eq.equipamento, 'PC Recepção')


if __name__ == '__main__':
    unittest.main()
