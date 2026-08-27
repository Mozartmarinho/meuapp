"""Rotas do Sistema de Controle de Pesagem."""
from functools import wraps
from datetime import date, datetime, timedelta
from pathlib import Path
import os
import socket
import uuid

from flask import (
    Blueprint, render_template, request, jsonify, redirect,
    url_for, flash, session, send_file,
)
from sqlalchemy import func
from werkzeug.utils import secure_filename

from models import db, Usuario
from models_pesagem import (
    PesagemBalanca,
    PesagemCliente,
    PesagemLeitura,
    PesagemWhatsAppDestino,
    PesagemWhatsAppEnvio,
)

pesagem = Blueprint('pesagem', __name__, template_folder='templates_pesagem')

# Token do agente local (.exe). Pode sobrescrever com PESAGEM_API_KEY no ambiente.
PESAGEM_API_KEY = os.environ.get('PESAGEM_API_KEY', 'saogeraldo-pesagem-2025')
_FOTO_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}
_UPLOAD_CLIENTES = Path(__file__).resolve().parent / 'static' / 'uploads' / 'pesagem_clientes'
_MAX_IMG_BYTES = 8 * 1024 * 1024
_AGENTE_DIR = Path(__file__).resolve().parent / 'agente_pesagem'
_AGENTE_DOWNLOAD_DIR = Path(__file__).resolve().parent / 'static' / 'downloads' / 'agente_pesagem'
_AGENTE_DOWNLOADS = {
    'AgentePesagem.exe': 'application/vnd.microsoft.portable-executable',
    'config.json': 'application/json',
    'instalar_inicio_windows.bat': 'application/x-bat',
}
_EXE_MIME = 'application/vnd.microsoft.portable-executable'


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
    'pesagem.dashboard_imprimir': 'dashboard',
    'pesagem.balancas_page': 'balancas',
    'pesagem.clientes_page': 'clientes',
    'pesagem.whatsapp_page': 'whatsapp',
    'pesagem.auditoria': 'auditoria',
    'pesagem.download_agente_arquivo': 'dashboard',
    'pesagem.api_listar_leituras': 'dashboard',
    'pesagem.api_excluir_leitura': 'dashboard',
    'pesagem.api_balancas': 'balancas',
    'pesagem.api_balanca': 'balancas',
    'pesagem.api_listar_clientes': 'clientes',
    'pesagem.api_criar_cliente': 'clientes',
    'pesagem.api_cliente': 'clientes',
    'pesagem.api_whatsapp_status': 'whatsapp',
    'pesagem.api_whatsapp_logout': 'whatsapp',
    'pesagem.api_whatsapp_preview': 'whatsapp',
    'pesagem.api_whatsapp_destinos': 'whatsapp',
    'pesagem.api_whatsapp_destino': 'whatsapp',
    'pesagem.api_whatsapp_enviar': 'whatsapp',
}


@pesagem.before_request
def _checar_permissao_menu_pesagem():
    if request.endpoint in ('pesagem.api_health', 'pesagem.api_receber_leitura'):
        return None
    path = (request.path or '').rstrip('/')
    # AgentePesagem.exe: lista clientes e envios do dia; exclusão de peso enviado errado
    if _check_api_key() and request.endpoint in (
        'pesagem.api_listar_clientes',
        'pesagem.api_listar_leituras',
        'pesagem.api_excluir_leitura',
    ):
        return None
    if request.method == 'GET' and path == '/api/pesagem/clientes' and _check_api_key():
        return None
    if request.endpoint == 'pesagem.api_listar_clientes' and _check_api_key():
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
        or request.headers.get('X-Api-Key')
        or request.headers.get('Authorization', '').replace('Bearer ', '').strip()
        or request.args.get('api_key')
    )
    if not key and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        key = (request.get_json(silent=True) or {}).get('api_key')
    return bool(key) and key == PESAGEM_API_KEY


def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _check_api_key():
            return jsonify({'ok': False, 'error': 'API key inválida'}), 401
        return f(*args, **kwargs)
    return decorated


def _api_key_ou_login():
    """Agente (X-API-Key) ou tela web (sessão). Resposta JSON, sem redirect de login."""
    if _check_api_key() or 'user_id' in session:
        return None
    return jsonify({'ok': False, 'error': 'Não autorizado'}), 401


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


def _agente_pesagem_version() -> str:
    src = _AGENTE_DIR / 'agente_pesagem.py'
    try:
        for line in src.read_text(encoding='utf-8').splitlines():
            stripped = line.strip()
            if stripped.startswith('APP_VERSION'):
                return stripped.split('=', 1)[1].strip().strip('\'"')
    except OSError:
        pass
    return '1.2.0'


def _agente_exe_download_name() -> str:
    return f'AgentePesagem-{_agente_pesagem_version()}.exe'


@pesagem.route('/pesagem/download/<path:nome>')
@login_required
def download_agente_arquivo(nome):
    """Serve o .exe/.json/.bat publicados por build_exe.bat, sem cache do navegador."""
    nome = Path(nome).name
    versioned_exe = _agente_exe_download_name()
    if nome in ('AgentePesagem.exe', versioned_exe):
        mime = _EXE_MIME
        path_versioned = _AGENTE_DOWNLOAD_DIR / versioned_exe
        path_plain = _AGENTE_DOWNLOAD_DIR / 'AgentePesagem.exe'
        path = path_versioned if path_versioned.is_file() else path_plain
        download_name = versioned_exe
    else:
        mime = _AGENTE_DOWNLOADS.get(nome)
        path = _AGENTE_DOWNLOAD_DIR / nome
        download_name = nome
    if not mime:
        return 'Arquivo não permitido.', 404
    if not path.is_file():
        return (
            f'{nome} não encontrado. Gere com agente_pesagem/build_exe.bat.',
            404,
        )
    resp = send_file(
        path,
        as_attachment=True,
        download_name=download_name,
        mimetype=mime,
        conditional=False,
        etag=False,
        max_age=0,
    )
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['Content-Disposition'] = f'attachment; filename="{download_name}"'
    return resp


def _imagem_url_cliente(cliente):
    """URL da foto do Cadastro de Cliente (pesagem). Relativa para o agente prefixar o servidor."""
    if not cliente or not cliente.imagem_path:
        return ''
    rel = str(cliente.imagem_path).replace('\\', '/').lstrip('/')
    if not rel.startswith('uploads/pesagem_clientes/'):
        return ''
    return f'/static/{rel}'


def _cliente_to_dict(cliente):
    return cliente.to_dict(imagem_url=_imagem_url_cliente(cliente))


def _apagar_arquivo_cliente(rel_path):
    if not rel_path:
        return
    rel = str(rel_path).replace('\\', '/').lstrip('/')
    if not rel.startswith('uploads/pesagem_clientes/'):
        return
    dest = Path(__file__).resolve().parent / 'static' / rel
    try:
        if dest.is_file():
            dest.unlink()
    except OSError:
        pass


def _salvar_imagem_cliente(upload, cliente_id):
    if not upload or not getattr(upload, 'filename', None):
        return None
    original = secure_filename(upload.filename or '')
    if not original:
        return None
    ext = Path(original).suffix.lower()
    if ext not in _FOTO_EXTS:
        raise ValueError('Use uma imagem JPG, PNG, WEBP, GIF ou BMP.')
    upload.stream.seek(0, os.SEEK_END)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if size > _MAX_IMG_BYTES:
        raise ValueError('Imagem maior que 8 MB.')
    _UPLOAD_CLIENTES.mkdir(parents=True, exist_ok=True)
    fname = f'cli_{int(cliente_id)}_{uuid.uuid4().hex[:10]}{ext}'
    dest = _UPLOAD_CLIENTES / fname
    upload.save(str(dest))
    return f'uploads/pesagem_clientes/{fname}'


def _resolver_cliente_leitura(d):
    """Resolve cliente cadastrado (pesagem_clientes) a partir do agente."""
    cliente_id = None
    raw_id = d.get('cliente_id')
    if raw_id not in (None, '', 0, '0'):
        try:
            cliente_id = int(raw_id)
        except (TypeError, ValueError):
            cliente_id = None
    nome = (d.get('cliente_nome') or d.get('cliente') or '').strip()[:120] or None
    if cliente_id:
        cli = PesagemCliente.query.get(cliente_id)
        if cli:
            return cli.id, nome or cli.nome
    if nome:
        cli = PesagemCliente.query.filter_by(nome=nome).first()
        if cli:
            return cli.id, cli.nome
    return None, None


def _resolver_data_leitura(d):
    raw = d.get('data_hora') or d.get('data_leitura')
    if not raw:
        return datetime.now()
    text = str(raw).strip().replace('Z', '')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now()


def _parse_float(value):
    if value is None or value == '':
        return None
    try:
        text = str(value).strip().replace(',', '.')
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_date_arg(value):
    if not value:
        return None
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return None


def _filtros_leituras_from_request(args=None):
    """Lê filtros da query string para o dashboard / impressão."""
    args = args if args is not None else request.args
    hoje = date.today()

    tem_param = any(k in args for k in ('data_de', 'data_ate', 'cliente_id', 'balanca', 'q', 'limit'))
    data_de = _parse_date_arg(args.get('data_de'))
    data_ate = _parse_date_arg(args.get('data_ate'))

    # Primeira carga (sem query): últimos 7 dias
    if not tem_param:
        data_de = hoje - timedelta(days=7)
        data_ate = hoje

    cliente_id = None
    raw_cli = args.get('cliente_id')
    if raw_cli not in (None, '', '0'):
        try:
            cliente_id = int(raw_cli)
        except (TypeError, ValueError):
            cliente_id = None

    balanca = (args.get('balanca') or '').strip().upper() or None
    q = (args.get('q') or '').strip() or None
    try:
        limit = min(int(args.get('limit') or 500), 2000)
    except (TypeError, ValueError):
        limit = 500

    if data_de and data_ate and data_de > data_ate:
        data_de, data_ate = data_ate, data_de

    return {
        'data_de': data_de,
        'data_ate': data_ate,
        'cliente_id': cliente_id,
        'balanca': balanca,
        'q': q,
        'limit': limit,
    }


def _aplicar_filtros_leituras(query, filtros):
    data_de = filtros.get('data_de')
    data_ate = filtros.get('data_ate')
    if data_de:
        query = query.filter(
            PesagemLeitura.data_leitura >= datetime.combine(data_de, datetime.min.time())
        )
    if data_ate:
        query = query.filter(
            PesagemLeitura.data_leitura
            <= datetime.combine(data_ate, datetime.max.time()).replace(microsecond=0)
        )
    if filtros.get('cliente_id'):
        query = query.filter(PesagemLeitura.cliente_id == filtros['cliente_id'])
    if filtros.get('balanca'):
        query = query.filter(PesagemLeitura.balanca_codigo == filtros['balanca'])
    if filtros.get('q'):
        like = f"%{filtros['q']}%"
        query = query.filter(
            db.or_(
                PesagemLeitura.cliente_nome.ilike(like),
                PesagemLeitura.balanca_codigo.ilike(like),
                PesagemLeitura.computador.ilike(like),
                PesagemLeitura.observacao.ilike(like),
            )
        )
    return query


def _rotulo_filtros(filtros, cliente_nome=None):
    partes = []
    if filtros.get('data_de') or filtros.get('data_ate'):
        de = filtros['data_de'].strftime('%d/%m/%Y') if filtros.get('data_de') else '—'
        ate = filtros['data_ate'].strftime('%d/%m/%Y') if filtros.get('data_ate') else '—'
        partes.append(f'Período: {de} a {ate}')
    else:
        partes.append('Período: todos')
    if filtros.get('cliente_id'):
        partes.append(f'Cliente: {cliente_nome or ("#" + str(filtros["cliente_id"]))}')
    else:
        partes.append('Cliente: todos')
    if filtros.get('balanca'):
        partes.append(f'Balança: {filtros["balanca"]}')
    else:
        partes.append('Balança: todas')
    if filtros.get('q'):
        partes.append(f'Busca: {filtros["q"]}')
    return ' · '.join(partes)


def _resumo_leituras(filtros):
    q = _aplicar_filtros_leituras(PesagemLeitura.query, filtros)
    total = q.count()
    soma = (
        _aplicar_filtros_leituras(
            db.session.query(func.coalesce(func.sum(PesagemLeitura.peso), 0.0)),
            filtros,
        ).scalar()
    )
    media = None
    if total:
        media = (
            _aplicar_filtros_leituras(
                db.session.query(func.avg(PesagemLeitura.peso)),
                filtros,
            ).scalar()
        )
    ultima = q.order_by(PesagemLeitura.data_leitura.desc()).first()
    return {
        'total': int(total or 0),
        'soma': float(soma or 0),
        'media': float(media or 0),
        'ultima': ultima.to_dict() if ultima else None,
    }


def _consultar_dashboard(filtros):
    resumo = _resumo_leituras(filtros)
    leituras = (
        _aplicar_filtros_leituras(PesagemLeitura.query, filtros)
        .order_by(PesagemLeitura.data_leitura.desc())
        .limit(filtros.get('limit') or 500)
        .all()
    )
    cliente_nome = None
    if filtros.get('cliente_id'):
        cli = PesagemCliente.query.get(filtros['cliente_id'])
        cliente_nome = cli.nome if cli else None
    return resumo, leituras, cliente_nome


# ---- PÁGINAS ----
@pesagem.route('/pesagem')
@login_required
def dashboard():
    seed_pesagem()
    filtros = _filtros_leituras_from_request()
    resumo, leituras, cliente_nome = _consultar_dashboard(filtros)

    hoje = date.today()
    inicio_hoje = datetime.combine(hoje, datetime.min.time())
    total_hoje = PesagemLeitura.query.filter(PesagemLeitura.data_leitura >= inicio_hoje).count()
    soma_hoje = (
        db.session.query(func.coalesce(func.sum(PesagemLeitura.peso), 0.0))
        .filter(PesagemLeitura.data_leitura >= inicio_hoje)
        .scalar()
    )

    clientes = PesagemCliente.query.order_by(PesagemCliente.nome).all()
    balancas = PesagemBalanca.query.order_by(PesagemBalanca.codigo).all()

    filtros_ui = {
        'data_de': filtros['data_de'].isoformat() if filtros.get('data_de') else '',
        'data_ate': filtros['data_ate'].isoformat() if filtros.get('data_ate') else '',
        'cliente_id': filtros.get('cliente_id') or '',
        'balanca': filtros.get('balanca') or '',
        'q': filtros.get('q') or '',
        'limit': filtros.get('limit') or 500,
        'rotulo': _rotulo_filtros(filtros, cliente_nome),
        'cliente_nome': cliente_nome or '',
    }

    return render_template(
        'pesagem_dashboard.html',
        balancas=[b.to_dict() for b in balancas],
        clientes=[_cliente_to_dict(c) for c in clientes],
        leituras=[l.to_dict() for l in leituras],
        total_hoje=total_hoje,
        soma_hoje=float(soma_hoje or 0),
        total_filtro=resumo['total'],
        soma_filtro=resumo['soma'],
        media_filtro=resumo['media'],
        ultima=resumo['ultima'],
        filtros=filtros_ui,
        api_key=PESAGEM_API_KEY,
        server_hint=request.host_url.rstrip('/'),
        agente_versao=_agente_pesagem_version(),
        **{'active_page': 'dashboard'},
    )


@pesagem.route('/pesagem/imprimir')
@login_required
def dashboard_imprimir():
    """Impressão das leituras com os mesmos filtros da tela."""
    seed_pesagem()
    filtros = _filtros_leituras_from_request()
    filtros['limit'] = min(int(filtros.get('limit') or 2000), 2000)
    resumo, leituras, cliente_nome = _consultar_dashboard(filtros)
    return render_template(
        'pesagem_dashboard_print.html',
        leituras=[l.to_dict() for l in leituras],
        total=resumo['total'],
        soma=resumo['soma'],
        media=resumo['media'],
        filtros_rotulo=_rotulo_filtros(filtros, cliente_nome),
        filtros={
            'data_de': filtros['data_de'].strftime('%d/%m/%Y') if filtros.get('data_de') else '—',
            'data_ate': filtros['data_ate'].strftime('%d/%m/%Y') if filtros.get('data_ate') else '—',
            'cliente': cliente_nome or 'Todos',
            'balanca': filtros.get('balanca') or 'Todas',
            'q': filtros.get('q') or '',
        },
        gerado_em=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
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


@pesagem.route('/pesagem/clientes')
@login_required
def clientes_page():
    clientes = PesagemCliente.query.order_by(PesagemCliente.nome).all()
    return render_template(
        'pesagem_clientes.html',
        clientes=[_cliente_to_dict(c) for c in clientes],
        **{'active_page': 'clientes'},
    )


@pesagem.route('/pesagem/whatsapp')
@login_required
def whatsapp_page():
    from whatsapp_pesagem import ultimo_envio_por_destino

    destinos = PesagemWhatsAppDestino.query.order_by(PesagemWhatsAppDestino.nome).all()
    ids = [d.id for d in destinos]
    return render_template(
        'pesagem_whatsapp.html',
        destinos=[d.to_dict() for d in destinos],
        ultimos=ultimo_envio_por_destino(ids),
        **{'active_page': 'whatsapp'},
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

    tara = _parse_float(d.get('tara'))
    if tara is None:
        tara = 0.0
    peso_liquido = _parse_float(d.get('peso_liquido'))
    if peso_liquido is None:
        peso_liquido = _parse_float(d.get('liquido') or d.get('peso_liq'))
    if peso_liquido is None:
        peso_liquido = peso
    peso_bruto = _parse_float(d.get('peso_bruto'))
    if peso_bruto is None:
        peso_bruto = _parse_float(d.get('bruto'))
    if peso_bruto is None:
        peso_bruto = round(peso_liquido + tara, 4) if abs(tara) >= 0.0005 else peso_liquido
    # Peso gravado = líquido (produto), não o total da balança
    peso = peso_liquido

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

    cliente_id, cliente_nome = _resolver_cliente_leitura(d)
    if not cliente_id:
        return jsonify({
            'ok': False,
            'error': 'Cliente selecionado é obrigatório e deve estar cadastrado.',
        }), 400

    leitura = PesagemLeitura(
        balanca_id=balanca.id,
        balanca_codigo=codigo,
        peso=peso,
        unidade=(d.get('unidade') or 'kg')[:10],
        tara=tara,
        peso_bruto=peso_bruto,
        peso_liquido=peso_liquido,
        bruto_serial=(d.get('bruto_serial') or d.get('raw') or '')[:255] or None,
        estavel=bool(d.get('estavel', True)),
        origem=(d.get('origem') or 'agente')[:40],
        computador=(d.get('computador') or '')[:120] or None,
        porta_com=(d.get('porta_com') or '')[:20] or None,
        observacao=(d.get('observacao') or '')[:255] or None,
        cliente_id=cliente_id,
        cliente_nome=cliente_nome,
        data_leitura=_resolver_data_leitura(d),
    )
    db.session.add(leitura)
    if d.get('porta_com'):
        balanca.porta_com = str(d.get('porta_com'))[:20]
    db.session.commit()
    return jsonify({'ok': True, 'id': leitura.id, 'leitura': leitura.to_dict()})


@pesagem.route('/api/pesagem/leituras', methods=['GET'])
def api_listar_leituras():
    """Lista leituras para o dashboard e para o agente (envios do dia)."""
    auth = _api_key_ou_login()
    if auth:
        return auth
    filtros = {
        'data_de': _parse_date_arg(request.args.get('data_de')),
        'data_ate': _parse_date_arg(request.args.get('data_ate')),
        'cliente_id': None,
        'balanca': (request.args.get('balanca') or '').strip().upper() or None,
        'q': (request.args.get('q') or '').strip() or None,
        'limit': min(int(request.args.get('limit', 100) or 100), 500),
    }
    raw_cli = request.args.get('cliente_id')
    if raw_cli not in (None, '', '0'):
        try:
            filtros['cliente_id'] = int(raw_cli)
        except (TypeError, ValueError):
            pass
    rows = (
        _aplicar_filtros_leituras(PesagemLeitura.query, filtros)
        .order_by(PesagemLeitura.data_leitura.desc())
        .limit(filtros['limit'])
        .all()
    )
    return jsonify({'ok': True, 'leituras': [r.to_dict() for r in rows]})


@pesagem.route('/api/pesagem/leituras/<int:lid>', methods=['DELETE'])
def api_excluir_leitura(lid):
    """Remove um lançamento de pesagem (dashboard ou agente — peso enviado errado)."""
    auth = _api_key_ou_login()
    if auth:
        return auth
    leitura = PesagemLeitura.query.get(lid)
    if not leitura:
        return jsonify({'ok': False, 'error': 'Lançamento não encontrado'}), 404
    db.session.delete(leitura)
    db.session.commit()
    return jsonify({'ok': True, 'id': lid})


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


@pesagem.route('/api/pesagem/balancas/<int:bid>', methods=['PUT', 'DELETE'])
@login_required
def api_balanca(bid):
    b = PesagemBalanca.query.get(bid)
    if not b:
        return jsonify({'ok': False, 'error': 'Balança não encontrada'}), 404

    if request.method == 'DELETE':
        PesagemLeitura.query.filter_by(balanca_id=b.id).update(
            {PesagemLeitura.balanca_id: None}, synchronize_session=False
        )
        db.session.delete(b)
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    codigo = (d.get('codigo') or '').strip().upper()
    nome = (d.get('nome') or '').strip()
    if not codigo or not nome:
        return jsonify({'ok': False, 'error': 'codigo e nome são obrigatórios'}), 400
    outro = PesagemBalanca.query.filter(
        PesagemBalanca.codigo == codigo, PesagemBalanca.id != b.id
    ).first()
    if outro:
        return jsonify({'ok': False, 'error': 'Código já existe'}), 409
    b.codigo = codigo
    b.nome = nome
    b.local = (d.get('local') or '').strip() or None
    b.porta_com = (d.get('porta_com') or '').strip() or None
    if 'ativo' in d:
        b.ativo = bool(d.get('ativo'))
    db.session.commit()
    return jsonify({'ok': True, 'balanca': b.to_dict()})


@pesagem.route('/api/pesagem/clientes', methods=['GET'])
def api_listar_clientes():
    """Lista o Cadastro de Cliente da pesagem (tabela pesagem_clientes), não os clientes de Chamados.

    AgentePesagem.exe autentica com X-API-Key; a tela web usa a sessão.
    """
    if not _check_api_key() and 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'Não autorizado'}), 401
    rows = PesagemCliente.query.order_by(PesagemCliente.nome).all()
    return jsonify({'ok': True, 'clientes': [_cliente_to_dict(c) for c in rows]})


@pesagem.route('/api/pesagem/clientes', methods=['POST'])
@login_required
def api_criar_cliente():
    nome = (request.form.get('nome') or '').strip()
    if not nome and request.is_json:
        nome = ((request.get_json(silent=True) or {}).get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome do cliente é obrigatório'}), 400
    c = PesagemCliente(nome=nome[:120])
    db.session.add(c)
    db.session.flush()
    try:
        path = _salvar_imagem_cliente(request.files.get('imagem'), c.id)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    if path:
        c.imagem_path = path
    db.session.commit()
    return jsonify({'ok': True, 'cliente': _cliente_to_dict(c)})


@pesagem.route('/api/pesagem/clientes/<int:cid>', methods=['PUT', 'DELETE'])
@login_required
def api_cliente(cid):
    c = PesagemCliente.query.get(cid)
    if not c:
        return jsonify({'ok': False, 'error': 'Cliente não encontrado'}), 404

    if request.method == 'DELETE':
        PesagemLeitura.query.filter_by(cliente_id=c.id).update(
            {PesagemLeitura.cliente_id: None}, synchronize_session=False
        )
        _apagar_arquivo_cliente(c.imagem_path)
        db.session.delete(c)
        db.session.commit()
        return jsonify({'ok': True})

    nome = (request.form.get('nome') or '').strip()
    if not nome and request.is_json:
        nome = ((request.get_json(silent=True) or {}).get('nome') or '').strip()
    if not nome:
        nome = (c.nome or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome do cliente é obrigatório'}), 400
    c.nome = nome[:120]
    upload = request.files.get('imagem')
    if upload and getattr(upload, 'filename', None):
        try:
            path = _salvar_imagem_cliente(upload, c.id)
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        if path:
            _apagar_arquivo_cliente(c.imagem_path)
            c.imagem_path = path
    db.session.commit()
    return jsonify({'ok': True, 'cliente': _cliente_to_dict(c)})


def _destino_payload():
    from whatsapp_pesagem import parse_hora, telefone_valido, normalizar_telefone

    d = request.get_json(silent=True) or {}
    nome = (d.get('nome') or '').strip()[:120]
    telefone_raw = (d.get('telefone') or '').strip()
    hora = parse_hora(d.get('hora'))
    mensagem = (d.get('mensagem') if d.get('mensagem') is not None else '')
    mensagem = str(mensagem).strip()
    ativo = d.get('ativo', True)
    if isinstance(ativo, str):
        ativo = ativo.lower() in ('1', 'true', 'on', 'sim')
    else:
        ativo = bool(ativo)
    erros = []
    if not nome:
        erros.append('Nome é obrigatório')
    if not telefone_valido(telefone_raw):
        erros.append('Telefone inválido. Use DDD + número, com ou sem 55.')
    if not hora:
        erros.append('Hora inválida')
    if erros:
        return None, erros
    return {
        'nome': nome,
        'telefone': normalizar_telefone(telefone_raw),
        'hora': hora,
        'mensagem': mensagem,
        'ativo': ativo,
    }, None


@pesagem.route('/api/pesagem/whatsapp/status', methods=['GET'])
@login_required
def api_whatsapp_status():
    from whatsapp_pesagem import status_whatsapp
    return jsonify(status_whatsapp())


@pesagem.route('/api/pesagem/whatsapp/logout', methods=['POST'])
@login_required
def api_whatsapp_logout():
    from whatsapp_pesagem import logout_whatsapp
    result = logout_whatsapp()
    code = 200 if result.get('ok') else 400
    return jsonify(result), code


@pesagem.route('/api/pesagem/whatsapp/preview', methods=['GET'])
@login_required
def api_whatsapp_preview():
    from whatsapp_pesagem import montar_mensagem, totais_bruto_do_dia

    template = (request.args.get('mensagem') or '').strip()
    if not template:
        dest_id = request.args.get('destino_id')
        if dest_id:
            dest = PesagemWhatsAppDestino.query.get(dest_id)
            if dest:
                template = dest.mensagem or ''
        if not template:
            primeiro = PesagemWhatsAppDestino.query.filter_by(ativo=True).order_by(
                PesagemWhatsAppDestino.id
            ).first()
            if primeiro:
                template = primeiro.mensagem or ''
    if not template:
        template = 'Resumo da pesagem de hoje:'
    dia = _parse_date_arg(request.args.get('data')) or date.today()
    totais = totais_bruto_do_dia(dia)
    corpo = montar_mensagem(template, totais=totais, dia=dia)
    return jsonify({
        'ok': True,
        'data': dia.isoformat(),
        'corpo': corpo,
        'totais': totais,
    })


@pesagem.route('/api/pesagem/whatsapp/destinos', methods=['GET', 'POST'])
@login_required
def api_whatsapp_destinos():
    if request.method == 'POST':
        payload, erros = _destino_payload()
        if erros:
            return jsonify({'ok': False, 'error': '; '.join(erros)}), 400
        dest = PesagemWhatsAppDestino(**payload)
        db.session.add(dest)
        db.session.commit()
        return jsonify({'ok': True, 'destino': dest.to_dict()})
    rows = PesagemWhatsAppDestino.query.order_by(PesagemWhatsAppDestino.nome).all()
    return jsonify({'ok': True, 'destinos': [r.to_dict() for r in rows]})


@pesagem.route('/api/pesagem/whatsapp/destinos/<int:did>', methods=['PUT', 'DELETE'])
@login_required
def api_whatsapp_destino(did):
    dest = PesagemWhatsAppDestino.query.get(did)
    if not dest:
        return jsonify({'ok': False, 'error': 'Destinatário não encontrado'}), 404
    if request.method == 'DELETE':
        PesagemWhatsAppEnvio.query.filter_by(destino_id=dest.id).delete(
            synchronize_session=False
        )
        db.session.delete(dest)
        db.session.commit()
        return jsonify({'ok': True})
    payload, erros = _destino_payload()
    if erros:
        return jsonify({'ok': False, 'error': '; '.join(erros)}), 400
    dest.nome = payload['nome']
    dest.telefone = payload['telefone']
    dest.hora = payload['hora']
    dest.mensagem = payload['mensagem']
    dest.ativo = payload['ativo']
    db.session.commit()
    return jsonify({'ok': True, 'destino': dest.to_dict()})


@pesagem.route('/api/pesagem/whatsapp/enviar/<int:did>', methods=['POST'])
@login_required
def api_whatsapp_enviar(did):
    from whatsapp_pesagem import enviar_para_destino

    dest = PesagemWhatsAppDestino.query.get(did)
    if not dest:
        return jsonify({'ok': False, 'error': 'Destinatário não encontrado'}), 404
    result = enviar_para_destino(dest, tipo='manual')
    code = 200 if result.get('ok') else 400
    return jsonify(result), code
