"""Rotas do Sistema de Controle de Acesso — São Geraldo Service."""
from __future__ import annotations

from functools import wraps
from datetime import datetime, date, time, timedelta
import csv
import io
import json
import logging
import os
import secrets
import re
import uuid
from pathlib import Path

from flask import (
    Blueprint, render_template, request, jsonify, redirect,
    url_for, flash, session, Response, send_file,
)
from sqlalchemy import func, or_, inspect, text
from werkzeug.utils import secure_filename

from models import db, Usuario
from password_utils import generate_password_hash
import controlid_client as cid
from models_acesso import (
    AcessoGrupo, AcessoHorario, AcessoEquipamento,
    AcessoPessoa, AcessoVisitante, AcessoEvento, AcessoAmbiente,
    AcessoAmbienteEquipamento,
    AcessoEstacionamento, AcessoEstacionamentoEquipamento, AcessoEstacionamentoPermissao,
    AcessoEmpresa, AcessoClassificacao, AcessoDepartamento,
    AcessoSetor, AcessoCentroCusto, AcessoLocal, AcessoTipoDocumento,
    AcessoPessoaDocumento,
    AcessoUsuarioPermissao, AcessoPerfilPermissao,
    AcessoBackupLog, AcessoBackupConfig, AcessoRefeicao,
    AcessoControleAdicional, AcessoEscala,
    AcessoGrupoRefeicao, AcessoItemRefeicao, AcessoVinculoRefeicao,
    AcessoVeiculo, AcessoVeiculoEvento,
    AcessoImpressora,
)

acesso = Blueprint('acesso', __name__, template_folder='templates_acesso')
LOG = logging.getLogger(__name__)

TIPO_LABELS = {
    'admin': 'admin',
    'agente': 'Agente',
    'operador': 'Operador',
    'consulta': 'Consulta',
}


def _normalize_tipo(value, default='agente'):
    tipo = (value or default).strip().lower()
    aliases = {
        'administrador': 'admin',
        'administrator': 'admin',
        'agent': 'agente',
    }
    tipo = aliases.get(tipo, tipo)
    if tipo not in TIPO_LABELS:
        return default
    return tipo


def _generate_user_token():
    return secrets.token_hex(16)


def _login_from_email(email):
    email = (email or '').strip()
    if not email:
        return ''
    return email.split('@', 1)[0].strip().lower()


def _email_from_usuario(usuario):
    usuario = (usuario or '').strip().lower()
    if not usuario:
        return ''
    if '@' in usuario:
        return usuario
    safe = re.sub(r'[^a-z0-9._+-]+', '', usuario) or 'user'
    return f'{safe}@acesso.local'


def _ensure_usuario_login_fields(u):
    """Preenche usuario/token faltantes sem alterar login por e-mail."""
    changed = False
    if not (getattr(u, 'usuario', None) or '').strip():
        login = _login_from_email(u.email)
        if login:
            base = login
            candidate = base
            n = 1
            while Usuario.query.filter(Usuario.usuario == candidate, Usuario.id != u.id).first():
                n += 1
                candidate = f'{base}{n}'
            u.usuario = candidate
            changed = True
    if not (getattr(u, 'token', None) or '').strip():
        u.token = _generate_user_token()
        changed = True
    return changed

ACESSO_MATRIZ_PERMISSOES = {
    'Pessoas': [
        {'chave': 'pessoas.cadastros', 'label': 'Cadastros', 'icone': 'fa-id-card'},
        {'chave': 'pessoas.escalas', 'label': 'Escalas', 'icone': 'fa-calendar-days'},
        {'chave': 'pessoas.veiculos', 'label': 'Veículos', 'icone': 'fa-car'},
        {'chave': 'pessoas.visitantes', 'label': 'Visitantes', 'icone': 'fa-user-clock'},
        {'chave': 'pessoas.empresas', 'label': 'Empresas', 'icone': 'fa-building'},
    ],
    'Hierarquia': [
        {'chave': 'hierarquia.classificacoes', 'label': 'Classificações', 'icone': 'fa-tags'},
        {'chave': 'hierarquia.cadastros_diversos', 'label': 'Cadastros Diversos', 'icone': 'fa-sitemap'},
    ],
    'Controle de Acesso': [
        {'chave': 'acesso.equipamentos', 'label': 'Equipamentos', 'icone': 'fa-microchip'},
        {'chave': 'acesso.grupos', 'label': 'Horários & Grupos', 'icone': 'fa-clock'},
        {'chave': 'acesso.ambientes', 'label': 'Gestão de Ambientes', 'icone': 'fa-building'},
        {'chave': 'acesso.estacionamentos', 'label': 'Gestão de Estacionamentos', 'icone': 'fa-square-parking'},
        {'chave': 'acesso.operacoes', 'label': 'Operações', 'icone': 'fa-gears'},
        {'chave': 'acesso.limpeza_dados', 'label': 'Limpeza de Dados', 'icone': 'fa-broom'},
        {'chave': 'acesso.sincronizar_offline', 'label': 'Sincronizar Offline', 'icone': 'fa-cloud-arrow-down'},
        {'chave': 'acesso.status_portas', 'label': 'Status das Portas', 'icone': 'fa-door-open'},
        {'chave': 'acesso.impressoras', 'label': 'Impressoras', 'icone': 'fa-print'},
    ],
    'Parâmetros': [
        {'chave': 'parametros.controle_adicional', 'label': 'Controle Adicional', 'icone': 'fa-sliders'},
        {'chave': 'parametros.refeicoes', 'label': 'Refeições', 'icone': 'fa-utensils'},
        {'chave': 'parametros.documentos', 'label': 'Documentos', 'icone': 'fa-file-lines'},
    ],
    'Relatórios': [
        {'chave': 'relatorios.dashboard', 'label': 'Dashboard', 'icone': 'fa-gauge-high'},
        {'chave': 'relatorios.acessos', 'label': 'Acessos', 'icone': 'fa-right-left'},
        {'chave': 'relatorios.veiculos', 'label': 'Veículos', 'icone': 'fa-car-side'},
        {'chave': 'relatorios.refeicoes', 'label': 'Refeições', 'icone': 'fa-utensils'},
        {'chave': 'relatorios.permanencia', 'label': 'Permanência', 'icone': 'fa-hourglass-half'},
        {'chave': 'relatorios.auditoria', 'label': 'Auditoria', 'icone': 'fa-clipboard-check'},
    ],
    'Administração': [
        {'chave': 'admin.usuarios', 'label': 'Usuários', 'icone': 'fa-users'},
        {'chave': 'admin.permissoes', 'label': 'Permissões', 'icone': 'fa-key'},
        {'chave': 'admin.backup', 'label': 'Backup do Sistema', 'icone': 'fa-database'},
    ],
}


def _matriz_chaves_permitidas():
    return {
        item['chave']
        for itens in ACESSO_MATRIZ_PERMISSOES.values()
        for item in itens
    }


def _perfil_permissoes(perfil):
    return [
        p.chave for p in AcessoPerfilPermissao.query.filter_by(perfil=perfil).all()
    ]

BACKUP_DIR = Path(__file__).resolve().parent / 'static' / 'acesso_backups'
DOCUMENTOS_DIR = Path(__file__).resolve().parent / 'static' / 'acesso_documentos'
DOCUMENTOS_ALLOWED_EXT = {
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp',
    '.doc', '.docx', '.xls', '.xlsx', '.txt',
}


def _usuario_to_dict(u):
    tipo = _normalize_tipo(u.tipo, default='operador')
    login = (getattr(u, 'usuario', None) or '').strip() or _login_from_email(u.email)
    nome = u.nome or '?'
    inicial = (nome.strip()[:1] or '?').upper()
    return {
        'id': u.id,
        'nome': u.nome,
        'email': u.email,
        'usuario': login,
        'tipo': tipo,
        'tipo_label': TIPO_LABELS.get(tipo, tipo),
        'token': getattr(u, 'token', None) or '',
        'ativo': bool(u.ativo),
        'inicial': inicial,
        'data_criacao': u.data_criacao.strftime('%d/%m/%Y %H:%M') if u.data_criacao else '',
    }


def _fmt_bytes(n):
    n = int(n or 0)
    if n < 1024:
        return f'{n} B'
    if n < 1024 * 1024:
        return f'{n / 1024:.1f} KB'
    return f'{n / (1024 * 1024):.2f} MB'


def _serialize_row(row):
    data = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, datetime):
            data[col.name] = val.isoformat(sep=' ', timespec='seconds')
        elif isinstance(val, date) and not isinstance(val, datetime):
            data[col.name] = val.isoformat()
        elif isinstance(val, time):
            data[col.name] = val.strftime('%H:%M:%S')
        else:
            data[col.name] = val
    return data


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _parse_time(value):
    if not value:
        return None
    text_v = str(value).strip()
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(text_v, fmt).time()
        except ValueError:
            continue
    return None


def _horario_from_item(grupo_id, item):
    """Monta AcessoHorario a partir de um dict de variação."""
    if not isinstance(item, dict):
        item = {}
    dia = (item.get('dia_semana') or 'TODOS').strip().upper() or 'TODOS'
    hi = _parse_time(item.get('hora_inicial')) or time(0, 0)
    hf = _parse_time(item.get('hora_final')) or time(23, 59)
    entradas = _parse_int(item.get('entradas'))
    saidas = _parse_int(item.get('saidas'))
    return AcessoHorario(
        grupo_id=grupo_id,
        dia_semana=dia,
        hora_inicial=hi,
        hora_final=hf,
        entradas=entradas if entradas is not None and entradas >= 0 else 1,
        saidas=saidas if saidas is not None and saidas >= 0 else 1,
        livre=_parse_bool(item.get('livre'), default=True),
        por_equipamento=_parse_bool(item.get('por_equipamento'), default=False),
    )


def _grupo_payload(grupo):
    d = grupo.to_dict()
    d['equipamento_ids'] = [e.id for e in grupo.equipamentos]
    d['horarios'] = [h.to_dict() for h in grupo.horarios]
    return d


def _parse_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'on', 'yes', 'sim')


def _controlid_server_host_port(data=None):
    """Host/porta do servidor de monitor (env, request ou request.host)."""
    data = data or {}
    host = (
        (data.get('host') or '').strip()
        or os.environ.get('CONTROLID_SERVER_HOST', '').strip()
        or (request.host.split(':')[0] if request and request.host else '')
        or '127.0.0.1'
    )
    porta_raw = data.get('porta') or data.get('port') or os.environ.get('CONTROLID_SERVER_PORT')
    if porta_raw in (None, ''):
        try:
            porta = int(os.environ.get('PORT', '80') or 80)
        except ValueError:
            porta = 80
    else:
        try:
            porta = int(porta_raw)
        except (TypeError, ValueError):
            porta = 80
    path = (data.get('path') or os.environ.get('CONTROLID_MONITOR_PATH') or cid.MONITOR_PATH).strip()
    return host, porta, path


def _controlid_mark_online(eq, online=True, device_id=None):
    eq.online = bool(online)
    eq.last_alive = datetime.utcnow()
    if device_id is not None and str(device_id).strip():
        eq.device_id = str(device_id).strip()


def _controlid_eqs_alvo(equipamento_id=None, ids=None, only_online=False, only_ativo=True):
    q = AcessoEquipamento.query
    if only_ativo:
        q = q.filter(AcessoEquipamento.ativo.is_(True))
    if ids:
        q = q.filter(AcessoEquipamento.id.in_(list(ids)))
    elif equipamento_id:
        q = q.filter(AcessoEquipamento.id == int(equipamento_id))
    elif only_online:
        q = q.filter(AcessoEquipamento.online.is_(True))
    return [e for e in q.order_by(AcessoEquipamento.nome).all() if (e.ip or '').strip()]


def _controlid_direction_for_eq(eq, row=None):
    giro = (eq.controle_giro or '').strip().lower()
    if giro.startswith('somente entrada'):
        return 'Entrada'
    if giro.startswith('somente saida') or giro.startswith('somente saída'):
        return 'Saída'
    return 'Entrada'


def _controlid_resolve_pessoa(user_id_str):
    uid = str(user_id_str or '').strip()
    if not uid or uid == '0':
        return None, 'Não identificado', 'PESSOA'
    p = AcessoPessoa.query.filter_by(matricula=uid).first()
    if p:
        return p.matricula, p.nome, 'PESSOA'
    v = AcessoVisitante.query.filter(
        or_(AcessoVisitante.visitor_id == uid, AcessoVisitante.documento == uid)
    ).first()
    if v:
        return (v.visitor_id or uid), v.nome, 'VISITANTE'
    return uid, f'ID {uid}', 'PESSOA'


def _controlid_push_pessoa(eq, pessoa, enviar_fotos=True):
    """Envia uma pessoa para o equipamento (user + cartão + foto)."""
    creds = cid.creds_from_equipamento(eq)
    matricula = str(pessoa.matricula or '').strip()
    if not matricula:
        raise cid.ControlIDError(f'Pessoa {pessoa.id} sem matrícula')
    user_id = int(matricula) if matricula.isdigit() else None
    result = cid.upsert_user(
        creds,
        user_id=user_id,
        name=pessoa.nome,
        registration=matricula,
    )
    device_uid = result.get('user_id') or user_id
    if device_uid is None and matricula.isdigit():
        device_uid = int(matricula)
    out = {'user': result, 'card': None, 'foto': None}
    if pessoa.cartao and device_uid is not None:
        try:
            out['card'] = cid.upsert_card(creds, int(device_uid), pessoa.cartao)
        except cid.ControlIDError as exc:
            out['card'] = {'ok': False, 'error': str(exc)}
    if enviar_fotos and pessoa.foto and device_uid is not None:
        img = cid.load_image_bytes(pessoa.foto)
        if img:
            try:
                out['foto'] = cid.set_user_image(creds, int(device_uid), img)
            except cid.ControlIDError as exc:
                out['foto'] = {'ok': False, 'error': str(exc)}
        else:
            out['foto'] = {'ok': False, 'error': 'foto não encontrada'}
    return out


def ensure_acesso_schema():
    """Cria tabelas novas e colunas extras em acesso_pessoas (MySQL)."""
    try:
        db.create_all()
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())

        if 'acesso_horarios' in tables:
            hcols = {c['name'] for c in insp.get_columns('acesso_horarios')}
            halters = []
            hspecs = {
                'entradas': 'INT NOT NULL DEFAULT 1',
                'saidas': 'INT NOT NULL DEFAULT 1',
                'livre': 'TINYINT(1) NOT NULL DEFAULT 1',
                'por_equipamento': 'TINYINT(1) NOT NULL DEFAULT 0',
            }
            for name, ddl in hspecs.items():
                if name not in hcols:
                    halters.append(f'ADD COLUMN `{name}` {ddl}')
            if halters:
                db.session.execute(text(
                    f"ALTER TABLE acesso_horarios {', '.join(halters)}"
                ))
                db.session.commit()

        if 'acesso_grupos_refeicao' in tables:
            gcols = {c['name'] for c in insp.get_columns('acesso_grupos_refeicao')}
            galters = []
            gspecs = {
                'tipo_cobranca': "VARCHAR(40) NOT NULL DEFAULT 'MENSAL'",
                'observacoes': 'TEXT NULL',
                'exibir_visitantes': 'TINYINT(1) NOT NULL DEFAULT 0',
                'ativo': 'TINYINT(1) NOT NULL DEFAULT 1',
            }
            for name, ddl in gspecs.items():
                if name not in gcols:
                    galters.append(f'ADD COLUMN `{name}` {ddl}')
            if galters:
                db.session.execute(text(
                    f"ALTER TABLE acesso_grupos_refeicao {', '.join(galters)}"
                ))
                db.session.commit()
            has_obs = 'observacoes' in gcols or any('`observacoes`' in a for a in galters)
            if 'descricao' in gcols and has_obs:
                try:
                    db.session.execute(text(
                        "UPDATE acesso_grupos_refeicao SET observacoes = descricao "
                        "WHERE (observacoes IS NULL OR observacoes='') "
                        "AND descricao IS NOT NULL AND descricao<>''"
                    ))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        if 'acesso_itens_refeicao' in tables:
            icols = {c['name'] for c in insp.get_columns('acesso_itens_refeicao')}
            ialters = []
            ispecs = {
                'hora_inicio': 'TIME NULL',
                'hora_fim': 'TIME NULL',
                'ativo': 'TINYINT(1) NOT NULL DEFAULT 1',
            }
            for name, ddl in ispecs.items():
                if name not in icols:
                    ialters.append(f'ADD COLUMN `{name}` {ddl}')
            if ialters:
                db.session.execute(text(
                    f"ALTER TABLE acesso_itens_refeicao {', '.join(ialters)}"
                ))
                db.session.commit()

        if 'acesso_pessoas' not in tables:
            return
        cols = {c['name'] for c in insp.get_columns('acesso_pessoas')}
        alters = []
        specs = {
            'empresa_id': 'INT NULL',
            'classificacao_id': 'INT NULL',
            'departamento_id': 'INT NULL',
            'setor_id': 'INT NULL',
            'centro_custo_id': 'INT NULL',
            'status': "VARCHAR(20) NULL DEFAULT 'Ativo'",
            'foto': 'LONGTEXT NULL',
            'hora_inicial': 'TIME NULL',
            'hora_final': 'TIME NULL',
            'tipo_cartao': "VARCHAR(20) NULL DEFAULT 'wiegand'",
            'token': 'VARCHAR(100) NULL',
            'equipamentos_ids': 'VARCHAR(255) NULL',
        }
        for name, ddl in specs.items():
            if name not in cols:
                alters.append(f'ADD COLUMN `{name}` {ddl}')
        if alters:
            db.session.execute(text(f"ALTER TABLE acesso_pessoas {', '.join(alters)}"))
            db.session.commit()
        # data-URL de foto não cabe em VARCHAR(255)
        try:
            db.session.execute(text(
                'ALTER TABLE acesso_pessoas MODIFY COLUMN `foto` LONGTEXT NULL'
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
        # sincroniza status a partir de ativo legado
        db.session.execute(text(
            "UPDATE acesso_pessoas SET status='Ativo' "
            "WHERE (status IS NULL OR status='') AND (ativo=1 OR ativo IS NULL)"
        ))
        db.session.execute(text(
            "UPDATE acesso_pessoas SET status='Inativo' "
            "WHERE (status IS NULL OR status='') AND ativo=0"
        ))
        db.session.commit()

        if 'acesso_visitantes' in set(insp.get_table_names()):
            vcols = {c['name'] for c in insp.get_columns('acesso_visitantes')}
            vspecs = {
                'tipo_documento': "VARCHAR(40) NULL DEFAULT 'CPF'",
                'rg': 'VARCHAR(20) NULL',
                'empresa_id': 'INT NULL',
                'classificacao_id': 'INT NULL',
                'anfitriao': 'VARCHAR(120) NULL',
                'tipo_cartao': "VARCHAR(20) NULL DEFAULT 'wiegand'",
                'token': 'VARCHAR(100) NULL',
                'foto': 'LONGTEXT NULL',
                'equipamento_id': 'INT NULL',
                'local_acesso': 'VARCHAR(120) NULL',
                'ident_modo': "VARCHAR(20) NULL DEFAULT 'foto'",
                'refeicao': 'TINYINT(1) NULL DEFAULT 0',
                'refeicao_creditos': 'INT NULL DEFAULT 0',
                'imprimir_ao_salvar': 'TINYINT(1) NULL DEFAULT 0',
                'baixar_qr_ao_salvar': 'TINYINT(1) NULL DEFAULT 0',
                'impressora': 'VARCHAR(80) NULL',
                'modelo_impressao': 'VARCHAR(80) NULL',
            }
            valters = []
            for name, ddl in vspecs.items():
                if name not in vcols:
                    valters.append(f'ADD COLUMN `{name}` {ddl}')
            if valters:
                db.session.execute(text(f"ALTER TABLE acesso_visitantes {', '.join(valters)}"))
                db.session.commit()

        if 'acesso_pessoa_documentos' in set(insp.get_table_names()):
            dcols = {c['name'] for c in insp.get_columns('acesso_pessoa_documentos')}
            if 'arquivo' not in dcols:
                db.session.execute(text(
                    'ALTER TABLE acesso_pessoa_documentos '
                    'ADD COLUMN `arquivo` VARCHAR(255) NULL'
                ))
                db.session.commit()

        if 'acesso_ambientes' in set(insp.get_table_names()):
            acols = {c['name'] for c in insp.get_columns('acesso_ambientes')}
            aspecs = {
                'vigencia_tipo': "VARCHAR(20) NULL DEFAULT 'definitivo'",
                'data_fim': 'DATE NULL',
                'publico': 'VARCHAR(255) NULL',
                'data_criacao': 'DATETIME NULL',
            }
            aalters = []
            for name, ddl in aspecs.items():
                if name not in acols:
                    aalters.append(f'ADD COLUMN `{name}` {ddl}')
            if aalters:
                db.session.execute(text(
                    f"ALTER TABLE acesso_ambientes {', '.join(aalters)}"
                ))
                db.session.commit()
            # descricao legado VARCHAR → TEXT (best-effort)
            try:
                db.session.execute(text(
                    'ALTER TABLE acesso_ambientes MODIFY COLUMN `descricao` TEXT NULL'
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()

        if 'acesso_classificacoes' in set(insp.get_table_names()):
            ccols = {c['name'] for c in insp.get_columns('acesso_classificacoes')}
            calters = []
            if 'mostrar_visitante' not in ccols:
                calters.append('ADD COLUMN `mostrar_visitante` TINYINT(1) NOT NULL DEFAULT 0')
            if 'perfil_fixo' not in ccols:
                calters.append('ADD COLUMN `perfil_fixo` VARCHAR(40) NULL')
            if calters:
                db.session.execute(text(
                    f"ALTER TABLE acesso_classificacoes {', '.join(calters)}"
                ))
                db.session.commit()

        # Escalas: colunas do ciclo/horário (migração leve se tabela já existia)
        if 'acesso_escalas' in set(insp.get_table_names()):
            ecols = {c['name'] for c in insp.get_columns('acesso_escalas')}
            especs = {
                'nome_pessoa': "VARCHAR(120) NOT NULL DEFAULT ''",
                'tipo': "VARCHAR(40) NOT NULL DEFAULT '5x2'",
                'dias_trabalho': 'INT NOT NULL DEFAULT 5',
                'dias_folga': 'INT NOT NULL DEFAULT 2',
                'hora_entrada': 'TIME NULL',
                'hora_saida': 'TIME NULL',
                'ativo': 'TINYINT(1) NOT NULL DEFAULT 1',
                'data_criacao': 'DATETIME NULL',
            }
            ealters = []
            for name, ddl in especs.items():
                if name not in ecols:
                    ealters.append(f'ADD COLUMN `{name}` {ddl}')
            if ealters:
                db.session.execute(text(
                    f"ALTER TABLE acesso_escalas {', '.join(ealters)}"
                ))
                db.session.commit()

        # Empresas: logo para listagem / relatórios
        if 'acesso_empresas' in set(insp.get_table_names()):
            emp_cols = {c['name'] for c in insp.get_columns('acesso_empresas')}
            if 'logo_path' not in emp_cols:
                db.session.execute(text(
                    'ALTER TABLE acesso_empresas ADD COLUMN `logo_path` VARCHAR(255) NULL'
                ))
                db.session.commit()
    except Exception:
        db.session.rollback()


def _seed_lookup(model, field, values):
    for value in values:
        exists = model.query.filter(getattr(model, field) == value).first()
        if not exists:
            db.session.add(model(**{field: value}))


def ensure_usuarios_acesso_schema():
    """Garante colunas usuario/token em usuarios (sem circular import com app)."""
    try:
        insp = inspect(db.engine)
        if 'usuarios' not in set(insp.get_table_names()):
            return
        cols = {c['name'] for c in insp.get_columns('usuarios')}
        if 'usuario' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN usuario VARCHAR(80) NULL'))
            db.session.commit()
        if 'token' not in cols:
            db.session.execute(text('ALTER TABLE usuarios ADD COLUMN token VARCHAR(64) NULL'))
            db.session.commit()
        try:
            db.session.execute(text('CREATE UNIQUE INDEX uq_usuarios_usuario ON usuarios (usuario)'))
            db.session.commit()
        except Exception:
            db.session.rollback()
    except Exception:
        db.session.rollback()


def seed_acesso():
    """Dados iniciais do módulo de Controle de Acesso."""
    ensure_acesso_schema()
    ensure_usuarios_acesso_schema()
    try:
        changed = False
        for u in Usuario.query.all():
            if _ensure_usuario_login_fields(u):
                changed = True
        if changed:
            db.session.commit()
    except Exception:
        db.session.rollback()

    if AcessoEmpresa.query.count() == 0:
        db.session.add(AcessoEmpresa(nome='São Geraldo Service', cnpj=''))

    _seed_lookup(AcessoClassificacao, 'descricao', [
        'Funcionários', 'Visitantes', 'Colaborador', 'Terceirizado', 'Estagiário', 'Livre',
    ])
    _seed_lookup(AcessoDepartamento, 'descricao', [
        'Operações', 'Administrativo', 'Manutenção', 'Nutrição',
    ])
    _seed_lookup(AcessoSetor, 'descricao', [
        'Acesso', 'Recepção', 'TI', 'Cozinha',
    ])
    _seed_lookup(AcessoCentroCusto, 'descricao', [
        'Geral', 'Hospital', 'Administração',
    ])
    _seed_lookup(AcessoLocal, 'descricao', [
        'Recepção', 'Portaria', 'Refeitório', 'Escritório', 'Fábrica', 'Portão Principal',
    ])

    if AcessoTipoDocumento.query.count() == 0:
        db.session.add_all([
            AcessoTipoDocumento(descricao='CPF', digitos=11),
            AcessoTipoDocumento(descricao='RG', digitos=0),
            AcessoTipoDocumento(descricao='Passaporte', digitos=0),
            AcessoTipoDocumento(descricao='CNH', digitos=11),
        ])

    if AcessoGrupo.query.count() == 0:
        padrao = AcessoGrupo(
            nome='Acesso Geral',
            descricao='Grupo padrão com liberação em todos os equipamentos.',
            ativo=True,
        )
        visitantes = AcessoGrupo(
            nome='Visitantes',
            descricao='Acesso temporário para visitantes.',
            ativo=True,
        )
        db.session.add_all([padrao, visitantes])
        db.session.flush()
        db.session.add(AcessoHorario(
            grupo_id=padrao.id,
            dia_semana='TODOS',
            hora_inicial=time(0, 0),
            hora_final=time(23, 59),
        ))
        db.session.add(AcessoHorario(
            grupo_id=visitantes.id,
            dia_semana='TODOS',
            hora_inicial=time(7, 0),
            hora_final=time(19, 0),
        ))

    agora = datetime.utcnow()
    equipamentos_seed = [
        ('Recepção', '192.168.0.237', 'DEV-REC', True, 'Ambos os lados', 'iDFace'),
        ('Fabrica', '192.168.0.234', 'DEV-FAB', True, 'Ambos os lados', 'iDFace'),
        ('Escritorio', '192.168.0.247', 'DEV-ESC', False, 'Somente Entrada', 'iDFlex'),
        ('Portão Principal', '192.168.0.246', 'DEV-POR', False, 'Ambos os lados', 'iDBlock'),
        ('Portaria', '192.168.0.239', 'DEV-PTA', False, 'Ambos os lados', 'iDFace'),
        ('Refeitorio', '192.168.0.233', 'DEV-REF', False, 'Entrada/Saida', 'iDFace'),
    ]
    for nome, ip, device_id, online, giro, modelo in equipamentos_seed:
        eq = AcessoEquipamento.query.filter(
            or_(AcessoEquipamento.device_id == device_id, AcessoEquipamento.nome == nome)
        ).first()
        if not eq:
            db.session.add(AcessoEquipamento(
                nome=nome, marca='Control iD', modelo=modelo, ip=ip, device_id=device_id,
                controle_giro=giro, local=nome, online=online,
                last_alive=agora if online else None, ativo=True,
            ))
        else:
            eq.ip = eq.ip or ip
            eq.online = online if eq.last_alive is None else eq.online
            if online and not eq.last_alive:
                eq.last_alive = agora

    if AcessoAmbiente.query.count() == 0:
        db.session.add_all([
            AcessoAmbiente(nome='Refeitório', descricao='Área de refeições', capacidade_maxima=120, ocupacao_atual=34, ativo=True),
            AcessoAmbiente(nome='Auditorio', descricao='Eventos e treinamentos', capacidade_maxima=80, ocupacao_atual=12, ativo=True),
            AcessoAmbiente(nome='Área VIP', descricao='Acesso restrito', capacidade_maxima=20, ocupacao_atual=5, ativo=True),
        ])

    if AcessoPessoa.query.count() == 0:
        grupo = AcessoGrupo.query.filter_by(nome='Acesso Geral').first()
        emp = AcessoEmpresa.query.first()
        clas = AcessoClassificacao.query.filter_by(descricao='Colaborador').first()
        dep = AcessoDepartamento.query.filter_by(descricao='Operações').first()
        setr = AcessoSetor.query.filter_by(descricao='Acesso').first()
        cc = AcessoCentroCusto.query.filter_by(descricao='Geral').first()
        pessoa = AcessoPessoa(
            matricula='1001',
            nome='COLABORADOR DEMO',
            cartao='123456',
            empresa_id=emp.id if emp else None,
            classificacao_id=clas.id if clas else None,
            departamento_id=dep.id if dep else None,
            setor_id=setr.id if setr else None,
            centro_custo_id=cc.id if cc else None,
            departamento=dep.descricao if dep else 'Operações',
            setor=setr.descricao if setr else 'Acesso',
            empresa=emp.nome if emp else 'São Geraldo Service',
            grupo_id=grupo.id if grupo else None,
            status='Ativo',
            ativo=True,
        )
        db.session.add(pessoa)

    if AcessoEvento.query.count() == 0:
        eq_rec = AcessoEquipamento.query.filter_by(nome='Recepção').first()
        eq_fab = AcessoEquipamento.query.filter_by(nome='Fabrica').first()
        agora = datetime.utcnow()
        amostras = [
            ('12977641700', 'MARIA SILVA SANTOS', 'Liberado', 'Entrada', 'Face', 'TURN LEFT', eq_rec, 2),
            ('12977827714', 'ADALBERTO GOMES DA CRUZ', 'Liberado', 'Saída', 'Face', 'TURN RIGHT', eq_fab, 5),
            ('1001', 'COLABORADOR DEMO', 'Negado', 'Entrada', 'Cartao', '', eq_rec, 8),
            ('12977001122', 'ANA PAULA FERREIRA', 'Desistência', 'Entrada', 'Face', 'GIVE UP', eq_fab, 12),
            ('12977641700', 'MARIA SILVA SANTOS', 'Liberado', 'Saída', 'Face', 'TURN RIGHT', eq_rec, 20),
            ('12977999888', 'JOAO PEDRO ALMEIDA', 'Liberado', 'Entrada', 'QR', 'TURN LEFT', eq_fab, 35),
            ('1001', 'COLABORADOR DEMO', 'Liberado', 'Entrada', 'Face', 'TURN LEFT', eq_rec, 50),
            ('12977001122', 'ANA PAULA FERREIRA', 'Negado', 'Entrada', 'Face', '', eq_fab, 65),
        ]
        for mat, nome, st, direcao, metodo, girou, eq, mins in amostras:
            db.session.add(AcessoEvento(
                pessoa_ref=mat,
                nome=nome,
                tipo_pessoa='PESSOA',
                status=st,
                direction=direcao,
                event_type=metodo,
                equipamento_id=eq.id if eq else None,
                equipamento_nome=eq.nome if eq else None,
                girou=girou or None,
                data_hora=agora - timedelta(minutes=mins),
            ))

    # Config padrão de backup agendado (desativado / Diário / 02:00).
    # A execução automática será feita por job/serviço externo — aqui só persistimos a UI.
    if AcessoBackupConfig.query.count() == 0:
        db.session.add(AcessoBackupConfig(ativo=False, frequencia='Diário', horario='02:00'))

    db.session.commit()


def _get_backup_config():
    cfg = AcessoBackupConfig.query.order_by(AcessoBackupConfig.id.asc()).first()
    if not cfg:
        cfg = AcessoBackupConfig(ativo=False, frequencia='Diário', horario='02:00')
        db.session.add(cfg)
        db.session.commit()
    return cfg


def _catalogos():
    return {
        'empresas': [e.to_dict() for e in AcessoEmpresa.query.order_by(AcessoEmpresa.nome).all()],
        'classificacoes': [c.to_dict() for c in AcessoClassificacao.query.order_by(AcessoClassificacao.descricao).all()],
        'departamentos': [d.to_dict() for d in AcessoDepartamento.query.order_by(AcessoDepartamento.descricao).all()],
        'setores': [s.to_dict() for s in AcessoSetor.query.order_by(AcessoSetor.descricao).all()],
        'centros': [c.to_dict() for c in AcessoCentroCusto.query.order_by(AcessoCentroCusto.descricao).all()],
        'grupos': [g.to_dict() for g in AcessoGrupo.query.order_by(AcessoGrupo.nome).all()],
    }


def _apply_pessoa_fields(pessoa, data):
    if 'nome' in data and data.get('nome') is not None:
        pessoa.nome = (data.get('nome') or pessoa.nome).strip().upper()
    if 'matricula' in data and data.get('matricula') is not None:
        nova = (data.get('matricula') or '').strip()
        if nova and nova != pessoa.matricula:
            if AcessoPessoa.query.filter(
                AcessoPessoa.matricula == nova,
                AcessoPessoa.id != (pessoa.id or 0),
            ).first():
                raise ValueError('Matrícula já cadastrada')
            pessoa.matricula = nova
    for field in ('cartao', 'qr_code', 'documento', 'observacao', 'foto', 'token', 'tipo_cartao', 'equipamentos_ids'):
        if field in data:
            setattr(pessoa, field, (data.get(field) or '').strip() or None)

    for field in ('empresa_id', 'classificacao_id', 'departamento_id', 'setor_id', 'centro_custo_id', 'grupo_id'):
        if field in data:
            setattr(pessoa, field, _parse_int(data.get(field)))

    # espelha nomes em campos texto legados
    if pessoa.empresa_id:
        emp = AcessoEmpresa.query.get(pessoa.empresa_id)
        pessoa.empresa = emp.nome if emp else pessoa.empresa
    elif 'empresa' in data:
        pessoa.empresa = (data.get('empresa') or '').strip() or None

    if pessoa.departamento_id:
        dep = AcessoDepartamento.query.get(pessoa.departamento_id)
        pessoa.departamento = dep.descricao if dep else pessoa.departamento
    if pessoa.setor_id:
        setr = AcessoSetor.query.get(pessoa.setor_id)
        pessoa.setor = setr.descricao if setr else pessoa.setor

    if 'data_inicial' in data:
        pessoa.data_inicial = _parse_date(data.get('data_inicial')) or pessoa.data_inicial or date.today()
    if 'hora_inicial' in data:
        pessoa.hora_inicial = _parse_time(data.get('hora_inicial')) or pessoa.hora_inicial or time(0, 0)
    if 'data_final' in data:
        pessoa.data_final = _parse_date(data.get('data_final'))
    if 'hora_final' in data:
        pessoa.hora_final = _parse_time(data.get('hora_final'))

    if 'status' in data and data.get('status') is not None and data.get('status') != '':
        raw = str(data.get('status')).strip()
        # compatível com 1/0/2 da UI de referência
        mapa = {'1': 'Ativo', '0': 'Inativo', '2': 'Livre', 'ativo': 'Ativo', 'inativo': 'Inativo', 'livre': 'Livre'}
        pessoa.status = mapa.get(raw.lower(), raw)
    elif 'ativo' in data:
        pessoa.status = 'Ativo' if str(data.get('ativo')).lower() not in ('0', 'false', 'off') else 'Inativo'
    pessoa.sync_ativo_status()


def _date_range(range_key, custom_date=None):
    """Retorna (inicio, fim, label_comparacao, inicio_cmp, fim_cmp)."""
    hoje = date.today()
    if custom_date:
        d = _parse_date(custom_date)
        if d:
            ini = datetime.combine(d, time.min)
            fim = datetime.combine(d, time.max)
            cmp_ini = ini - timedelta(days=30)
            cmp_fim = fim - timedelta(days=30)
            return ini, fim, 'vs. 30 dias anteriores', cmp_ini, cmp_fim

    key = (range_key or 'today').lower()
    if key == 'all':
        return None, None, 'vs. período anterior', None, None
    if key == 'yesterday':
        d = hoje - timedelta(days=1)
        ini = datetime.combine(d, time.min)
        fim = datetime.combine(d, time.max)
        cmp_ini = ini - timedelta(days=1)
        cmp_fim = fim - timedelta(days=1)
        return ini, fim, 'vs. dia anterior', cmp_ini, cmp_fim
    if key == '7days':
        ini = datetime.combine(hoje - timedelta(days=6), time.min)
        fim = datetime.combine(hoje, time.max)
        cmp_ini = ini - timedelta(days=7)
        cmp_fim = ini - timedelta(seconds=1)
        return ini, fim, 'vs. 7 dias anteriores', cmp_ini, cmp_fim

    # today (default)
    ini = datetime.combine(hoje, time.min)
    fim = datetime.combine(hoje, time.max)
    cmp_ini = ini - timedelta(days=30)
    cmp_fim = ini - timedelta(seconds=1)
    return ini, fim, 'vs. 30 dias anteriores', cmp_ini, cmp_fim


def _count_status(query):
    liberados = negados = desistencias = 0
    for st, girou in query.with_entities(AcessoEvento.status, AcessoEvento.girou).all():
        if (girou or '').upper() == 'GIVE UP' or st == 'Desistência':
            desistencias += 1
        elif st == 'Negado':
            negados += 1
        else:
            liberados += 1
    return liberados, negados, desistencias


_ACESSO_FOTOS_DIR = Path(__file__).resolve().parent / 'static' / 'acesso_fotos'


def _foto_arquivo_estatico(ref: str) -> str:
    """Se existir JPG/PNG em static/acesso_fotos/{ref}.*, retorna URL web."""
    ref = (ref or '').strip()
    if not ref or ref in ('0', '-1'):
        return ''
    # evita path traversal
    safe = Path(ref).name
    if safe != ref or '..' in ref or '/' in ref or '\\' in ref:
        return ''
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        path = _ACESSO_FOTOS_DIR / f'{safe}{ext}'
        if path.is_file():
            return f'/static/acesso_fotos/{safe}{ext}'
    return ''


def _foto_url_para_exibicao(tipo: str, ref: str, foto_raw: str | None) -> str:
    """URL leve para UI: path estático direto; data-URL via endpoint."""
    from urllib.parse import quote

    ref = (ref or '').strip()
    if not ref:
        return ''
    raw = (foto_raw or '').strip()
    if raw.startswith('/static/'):
        return raw
    if raw.startswith('static/'):
        return '/' + raw
    if raw.startswith('http://') or raw.startswith('https://'):
        return raw
    tipo_key = 'visitante' if (tipo or '').upper() == 'VISITANTE' else 'pessoa'
    if raw.startswith('data:') or raw:
        # path relativo / data-URL — evita embutir base64 na lista de eventos
        return f'/acesso/api/foto/{tipo_key}/{quote(ref, safe="")}'
    return _foto_arquivo_estatico(ref)


def _map_fotos_eventos(eventos):
    """Batch: pessoa_ref → foto bruta (data-URL ou path) de Pessoa/Visitante."""
    pessoa_refs = set()
    visitante_refs = set()
    for e in eventos:
        ref = (getattr(e, 'pessoa_ref', None) or '').strip()
        if not ref or ref in ('0', '-1'):
            continue
        if (getattr(e, 'tipo_pessoa', None) or '').upper() == 'VISITANTE':
            visitante_refs.add(ref)
        else:
            pessoa_refs.add(ref)

    foto_map = {}
    if pessoa_refs:
        for p in AcessoPessoa.query.filter(AcessoPessoa.matricula.in_(list(pessoa_refs))).all():
            if p.foto:
                foto_map[('PESSOA', p.matricula)] = p.foto
    if visitante_refs:
        for v in AcessoVisitante.query.filter(or_(
            AcessoVisitante.visitor_id.in_(list(visitante_refs)),
            AcessoVisitante.documento.in_(list(visitante_refs)),
        )).all():
            if not v.foto:
                continue
            if v.visitor_id:
                foto_map[('VISITANTE', v.visitor_id)] = v.foto
            if v.documento:
                foto_map[('VISITANTE', v.documento)] = v.foto
    return foto_map


def _eventos_to_dicts_com_foto(eventos):
    """Serializa eventos incluindo foto (URL) com fallback para iniciais no front."""
    foto_map = _map_fotos_eventos(eventos)
    out = []
    for e in eventos:
        d = e.to_dict()
        ref = (e.pessoa_ref or '').strip()
        tipo = (e.tipo_pessoa or 'PESSOA').upper()
        key = 'VISITANTE' if tipo == 'VISITANTE' else 'PESSOA'
        raw = foto_map.get((key, ref)) if ref else None
        url = _foto_url_para_exibicao(tipo, ref, raw)
        d['foto'] = url or ''
        d['tem_foto'] = bool(url)
        out.append(d)
    return out


def _ultima_data_com_eventos():
    """Retorna a data (date) do evento mais recente, ou None."""
    mx = db.session.query(func.max(AcessoEvento.data_hora)).scalar()
    return mx.date() if mx else None


def _eventos_filtrados(range_key='today', custom_date=None, status_filter='', search=''):
    ini, fim, cmp_label, cmp_ini, cmp_fim = _date_range(range_key, custom_date)
    q = AcessoEvento.query
    if ini and fim:
        q = q.filter(AcessoEvento.data_hora >= ini, AcessoEvento.data_hora <= fim)
    if search:
        like = f'%{search}%'
        q = q.filter(or_(
            AcessoEvento.nome.ilike(like),
            AcessoEvento.pessoa_ref.ilike(like),
            AcessoEvento.equipamento_nome.ilike(like),
        ))
    if status_filter:
        sf = status_filter.lower()
        if sf == 'liberado':
            q = q.filter(AcessoEvento.status == 'Liberado').filter(
                or_(AcessoEvento.girou.is_(None), AcessoEvento.girou != 'GIVE UP')
            )
        elif sf == 'negado':
            q = q.filter(AcessoEvento.status == 'Negado')
        elif sf == 'desistencia':
            q = q.filter(or_(
                AcessoEvento.status == 'Desistência',
                AcessoEvento.girou == 'GIVE UP',
            ))
    return q, ini, fim, cmp_label, cmp_ini, cmp_fim


def _dashboard_periodo(range_key='today', custom_date=None, status_filter='', search='', auto_fallback=True):
    """
    Monta query/KPIs do dashboard.
    Se o padrão 'Hoje' estiver vazio e o usuário não escolheu data/range,
    cai automaticamente no último dia com eventos (UX: não parecer vazio).
    """
    range_key = (range_key or 'today').strip() or 'today'
    custom_date = (custom_date or '').strip()
    status_filter = (status_filter or '').strip()
    search = (search or '').strip()

    # Só aplica fallback no default implícito "Hoje" (sem date= e sem range explícito na UI
    # seria range=today). Se o usuário clicou Hoje de propósito, ainda faz sentido
    # mostrar o último dia com dados + aviso, pois "vazio" confunde com falha.
    explicit_range = range_key.lower() not in ('', 'today')
    q, ini, fim, cmp_label, cmp_ini, cmp_fim = _eventos_filtrados(
        range_key, custom_date or None, status_filter, search
    )

    fallback_aviso = None
    used_fallback = False
    # "Hoje" vazio → último dia com eventos (mesmo se o usuário clicou Hoje)
    if (
        auto_fallback
        and not custom_date
        and not explicit_range
        and q.limit(1).first() is None
    ):
        ultima = _ultima_data_com_eventos()
        if ultima and ultima != date.today():
            custom_date = ultima.isoformat()
            q, ini, fim, cmp_label, cmp_ini, cmp_fim = _eventos_filtrados(
                'custom', custom_date, status_filter, search
            )
            used_fallback = True
            fallback_aviso = (
                f'Sem eventos hoje ({date.today().strftime("%d/%m/%Y")}). '
                f'Exibindo o último dia com registros: {ultima.strftime("%d/%m/%Y")}.'
            )
            range_key = 'custom'

    return {
        'q': q,
        'ini': ini,
        'fim': fim,
        'cmp_label': cmp_label,
        'cmp_ini': cmp_ini,
        'cmp_fim': cmp_fim,
        'range_key': range_key if not custom_date else 'custom',
        'custom_date': custom_date,
        'status_filter': status_filter,
        'search': search,
        'fallback_aviso': fallback_aviso,
        'used_fallback': used_fallback,
    }


def _stats_periodo(ini, fim):
    q = AcessoEvento.query
    if ini and fim:
        q = q.filter(AcessoEvento.data_hora >= ini, AcessoEvento.data_hora <= fim)
    liberados, negados, desistencias = _count_status(q)
    total = liberados + negados  # total acessos (sem desistências no total principal, como referência)
    # na UI de referência: Total = liberados + negados
    return {
        'total': total,
        'liberados': liberados,
        'negados': negados,
        'desistencias': desistencias,
    }


# ---- PÁGINAS ----
@acesso.route('/acesso')
@login_required
def dashboard():
    seed_acesso()
    periodo = _dashboard_periodo(
        request.args.get('range') or 'today',
        request.args.get('date') or '',
        request.args.get('status') or '',
        request.args.get('q') or '',
        auto_fallback=True,
    )
    q = periodo['q']
    ini, fim = periodo['ini'], periodo['fim']
    cmp_label, cmp_ini, cmp_fim = periodo['cmp_label'], periodo['cmp_ini'], periodo['cmp_fim']

    stats = _stats_periodo(ini, fim)
    stats_cmp = _stats_periodo(cmp_ini, cmp_fim) if cmp_ini and cmp_fim else {'liberados': 0}
    base_lib = stats_cmp.get('liberados') or 0
    if base_lib:
        pct_lib = ((stats['liberados'] - base_lib) / base_lib) * 100
    else:
        pct_lib = 100.0 if stats['liberados'] else 0.0

    eventos = q.order_by(AcessoEvento.data_hora.desc()).limit(50).all()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    online_list = [e for e in equipamentos if e.online]
    ambientes = AcessoAmbiente.query.filter_by(ativo=True).order_by(AcessoAmbiente.nome).all()

    return render_template(
        'acesso_dashboard.html',
        stats=stats,
        pct_liberados=pct_lib,
        comparison_label=cmp_label,
        eventos=_eventos_to_dicts_com_foto(eventos),
        equipamentos=[e.to_dict() for e in equipamentos],
        online_count=len(online_list),
        offline_count=len(equipamentos) - len(online_list),
        ambientes=[a.to_dict() for a in ambientes],
        range_key=periodo['range_key'],
        custom_date=periodo['custom_date'],
        status_filter=periodo['status_filter'],
        search=periodo['search'],
        fallback_aviso=periodo['fallback_aviso'],
        active_page='dashboard',
        active_sub='dashboard',
    )


@acesso.route('/acesso/api/dashboard')
@login_required
def api_dashboard():
    """JSON para atualização periódica do monitoramento."""
    seed_acesso()
    # API: não aplica fallback automático — respeita o range/date já escolhidos na página
    # (após fallback SSR o front envia date=YYYY-MM-DD).
    periodo = _dashboard_periodo(
        request.args.get('range') or 'today',
        request.args.get('date') or '',
        request.args.get('status') or '',
        request.args.get('q') or '',
        auto_fallback=False,
    )
    q = periodo['q']
    ini, fim = periodo['ini'], periodo['fim']
    cmp_label, cmp_ini, cmp_fim = periodo['cmp_label'], periodo['cmp_ini'], periodo['cmp_fim']
    stats = _stats_periodo(ini, fim)
    stats_cmp = _stats_periodo(cmp_ini, cmp_fim) if cmp_ini and cmp_fim else {'liberados': 0}
    base_lib = stats_cmp.get('liberados') or 0
    pct_lib = ((stats['liberados'] - base_lib) / base_lib) * 100 if base_lib else (100.0 if stats['liberados'] else 0.0)
    eventos = q.order_by(AcessoEvento.data_hora.desc()).limit(50).all()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    online = sum(1 for e in equipamentos if e.online)
    return jsonify({
        'ok': True,
        'stats': stats,
        'pct_liberados': pct_lib,
        'comparison_label': cmp_label,
        'eventos': _eventos_to_dicts_com_foto(eventos),
        'equipamentos': [e.to_dict() for e in equipamentos],
        'online_count': online,
        'offline_count': len(equipamentos) - online,
        'ambientes': [a.to_dict() for a in AcessoAmbiente.query.filter_by(ativo=True).all()],
        'range_key': periodo['range_key'],
        'custom_date': periodo['custom_date'],
        'fallback_aviso': periodo['fallback_aviso'],
    })


@acesso.route('/acesso/api/foto/<tipo>/<path:ref>')
@login_required
def api_foto_by_ref(tipo, ref):
    """Serve foto de pessoa/visitante (data-URL no banco ou arquivo em disco)."""
    tipo_n = (tipo or 'pessoa').strip().lower()
    ref = (ref or '').strip()
    if not ref or ref in ('0', '-1'):
        return '', 404

    foto_raw = None
    if tipo_n == 'visitante':
        v = AcessoVisitante.query.filter(or_(
            AcessoVisitante.visitor_id == ref,
            AcessoVisitante.documento == ref,
        )).first()
        foto_raw = v.foto if v else None
    else:
        p = AcessoPessoa.query.filter_by(matricula=ref).first()
        foto_raw = p.foto if p else None

    if not foto_raw:
        static_url = _foto_arquivo_estatico(ref)
        if static_url:
            return redirect(static_url)
        return '', 404

    raw = str(foto_raw).strip()
    if raw.startswith('/static/'):
        return redirect(raw)
    if raw.startswith('static/'):
        return redirect('/' + raw)

    img = cid.load_image_bytes(raw, static_root=Path(__file__).resolve().parent / 'static')
    if not img:
        static_url = _foto_arquivo_estatico(ref)
        if static_url:
            return redirect(static_url)
        return '', 404

    mime = 'image/jpeg'
    if raw.startswith('data:') and ';' in raw:
        mime = raw[5:].split(';', 1)[0] or mime
    elif raw.lower().endswith('.png'):
        mime = 'image/png'
    elif raw.lower().endswith('.webp'):
        mime = 'image/webp'
    return Response(
        img,
        mimetype=mime,
        headers={'Cache-Control': 'private, max-age=3600'},
    )


@acesso.route('/acesso/pessoas')
@login_required
def pessoas_page():
    seed_acesso()
    filtros = {
        'q': (request.args.get('q') or request.args.get('search_term') or '').strip(),
        'empresa_id': request.args.get('f_empresa_id') or request.args.get('empresa_id') or '',
        'classificacao_id': request.args.get('f_classificacao') or request.args.get('classificacao_id') or '',
        'departamento_id': request.args.get('f_departamento_id') or request.args.get('departamento_id') or '',
        'setor_id': request.args.get('f_setor_id') or request.args.get('setor_id') or '',
        'centro_custo_id': request.args.get('f_centro_de_custo_id') or request.args.get('centro_custo_id') or '',
        'mostrar_inativos': request.args.get('mostrar_inativos') in ('1', 'true', 'on'),
        'apenas_sem_foto': request.args.get('apenas_sem_foto') in ('1', 'true', 'on'),
    }

    query = AcessoPessoa.query
    if filtros['q']:
        like = f"%{filtros['q']}%"
        query = query.filter(or_(
            AcessoPessoa.nome.ilike(like),
            AcessoPessoa.matricula.ilike(like),
            AcessoPessoa.cartao.ilike(like),
            AcessoPessoa.documento.ilike(like),
        ))
    if filtros['empresa_id']:
        query = query.filter(AcessoPessoa.empresa_id == int(filtros['empresa_id']))
    if filtros['classificacao_id']:
        query = query.filter(AcessoPessoa.classificacao_id == int(filtros['classificacao_id']))
    if filtros['departamento_id']:
        query = query.filter(AcessoPessoa.departamento_id == int(filtros['departamento_id']))
    if filtros['setor_id']:
        query = query.filter(AcessoPessoa.setor_id == int(filtros['setor_id']))
    if filtros['centro_custo_id']:
        query = query.filter(AcessoPessoa.centro_custo_id == int(filtros['centro_custo_id']))
    if not filtros['mostrar_inativos']:
        query = query.filter(or_(
            AcessoPessoa.status.in_(['Ativo', 'Livre']),
            AcessoPessoa.status.is_(None),
        ))
        query = query.filter(or_(AcessoPessoa.ativo.is_(True), AcessoPessoa.ativo.is_(None)))
    if filtros['apenas_sem_foto']:
        query = query.filter(or_(AcessoPessoa.foto.is_(None), AcessoPessoa.foto == ''))

    pessoas = query.order_by(AcessoPessoa.nome).all()
    cats = _catalogos()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    return render_template(
        'acesso_pessoas.html',
        pessoas=[p.to_dict() for p in pessoas],
        total_encontrados=len(pessoas),
        filtros=filtros,
        equipamentos=[e.to_dict() for e in equipamentos],
        active_page='pessoas',
        active_sub='cadastros',
        **cats,
    )


@acesso.route('/acesso/pessoas/export.csv')
@login_required
def pessoas_export_csv():
    seed_acesso()
    pessoas = AcessoPessoa.query.order_by(AcessoPessoa.nome).all()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow([
        'matricula', 'nome', 'status', 'cartao', 'empresa', 'classificacao',
        'departamento', 'setor', 'centro_custo', 'grupo', 'documento',
    ])
    for p in pessoas:
        d = p.to_dict()
        writer.writerow([
            d['matricula'], d['nome'], d['status'], d['cartao'], d['empresa_nome'],
            d['classificacao'], d['departamento'], d['setor'], d['centro_custo'],
            d['grupo_nome'], d['documento'],
        ])
    data = '\ufeff' + buf.getvalue()
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=colaboradores.csv'},
    )


@acesso.route('/acesso/equipamentos')
@login_required
def equipamentos_page():
    seed_acesso()
    equipamentos = AcessoEquipamento.query.order_by(AcessoEquipamento.nome).all()
    online_count = sum(1 for e in equipamentos if e.online)
    return render_template(
        'acesso_equipamentos.html',
        equipamentos=[e.to_dict() for e in equipamentos],
        online_count=online_count,
        offline_count=len(equipamentos) - online_count,
        active_page='equipamentos',
    )


@acesso.route('/acesso/operacoes')
@login_required
def operacoes_page():
    seed_acesso()
    cats = _catalogos()
    return render_template(
        'acesso_operacoes.html',
        active_page='operacoes',
        **cats,
    )


def _operacoes_pessoas_query(args):
    """Filtros compartilhados da Central de Operações."""
    q = (args.get('q') or '').strip()
    empresa_id = args.get('empresa_id') or ''
    departamento_id = args.get('departamento_id') or ''
    setor_id = args.get('setor_id') or ''
    classificacao_id = args.get('classificacao_id') or ''

    query = AcessoPessoa.query.filter(or_(
        AcessoPessoa.status.in_(['Ativo', 'Livre']),
        AcessoPessoa.status.is_(None),
    ))
    query = query.filter(or_(AcessoPessoa.ativo.is_(True), AcessoPessoa.ativo.is_(None)))

    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoPessoa.nome.ilike(like),
            AcessoPessoa.matricula.ilike(like),
            AcessoPessoa.cartao.ilike(like),
            AcessoPessoa.documento.ilike(like),
        ))
    if empresa_id:
        query = query.filter(AcessoPessoa.empresa_id == int(empresa_id))
    if departamento_id:
        query = query.filter(AcessoPessoa.departamento_id == int(departamento_id))
    if setor_id:
        query = query.filter(AcessoPessoa.setor_id == int(setor_id))
    if classificacao_id:
        query = query.filter(AcessoPessoa.classificacao_id == int(classificacao_id))
    return query.order_by(AcessoPessoa.nome)


@acesso.route('/acesso/api/operacoes/pessoas')
@login_required
def api_operacoes_pessoas():
    seed_acesso()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(100, max(5, int(request.args.get('per_page') or 20)))
    except (TypeError, ValueError):
        per_page = 20

    query = _operacoes_pessoas_query(request.args)
    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page) if total else 1
    if page > pages:
        page = pages
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    items = []
    for p in rows:
        d = p.to_dict()
        items.append({
            'id': d['id'],
            'nome': d['nome'],
            'matricula': d['matricula'],
            'foto': d['foto'],
            'tem_foto': d['tem_foto'],
            'departamento': d['departamento'],
            'setor': d['setor'],
        })
    return jsonify({
        'ok': True,
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages,
    })


@acesso.route('/acesso/api/operacoes/pessoas/ids')
@login_required
def api_operacoes_pessoas_ids():
    """IDs de todas as pessoas que batem nos filtros (para >> todos)."""
    seed_acesso()
    query = _operacoes_pessoas_query(request.args)
    rows = query.with_entities(
        AcessoPessoa.id, AcessoPessoa.nome, AcessoPessoa.matricula, AcessoPessoa.foto,
    ).all()
    items = [
        {
            'id': r.id,
            'nome': r.nome,
            'matricula': r.matricula,
            'foto': r.foto or '',
            'tem_foto': bool(r.foto),
        }
        for r in rows
    ]
    return jsonify({'ok': True, 'items': items, 'total': len(items)})


@acesso.route('/acesso/api/operacoes/executar', methods=['POST'])
@login_required
def api_operacoes_executar():
    """Envia pessoas aos equipamentos Control iD ou atualiza data/hora."""
    data = request.get_json(silent=True) or {}
    acao = (data.get('acao') or '').strip().lower()
    raw_ids = data.get('pessoa_ids') or []
    enviar_fotos = bool(data.get('enviar_fotos', True))
    enviar_digitais = bool(data.get('enviar_digitais', True))
    forcar = bool(data.get('forcar', False))
    eq_ids = _parse_int_list(data.get('equipamento_ids') or data.get('equipamentos') or [])

    ids = []
    for x in raw_ids:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))

    acoes_ok = {
        'enviar_equipamentos': 'Enviar para equipamentos',
        'atualizar_data_hora': 'Atualizar data-hora nos equipamentos',
    }
    if acao not in acoes_ok:
        return jsonify({'ok': False, 'error': 'Ação desconhecida'}), 400
    if not ids:
        return jsonify({'ok': False, 'error': 'Selecione ao menos uma pessoa'}), 400

    existentes = {
        p.id: p
        for p in AcessoPessoa.query.filter(AcessoPessoa.id.in_(ids)).all()
    }
    encontrados = [existentes[i] for i in ids if i in existentes]
    if not encontrados:
        return jsonify({'ok': False, 'error': 'Nenhuma pessoa válida na seleção'}), 400

    eqs = _controlid_eqs_alvo(ids=eq_ids or None, only_online=not forcar and not eq_ids)
    if not eqs:
        eqs = _controlid_eqs_alvo(ids=eq_ids or None, only_online=False)
    if not eqs:
        return jsonify({'ok': False, 'error': 'Nenhum equipamento com IP cadastrado'}), 400

    detalhes = []
    ok_count = 0
    err_count = 0

    if acao == 'atualizar_data_hora':
        agora = datetime.now()
        for eq in eqs:
            try:
                cid.set_system_time(cid.creds_from_equipamento(eq), agora)
                _controlid_mark_online(eq, True)
                ok_count += 1
                detalhes.append({'equipamento': eq.nome, 'ok': True})
            except cid.ControlIDError as exc:
                err_count += 1
                _controlid_mark_online(eq, False)
                detalhes.append({'equipamento': eq.nome, 'ok': False, 'error': str(exc)})
        db.session.commit()
        return jsonify({
            'ok': err_count == 0,
            'stub': False,
            'acao': acao,
            'message': (
                f'Data/hora enviada a {ok_count} equipamento(s)'
                + (f'; {err_count} falha(s)' if err_count else '')
            ),
            'ok_count': ok_count,
            'err_count': err_count,
            'detalhes': detalhes,
            'pessoa_ids': [p.id for p in encontrados],
        })

    # enviar_equipamentos
    for pessoa in encontrados:
        alvo_eqs = eqs
        if pessoa.equipamentos_ids and not eq_ids:
            allowed = set(_parse_int_list(
                [x.strip() for x in str(pessoa.equipamentos_ids).split(',') if x.strip()]
            ))
            if allowed:
                alvo_eqs = [e for e in eqs if e.id in allowed] or eqs
        for eq in alvo_eqs:
            try:
                push = _controlid_push_pessoa(eq, pessoa, enviar_fotos=enviar_fotos)
                _controlid_mark_online(eq, True)
                ok_count += 1
                detalhes.append({
                    'pessoa': pessoa.matricula,
                    'equipamento': eq.nome,
                    'ok': True,
                    'result': {
                        'user': push.get('user', {}).get('action'),
                        'card': bool(push.get('card') and push['card'].get('ok') is not False),
                        'foto': bool(push.get('foto') and push['foto'].get('ok') is not False)
                        if enviar_fotos else None,
                    },
                })
            except cid.ControlIDError as exc:
                err_count += 1
                _controlid_mark_online(eq, False)
                detalhes.append({
                    'pessoa': pessoa.matricula,
                    'equipamento': eq.nome,
                    'ok': False,
                    'error': str(exc),
                })
    db.session.commit()
    sem_foto = sum(1 for p in encontrados if not p.foto)
    return jsonify({
        'ok': err_count == 0,
        'stub': False,
        'acao': acao,
        'message': (
            f'Envio: {ok_count} ok, {err_count} falha(s) — '
            f'{len(encontrados)} pessoa(s) × {len(eqs)} equipamento(s)'
            + (f' ({sem_foto} sem foto)' if sem_foto else '')
            + ('; digitais não suportadas nesta versão' if enviar_digitais else '')
        ),
        'ok_count': ok_count,
        'err_count': err_count,
        'detalhes': detalhes[:80],
        'pessoa_ids': [p.id for p in encontrados],
        'enviar_fotos': enviar_fotos,
        'enviar_digitais': enviar_digitais,
        'forcar': forcar,
        'sem_foto': sem_foto,
    })


def _parse_int_list(raw):
    ids = []
    if not isinstance(raw, (list, tuple)):
        return ids
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(ids))


def _limpeza_ultimo_acesso_map(tipo, equipamento_ids=None):
    """pessoa_ref → última data_hora de AcessoEvento para o tipo informado."""
    tipo_u = (tipo or 'PESSOA').upper()
    q = db.session.query(
        AcessoEvento.pessoa_ref,
        func.max(AcessoEvento.data_hora).label('ultimo'),
    ).filter(
        func.upper(AcessoEvento.tipo_pessoa) == tipo_u,
        AcessoEvento.pessoa_ref.isnot(None),
        AcessoEvento.pessoa_ref != '',
    )
    if equipamento_ids:
        q = q.filter(AcessoEvento.equipamento_id.in_(equipamento_ids))
    q = q.group_by(AcessoEvento.pessoa_ref)
    return {row.pessoa_ref: row.ultimo for row in q.all() if row.pessoa_ref}


def _limpeza_status_pessoa(p):
    return (p.status or ('Ativo' if p.ativo else 'Inativo')).strip() or 'Ativo'


def _limpeza_filtra_status_pessoa(query, status_filtro):
    st = (status_filtro or 'ativos').strip().lower()
    if st in ('ativos', 'ativo'):
        return query.filter(or_(
            AcessoPessoa.status.in_(['Ativo', 'Livre']),
            AcessoPessoa.status.is_(None),
        )).filter(or_(AcessoPessoa.ativo.is_(True), AcessoPessoa.ativo.is_(None)))
    if st in ('inativos', 'inativo'):
        return query.filter(or_(
            AcessoPessoa.status == 'Inativo',
            AcessoPessoa.ativo.is_(False),
        ))
    return query


def _limpeza_filtra_status_visitante(query, status_filtro):
    st = (status_filtro or 'ativos').strip().lower()
    if st in ('ativos', 'ativo'):
        return query.filter(or_(AcessoVisitante.ativo.is_(True), AcessoVisitante.ativo.is_(None)))
    if st in ('inativos', 'inativo'):
        return query.filter(AcessoVisitante.ativo.is_(False))
    return query


def _limpeza_analisar(data):
    """Pessoas/visitantes sem evento de acesso há X dias (AcessoEvento.data_hora)."""
    try:
        dias = max(1, int(data.get('dias') or 30))
    except (TypeError, ValueError):
        dias = 30
    status_filtro = (data.get('status') or 'ativos').strip().lower()
    equipamento_ids = _parse_int_list(data.get('equipamento_ids') or [])
    nome_q = (data.get('nome') or '').strip()
    empresa_id = data.get('empresa_id') or ''
    cutoff = datetime.utcnow() - timedelta(days=dias)

    ultimo_pessoa = _limpeza_ultimo_acesso_map('PESSOA', equipamento_ids or None)
    ultimo_vis = _limpeza_ultimo_acesso_map('VISITANTE', equipamento_ids or None)

    pq = _limpeza_filtra_status_pessoa(AcessoPessoa.query, status_filtro)
    vq = _limpeza_filtra_status_visitante(AcessoVisitante.query, status_filtro)
    if nome_q:
        like = f'%{nome_q}%'
        pq = pq.filter(or_(
            AcessoPessoa.nome.ilike(like),
            AcessoPessoa.matricula.ilike(like),
        ))
        vq = vq.filter(or_(
            AcessoVisitante.nome.ilike(like),
            AcessoVisitante.visitor_id.ilike(like),
            AcessoVisitante.documento.ilike(like),
        ))
    if empresa_id:
        try:
            eid = int(empresa_id)
            pq = pq.filter(AcessoPessoa.empresa_id == eid)
            vq = vq.filter(AcessoVisitante.empresa_id == eid)
        except (TypeError, ValueError):
            pass

    usuarios = []
    for p in pq.order_by(AcessoPessoa.nome).all():
        ref = (p.matricula or '').strip()
        ultimo = ultimo_pessoa.get(ref)
        if ultimo and ultimo >= cutoff:
            continue
        usuarios.append({
            'id': p.id,
            'tipo': 'usuario',
            'ref': ref,
            'nome': p.nome,
            'matricula': p.matricula or '',
            'status': _limpeza_status_pessoa(p),
            'empresa': (
                p.empresa_ref.nome if p.empresa_ref else (p.empresa or '')
            ),
            'ultimo_acesso': ultimo.strftime('%d/%m/%Y %H:%M') if ultimo else 'Nunca',
            'dias_sem_acesso': (
                (datetime.utcnow() - ultimo).days if ultimo else None
            ),
            'foto': p.foto or '',
        })

    visitantes = []
    for v in vq.order_by(AcessoVisitante.nome).all():
        ref = (v.visitor_id or '').strip()
        ultimo = ultimo_vis.get(ref)
        if ultimo and ultimo >= cutoff:
            continue
        visitantes.append({
            'id': v.id,
            'tipo': 'visitante',
            'ref': ref,
            'nome': v.nome,
            'visitor_id': v.visitor_id or '',
            'documento': v.documento or v.cpf or '',
            'status': 'Ativo' if v.ativo else 'Inativo',
            'empresa': (
                v.empresa_ref.nome if v.empresa_ref else (v.empresa_visitada or '')
            ),
            'ultimo_acesso': ultimo.strftime('%d/%m/%Y %H:%M') if ultimo else 'Nunca',
            'dias_sem_acesso': (
                (datetime.utcnow() - ultimo).days if ultimo else None
            ),
            'foto': v.foto or '',
        })

    return {
        'ok': True,
        'dias': dias,
        'status': status_filtro,
        'equipamento_ids': equipamento_ids,
        'cutoff': cutoff.strftime('%d/%m/%Y %H:%M'),
        'usuarios': usuarios,
        'visitantes': visitantes,
        'total_usuarios': len(usuarios),
        'total_visitantes': len(visitantes),
    }


@acesso.route('/acesso/limpeza')
@login_required
def limpeza_page():
    seed_acesso()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(
        AcessoEquipamento.nome
    ).all()
    cats = _catalogos()
    return render_template(
        'acesso_limpeza.html',
        active_page='limpeza',
        equipamentos=[e.to_dict() for e in equipamentos],
        **cats,
    )


@acesso.route('/acesso/api/limpeza/analisar', methods=['POST'])
@login_required
def api_limpeza_analisar():
    seed_acesso()
    data = request.get_json(silent=True) or {}
    return jsonify(_limpeza_analisar(data))


@acesso.route('/acesso/api/limpeza/executar', methods=['POST'])
@login_required
def api_limpeza_executar():
    """Stub de limpeza: opcionalmente desativa no banco e remove vínculos."""
    seed_acesso()
    data = request.get_json(silent=True) or {}
    modo = (data.get('modo') or '').strip().lower()
    desativar_banco = bool(data.get('desativar_banco'))
    remover_vinculos = bool(data.get('remover_vinculos', True))
    equipamento_ids = _parse_int_list(data.get('equipamento_ids') or [])

    modos_ok = {
        'limpeza_total': 'Limpeza Total',
        'remover_filtro': 'Remover Tudo (Filtro)',
        'remover_selecionados': 'Remover Selecionados',
    }
    if modo not in modos_ok:
        return jsonify({'ok': False, 'error': 'Modo desconhecido'}), 400

    if modo == 'remover_selecionados':
        usuario_ids = _parse_int_list(data.get('usuario_ids') or [])
        visitante_ids = _parse_int_list(data.get('visitante_ids') or [])
        if not usuario_ids and not visitante_ids:
            return jsonify({'ok': False, 'error': 'Selecione ao menos um registro'}), 400
        pessoas = AcessoPessoa.query.filter(AcessoPessoa.id.in_(usuario_ids)).all() if usuario_ids else []
        visitantes = (
            AcessoVisitante.query.filter(AcessoVisitante.id.in_(visitante_ids)).all()
            if visitante_ids else []
        )
    else:
        analise = _limpeza_analisar(data)
        pessoas = AcessoPessoa.query.filter(
            AcessoPessoa.id.in_([u['id'] for u in analise['usuarios']] or [-1])
        ).all() if analise['usuarios'] else []
        visitantes = AcessoVisitante.query.filter(
            AcessoVisitante.id.in_([v['id'] for v in analise['visitantes']] or [-1])
        ).all() if analise['visitantes'] else []

    if not pessoas and not visitantes:
        return jsonify({'ok': False, 'error': 'Nenhum registro elegível para limpeza'}), 400

    afetados_pessoas = 0
    afetados_visitantes = 0
    if desativar_banco:
        for p in pessoas:
            p.status = 'Inativo'
            p.ativo = False
            if remover_vinculos:
                p.grupo_id = None
                p.equipamentos_ids = ''
            afetados_pessoas += 1
        for v in visitantes:
            v.ativo = False
            if remover_vinculos:
                v.grupo_id = None
                v.equipamento_id = None
            afetados_visitantes += 1
        db.session.commit()

    label = modos_ok[modo]
    eq_txt = f'{len(equipamento_ids)} equipamento(s)' if equipamento_ids else 'todos equipamentos'
    acao_banco = (
        f'desativados no banco ({afetados_pessoas} usuário(s), {afetados_visitantes} visitante(s))'
        if desativar_banco
        else 'sem alteração no banco (somente remoção nos equipamentos — stub)'
    )
    return jsonify({
        'ok': True,
        'stub': True,
        'modo': modo,
        'desativar_banco': desativar_banco,
        'remover_vinculos': remover_vinculos,
        'equipamento_ids': equipamento_ids,
        'usuarios_afetados': [p.id for p in pessoas],
        'visitantes_afetados': [v.id for v in visitantes],
        'message': (
            f'[Stub] {label}: {len(pessoas)} usuário(s) + {len(visitantes)} visitante(s) '
            f'em {eq_txt} — {acao_banco}'
        ),
    })


# ---- Sincronizar Eventos Offline ----
def _sync_offline_status_filter(query, status):
    st = (status or 'Todos').strip()
    if not st or st.lower() == 'todos':
        return query
    if st == 'Liberado':
        return query.filter(AcessoEvento.status == 'Liberado').filter(
            or_(AcessoEvento.girou.is_(None), AcessoEvento.girou != 'GIVE UP')
        )
    if st == 'Negado':
        return query.filter(AcessoEvento.status == 'Negado')
    if st == 'Desistência':
        return query.filter(or_(
            AcessoEvento.status == 'Desistência',
            AcessoEvento.girou == 'GIVE UP',
        ))
    return query.filter(AcessoEvento.status == st)


def _sync_offline_evento_existe(eq_id, pessoa_ref, data_hora, status, direction):
    """Evita duplicar eventos já persistidos (chave aproximada)."""
    q = AcessoEvento.query.filter(
        AcessoEvento.equipamento_id == eq_id,
        AcessoEvento.data_hora == data_hora,
        AcessoEvento.status == status,
    )
    if pessoa_ref:
        q = q.filter(AcessoEvento.pessoa_ref == pessoa_ref)
    if direction:
        q = q.filter(AcessoEvento.direction == direction)
    return q.first() is not None


@acesso.route('/acesso/sincronizar-offline')
@login_required
def sync_offline_page():
    seed_acesso()
    equipamentos = AcessoEquipamento.query.order_by(AcessoEquipamento.nome).all()
    hoje = date.today()
    return render_template(
        'acesso_sync_offline.html',
        equipamentos=[e.to_dict() for e in equipamentos],
        data_inicio=(hoje - timedelta(days=7)).isoformat(),
        data_fim=hoje.isoformat(),
        active_page='sync_offline',
    )


@acesso.route('/acesso/api/sync-offline/coletar', methods=['POST'])
@login_required
def api_sync_offline_coletar():
    """Coleta access_logs do equipamento Control iD e cruza com AcessoEvento."""
    seed_acesso()
    data = request.get_json(silent=True) or {}
    eq_id = _parse_int(data.get('equipamento_id'))
    data_inicio = _parse_date(data.get('data_inicio'))
    data_fim = _parse_date(data.get('data_fim'))
    status = (data.get('status') or 'Todos').strip()

    if not eq_id:
        return jsonify({'ok': False, 'error': 'Selecione um equipamento'}), 400
    if not data_inicio or not data_fim:
        return jsonify({'ok': False, 'error': 'Informe data início e data fim'}), 400
    if data_fim < data_inicio:
        return jsonify({'ok': False, 'error': 'Data fim não pode ser anterior à data início'}), 400

    eq = AcessoEquipamento.query.get(eq_id)
    if not eq:
        return jsonify({'ok': False, 'error': 'Equipamento não encontrado'}), 404
    if not (eq.ip or '').strip():
        return jsonify({'ok': False, 'error': 'Equipamento sem IP configurado'}), 400

    ini_dt = datetime.combine(data_inicio, time.min)
    fim_dt = datetime.combine(data_fim, time.max)
    creds = cid.creds_from_equipamento(eq)

    try:
        rows = cid.collect_access_logs(creds, after_id=0)
        _controlid_mark_online(eq, True)
        db.session.commit()
    except cid.ControlIDError as exc:
        _controlid_mark_online(eq, False)
        db.session.commit()
        return jsonify({
            'ok': False,
            'error': f'Falha ao coletar de {eq.nome} ({eq.ip}): {exc}',
            'stub': False,
        }), 502

    pendentes = []
    for row in rows:
        try:
            dh = cid.parse_access_log_time(row)
        except Exception:
            continue
        if dh < ini_dt or dh > fim_dt:
            continue

        uid_raw = row.get('user_id')
        try:
            uid_int = int(uid_raw or 0)
        except (TypeError, ValueError):
            uid_int = 0
        st, event_type = cid.map_access_event(
            row.get('event'),
            user_id=uid_int,
            event_name=row.get('_event_name'),
        )
        if status and status != 'Todos' and st != status:
            if not (status == 'Desistência' and st == 'Desistência'):
                continue

        pessoa_ref, nome, tipo_pessoa = _controlid_resolve_pessoa(uid_raw)
        direction = _controlid_direction_for_eq(eq, row)
        card_val = row.get('card_value')
        if card_val not in (None, '', '0', 0):
            event_type = 'Cartão'
        elif row.get('qrcode_value'):
            event_type = 'QR Code'
        elif row.get('pin_value'):
            event_type = 'Senha'

        ja_existe = _sync_offline_evento_existe(eq.id, pessoa_ref, dh, st, direction)
        off_id = row.get('id')
        temp_id = f'cid-{eq.id}-{off_id}'
        pendentes.append({
            'temp_id': temp_id,
            'origem_event_id': off_id,
            'pessoa_ref': pessoa_ref or '',
            'nome': nome,
            'tipo_pessoa': tipo_pessoa,
            'status': st,
            'direction': direction,
            'event_type': event_type,
            'equipamento_id': eq.id,
            'equipamento_nome': eq.nome,
            'girou': 'GIVE UP' if st == 'Desistência' else '',
            'motivo': '',
            'cartao': str(card_val) if card_val not in (None, '', '0', 0) else '',
            'data_hora': dh.isoformat(sep=' ', timespec='seconds'),
            'data_hora_fmt': dh.strftime('%d/%m/%Y %H:%M:%S'),
            'ja_existe': ja_existe,
            'origem': 'equipamento',
            'raw': {
                'id': off_id,
                'event': row.get('event'),
                'user_id': uid_raw,
                'portal_id': row.get('portal_id'),
            },
        })

    pendentes.sort(key=lambda x: x.get('data_hora') or '')
    # limita UI
    if len(pendentes) > 2000:
        pendentes = pendentes[-2000:]
    novos = sum(1 for p in pendentes if not p.get('ja_existe'))
    return jsonify({
        'ok': True,
        'stub': False,
        'equipamento': eq.to_dict(),
        'total': len(pendentes),
        'novos': novos,
        'ja_existentes': len(pendentes) - novos,
        'eventos': pendentes,
        'message': (
            f'Coletados {len(pendentes)} evento(s) de {eq.nome} '
            f'({novos} novo(s), {len(pendentes) - novos} já no sistema).'
        ),
    })


@acesso.route('/acesso/api/sync-offline/salvar', methods=['POST'])
@login_required
def api_sync_offline_salvar():
    """Persiste eventos selecionados em AcessoEvento se ainda não existirem."""
    seed_acesso()
    data = request.get_json(silent=True) or {}
    eventos = data.get('eventos') or []
    if not isinstance(eventos, list) or not eventos:
        return jsonify({'ok': False, 'error': 'Nenhum evento selecionado'}), 400

    salvos = 0
    ignorados = 0
    erros = 0
    salvos_ids = []

    for item in eventos:
        if not isinstance(item, dict):
            erros += 1
            continue
        if item.get('ja_existe'):
            ignorados += 1
            continue

        eq_id = _parse_int(item.get('equipamento_id'))
        nome = (item.get('nome') or '').strip()
        if not nome:
            erros += 1
            continue

        eq = AcessoEquipamento.query.get(eq_id) if eq_id else None
        dh_raw = (item.get('data_hora') or '').strip()
        try:
            dh = datetime.strptime(dh_raw[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                dh = datetime.fromisoformat(dh_raw.replace('Z', ''))
            except ValueError:
                erros += 1
                continue

        status = (item.get('status') or 'Liberado').strip()
        if status == 'Desistência':
            status_db = 'Desistência'
            girou = 'GIVE UP'
        else:
            status_db = status
            girou = (item.get('girou') or '').strip() or None

        pessoa_ref = (item.get('pessoa_ref') or '').strip() or None
        direction = (item.get('direction') or '').strip() or None

        if eq_id and _sync_offline_evento_existe(eq_id, pessoa_ref, dh, status_db, direction):
            ignorados += 1
            continue

        ev = AcessoEvento(
            pessoa_ref=pessoa_ref,
            nome=nome,
            tipo_pessoa=(item.get('tipo_pessoa') or 'PESSOA').strip().upper(),
            status=status_db,
            direction=direction,
            event_type=(item.get('event_type') or 'Offline Sync').strip() or 'Offline Sync',
            equipamento_id=eq.id if eq else eq_id,
            equipamento_nome=(eq.nome if eq else (item.get('equipamento_nome') or '').strip()) or None,
            girou=girou,
            motivo=(item.get('motivo') or '').strip() or None,
            data_hora=dh,
        )
        db.session.add(ev)
        db.session.flush()
        salvos_ids.append(ev.id)
        salvos += 1

    if salvos:
        db.session.commit()

    return jsonify({
        'ok': True,
        'salvos': salvos,
        'ignorados': ignorados,
        'erros': erros,
        'ids': salvos_ids,
        'message': (
            f'{salvos} evento(s) salvos no sistema'
            + (f', {ignorados} ignorado(s) (já existiam)' if ignorados else '')
            + (f', {erros} com erro' if erros else '')
            + '.'
        ),
    })


@acesso.route('/acesso/grupos')
@login_required
def grupos_page():
    seed_acesso()
    grupos = AcessoGrupo.query.order_by(AcessoGrupo.nome).all()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    grupos_data = []
    for g in grupos:
        d = g.to_dict()
        d['equipamento_ids'] = [e.id for e in g.equipamentos]
        d['horarios'] = [h.to_dict() for h in g.horarios]
        grupos_data.append(d)
    return render_template(
        'acesso_grupos.html',
        grupos=grupos_data,
        equipamentos=[e.to_dict() for e in equipamentos],
        active_page='grupos',
    )


@acesso.route('/acesso/visitantes')
@login_required
def visitantes_page():
    seed_acesso()
    view = (request.args.get('view') or 'cadastro').strip().lower()
    if view not in ('cadastro', 'lista', 'relatorios'):
        view = 'cadastro'
    q = (request.args.get('q') or '').strip()
    query = AcessoVisitante.query
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoVisitante.nome.ilike(like),
            AcessoVisitante.visitor_id.ilike(like),
            AcessoVisitante.cpf.ilike(like),
            AcessoVisitante.documento.ilike(like),
            AcessoVisitante.anfitriao.ilike(like),
        ))
    visitantes = query.order_by(AcessoVisitante.data_criacao.desc()).limit(200).all()
    cats = _catalogos()
    tipos_doc = [t.to_dict() for t in AcessoTipoDocumento.query.order_by(AcessoTipoDocumento.descricao).all()]
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    hoje = date.today()
    ativos_hoje = AcessoVisitante.query.filter(
        AcessoVisitante.ativo.is_(True),
        AcessoVisitante.data_inicial <= hoje,
        or_(AcessoVisitante.data_final.is_(None), AcessoVisitante.data_final >= hoje),
    ).count()
    return render_template(
        'acesso_visitantes.html',
        view=view,
        visitantes=[v.to_dict() for v in visitantes],
        tipos_doc=tipos_doc,
        equipamentos=[e.to_dict() for e in equipamentos],
        q=q,
        total_visitantes=AcessoVisitante.query.count(),
        ativos_hoje=ativos_hoje,
        active_page='visitantes',
        active_sub='visitantes',
        **cats,
    )


@acesso.route('/acesso/escalas')
@login_required
def escalas_page():
    seed_acesso()
    q = (request.args.get('q') or '').strip()
    status = (request.args.get('status') or '').strip().lower()
    query = AcessoEscala.query
    if q:
        like = f'%{q}%'
        query = query.filter(AcessoEscala.nome_pessoa.ilike(like))
    if status == 'ativo':
        query = query.filter(AcessoEscala.ativo.is_(True))
    elif status == 'inativo':
        query = query.filter(AcessoEscala.ativo.is_(False))
    escalas = [
        e.to_dict()
        for e in query.order_by(
            AcessoEscala.nome_pessoa.asc(),
            AcessoEscala.data_inicio.desc(),
        ).limit(500).all()
    ]
    pessoas = (
        AcessoPessoa.query
        .order_by(AcessoPessoa.nome.asc())
        .limit(2000)
        .all()
    )
    return render_template(
        'acesso_escalas.html',
        active_page='escalas',
        escalas=escalas,
        pessoas=[{'id': p.id, 'nome': p.nome, 'matricula': p.matricula} for p in pessoas],
        q=q,
        status=status if status in ('ativo', 'inativo') else '',
        total=len(escalas),
    )


@acesso.route('/acesso/pessoas/veiculos')
@login_required
def pessoas_veiculos_page():
    seed_acesso()
    return render_template(
        'acesso_pessoas_veiculos.html',
        active_page='pessoas_veiculos',
    )


def _pessoa_veiculo_dict(p, veiculos_count=0):
    nome = p.nome or '?'
    iniciais = ''.join(part[0] for part in nome.split()[:2]).upper() if nome else '?'
    return {
        'id': p.id,
        'nome': nome,
        'matricula': p.matricula or '',
        'iniciais': iniciais[:2],
        'veiculos_count': int(veiculos_count or 0),
        'empresa': p.empresa_ref.nome if p.empresa_ref else (p.empresa or ''),
        'departamento': (
            p.departamento_ref.descricao if p.departamento_ref else (p.departamento or '')
        ),
    }


def _normalize_placa(value):
    raw = (value or '').strip().upper().replace(' ', '').replace('-', '')
    return raw


def _veiculo_from_payload(data, item=None, pessoa_id=None):
    pid = _parse_int(data.get('pessoa_id')) if data.get('pessoa_id') is not None else pessoa_id
    if item is not None and pid is None:
        pid = item.pessoa_id
    placa = _normalize_placa(data.get('placa'))
    modelo = (data.get('modelo') or '').strip()
    cor = (data.get('cor') or '').strip()
    tag_uhf = (data.get('tag_uhf') or '').strip() or None
    ativo = _parse_bool(data.get('ativo'), default=True if item is None else bool(item.ativo))

    if not pid:
        return None, ('Proprietário é obrigatório', 400)
    if not AcessoPessoa.query.get(pid):
        return None, ('Proprietário não encontrado', 404)
    if not placa:
        return None, ('Placa é obrigatória', 400)
    if len(placa) < 5 or len(placa) > 10:
        return None, ('Placa inválida', 400)

    q = AcessoVeiculo.query.filter(AcessoVeiculo.placa == placa)
    if item is not None:
        q = q.filter(AcessoVeiculo.id != item.id)
    if q.first():
        return None, ('Placa já cadastrada', 400)

    if tag_uhf:
        tq = AcessoVeiculo.query.filter(AcessoVeiculo.tag_uhf == tag_uhf)
        if item is not None:
            tq = tq.filter(AcessoVeiculo.id != item.id)
        if tq.first():
            return None, ('Tag UHF já cadastrada', 400)

    if item is None:
        item = AcessoVeiculo(pessoa_id=pid)
    else:
        item.pessoa_id = pid
    item.placa = placa
    item.modelo = modelo
    item.cor = cor
    item.tag_uhf = tag_uhf
    item.ativo = ativo
    return item, None


@acesso.route('/acesso/api/pessoas-veiculos/pessoas', methods=['GET'])
@login_required
def api_pessoas_veiculos_pessoas():
    """Lista proprietários (AcessoPessoa) com paginação e KPIs da frota."""
    seed_acesso()
    q = (request.args.get('q') or '').strip()
    page = max(_parse_int(request.args.get('page')) or 1, 1)
    per_page = min(max(_parse_int(request.args.get('per_page')) or 20, 5), 100)

    query = AcessoPessoa.query
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoPessoa.nome.ilike(like),
            AcessoPessoa.matricula.ilike(like),
        ))
    query = query.order_by(AcessoPessoa.nome.asc())
    total = query.count()
    pessoas = query.offset((page - 1) * per_page).limit(per_page).all()

    counts = dict(
        db.session.query(AcessoVeiculo.pessoa_id, func.count(AcessoVeiculo.id))
        .group_by(AcessoVeiculo.pessoa_id)
        .all()
    )
    total_veiculos = db.session.query(func.count(AcessoVeiculo.id)).scalar() or 0
    veiculos_ativos = (
        db.session.query(func.count(AcessoVeiculo.id))
        .filter(AcessoVeiculo.ativo.is_(True))
        .scalar()
        or 0
    )
    proprietarios_com_veiculo = (
        db.session.query(func.count(func.distinct(AcessoVeiculo.pessoa_id))).scalar() or 0
    )

    return jsonify({
        'ok': True,
        'pessoas': [
            _pessoa_veiculo_dict(p, counts.get(p.id, 0)) for p in pessoas
        ],
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': max((total + per_page - 1) // per_page, 1) if total else 0,
        'kpis': {
            'proprietarios': total,
            'proprietarios_com_veiculo': proprietarios_com_veiculo,
            'total_veiculos': total_veiculos,
            'veiculos_ativos': veiculos_ativos,
        },
    })


@acesso.route('/acesso/api/pessoas-veiculos/pessoas/<int:pid>/veiculos', methods=['GET', 'POST'])
@login_required
def api_pessoa_veiculos(pid):
    seed_acesso()
    pessoa = AcessoPessoa.query.get_or_404(pid)
    if request.method == 'GET':
        veiculos = (
            AcessoVeiculo.query
            .filter_by(pessoa_id=pid)
            .order_by(AcessoVeiculo.placa.asc())
            .all()
        )
        return jsonify({
            'ok': True,
            'pessoa': _pessoa_veiculo_dict(pessoa, len(veiculos)),
            'veiculos': [v.to_dict() for v in veiculos],
        })

    data = request.get_json(silent=True) or request.form or {}
    item, err = _veiculo_from_payload(data, pessoa_id=pid)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'veiculo': item.to_dict()}), 201


@acesso.route('/acesso/api/pessoas-veiculos/veiculos/<int:vid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_pessoa_veiculo_item(vid):
    seed_acesso()
    item = AcessoVeiculo.query.get_or_404(vid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'veiculo': item.to_dict()})
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    item, err = _veiculo_from_payload(data, item=item)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.commit()
    return jsonify({'ok': True, 'veiculo': item.to_dict()})


# ---- APIs Escalas ----
def _escala_from_payload(data, item=None):
    pessoa_id = _parse_int(data.get('pessoa_id'))
    nome_pessoa = (data.get('nome_pessoa') or data.get('nome') or '').strip()
    data_inicio = _parse_date(data.get('data_inicio'))
    data_fim = _parse_date(data.get('data_fim'))
    dias_trabalho = _parse_int(data.get('dias_trabalho'))
    dias_folga = _parse_int(data.get('dias_folga'))
    hora_entrada = _parse_time(data.get('hora_entrada'))
    hora_saida = _parse_time(data.get('hora_saida'))

    if pessoa_id:
        pessoa = AcessoPessoa.query.get(pessoa_id)
        if not pessoa:
            return None, ('Pessoa não encontrada', 404)
        if not nome_pessoa:
            nome_pessoa = pessoa.nome
    else:
        pessoa_id = None

    if not nome_pessoa:
        return None, ('Selecione um colaborador', 400)
    if not data_inicio:
        return None, ('Data inicial é obrigatória', 400)
    if data_fim and data_fim < data_inicio:
        return None, ('Data final não pode ser anterior à data inicial', 400)

    if dias_trabalho is None:
        dias_trabalho = 5
    if dias_folga is None:
        dias_folga = 2
    if dias_trabalho < 0 or dias_folga < 0:
        return None, ('Dias de trabalho/folga inválidos', 400)

    if item is None:
        item = AcessoEscala()

    item.pessoa_id = pessoa_id
    item.nome_pessoa = nome_pessoa
    item.data_inicio = data_inicio
    item.data_fim = data_fim
    item.dias_trabalho = dias_trabalho
    item.dias_folga = dias_folga
    item.hora_entrada = hora_entrada
    item.hora_saida = hora_saida
    item.sync_tipo()
    if 'ativo' in data:
        item.ativo = _parse_bool(data.get('ativo'), True)
    elif item.id is None:
        item.ativo = True
    return item, None


@acesso.route('/acesso/api/escalas', methods=['GET', 'POST'])
@login_required
def api_escalas():
    seed_acesso()
    if request.method == 'GET':
        q = (request.args.get('q') or '').strip()
        status = (request.args.get('status') or '').strip().lower()
        query = AcessoEscala.query
        if q:
            query = query.filter(AcessoEscala.nome_pessoa.ilike(f'%{q}%'))
        if status == 'ativo':
            query = query.filter(AcessoEscala.ativo.is_(True))
        elif status == 'inativo':
            query = query.filter(AcessoEscala.ativo.is_(False))
        items = query.order_by(
            AcessoEscala.nome_pessoa.asc(),
            AcessoEscala.data_inicio.desc(),
        ).limit(500).all()
        return jsonify([e.to_dict() for e in items])

    data = request.get_json(silent=True) or request.form or {}
    item, err = _escala_from_payload(data)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'escala': item.to_dict()}), 201


@acesso.route('/acesso/api/escalas/<int:eid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_escala_item(eid):
    seed_acesso()
    item = AcessoEscala.query.get_or_404(eid)

    if request.method == 'GET':
        return jsonify({'ok': True, 'escala': item.to_dict()})

    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    item, err = _escala_from_payload(data, item=item)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.commit()
    return jsonify({'ok': True, 'escala': item.to_dict()})


def _parse_date_arg(value):
    raw = (value or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _relatorio_eventos_query(
    inicio=None,
    fim=None,
    sentido='',
    status='',
    q='',
    tab='',
    equipamento_id='',
    event_type='',
):
    """Filtro compartilhado da página Relatório de Eventos e do export CSV."""
    query = AcessoEvento.query
    if inicio:
        query = query.filter(AcessoEvento.data_hora >= datetime.combine(inicio, time.min))
    if fim:
        query = query.filter(AcessoEvento.data_hora <= datetime.combine(fim, time.max))
    if sentido:
        query = query.filter(AcessoEvento.direction == sentido)
    if status:
        st = status.strip()
        if st == 'Liberado':
            query = query.filter(AcessoEvento.status == 'Liberado').filter(
                or_(AcessoEvento.girou.is_(None), AcessoEvento.girou != 'GIVE UP')
            )
        elif st == 'Negado':
            query = query.filter(AcessoEvento.status == 'Negado')
        elif st in ('Desistência', 'Desistencia'):
            query = query.filter(or_(
                AcessoEvento.status == 'Desistência',
                AcessoEvento.girou == 'GIVE UP',
            ))
        else:
            query = query.filter(AcessoEvento.status == st)
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoEvento.nome.ilike(like),
            AcessoEvento.pessoa_ref.ilike(like),
            AcessoEvento.equipamento_nome.ilike(like),
        ))
    tab_key = (tab or 'eventos').strip().lower()
    if tab_key == 'usuarios':
        query = query.filter(func.upper(AcessoEvento.tipo_pessoa) == 'PESSOA')
    elif tab_key == 'visitantes':
        query = query.filter(func.upper(AcessoEvento.tipo_pessoa) == 'VISITANTE')
    if equipamento_id:
        try:
            query = query.filter(AcessoEvento.equipamento_id == int(equipamento_id))
        except (TypeError, ValueError):
            pass
    if event_type:
        query = query.filter(AcessoEvento.event_type == event_type)
    return query


def _kpis_eventos(query):
    total = entradas = saidas = negados = 0
    rows = query.with_entities(
        AcessoEvento.direction, AcessoEvento.status, AcessoEvento.girou,
    ).all()
    for direction, status, girou in rows:
        total += 1
        d = (direction or '').strip().lower()
        if d == 'entrada':
            entradas += 1
        elif d in ('saída', 'saida'):
            saidas += 1
        st = status or ''
        if st == 'Negado' and (girou or '').upper() != 'GIVE UP':
            negados += 1
    return {
        'total': total,
        'entradas': entradas,
        'saidas': saidas,
        'negados': negados,
    }


def _eventos_filter_args():
    hoje = date.today()
    inicio = _parse_date_arg(request.args.get('inicio'))
    fim = _parse_date_arg(request.args.get('fim'))
    # padrão: últimos 7 dias quando nenhum período informado
    if inicio is None and fim is None and 'inicio' not in request.args and 'fim' not in request.args:
        inicio = hoje - timedelta(days=6)
        fim = hoje
    sentido = (request.args.get('sentido') or '').strip()
    status = (request.args.get('status') or '').strip()
    q = (request.args.get('q') or '').strip()
    tab = (request.args.get('tab') or 'eventos').strip().lower()
    if tab not in ('eventos', 'usuarios', 'visitantes'):
        tab = 'eventos'
    equipamento_id = (request.args.get('equipamento_id') or '').strip()
    event_type = (request.args.get('event_type') or '').strip()
    return {
        'inicio': inicio,
        'fim': fim,
        'sentido': sentido,
        'status': status,
        'q': q,
        'tab': tab,
        'equipamento_id': equipamento_id,
        'event_type': event_type,
    }


@acesso.route('/acesso/eventos')
@login_required
def eventos_page():
    seed_acesso()
    f = _eventos_filter_args()
    query = _relatorio_eventos_query(**f)
    kpis = _kpis_eventos(query)
    eventos = query.order_by(AcessoEvento.data_hora.desc()).limit(500).all()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    return render_template(
        'acesso_eventos.html',
        eventos=_eventos_to_dicts_com_foto(eventos),
        equipamentos=[eq.to_dict() for eq in equipamentos],
        kpis=kpis,
        inicio=f['inicio'].isoformat() if f['inicio'] else '',
        fim=f['fim'].isoformat() if f['fim'] else '',
        sentido=f['sentido'],
        status=f['status'],
        q=f['q'],
        tab=f['tab'],
        equipamento_id=f['equipamento_id'],
        event_type=f['event_type'],
        active_page='eventos',
    )


@acesso.route('/acesso/eventos/export.csv')
@login_required
def eventos_export_csv():
    seed_acesso()
    f = _eventos_filter_args()
    query = _relatorio_eventos_query(**f)
    eventos = query.order_by(AcessoEvento.data_hora.desc()).limit(5000).all()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow([
        'data_hora', 'nome', 'pessoa_ref', 'tipo_pessoa', 'equipamento',
        'sentido', 'status', 'modo', 'motivo',
    ])
    for e in eventos:
        d = e.to_dict()
        writer.writerow([
            d['data_hora'], d['nome'], d['pessoa_ref'], d['tipo_pessoa'],
            d['equipamento_nome'], d['direction'], d['status'],
            d['event_type'], d['motivo'],
        ])
    data = '\ufeff' + buf.getvalue()
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=relatorio_eventos.csv'},
    )


@acesso.route('/acesso/ambientes')
@login_required
def ambientes_page():
    seed_acesso()
    ambientes = [
        a.to_dict(detalhe=True)
        for a in AcessoAmbiente.query.order_by(AcessoAmbiente.nome).all()
    ]
    equipamentos = [
        e.to_dict()
        for e in AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    ]
    equip_labels = {
        str(e['id']): (e['nome'] + (f" ({e['ip']})" if e.get('ip') else ''))
        for e in equipamentos
    }
    return render_template(
        'acesso_ambientes.html',
        ambientes=ambientes,
        equipamentos=equipamentos,
        equip_labels=equip_labels,
        active_page='ambientes',
    )


PUBLICO_OPCOES = ('funcionarios', 'alunos', 'visitantes', 'responsaveis')
FLUXO_OPCOES = ('entrada', 'saida', 'ambos')


def _parse_publico(value):
    if value is None:
        return ''
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith('['):
            try:
                value = json.loads(raw)
            except Exception:
                value = [p.strip() for p in raw.split(',') if p.strip()]
        else:
            value = [p.strip() for p in raw.split(',') if p.strip()]
    if not isinstance(value, (list, tuple)):
        return ''
    out = []
    for item in value:
        key = str(item or '').strip().lower()
        aliases = {
            'funcionário': 'funcionarios',
            'funcionarios': 'funcionarios',
            'aluno': 'alunos',
            'alunos': 'alunos',
            'visitante': 'visitantes',
            'visitantes': 'visitantes',
            'responsavel': 'responsaveis',
            'responsável': 'responsaveis',
            'responsaveis': 'responsaveis',
        }
        key = aliases.get(key, key)
        if key in PUBLICO_OPCOES and key not in out:
            out.append(key)
    return ','.join(out)


def _normalize_fluxo(value):
    fluxo = (value or 'entrada').strip().lower()
    aliases = {
        'entrada': 'entrada',
        'saida': 'saida',
        'saída': 'saida',
        'ambos': 'ambos',
        'entrada/saida': 'ambos',
        'entrada/saída': 'ambos',
    }
    fluxo = aliases.get(fluxo, fluxo)
    return fluxo if fluxo in FLUXO_OPCOES else 'entrada'


def _sync_ambiente_equipamentos(ambiente, vinculos):
    """Substitui vínculos equipamento+fluxo do ambiente."""
    AcessoAmbienteEquipamento.query.filter_by(ambiente_id=ambiente.id).delete()
    if not vinculos:
        return
    if isinstance(vinculos, str):
        try:
            vinculos = json.loads(vinculos)
        except Exception:
            vinculos = []
    seen = set()
    for item in vinculos or []:
        if not isinstance(item, dict):
            continue
        eid = _parse_int(item.get('equipamento_id') or item.get('id'))
        if not eid or eid in seen:
            continue
        eq = AcessoEquipamento.query.get(eid)
        if not eq:
            continue
        seen.add(eid)
        db.session.add(AcessoAmbienteEquipamento(
            ambiente_id=ambiente.id,
            equipamento_id=eid,
            fluxo=_normalize_fluxo(item.get('fluxo')),
        ))


def _apply_ambiente_payload(ambiente, data, creating=False, sync_equipamentos=True):
    nome = (data.get('nome') or '').strip()
    if creating or 'nome' in data:
        if not nome:
            return 'Nome do ambiente é obrigatório'
        q = AcessoAmbiente.query.filter(AcessoAmbiente.nome == nome)
        if ambiente.id:
            q = q.filter(AcessoAmbiente.id != ambiente.id)
        if q.first():
            return 'Já existe um ambiente com este nome'
        ambiente.nome = nome

    if creating or 'descricao' in data:
        ambiente.descricao = (data.get('descricao') or '').strip() or None

    if creating or 'capacidade_maxima' in data:
        cap = _parse_int(data.get('capacidade_maxima'))
        if cap is None:
            cap = 10 if creating else (ambiente.capacidade_maxima or 10)
        ambiente.capacidade_maxima = max(0, cap)

    if 'ocupacao_atual' in data:
        occ = _parse_int(data.get('ocupacao_atual'))
        if occ is not None:
            ambiente.ocupacao_atual = max(0, occ)

    if creating or 'vigencia_tipo' in data:
        vigencia = (data.get('vigencia_tipo') or 'definitivo').strip().lower()
        if vigencia not in ('definitivo', 'temporario'):
            vigencia = 'definitivo'
        ambiente.vigencia_tipo = vigencia

    if creating or 'data_fim' in data or 'vigencia_tipo' in data:
        if (ambiente.vigencia_tipo or '') == 'temporario':
            ambiente.data_fim = _parse_date(data.get('data_fim'))
            if not ambiente.data_fim and (creating or 'data_fim' in data):
                return 'Informe a data fim para vigência temporária'
        else:
            ambiente.data_fim = None

    if creating or 'publico' in data:
        ambiente.publico = _parse_publico(data.get('publico'))

    if 'ativo' in data:
        ambiente.ativo = _parse_bool(data.get('ativo'), True)
    elif creating:
        ambiente.ativo = True

    if sync_equipamentos and (creating or 'equipamentos' in data or 'vinculos' in data):
        if not ambiente.id:
            return None  # caller deve flush e sincronizar
        _sync_ambiente_equipamentos(
            ambiente,
            data.get('equipamentos', data.get('vinculos')),
        )
    return None


@acesso.route('/acesso/api/ambientes', methods=['GET', 'POST'])
@login_required
def api_ambientes():
    seed_acesso()
    if request.method == 'GET':
        return jsonify([
            a.to_dict(detalhe=True)
            for a in AcessoAmbiente.query.order_by(AcessoAmbiente.nome).all()
        ])

    data = request.get_json(silent=True) or request.form or {}
    amb = AcessoAmbiente(ocupacao_atual=0, capacidade_maxima=10, vigencia_tipo='definitivo')
    err = _apply_ambiente_payload(amb, data, creating=True, sync_equipamentos=False)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    db.session.add(amb)
    db.session.flush()
    _sync_ambiente_equipamentos(amb, data.get('equipamentos', data.get('vinculos')))
    db.session.commit()
    return jsonify({'ok': True, 'ambiente': amb.to_dict(detalhe=True)}), 201


@acesso.route('/acesso/api/ambientes/<int:aid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_ambiente_item(aid):
    seed_acesso()
    amb = AcessoAmbiente.query.get_or_404(aid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'ambiente': amb.to_dict(detalhe=True)})

    if request.method == 'DELETE':
        db.session.delete(amb)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    err = _apply_ambiente_payload(amb, data, creating=False)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    db.session.commit()
    return jsonify({'ok': True, 'ambiente': amb.to_dict(detalhe=True)})


EST_PERM_TIPOS = (
    ('funcionarios', 'Funcionários'),
    ('visitantes', 'Visitantes'),
    ('alunos', 'Alunos'),
    ('responsaveis', 'Responsáveis'),
)
EST_FLUXO_OPCOES = ('entrada', 'saida')


def _estacionamento_permissoes_opcoes():
    opcoes = [
        {'chave': chave, 'label': label, 'grupo_id': None}
        for chave, label in EST_PERM_TIPOS
    ]
    for g in AcessoGrupo.query.filter_by(ativo=True).order_by(AcessoGrupo.nome).all():
        opcoes.append({
            'chave': f'grupo:{g.id}',
            'label': f'Grupo: {g.nome}',
            'grupo_id': g.id,
        })
    return opcoes


def _normalize_est_fluxo(value):
    fluxo = (value or 'entrada').strip().lower()
    aliases = {
        'entrada': 'entrada',
        'saida': 'saida',
        'saída': 'saida',
    }
    fluxo = aliases.get(fluxo, fluxo)
    return fluxo if fluxo in EST_FLUXO_OPCOES else 'entrada'


def _sync_estacionamento_equipamentos(est, vinculos):
    AcessoEstacionamentoEquipamento.query.filter_by(estacionamento_id=est.id).delete()
    if not vinculos:
        return
    if isinstance(vinculos, str):
        try:
            vinculos = json.loads(vinculos)
        except Exception:
            vinculos = []
    seen = set()
    for item in vinculos or []:
        if not isinstance(item, dict):
            continue
        eid = _parse_int(item.get('equipamento_id') or item.get('id'))
        if not eid or eid in seen:
            continue
        if not AcessoEquipamento.query.get(eid):
            continue
        seen.add(eid)
        db.session.add(AcessoEstacionamentoEquipamento(
            estacionamento_id=est.id,
            equipamento_id=eid,
            fluxo=_normalize_est_fluxo(item.get('fluxo')),
        ))


def _sync_estacionamento_permissoes(est, vinculos):
    AcessoEstacionamentoPermissao.query.filter_by(estacionamento_id=est.id).delete()
    if not vinculos:
        return
    if isinstance(vinculos, str):
        try:
            vinculos = json.loads(vinculos)
        except Exception:
            vinculos = []
    tipo_map = dict(EST_PERM_TIPOS)
    seen = set()
    for item in vinculos or []:
        if not isinstance(item, dict):
            continue
        chave = (item.get('chave') or '').strip()
        if not chave or chave in seen:
            continue
        grupo_id = _parse_int(item.get('grupo_id'))
        label = (item.get('label') or '').strip()
        if chave.startswith('grupo:'):
            gid = _parse_int(chave.split(':', 1)[1]) or grupo_id
            grupo = AcessoGrupo.query.get(gid) if gid else None
            if not grupo:
                continue
            chave = f'grupo:{grupo.id}'
            grupo_id = grupo.id
            label = label or f'Grupo: {grupo.nome}'
        elif chave in tipo_map:
            label = label or tipo_map[chave]
            grupo_id = None
        else:
            continue
        vagas = _parse_int(item.get('vagas'))
        if vagas is None:
            vagas = 1
        seen.add(chave)
        db.session.add(AcessoEstacionamentoPermissao(
            estacionamento_id=est.id,
            chave=chave,
            label=label,
            grupo_id=grupo_id,
            vagas=max(1, vagas),
        ))


def _apply_estacionamento_payload(est, data, creating=False):
    nome = (data.get('nome') or '').strip()
    if creating or 'nome' in data:
        if not nome:
            return 'Nome do estacionamento é obrigatório'
        q = AcessoEstacionamento.query.filter(AcessoEstacionamento.nome == nome)
        if est.id:
            q = q.filter(AcessoEstacionamento.id != est.id)
        if q.first():
            return 'Já existe um estacionamento com este nome'
        est.nome = nome

    if creating or 'capacidade_total' in data:
        cap = _parse_int(data.get('capacidade_total'))
        if cap is None:
            cap = 50 if creating else (est.capacidade_total if est.capacidade_total is not None else 50)
        est.capacidade_total = max(0, cap)

    if 'ocupacao_atual' in data:
        occ = _parse_int(data.get('ocupacao_atual'))
        if occ is not None:
            est.ocupacao_atual = max(0, occ)

    if 'ativo' in data or 'status' in data:
        raw = data.get('ativo') if 'ativo' in data else data.get('status')
        if isinstance(raw, str) and raw.strip().lower() in ('ativo', 'inativo'):
            est.ativo = raw.strip().lower() == 'ativo'
        else:
            est.ativo = _parse_bool(raw, True)
    elif creating:
        est.ativo = True

    if creating or 'hora_inicio' in data:
        est.hora_inicio = _parse_time(data.get('hora_inicio'))
    if creating or 'hora_fim' in data:
        est.hora_fim = _parse_time(data.get('hora_fim'))

    if creating or 'equipamentos' in data or 'vinculos' in data:
        _sync_estacionamento_equipamentos(
            est, data.get('equipamentos', data.get('vinculos')),
        )
    if creating or 'permissoes' in data:
        _sync_estacionamento_permissoes(est, data.get('permissoes'))
    return None


@acesso.route('/acesso/estacionamentos')
@login_required
def estacionamentos_page():
    seed_acesso()
    estacionamentos = [
        e.to_dict(detalhe=True)
        for e in AcessoEstacionamento.query.order_by(AcessoEstacionamento.nome).all()
    ]
    equipamentos = [
        e.to_dict()
        for e in AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    ]
    return render_template(
        'acesso_estacionamentos.html',
        estacionamentos=estacionamentos,
        equipamentos=equipamentos,
        permissoes_opcoes=_estacionamento_permissoes_opcoes(),
        active_page='estacionamentos',
    )


@acesso.route('/acesso/api/estacionamentos', methods=['GET', 'POST'])
@login_required
def api_estacionamentos():
    seed_acesso()
    if request.method == 'GET':
        return jsonify([
            e.to_dict(detalhe=True)
            for e in AcessoEstacionamento.query.order_by(AcessoEstacionamento.nome).all()
        ])

    data = request.get_json(silent=True) or request.form or {}
    est = AcessoEstacionamento(ocupacao_atual=0, capacidade_total=50, ativo=True)
    db.session.add(est)
    db.session.flush()
    err = _apply_estacionamento_payload(est, data, creating=True)
    if err:
        db.session.rollback()
        return jsonify({'ok': False, 'error': err}), 400
    db.session.commit()
    return jsonify({'ok': True, 'estacionamento': est.to_dict(detalhe=True)}), 201


@acesso.route('/acesso/api/estacionamentos/<int:eid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_estacionamento_item(eid):
    seed_acesso()
    est = AcessoEstacionamento.query.get_or_404(eid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'estacionamento': est.to_dict(detalhe=True)})

    if request.method == 'DELETE':
        db.session.delete(est)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    err = _apply_estacionamento_payload(est, data, creating=False)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    db.session.commit()
    return jsonify({'ok': True, 'estacionamento': est.to_dict(detalhe=True)})


@acesso.route('/acesso/impressoras')
@login_required
def impressoras_page():
    seed_acesso()
    return render_template(
        'acesso_impressoras.html',
        active_page='impressoras',
        tipos_impressora=list(AcessoImpressora.TIPOS),
    )


def _apply_impressora_payload(imp, data, creating=False):
    nome = (data.get('nome') or '').strip()
    if not nome:
        return 'Nome Identificador é obrigatório'
    q = AcessoImpressora.query.filter(AcessoImpressora.nome == nome)
    if not creating and imp.id:
        q = q.filter(AcessoImpressora.id != imp.id)
    if q.first():
        return 'Já existe uma impressora com este nome'

    ip = (data.get('ip') or '').strip()
    if not ip:
        return 'IP na Rede é obrigatório'

    porta = _parse_int(data.get('porta'))
    if porta is None:
        porta = 9100
    if porta < 1 or porta > 65535:
        return 'Porta inválida (1–65535)'

    tipo = (data.get('tipo') or '').strip() or AcessoImpressora.TIPOS[0]
    if tipo not in AcessoImpressora.TIPOS:
        # permite valor custom se vier de dados antigos, mas limita tamanho
        tipo = tipo[:80]

    ativo = _parse_bool(data.get('ativo'), default=True if creating else bool(imp.ativo))
    padrao = _parse_bool(data.get('padrao_voucher'), default=False)

    imp.nome = nome
    imp.ip = ip
    imp.porta = porta
    imp.tipo = tipo
    imp.ativo = ativo
    imp.padrao_voucher = padrao
    return None


def _ensure_unico_padrao_voucher(imp):
    """Garante no máximo uma impressora marcada como padrão para vouchers."""
    if not imp.padrao_voucher:
        return
    AcessoImpressora.query.filter(
        AcessoImpressora.id != imp.id,
        AcessoImpressora.padrao_voucher.is_(True),
    ).update({'padrao_voucher': False}, synchronize_session=False)


@acesso.route('/acesso/api/impressoras', methods=['GET', 'POST'])
@login_required
def api_impressoras():
    seed_acesso()
    if request.method == 'GET':
        itens = AcessoImpressora.query.order_by(
            AcessoImpressora.padrao_voucher.desc(),
            AcessoImpressora.nome,
        ).all()
        return jsonify([i.to_dict() for i in itens])

    data = request.get_json(silent=True) or {}
    imp = AcessoImpressora()
    err = _apply_impressora_payload(imp, data, creating=True)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    db.session.add(imp)
    db.session.flush()
    _ensure_unico_padrao_voucher(imp)
    db.session.commit()
    return jsonify({'ok': True, 'impressora': imp.to_dict()}), 201


@acesso.route('/acesso/api/impressoras/<int:iid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_impressora_item(iid):
    seed_acesso()
    imp = AcessoImpressora.query.get_or_404(iid)
    if request.method == 'GET':
        return jsonify(imp.to_dict())

    if request.method == 'DELETE':
        db.session.delete(imp)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    err = _apply_impressora_payload(imp, data, creating=False)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    _ensure_unico_padrao_voucher(imp)
    db.session.commit()
    return jsonify({'ok': True, 'impressora': imp.to_dict()})


# ---- Parâmetros ----
@acesso.route('/acesso/parametros/controle-adicional')
@login_required
def controle_adicional_page():
    seed_acesso()
    nome = (request.args.get('nome') or '').strip()
    de = _parse_date(request.args.get('de'))
    ate = _parse_date(request.args.get('ate'))
    tipo = (request.args.get('tipo') or '').strip().lower()
    mostrar_expirados = _parse_bool(request.args.get('expirados'), False)

    query = AcessoControleAdicional.query
    if nome:
        query = query.filter(AcessoControleAdicional.nome.ilike(f'%{nome}%'))
    if de:
        query = query.filter(AcessoControleAdicional.data_inicio >= de)
    if ate:
        query = query.filter(AcessoControleAdicional.data_inicio <= ate)
    if tipo in ('bloqueio', 'liberacao'):
        query = query.filter(AcessoControleAdicional.tipo == tipo)
    if not mostrar_expirados:
        hoje = date.today()
        query = query.filter(
            or_(
                AcessoControleAdicional.data_fim.is_(None),
                AcessoControleAdicional.data_fim >= hoje,
            )
        )

    controles = [
        c.to_dict()
        for c in query.order_by(
            AcessoControleAdicional.data_inicio.desc(),
            AcessoControleAdicional.id.desc(),
        ).limit(500).all()
    ]
    pessoas = (
        AcessoPessoa.query
        .order_by(AcessoPessoa.nome.asc())
        .limit(2000)
        .all()
    )
    return render_template(
        'acesso_controle_adicional.html',
        active_page='controle_adicional',
        controles=controles,
        pessoas=pessoas,
        filtros={
            'nome': nome,
            'de': de.isoformat() if de else '',
            'ate': ate.isoformat() if ate else '',
            'tipo': tipo if tipo in ('bloqueio', 'liberacao') else '',
            'expirados': mostrar_expirados,
        },
    )


@acesso.route('/acesso/parametros/refeicoes')
@login_required
def parametros_refeicoes_page():
    seed_acesso()
    return render_template(
        'acesso_param_refeicoes.html',
        active_page='param_refeicoes',
    )


@acesso.route('/acesso/parametros/documentos')
@login_required
def parametros_documentos_page():
    seed_acesso()
    cats = _catalogos()
    return render_template(
        'acesso_param_documentos.html',
        active_page='param_documentos',
        **cats,
    )


def _veiculos_periodo_bounds(periodo):
    """Retorna (ini, fim) para filtros do relatório de veículos."""
    key = (periodo or 'hoje').strip().lower()
    hoje = date.today()
    if key in ('ontem', 'yesterday'):
        d = hoje - timedelta(days=1)
        return datetime.combine(d, time.min), datetime.combine(d, time.max)
    if key in ('7dias', '7days', '7'):
        return (
            datetime.combine(hoje - timedelta(days=6), time.min),
            datetime.combine(hoje, time.max),
        )
    if key in ('todos', 'all'):
        return None, None
    # hoje / today (default)
    return datetime.combine(hoje, time.min), datetime.combine(hoje, time.max)


def _veiculos_filter_args():
    periodo = (request.args.get('periodo') or 'hoje').strip().lower()
    if periodo in ('today',):
        periodo = 'hoje'
    elif periodo in ('yesterday',):
        periodo = 'ontem'
    elif periodo in ('7days', '7'):
        periodo = '7dias'
    elif periodo in ('all',):
        periodo = 'todos'
    if periodo not in ('hoje', 'ontem', '7dias', 'todos'):
        periodo = 'hoje'
    equipamento = (request.args.get('equipamento') or '').strip()
    sentido = (request.args.get('sentido') or '').strip()
    placa = (request.args.get('placa') or '').strip().upper().replace('-', '').replace(' ', '')
    try:
        page = max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(100, max(10, int(request.args.get('per_page') or 25)))
    except (TypeError, ValueError):
        per_page = 25
    return {
        'periodo': periodo,
        'equipamento': equipamento,
        'sentido': sentido,
        'placa': placa,
        'page': page,
        'per_page': per_page,
    }


def _veiculos_query(f):
    """Query AcessoVeiculoEvento com filtros; lista vazia se tabela sem dados."""
    q = AcessoVeiculoEvento.query
    ini, fim = _veiculos_periodo_bounds(f['periodo'])
    if ini is not None:
        q = q.filter(AcessoVeiculoEvento.data_hora >= ini)
    if fim is not None:
        q = q.filter(AcessoVeiculoEvento.data_hora <= fim)
    if f['equipamento']:
        q = q.filter(AcessoVeiculoEvento.equipamento == f['equipamento'])
    if f['sentido'] in ('Entrada', 'Saída'):
        q = q.filter(AcessoVeiculoEvento.sentido == f['sentido'])
    if f['placa']:
        q = q.filter(AcessoVeiculoEvento.placa.ilike(f"%{f['placa']}%"))
    return q


@acesso.route('/acesso/veiculos')
@login_required
def veiculos_page():
    seed_acesso()
    f = _veiculos_filter_args()
    query = _veiculos_query(f)
    total = query.count() or 0
    total_pages = max(1, (total + f['per_page'] - 1) // f['per_page']) if total else 1
    page = min(f['page'], total_pages)
    rows = (
        query.order_by(AcessoVeiculoEvento.data_hora.desc())
        .offset((page - 1) * f['per_page'])
        .limit(f['per_page'])
        .all()
    )
    equipamentos = (
        AcessoEquipamento.query.filter_by(ativo=True)
        .order_by(AcessoEquipamento.nome)
        .all()
    )
    # Nomes distintos já usados em eventos (além do cadastro)
    eq_nomes = {e.nome for e in equipamentos if e.nome}
    try:
        for (nome,) in (
            db.session.query(AcessoVeiculoEvento.equipamento)
            .filter(AcessoVeiculoEvento.equipamento.isnot(None))
            .filter(AcessoVeiculoEvento.equipamento != '')
            .distinct()
            .all()
        ):
            if nome:
                eq_nomes.add(nome)
    except Exception:
        pass
    return render_template(
        'acesso_veiculos.html',
        active_page='veiculos',
        eventos=[e.to_dict() for e in rows],
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=f['per_page'],
        periodo=f['periodo'],
        equipamento=f['equipamento'],
        sentido=f['sentido'],
        placa=f['placa'],
        equipamentos=sorted(eq_nomes),
    )


@acesso.route('/acesso/veiculos/export.csv')
@login_required
def veiculos_export_csv():
    seed_acesso()
    f = _veiculos_filter_args()
    query = _veiculos_query(f)
    eventos = query.order_by(AcessoVeiculoEvento.data_hora.desc()).limit(10000).all()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow(['data_hora', 'usuario', 'placa', 'equipamento', 'sentido', 'status'])
    for e in eventos:
        d = e.to_dict()
        writer.writerow([
            d['data_hora'], d['usuario_nome'], d['placa'],
            d['equipamento'], d['sentido'], d['status'],
        ])
    data = '\ufeff' + buf.getvalue()
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=relatorio_veiculos.csv'},
    )


def _parse_datetime_arg(value, end_of_day=False):
    """Aceita datetime-local, data+hora ou só data (YYYY-MM-DD)."""
    raw = (value or '').strip()
    if not raw:
        return None
    raw = raw.replace(' ', 'T', 1) if ' ' in raw and 'T' not in raw else raw
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(raw, fmt)
            if fmt == '%Y-%m-%d' and end_of_day:
                return datetime.combine(dt.date(), time.max.replace(microsecond=0))
            return dt
        except ValueError:
            continue
    return None


def _fmt_datetime_local(dt):
    if not dt:
        return ''
    return dt.strftime('%Y-%m-%dT%H:%M')


def _fmt_duracao_hms(seconds):
    if seconds is None or seconds < 0:
        return '—'
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


def _evento_local(evento, eq_local_map):
    nome = (evento.equipamento_nome or '').strip()
    if evento.equipamento_id and evento.equipamento_id in eq_local_map:
        local = (eq_local_map[evento.equipamento_id] or '').strip()
        if local:
            return local
    return nome or '—'


def _is_entrada(direction):
    return (direction or '').strip().lower() == 'entrada'


def _is_saida(direction):
    d = (direction or '').strip().lower()
    return d in ('saída', 'saida')


def _permanencia_person_key(evento):
    ref = (evento.pessoa_ref or '').strip()
    if ref:
        return ('ref', ref)
    return ('nome', (evento.nome or '').strip().upper())


def _permanencia_filter_args():
    hoje = date.today()
    inicio = _parse_datetime_arg(request.args.get('inicio'))
    fim = _parse_datetime_arg(request.args.get('fim'), end_of_day=True)
    if inicio is None and fim is None and 'inicio' not in request.args and 'fim' not in request.args:
        inicio = datetime.combine(hoje, time.min)
        fim = datetime.combine(hoje, time.max.replace(microsecond=0))
    tab = (request.args.get('tab') or 'todos').strip().lower()
    if tab not in ('todos', 'pessoas', 'visitantes'):
        tab = 'todos'
    return {
        'inicio': inicio,
        'fim': fim,
        'nome': (request.args.get('nome') or '').strip(),
        'matricula': (request.args.get('matricula') or '').strip(),
        'empresa_id': (request.args.get('empresa_id') or '').strip(),
        'setor_id': (request.args.get('setor_id') or '').strip(),
        'departamento_id': (request.args.get('departamento_id') or '').strip(),
        'classificacao_id': (request.args.get('classificacao_id') or '').strip(),
        'fluxo': (request.args.get('fluxo') or 'global').strip().lower() or 'global',
        'tab': tab,
    }


def _permanencia_eventos_query(f):
    """Eventos liberados de entrada/saída no período (base do cálculo de permanência)."""
    query = AcessoEvento.query.filter(
        AcessoEvento.status == 'Liberado',
        or_(AcessoEvento.girou.is_(None), AcessoEvento.girou != 'GIVE UP'),
        AcessoEvento.direction.in_([
            'Entrada', 'entrada', 'ENTRADA',
            'Saída', 'Saida', 'saída', 'saida', 'SAÍDA', 'SAIDA',
        ]),
    )
    if f['inicio']:
        query = query.filter(AcessoEvento.data_hora >= f['inicio'])
    if f['fim']:
        query = query.filter(AcessoEvento.data_hora <= f['fim'])
    if f['nome']:
        query = query.filter(AcessoEvento.nome.ilike(f"%{f['nome']}%"))
    if f['matricula']:
        query = query.filter(AcessoEvento.pessoa_ref.ilike(f"%{f['matricula']}%"))
    tab = f['tab']
    if tab == 'pessoas':
        query = query.filter(func.upper(AcessoEvento.tipo_pessoa) == 'PESSOA')
    elif tab == 'visitantes':
        query = query.filter(func.upper(AcessoEvento.tipo_pessoa) == 'VISITANTE')
    return query.order_by(AcessoEvento.data_hora.asc())


def _lookup_permanencia_cadastros(pessoa_refs):
    """Mapas matricula/visitor_id → dados org para enriquecer linhas."""
    refs = {r for r in pessoa_refs if r}
    pessoas_map = {}
    visitantes_map = {}
    if not refs:
        return pessoas_map, visitantes_map
    for p in AcessoPessoa.query.filter(AcessoPessoa.matricula.in_(list(refs))).all():
        pessoas_map[p.matricula] = p
    for v in AcessoVisitante.query.filter(AcessoVisitante.visitor_id.in_(list(refs))).all():
        visitantes_map[v.visitor_id] = v
    return pessoas_map, visitantes_map


def _enrich_org(evento, pessoas_map, visitantes_map):
    ref = (evento.pessoa_ref or '').strip()
    tipo = (evento.tipo_pessoa or 'PESSOA').upper()
    empresa = setor = departamento = classificacao = ''
    empresa_id = setor_id = departamento_id = classificacao_id = None

    pessoa = pessoas_map.get(ref) if ref else None
    visitante = visitantes_map.get(ref) if ref else None

    if tipo == 'VISITANTE' and visitante:
        empresa = (
            visitante.empresa_ref.nome if visitante.empresa_ref
            else (visitante.empresa_visitada or '')
        )
        classificacao = visitante.classificacao_ref.descricao if visitante.classificacao_ref else ''
        empresa_id = visitante.empresa_id
        classificacao_id = visitante.classificacao_id
    elif pessoa:
        empresa = (
            pessoa.empresa_ref.nome if pessoa.empresa_ref else (pessoa.empresa or '')
        )
        setor = pessoa.setor_ref.descricao if pessoa.setor_ref else (pessoa.setor or '')
        departamento = (
            pessoa.departamento_ref.descricao if pessoa.departamento_ref
            else (pessoa.departamento or '')
        )
        classificacao = pessoa.classificacao_ref.descricao if pessoa.classificacao_ref else ''
        empresa_id = pessoa.empresa_id
        setor_id = pessoa.setor_id
        departamento_id = pessoa.departamento_id
        classificacao_id = pessoa.classificacao_id
    elif visitante:
        empresa = (
            visitante.empresa_ref.nome if visitante.empresa_ref
            else (visitante.empresa_visitada or '')
        )
        classificacao = visitante.classificacao_ref.descricao if visitante.classificacao_ref else ''
        empresa_id = visitante.empresa_id
        classificacao_id = visitante.classificacao_id

    return {
        'empresa': empresa or '—',
        'setor': setor or '—',
        'departamento': departamento or '—',
        'classificacao': classificacao or '—',
        'empresa_id': empresa_id,
        'setor_id': setor_id,
        'departamento_id': departamento_id,
        'classificacao_id': classificacao_id,
    }


def _match_org_filters(org, f):
    def _match_id(raw, value):
        if not raw:
            return True
        try:
            return value is not None and int(raw) == int(value)
        except (TypeError, ValueError):
            return True

    return (
        _match_id(f['empresa_id'], org['empresa_id'])
        and _match_id(f['setor_id'], org['setor_id'])
        and _match_id(f['departamento_id'], org['departamento_id'])
        and _match_id(f['classificacao_id'], org['classificacao_id'])
    )


def _build_permanencia_rows(eventos, f):
    """Pareia Entrada→Saída por pessoa_ref/nome e devolve linhas do relatório."""
    eq_ids = {e.equipamento_id for e in eventos if e.equipamento_id}
    eq_local_map = {}
    if eq_ids:
        for eq in AcessoEquipamento.query.filter(AcessoEquipamento.id.in_(list(eq_ids))).all():
            eq_local_map[eq.id] = eq.local or eq.nome

    refs = [(e.pessoa_ref or '').strip() for e in eventos]
    pessoas_map, visitantes_map = _lookup_permanencia_cadastros(refs)

    from collections import defaultdict
    groups = defaultdict(list)
    for e in eventos:
        groups[_permanencia_person_key(e)].append(e)

    rows = []
    for _key, seq in groups.items():
        open_entrada = None
        for e in seq:
            if _is_entrada(e.direction):
                if open_entrada is not None:
                    # Nova entrada sem saída da anterior → fecha com saída vazia
                    rows.append(_permanencia_row(
                        open_entrada, None, eq_local_map, pessoas_map, visitantes_map,
                    ))
                open_entrada = e
            elif _is_saida(e.direction):
                if open_entrada is not None:
                    rows.append(_permanencia_row(
                        open_entrada, e, eq_local_map, pessoas_map, visitantes_map,
                    ))
                    open_entrada = None
                # Saída órfã: ignora (sem entrada correspondente no período)
        if open_entrada is not None:
            rows.append(_permanencia_row(
                open_entrada, None, eq_local_map, pessoas_map, visitantes_map,
            ))

    filtered = [r for r in rows if _match_org_filters(r['_org'], f)]
    filtered.sort(key=lambda r: (r['entrada_dt'] or datetime.min), reverse=True)
    for r in filtered:
        r.pop('_org', None)
    return filtered


def _permanencia_row(entrada, saida, eq_local_map, pessoas_map, visitantes_map):
    org = _enrich_org(entrada, pessoas_map, visitantes_map)
    entrada_dt = entrada.data_hora
    saida_dt = saida.data_hora if saida else None
    duracao_s = None
    if entrada_dt and saida_dt:
        duracao_s = (saida_dt - entrada_dt).total_seconds()

    return {
        'dia': entrada_dt.strftime('%d/%m/%Y') if entrada_dt else '—',
        'nome': entrada.nome or '—',
        'matricula': (entrada.pessoa_ref or '').strip() or '—',
        'tipo_pessoa': (entrada.tipo_pessoa or 'PESSOA').upper(),
        'empresa': org['empresa'],
        'setor': org['setor'],
        'departamento': org['departamento'],
        'empresa_setor_depto': ' / '.join([
            x for x in (org['empresa'], org['setor'], org['departamento'])
            if x and x != '—'
        ]) or '—',
        'entrada_hora': entrada_dt.strftime('%H:%M:%S') if entrada_dt else '—',
        'entrada_local': _evento_local(entrada, eq_local_map),
        'saida_hora': saida_dt.strftime('%H:%M:%S') if saida_dt else '—',
        'saida_local': _evento_local(saida, eq_local_map) if saida else '—',
        'permanencia': _fmt_duracao_hms(duracao_s),
        'entrada_dt': entrada_dt,
        'saida_dt': saida_dt,
        '_org': org,
    }


def _permanencia_rows_for_request():
    seed_acesso()
    f = _permanencia_filter_args()
    eventos = _permanencia_eventos_query(f).limit(8000).all()
    rows = _build_permanencia_rows(eventos, f)
    return f, rows


@acesso.route('/acesso/permanencia')
@login_required
def permanencia_page():
    f, rows = _permanencia_rows_for_request()
    cats = _catalogos()
    try:
        from audit_service import registrar_auditoria
        registrar_auditoria(
            'relatorio_permanencia_visualizar',
            modulo='acesso',
            entidade='permanencia',
            detalhe={
                'total': len(rows),
                'tab': f['tab'],
                'inicio': _fmt_datetime_local(f['inicio']),
                'fim': _fmt_datetime_local(f['fim']),
                'filtros': {
                    'nome': f['nome'],
                    'matricula': f['matricula'],
                    'fluxo': f['fluxo'],
                },
            },
            caminho='/acesso/permanencia',
            metodo='GET',
            status_http=200,
        )
    except Exception:
        pass
    return render_template(
        'acesso_permanencia.html',
        rows=rows,
        total=len(rows),
        inicio=_fmt_datetime_local(f['inicio']),
        fim=_fmt_datetime_local(f['fim']),
        nome=f['nome'],
        matricula=f['matricula'],
        empresa_id=f['empresa_id'],
        setor_id=f['setor_id'],
        departamento_id=f['departamento_id'],
        classificacao_id=f['classificacao_id'],
        fluxo=f['fluxo'],
        tab=f['tab'],
        empresas=cats['empresas'],
        setores=cats['setores'],
        departamentos=cats['departamentos'],
        classificacoes=cats['classificacoes'],
        active_page='permanencia',
    )


@acesso.route('/acesso/permanencia/export.csv')
@login_required
def permanencia_export_csv():
    f, rows = _permanencia_rows_for_request()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow([
        'dia', 'nome', 'matricula', 'empresa', 'setor', 'departamento',
        'entrada_hora', 'entrada_local', 'saida_hora', 'saida_local', 'permanencia',
    ])
    for r in rows:
        writer.writerow([
            r['dia'], r['nome'], r['matricula'], r['empresa'], r['setor'], r['departamento'],
            r['entrada_hora'], r['entrada_local'], r['saida_hora'], r['saida_local'],
            r['permanencia'],
        ])
    data = '\ufeff' + buf.getvalue()
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=relatorio_permanencia.csv'},
    )





def _format_detalhes_json(detalhe):
    """Normaliza detalhe para bloco JSON legível na UI."""
    raw = (detalhe or '').strip()
    if not raw:
        return '{}'
    try:
        parsed = json.loads(raw)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except (TypeError, ValueError, json.JSONDecodeError):
        return json.dumps({'mensagem': raw}, ensure_ascii=False, indent=2)


def _seed_acesso_auditoria_demo():
    """Se não houver logs do módulo acesso, cria exemplos para demonstração."""
    try:
        from audit_service import ensure_audit_table, registrar_auditoria
        from models_audit import AuditLog
        ensure_audit_table()
        if AuditLog.query.filter_by(modulo='acesso').count() > 0:
            return
        agora = datetime.utcnow()
        exemplos = [
            ('login', {'origem': 'demo', 'ip': '127.0.0.1'}),
            ('relatorio_permanencia_visualizar', {'total': 12, 'tab': 'todos'}),
            ('relatorio_eventos_visualizar', {'tab': 'eventos', 'total': 48}),
            ('backup_gerar', {'arquivo': 'acesso_backup_demo.json', 'tabelas': 14}),
            ('usuario_criar', {'usuario': 'operador.demo', 'tipo': 'operador'}),
            ('permissoes_salvar', {'perfil': 'operador', 'chaves': 8}),
        ]
        nomes = ['Administrador', 'Operador Demo', 'Agente TI']
        for i, (acao, detalhe) in enumerate(exemplos):
            registrar_auditoria(
                acao,
                modulo='acesso',
                entidade=acao.split('_')[0],
                detalhe=detalhe,
                caminho=f'/acesso/auditoria/demo/{acao}',
                metodo='POST' if acao not in ('login', 'relatorio_permanencia_visualizar', 'relatorio_eventos_visualizar') else 'GET',
                status_http=200,
                usuario_nome=nomes[i % len(nomes)],
            )
            # Ajusta horário para espalhar no histórico
            row = AuditLog.query.filter_by(modulo='acesso', acao=acao).order_by(AuditLog.id.desc()).first()
            if row:
                row.data_hora = agora - timedelta(hours=i * 5, minutes=i * 7)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


@acesso.route('/acesso/auditoria')
@login_required
def auditoria_page():
    seed_acesso()
    _seed_acesso_auditoria_demo()

    from audit_service import ensure_audit_table, listar_logs
    from models_audit import AuditLog

    ensure_audit_table()

    operador = (request.args.get('operador') or '').strip()
    acao = (request.args.get('acao') or '').strip()
    data_inicial = _parse_date_arg(request.args.get('data_inicial'))
    data_final = _parse_date_arg(request.args.get('data_final'))
    ordem = (request.args.get('ordem') or 'recentes').strip().lower()
    if ordem not in ('recentes', 'antigos'):
        ordem = 'recentes'
    try:
        per_page = int(request.args.get('per_page') or 20)
    except (TypeError, ValueError):
        per_page = 20
    if per_page not in (20, 50, 100):
        per_page = 20
    try:
        page = max(int(request.args.get('page') or 1), 1)
    except (TypeError, ValueError):
        page = 1

    total, logs_raw = listar_logs(
        modulo='acesso',
        usuario=operador or None,
        acao=acao or None,
        data_de=data_inicial,
        data_ate=data_final,
        limit=per_page,
        offset=(page - 1) * per_page,
        ordem='asc' if ordem == 'antigos' else 'desc',
    )
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    if page > total_pages:
        page = total_pages
        total, logs_raw = listar_logs(
            modulo='acesso',
            usuario=operador or None,
            acao=acao or None,
            data_de=data_inicial,
            data_ate=data_final,
            limit=per_page,
            offset=(page - 1) * per_page,
            ordem='asc' if ordem == 'antigos' else 'desc',
        )

    logs = []
    for l in logs_raw:
        item = dict(l)
        item['detalhes_json'] = _format_detalhes_json(l.get('detalhe'))
        logs.append(item)

    acoes_db = (
        db.session.query(AuditLog.acao)
        .filter(AuditLog.modulo == 'acesso', AuditLog.acao.isnot(None), AuditLog.acao != '')
        .distinct()
        .order_by(AuditLog.acao.asc())
        .all()
    )
    acoes = [a[0] for a in acoes_db]
    for extra in (
        'login',
        'relatorio_permanencia_visualizar',
        'relatorio_eventos_visualizar',
        'backup_gerar',
        'usuario_criar',
        'permissoes_salvar',
        'criar',
        'editar',
        'excluir',
    ):
        if extra not in acoes:
            acoes.append(extra)
    acoes = sorted(set(acoes))

    return render_template(
        'acesso_auditoria.html',
        logs=logs,
        total=total,
        page=page,
        total_pages=total_pages,
        acoes=acoes,
        filtros={
            'operador': operador,
            'acao': acao,
            'data_inicial': data_inicial.isoformat() if data_inicial else '',
            'data_final': data_final.isoformat() if data_final else '',
            'ordem': ordem,
            'per_page': per_page,
        },
        active_page='auditoria',
    )


def _fmt_brl(valor):
    v = float(valor or 0)
    return f'R$ {v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _refeicoes_filter_args():
    """Lê filtros comuns da análise de refeições."""
    tipo_pessoa = (request.args.get('tipo_pessoa') or 'todos').strip().lower()
    if tipo_pessoa not in ('interno', 'visitante', 'todos'):
        tipo_pessoa = 'todos'
    return {
        'modo': (request.args.get('modo') or 'detalhado').strip().lower(),
        'tipo_pessoa': tipo_pessoa,
        'q': (request.args.get('q') or '').strip(),
        'de': (request.args.get('de') or '').strip(),
        'ate': (request.args.get('ate') or '').strip(),
        'empresa': (request.args.get('empresa') or '').strip(),
    }


def _refeicoes_agregar(rows, group_attr, label_key):
    """Agrupa refeições por atributo → volume, ticket médio e total."""
    buckets = {}
    for r in rows:
        raw = (getattr(r, group_attr, None) or '').strip()
        if not raw and group_attr == 'setor':
            raw = (r.setor_empresa or '').strip()
        if not raw and group_attr == 'tipo_refeicao':
            raw = 'Sem classificação'
        if not raw:
            raw = 'Não informado'
        bucket = buckets.setdefault(raw, {'volume': 0, 'total': 0.0})
        bucket['volume'] += 1
        bucket['total'] += float(r.valor or 0)

    out = []
    for key, data in sorted(buckets.items(), key=lambda kv: (-kv[1]['total'], kv[0].lower())):
        volume = data['volume']
        total = data['total']
        ticket = (total / volume) if volume else 0.0
        out.append({
            label_key: key,
            'volume': volume,
            'ticket': ticket,
            'ticket_fmt': _fmt_brl(ticket),
            'total': total,
            'total_fmt': _fmt_brl(total),
        })
    return out


def _refeicoes_query(tipo_pessoa='todos', q='', de='', ate=''):
    """Filtra AcessoRefeicao; retorna query ordenada (mais recente primeiro)."""
    query = AcessoRefeicao.query
    tipo = (tipo_pessoa or 'todos').lower()
    if tipo in ('interno', 'visitante'):
        query = query.filter(AcessoRefeicao.tipo_pessoa == tipo)
    q = (q or '').strip()
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoRefeicao.pessoa_nome.ilike(like),
            AcessoRefeicao.matricula.ilike(like),
            AcessoRefeicao.setor_empresa.ilike(like),
            AcessoRefeicao.tipo_refeicao.ilike(like),
            AcessoRefeicao.empresa.ilike(like),
            AcessoRefeicao.setor.ilike(like),
            AcessoRefeicao.classificacao.ilike(like),
        ))
    if de:
        try:
            d0 = datetime.strptime(de, '%Y-%m-%d')
            query = query.filter(AcessoRefeicao.data_hora >= d0)
        except ValueError:
            pass
    if ate:
        try:
            d1 = datetime.strptime(ate, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(AcessoRefeicao.data_hora < d1)
        except ValueError:
            pass
    return query.order_by(AcessoRefeicao.data_hora.desc())


def _refeicoes_kpis(tipo_pessoa='todos'):
    agora = datetime.utcnow()
    hoje = agora - timedelta(hours=24)
    d7 = agora - timedelta(days=7)
    d30 = agora - timedelta(days=30)

    base = AcessoRefeicao.query
    tipo = (tipo_pessoa or 'todos').lower()
    if tipo in ('interno', 'visitante'):
        base = base.filter(AcessoRefeicao.tipo_pessoa == tipo)

    def _sum_desde(dt):
        total = (
            base.filter(AcessoRefeicao.data_hora >= dt)
            .with_entities(func.coalesce(func.sum(AcessoRefeicao.valor), 0))
            .scalar()
        )
        return float(total or 0)

    return {
        'hoje': _sum_desde(hoje),
        'd7': _sum_desde(d7),
        'd30': _sum_desde(d30),
    }


@acesso.route('/acesso/refeicoes')
@login_required
def refeicoes_page():
    seed_acesso()
    modos = [
        ('diario', 'Diário'),
        ('detalhado', 'Planilha/Detalhado'),
        ('colaborador', 'Por Colaborador'),
        ('tipo', 'Por Tipo'),
        ('setor', 'Por Setor'),
        ('empresa', 'Por Empresa'),
        ('classificacao', 'Por Classificação'),
    ]
    modo = (request.args.get('modo') or 'detalhado').strip().lower()
    if modo not in {m[0] for m in modos}:
        modo = 'detalhado'
    tipo_pessoa = (request.args.get('tipo_pessoa') or 'todos').strip().lower()
    if tipo_pessoa not in ('interno', 'visitante', 'todos'):
        tipo_pessoa = 'todos'
    q = (request.args.get('q') or '').strip()
    de = (request.args.get('de') or '').strip()
    ate = (request.args.get('ate') or '').strip()

    rows = _refeicoes_query(tipo_pessoa=tipo_pessoa, q=q, de=de, ate=ate).limit(2000).all()
    refeicoes = [r.to_dict() for r in rows]
    pesquisado = sum(float(r.valor or 0) for r in rows)
    kpi_base = _refeicoes_kpis(tipo_pessoa=tipo_pessoa)
    kpis = {
        'hoje_fmt': _fmt_brl(kpi_base['hoje']),
        'd7_fmt': _fmt_brl(kpi_base['d7']),
        'd30_fmt': _fmt_brl(kpi_base['d30']),
        'pesquisado_fmt': _fmt_brl(pesquisado),
    }
    return render_template(
        'acesso_refeicoes.html',
        active_page='refeicoes',
        modos=modos,
        modo=modo,
        tipo_pessoa=tipo_pessoa,
        q_global=q,
        de=de,
        ate=ate,
        refeicoes=refeicoes,
        kpis=kpis,
    )


@acesso.route('/acesso/refeicoes/export.xls')
@login_required
def refeicoes_export():
    seed_acesso()
    f = _refeicoes_filter_args()
    rows = _refeicoes_query(
        tipo_pessoa=f['tipo_pessoa'], q=f['q'], de=f['de'], ate=f['ate'],
    ).limit(5000).all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow([
        'Data/Hora', 'Colaborador', 'Matrícula', 'Setor/Empresa',
        'Refeição', 'Valor', 'Tipo Pessoa', 'Classificação', 'Empresa', 'Setor',
    ])
    for r in rows:
        d = r.to_dict()
        writer.writerow([
            d['data_hora_fmt'], d['pessoa_nome'], d['matricula'], d['setor_empresa'],
            d['tipo_refeicao'], d['valor_fmt'], d['tipo_pessoa'],
            d['classificacao'], d['empresa'], d['setor'],
        ])
    data = '\ufeff' + buf.getvalue()
    return Response(
        data,
        mimetype='application/vnd.ms-excel; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=analise_refeicoes.xls'},
    )


@acesso.route('/acesso/refeicoes/imprimir')
@login_required
def refeicoes_imprimir():
    """Visão de impressão/PDF — relatório gerencial sem sidebar."""
    seed_acesso()
    f = _refeicoes_filter_args()
    rows = _refeicoes_query(
        tipo_pessoa=f['tipo_pessoa'], q=f['q'], de=f['de'], ate=f['ate'],
    ).limit(5000).all()
    pesquisado = sum(float(r.valor or 0) for r in rows)
    kpi_base = _refeicoes_kpis(tipo_pessoa=f['tipo_pessoa'])
    kpis = {
        'hoje_fmt': _fmt_brl(kpi_base['hoje']),
        'd7_fmt': _fmt_brl(kpi_base['d7']),
        'd30_fmt': _fmt_brl(kpi_base['d30']),
        'pesquisado_fmt': _fmt_brl(pesquisado),
    }

    resumo_itens = _refeicoes_agregar(rows, 'tipo_refeicao', 'item')
    detalhe_setor = _refeicoes_agregar(rows, 'setor', 'setor')

    empresa_nome = f['empresa']
    if not empresa_nome:
        emp = AcessoEmpresa.query.filter_by(ativo=True).order_by(AcessoEmpresa.nome).first()
        if not emp:
            emp = AcessoEmpresa.query.order_by(AcessoEmpresa.nome).first()
        empresa_nome = emp.nome if emp else 'SGHN - HIGIENIZACAO TEXTIL E NUTRICAO HOSPITALAR LTDA'

    return render_template(
        'acesso_refeicoes_print.html',
        kpis=kpis,
        resumo_itens=resumo_itens,
        detalhe_setor=detalhe_setor,
        empresa_nome=empresa_nome,
        pagina=1,
        total_paginas=1,
        gerado_em=datetime.now().strftime('%d/%m/%Y %H:%M'),
        modo=f['modo'],
        tipo_pessoa=f['tipo_pessoa'],
        q_global=f['q'],
        de=f['de'],
        ate=f['ate'],
    )


@acesso.route('/acesso/sobre')
@login_required
def sobre_page():
    return render_template(
        'acesso_sobre.html',
        active_page='sobre',
    )


# ---- Administração: Usuários / Permissões / Backup / Documentação / Sollus ----
@acesso.route('/acesso/usuarios')
@login_required
def usuarios_page():
    seed_acesso()
    q = (request.args.get('q') or '').strip()
    query = Usuario.query
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            Usuario.nome.ilike(like),
            Usuario.email.ilike(like),
            Usuario.usuario.ilike(like),
        ))
    usuarios = query.order_by(Usuario.nome).all()
    return render_template(
        'acesso_usuarios.html',
        usuarios=[_usuario_to_dict(u) for u in usuarios],
        tipos=[{'value': k, 'label': v} for k, v in TIPO_LABELS.items()],
        search=q,
        total=len(usuarios),
        active_page='usuarios',
    )


@acesso.route('/acesso/permissoes')
@login_required
def permissoes_page():
    seed_acesso()
    perfis = [{'value': k, 'label': v} for k, v in TIPO_LABELS.items()]
    raw_perfil = (request.args.get('perfil') or '').strip().lower()
    perfil = raw_perfil if raw_perfil in TIPO_LABELS else ''
    selecionadas = set(_perfil_permissoes(perfil)) if perfil else set()
    return render_template(
        'acesso_permissoes.html',
        perfis=perfis,
        perfil=perfil,
        perfil_label=TIPO_LABELS.get(perfil, '') if perfil else '',
        matriz=ACESSO_MATRIZ_PERMISSOES,
        selecionadas=selecionadas,
        active_page='permissoes',
    )


@acesso.route('/acesso/backup')
@login_required
def backup_page():
    seed_acesso()
    cfg = _get_backup_config()
    logs = AcessoBackupLog.query.order_by(AcessoBackupLog.data_criacao.desc()).limit(50).all()
    backups = []
    for b in logs:
        d = b.to_dict()
        d['tamanho_fmt'] = _fmt_bytes(b.tamanho_bytes)
        backups.append(d)
    return render_template(
        'acesso_backup.html',
        backups=backups,
        config=cfg.to_dict(),
        active_page='backup',
    )


@acesso.route('/acesso/documentacao')
@login_required
def documentacao_page():
    return render_template(
        'acesso_documentacao.html',
        active_page='documentacao',
    )


@acesso.route('/acesso/sollus-sync')
@login_required
def sollus_sync_page():
    return render_template(
        'acesso_sollus_sync.html',
        active_page='sollus_sync',
    )


@acesso.route('/acesso/api/backup/agendamento', methods=['GET', 'PUT', 'POST'])
@login_required
def api_backup_agendamento():
    seed_acesso()
    cfg = _get_backup_config()
    if request.method == 'GET':
        return jsonify({'ok': True, 'config': cfg.to_dict()})

    data = request.get_json(silent=True) or {}
    frequencias = {'Diário', 'Semanal', 'Mensal'}
    if 'ativo' in data:
        cfg.ativo = _parse_bool(data.get('ativo'), False)
    if 'frequencia' in data:
        freq = (data.get('frequencia') or 'Diário').strip()
        if freq not in frequencias:
            return jsonify({'ok': False, 'error': 'Frequência inválida'}), 400
        cfg.frequencia = freq
    if 'horario' in data:
        horario = (data.get('horario') or '').strip()
        if not _parse_time(horario):
            return jsonify({'ok': False, 'error': 'Horário inválido (use HH:MM)'}), 400
        # Normaliza para HH:MM
        t = _parse_time(horario)
        cfg.horario = t.strftime('%H:%M')
    cfg.atualizado_em = datetime.utcnow()
    db.session.commit()
    return jsonify({
        'ok': True,
        'config': cfg.to_dict(),
        # Nota: a execução agendada será feita por job/serviço externo.
        'nota': 'Configuração salva. A execução automática será processada pelo serviço de agendamento.',
    })


@acesso.route('/acesso/api/usuarios', methods=['GET', 'POST'])
@login_required
def api_usuarios():
    seed_acesso()
    if request.method == 'GET':
        return jsonify({'ok': True, 'itens': [_usuario_to_dict(u) for u in Usuario.query.order_by(Usuario.nome).all()]})

    data = request.get_json(silent=True) or {}
    nome = (data.get('nome') or '').strip()
    login = (data.get('usuario') or data.get('login') or '').strip().lower()
    senha = data.get('senha') or ''
    tipo = _normalize_tipo(data.get('tipo'), default='agente')
    token = (data.get('token') or '').strip() or _generate_user_token()
    email = (data.get('email') or '').strip().lower() or _email_from_usuario(login)

    if not nome or not login:
        return jsonify({'ok': False, 'error': 'Nome e usuário são obrigatórios'}), 400
    if not senha:
        return jsonify({'ok': False, 'error': 'Senha obrigatória no cadastro'}), 400
    if Usuario.query.filter(func.lower(Usuario.usuario) == login).first():
        return jsonify({'ok': False, 'error': 'Usuário já cadastrado'}), 400
    if Usuario.query.filter_by(email=email).first():
        return jsonify({'ok': False, 'error': 'E-mail já cadastrado'}), 400

    user = Usuario(
        nome=nome,
        email=email,
        usuario=login,
        senha=generate_password_hash(senha),
        tipo=tipo,
        token=token,
        ativo=_parse_bool(data.get('ativo'), True),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'ok': True, 'item': _usuario_to_dict(user)}), 201


@acesso.route('/acesso/api/usuarios/<int:uid>', methods=['PUT', 'DELETE'])
@login_required
def api_usuarios_item(uid):
    user = Usuario.query.get_or_404(uid)
    if request.method == 'DELETE':
        if session.get('user_id') == user.id:
            return jsonify({'ok': False, 'error': 'Não é possível excluir o usuário logado'}), 400
        AcessoUsuarioPermissao.query.filter_by(usuario_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    if 'nome' in data:
        nome = (data.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome obrigatório'}), 400
        user.nome = nome
    if 'usuario' in data or 'login' in data:
        login = (data.get('usuario') or data.get('login') or '').strip().lower()
        if not login:
            return jsonify({'ok': False, 'error': 'Usuário obrigatório'}), 400
        exists = Usuario.query.filter(
            func.lower(Usuario.usuario) == login,
            Usuario.id != user.id,
        ).first()
        if exists:
            return jsonify({'ok': False, 'error': 'Usuário já cadastrado'}), 400
        old_login = (user.usuario or _login_from_email(user.email) or '').strip().lower()
        user.usuario = login
        # Mantém e-mail real; só sincroniza se era o derivado @acesso.local
        if (user.email or '').endswith('@acesso.local') or (user.email or '').startswith(f'{old_login}@'):
            new_email = _email_from_usuario(login)
            if not Usuario.query.filter(Usuario.email == new_email, Usuario.id != user.id).first():
                user.email = new_email
    if 'email' in data and data.get('email'):
        email = (data.get('email') or '').strip().lower()
        exists = Usuario.query.filter(Usuario.email == email, Usuario.id != user.id).first()
        if exists:
            return jsonify({'ok': False, 'error': 'E-mail já cadastrado'}), 400
        user.email = email
    if data.get('senha'):
        user.senha = generate_password_hash(data.get('senha'))
    if 'tipo' in data:
        user.tipo = _normalize_tipo(data.get('tipo'), default=user.tipo or 'agente')
    if 'token' in data:
        token = (data.get('token') or '').strip()
        user.token = token or _generate_user_token()
    if 'ativo' in data:
        user.ativo = _parse_bool(data.get('ativo'), True)
    db.session.commit()
    return jsonify({'ok': True, 'item': _usuario_to_dict(user)})


@acesso.route('/acesso/api/permissoes/<int:usuario_id>', methods=['GET', 'PUT'])
@login_required
def api_permissoes(usuario_id):
    """API legada: permissões por usuário (mantida por compatibilidade)."""
    seed_acesso()
    user = Usuario.query.get_or_404(usuario_id)
    if request.method == 'GET':
        chaves = [p.chave for p in AcessoUsuarioPermissao.query.filter_by(usuario_id=user.id).all()]
        return jsonify({'ok': True, 'usuario_id': user.id, 'permissoes': chaves})

    data = request.get_json(silent=True) or {}
    permitidas = _matriz_chaves_permitidas()
    recebidas = data.get('permissoes') or []
    if not isinstance(recebidas, list):
        return jsonify({'ok': False, 'error': 'Lista de permissões inválida'}), 400
    chaves = [str(c).strip() for c in recebidas if str(c).strip() in permitidas]

    AcessoUsuarioPermissao.query.filter_by(usuario_id=user.id).delete()
    for chave in chaves:
        db.session.add(AcessoUsuarioPermissao(usuario_id=user.id, chave=chave))
    db.session.commit()
    return jsonify({'ok': True, 'permissoes': chaves})


@acesso.route('/acesso/api/permissoes/perfil/<perfil>', methods=['GET', 'PUT'])
@login_required
def api_permissoes_perfil(perfil):
    seed_acesso()
    perfil = _normalize_tipo(perfil, default='')
    if not perfil or perfil not in TIPO_LABELS:
        return jsonify({'ok': False, 'error': 'Perfil inválido'}), 400

    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'perfil': perfil,
            'perfil_label': TIPO_LABELS.get(perfil, perfil),
            'permissoes': _perfil_permissoes(perfil),
        })

    data = request.get_json(silent=True) or {}
    permitidas = _matriz_chaves_permitidas()
    recebidas = data.get('permissoes') or []
    if not isinstance(recebidas, list):
        return jsonify({'ok': False, 'error': 'Lista de permissões inválida'}), 400
    chaves = [str(c).strip() for c in recebidas if str(c).strip() in permitidas]

    AcessoPerfilPermissao.query.filter_by(perfil=perfil).delete()
    for chave in chaves:
        db.session.add(AcessoPerfilPermissao(perfil=perfil, chave=chave))
    db.session.commit()
    return jsonify({
        'ok': True,
        'perfil': perfil,
        'perfil_label': TIPO_LABELS.get(perfil, perfil),
        'permissoes': chaves,
    })


@acesso.route('/acesso/api/backup', methods=['POST'])
@login_required
def api_backup_gerar():
    seed_acesso()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    models = [
        AcessoEmpresa, AcessoClassificacao, AcessoDepartamento, AcessoSetor,
        AcessoCentroCusto, AcessoLocal, AcessoTipoDocumento, AcessoGrupo, AcessoHorario,
        AcessoEquipamento, AcessoPessoa, AcessoVisitante, AcessoAmbiente,
        AcessoAmbienteEquipamento,
        AcessoEstacionamento, AcessoEstacionamentoEquipamento, AcessoEstacionamentoPermissao,
        AcessoEvento, AcessoUsuarioPermissao, AcessoPerfilPermissao,
        AcessoBackupLog, AcessoBackupConfig, AcessoControleAdicional,
        AcessoPessoaDocumento,
        AcessoGrupoRefeicao, AcessoItemRefeicao, AcessoVinculoRefeicao,
    ]
    payload = {
        'gerado_em': datetime.utcnow().isoformat(sep=' ', timespec='seconds'),
        'modulo': 'controle_acesso',
        'tabelas': {},
    }
    for model in models:
        rows = model.query.all()
        payload['tabelas'][model.__tablename__] = [_serialize_row(r) for r in rows]

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'acesso_backup_{stamp}.json'
    path = BACKUP_DIR / filename
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(content, encoding='utf-8')

    user = Usuario.query.get(session.get('user_id')) if session.get('user_id') else None
    log = AcessoBackupLog(
        arquivo=filename,
        tamanho_bytes=path.stat().st_size,
        tabelas=len(payload['tabelas']),
        usuario_nome=user.nome if user else None,
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({
        'ok': True,
        'id': log.id,
        'arquivo': filename,
        'tamanho_fmt': _fmt_bytes(log.tamanho_bytes),
        'tabelas': log.tabelas,
    })


@acesso.route('/acesso/backup/<int:bid>/download')
@login_required
def backup_download(bid):
    log = AcessoBackupLog.query.get_or_404(bid)
    path = BACKUP_DIR / log.arquivo
    if not path.exists():
        flash('Arquivo de backup não encontrado.', 'error')
        return redirect(url_for('acesso.backup_page'))
    return send_file(path, as_attachment=True, download_name=log.arquivo)


# ---- Administração (cadastros auxiliares) ----
@acesso.route('/acesso/empresas')
@login_required
def empresas_page():
    seed_acesso()
    q = (request.args.get('q') or request.args.get('search') or '').strip()
    query = AcessoEmpresa.query
    if q:
        like = f'%{q}%'
        query = query.filter(or_(AcessoEmpresa.nome.ilike(like), AcessoEmpresa.cnpj.ilike(like)))
    items = [e.to_dict() for e in query.order_by(AcessoEmpresa.nome).all()]
    return render_template(
        'acesso_empresas.html',
        items=items,
        search_term=q,
        api_url=url_for('acesso.api_empresas'),
        cnpj_api_url=url_for('acesso.api_consultar_cnpj'),
        active_page='empresas',
    )


@acesso.route('/acesso/classificacoes')
@acesso.route('/acesso/hierarquia/classificacoes')
@login_required
def classificacoes_page():
    seed_acesso()
    items = [c.to_dict() for c in AcessoClassificacao.query.order_by(AcessoClassificacao.id).all()]
    perfis = [{'value': k, 'label': v} for k, v in TIPO_LABELS.items()]
    return render_template(
        'acesso_classificacoes.html',
        items=items,
        perfis=perfis,
        api_url=url_for('acesso.api_classificacoes'),
        active_page='classificacoes',
    )


@acesso.route('/acesso/cadastros-diversos')
@acesso.route('/acesso/hierarquia/cadastros-diversos')
@login_required
def cadastros_diversos_page():
    seed_acesso()
    tabs = {
        'departamentos': {
            'label': 'Departamentos',
            'singular': 'Departamento',
            'api': url_for('acesso.api_departamentos'),
            'items': [d.to_dict() for d in AcessoDepartamento.query.order_by(AcessoDepartamento.descricao).all()],
        },
        'centros_custo': {
            'label': 'Centros de Custo',
            'singular': 'Centro de Custo',
            'api': url_for('acesso.api_centros_custo'),
            'items': [c.to_dict() for c in AcessoCentroCusto.query.order_by(AcessoCentroCusto.descricao).all()],
        },
        'setores': {
            'label': 'Setores',
            'singular': 'Setor',
            'api': url_for('acesso.api_setores'),
            'items': [s.to_dict() for s in AcessoSetor.query.order_by(AcessoSetor.descricao).all()],
        },
        'locais': {
            'label': 'Locais',
            'singular': 'Local',
            'api': url_for('acesso.api_locais'),
            'items': [l.to_dict() for l in AcessoLocal.query.order_by(AcessoLocal.descricao).all()],
        },
    }
    return render_template(
        'acesso_cadastros_diversos.html',
        tabs=tabs,
        active_page='cadastros_diversos',
    )


@acesso.route('/acesso/departamentos')
@login_required
def departamentos_page():
    seed_acesso()
    items = [d.to_dict() for d in AcessoDepartamento.query.order_by(AcessoDepartamento.descricao).all()]
    return render_template(
        'acesso_admin_cadastro.html',
        page_title='Departamentos',
        page_desc='Departamentos organizacionais dos colaboradores.',
        form_title='Novo departamento',
        kind='departamentos',
        columns=['Descrição'],
        items=items,
        placeholder='Ex: Operações',
        api_url=url_for('acesso.api_departamentos'),
        active_page='departamentos',
    )


@acesso.route('/acesso/setores')
@login_required
def setores_page():
    seed_acesso()
    items = [s.to_dict() for s in AcessoSetor.query.order_by(AcessoSetor.descricao).all()]
    return render_template(
        'acesso_admin_cadastro.html',
        page_title='Setores',
        page_desc='Setores vinculados aos cadastros de pessoas.',
        form_title='Novo setor',
        kind='setores',
        columns=['Descrição'],
        items=items,
        placeholder='Ex: Recepção',
        api_url=url_for('acesso.api_setores'),
        active_page='setores',
    )


@acesso.route('/acesso/centros-custo')
@login_required
def centros_custo_page():
    seed_acesso()
    items = [c.to_dict() for c in AcessoCentroCusto.query.order_by(AcessoCentroCusto.descricao).all()]
    return render_template(
        'acesso_admin_cadastro.html',
        page_title='Centros de Custo',
        page_desc='Centros de custo usados no cadastro de colaboradores.',
        form_title='Novo centro de custo',
        kind='centros_custo',
        columns=['Descrição'],
        items=items,
        placeholder='Ex: Hospital',
        api_url=url_for('acesso.api_centros_custo'),
        active_page='centros_custo',
    )


@acesso.route('/acesso/tipos-documento')
@login_required
def tipos_documento_page():
    seed_acesso()
    items = [t.to_dict() for t in AcessoTipoDocumento.query.order_by(AcessoTipoDocumento.descricao).all()]
    return render_template(
        'acesso_admin_cadastro.html',
        page_title='Tipos de Documento',
        page_desc='Documentos aceitos no cadastro de visitantes (CPF, RG, CNH…).',
        form_title='Novo tipo de documento',
        kind='tipos_documento',
        columns=['Descrição', 'Dígitos'],
        items=items,
        api_url=url_for('acesso.api_tipos_documento'),
        active_page='tipos_documento',
    )


def _api_lookup_list_create(model, field='descricao', unique=True, transform=None):
    """GET lista / POST cria para cadastros auxiliares simples."""
    seed_acesso()
    if request.method == 'GET':
        rows = model.query.order_by(getattr(model, field)).all()
        return jsonify({'ok': True, 'itens': [r.to_dict() for r in rows]})

    data = request.get_json(silent=True) or {}
    if transform:
        data = transform(data) or data
    value = (data.get(field) or '').strip()
    if not value:
        err = 'Descrição é obrigatória' if field == 'descricao' else f'{field.capitalize()} obrigatório'
        return jsonify({'ok': False, 'error': err}), 400
    if unique and model.query.filter(getattr(model, field) == value).first():
        return jsonify({'ok': False, 'error': 'Registro já existe'}), 400

    kwargs = {field: value}
    for key, val in data.items():
        if key != field and hasattr(model, key):
            kwargs[key] = val
    row = model(**kwargs)
    db.session.add(row)
    db.session.commit()
    return jsonify({'ok': True, 'item': row.to_dict()}), 201


def _api_lookup_item(model, item_id, field='descricao', unique=True, transform=None):
    row = model.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(row)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    if transform:
        data = transform(data) or data
    if field in data:
        value = (data.get(field) or '').strip()
        if not value:
            err = 'Descrição é obrigatória' if field == 'descricao' else f'{field.capitalize()} obrigatório'
            return jsonify({'ok': False, 'error': err}), 400
        if unique:
            exists = model.query.filter(
                getattr(model, field) == value,
                model.id != row.id,
            ).first()
            if exists:
                return jsonify({'ok': False, 'error': 'Registro já existe'}), 400
        setattr(row, field, value)
    for key, val in data.items():
        if key != field and hasattr(model, key):
            setattr(row, key, val)
    db.session.commit()
    return jsonify({'ok': True, 'item': row.to_dict()})


_ACESSO_EMPRESAS_DIR = Path(__file__).resolve().parent / 'static' / 'acesso_empresas'
_LOGO_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


def _empresa_payload():
    """Lê JSON ou multipart/form-data (com logo opcional)."""
    is_multipart = (
        request.files
        or (request.content_type and 'multipart/form-data' in request.content_type)
        or (request.form and not request.is_json)
    )
    if is_multipart and (request.form or request.files):
        data = {
            'nome': request.form.get('nome'),
            'cnpj': request.form.get('cnpj'),
            'ativo': request.form.get('ativo'),
        }
        logo = request.files.get('logo') or request.files.get('logo_edit')
        return data, logo
    data = request.get_json(silent=True) or {}
    return data, None


def _save_empresa_logo(upload, empresa_id):
    """Salva logo em static/acesso_empresas/ e retorna path relativo a static/."""
    if not upload or not getattr(upload, 'filename', None):
        return None
    original = secure_filename(upload.filename or '')
    if not original:
        return None
    ext = Path(original).suffix.lower()
    if ext not in _LOGO_EXTS:
        raise ValueError('Formato de logo inválido. Use PNG, JPG, WEBP ou GIF.')
    _ACESSO_EMPRESAS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f'emp_{int(empresa_id)}_{uuid.uuid4().hex[:10]}{ext}'
    dest = _ACESSO_EMPRESAS_DIR / fname
    upload.save(dest)
    return f'acesso_empresas/{fname}'


def _delete_empresa_logo_file(logo_path):
    path = (logo_path or '').strip().replace('\\', '/')
    if not path.startswith('acesso_empresas/'):
        return
    name = Path(path).name
    if not name or name != Path(path).name:
        return
    full = _ACESSO_EMPRESAS_DIR / name
    try:
        if full.is_file():
            full.unlink()
    except OSError:
        pass


@acesso.route('/acesso/api/consultar_cnpj')
@login_required
def api_consultar_cnpj():
    """Consulta pública de CNPJ (BrasilAPI) para preencher razão social."""
    import urllib.request
    import urllib.error

    raw = (request.args.get('cnpj') or '').strip()
    digits = re.sub(r'\D', '', raw)
    if len(digits) != 14:
        return jsonify({'ok': False, 'error': 'CNPJ deve ter 14 dígitos'}), 400
    url = f'https://brasilapi.com.br/api/cnpj/v1/{digits}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SaoGeraldoAcesso/1.0'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return jsonify({'ok': False, 'error': 'CNPJ não encontrado'}), 404
        return jsonify({'ok': False, 'error': 'Falha ao consultar CNPJ'}), 502
    except Exception:
        return jsonify({'ok': False, 'error': 'Falha ao consultar CNPJ'}), 502

    nome = (
        payload.get('razao_social')
        or payload.get('nome_fantasia')
        or payload.get('nome')
        or ''
    ).strip()
    fantasia = (payload.get('nome_fantasia') or '').strip()
    return jsonify({
        'ok': True,
        'nome': nome,
        'razao_social': (payload.get('razao_social') or nome).strip(),
        'nome_fantasia': fantasia,
        'cnpj': digits,
    })


@acesso.route('/acesso/api/empresas', methods=['GET', 'POST'])
@login_required
def api_empresas():
    seed_acesso()
    if request.method == 'GET':
        q = (request.args.get('q') or request.args.get('search') or '').strip()
        query = AcessoEmpresa.query
        if q:
            like = f'%{q}%'
            query = query.filter(or_(AcessoEmpresa.nome.ilike(like), AcessoEmpresa.cnpj.ilike(like)))
        rows = query.order_by(AcessoEmpresa.nome).all()
        return jsonify({'ok': True, 'itens': [r.to_dict() for r in rows]})

    data, logo = _empresa_payload()
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome obrigatório'}), 400
    if AcessoEmpresa.query.filter_by(nome=nome).first():
        return jsonify({'ok': False, 'error': 'Empresa já existe'}), 400
    row = AcessoEmpresa(
        nome=nome,
        cnpj=(data.get('cnpj') or '').strip() or None,
        ativo=_parse_bool(data.get('ativo'), True),
    )
    db.session.add(row)
    db.session.flush()
    if logo and getattr(logo, 'filename', None):
        try:
            row.logo_path = _save_empresa_logo(logo, row.id)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'ok': False, 'error': str(exc)}), 400
    db.session.commit()
    return jsonify({'ok': True, 'item': row.to_dict()}), 201


@acesso.route('/acesso/api/empresas/<int:eid>', methods=['PUT', 'DELETE'])
@login_required
def api_empresas_item(eid):
    row = AcessoEmpresa.query.get_or_404(eid)
    if request.method == 'DELETE':
        _delete_empresa_logo_file(row.logo_path)
        db.session.delete(row)
        db.session.commit()
        return jsonify({'ok': True})

    data, logo = _empresa_payload()
    if 'nome' in data and data.get('nome') is not None:
        nome = (data.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome obrigatório'}), 400
        exists = AcessoEmpresa.query.filter(AcessoEmpresa.nome == nome, AcessoEmpresa.id != row.id).first()
        if exists:
            return jsonify({'ok': False, 'error': 'Empresa já existe'}), 400
        row.nome = nome
    if 'cnpj' in data:
        row.cnpj = (data.get('cnpj') or '').strip() or None
    if 'ativo' in data and data.get('ativo') is not None and data.get('ativo') != '':
        row.ativo = _parse_bool(data.get('ativo'), True)
    if logo and getattr(logo, 'filename', None):
        try:
            new_path = _save_empresa_logo(logo, row.id)
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        old = row.logo_path
        row.logo_path = new_path
        if old and old != new_path:
            _delete_empresa_logo_file(old)
    db.session.commit()
    return jsonify({'ok': True, 'item': row.to_dict()})


def _normalize_classificacao_perfil(raw):
    """Normaliza perfil_fixo: None/'', 'sem_perfil' → None; senão chave TIPO_LABELS."""
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if not value or value in ('sem_perfil', 'sem perfil', 'none', 'null'):
        return None
    if value in TIPO_LABELS:
        return value
    return _normalize_tipo(value, default='') or None


def _tf_classificacao(data):
    out = dict(data or {})
    if 'descricao' in out and out['descricao'] is not None:
        out['descricao'] = str(out['descricao']).strip()
    if 'mostrar_visitante' in out:
        out['mostrar_visitante'] = _parse_bool(out.get('mostrar_visitante'), False)
    # Vincular perfil fixo (perfil | perfil_fixo)
    if 'perfil_fixo' in out or 'perfil' in out:
        raw = out.get('perfil_fixo', out.get('perfil'))
        out['perfil_fixo'] = _normalize_classificacao_perfil(raw)
        out.pop('perfil', None)
    return out


@acesso.route('/acesso/api/classificacoes', methods=['GET', 'POST'])
@login_required
def api_classificacoes():
    return _api_lookup_list_create(AcessoClassificacao, transform=_tf_classificacao)


@acesso.route('/acesso/api/classificacoes/<int:cid>', methods=['PUT', 'DELETE'])
@login_required
def api_classificacoes_item(cid):
    return _api_lookup_item(AcessoClassificacao, cid, transform=_tf_classificacao)


@acesso.route('/acesso/api/departamentos', methods=['GET', 'POST'])
@login_required
def api_departamentos():
    return _api_lookup_list_create(AcessoDepartamento)


@acesso.route('/acesso/api/departamentos/<int:did>', methods=['PUT', 'DELETE'])
@login_required
def api_departamentos_item(did):
    return _api_lookup_item(AcessoDepartamento, did)


@acesso.route('/acesso/api/setores', methods=['GET', 'POST'])
@login_required
def api_setores():
    return _api_lookup_list_create(AcessoSetor)


@acesso.route('/acesso/api/setores/<int:sid>', methods=['PUT', 'DELETE'])
@login_required
def api_setores_item(sid):
    return _api_lookup_item(AcessoSetor, sid)


@acesso.route('/acesso/api/centros-custo', methods=['GET', 'POST'])
@login_required
def api_centros_custo():
    return _api_lookup_list_create(AcessoCentroCusto)


@acesso.route('/acesso/api/centros-custo/<int:cid>', methods=['PUT', 'DELETE'])
@login_required
def api_centros_custo_item(cid):
    return _api_lookup_item(AcessoCentroCusto, cid)


@acesso.route('/acesso/api/locais', methods=['GET', 'POST'])
@login_required
def api_locais():
    return _api_lookup_list_create(AcessoLocal)


@acesso.route('/acesso/api/locais/<int:lid>', methods=['PUT', 'DELETE'])
@login_required
def api_locais_item(lid):
    return _api_lookup_item(AcessoLocal, lid)


# ---- APIs Pessoas ----
@acesso.route('/acesso/api/pessoas', methods=['GET', 'POST'])
@login_required
def api_pessoas():
    seed_acesso()
    if request.method == 'GET':
        return jsonify([p.to_dict() for p in AcessoPessoa.query.order_by(AcessoPessoa.nome).all()])

    data = request.get_json(silent=True) or request.form.to_dict()
    matricula = (data.get('matricula') or '').strip()
    nome = (data.get('nome') or '').strip()
    if not matricula or not nome:
        return jsonify({'ok': False, 'error': 'Matrícula e nome são obrigatórios'}), 400
    if AcessoPessoa.query.filter_by(matricula=matricula).first():
        return jsonify({'ok': False, 'error': 'Matrícula já cadastrada'}), 400

    pessoa = AcessoPessoa(
        matricula=matricula,
        nome=nome.upper(),
        status=(data.get('status') or 'Ativo').strip(),
        data_inicial=_parse_date(data.get('data_inicial')) or date.today(),
    )
    try:
        _apply_pessoa_fields(pessoa, data)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    db.session.add(pessoa)
    db.session.commit()
    return jsonify({'ok': True, 'pessoa': pessoa.to_dict()}), 201


@acesso.route('/acesso/api/pessoas/<int:pid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_pessoa_item(pid):
    pessoa = AcessoPessoa.query.get_or_404(pid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'pessoa': pessoa.to_dict()})
    if request.method == 'DELETE':
        db.session.delete(pessoa)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    try:
        _apply_pessoa_fields(pessoa, data)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    db.session.commit()
    return jsonify({'ok': True, 'pessoa': pessoa.to_dict()})


# ---- APIs Equipamentos ----
@acesso.route('/acesso/api/equipamentos', methods=['GET', 'POST'])
@login_required
def api_equipamentos():
    seed_acesso()
    if request.method == 'GET':
        return jsonify([e.to_dict() for e in AcessoEquipamento.query.order_by(AcessoEquipamento.nome).all()])

    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome é obrigatório'}), 400

    device_id = (data.get('device_id') or '').strip() or None
    if device_id and AcessoEquipamento.query.filter_by(device_id=device_id).first():
        return jsonify({'ok': False, 'error': 'device_id já cadastrado'}), 400

    eq = AcessoEquipamento(
        nome=nome,
        marca=(data.get('marca') or 'Control iD').strip(),
        modelo=(data.get('modelo') or '').strip() or None,
        ip=(data.get('ip') or '').strip() or None,
        device_id=device_id,
        usuario_disp=(data.get('usuario_disp') or 'admin').strip(),
        senha_disp=(data.get('senha_disp') or '').strip() or None,
        controle_giro=(data.get('controle_giro') or 'Ambos os lados').strip(),
        local=(data.get('local') or '').strip() or None,
        ativo=str(data.get('ativo', '1')).lower() not in ('0', 'false', 'off'),
    )
    db.session.add(eq)
    db.session.commit()
    return jsonify({'ok': True, 'equipamento': eq.to_dict()}), 201


@acesso.route('/acesso/api/equipamentos/acoes', methods=['POST'])
@login_required
def api_equipamentos_acoes():
    """Ações do Hub: configurar servidor / reiniciar / probe Control iD."""
    data = request.get_json(silent=True) or {}
    acao = (data.get('acao') or '').strip().lower()
    eid = data.get('equipamento_id')
    alvo = None
    if eid:
        alvo = AcessoEquipamento.query.get(int(eid))

    if acao == 'configurar_servidor':
        host, porta, path = _controlid_server_host_port(data)
        eqs = [alvo] if alvo else _controlid_eqs_alvo(only_online=False)
        eqs = [e for e in eqs if e and (e.ip or '').strip()]
        if not eqs:
            return jsonify({'ok': False, 'error': 'Nenhum equipamento com IP'}), 400
        ok_n = err_n = 0
        detalhes = []
        for eq in eqs:
            try:
                cid.configurar_monitor(
                    cid.creds_from_equipamento(eq), host, porta, path=path,
                )
                _controlid_mark_online(eq, True)
                ok_n += 1
                detalhes.append({'equipamento': eq.nome, 'ok': True})
            except cid.ControlIDError as exc:
                err_n += 1
                _controlid_mark_online(eq, False)
                detalhes.append({'equipamento': eq.nome, 'ok': False, 'error': str(exc)})
        db.session.commit()
        escopo = f'em "{alvo.nome}"' if alvo else f'em {ok_n + err_n} equipamento(s)'
        return jsonify({
            'ok': err_n == 0,
            'stub': False,
            'message': (
                f'Servidor {host}:{porta}/{path} aplicado {escopo}'
                + (f' — {err_n} falha(s)' if err_n else '')
            ),
            'ok_count': ok_n,
            'err_count': err_n,
            'detalhes': detalhes,
        })

    if acao in ('reiniciar_conexao', 'reiniciar'):
        host, porta, path = _controlid_server_host_port(data)
        eqs = [alvo] if alvo else _controlid_eqs_alvo(only_online=False)
        eqs = [e for e in eqs if e and (e.ip or '').strip()]
        if not eqs:
            return jsonify({'ok': False, 'error': 'Nenhum equipamento com IP'}), 400
        ok_n = err_n = 0
        for eq in eqs:
            try:
                info = cid.reiniciar_conexao(
                    cid.creds_from_equipamento(eq),
                    hostname=host,
                    porta=porta,
                    path=path,
                )
                _controlid_mark_online(eq, True, info.get('device_id'))
                ok_n += 1
            except cid.ControlIDError as exc:
                err_n += 1
                _controlid_mark_online(eq, False)
                LOG.warning('reiniciar %s: %s', eq.nome, exc)
        db.session.commit()
        return jsonify({
            'ok': err_n == 0,
            'stub': False,
            'message': (
                f'Conexão reiniciada em {ok_n} equipamento(s)'
                + (f'; {err_n} falha(s)' if err_n else '')
            ),
            'ok_count': ok_n,
            'err_count': err_n,
        })

    if acao in ('atualizar_datetime', 'atualizar_data_hora'):
        return api_equipamentos_atualizar_data_hora()

    if acao in ('probe', 'testar', 'ping'):
        if not alvo or not (alvo.ip or '').strip():
            return jsonify({'ok': False, 'error': 'Selecione um equipamento com IP'}), 400
        try:
            info = cid.probe(cid.creds_from_equipamento(alvo))
            _controlid_mark_online(alvo, True, info.get('device_id'))
            db.session.commit()
            return jsonify({
                'ok': True,
                'message': f'{alvo.nome} online (device_id={info.get("device_id") or alvo.device_id or "—"})',
                'equipamento': alvo.to_dict(),
            })
        except cid.ControlIDError as exc:
            _controlid_mark_online(alvo, False)
            db.session.commit()
            return jsonify({'ok': False, 'error': str(exc)}), 502

    if acao in ('puxar_device_id', 'puxar_id'):
        if not alvo or not (alvo.ip or '').strip():
            return jsonify({'ok': False, 'error': 'Selecione um equipamento com IP'}), 400
        try:
            did = cid.puxar_device_id(cid.creds_from_equipamento(alvo))
            alvo.device_id = did
            _controlid_mark_online(alvo, True, did)
            db.session.commit()
            return jsonify({
                'ok': True,
                'device_id': did,
                'message': f'Device ID {did} obtido de {alvo.nome}',
                'equipamento': alvo.to_dict(),
            })
        except cid.ControlIDError as exc:
            _controlid_mark_online(alvo, False)
            db.session.commit()
            return jsonify({'ok': False, 'error': str(exc)}), 502

    return jsonify({'ok': False, 'error': 'Ação desconhecida'}), 400


@acesso.route('/acesso/api/equipamentos/atualizar-data-hora', methods=['POST'])
@login_required
def api_equipamentos_atualizar_data_hora():
    """Envia data/hora aos equipamentos via set_system_time.fcgi."""
    data = request.get_json(silent=True) or {}
    data_str = (data.get('data') or '').strip()
    hora_str = (data.get('hora') or '').strip()
    raw_ids = data.get('equipamento_ids') or []
    if not data_str or not hora_str:
        return jsonify({'ok': False, 'error': 'Data e hora são obrigatórias'}), 400
    ids = _parse_int_list(raw_ids)
    if not ids:
        return jsonify({'ok': False, 'error': 'Selecione ao menos um equipamento'}), 400

    try:
        when = cid.parse_data_hora_ui(data_str, hora_str)
    except cid.ControlIDError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    eqs = AcessoEquipamento.query.filter(AcessoEquipamento.id.in_(ids)).all()
    ok_n = err_n = 0
    detalhes = []
    for eq in eqs:
        if not (eq.ip or '').strip():
            err_n += 1
            detalhes.append({'equipamento': eq.nome, 'ok': False, 'error': 'sem IP'})
            continue
        try:
            cid.set_system_time(cid.creds_from_equipamento(eq), when)
            _controlid_mark_online(eq, True)
            ok_n += 1
            detalhes.append({'equipamento': eq.nome, 'ok': True})
        except cid.ControlIDError as exc:
            err_n += 1
            _controlid_mark_online(eq, False)
            detalhes.append({'equipamento': eq.nome, 'ok': False, 'error': str(exc)})
    db.session.commit()
    return jsonify({
        'ok': err_n == 0,
        'stub': False,
        'count': ok_n,
        'err_count': err_n,
        'data': data_str,
        'hora': hora_str,
        'detalhes': detalhes,
        'message': (
            f'Data/hora enviada para {ok_n} equipamento(s)'
            + (f'; {err_n} falha(s)' if err_n else '')
        ),
    })


@acesso.route('/acesso/api/equipamentos/reiniciar-conexao', methods=['POST'])
@login_required
def api_equipamentos_reiniciar_conexao():
    """Reloga e reaplica monitor em todos os equipamentos ativos com IP."""
    data = request.get_json(silent=True) or {}
    host, porta, path = _controlid_server_host_port(data)
    eqs = _controlid_eqs_alvo(only_online=False)
    ok_n = err_n = 0
    for eq in eqs:
        try:
            info = cid.reiniciar_conexao(
                cid.creds_from_equipamento(eq),
                hostname=host,
                porta=porta,
                path=path,
            )
            _controlid_mark_online(eq, True, info.get('device_id'))
            ok_n += 1
        except cid.ControlIDError as exc:
            err_n += 1
            _controlid_mark_online(eq, False)
            LOG.warning('reiniciar-conexao %s: %s', eq.nome, exc)
    db.session.commit()
    return jsonify({
        'ok': err_n == 0,
        'stub': False,
        'count': ok_n,
        'err_count': err_n,
        'message': (
            f'Conexão reiniciada em {ok_n} equipamento(s)'
            + (f'; {err_n} falha(s)' if err_n else '')
            + f' (servidor {host}:{porta})'
        ),
    })


@acesso.route('/acesso/api/equipamentos/puxar-device-id', methods=['POST'])
@login_required
def api_equipamentos_puxar_device_id():
    data = request.get_json(silent=True) or {}
    eid = _parse_int(data.get('equipamento_id') or data.get('id'))
    if not eid:
        return jsonify({'ok': False, 'error': 'equipamento_id obrigatório'}), 400
    eq = AcessoEquipamento.query.get(eid)
    if not eq:
        return jsonify({'ok': False, 'error': 'Equipamento não encontrado'}), 404
    # senha opcional só para esta chamada
    if data.get('senha_disp') or data.get('senha'):
        eq.senha_disp = (data.get('senha_disp') or data.get('senha') or '').strip() or eq.senha_disp
    if data.get('usuario_disp') or data.get('usuario'):
        eq.usuario_disp = (data.get('usuario_disp') or data.get('usuario') or 'admin').strip()
    if data.get('ip'):
        eq.ip = (data.get('ip') or '').strip()
    try:
        did = cid.puxar_device_id(cid.creds_from_equipamento(eq))
        eq.device_id = did
        _controlid_mark_online(eq, True, did)
        db.session.commit()
        return jsonify({'ok': True, 'device_id': did, 'equipamento': eq.to_dict()})
    except cid.ControlIDError as exc:
        _controlid_mark_online(eq, False)
        db.session.commit()
        return jsonify({'ok': False, 'error': str(exc)}), 502


@acesso.route('/acesso/api/equipamentos/<int:eid>', methods=['PUT', 'DELETE'])
@login_required
def api_equipamento_item(eid):
    eq = AcessoEquipamento.query.get_or_404(eid)
    if request.method == 'DELETE':
        db.session.delete(eq)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    for field in ('nome', 'marca', 'modelo', 'ip', 'usuario_disp', 'controle_giro', 'local'):
        if field in data:
            setattr(eq, field, (data.get(field) or '').strip() or None)
    if 'senha_disp' in data:
        senha = data.get('senha_disp')
        # string vazia mantém senha atual; null explícito limpa
        if senha is None:
            pass
        elif str(senha) == '' and data.get('limpar_senha'):
            eq.senha_disp = None
        elif str(senha).strip():
            eq.senha_disp = str(senha).strip()
    if 'device_id' in data:
        nova = (data.get('device_id') or '').strip() or None
        if nova and nova != eq.device_id:
            if AcessoEquipamento.query.filter_by(device_id=nova).first():
                return jsonify({'ok': False, 'error': 'device_id já cadastrado'}), 400
        eq.device_id = nova
    if 'online' in data:
        eq.online = bool(data.get('online'))
        if eq.online:
            eq.last_alive = datetime.utcnow()
    if 'ativo' in data:
        eq.ativo = str(data.get('ativo')).lower() not in ('0', 'false', 'off')
    db.session.commit()
    return jsonify({'ok': True, 'equipamento': eq.to_dict()})


# ---- Monitor callbacks (device → servidor; sem login de usuário) ----
def _controlid_find_eq_by_device(device_id):
    if device_id is None or str(device_id).strip() == '':
        return None
    did = str(device_id).strip()
    eq = AcessoEquipamento.query.filter_by(device_id=did).first()
    if eq:
        return eq
    # tenta match numérico sem zeros
    try:
        eq = AcessoEquipamento.query.filter_by(device_id=str(int(did))).first()
    except Exception:
        eq = None
    return eq


def _controlid_ingest_access_log_values(values, device_id=None):
    """Persiste um access_log vindo do monitor dao."""
    if not isinstance(values, dict):
        return None
    eq = _controlid_find_eq_by_device(device_id or values.get('device_id'))
    dh = cid.parse_access_log_time(values)
    uid = values.get('user_id')
    try:
        uid_int = int(uid or 0)
    except (TypeError, ValueError):
        uid_int = 0
    st, event_type = cid.map_access_event(values.get('event'), user_id=uid_int)
    pessoa_ref, nome, tipo_pessoa = _controlid_resolve_pessoa(uid)
    direction = _controlid_direction_for_eq(eq) if eq else 'Entrada'
    if eq and _sync_offline_evento_existe(eq.id, pessoa_ref, dh, st, direction):
        return None
    ev = AcessoEvento(
        pessoa_ref=pessoa_ref,
        nome=nome,
        tipo_pessoa=tipo_pessoa,
        status=st,
        direction=direction,
        event_type=event_type or 'Monitor',
        equipamento_id=eq.id if eq else None,
        equipamento_nome=eq.nome if eq else None,
        cartao=str(values.get('card_value') or '') or None,
        data_hora=dh,
    )
    db.session.add(ev)
    return ev


@acesso.route('/acesso/controlid/notifications/device_is_alive', methods=['POST'])
def controlid_device_is_alive():
    data = request.get_json(silent=True) or {}
    device_id = data.get('device_id')
    eq = _controlid_find_eq_by_device(device_id)
    if eq:
        _controlid_mark_online(eq, True, device_id)
        db.session.commit()
    return jsonify({'ok': True})


@acesso.route('/acesso/controlid/notifications/dao', methods=['POST'])
def controlid_notifications_dao():
    data = request.get_json(silent=True) or {}
    device_id = data.get('device_id')
    changes = data.get('object_changes') or []
    saved = 0
    for ch in changes:
        if not isinstance(ch, dict):
            continue
        if (ch.get('object') or '') != 'access_logs':
            continue
        if (ch.get('type') or '') not in ('inserted', 'insert', ''):
            continue
        values = ch.get('values') or {}
        try:
            if _controlid_ingest_access_log_values(values, device_id):
                saved += 1
        except Exception as exc:
            LOG.warning('dao ingest: %s', exc)
    if saved:
        eq = _controlid_find_eq_by_device(device_id)
        if eq:
            _controlid_mark_online(eq, True, device_id)
        db.session.commit()
    elif device_id:
        eq = _controlid_find_eq_by_device(device_id)
        if eq:
            _controlid_mark_online(eq, True, device_id)
            db.session.commit()
    return jsonify({'ok': True, 'saved': saved})


@acesso.route('/acesso/controlid/notifications/door', methods=['POST'])
@acesso.route('/acesso/controlid/notifications/secbox', methods=['POST'])
@acesso.route('/acesso/controlid/notifications/catra_event', methods=['POST'])
@acesso.route('/acesso/controlid/notifications/operation_mode', methods=['POST'])
def controlid_notifications_misc():
    data = request.get_json(silent=True) or {}
    eq = _controlid_find_eq_by_device(data.get('device_id'))
    if eq:
        _controlid_mark_online(eq, True, data.get('device_id'))
        db.session.commit()
    return jsonify({'ok': True})


# ---- APIs Grupos ----
@acesso.route('/acesso/api/grupos', methods=['GET', 'POST'])
@login_required
def api_grupos():
    seed_acesso()
    if request.method == 'GET':
        out = []
        for g in AcessoGrupo.query.order_by(AcessoGrupo.nome).all():
            d = g.to_dict()
            d['equipamento_ids'] = [e.id for e in g.equipamentos]
            d['horarios'] = [h.to_dict() for h in g.horarios]
            out.append(d)
        return jsonify(out)

    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome é obrigatório'}), 400
    if AcessoGrupo.query.filter_by(nome=nome).first():
        return jsonify({'ok': False, 'error': 'Grupo já existe'}), 400

    grupo = AcessoGrupo(
        nome=nome,
        descricao=(data.get('descricao') or '').strip() or None,
        ativo=True,
    )
    db.session.add(grupo)
    db.session.flush()

    eq_ids = data.get('equipamento_ids') or []
    if isinstance(eq_ids, str):
        eq_ids = [x for x in eq_ids.split(',') if x.strip()]
    for eid in eq_ids:
        eq = AcessoEquipamento.query.get(int(eid))
        if eq:
            grupo.equipamentos.append(eq)

    horarios_in = data.get('horarios')
    if isinstance(horarios_in, list) and horarios_in:
        for item in horarios_in:
            if not isinstance(item, dict):
                continue
            db.session.add(_horario_from_item(grupo.id, item))
    else:
        db.session.add(_horario_from_item(grupo.id, {
            'dia_semana': data.get('dia_semana') or 'TODOS',
            'hora_inicial': data.get('hora_inicial'),
            'hora_final': data.get('hora_final'),
            'entradas': data.get('entradas'),
            'saidas': data.get('saidas'),
            'livre': data.get('livre'),
            'por_equipamento': data.get('por_equipamento'),
        }))
    db.session.commit()
    return jsonify({'ok': True, 'grupo': _grupo_payload(grupo)}), 201


@acesso.route('/acesso/api/grupos/<int:gid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_grupo_item(gid):
    grupo = AcessoGrupo.query.get_or_404(gid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'grupo': _grupo_payload(grupo)})

    if request.method == 'DELETE':
        db.session.delete(grupo)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    if 'nome' in data:
        nome = (data.get('nome') or '').strip()
        if nome:
            conflito = AcessoGrupo.query.filter(
                AcessoGrupo.nome == nome,
                AcessoGrupo.id != grupo.id,
            ).first()
            if conflito:
                return jsonify({'ok': False, 'error': 'Já existe um horário/grupo com este nome'}), 400
            grupo.nome = nome
    if 'descricao' in data:
        grupo.descricao = (data.get('descricao') or '').strip() or None
    if 'ativo' in data:
        grupo.ativo = str(data.get('ativo')).lower() not in ('0', 'false', 'off')
    if 'equipamento_ids' in data:
        eq_ids = data.get('equipamento_ids') or []
        grupo.equipamentos = []
        for eid in eq_ids:
            eq = AcessoEquipamento.query.get(int(eid))
            if eq:
                grupo.equipamentos.append(eq)
    if 'horarios' in data:
        horarios_in = data.get('horarios') or []
        grupo.horarios = []
        db.session.flush()
        if isinstance(horarios_in, list):
            for item in horarios_in:
                if not isinstance(item, dict):
                    continue
                db.session.add(_horario_from_item(grupo.id, item))
    db.session.commit()
    return jsonify({'ok': True, 'grupo': _grupo_payload(grupo)})


# ---- APIs Visitantes ----
def _apply_visitante_fields(visitante, data, creating=False):
    if 'nome' in data or creating:
        nome = (data.get('nome') or '').strip()
        if not nome:
            raise ValueError('Nome é obrigatório')
        visitante.nome = nome.upper()

    tipo_doc = (data.get('tipo_documento') or data.get('documento_tipo') or '').strip()
    if tipo_doc or creating:
        visitante.tipo_documento = tipo_doc or visitante.tipo_documento or 'CPF'

    doc = (data.get('documento') or '').strip()
    if 'documento' in data or creating:
        visitante.documento = doc or None
        if (visitante.tipo_documento or '').upper() == 'CPF':
            visitante.cpf = doc or None
        elif (visitante.tipo_documento or '').upper() == 'RG':
            visitante.rg = doc or None

    for field in (
        'cpf', 'rg', 'empresa_visitada', 'motivo', 'cartao', 'tipo_cartao',
        'qr_code', 'token', 'foto', 'local_acesso', 'ident_modo',
        'impressora', 'modelo_impressao', 'anfitriao',
    ):
        if field in data:
            val = data.get(field)
            if field == 'foto':
                setattr(visitante, field, val or None)
            else:
                setattr(visitante, field, (str(val).strip() if val is not None else '') or None)

    for field in ('grupo_id', 'empresa_id', 'classificacao_id', 'equipamento_id', 'refeicao_creditos'):
        if field in data:
            setattr(visitante, field, _parse_int(data.get(field)))

    if visitante.empresa_id:
        emp = AcessoEmpresa.query.get(visitante.empresa_id)
        if emp:
            visitante.empresa_visitada = emp.nome

    if 'data_inicial' in data or creating:
        visitante.data_inicial = _parse_date(data.get('data_inicial')) or visitante.data_inicial or date.today()
    if 'hora_inicial' in data or creating:
        visitante.hora_inicial = _parse_time(data.get('hora_inicial')) or visitante.hora_inicial or time(7, 0)
    if 'data_final' in data:
        visitante.data_final = _parse_date(data.get('data_final'))
    elif creating and not visitante.data_final:
        visitante.data_final = visitante.data_inicial
    if 'hora_final' in data or creating:
        visitante.hora_final = _parse_time(data.get('hora_final')) or visitante.hora_final or time(19, 0)

    for flag in (
        'visita_unica', 'refeicao', 'imprimir_ao_salvar', 'baixar_qr_ao_salvar', 'ativo',
    ):
        if flag in data or (creating and flag != 'ativo'):
            if flag == 'ativo' and flag not in data:
                visitante.ativo = True
            else:
                setattr(visitante, flag, _parse_bool(data.get(flag), default=False if flag != 'ativo' else True))


@acesso.route('/acesso/api/visitantes', methods=['GET', 'POST'])
@login_required
def api_visitantes():
    seed_acesso()
    if request.method == 'GET':
        q = (request.args.get('q') or '').strip()
        query = AcessoVisitante.query
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                AcessoVisitante.nome.ilike(like),
                AcessoVisitante.visitor_id.ilike(like),
                AcessoVisitante.cpf.ilike(like),
                AcessoVisitante.documento.ilike(like),
                AcessoVisitante.anfitriao.ilike(like),
            ))
        limit = min(int(request.args.get('limit', 200)), 500)
        rows = query.order_by(AcessoVisitante.id.desc()).limit(limit).all()
        return jsonify({'ok': True, 'visitantes': [v.to_dict() for v in rows]})

    data = request.get_json(silent=True) or request.form.to_dict()
    visitor_id = (data.get('visitor_id') or '').strip()
    if not visitor_id:
        last = db.session.query(func.count(AcessoVisitante.id)).scalar() or 0
        visitor_id = f'V{last + 1:05d}'
    if AcessoVisitante.query.filter_by(visitor_id=visitor_id).first():
        return jsonify({'ok': False, 'error': 'visitor_id já cadastrado'}), 400

    grupo = AcessoGrupo.query.filter_by(nome='Visitantes').first()
    visitante = AcessoVisitante(visitor_id=visitor_id, ativo=True)
    try:
        _apply_visitante_fields(visitante, data, creating=True)
        if not visitante.grupo_id and grupo:
            visitante.grupo_id = grupo.id
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    db.session.add(visitante)
    db.session.commit()
    return jsonify({'ok': True, 'visitante': visitante.to_dict()}), 201


@acesso.route('/acesso/api/visitantes/<int:vid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_visitante_item(vid):
    visitante = AcessoVisitante.query.get_or_404(vid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'visitante': visitante.to_dict()})
    if request.method == 'DELETE':
        db.session.delete(visitante)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    try:
        _apply_visitante_fields(visitante, data, creating=False)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    db.session.commit()
    return jsonify({'ok': True, 'visitante': visitante.to_dict()})


@acesso.route('/acesso/api/visitantes/buscar', methods=['GET'])
@login_required
def api_visitantes_buscar():
    """Busca por documento ou nome (reutiliza cadastro existente)."""
    seed_acesso()
    doc = (request.args.get('documento') or request.args.get('doc') or '').strip()
    nome = (request.args.get('nome') or request.args.get('q') or '').strip()
    query = AcessoVisitante.query
    if doc:
        digits = ''.join(ch for ch in doc if ch.isalnum())
        query = query.filter(or_(
            AcessoVisitante.documento == doc,
            AcessoVisitante.cpf == doc,
            AcessoVisitante.rg == doc,
            AcessoVisitante.documento.ilike(f'%{digits}%'),
            AcessoVisitante.cpf.ilike(f'%{digits}%'),
        ))
    elif nome:
        query = query.filter(AcessoVisitante.nome.ilike(f'%{nome}%'))
    else:
        return jsonify({'ok': False, 'error': 'Informe documento ou nome'}), 400
    rows = query.order_by(AcessoVisitante.data_criacao.desc()).limit(30).all()
    return jsonify({'ok': True, 'visitantes': [v.to_dict() for v in rows]})


@acesso.route('/acesso/api/visitantes/anfitrioes', methods=['GET'])
@login_required
def api_visitantes_anfitrioes():
    """Autocomplete de anfitrião a partir de colaboradores."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'ok': True, 'itens': []})
    like = f'%{q}%'
    pessoas = AcessoPessoa.query.filter(
        or_(AcessoPessoa.nome.ilike(like), AcessoPessoa.matricula.ilike(like))
    ).order_by(AcessoPessoa.nome).limit(15).all()
    return jsonify({
        'ok': True,
        'itens': [{
            'id': p.id,
            'nome': p.nome,
            'matricula': p.matricula,
            'documento': p.documento or '',
        } for p in pessoas],
    })


@acesso.route('/acesso/api/tipos-documento', methods=['GET', 'POST'])
@login_required
def api_tipos_documento():
    seed_acesso()
    if request.method == 'GET':
        rows = AcessoTipoDocumento.query.order_by(AcessoTipoDocumento.descricao).all()
        counts = dict(
            db.session.query(
                AcessoPessoaDocumento.tipo_documento_id,
                func.count(AcessoPessoaDocumento.id),
            ).group_by(AcessoPessoaDocumento.tipo_documento_id).all()
        )
        return jsonify({
            'ok': True,
            'tipos': [t.to_dict(vinculos=counts.get(t.id, 0)) for t in rows],
        })

    data = request.get_json(silent=True) or {}
    desc = (data.get('descricao') or data.get('nome') or '').strip().upper()
    if not desc:
        return jsonify({'ok': False, 'error': 'Nome do tipo obrigatório'}), 400
    if AcessoTipoDocumento.query.filter_by(descricao=desc).first():
        return jsonify({'ok': False, 'error': 'Tipo já existe'}), 400
    tipo = AcessoTipoDocumento(descricao=desc, digitos=_parse_int(data.get('digitos')) or 0)
    db.session.add(tipo)
    db.session.commit()
    return jsonify({'ok': True, 'tipo': tipo.to_dict(vinculos=0)}), 201


@acesso.route('/acesso/api/tipos-documento/<int:tid>', methods=['PUT', 'DELETE'])
@login_required
def api_tipos_documento_item(tid):
    tipo = AcessoTipoDocumento.query.get_or_404(tid)
    if request.method == 'DELETE':
        n_vinc = AcessoPessoaDocumento.query.filter_by(tipo_documento_id=tid).count()
        if n_vinc:
            return jsonify({
                'ok': False,
                'error': f'Não é possível excluir: há {n_vinc} vínculo(s) com este tipo.',
            }), 400
        db.session.delete(tipo)
        db.session.commit()
        return jsonify({'ok': True})
    data = request.get_json(silent=True) or {}
    if 'descricao' in data or 'nome' in data:
        desc = (data.get('descricao') or data.get('nome') or '').strip().upper()
        if not desc:
            return jsonify({'ok': False, 'error': 'Nome do tipo obrigatório'}), 400
        outro = AcessoTipoDocumento.query.filter(
            AcessoTipoDocumento.descricao == desc,
            AcessoTipoDocumento.id != tid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Tipo já existe'}), 400
        tipo.descricao = desc
    if 'digitos' in data:
        tipo.digitos = _parse_int(data.get('digitos')) or 0
    db.session.commit()
    vinculos = AcessoPessoaDocumento.query.filter_by(tipo_documento_id=tid).count()
    return jsonify({'ok': True, 'tipo': tipo.to_dict(vinculos=vinculos)})


def _hub_docs_filter_pessoas():
    """Filtros comuns do Hub de Documentos."""
    q = (request.args.get('q') or request.args.get('nome') or '').strip()
    empresa_id = _parse_int(request.args.get('empresa_id'))
    departamento_id = _parse_int(request.args.get('departamento_id'))
    setor_id = _parse_int(request.args.get('setor_id'))
    classificacao_id = _parse_int(request.args.get('classificacao_id'))
    query = AcessoPessoa.query
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoPessoa.nome.ilike(like),
            AcessoPessoa.matricula.ilike(like),
        ))
    if empresa_id:
        query = query.filter(AcessoPessoa.empresa_id == empresa_id)
    if departamento_id:
        query = query.filter(AcessoPessoa.departamento_id == departamento_id)
    if setor_id:
        query = query.filter(AcessoPessoa.setor_id == setor_id)
    if classificacao_id:
        query = query.filter(AcessoPessoa.classificacao_id == classificacao_id)
    return query.order_by(AcessoPessoa.nome)


def _pessoa_hub_dict(p):
    nome = p.nome or '?'
    iniciais = ''.join(part[0] for part in nome.split()[:2]).upper() if nome else '?'
    return {
        'id': p.id,
        'nome': nome,
        'matricula': p.matricula or '',
        'iniciais': iniciais[:2],
        'empresa_id': p.empresa_id,
        'empresa': p.empresa_ref.nome if p.empresa_ref else (p.empresa or ''),
        'departamento_id': p.departamento_id,
        'departamento': (
            p.departamento_ref.descricao if p.departamento_ref else (p.departamento or '')
        ),
        'setor_id': p.setor_id,
        'setor': p.setor_ref.descricao if p.setor_ref else (p.setor or ''),
        'classificacao_id': p.classificacao_id,
        'classificacao': p.classificacao_ref.descricao if p.classificacao_ref else '',
    }


@acesso.route('/acesso/api/hub-documentos/pessoas', methods=['GET'])
@login_required
def api_hub_documentos_pessoas():
    seed_acesso()
    page = max(_parse_int(request.args.get('page')) or 1, 1)
    per_page = min(max(_parse_int(request.args.get('per_page')) or 20, 5), 100)
    query = _hub_docs_filter_pessoas()
    total = query.count()
    pessoas = query.offset((page - 1) * per_page).limit(per_page).all()
    ids = [p.id for p in pessoas]
    docs_total = docs_validos = 0
    if ids:
        docs = AcessoPessoaDocumento.query.filter(
            AcessoPessoaDocumento.pessoa_id.in_(ids)
        ).all()
        docs_total = len(docs)
        docs_validos = sum(1 for d in docs if d.is_valido_efetivo())
    # KPIs sobre o conjunto filtrado completo (não só a página)
    all_ids = [r.id for r in query.with_entities(AcessoPessoa.id).all()]
    if all_ids:
        all_docs = AcessoPessoaDocumento.query.filter(
            AcessoPessoaDocumento.pessoa_id.in_(all_ids)
        ).all()
        kpi_total = len(all_docs)
        kpi_validos = sum(1 for d in all_docs if d.is_valido_efetivo())
    else:
        kpi_total = kpi_validos = 0
    return jsonify({
        'ok': True,
        'pessoas': [_pessoa_hub_dict(p) for p in pessoas],
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': max((total + per_page - 1) // per_page, 1) if total else 0,
        'kpis': {
            'pessoas': total,
            'documentos_total': kpi_total,
            'documentos_validos': kpi_validos,
            'documentos_pagina': docs_total,
            'documentos_validos_pagina': docs_validos,
        },
    })


def _save_documento_upload(upload, pessoa_id):
    """Salva arquivo em static/acesso_documentos/ e retorna o nome do arquivo."""
    if not upload or not getattr(upload, 'filename', None):
        return None
    original = secure_filename(upload.filename or '')
    if not original:
        return None
    ext = Path(original).suffix.lower()
    if ext not in DOCUMENTOS_ALLOWED_EXT:
        raise ValueError(
            'Tipo de arquivo não permitido. Use PDF, imagem ou Office.'
        )
    DOCUMENTOS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f'p{pessoa_id}_{uuid.uuid4().hex[:12]}{ext}'
    dest = DOCUMENTOS_DIR / fname
    upload.save(dest)
    return fname


def _delete_documento_arquivo(filename):
    if not filename:
        return
    safe = Path(str(filename)).name
    if not safe or safe != str(filename):
        return
    path = DOCUMENTOS_DIR / safe
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


@acesso.route('/acesso/api/hub-documentos/pessoas/<int:pid>/documentos', methods=['GET', 'POST'])
@login_required
def api_hub_pessoa_documentos(pid):
    seed_acesso()
    pessoa = AcessoPessoa.query.get_or_404(pid)
    if request.method == 'GET':
        docs = (
            AcessoPessoaDocumento.query
            .filter_by(pessoa_id=pid)
            .order_by(AcessoPessoaDocumento.id.desc())
            .all()
        )
        return jsonify({
            'ok': True,
            'pessoa': _pessoa_hub_dict(pessoa),
            'documentos': [d.to_dict() for d in docs],
        })

    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form
        upload = request.files.get('arquivo') or request.files.get('file')
    else:
        data = request.get_json(silent=True) or {}
        upload = None

    tipo_id = _parse_int(data.get('tipo_documento_id'))
    if not tipo_id:
        return jsonify({'ok': False, 'error': 'Tipo de documento obrigatório'}), 400
    tipo = AcessoTipoDocumento.query.get(tipo_id)
    if not tipo:
        return jsonify({'ok': False, 'error': 'Tipo de documento inválido'}), 400

    arquivo_nome = None
    try:
        arquivo_nome = _save_documento_upload(upload, pid)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception:
        return jsonify({'ok': False, 'error': 'Falha ao salvar o arquivo'}), 500

    doc = AcessoPessoaDocumento(
        pessoa_id=pid,
        tipo_documento_id=tipo_id,
        numero=(data.get('numero') or '').strip() or None,
        validade=_parse_date(data.get('validade')),
        valido=_parse_bool(data.get('valido'), default=True),
        arquivo=arquivo_nome,
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify({'ok': True, 'documento': doc.to_dict()}), 201


@acesso.route('/acesso/api/hub-documentos/documentos/<int:did>', methods=['PUT', 'DELETE'])
@login_required
def api_hub_documento_item(did):
    seed_acesso()
    doc = AcessoPessoaDocumento.query.get_or_404(did)
    if request.method == 'DELETE':
        arquivo = doc.arquivo
        db.session.delete(doc)
        db.session.commit()
        _delete_documento_arquivo(arquivo)
        return jsonify({'ok': True})

    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form
        upload = request.files.get('arquivo') or request.files.get('file')
    else:
        data = request.get_json(silent=True) or {}
        upload = None

    if 'tipo_documento_id' in data:
        tipo_id = _parse_int(data.get('tipo_documento_id'))
        if not tipo_id or not AcessoTipoDocumento.query.get(tipo_id):
            return jsonify({'ok': False, 'error': 'Tipo de documento inválido'}), 400
        doc.tipo_documento_id = tipo_id
    if 'numero' in data:
        doc.numero = (data.get('numero') or '').strip() or None
    if 'validade' in data:
        doc.validade = _parse_date(data.get('validade'))
    if 'valido' in data:
        doc.valido = _parse_bool(data.get('valido'), default=True)

    if upload and getattr(upload, 'filename', None):
        try:
            novo = _save_documento_upload(upload, doc.pessoa_id)
        except ValueError as e:
            return jsonify({'ok': False, 'error': str(e)}), 400
        except Exception:
            return jsonify({'ok': False, 'error': 'Falha ao salvar o arquivo'}), 500
        if novo:
            antigo = doc.arquivo
            doc.arquivo = novo
            _delete_documento_arquivo(antigo)

    db.session.commit()
    return jsonify({'ok': True, 'documento': doc.to_dict()})


# ---- APIs Eventos ----
@acesso.route('/acesso/api/eventos', methods=['GET', 'POST'])
@login_required
def api_eventos():
    seed_acesso()
    if request.method == 'GET':
        limit = min(int(request.args.get('limit', 100)), 500)
        eventos = AcessoEvento.query.order_by(AcessoEvento.data_hora.desc()).limit(limit).all()
        return jsonify([e.to_dict() for e in eventos])

    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome é obrigatório'}), 400

    eq = None
    if data.get('equipamento_id'):
        eq = AcessoEquipamento.query.get(int(data['equipamento_id']))

    evento = AcessoEvento(
        pessoa_ref=(data.get('pessoa_ref') or '').strip() or None,
        nome=nome,
        tipo_pessoa=(data.get('tipo_pessoa') or 'PESSOA').strip().upper(),
        status=(data.get('status') or 'Liberado').strip(),
        direction=(data.get('direction') or '').strip() or None,
        event_type=(data.get('event_type') or 'manual').strip(),
        equipamento_id=eq.id if eq else None,
        equipamento_nome=eq.nome if eq else (data.get('equipamento_nome') or '').strip() or None,
        cartao=(data.get('cartao') or '').strip() or None,
        girou=(data.get('girou') or '').strip() or None,
        motivo=(data.get('motivo') or '').strip() or None,
        data_hora=datetime.utcnow(),
    )
    db.session.add(evento)
    db.session.commit()
    return jsonify({'ok': True, 'evento': evento.to_dict()}), 201


# ---- APIs Controle Adicional ----
def _controle_adicional_from_payload(data, item=None):
    nome = (data.get('nome') or '').strip()
    tipo = (data.get('tipo') or 'bloqueio').strip().lower()
    data_inicio = _parse_date(data.get('data_inicio'))
    data_fim = _parse_date(data.get('data_fim'))
    pessoa_id = _parse_int(data.get('pessoa_id'))
    motivo = (data.get('motivo') or '').strip() or None

    if not nome:
        return None, ('Nome é obrigatório', 400)
    if tipo not in ('bloqueio', 'liberacao'):
        return None, ('Tipo inválido (bloqueio|liberacao)', 400)
    if not data_inicio:
        return None, ('Data início é obrigatória', 400)
    if data_fim and data_fim < data_inicio:
        return None, ('Data fim não pode ser anterior à data início', 400)

    if pessoa_id:
        pessoa = AcessoPessoa.query.get(pessoa_id)
        if not pessoa:
            return None, ('Pessoa não encontrada', 404)
        if not nome:
            nome = pessoa.nome
    else:
        pessoa_id = None

    if item is None:
        item = AcessoControleAdicional()

    item.pessoa_id = pessoa_id
    item.nome = nome
    item.tipo = tipo
    item.data_inicio = data_inicio
    item.data_fim = data_fim
    item.motivo = motivo
    if 'ativo' in data:
        item.ativo = _parse_bool(data.get('ativo'), True)
    elif item.id is None:
        item.ativo = True
    return item, None


@acesso.route('/acesso/api/controles-adicionais', methods=['GET', 'POST'])
@login_required
def api_controles_adicionais():
    seed_acesso()
    if request.method == 'GET':
        nome = (request.args.get('nome') or '').strip()
        de = _parse_date(request.args.get('de'))
        ate = _parse_date(request.args.get('ate'))
        tipo = (request.args.get('tipo') or '').strip().lower()
        mostrar_expirados = _parse_bool(request.args.get('expirados'), False)

        query = AcessoControleAdicional.query
        if nome:
            query = query.filter(AcessoControleAdicional.nome.ilike(f'%{nome}%'))
        if de:
            query = query.filter(AcessoControleAdicional.data_inicio >= de)
        if ate:
            query = query.filter(AcessoControleAdicional.data_inicio <= ate)
        if tipo in ('bloqueio', 'liberacao'):
            query = query.filter(AcessoControleAdicional.tipo == tipo)
        if not mostrar_expirados:
            hoje = date.today()
            query = query.filter(
                or_(
                    AcessoControleAdicional.data_fim.is_(None),
                    AcessoControleAdicional.data_fim >= hoje,
                )
            )
        items = query.order_by(
            AcessoControleAdicional.data_inicio.desc(),
            AcessoControleAdicional.id.desc(),
        ).limit(500).all()
        return jsonify([c.to_dict() for c in items])

    data = request.get_json(silent=True) or request.form or {}
    item, err = _controle_adicional_from_payload(data)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'controle': item.to_dict()}), 201


@acesso.route('/acesso/api/controles-adicionais/<int:cid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_controle_adicional_item(cid):
    seed_acesso()
    item = AcessoControleAdicional.query.get_or_404(cid)

    if request.method == 'GET':
        return jsonify(item.to_dict())

    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or request.form or {}
    item, err = _controle_adicional_from_payload(data, item=item)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.commit()
    return jsonify({'ok': True, 'controle': item.to_dict()})


# ---- APIs Gerenciamento de Refeições (Parâmetros) ----
TIPOS_COBRANCA_REFEICAO = ('MENSAL', 'DIARIO', 'POR_REFEICAO', 'SEMANAL', 'ISENTO')
TIPO_COBRANCA_LABELS = {
    'MENSAL': 'Mensal',
    'DIARIO': 'Diário',
    'POR_REFEICAO': 'Por refeição',
    'SEMANAL': 'Semanal',
    'ISENTO': 'Isento',
}


def _parse_valor_refeicao(value):
    if value is None or value == '':
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace('R$', '').replace(' ', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif ',' in raw:
        raw = raw.replace(',', '.')
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValueError('Valor inválido')


def _item_refeicao_from_payload(data, item=None, grupo_id=None):
    """Cria/atualiza item. Aceita hora_inicio > hora_fim (cruza meia-noite)."""
    creating = item is None
    if creating:
        item = AcessoItemRefeicao(grupo_id=grupo_id)

    if 'nome' in data or creating:
        nome = (data.get('nome') or '').strip()
        if not nome:
            return None, ('Nome do item é obrigatório', 400)
        item.nome = nome

    # Preço: preco_mensal ou valor
    if 'preco_mensal' in data or 'valor' in data or creating:
        raw_preco = data.get('preco_mensal')
        if raw_preco is None:
            raw_preco = data.get('valor')
        try:
            valor = _parse_valor_refeicao(raw_preco)
        except ValueError as exc:
            return None, (str(exc), 400)
        if valor < 0:
            return None, ('Preço não pode ser negativo', 400)
        item.valor = valor

    # Horários: NÃO rejeitar quando hora_inicio > hora_fim (janela noturna)
    if 'hora_inicio' in data or creating:
        raw_hi = data.get('hora_inicio')
        if raw_hi in (None, ''):
            item.hora_inicio = None
        else:
            hi = _parse_time(raw_hi)
            if hi is None:
                return None, ('Hora início inválida', 400)
            item.hora_inicio = hi

    if 'hora_fim' in data or creating:
        raw_hf = data.get('hora_fim')
        if raw_hf in (None, ''):
            item.hora_fim = None
        else:
            hf = _parse_time(raw_hf)
            if hf is None:
                return None, ('Hora fim inválida', 400)
            item.hora_fim = hf

    if 'ativo' in data or creating:
        item.ativo = _parse_bool(data.get('ativo'), default=True)

    return item, None


def _grupo_refeicao_from_payload(data, grupo=None):
    nome = (data.get('nome') or '').strip()
    if not nome and grupo is None:
        return None, ('Nome é obrigatório', 400)
    if grupo is None:
        grupo = AcessoGrupoRefeicao()
    if nome or 'nome' in data:
        if not nome:
            return None, ('Nome é obrigatório', 400)
        conflito = AcessoGrupoRefeicao.query.filter(
            AcessoGrupoRefeicao.nome == nome,
            AcessoGrupoRefeicao.id != (grupo.id or 0),
        ).first()
        if conflito:
            return None, ('Já existe um grupo com este nome', 400)
        grupo.nome = nome

    if 'tipo_cobranca' in data or grupo.id is None:
        tipo = (data.get('tipo_cobranca') or 'MENSAL').strip().upper()
        if tipo not in TIPOS_COBRANCA_REFEICAO:
            return None, ('Tipo de cobrança inválido', 400)
        grupo.tipo_cobranca = tipo

    # Aceita observacoes ou descricao (legado)
    if 'observacoes' in data or 'descricao' in data or grupo.id is None:
        obs = data.get('observacoes')
        if obs is None:
            obs = data.get('descricao')
        grupo.observacoes = (str(obs).strip() if obs is not None else '') or None

    if 'ativo' in data or grupo.id is None:
        grupo.ativo = _parse_bool(data.get('ativo'), default=True)

    if 'exibir_visitantes' in data or grupo.id is None:
        grupo.exibir_visitantes = _parse_bool(data.get('exibir_visitantes'), default=False)

    return grupo, None


@acesso.route('/acesso/api/grupos-refeicao/pessoas-busca', methods=['GET'])
@login_required
def api_grupos_refeicao_pessoas_busca():
    """Busca pessoas para vínculo em grupos de refeição."""
    seed_acesso()
    q = (request.args.get('q') or '').strip()
    query = AcessoPessoa.query
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoPessoa.nome.ilike(like),
            AcessoPessoa.matricula.ilike(like),
        ))
    pessoas = query.order_by(AcessoPessoa.nome).limit(30).all()
    return jsonify({
        'ok': True,
        'pessoas': [
            {
                'id': p.id,
                'nome': p.nome or '',
                'matricula': p.matricula or '',
                'label': f"{p.nome or ''}{' (' + p.matricula + ')' if p.matricula else ''}".strip(),
            }
            for p in pessoas
        ],
    })


@acesso.route('/acesso/api/grupos-refeicao', methods=['GET', 'POST'])
@login_required
def api_grupos_refeicao():
    seed_acesso()
    if request.method == 'GET':
        q = (request.args.get('q') or '').strip()
        query = AcessoGrupoRefeicao.query
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                AcessoGrupoRefeicao.nome.ilike(like),
                AcessoGrupoRefeicao.observacoes.ilike(like),
                AcessoGrupoRefeicao.tipo_cobranca.ilike(like),
            ))
        grupos = query.order_by(AcessoGrupoRefeicao.nome).all()
        return jsonify({
            'ok': True,
            'total': len(grupos),
            'tipos_cobranca': [
                {'value': k, 'label': TIPO_COBRANCA_LABELS[k]} for k in TIPOS_COBRANCA_REFEICAO
            ],
            'grupos': [g.to_dict() for g in grupos],
        })

    data = request.get_json(silent=True) or request.form or {}
    grupo, err = _grupo_refeicao_from_payload(data)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.add(grupo)
    db.session.commit()
    return jsonify({'ok': True, 'grupo': grupo.to_dict(detalhe=True)}), 201


@acesso.route('/acesso/api/grupos-refeicao/<int:gid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_grupo_refeicao_item(gid):
    seed_acesso()
    grupo = AcessoGrupoRefeicao.query.get_or_404(gid)

    if request.method == 'GET':
        return jsonify({'ok': True, 'grupo': grupo.to_dict(detalhe=True)})

    if request.method == 'DELETE':
        db.session.delete(grupo)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or request.form or {}
    grupo, err = _grupo_refeicao_from_payload(data, grupo=grupo)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.commit()
    return jsonify({'ok': True, 'grupo': grupo.to_dict(detalhe=True)})


@acesso.route('/acesso/api/grupos-refeicao/<int:gid>/itens', methods=['GET', 'POST'])
@login_required
def api_grupo_refeicao_itens(gid):
    seed_acesso()
    grupo = AcessoGrupoRefeicao.query.get_or_404(gid)
    if request.method == 'GET':
        itens = grupo.itens.order_by(AcessoItemRefeicao.nome).all()
        return jsonify({'ok': True, 'itens': [i.to_dict() for i in itens]})

    data = request.get_json(silent=True) or request.form or {}
    item, err = _item_refeicao_from_payload(data, grupo_id=grupo.id)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'item': item.to_dict()}), 201


@acesso.route('/acesso/api/itens-refeicao/<int:iid>', methods=['PUT', 'DELETE'])
@login_required
def api_item_refeicao(iid):
    seed_acesso()
    item = AcessoItemRefeicao.query.get_or_404(iid)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or request.form or {}
    item, err = _item_refeicao_from_payload(data, item=item)
    if err:
        msg, code = err
        return jsonify({'ok': False, 'error': msg}), code
    db.session.commit()
    return jsonify({'ok': True, 'item': item.to_dict()})


@acesso.route('/acesso/api/grupos-refeicao/<int:gid>/vinculos', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_grupo_refeicao_vinculos(gid):
    seed_acesso()
    grupo = AcessoGrupoRefeicao.query.get_or_404(gid)

    if request.method == 'GET':
        q = (request.args.get('q') or '').strip()
        page = max(1, _parse_int(request.args.get('page')) or 1)
        per_page = min(50, max(1, _parse_int(request.args.get('per_page')) or 5))
        query = AcessoVinculoRefeicao.query.filter_by(grupo_id=grupo.id)
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                AcessoVinculoRefeicao.pessoa_nome.ilike(like),
                AcessoVinculoRefeicao.matricula.ilike(like),
            ))
        total = query.count()
        vinculos = (
            query.order_by(AcessoVinculoRefeicao.pessoa_nome)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return jsonify({
            'ok': True,
            'total': total,
            'page': page,
            'per_page': per_page,
            'vinculos': [v.to_dict() for v in vinculos],
        })

    if request.method == 'DELETE':
        # Remover todos os vínculos do grupo
        AcessoVinculoRefeicao.query.filter_by(grupo_id=grupo.id).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or request.form or {}

    # Batch: pessoa_ids
    pessoa_ids = data.get('pessoa_ids')
    if isinstance(pessoa_ids, list):
        adicionados = 0
        for raw_id in pessoa_ids:
            pid = _parse_int(raw_id)
            if not pid:
                continue
            pessoa = AcessoPessoa.query.get(pid)
            if not pessoa:
                continue
            existe = AcessoVinculoRefeicao.query.filter_by(
                grupo_id=grupo.id, pessoa_id=pessoa.id,
            ).first()
            if existe:
                continue
            db.session.add(AcessoVinculoRefeicao(
                grupo_id=grupo.id,
                pessoa_id=pessoa.id,
                pessoa_nome=pessoa.nome or '',
                matricula=pessoa.matricula or None,
            ))
            adicionados += 1
        db.session.commit()
        return jsonify({'ok': True, 'adicionados': adicionados}), 201

    # Single (compat)
    pessoa_id = _parse_int(data.get('pessoa_id'))
    pessoa = AcessoPessoa.query.get(pessoa_id) if pessoa_id else None
    nome = (data.get('pessoa_nome') or data.get('nome') or '').strip()
    matricula = (data.get('matricula') or '').strip() or None

    if pessoa:
        nome = pessoa.nome or nome
        matricula = pessoa.matricula or matricula
        pessoa_id = pessoa.id
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe a pessoa ou o nome'}), 400

    if pessoa_id:
        existe = AcessoVinculoRefeicao.query.filter_by(
            grupo_id=grupo.id, pessoa_id=pessoa_id,
        ).first()
        if existe:
            return jsonify({'ok': False, 'error': 'Pessoa já vinculada a este grupo'}), 400

    vinculo = AcessoVinculoRefeicao(
        grupo_id=grupo.id,
        pessoa_id=pessoa_id,
        pessoa_nome=nome,
        matricula=matricula,
    )
    db.session.add(vinculo)
    db.session.commit()
    return jsonify({'ok': True, 'vinculo': vinculo.to_dict()}), 201


@acesso.route('/acesso/api/grupos-refeicao/<int:gid>/pessoas-disponiveis', methods=['GET'])
@login_required
def api_grupo_refeicao_pessoas_disponiveis(gid):
    """Pessoas ativas ainda não vinculadas a este grupo de refeição."""
    seed_acesso()
    grupo = AcessoGrupoRefeicao.query.get_or_404(gid)
    q = (request.args.get('q') or '').strip()
    page = max(1, _parse_int(request.args.get('page')) or 1)
    per_page = min(50, max(1, _parse_int(request.args.get('per_page')) or 5))

    vinculados_ids = db.session.query(AcessoVinculoRefeicao.pessoa_id).filter(
        AcessoVinculoRefeicao.grupo_id == grupo.id,
        AcessoVinculoRefeicao.pessoa_id.isnot(None),
    )
    query = AcessoPessoa.query.filter(
        or_(AcessoPessoa.status != 'Inativo', AcessoPessoa.status.is_(None)),
        ~AcessoPessoa.id.in_(vinculados_ids),
    )
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoPessoa.nome.ilike(like),
            AcessoPessoa.matricula.ilike(like),
        ))
    total = query.count()
    pessoas = (
        query.order_by(AcessoPessoa.nome)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return jsonify({
        'ok': True,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pessoas': [
            {
                'id': p.id,
                'nome': p.nome or '',
                'matricula': p.matricula or '',
                'label': f"{p.nome or ''}{' (' + p.matricula + ')' if p.matricula else ''}".strip(),
            }
            for p in pessoas
        ],
    })


@acesso.route('/acesso/api/grupos-refeicao/<int:gid>/vinculos/remover', methods=['POST'])
@login_required
def api_grupo_refeicao_vinculos_remover(gid):
    """Remove vínculos selecionados (por id de vínculo ou pessoa_id)."""
    seed_acesso()
    grupo = AcessoGrupoRefeicao.query.get_or_404(gid)
    data = request.get_json(silent=True) or {}
    vinculo_ids = data.get('vinculo_ids') or data.get('ids') or []
    pessoa_ids = data.get('pessoa_ids') or []
    removidos = 0

    if isinstance(vinculo_ids, list) and vinculo_ids:
        ids = [i for i in (_parse_int(x) for x in vinculo_ids) if i]
        if ids:
            removidos = AcessoVinculoRefeicao.query.filter(
                AcessoVinculoRefeicao.grupo_id == grupo.id,
                AcessoVinculoRefeicao.id.in_(ids),
            ).delete(synchronize_session=False)

    if isinstance(pessoa_ids, list) and pessoa_ids:
        pids = [i for i in (_parse_int(x) for x in pessoa_ids) if i]
        if pids:
            n = AcessoVinculoRefeicao.query.filter(
                AcessoVinculoRefeicao.grupo_id == grupo.id,
                AcessoVinculoRefeicao.pessoa_id.in_(pids),
            ).delete(synchronize_session=False)
            removidos += n or 0

    db.session.commit()
    return jsonify({'ok': True, 'removidos': removidos})


@acesso.route('/acesso/api/grupos-refeicao/<int:gid>/vinculos/por-grupo', methods=['POST'])
@login_required
def api_grupo_refeicao_vinculos_por_grupo(gid):
    """Add/Remover em lote a partir de outro grupo de acesso ou de refeição."""
    seed_acesso()
    grupo = AcessoGrupoRefeicao.query.get_or_404(gid)
    data = request.get_json(silent=True) or {}
    acao = (data.get('acao') or 'add').strip().lower()  # add | remove
    origem = (data.get('origem') or 'acesso').strip().lower()  # acesso | refeicao
    origem_id = _parse_int(data.get('grupo_id') or data.get('origem_id'))
    if not origem_id:
        return jsonify({'ok': False, 'error': 'Selecione o grupo de origem'}), 400

    pessoa_ids = []
    if origem == 'refeicao':
        outro = AcessoGrupoRefeicao.query.get(origem_id)
        if not outro:
            return jsonify({'ok': False, 'error': 'Grupo de refeição não encontrado'}), 404
        if outro.id == grupo.id and acao == 'add':
            return jsonify({'ok': False, 'error': 'Selecione outro grupo'}), 400
        pessoa_ids = [
            v.pessoa_id for v in outro.vinculos.filter(
                AcessoVinculoRefeicao.pessoa_id.isnot(None)
            ).all()
            if v.pessoa_id
        ]
    else:
        g_acesso = AcessoGrupo.query.get(origem_id)
        if not g_acesso:
            return jsonify({'ok': False, 'error': 'Grupo de acesso não encontrado'}), 404
        pessoa_ids = [
            p.id for p in AcessoPessoa.query.filter(
                AcessoPessoa.grupo_id == g_acesso.id,
                or_(AcessoPessoa.status != 'Inativo', AcessoPessoa.status.is_(None)),
            ).all()
        ]

    if acao == 'remove':
        if not pessoa_ids:
            return jsonify({'ok': True, 'removidos': 0})
        removidos = AcessoVinculoRefeicao.query.filter(
            AcessoVinculoRefeicao.grupo_id == grupo.id,
            AcessoVinculoRefeicao.pessoa_id.in_(pessoa_ids),
        ).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'ok': True, 'removidos': removidos or 0})

    adicionados = 0
    for pid in pessoa_ids:
        pessoa = AcessoPessoa.query.get(pid)
        if not pessoa:
            continue
        existe = AcessoVinculoRefeicao.query.filter_by(
            grupo_id=grupo.id, pessoa_id=pessoa.id,
        ).first()
        if existe:
            continue
        db.session.add(AcessoVinculoRefeicao(
            grupo_id=grupo.id,
            pessoa_id=pessoa.id,
            pessoa_nome=pessoa.nome or '',
            matricula=pessoa.matricula or None,
        ))
        adicionados += 1
    db.session.commit()
    return jsonify({'ok': True, 'adicionados': adicionados}), 201


@acesso.route('/acesso/api/vinculos-refeicao/<int:vid>', methods=['DELETE'])
@login_required
def api_vinculo_refeicao(vid):
    seed_acesso()
    vinculo = AcessoVinculoRefeicao.query.get_or_404(vid)
    db.session.delete(vinculo)
    db.session.commit()
    return jsonify({'ok': True})


@acesso.route('/acesso/api/grupos-acesso-lista', methods=['GET'])
@login_required
def api_grupos_acesso_lista():
    """Lista simples de grupos de acesso (para Add/Remover por Grupo)."""
    seed_acesso()
    grupos = AcessoGrupo.query.order_by(AcessoGrupo.nome).all()
    return jsonify({
        'ok': True,
        'grupos': [{'id': g.id, 'nome': g.nome or '', 'tipo': 'acesso'} for g in grupos],
    })
