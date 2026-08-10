from flask import Flask
from routes import main
from routes_nutricao import nutricao
from routes_pesagem import pesagem
from routes_acesso import acesso
from routes_audit import auditoria
from models import db, Usuario
from db_config import SQLALCHEMY_DATABASE_URI
import models_nutricao  # noqa: F401 — registra tabelas de nutrição
import models_pesagem  # noqa: F401 — registra tabelas de pesagem
import models_acesso  # noqa: F401 — registra tabelas de controle de acesso
import models_audit  # noqa: F401 — registra tabelas de auditoria
import os
import socket
import threading


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'saogeraldo2025')
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Dual HTTP/HTTPS: cookies must work on both (do not force Secure-only).
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['REMEMBER_COOKIE_SECURE'] = False

    db.init_app(app)
    app.register_blueprint(main)
    app.register_blueprint(nutricao)
    app.register_blueprint(pesagem)
    app.register_blueprint(acesso)
    app.register_blueprint(auditoria)

    from audit_service import register_audit_hooks
    register_audit_hooks(app)

    return app


def _port_available(host: str, port: int) -> bool:
    """Return True if we can bind host:port (then immediately release it)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _resolve_https_port(host: str, preferred: int, fallback: int = 8443) -> int:
    if _port_available(host, preferred):
        return preferred
    if preferred != fallback and _port_available(host, fallback):
        print(
            f"AVISO: porta HTTPS {preferred} indisponível "
            f"(permissão de admin ou em uso). Usando {fallback}."
        )
        return fallback
    print(
        f"AVISO: não foi possível reservar HTTPS em {preferred} nem {fallback}; "
        f"tentando {preferred} mesmo assim."
    )
    return preferred


def run_http_and_https(app, host: str, http_port: int, https_port: int):
    """Serve HTTP on the main thread and HTTPS in a background thread."""
    from generate_certs import generate_self_signed_certs

    cert_file, key_file = generate_self_signed_certs()
    https_port = _resolve_https_port(host, https_port)

    def _serve_https():
        try:
            app.run(
                host=host,
                port=https_port,
                ssl_context=(cert_file, key_file),
                debug=False,
                use_reloader=False,
                threaded=True,
            )
        except OSError as exc:
            print(f"Falha ao iniciar HTTPS em {host}:{https_port}: {exc}")

    threading.Thread(target=_serve_https, name='flask-https', daemon=True).start()

    http_display = f"http://127.0.0.1:{http_port}/" if http_port != 80 else "http://127.0.0.1/"
    https_display = (
        f"https://127.0.0.1:{https_port}/" if https_port != 443 else "https://127.0.0.1/"
    )
    print(f"HTTP:  {http_display}  (bind {host}:{http_port})")
    print(f"HTTPS: {https_display}  (bind {host}:{https_port}, cert {cert_file})")
    print(
        "Nota: cert autoassinado. Sem trust no Windows, o Chrome/Edge avisa "
        "(rode trust_local_cert.ps1 ou: python generate_certs.py --trust; reinicie o navegador)."
    )

    # Reloader would spawn a second process and break the HTTPS thread.
    app.run(host=host, port=http_port, debug=True, use_reloader=False, threaded=True)


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
    from password_utils import generate_password_hash

    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_usuarios_schema()
        ensure_clientes_schema()
        ensure_chamados_schema()
        from nutricao_service import seed_nutricao
        from routes_pesagem import seed_pesagem
        from routes_acesso import seed_acesso
        from audit_service import ensure_audit_table
        seed_nutricao()
        seed_pesagem()
        seed_acesso()
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
    https_port = int(os.environ.get('HTTPS_PORT', '443'))
    enable_https = os.environ.get('ENABLE_HTTPS', '1').strip().lower() not in ('0', 'false', 'no')

    if enable_https:
        run_http_and_https(app, host=host, http_port=port, https_port=https_port)
    else:
        print(f"Servidor em http://{host}:{port}/ (acesse http://localhost/ )")
        app.run(host=host, port=port, debug=True, use_reloader=False, threaded=True)
