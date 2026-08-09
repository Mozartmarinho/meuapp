from datetime import date, timedelta

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from functools import wraps

from audit_service import listar_logs, ensure_audit_table
from nutricao_service import _parse_date

auditoria = Blueprint('auditoria', __name__, template_folder='templates_auditoria')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Faça login para acessar a auditoria.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated


def active(page):
    return dict(active_page=page)


@auditoria.route('/auditoria')
@login_required
def dashboard():
    ensure_audit_table()
    hoje = date.today()
    data_de = _parse_date(request.args.get('data_de')) or (hoje - timedelta(days=7))
    data_ate = _parse_date(request.args.get('data_ate')) or hoje
    modulo = (request.args.get('modulo') or '').strip() or None
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
        'auditoria_dashboard.html',
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
        **active('dashboard')
    )


@auditoria.route('/auditoria/api/logs', methods=['GET'])
@login_required
def api_logs():
    ensure_audit_table()
    data_de = _parse_date(request.args.get('data_de'))
    data_ate = _parse_date(request.args.get('data_ate'))
    try:
        limit = min(int(request.args.get('limit') or 200), 500)
        offset = max(int(request.args.get('offset') or 0), 0)
    except (TypeError, ValueError):
        limit, offset = 200, 0
    total, logs = listar_logs(
        modulo=(request.args.get('modulo') or '').strip() or None,
        usuario=(request.args.get('usuario') or '').strip() or None,
        acao=(request.args.get('acao') or '').strip() or None,
        q=(request.args.get('q') or '').strip() or None,
        data_de=data_de,
        data_ate=data_ate,
        limit=limit,
        offset=offset,
    )
    return jsonify({'ok': True, 'total': total, 'logs': logs})
