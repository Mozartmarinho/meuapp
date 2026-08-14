"""Rotas do Sistema de Controle de Pesagem."""
from functools import wraps
from datetime import datetime
import os
import socket

from flask import (
    Blueprint, render_template, request, jsonify, redirect,
    url_for, flash, session,
)
from sqlalchemy import func

from models import db, Usuario
from models_pesagem import PesagemBalanca, PesagemLeitura

pesagem = Blueprint('pesagem', __name__, template_folder='templates_pesagem')

# Token do agente local (.exe). Pode sobrescrever com PESAGEM_API_KEY no ambiente.
PESAGEM_API_KEY = os.environ.get('PESAGEM_API_KEY', 'saogeraldo-pesagem-2025')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated


_PESAGEM_ENDPOINT_MENUS = {
    'pesagem.dashboard': 'dashboard',
    'pesagem.balancas_page': 'balancas',
    'pesagem.auditoria': 'auditoria',
    'pesagem.api_listar_leituras': 'dashboard',
    'pesagem.api_balancas': 'balancas',
}


@pesagem.before_request
def _checar_permissao_menu_pesagem():
    if request.endpoint in ('pesagem.api_health', 'pesagem.api_receber_leitura'):
        return None
    if 'user_id' not in session:
        return None
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_sistema('pesagem'):
        flash('Você não tem permissão para o Sistema de Controle de Pesagem.', 'error')
        return redirect(url_for('main.inicio'))
    menu_key = _PESAGEM_ENDPOINT_MENUS.get(request.endpoint)
    if not menu_key:
        return None
    if user.tem_menu('pesagem', menu_key):
        return None
    if (request.path or '').startswith('/api/pesagem/'):
        return jsonify({'ok': False, 'error': 'Você não tem permissão para acessar esta aba.'}), 403
    flash('Você não tem permissão para acessar esta aba.', 'error')
    return redirect(url_for('main.inicio'))


def _check_api_key():
    key = (
        request.headers.get('X-API-Key')
        or request.headers.get('Authorization', '').replace('Bearer ', '').strip()
        or (request.get_json(silent=True) or {}).get('api_key')
        or request.args.get('api_key')
    )
    return key and key == PESAGEM_API_KEY


def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _check_api_key():
            return jsonify({'ok': False, 'error': 'API key inválida'}), 401
        return f(*args, **kwargs)
    return decorated


def seed_pesagem():
    if PesagemBalanca.query.count() == 0:
        db.session.add(PesagemBalanca(
            codigo='BAL-01',
            nome='Balança Principal',
            local='Recepção / Expedição',
            porta_com='COM3',
            ativo=True,
        ))
        db.session.commit()


def _parse_float(value):
    if value is None or value == '':
        return None
    try:
        text = str(value).strip().replace(',', '.')
        return float(text)
    except (TypeError, ValueError):
        return None


# ---- PÁGINAS ----
@pesagem.route('/pesagem')
@login_required
def dashboard():
    seed_pesagem()
    hoje = datetime.utcnow().date()
    inicio_hoje = datetime.combine(hoje, datetime.min.time())

    total_hoje = PesagemLeitura.query.filter(PesagemLeitura.data_leitura >= inicio_hoje).count()
    ultima = PesagemLeitura.query.order_by(PesagemLeitura.data_leitura.desc()).first()
    balancas = PesagemBalanca.query.order_by(PesagemBalanca.codigo).all()
    leituras = (
        PesagemLeitura.query
        .order_by(PesagemLeitura.data_leitura.desc())
        .limit(100)
        .all()
    )
    soma_hoje = (
        db.session.query(func.coalesce(func.sum(PesagemLeitura.peso), 0.0))
        .filter(PesagemLeitura.data_leitura >= inicio_hoje)
        .scalar()
    )

    return render_template(
        'pesagem_dashboard.html',
        balancas=[b.to_dict() for b in balancas],
        leituras=[l.to_dict() for l in leituras],
        total_hoje=total_hoje,
        soma_hoje=float(soma_hoje or 0),
        ultima=ultima.to_dict() if ultima else None,
        api_key=PESAGEM_API_KEY,
        server_hint=request.host_url.rstrip('/'),
        **{'active_page': 'dashboard'},
    )


@pesagem.route('/pesagem/balancas')
@login_required
def balancas_page():
    seed_pesagem()
    balancas = PesagemBalanca.query.order_by(PesagemBalanca.codigo).all()
    return render_template(
        'pesagem_balancas.html',
        balancas=[b.to_dict() for b in balancas],
        **{'active_page': 'balancas'},
    )


@pesagem.route('/pesagem/auditoria')
@login_required
def auditoria():
    """Auditoria dentro do layout de Controle de Pesagem (sidebar preservada)."""
    from datetime import date, timedelta
    from audit_service import listar_logs, ensure_audit_table
    from nutricao_service import _parse_date

    ensure_audit_table()
    hoje = date.today()
    data_de = _parse_date(request.args.get('data_de')) or (hoje - timedelta(days=7))
    data_ate = _parse_date(request.args.get('data_ate')) or hoje
    if 'modulo' in request.args:
        modulo = (request.args.get('modulo') or '').strip() or None
    else:
        modulo = 'pesagem'
    usuario = (request.args.get('usuario') or '').strip() or None
    acao = (request.args.get('acao') or '').strip() or None
    q = (request.args.get('q') or '').strip() or None
    try:
        limit = min(int(request.args.get('limit') or 200), 500)
    except (TypeError, ValueError):
        limit = 200

    total, logs = listar_logs(
        modulo=modulo,
        usuario=usuario,
        acao=acao,
        q=q,
        data_de=data_de,
        data_ate=data_ate,
        limit=limit,
        offset=0,
    )
    return render_template(
        'pesagem_auditoria.html',
        logs=logs,
        total=total,
        filtros={
            'data_de': data_de.isoformat(),
            'data_ate': data_ate.isoformat(),
            'modulo': modulo or '',
            'usuario': usuario or '',
            'acao': acao or '',
            'q': q or '',
            'limit': limit,
        },
        **{'active_page': 'auditoria'},
    )


# ---- API AGENTE ----
@pesagem.route('/api/pesagem/health', methods=['GET'])
def api_health():
    return jsonify({
        'ok': True,
        'servico': 'controle-pesagem',
        'host': socket.gethostname(),
        'hora': datetime.utcnow().isoformat(sep=' ', timespec='seconds') + 'Z',
    })


@pesagem.route('/api/pesagem/leituras', methods=['POST'])
@api_key_required
def api_receber_leitura():
    """Recebe peso do agente Windows (.exe) ou integração."""
    d = request.get_json(force=True, silent=True) or {}
    peso = _parse_float(d.get('peso'))
    if peso is None:
        return jsonify({'ok': False, 'error': 'Campo peso é obrigatório e numérico'}), 400

    codigo = (d.get('balanca_codigo') or d.get('balanca') or 'BAL-01').strip().upper()
    balanca = PesagemBalanca.query.filter_by(codigo=codigo).first()
    if not balanca:
        balanca = PesagemBalanca(
            codigo=codigo,
            nome=d.get('balanca_nome') or f'Balança {codigo}',
            local=d.get('local') or '',
            porta_com=(d.get('porta_com') or '')[:20] or None,
            ativo=True,
        )
        db.session.add(balanca)
        db.session.flush()
    else:
        if d.get('balanca_nome'):
            balanca.nome = str(d.get('balanca_nome'))[:120]
        if d.get('local'):
            balanca.local = str(d.get('local'))[:120]
        if d.get('porta_com'):
            balanca.porta_com = str(d.get('porta_com'))[:20]

    leitura = PesagemLeitura(
        balanca_id=balanca.id,
        balanca_codigo=codigo,
        peso=peso,
        unidade=(d.get('unidade') or 'kg')[:10],
        bruto_serial=(d.get('bruto_serial') or d.get('raw') or '')[:255] or None,
        estavel=bool(d.get('estavel', True)),
        origem=(d.get('origem') or 'agente')[:40],
        computador=(d.get('computador') or '')[:120] or None,
        porta_com=(d.get('porta_com') or '')[:20] or None,
        observacao=(d.get('observacao') or '')[:255] or None,
        data_leitura=datetime.utcnow(),
    )
    db.session.add(leitura)
    if d.get('porta_com'):
        balanca.porta_com = str(d.get('porta_com'))[:20]
    db.session.commit()
    return jsonify({'ok': True, 'id': leitura.id, 'leitura': leitura.to_dict()})


@pesagem.route('/api/pesagem/leituras', methods=['GET'])
@login_required
def api_listar_leituras():
    limit = min(int(request.args.get('limit', 100) or 100), 500)
    codigo = (request.args.get('balanca') or '').strip().upper()
    q = PesagemLeitura.query
    if codigo:
        q = q.filter_by(balanca_codigo=codigo)
    rows = q.order_by(PesagemLeitura.data_leitura.desc()).limit(limit).all()
    return jsonify({'ok': True, 'leituras': [r.to_dict() for r in rows]})


@pesagem.route('/api/pesagem/balancas', methods=['GET', 'POST'])
@login_required
def api_balancas():
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        codigo = (d.get('codigo') or '').strip().upper()
        nome = (d.get('nome') or '').strip()
        if not codigo or not nome:
            return jsonify({'ok': False, 'error': 'codigo e nome são obrigatórios'}), 400
        if PesagemBalanca.query.filter_by(codigo=codigo).first():
            return jsonify({'ok': False, 'error': 'Código já existe'}), 409
        b = PesagemBalanca(
            codigo=codigo,
            nome=nome,
            local=(d.get('local') or '').strip() or None,
            porta_com=(d.get('porta_com') or '').strip() or None,
            ativo=bool(d.get('ativo', True)),
        )
        db.session.add(b)
        db.session.commit()
        return jsonify({'ok': True, 'balanca': b.to_dict()})
    return jsonify({
        'ok': True,
        'balancas': [b.to_dict() for b in PesagemBalanca.query.order_by(PesagemBalanca.codigo).all()],
    })
