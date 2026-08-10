"""Serviço de auditoria — grava logs de ações em todos os módulos."""
from __future__ import annotations

import json
import re
from datetime import datetime, date, timedelta
from typing import Any, Optional

from flask import Request, Response, g, has_request_context, request, session
from sqlalchemy import inspect, or_

from models import db
from models_audit import AuditLog

SENSITIVE_KEYS = {
    'senha', 'password', 'senha_hash', 'token', 'api_key', 'apikey', 'secret',
    'authorization', 'confirm_senha', 'confirmar_senha',
}

SKIP_PATH_PREFIXES = (
    '/static/',
    '/favicon',
)

SKIP_EXACT_PATHS = {
    '/auditoria/api/logs',  # consulta de logs (evita ruído)
    '/login',  # login já registra explicitamente (sucesso/falha)
}

# leituras de balança são muito frequentes — loga resumo curto
LEITURA_PATH = '/api/pesagem/leituras'


def ensure_audit_table():
    """Garante tabela audit_logs (create_all não altera schemas existentes)."""
    try:
        insp = inspect(db.engine)
        if 'audit_logs' not in set(insp.get_table_names()):
            AuditLog.__table__.create(db.engine, checkfirst=True)
            db.session.commit()
    except Exception:
        db.session.rollback()


def _modulo_de_path(path: str) -> str:
    p = (path or '').lower()
    if p.startswith('/nutricao') or p.startswith('/api/nutricao'):
        return 'nutricao'
    if p.startswith('/pesagem') or p.startswith('/api/pesagem'):
        return 'pesagem'
    if p.startswith('/acesso') or p.startswith('/api/acesso'):
        return 'acesso'
    if p.startswith('/auditoria'):
        return 'auditoria'
    if p.startswith('/login') or p.startswith('/logout'):
        return 'sistema'
    return 'chamados'


def _acao_de_metodo(method: str, path: str) -> str:
    m = (method or '').upper()
    pl = (path or '').lower()
    if 'login' in pl:
        return 'login'
    if 'logout' in pl:
        return 'logout'
    if 'toggle' in pl:
        return 'alterar'
    if 'saida' in pl or 'excluir' in pl:
        return 'excluir'
    if 'inserir' in pl or 'novo' in pl:
        return 'criar'
    if m == 'POST':
        return 'criar'
    if m == 'PUT' or m == 'PATCH':
        return 'editar'
    if m == 'DELETE':
        return 'excluir'
    return m.lower() or 'acao'


def _entidade_de_path(path: str) -> str:
    parts = [p for p in (path or '').split('/') if p and not p.isdigit()]
    # remove prefixos conhecidos
    skip = {'api', 'nutricao', 'pesagem', 'acesso', 'auditoria'}
    parts = [p for p in parts if p not in skip]
    if not parts:
        return 'sistema'
    return parts[0][:80]


def _entidade_id_de_path(path: str) -> str:
    nums = re.findall(r'/(\d+)(?:/|$)', path or '')
    return nums[-1] if nums else ''


def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > 4:
        return '...'
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k)
            if key.lower() in SENSITIVE_KEYS or 'senha' in key.lower() or 'password' in key.lower():
                out[key] = '***'
            else:
                out[key] = _sanitize(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_sanitize(x, depth + 1) for x in list(obj)[:30]]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)[:200]


def _payload_resumo(req: Request, max_len: int = 1800) -> str:
    try:
        if req.is_json:
            data = req.get_json(silent=True)
            if data is not None:
                return json.dumps(_sanitize(data), ensure_ascii=False)[:max_len]
        if req.form:
            data = {k: req.form.get(k) for k in req.form.keys()}
            return json.dumps(_sanitize(data), ensure_ascii=False)[:max_len]
        if req.args and req.method in ('GET',):
            return ''
        raw = (req.get_data(as_text=True) or '').strip()
        if raw:
            return raw[:max_len]
    except Exception:
        return ''
    return ''


def _usuario_atual():
    if not has_request_context():
        return None, 'sistema'
    uid = session.get('user_id')
    nome = session.get('user_name') or session.get('user_email') or 'sistema'
    return uid, nome


def registrar_auditoria(
    acao: str,
    *,
    modulo: Optional[str] = None,
    entidade: Optional[str] = None,
    entidade_id: Optional[str] = None,
    detalhe: Any = None,
    metodo: Optional[str] = None,
    caminho: Optional[str] = None,
    status_http: Optional[int] = None,
    sucesso: bool = True,
    usuario_id: Optional[int] = None,
    usuario_nome: Optional[str] = None,
    ip: Optional[str] = None,
):
    """Grava um evento de auditoria (uso explícito ou via hook)."""
    try:
        ensure_audit_table()
        uid, unome = _usuario_atual()
        if usuario_id is not None:
            uid = usuario_id
        if usuario_nome:
            unome = usuario_nome

        if detalhe is None:
            det = ''
        elif isinstance(detalhe, str):
            det = detalhe[:4000]
        else:
            det = json.dumps(_sanitize(detalhe), ensure_ascii=False)[:4000]

        path = caminho
        if path is None and has_request_context():
            path = request.path
        method = metodo
        if method is None and has_request_context():
            method = request.method
        if ip is None and has_request_context():
            ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()

        ua = ''
        if has_request_context():
            ua = (request.headers.get('User-Agent') or '')[:255]

        row = AuditLog(
            data_hora=datetime.utcnow(),
            usuario_id=uid,
            usuario_nome=(unome or 'sistema')[:120],
            modulo=(modulo or _modulo_de_path(path or ''))[:40],
            acao=(acao or 'acao')[:40],
            entidade=(entidade or _entidade_de_path(path or ''))[:80],
            entidade_id=str(entidade_id or _entidade_id_de_path(path or ''))[:40],
            metodo=(method or '')[:10],
            caminho=(path or '')[:255],
            status_http=status_http,
            ip=(ip or '')[:60],
            user_agent=ua,
            detalhe=det,
            sucesso=bool(sucesso),
        )
        db.session.add(row)
        db.session.commit()
        return row
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def deve_auditar_request(req: Request) -> bool:
    method = (req.method or '').upper()
    if method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return False
    path = req.path or ''
    if any(path.startswith(p) for p in SKIP_PATH_PREFIXES):
        return False
    if path in SKIP_EXACT_PATHS:
        return False
    # logout é GET — tratado à parte se necessário
    return True


def log_from_request(req: Request, resp: Response):
    """Hook after_request: registra mutações HTTP."""
    if not deve_auditar_request(req):
        return
    # evita logar a própria gravação em loop (não ocorre, mas seguro)
    if getattr(g, '_audit_skip', False):
        return

    status = getattr(resp, 'status_code', 200) or 200
    path = req.path or ''
    detalhe = _payload_resumo(req, max_len=600 if path == LEITURA_PATH else 1800)
    if path == LEITURA_PATH and not detalhe:
        detalhe = 'leitura de balança'

    registrar_auditoria(
        acao=_acao_de_metodo(req.method, path),
        modulo=_modulo_de_path(path),
        entidade=_entidade_de_path(path),
        entidade_id=_entidade_id_de_path(path),
        detalhe=detalhe,
        metodo=req.method,
        caminho=path,
        status_http=status,
        sucesso=200 <= status < 400,
    )


def listar_logs(
    *,
    modulo: Optional[str] = None,
    usuario: Optional[str] = None,
    acao: Optional[str] = None,
    q: Optional[str] = None,
    data_de: Optional[date] = None,
    data_ate: Optional[date] = None,
    limit: int = 200,
    offset: int = 0,
):
    ensure_audit_table()
    query = AuditLog.query
    if modulo:
        query = query.filter(AuditLog.modulo == modulo)
    if acao:
        query = query.filter(AuditLog.acao == acao)
    if usuario:
        query = query.filter(AuditLog.usuario_nome.ilike(f'%{usuario.strip()}%'))
    if q:
        like = f'%{q.strip()}%'
        query = query.filter(
            or_(
                AuditLog.caminho.ilike(like),
                AuditLog.entidade.ilike(like),
                AuditLog.detalhe.ilike(like),
                AuditLog.usuario_nome.ilike(like),
            )
        )
    if data_de:
        query = query.filter(AuditLog.data_hora >= datetime.combine(data_de, datetime.min.time()))
    if data_ate:
        fim = datetime.combine(data_ate, datetime.max.time())
        query = query.filter(AuditLog.data_hora <= fim)

    total = query.count()
    rows = (
        query.order_by(AuditLog.data_hora.desc(), AuditLog.id.desc())
        .offset(max(0, offset))
        .limit(min(limit or 200, 500))
        .all()
    )
    return total, [r.to_dict() for r in rows]


def register_audit_hooks(app):
    """Registra after_request global no app Flask."""

    @app.after_request
    def _audit_after_request(response):
        try:
            if has_request_context():
                log_from_request(request, response)
        except Exception:
            pass
        return response

    @app.before_request
    def _audit_ensure():
        # cria tabela sob demanda na primeira request
        if not getattr(g, '_audit_table_ok', False):
            try:
                ensure_audit_table()
                g._audit_table_ok = True
            except Exception:
                pass
