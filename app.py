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
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    db.init_app(app)
    app.register_blueprint(main)
    app.register_blueprint(nutricao)
    app.register_blueprint(pesagem)
    app.register_blueprint(acesso)
    app.register_blueprint(auditoria)

    from audit_service import register_audit_hooks
    register_audit_hooks(app)

    @app.context_processor
    def inject_acesso():
        from flask import session
        user = None
        if session.get('user_id'):
            user = Usuario.query.get(session['user_id'])
        return {'usuario_atual': user}

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
    """Garante colunas senha_hash, usuario e token em usuarios."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        if 'usuarios' not in set(insp.get_table_names()):
            return
        cols = {c['name'] for c in insp.get_columns('usuarios')}
        if 'senha_hash' not in cols:
            if 'senha' in cols:
                db.session.execute(text('ALTER TABLE usuarios CHANGE COLUMN senha senha_hash VARCHAR(255) NOT NULL'))
            else:
                db.session.execute(text("ALTER TABLE usuarios ADD COLUMN senha_hash VARCHAR(255) NOT NULL DEFAULT ''"))
            db.session.commit()
            cols = {c['name'] for c in insp.get_columns('usuarios')}
        if 'usuario' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN usuario VARCHAR(80) NULL'))
            db.session.commit()
        if 'token' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN token VARCHAR(64) NULL'))
            db.session.commit()
        if 'reset_token' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN reset_token VARCHAR(80) NULL'))
            db.session.commit()
        if 'reset_token_expira' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN reset_token_expira DATETIME NULL'))
            db.session.commit()
        for col in ('is_master', 'perm_chamados', 'perm_nutricao', 'perm_pesagem', 'perm_acesso'):
            if col not in cols:
                db.session.execute(text(f'ALTER TABLE usuarios ADD COLUMN {col} TINYINT(1) NOT NULL DEFAULT 0'))
                db.session.commit()
                cols.add(col)
        if 'setor' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN setor VARCHAR(80) NULL'))
            db.session.commit()
            cols.add('setor')
        if 'setor_nutricao' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN setor_nutricao VARCHAR(80) NULL'))
            db.session.commit()
            cols.add('setor_nutricao')
        if 'telefone' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN telefone VARCHAR(20) NULL'))
            db.session.commit()
            cols.add('telefone')
        try:
            db.session.execute(text('ALTER TABLE usuarios MODIFY COLUMN setor VARCHAR(80) NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        # Índice único em usuario (ignora se já existir)
        try:
            db.session.execute(text('CREATE UNIQUE INDEX uq_usuarios_usuario ON usuarios (usuario)'))
            db.session.commit()
        except Exception:
            db.session.rollback()
    except Exception:
        db.session.rollback()


def ensure_chamados_schema():
    """Garante colunas do modelo Chamado (tecnico_id, equipamento, atendimento) e FK de tecnico."""
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
            cols.add('tecnico_id')
        if 'equipamento' not in cols:
            db.session.execute(text('ALTER TABLE chamados ADD COLUMN equipamento VARCHAR(100) NULL'))
            db.session.commit()
            cols.add('equipamento')
        extras = {
            'atendimento_notas': 'TEXT NULL',
            'setor_destino': 'VARCHAR(40) NULL',
            'setor_origem': 'VARCHAR(40) NULL',
            'encaminhamento_instrucoes': 'TEXT NULL',
            'encaminhado_por_id': 'INT NULL',
            'encaminhado_em': 'DATETIME NULL',
            'patrimonio': 'VARCHAR(50) NULL',
            'equipamento_id': 'INT NULL',
            'mesa_id': 'INT NULL',
            'contrato_id': 'INT NULL',
        }
        for col, ddl in extras.items():
            if col not in cols:
                db.session.execute(text(f'ALTER TABLE chamados ADD COLUMN {col} {ddl}'))
                db.session.commit()
                cols.add(col)
        try:
            db.session.execute(text('ALTER TABLE chamados MODIFY COLUMN status VARCHAR(40) NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(text('ALTER TABLE chamados MODIFY COLUMN setor_destino VARCHAR(80) NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(text('ALTER TABLE chamados MODIFY COLUMN setor_origem VARCHAR(80) NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'chamado_fotos' in tables:
            foto_cols = {c['name'] for c in insp.get_columns('chamado_fotos')}
            if 'tipo' not in foto_cols:
                db.session.execute(text(
                    "ALTER TABLE chamado_fotos ADD COLUMN tipo VARCHAR(20) NULL DEFAULT 'conserto'"
                ))
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


def ensure_equipamentos_schema():
    """Garante tabela/colunas de equipamentos (patrimônio vinculado ao cliente)."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'recurso_grupos' not in tables:
            from models import RecursoGrupo
            RecursoGrupo.__table__.create(db.engine, checkfirst=True)
        if 'equipamentos' not in tables:
            return
        cols = {c['name'] for c in insp.get_columns('equipamentos')}
        extras = {
            'setor': 'VARCHAR(100) NULL',
            'cliente_id': 'INT NULL',
            'patrimonio': 'VARCHAR(50) NULL',
            'localizacao': 'VARCHAR(100) NULL',
            'data_compra': 'DATE NULL',
            'ativo': 'TINYINT(1) NOT NULL DEFAULT 1',
            'nome_equipamento': 'VARCHAR(100) NULL',
            'tipo_recurso': "VARCHAR(40) NULL DEFAULT 'Estação'",
            'grupo_id': 'INT NULL',
            'usuario_equipamento': 'VARCHAR(120) NULL',
            'ip': 'VARCHAR(45) NULL',
            'is_agente': 'TINYINT(1) NOT NULL DEFAULT 0',
            'atualizado_em': 'DATETIME NULL',
        }
        for col, ddl in extras.items():
            if col not in cols:
                db.session.execute(text(f'ALTER TABLE equipamentos ADD COLUMN {col} {ddl}'))
                db.session.commit()
                cols.add(col)
        if 'equipamento' in cols and 'nome_equipamento' in cols:
            try:
                db.session.execute(text(
                    'UPDATE equipamentos SET nome_equipamento = equipamento '
                    'WHERE (nome_equipamento IS NULL OR nome_equipamento = \'\') '
                    'AND equipamento IS NOT NULL'
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
        try:
            db.session.execute(text(
                'ALTER TABLE equipamentos ADD CONSTRAINT fk_equipamentos_grupo '
                'FOREIGN KEY (grupo_id) REFERENCES recurso_grupos(id)'
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
        if 'clientes' in tables:
            fks = insp.get_foreign_keys('equipamentos')
            has_fk = any(
                'cliente_id' in (fk.get('constrained_columns') or [])
                and fk.get('referred_table') == 'clientes'
                for fk in fks
            )
            if not has_fk and 'cliente_id' in cols:
                try:
                    db.session.execute(text(
                        'ALTER TABLE equipamentos '
                        'ADD CONSTRAINT fk_equipamentos_cliente '
                        'FOREIGN KEY (cliente_id) REFERENCES clientes(id)'
                    ))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
        if 'chamados' in tables:
            chamado_cols = {c['name'] for c in insp.get_columns('chamados')}
            if 'equipamento_id' in chamado_cols:
                fks = insp.get_foreign_keys('chamados')
                has_eq_fk = any(
                    'equipamento_id' in (fk.get('constrained_columns') or [])
                    and fk.get('referred_table') == 'equipamentos'
                    for fk in fks
                )
                if not has_eq_fk:
                    try:
                        db.session.execute(text(
                            'ALTER TABLE chamados '
                            'ADD CONSTRAINT fk_chamados_equipamento '
                            'FOREIGN KEY (equipamento_id) REFERENCES equipamentos(id)'
                        ))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
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
        if 'email' not in cols:
            alters.append('ADD COLUMN email VARCHAR(120) NULL')
        for clause in alters:
            db.session.execute(text(f'ALTER TABLE clientes {clause}'))
            db.session.commit()
    except Exception:
        db.session.rollback()


def ensure_pesagem_schema():
    """Garante tabela pesagem_clientes e colunas de cliente nas leituras."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'pesagem_leituras' not in tables:
            return
        cols = {c['name'] for c in insp.get_columns('pesagem_leituras')}
        if 'cliente_id' not in cols:
            db.session.execute(text('ALTER TABLE pesagem_leituras ADD COLUMN cliente_id INT NULL'))
            db.session.commit()
            cols.add('cliente_id')
        if 'cliente_nome' not in cols:
            db.session.execute(text('ALTER TABLE pesagem_leituras ADD COLUMN cliente_nome VARCHAR(120) NULL'))
            db.session.commit()
            cols.add('cliente_nome')
    except Exception:
        db.session.rollback()


def ensure_setores_funcao_schema():
    """Cria setores_funcao e semeia os padrões de chamados e nutrição."""
    from sqlalchemy import inspect
    from models import (
        SetorFuncao,
        SETORES_CHAMADO,
        SETORES_NUTRICAO,
        TIPO_SETOR_CHAMADOS,
        TIPO_SETOR_NUTRICAO,
        _fold_setor,
    )
    try:
        insp = inspect(db.engine)
        if 'setores_funcao' not in set(insp.get_table_names()):
            SetorFuncao.__table__.create(db.engine, checkfirst=True)
        seeds = (
            (TIPO_SETOR_CHAMADOS, SETORES_CHAMADO),
            (TIPO_SETOR_NUTRICAO, SETORES_NUTRICAO),
        )
        existentes = SetorFuncao.query.all()
        seen = {(_fold_setor(r.tipo), _fold_setor(r.nome)) for r in existentes}
        for tipo, nomes in seeds:
            for nome in nomes:
                key = (_fold_setor(tipo), _fold_setor(nome))
                if key in seen:
                    continue
                db.session.add(SetorFuncao(tipo=tipo, nome=nome, padrao=True))
                seen.add(key)
        db.session.commit()
    except Exception:
        db.session.rollback()


def ensure_tecnicos_schema():
    """Cria tabelas chamado_setores e chamado_tecnicos e semeia setores padrão."""
    from sqlalchemy import inspect, text
    from models import ChamadoSetor, ChamadoTecnico
    SETORES_PADRAO = ['Informática', 'Edificação', 'Elétrica', 'Máquinas', 'Compras']
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'chamado_setores' not in tables:
            ChamadoSetor.__table__.create(db.engine, checkfirst=True)
        if 'chamado_tecnicos' not in tables:
            ChamadoTecnico.__table__.create(db.engine, checkfirst=True)
        # Add setor_tecnico_id to chamados if missing
        if 'chamados' in tables:
            cols = {c['name'] for c in insp.get_columns('chamados')}
            if 'setor_tecnico_id' not in cols:
                db.session.execute(text('ALTER TABLE chamados ADD COLUMN setor_tecnico_id INT NULL'))
                db.session.commit()
                try:
                    db.session.execute(text(
                        'ALTER TABLE chamados ADD CONSTRAINT fk_chamados_setor_tecnico '
                        'FOREIGN KEY (setor_tecnico_id) REFERENCES chamado_setores(id)'
                    ))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
        # Seed default setores
        for nome in SETORES_PADRAO:
            if not ChamadoSetor.query.filter_by(nome=nome).first():
                db.session.add(ChamadoSetor(nome=nome, ativo=True))
        db.session.commit()
    except Exception:
        db.session.rollback()


def ensure_cameras_schema():
    """Garante tabela chamado_cameras (cadastro de câmeras)."""
    from sqlalchemy import inspect
    from models import ChamadoCamera, ChamadoSetor
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'chamado_setores' not in tables:
            ChamadoSetor.__table__.create(db.engine, checkfirst=True)
        if 'chamado_cameras' not in tables:
            ChamadoCamera.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()


def ensure_portoes_schema():
    """Garante tabela chamado_portoes (cadastro de portões)."""
    from sqlalchemy import inspect
    from models import ChamadoPortao, ChamadoSetor
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'chamado_setores' not in tables:
            ChamadoSetor.__table__.create(db.engine, checkfirst=True)
        if 'chamado_portoes' not in tables:
            ChamadoPortao.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()


def ensure_operacao_chamados_schema():
    """Tabelas e sementes: mesas, SLA, contratos, mensagens, automações, pastas."""
    from sqlalchemy import inspect, text
    from models import (
        MesaServico,
        SlaPrioridade,
        ChamadoAutomacao,
        ConhecimentoPasta,
        MESA_PADRAO,
        PASTA_CONHECIMENTO_PADRAO,
        SLA_PADRAO_HORAS,
        STATUS_ENCAMINHADO,
    )
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'mesas' not in tables:
            MesaServico.__table__.create(db.engine, checkfirst=True)
        if 'sla_prioridades' not in tables:
            SlaPrioridade.__table__.create(db.engine, checkfirst=True)
        if 'contratos' not in tables:
            from models import Contrato
            Contrato.__table__.create(db.engine, checkfirst=True)
        if 'chamado_mensagens' not in tables:
            from models import ChamadoMensagem
            ChamadoMensagem.__table__.create(db.engine, checkfirst=True)
        if 'chamado_automacoes' not in tables:
            ChamadoAutomacao.__table__.create(db.engine, checkfirst=True)
        if 'conhecimento_pastas' not in tables:
            ConhecimentoPasta.__table__.create(db.engine, checkfirst=True)
        insp = inspect(db.engine)
        if 'contratos' in set(insp.get_table_names()):
            ccols = {c['name'] for c in insp.get_columns('contratos')}
            if 'sla_atendimento_horas' not in ccols:
                db.session.execute(text('ALTER TABLE contratos ADD COLUMN sla_atendimento_horas INT NULL'))
                db.session.commit()
            if 'sla_solucao_horas' not in ccols:
                db.session.execute(text('ALTER TABLE contratos ADD COLUMN sla_solucao_horas INT NULL'))
                db.session.commit()
        if 'chamados' in set(insp.get_table_names()):
            cols = {c['name'] for c in insp.get_columns('chamados')}
            if 'mesa_id' not in cols:
                db.session.execute(text('ALTER TABLE chamados ADD COLUMN mesa_id INT NULL'))
                db.session.commit()
            if 'contrato_id' not in cols:
                db.session.execute(text('ALTER TABLE chamados ADD COLUMN contrato_id INT NULL'))
                db.session.commit()
            try:
                db.session.execute(text(
                    'ALTER TABLE chamados ADD CONSTRAINT fk_chamados_mesa '
                    'FOREIGN KEY (mesa_id) REFERENCES mesas(id)'
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
            try:
                db.session.execute(text(
                    'ALTER TABLE chamados ADD CONSTRAINT fk_chamados_contrato '
                    'FOREIGN KEY (contrato_id) REFERENCES contratos(id)'
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
        if not MesaServico.query.filter_by(nome=MESA_PADRAO).first():
            db.session.add(MesaServico(nome=MESA_PADRAO, ativa=True))
            db.session.flush()
        suporte = MesaServico.query.filter_by(nome=MESA_PADRAO).first()
        if suporte:
            try:
                db.session.execute(
                    text('UPDATE chamados SET mesa_id = :mid WHERE mesa_id IS NULL'),
                    {'mid': suporte.id},
                )
            except Exception:
                db.session.rollback()
        for pri, horas in (('Alta', (4, 8)), ('Normal', (8, 24)), ('Baixa', (24, 72))):
            row = SlaPrioridade.query.filter_by(prioridade=pri).first()
            if not row:
                db.session.add(SlaPrioridade(
                    prioridade=pri,
                    prazo_atendimento_horas=horas[0],
                    prazo_solucao_horas=horas[1],
                ))
        if not ConhecimentoPasta.query.filter_by(nome=PASTA_CONHECIMENTO_PADRAO).first():
            db.session.add(ConhecimentoPasta(nome=PASTA_CONHECIMENTO_PADRAO))
        if not ChamadoAutomacao.query.first():
            db.session.add(ChamadoAutomacao(
                nome='Prioridade Alta — nota na abertura',
                gatilho='criar',
                prioridade_quando='Alta',
                acao='mensagem',
                mensagem_padrao='Ticket de prioridade Alta. Atenção ao SLA de atendimento e solução.',
                ativa=True,
            ))
            db.session.add(ChamadoAutomacao(
                nome='Encaminhado — nota na timeline',
                gatilho='status',
                status_quando=STATUS_ENCAMINHADO,
                acao='mensagem',
                mensagem_padrao='Ticket encaminhado. Acompanhe o setor de destino.',
                ativa=True,
            ))
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
        ensure_equipamentos_schema()
        ensure_pesagem_schema()
        ensure_setores_funcao_schema()
        ensure_operacao_chamados_schema()
        ensure_tecnicos_schema()
        ensure_cameras_schema()
        ensure_portoes_schema()
        from nutricao_service import seed_nutricao
        from routes_pesagem import seed_pesagem
        from routes_acesso import seed_acesso
        from audit_service import ensure_audit_table
        seed_nutricao()
        seed_pesagem()
        seed_acesso()
        ensure_audit_table()
        try:
            from permissions_sistemas import garantir_acesso_master
            garantir_acesso_master()
        except Exception as exc:
            print(f"Aviso ao criar acesso master: {exc}")
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
    port = 80
    https_port = int(os.environ.get('HTTPS_PORT', '443'))
    enable_https = os.environ.get('ENABLE_HTTPS', '1').strip().lower() not in ('0', 'false', 'no')

    if enable_https:
        run_http_and_https(app, host=host, http_port=port, https_port=https_port)
    else:
        print(f"Servidor em http://{host}:{port}/ (acesse http://localhost/ )")
        app.run(host=host, port=port, debug=True, use_reloader=False, threaded=True)
