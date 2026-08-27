#!/usr/bin/env python3
"""Ordem das colunas e endereço na coluna Local do cadastro de equipamentos."""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATE = os.path.join(ROOT, 'templates', 'equipamentos.html')
MODELS = os.path.join(ROOT, 'models.py')
SQLITE_URI = 'sqlite:///:memory:'


def _sqlite_app():
    os.environ['DATABASE_URL'] = SQLITE_URI
    import db_config
    import app as app_mod
    db_config.SQLALCHEMY_DATABASE_URI = SQLITE_URI
    app_mod.SQLALCHEMY_DATABASE_URI = SQLITE_URI
    app = app_mod.create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLITE_URI
    app.config['TESTING'] = True
    return app, app_mod


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
        sql = str(Equipamento.__table__.select().compile())
        self.assertNotIn('equipamentos.equipamento,', sql)
        self.assertNotIn('equipamentos.equipamento ', sql)

    def test_listagem_usa_consulta_com_retry(self):
        with open(os.path.join(ROOT, 'routes.py'), encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('def _listar_equipamentos_cadastrados', src)
        self.assertIn('ensure_equipamentos_schema()', src)
        self.assertIn('is_missing_equipamentos_equipamento_column', src)
        self.assertIn('equipamentos = _listar_equipamentos_cadastrados()', src)

    def test_forcar_coluna_nao_mexe_em_sqlite(self):
        from db_config import forcar_coluna_equipamento
        import db_config
        old = db_config.SQLALCHEMY_DATABASE_URI
        db_config.SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
        try:
            self.assertFalse(forcar_coluna_equipamento())
        finally:
            db_config.SQLALCHEMY_DATABASE_URI = old

    def test_detecta_erro_coluna_ausente(self):
        from app import is_missing_equipamentos_equipamento_column
        self.assertTrue(is_missing_equipamentos_equipamento_column(
            Exception("(1054, \"Unknown column 'equipamentos.equipamento' in 'field list'\")")
        ))
        self.assertFalse(is_missing_equipamentos_equipamento_column(
            Exception("(1054, \"Unknown column 'equipamentos.marca' in 'field list'\")")
        ))

    def test_consulta_funciona_sem_coluna_legado(self):
        from sqlalchemy import text
        from models import Equipamento, db

        app, _app_mod = _sqlite_app()
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
            itens = Equipamento.consulta().all()
            self.assertEqual(len(itens), 1)
            self.assertEqual(itens[0].nome_equipamento, 'PC Recepção')
            self.assertEqual(itens[0].equipamento, 'PC Recepção')

    def test_ensure_adiciona_coluna_equipamento_ausente(self):
        from sqlalchemy import text
        from models import Equipamento, db

        app, app_mod = _sqlite_app()
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
            cols = {c.lower() for c in app_mod.equipamentos_column_names()}
            self.assertNotIn('equipamento', cols)
            app_mod.ensure_equipamentos_schema()
            cols = {c.lower() for c in app_mod.equipamentos_column_names()}
            self.assertIn('equipamento', cols)
            self.assertTrue(Equipamento._tem_coluna_legado)
            eq = Equipamento.consulta().first()
            self.assertIsNotNone(eq)
            self.assertEqual(eq.nome_equipamento, 'PC Recepção')
            self.assertEqual(eq.equipamento, 'PC Recepção')
            novo = Equipamento(
                nome_equipamento='Notebook',
                patrimonio='EQ-2',
                cliente_id=1,
            )
            db.session.add(novo)
            db.session.commit()
            self.assertEqual(novo.equipamento, 'Notebook')


if __name__ == '__main__':
    unittest.main()
