from flask import Flask
from routes import main
from routes_nutricao import nutricao
from routes_pesagem import pesagem
from routes_audit import auditoria
from models import db, Usuario
from db_config import SQLALCHEMY_DATABASE_URI
import models_nutricao  # noqa: F401 — registra tabelas de nutrição
import models_pesagem  # noqa: F401 — registra tabelas de pesagem
import models_audit  # noqa: F401 — registra tabelas de auditoria
import os


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'saogeraldo2025')
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    app.register_blueprint(main)
    app.register_blueprint(nutricao)
    app.register_blueprint(pesagem)
    app.register_blueprint(auditoria)

    from audit_service import register_audit_hooks
    register_audit_hooks(app)

    return app


def ensure_usuarios_schema():
    """Garante coluna senha_hash (modelo mapeia Usuario.senha -> senha_hash)."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        if 'usuarios' not in set(insp.get_table_names()):
            return
        cols = {c['name'] for c in insp.get_columns('usuarios')}
        if 'senha_hash' in cols:
            return
        if 'senha' in cols:
            db.session.execute(text('ALTER TABLE usuarios CHANGE COLUMN senha senha_hash VARCHAR(255) NOT NULL'))
        else:
            db.session.execute(text("ALTER TABLE usuarios ADD COLUMN senha_hash VARCHAR(255) NOT NULL DEFAULT ''"))
        db.session.commit()
    except Exception:
        db.session.rollback()


def ensure_chamados_schema():
    """Garante colunas do modelo Chamado (tecnico_id, equipamento) e FK de tecnico."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'chamados' not in tables:
            return
        cols = {c['name'] for c in insp.get_columns('chamados')}
        if 'tecnico_id' not in cols:
            db.session.execute(text('ALTER TABLE chamados ADD COLUMN tecnico_id INT NULL'))
            db.session.commit()
        if 'equipamento' not in cols:
            db.session.execute(text('ALTER TABLE chamados ADD COLUMN equipamento VARCHAR(100) NULL'))
            db.session.commit()
        if 'usuarios' not in tables:
            return
        insp = inspect(db.engine)
        fks = insp.get_foreign_keys('chamados')
        has_fk = any(
            'tecnico_id' in (fk.get('constrained_columns') or [])
            and fk.get('referred_table') == 'usuarios'
            for fk in fks
        )
        if not has_fk:
            db.session.execute(text(
                'ALTER TABLE chamados '
                'ADD CONSTRAINT fk_chamados_tecnico '
                'FOREIGN KEY (tecnico_id) REFERENCES usuarios(id)'
            ))
            db.session.commit()
    except Exception:
        db.session.rollback()


def ensure_clientes_schema():
    """Garante colunas do modelo Cliente ausentes no banco legado."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        if 'clientes' not in set(insp.get_table_names()):
            return
        cols = {c['name'] for c in insp.get_columns('clientes')}
        alters = []
        if 'telefone' not in cols:
            alters.append('ADD COLUMN telefone VARCHAR(20) NULL')
        if 'responsavel' not in cols:
            alters.append('ADD COLUMN responsavel VARCHAR(100) NULL')
        if 'telefone_responsavel' not in cols:
            alters.append('ADD COLUMN telefone_responsavel VARCHAR(20) NULL')
        if 'ativo' not in cols:
            alters.append('ADD COLUMN ativo TINYINT(1) NOT NULL DEFAULT 1')
        if 'data_criacao' not in cols:
            alters.append('ADD COLUMN data_criacao DATETIME NULL')
        for clause in alters:
            db.session.execute(text(f'ALTER TABLE clientes {clause}'))
            db.session.commit()
    except Exception:
        db.session.rollback()


if __name__ == '__main__':
    from werkzeug.security import generate_password_hash

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_usuarios_schema()
        ensure_clientes_schema()
        ensure_chamados_schema()
        from nutricao_service import seed_nutricao
        from routes_pesagem import seed_pesagem
        from audit_service import ensure_audit_table
        seed_nutricao()
        seed_pesagem()
        ensure_audit_table()
        if not Usuario.query.first():
            admin = Usuario(
                nome='Admin',
                email='admin@example.com',
                senha=generate_password_hash('admin'),
                tipo='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: email=admin@example.com, password=admin")

    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '80'))
    print(f"Servidor em http://{host}:{port}/ (acesse http://localhost/ )")
    app.run(host=host, port=port, debug=True)
