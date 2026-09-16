"""Rotas do Sistema de Controle de Logística."""
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, flash, jsonify, redirect, render_template, request, session, url_for,
)

from logistica_service import (
    CAMPOS_DESCONTOS,
    CAMPOS_EMPRESA,
    CAMPOS_PROVENTOS,
    CATEGORIAS_LANCAMENTO,
    FUNCOES_DP,
    STATUS_ENTREGA,
    STATUS_MANUTENCAO,
    STATUS_REVISAO,
    TIPOS_CHECKLIST,
    TIPOS_SERVICO,
    alertas_dashboard,
    custo_operacional,
    custo_por_veiculo,
    periodo_padrao,
    seed_logistica,
)
from models import Usuario, db
from models_logistica import (
    LogisticaChecklist,
    LogisticaColeta,
    LogisticaColaborador,
    LogisticaEntrega,
    LogisticaFolga,
    LogisticaFolha,
    LogisticaHigiene,
    LogisticaLancamento,
    LogisticaManutencao,
    LogisticaOciosidade,
    LogisticaRevisao,
    LogisticaRota,
    LogisticaVeiculo,
)

logistica = Blueprint('logistica', __name__, template_folder='templates_logistica')

_LOGISTICA_ENDPOINT_MENUS = {
    'logistica.dashboard': 'dashboard',
    'logistica.lancamentos_page': 'lancamentos',
    'logistica.frota_page': 'frota',
    'logistica.rotas_page': 'rotas',
    'logistica.manutencao_page': 'manutencao',
    'logistica.revisoes_page': 'revisoes',
    'logistica.entregas_page': 'entregas',
    'logistica.dp_page': 'dp',
    'logistica.folgas_page': 'folgas',
    'logistica.ociosidade_page': 'ociosidade',
    'logistica.operacao_page': 'operacao',
    'logistica.checklist_page': 'checklist',
    'logistica.higiene_page': 'higiene',
    'logistica.coletas_page': 'coletas',
    'logistica.auditoria': 'auditoria',
    'logistica.api_resumo': 'dashboard',
    'logistica.api_veiculos': 'frota',
    'logistica.api_veiculo': 'frota',
    'logistica.api_lancamentos': 'lancamentos',
    'logistica.api_lancamento': 'lancamentos',
    'logistica.api_manutencoes': 'manutencao',
    'logistica.api_manutencao': 'manutencao',
    'logistica.api_revisoes': 'revisoes',
    'logistica.api_revisao': 'revisoes',
    'logistica.api_rotas': 'rotas',
    'logistica.api_rota': 'rotas',
    'logistica.api_entregas': 'entregas',
    'logistica.api_entrega': 'entregas',
    'logistica.api_colaboradores': 'dp',
    'logistica.api_colaborador': 'dp',
    'logistica.api_folhas': 'dp',
    'logistica.api_folha': 'dp',
    'logistica.api_folgas': 'folgas',
    'logistica.api_folga': 'folgas',
    'logistica.api_ociosidade': 'ociosidade',
    'logistica.api_ociosidade_item': 'ociosidade',
    'logistica.api_checklists': 'checklist',
    'logistica.api_checklist': 'checklist',
    'logistica.api_higienes': 'higiene',
    'logistica.api_higiene': 'higiene',
    'logistica.api_coletas': 'coletas',
    'logistica.api_coleta': 'coletas',
}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated


@logistica.before_request
def _checar_permissao_menu_logistica():
    if 'user_id' not in session:
        return None
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_sistema('logistica'):
        flash('Você não tem permissão para o Sistema de Controle de Logística.', 'error')
        return redirect(url_for('main.inicio'))
    menu_key = _LOGISTICA_ENDPOINT_MENUS.get(request.endpoint)
    if not menu_key:
        return None
    if user.tem_menu('logistica', menu_key):
        return None
    if (request.path or '').startswith('/api/logistica/'):
        return jsonify({'ok': False, 'error': 'Você não tem permissão para acessar esta aba.'}), 403
    flash('Você não tem permissão para acessar esta aba.', 'error')
    return redirect(url_for('main.inicio'))


def _parse_float(value):
    if value is None or value == '':
        return None
    try:
        return float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _parse_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    if not value:
        return None
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'on', 'sim', 'yes')


def _json_body():
    return request.get_json(silent=True) or {}


def _placa_de_veiculo(veiculo_id, placa):
    placa = (placa or '').strip().upper()
    if veiculo_id:
        veiculo = LogisticaVeiculo.query.get(veiculo_id)
        if veiculo:
            return veiculo.id, veiculo.placa
    if placa:
        veiculo = LogisticaVeiculo.query.filter_by(placa=placa).first()
        if veiculo:
            return veiculo.id, veiculo.placa
        return None, placa
    return None, ''


def _page(template, active, **ctx):
    ctx.setdefault('veiculos', LogisticaVeiculo.query.order_by(LogisticaVeiculo.placa).all())
    ctx['veiculos_js'] = [v.to_dict() for v in ctx['veiculos']]
    if 'colaboradores' in ctx:
        ctx['colaboradores_js'] = [c.to_dict() for c in ctx['colaboradores']]
    ctx['active_page'] = active
    return render_template(template, **ctx)


# ---- páginas ----
@logistica.route('/logistica')
@login_required
def dashboard():
    data_de, data_ate = periodo_padrao(request.args)
    placa = (request.args.get('placa') or 'all').strip()
    resumo = custo_operacional(data_de, data_ate, None if placa == 'all' else placa)
    por_veiculo = custo_por_veiculo(data_de, data_ate, None if placa == 'all' else placa)
    alertas = alertas_dashboard()
    return _page(
        'logistica_dashboard.html',
        'dashboard',
        resumo=resumo,
        por_veiculo=por_veiculo,
        alertas=alertas,
        filtros={
            'data_de': data_de.isoformat() if data_de else '',
            'data_ate': data_ate.isoformat() if data_ate else '',
            'placa': placa,
        },
    )


@logistica.route('/logistica/lancamentos')
@login_required
def lancamentos_page():
    return _page(
        'logistica_crud.html',
        'lancamentos',
        page_title='Combustível e Pedágio',
        page_desc='Lançamentos de combustível, pedágio, pneus e demais custos da frota.',
        crud_kind='lancamentos',
        categorias=CATEGORIAS_LANCAMENTO,
    )


@logistica.route('/logistica/frota')
@login_required
def frota_page():
    return _page(
        'logistica_crud.html',
        'frota',
        page_title='Frota',
        page_desc='Cadastro de veículos, Renavam, capacidade e valores.',
        crud_kind='frota',
        categorias=(),
    )


@logistica.route('/logistica/rotas')
@login_required
def rotas_page():
    return _page(
        'logistica_crud.html',
        'rotas',
        page_title='Grade de rotas',
        page_desc='Rotas, quilometragem, motorista e ajudante.',
        crud_kind='rotas',
        categorias=(),
    )


@logistica.route('/logistica/manutencao')
@login_required
def manutencao_page():
    return _page(
        'logistica_crud.html',
        'manutencao',
        page_title='Notas e Manutenção',
        page_desc='Notas fiscais, fornecedor, responsável, parcelas e custos de manutenção.',
        crud_kind='manutencao',
        categorias=STATUS_MANUTENCAO,
        extras=TIPOS_SERVICO,
    )


@logistica.route('/logistica/revisoes')
@login_required
def revisoes_page():
    return _page(
        'logistica_crud.html',
        'revisoes',
        page_title='Revisões',
        page_desc='Agenda de revisões por km ou data.',
        crud_kind='revisoes',
        categorias=STATUS_REVISAO,
    )


@logistica.route('/logistica/entregas')
@login_required
def entregas_page():
    rotas = LogisticaRota.query.order_by(LogisticaRota.nome).all()
    return _page(
        'logistica_entregas.html',
        'entregas',
        rotas=rotas,
        rotas_js=[r.to_dict() for r in rotas],
        status_entrega=STATUS_ENTREGA,
    )


@logistica.route('/logistica/dp')
@login_required
def dp_page():
    mes = (request.args.get('mes') or datetime.utcnow().strftime('%Y-%m'))[:7]
    return _page(
        'logistica_dp.html',
        'dp',
        mes=mes,
        funcoes=FUNCOES_DP,
        campos_proventos=CAMPOS_PROVENTOS,
        campos_descontos=CAMPOS_DESCONTOS,
        campos_empresa=CAMPOS_EMPRESA,
    )


@logistica.route('/logistica/folgas')
@login_required
def folgas_page():
    mes = (request.args.get('mes') or datetime.utcnow().strftime('%Y-%m'))[:7]
    colaboradores = LogisticaColaborador.query.order_by(LogisticaColaborador.nome).all()
    return _page(
        'logistica_crud.html',
        'folgas',
        page_title='Folgas',
        page_desc='Grade de folgas do mês por colaborador e rota.',
        crud_kind='folgas',
        categorias=(),
        mes=mes,
        colaboradores=colaboradores,
    )


@logistica.route('/logistica/ociosidade')
@login_required
def ociosidade_page():
    return _page(
        'logistica_crud.html',
        'ociosidade',
        page_title='Ociosidade',
        page_desc='Horas paradas da frota e custo associado.',
        crud_kind='ociosidade',
        categorias=(),
    )


@logistica.route('/logistica/operacao')
@login_required
def operacao_page():
    return _page(
        'logistica_operacao.html',
        'operacao',
    )


@logistica.route('/logistica/checklist')
@login_required
def checklist_page():
    return _page(
        'logistica_crud.html',
        'checklist',
        page_title='Check-list',
        page_desc='Conferência de saída e retorno da frota.',
        crud_kind='checklist',
        categorias=TIPOS_CHECKLIST,
    )


@logistica.route('/logistica/higiene')
@login_required
def higiene_page():
    return _page(
        'logistica_crud.html',
        'higiene',
        page_title='Higiene',
        page_desc='Registros de higienização da frota.',
        crud_kind='higiene',
        categorias=(),
    )


@logistica.route('/logistica/coletas')
@login_required
def coletas_page():
    return _page(
        'logistica_crud.html',
        'coletas',
        page_title='Controle de peso',
        page_desc='Peso sujo coletado, peso limpo entregue, gaiolas e valor por quilo.',
        crud_kind='coletas',
        categorias=(),
    )


@logistica.route('/logistica/auditoria')
@login_required
def auditoria():
    from datetime import date, timedelta
    from audit_service import listar_logs, ensure_audit_table
    from nutricao_service import _parse_date as parse_nut

    ensure_audit_table()
    hoje = date.today()
    data_de = parse_nut(request.args.get('data_de')) or (hoje - timedelta(days=7))
    data_ate = parse_nut(request.args.get('data_ate')) or hoje
    if 'modulo' in request.args:
        modulo = (request.args.get('modulo') or '').strip() or None
    else:
        modulo = 'logistica'
    usuario = (request.args.get('usuario') or '').strip() or None
    acao = (request.args.get('acao') or '').strip() or None
    q = (request.args.get('q') or '').strip() or None
    try:
        limit = min(int(request.args.get('limit') or 200), 500)
    except (TypeError, ValueError):
        limit = 200
    total, logs = listar_logs(
        modulo=modulo, usuario=usuario, acao=acao, q=q,
        data_de=data_de, data_ate=data_ate, limit=limit, offset=0,
    )
    return render_template(
        'logistica_auditoria.html',
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
        active_page='auditoria',
    )


# ---- APIs ----
@logistica.route('/api/logistica/resumo')
@login_required
def api_resumo():
    data_de, data_ate = periodo_padrao(request.args)
    placa = (request.args.get('placa') or 'all').strip()
    return jsonify({
        'ok': True,
        'resumo': custo_operacional(data_de, data_ate, None if placa == 'all' else placa),
        'por_veiculo': custo_por_veiculo(data_de, data_ate, None if placa == 'all' else placa),
    })


def _lista_veiculos():
    return [v.to_dict() for v in LogisticaVeiculo.query.order_by(LogisticaVeiculo.placa).all()]


@logistica.route('/api/logistica/veiculos', methods=['GET', 'POST'])
@login_required
def api_veiculos():
    if request.method == 'GET':
        return jsonify({'ok': True, 'rows': _lista_veiculos()})
    d = _json_body()
    placa = (d.get('placa') or '').strip().upper()
    modelo = (d.get('modelo') or '').strip()
    if not placa or not modelo:
        return jsonify({'ok': False, 'error': 'Informe placa e modelo.'}), 400
    if LogisticaVeiculo.query.filter_by(placa=placa).first():
        return jsonify({'ok': False, 'error': 'Já existe veículo com esta placa.'}), 400
    item = LogisticaVeiculo(
        placa=placa,
        renavam=(d.get('renavam') or '').strip()[:20] or None,
        modelo=modelo[:120],
        ano=(d.get('ano') or '').strip()[:20] or None,
        capacidade=(d.get('capacidade') or '').strip()[:40] or None,
        valor_veiculo=_parse_float(d.get('valor_veiculo')),
        valor_carroceria=_parse_float(d.get('valor_carroceria')),
        valor_plataforma=_parse_float(d.get('valor_plataforma')),
        gaiolas=_parse_int(d.get('gaiolas')),
        unidade=(d.get('unidade') or '').strip()[:80] or None,
        observacao=(d.get('observacao') or '').strip()[:255] or None,
        ativo=_parse_bool(d.get('ativo'), True),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/veiculos/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_veiculo(item_id):
    item = LogisticaVeiculo.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    placa = (d.get('placa') or item.placa).strip().upper()
    outro = LogisticaVeiculo.query.filter(
        LogisticaVeiculo.placa == placa, LogisticaVeiculo.id != item.id
    ).first()
    if outro:
        return jsonify({'ok': False, 'error': 'Já existe veículo com esta placa.'}), 400
    item.placa = placa
    item.renavam = (d.get('renavam') or '').strip()[:20] or None
    item.modelo = (d.get('modelo') or item.modelo).strip()[:120]
    item.ano = (d.get('ano') or '').strip()[:20] or None
    item.capacidade = (d.get('capacidade') or '').strip()[:40] or None
    item.valor_veiculo = _parse_float(d.get('valor_veiculo'))
    item.valor_carroceria = _parse_float(d.get('valor_carroceria'))
    item.valor_plataforma = _parse_float(d.get('valor_plataforma'))
    item.gaiolas = _parse_int(d.get('gaiolas'))
    item.unidade = (d.get('unidade') or '').strip()[:80] or None
    item.observacao = (d.get('observacao') or '').strip()[:255] or None
    if 'ativo' in d:
        item.ativo = _parse_bool(d.get('ativo'), True)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/lancamentos', methods=['GET', 'POST'])
@login_required
def api_lancamentos():
    if request.method == 'GET':
        q = LogisticaLancamento.query.order_by(LogisticaLancamento.data.desc(), LogisticaLancamento.id.desc())
        placa = (request.args.get('placa') or '').strip()
        categoria = (request.args.get('categoria') or '').strip()
        if placa:
            q = q.filter(LogisticaLancamento.placa == placa)
        if categoria:
            q = q.filter(LogisticaLancamento.categoria == categoria)
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.limit(1000).all()]})
    d = _json_body()
    data = _parse_date(d.get('data'))
    if not data:
        return jsonify({'ok': False, 'error': 'Informe a data.'}), 400
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa'))
    categoria = (d.get('categoria') or 'Outros').strip()
    if categoria == 'Abastecimento':
        categoria = 'Combustível'
    if categoria not in CATEGORIAS_LANCAMENTO:
        categoria = 'Outros'
    item = LogisticaLancamento(
        data=data,
        veiculo_id=veiculo_id,
        placa=placa,
        categoria=categoria,
        descricao=(d.get('descricao') or '').strip()[:255] or None,
        valor=_parse_float(d.get('valor')) or 0,
        km=_parse_float(d.get('km')),
        litros=_parse_float(d.get('litros')),
        posto=(d.get('posto') or '').strip()[:120] or None,
        observacao=(d.get('observacao') or '').strip()[:255] or None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/lancamentos/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_lancamento(item_id):
    item = LogisticaLancamento.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    if d.get('data'):
        item.data = _parse_date(d.get('data')) or item.data
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa') or item.placa)
    item.veiculo_id = veiculo_id
    item.placa = placa
    if d.get('categoria'):
        cat = d.get('categoria').strip()
        item.categoria = cat if cat in CATEGORIAS_LANCAMENTO else item.categoria
    item.descricao = (d.get('descricao') or '').strip()[:255] or None
    if 'valor' in d:
        item.valor = _parse_float(d.get('valor')) or 0
    item.km = _parse_float(d.get('km')) if 'km' in d else item.km
    item.litros = _parse_float(d.get('litros')) if 'litros' in d else item.litros
    item.posto = (d.get('posto') or '').strip()[:120] or None
    item.observacao = (d.get('observacao') or '').strip()[:255] or None
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/manutencoes', methods=['GET', 'POST'])
@login_required
def api_manutencoes():
    if request.method == 'GET':
        q = LogisticaManutencao.query.order_by(LogisticaManutencao.data.desc(), LogisticaManutencao.id.desc())
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.limit(1000).all()]})
    d = _json_body()
    data = _parse_date(d.get('data'))
    descricao = (d.get('descricao') or '').strip()
    if not data or not descricao:
        return jsonify({'ok': False, 'error': 'Informe data e descrição.'}), 400
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa'))
    item = LogisticaManutencao(
        data=data,
        veiculo_id=veiculo_id,
        placa=placa,
        categoria=(d.get('categoria') or '').strip()[:80] or None,
        tipo_servico=(d.get('tipo_servico') or '').strip()[:80] or None,
        responsavel=(d.get('responsavel') or '').strip()[:120] or None,
        fornecedor=(d.get('fornecedor') or '').strip()[:160] or None,
        nf=(d.get('nf') or '').strip()[:80] or None,
        descricao=descricao[:255],
        valor=_parse_float(d.get('valor')) or 0,
        parcelas=_parse_int(d.get('parcelas')) or 1,
        parcelas_pagas=_parse_int(d.get('parcelas_pagas')) or 0,
        vencimento=_parse_date(d.get('vencimento')),
        status=(d.get('status') or 'Aberto').strip()[:40],
        observacao=(d.get('observacao') or '').strip()[:255] or None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/manutencoes/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_manutencao(item_id):
    item = LogisticaManutencao.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    if d.get('data'):
        item.data = _parse_date(d.get('data')) or item.data
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa') or item.placa)
    item.veiculo_id = veiculo_id
    item.placa = placa
    item.categoria = (d.get('categoria') or '').strip()[:80] or None
    item.tipo_servico = (d.get('tipo_servico') or '').strip()[:80] or None
    item.responsavel = (d.get('responsavel') or '').strip()[:120] or None
    item.fornecedor = (d.get('fornecedor') or '').strip()[:160] or None
    item.nf = (d.get('nf') or '').strip()[:80] or None
    item.descricao = (d.get('descricao') or item.descricao).strip()[:255]
    if 'valor' in d:
        item.valor = _parse_float(d.get('valor')) or 0
    if 'parcelas' in d:
        item.parcelas = _parse_int(d.get('parcelas')) or 1
    if 'parcelas_pagas' in d:
        item.parcelas_pagas = _parse_int(d.get('parcelas_pagas')) or 0
    if 'vencimento' in d:
        item.vencimento = _parse_date(d.get('vencimento'))
    item.status = (d.get('status') or item.status or 'Aberto')[:40]
    item.observacao = (d.get('observacao') or '').strip()[:255] or None
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/revisoes', methods=['GET', 'POST'])
@login_required
def api_revisoes():
    if request.method == 'GET':
        q = LogisticaRevisao.query.order_by(LogisticaRevisao.id.desc())
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.limit(1000).all()]})
    d = _json_body()
    tipo = (d.get('tipo') or '').strip()
    if not tipo:
        return jsonify({'ok': False, 'error': 'Informe o tipo da revisão.'}), 400
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa'))
    item = LogisticaRevisao(
        veiculo_id=veiculo_id,
        placa=placa,
        tipo=tipo[:80],
        km_previsto=_parse_float(d.get('km_previsto')),
        data_prevista=_parse_date(d.get('data_prevista')),
        km_realizado=_parse_float(d.get('km_realizado')),
        data_realizado=_parse_date(d.get('data_realizado')),
        status=(d.get('status') or 'Pendente').strip()[:40],
        observacao=(d.get('observacao') or '').strip()[:255] or None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/revisoes/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_revisao(item_id):
    item = LogisticaRevisao.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa') or item.placa)
    item.veiculo_id = veiculo_id
    item.placa = placa
    item.tipo = (d.get('tipo') or item.tipo)[:80]
    item.km_previsto = _parse_float(d.get('km_previsto')) if 'km_previsto' in d else item.km_previsto
    item.data_prevista = _parse_date(d.get('data_prevista')) if 'data_prevista' in d else item.data_prevista
    item.km_realizado = _parse_float(d.get('km_realizado')) if 'km_realizado' in d else item.km_realizado
    item.data_realizado = _parse_date(d.get('data_realizado')) if 'data_realizado' in d else item.data_realizado
    item.status = (d.get('status') or item.status or 'Pendente')[:40]
    item.observacao = (d.get('observacao') or '').strip()[:255] or None
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/rotas', methods=['GET', 'POST'])
@login_required
def api_rotas():
    if request.method == 'GET':
        q = LogisticaRota.query.order_by(LogisticaRota.nome)
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.all()]})
    d = _json_body()
    nome = (d.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome da rota.'}), 400
    item = LogisticaRota(
        nome=nome[:120],
        setor=(d.get('setor') or '').strip()[:80] or None,
        origem=(d.get('origem') or '').strip()[:120] or None,
        destino=(d.get('destino') or '').strip()[:120] or None,
        km=_parse_float(d.get('km')),
        placa_padrao=(d.get('placa_padrao') or '').strip().upper()[:12] or None,
        motorista=(d.get('motorista') or '').strip()[:120] or None,
        ajudante=(d.get('ajudante') or '').strip()[:120] or None,
        ativa=_parse_bool(d.get('ativa'), True),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/rotas/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_rota(item_id):
    item = LogisticaRota.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    item.nome = (d.get('nome') or item.nome).strip()[:120]
    item.setor = (d.get('setor') or '').strip()[:80] or None
    item.origem = (d.get('origem') or '').strip()[:120] or None
    item.destino = (d.get('destino') or '').strip()[:120] or None
    if 'km' in d:
        item.km = _parse_float(d.get('km'))
    item.placa_padrao = (d.get('placa_padrao') or '').strip().upper()[:12] or None
    item.motorista = (d.get('motorista') or '').strip()[:120] or None
    item.ajudante = (d.get('ajudante') or '').strip()[:120] or None
    if 'ativa' in d:
        item.ativa = _parse_bool(d.get('ativa'), True)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/entregas', methods=['GET', 'POST'])
@login_required
def api_entregas():
    if request.method == 'GET':
        q = LogisticaEntrega.query.order_by(LogisticaEntrega.nome)
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.all()]})
    d = _json_body()
    nome = (d.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o ponto de entrega.'}), 400
    item = LogisticaEntrega(
        rota_id=_parse_int(d.get('rota_id')),
        nome=nome[:160],
        endereco=(d.get('endereco') or '').strip()[:255] or None,
        lat=_parse_float(d.get('lat')),
        lng=_parse_float(d.get('lng')),
        status=(d.get('status') or 'Pendente').strip()[:40],
        observacao=(d.get('observacao') or '').strip()[:255] or None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/entregas/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_entrega(item_id):
    item = LogisticaEntrega.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    if 'rota_id' in d:
        item.rota_id = _parse_int(d.get('rota_id'))
    item.nome = (d.get('nome') or item.nome).strip()[:160]
    item.endereco = (d.get('endereco') or '').strip()[:255] or None
    if 'lat' in d:
        item.lat = _parse_float(d.get('lat'))
    if 'lng' in d:
        item.lng = _parse_float(d.get('lng'))
    item.status = (d.get('status') or item.status or 'Pendente')[:40]
    item.observacao = (d.get('observacao') or '').strip()[:255] or None
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/colaboradores', methods=['GET', 'POST'])
@login_required
def api_colaboradores():
    if request.method == 'GET':
        q = LogisticaColaborador.query.order_by(LogisticaColaborador.nome)
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.all()]})
    d = _json_body()
    nome = (d.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome.'}), 400
    item = LogisticaColaborador(
        nome=nome[:120],
        funcao=(d.get('funcao') or '').strip()[:80] or None,
        setor=(d.get('setor') or '').strip()[:80] or None,
        ativo=_parse_bool(d.get('ativo'), True),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/colaboradores/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_colaborador(item_id):
    item = LogisticaColaborador.query.get_or_404(item_id)
    if request.method == 'DELETE':
        LogisticaFolha.query.filter_by(colaborador_id=item.id).delete()
        LogisticaFolga.query.filter_by(colaborador_id=item.id).delete()
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    item.nome = (d.get('nome') or item.nome).strip()[:120]
    item.funcao = (d.get('funcao') or '').strip()[:80] or None
    item.setor = (d.get('setor') or '').strip()[:80] or None
    if 'ativo' in d:
        item.ativo = _parse_bool(d.get('ativo'), True)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/folhas', methods=['GET', 'POST'])
@login_required
def api_folhas():
    mes = (request.args.get('mes') or (_json_body().get('mes') if request.method == 'POST' else '') or datetime.utcnow().strftime('%Y-%m'))[:7]
    if request.method == 'GET':
        rows = []
        for colab in LogisticaColaborador.query.order_by(LogisticaColaborador.nome).all():
            folha = LogisticaFolha.query.filter_by(colaborador_id=colab.id, mes=mes).first()
            if folha:
                rows.append(folha.to_dict())
            else:
                rows.append({
                    'id': None,
                    'colaborador_id': colab.id,
                    'colaborador': colab.nome,
                    'funcao': colab.funcao or '',
                    'setor': colab.setor or '',
                    'mes': mes,
                    'proventos': 0, 'descontos': 0, 'liquido': 0, 'custo_empresa': 0,
                    **{campo: 0 for campo, _ in CAMPOS_PROVENTOS + CAMPOS_DESCONTOS + CAMPOS_EMPRESA},
                })
        return jsonify({'ok': True, 'rows': rows, 'mes': mes})
    d = _json_body()
    colab_id = _parse_int(d.get('colaborador_id'))
    mes = (d.get('mes') or mes)[:7]
    if not colab_id:
        return jsonify({'ok': False, 'error': 'Informe o colaborador.'}), 400
    folha = LogisticaFolha.query.filter_by(colaborador_id=colab_id, mes=mes).first()
    if not folha:
        folha = LogisticaFolha(colaborador_id=colab_id, mes=mes)
        db.session.add(folha)
    for campo, _label in CAMPOS_PROVENTOS + CAMPOS_DESCONTOS + CAMPOS_EMPRESA:
        if campo in d:
            setattr(folha, campo, _parse_float(d.get(campo)) or 0)
    db.session.commit()
    return jsonify({'ok': True, 'row': folha.to_dict()})


@logistica.route('/api/logistica/folhas/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_folha(item_id):
    item = LogisticaFolha.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    for campo, _label in CAMPOS_PROVENTOS + CAMPOS_DESCONTOS + CAMPOS_EMPRESA:
        if campo in d:
            setattr(item, campo, _parse_float(d.get(campo)) or 0)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/folgas', methods=['GET', 'POST'])
@login_required
def api_folgas():
    mes = (request.args.get('mes') or datetime.utcnow().strftime('%Y-%m'))[:7]
    if request.method == 'GET':
        q = LogisticaFolga.query.filter_by(mes=mes)
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.all()], 'mes': mes})
    d = _json_body()
    colab_id = _parse_int(d.get('colaborador_id'))
    mes = (d.get('mes') or mes)[:7]
    if not colab_id:
        return jsonify({'ok': False, 'error': 'Informe o colaborador.'}), 400
    dias = d.get('dias')
    if isinstance(dias, list):
        dias_texto = ','.join(str(int(x)) for x in dias if str(x).strip().isdigit())
    else:
        dias_texto = ','.join(
            p.strip() for p in str(dias or d.get('dias_texto') or '').split(',') if p.strip().isdigit()
        )
    item = LogisticaFolga.query.filter_by(colaborador_id=colab_id, mes=mes).first()
    if not item:
        item = LogisticaFolga(colaborador_id=colab_id, mes=mes)
        db.session.add(item)
    item.setor = (d.get('setor') or '').strip()[:80] or None
    item.rota = (d.get('rota') or '').strip()[:120] or None
    item.dias = dias_texto
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/folgas/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_folga(item_id):
    item = LogisticaFolga.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    item.setor = (d.get('setor') or '').strip()[:80] or None
    item.rota = (d.get('rota') or '').strip()[:120] or None
    if 'dias' in d or 'dias_texto' in d:
        dias = d.get('dias')
        if isinstance(dias, list):
            item.dias = ','.join(str(int(x)) for x in dias if str(x).strip().isdigit())
        else:
            item.dias = ','.join(
                p.strip() for p in str(dias or d.get('dias_texto') or '').split(',') if p.strip().isdigit()
            )
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/ociosidade', methods=['GET', 'POST'])
@login_required
def api_ociosidade():
    if request.method == 'GET':
        q = LogisticaOciosidade.query.order_by(LogisticaOciosidade.data.desc())
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.limit(1000).all()]})
    d = _json_body()
    data = _parse_date(d.get('data'))
    if not data:
        return jsonify({'ok': False, 'error': 'Informe a data.'}), 400
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa'))
    item = LogisticaOciosidade(
        data=data,
        veiculo_id=veiculo_id,
        placa=placa,
        horas=_parse_float(d.get('horas')) or 0,
        motivo=(d.get('motivo') or '').strip()[:255] or None,
        valor=_parse_float(d.get('valor')) or 0,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/ociosidade/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_ociosidade_item(item_id):
    item = LogisticaOciosidade.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    if d.get('data'):
        item.data = _parse_date(d.get('data')) or item.data
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa') or item.placa)
    item.veiculo_id = veiculo_id
    item.placa = placa
    if 'horas' in d:
        item.horas = _parse_float(d.get('horas')) or 0
    item.motivo = (d.get('motivo') or '').strip()[:255] or None
    if 'valor' in d:
        item.valor = _parse_float(d.get('valor')) or 0
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/checklists', methods=['GET', 'POST'])
@login_required
def api_checklists():
    if request.method == 'GET':
        q = LogisticaChecklist.query.order_by(LogisticaChecklist.data.desc())
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.limit(1000).all()]})
    d = _json_body()
    data = _parse_date(d.get('data'))
    if not data:
        return jsonify({'ok': False, 'error': 'Informe a data.'}), 400
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa'))
    item = LogisticaChecklist(
        data=data,
        veiculo_id=veiculo_id,
        placa=placa,
        rota=(d.get('rota') or '').strip()[:120] or None,
        motorista=(d.get('motorista') or '').strip()[:120] or None,
        tipo=(d.get('tipo') or 'Saída').strip()[:20],
        itens=(d.get('itens') or '').strip()[:255] or None,
        observacao=(d.get('observacao') or '').strip()[:255] or None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/checklists/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_checklist(item_id):
    item = LogisticaChecklist.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    if d.get('data'):
        item.data = _parse_date(d.get('data')) or item.data
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa') or item.placa)
    item.veiculo_id = veiculo_id
    item.placa = placa
    item.rota = (d.get('rota') or '').strip()[:120] or None
    item.motorista = (d.get('motorista') or '').strip()[:120] or None
    item.tipo = (d.get('tipo') or item.tipo or 'Saída')[:20]
    item.itens = (d.get('itens') or '').strip()[:255] or None
    item.observacao = (d.get('observacao') or '').strip()[:255] or None
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/higiene', methods=['GET', 'POST'])
@login_required
def api_higienes():
    if request.method == 'GET':
        q = LogisticaHigiene.query.order_by(LogisticaHigiene.data.desc())
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.limit(1000).all()]})
    d = _json_body()
    data = _parse_date(d.get('data'))
    if not data:
        return jsonify({'ok': False, 'error': 'Informe a data.'}), 400
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa'))
    item = LogisticaHigiene(
        data=data,
        veiculo_id=veiculo_id,
        placa=placa,
        tipo=(d.get('tipo') or '').strip()[:80] or None,
        responsavel=(d.get('responsavel') or '').strip()[:120] or None,
        observacao=(d.get('observacao') or '').strip()[:255] or None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/higiene/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_higiene(item_id):
    item = LogisticaHigiene.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    if d.get('data'):
        item.data = _parse_date(d.get('data')) or item.data
    veiculo_id, placa = _placa_de_veiculo(d.get('veiculo_id'), d.get('placa') or item.placa)
    item.veiculo_id = veiculo_id
    item.placa = placa
    item.tipo = (d.get('tipo') or '').strip()[:80] or None
    item.responsavel = (d.get('responsavel') or '').strip()[:120] or None
    item.observacao = (d.get('observacao') or '').strip()[:255] or None
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/coletas', methods=['GET', 'POST'])
@login_required
def api_coletas():
    if request.method == 'GET':
        q = LogisticaColeta.query.order_by(LogisticaColeta.data.desc())
        return jsonify({'ok': True, 'rows': [r.to_dict() for r in q.limit(1000).all()]})
    d = _json_body()
    data = _parse_date(d.get('data'))
    if not data:
        return jsonify({'ok': False, 'error': 'Informe a data.'}), 400
    sujo = _parse_float(d.get('peso_sujo')) or 0
    limpo = _parse_float(d.get('peso_limpo')) or 0
    item = LogisticaColeta(
        data=data,
        cliente=(d.get('cliente') or '').strip()[:160] or None,
        rota=(d.get('rota') or '').strip()[:120] or None,
        peso_sujo=sujo,
        peso_limpo=limpo,
        gaiolas=_parse_int(d.get('gaiolas')) or 0,
        valor_kg=_parse_float(d.get('valor_kg')) or 0,
        observacao=(d.get('observacao') or '').strip()[:255] or None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})


@logistica.route('/api/logistica/coletas/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def api_coleta(item_id):
    item = LogisticaColeta.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True})
    d = _json_body()
    if d.get('data'):
        item.data = _parse_date(d.get('data')) or item.data
    item.cliente = (d.get('cliente') or '').strip()[:160] or None
    item.rota = (d.get('rota') or '').strip()[:120] or None
    if 'peso_sujo' in d:
        item.peso_sujo = _parse_float(d.get('peso_sujo')) or 0
    if 'peso_limpo' in d:
        item.peso_limpo = _parse_float(d.get('peso_limpo')) or 0
    if 'gaiolas' in d:
        item.gaiolas = _parse_int(d.get('gaiolas')) or 0
    if 'valor_kg' in d:
        item.valor_kg = _parse_float(d.get('valor_kg')) or 0
    item.observacao = (d.get('observacao') or '').strip()[:255] or None
    db.session.commit()
    return jsonify({'ok': True, 'row': item.to_dict()})
