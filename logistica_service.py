"""Regras de cálculo do Sistema de Controle de Logística."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

from models_logistica import (
    LogisticaLancamento,
    LogisticaManutencao,
    LogisticaOciosidade,
    LogisticaRota,
    LogisticaVeiculo,
)

CATEGORIAS_LANCAMENTO = ('Combustível', 'Pedágio', 'Pneus', 'Outros')
TIPOS_SERVICO = ('Manutenção do veículo', 'Plataforma', 'Lavagem', 'Revisão')
STATUS_MANUTENCAO = ('Aberto', 'Em andamento', 'Concluído', 'Cancelado')
STATUS_REVISAO = ('Pendente', 'Agendada', 'Realizada', 'Atrasada')
STATUS_ENTREGA = ('Pendente', 'Em rota', 'Entregue', 'Falhou')
FUNCOES_DP = ('Motorista', 'Ajudante', 'Encarregado', 'Administrativo')
TIPOS_CHECKLIST = ('Saída', 'Retorno')

CAMPOS_PROVENTOS = (
    ('salario', 'Salário-base'),
    ('insalubridade', 'Insalubridade'),
    ('noturno', 'Adicional noturno'),
    ('hora_extra_100', 'Hora extra 100%'),
    ('hora_extra_50', 'Hora extra 50%'),
    ('hora_extra', 'Hora extra (legado)'),
    ('repouso', 'Repouso remunerado'),
    ('feriado', 'Feriado'),
    ('adicional', 'Adicional'),
)
CAMPOS_DESCONTOS = (
    ('alimentacao', 'Alimentação'),
    ('refeicao', 'Refeição'),
    ('vale_transporte', 'Vale-transporte'),
    ('faltas', 'Faltas / atrasos'),
    ('pensao', 'Pensão alimentícia'),
    ('vale', 'Vale'),
    ('emprestimo', 'Empréstimo'),
    ('inss', 'INSS'),
)
CAMPOS_EMPRESA = (
    ('beneficios', 'Benefícios da empresa'),
    ('encargos', 'Encargos da empresa'),
    ('outros_empresa', 'Outros custos da empresa'),
)


def totais_folha(folha):
    proventos = sum(float(getattr(folha, campo, 0) or 0) for campo, _ in CAMPOS_PROVENTOS)
    descontos = sum(float(getattr(folha, campo, 0) or 0) for campo, _ in CAMPOS_DESCONTOS)
    empresa = sum(float(getattr(folha, campo, 0) or 0) for campo, _ in CAMPOS_EMPRESA)
    return {
        'proventos': round(proventos, 2),
        'descontos': round(descontos, 2),
        'liquido': round(proventos - descontos, 2),
        'custo_empresa': round(proventos + empresa, 2),
    }


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return None


def periodo_padrao(args):
    hoje = date.today()
    tem_param = any(k in args for k in ('data_de', 'data_ate', 'placa'))
    data_de = _parse_date(args.get('data_de'))
    data_ate = _parse_date(args.get('data_ate'))
    if not tem_param:
        data_de = hoje.replace(day=1)
        data_ate = hoje
    if data_de and data_ate and data_de > data_ate:
        data_de, data_ate = data_ate, data_de
    return data_de, data_ate


def custo_operacional(data_de=None, data_ate=None, placa=None):
    """Totais de custo, km e custo/km no período (fórmula do painel original)."""
    lanc_q = LogisticaLancamento.query
    man_q = LogisticaManutencao.query
    oci_q = LogisticaOciosidade.query
    if data_de:
        lanc_q = lanc_q.filter(LogisticaLancamento.data >= data_de)
        man_q = man_q.filter(LogisticaManutencao.data >= data_de)
        oci_q = oci_q.filter(LogisticaOciosidade.data >= data_de)
    if data_ate:
        lanc_q = lanc_q.filter(LogisticaLancamento.data <= data_ate)
        man_q = man_q.filter(LogisticaManutencao.data <= data_ate)
        oci_q = oci_q.filter(LogisticaOciosidade.data <= data_ate)
    if placa and placa != 'all':
        lanc_q = lanc_q.filter(LogisticaLancamento.placa == placa)
        man_q = man_q.filter(LogisticaManutencao.placa == placa)
        oci_q = oci_q.filter(LogisticaOciosidade.placa == placa)

    por_cat = defaultdict(float)
    km_total = 0.0
    litros_total = 0.0
    for row in lanc_q.all():
        por_cat[row.categoria or 'Outros'] += float(row.valor or 0)
        if row.km:
            km_total += float(row.km)
        if row.litros:
            litros_total += float(row.litros)

    manutencao = sum(float(r.valor or 0) for r in man_q.all())
    ociosidade = sum(float(r.valor or 0) for r in oci_q.all())
    horas_ociosas = sum(float(r.horas or 0) for r in oci_q.all())
    abastecimento = por_cat.get('Combustível', 0.0) + por_cat.get('Abastecimento', 0.0)
    pedagio = por_cat.get('Pedágio', 0.0)
    outros = por_cat.get('Outros', 0.0) + por_cat.get('Pneus', 0.0)
    total = abastecimento + pedagio + outros + manutencao + ociosidade
    custo_km = (total / km_total) if km_total else 0.0
    media_litro = (abastecimento / litros_total) if litros_total else 0.0

    return {
        'abastecimento': round(abastecimento, 2),
        'pedagio': round(pedagio, 2),
        'manutencao': round(manutencao, 2),
        'outros': round(outros, 2),
        'ociosidade': round(ociosidade, 2),
        'horas_ociosas': round(horas_ociosas, 2),
        'total': round(total, 2),
        'km': round(km_total, 1),
        'custo_km': round(custo_km, 4),
        'litros': round(litros_total, 1),
        'media_litro': round(media_litro, 3),
        'veiculos': LogisticaVeiculo.query.filter_by(ativo=True).count(),
        'rotas': LogisticaRota.query.filter_by(ativa=True).count(),
    }


def _chave_categoria(categoria):
    cat = categoria or 'Outros'
    if cat in ('Combustível', 'Abastecimento'):
        return 'abastecimento'
    if cat == 'Pedágio':
        return 'pedagio'
    return 'outros'


def _eixos_periodo(data_de, data_ate):
    """Lista de (chave, rótulo) cobrindo o intervalo filtrado."""
    if not data_de or not data_ate:
        return [], 'dia'
    span = (data_ate - data_de).days
    eixos = []
    if span <= 45:
        atual = data_de
        while atual <= data_ate:
            eixos.append((atual.isoformat(), atual.strftime('%d/%m')))
            atual += timedelta(days=1)
        return eixos, 'dia'
    if span <= 180:
        visto = set()
        atual = data_de
        while atual <= data_ate:
            inicio = atual - timedelta(days=atual.weekday())
            chave = inicio.isoformat()
            if chave not in visto:
                visto.add(chave)
                eixos.append((chave, inicio.strftime('%d/%m')))
            atual += timedelta(days=1)
        return eixos, 'semana'
    atual = data_de.replace(day=1)
    while atual <= data_ate:
        meses = ('jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez')
        eixos.append((atual.strftime('%Y-%m'), f'{meses[atual.month - 1]}/{atual.year % 100:02d}'))
        if atual.month == 12:
            atual = atual.replace(year=atual.year + 1, month=1)
        else:
            atual = atual.replace(month=atual.month + 1)
    return eixos, 'mes'


def _bucket_data(valor, granularidade):
    if not valor:
        return None
    if granularidade == 'dia':
        return valor.isoformat()
    if granularidade == 'semana':
        inicio = valor - timedelta(days=valor.weekday())
        return inicio.isoformat()
    return valor.strftime('%Y-%m')


def evolucao_custos(data_de=None, data_ate=None, placa=None):
    """Série temporal e composição dos custos respeitando o filtro da tela."""
    series_keys = ('abastecimento', 'pedagio', 'manutencao', 'ociosidade', 'outros')
    vazio = {
        'labels': [],
        'abastecimento': [],
        'pedagio': [],
        'manutencao': [],
        'ociosidade': [],
        'outros': [],
        'composicao': [
            {'chave': 'abastecimento', 'label': 'Abastecimento', 'cor': '#3b82f6', 'valor': 0.0, 'pct': 0.0},
            {'chave': 'pedagio', 'label': 'Pedágio', 'cor': '#eab308', 'valor': 0.0, 'pct': 0.0},
            {'chave': 'manutencao', 'label': 'Manutenção', 'cor': '#22c55e', 'valor': 0.0, 'pct': 0.0},
            {'chave': 'ociosidade', 'label': 'Ociosidade', 'cor': '#f97316', 'valor': 0.0, 'pct': 0.0},
            {'chave': 'outros', 'label': 'Outros', 'cor': '#a855f7', 'valor': 0.0, 'pct': 0.0},
        ],
        'maior_pct': 0.0,
        'maior_label': '',
        'total': 0.0,
    }

    lanc_q = LogisticaLancamento.query
    man_q = LogisticaManutencao.query
    oci_q = LogisticaOciosidade.query
    if data_de:
        lanc_q = lanc_q.filter(LogisticaLancamento.data >= data_de)
        man_q = man_q.filter(LogisticaManutencao.data >= data_de)
        oci_q = oci_q.filter(LogisticaOciosidade.data >= data_de)
    if data_ate:
        lanc_q = lanc_q.filter(LogisticaLancamento.data <= data_ate)
        man_q = man_q.filter(LogisticaManutencao.data <= data_ate)
        oci_q = oci_q.filter(LogisticaOciosidade.data <= data_ate)
    if placa and placa != 'all':
        lanc_q = lanc_q.filter(LogisticaLancamento.placa == placa)
        man_q = man_q.filter(LogisticaManutencao.placa == placa)
        oci_q = oci_q.filter(LogisticaOciosidade.placa == placa)

    lancamentos = lanc_q.all()
    manutencoes = man_q.all()
    ociosidades = oci_q.all()

    if not data_de or not data_ate:
        datas = [r.data for r in (*lancamentos, *manutencoes, *ociosidades) if r.data]
        if not datas:
            return vazio
        data_de = data_de or min(datas)
        data_ate = data_ate or max(datas)
        if data_de > data_ate:
            data_de, data_ate = data_ate, data_de

    eixos, granularidade = _eixos_periodo(data_de, data_ate)
    if not eixos:
        return vazio

    acumulado = {chave: defaultdict(float) for chave in series_keys}
    for row in lancamentos:
        bucket = _bucket_data(row.data, granularidade)
        if not bucket:
            continue
        acumulado[_chave_categoria(row.categoria)][bucket] += float(row.valor or 0)
    for row in manutencoes:
        bucket = _bucket_data(row.data, granularidade)
        if bucket:
            acumulado['manutencao'][bucket] += float(row.valor or 0)
    for row in ociosidades:
        bucket = _bucket_data(row.data, granularidade)
        if bucket:
            acumulado['ociosidade'][bucket] += float(row.valor or 0)

    labels = [rotulo for _, rotulo in eixos]
    saida = {
        'labels': labels,
        'abastecimento': [round(acumulado['abastecimento'][chave], 2) for chave, _ in eixos],
        'pedagio': [round(acumulado['pedagio'][chave], 2) for chave, _ in eixos],
        'manutencao': [round(acumulado['manutencao'][chave], 2) for chave, _ in eixos],
        'ociosidade': [round(acumulado['ociosidade'][chave], 2) for chave, _ in eixos],
        'outros': [round(acumulado['outros'][chave], 2) for chave, _ in eixos],
    }

    cores = {
        'abastecimento': '#3b82f6',
        'pedagio': '#eab308',
        'manutencao': '#22c55e',
        'ociosidade': '#f97316',
        'outros': '#a855f7',
    }
    nomes = {
        'abastecimento': 'Abastecimento',
        'pedagio': 'Pedágio',
        'manutencao': 'Manutenção',
        'ociosidade': 'Ociosidade',
        'outros': 'Outros',
    }
    composicao = []
    for chave in series_keys:
        valor = round(sum(saida[chave]), 2)
        composicao.append({
            'chave': chave,
            'label': nomes[chave],
            'cor': cores[chave],
            'valor': valor,
            'pct': 0.0,
        })
    total = round(sum(item['valor'] for item in composicao), 2)
    maior_pct = 0.0
    maior_label = ''
    if total:
        for item in composicao:
            item['pct'] = round((item['valor'] / total) * 100, 1)
        maior = max(composicao, key=lambda item: item['valor'])
        maior_pct = maior['pct']
        maior_label = maior['label']

    saida['composicao'] = composicao
    saida['maior_pct'] = maior_pct
    saida['maior_label'] = maior_label
    saida['total'] = total
    return saida


def custo_por_veiculo(data_de=None, data_ate=None, placa=None):
    totais = defaultdict(lambda: {
        'placa': '',
        'abastecimento': 0.0,
        'pedagio': 0.0,
        'manutencao': 0.0,
        'outros': 0.0,
        'ociosidade': 0.0,
        'km': 0.0,
        'total': 0.0,
        'custo_km': 0.0,
    })
    veiculos = {v.id: v.placa for v in LogisticaVeiculo.query.all()}

    lanc_q = LogisticaLancamento.query
    man_q = LogisticaManutencao.query
    oci_q = LogisticaOciosidade.query
    if data_de:
        lanc_q = lanc_q.filter(LogisticaLancamento.data >= data_de)
        man_q = man_q.filter(LogisticaManutencao.data >= data_de)
        oci_q = oci_q.filter(LogisticaOciosidade.data >= data_de)
    if data_ate:
        lanc_q = lanc_q.filter(LogisticaLancamento.data <= data_ate)
        man_q = man_q.filter(LogisticaManutencao.data <= data_ate)
        oci_q = oci_q.filter(LogisticaOciosidade.data <= data_ate)
    if placa and placa != 'all':
        lanc_q = lanc_q.filter(LogisticaLancamento.placa == placa)
        man_q = man_q.filter(LogisticaManutencao.placa == placa)
        oci_q = oci_q.filter(LogisticaOciosidade.placa == placa)

    for row in lanc_q.all():
        key = row.veiculo_id or row.placa or 0
        item = totais[key]
        item['placa'] = row.placa or veiculos.get(row.veiculo_id) or ''
        cat = (row.categoria or 'Outros')
        if cat in ('Combustível', 'Abastecimento'):
            item['abastecimento'] += float(row.valor or 0)
        elif cat == 'Pedágio':
            item['pedagio'] += float(row.valor or 0)
        else:
            item['outros'] += float(row.valor or 0)
        if row.km:
            item['km'] += float(row.km)
    for row in man_q.all():
        key = row.veiculo_id or row.placa or 0
        item = totais[key]
        item['placa'] = row.placa or veiculos.get(row.veiculo_id) or item['placa']
        item['manutencao'] += float(row.valor or 0)
    for row in oci_q.all():
        key = row.veiculo_id or row.placa or 0
        item = totais[key]
        item['placa'] = row.placa or veiculos.get(row.veiculo_id) or item['placa']
        item['ociosidade'] += float(row.valor or 0)

    saida = []
    for item in totais.values():
        item['total'] = (
            item['abastecimento'] + item['pedagio'] + item['manutencao']
            + item['outros'] + item['ociosidade']
        )
        item['custo_km'] = (item['total'] / item['km']) if item['km'] else 0.0
        for k in ('abastecimento', 'pedagio', 'manutencao', 'outros', 'ociosidade', 'total', 'km', 'custo_km'):
            item[k] = round(item[k], 4 if k == 'custo_km' else 2)
        saida.append(item)
    saida.sort(key=lambda x: x['total'], reverse=True)
    return saida


def alertas_dashboard(mes=None):
    from models_logistica import LogisticaFolga, LogisticaFolha, LogisticaRevisao
    hoje = date.today()
    mes = mes or hoje.strftime('%Y-%m')
    revisoes = []
    for row in LogisticaRevisao.query.filter(LogisticaRevisao.status != 'Realizada').all():
        km_restante = None
        if row.km_previsto is not None and row.km_realizado is not None:
            km_restante = float(row.km_previsto) - float(row.km_realizado)
        status = 'em dia'
        if km_restante is not None:
            if km_restante <= 0:
                status = 'vencida'
            elif km_restante <= 2000:
                status = 'próxima'
        elif row.data_prevista and row.data_prevista <= hoje:
            status = 'vencida'
        if status in ('vencida', 'próxima'):
            item = row.to_dict()
            item['alerta'] = status
            item['km_restante'] = km_restante
            revisoes.append(item)
    boletos = []
    for row in LogisticaManutencao.query.filter(
        LogisticaManutencao.vencimento.isnot(None),
        LogisticaManutencao.status != 'Concluído',
    ).all():
        if row.vencimento and 0 <= (row.vencimento - hoje).days <= 15:
            boletos.append(row.to_dict())
    folgas = [r.to_dict() for r in LogisticaFolga.query.filter_by(mes=mes).all()]
    folhas = LogisticaFolha.query.filter_by(mes=mes).all()
    custo_folha = sum(totais_folha(f)['custo_empresa'] for f in folhas)
    pessoas = max(len(folhas), 1) if folhas else 0
    media = (custo_folha / pessoas) if pessoas else 0
    return {
        'revisoes': revisoes,
        'boletos': boletos,
        'folgas': folgas,
        'media_funcionario': round(media, 2),
        'folha_mes': round(custo_folha, 2),
    }


NOMINATIM_UA = 'SaoGeraldoLogistica/1.0 (logistica@saogeraldo)'
_CEP_RE = re.compile(r'\b(\d{5})-?(\d{3})\b')


def _nominatim_search(params):
    query = urllib.parse.urlencode(params)
    url = 'https://nominatim.openstreetmap.org/search?' + query
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': NOMINATIM_UA,
            'Accept-Language': 'pt-BR,pt;q=0.9',
        },
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode('utf-8', errors='replace'))


def _extrair_cep(texto):
    m = _CEP_RE.search(texto or '')
    return (m.group(1) + m.group(2)) if m else None


def _limpar_endereco(texto):
    t = re.sub(r'\bCEP\b[:\s]*', ' ', texto or '', flags=re.I)
    t = re.sub(r'\s*[-–—]\s*', ', ', t)
    t = _CEP_RE.sub('', t)
    t = re.sub(r'\s+,', ',', t)
    t = re.sub(r',\s*,+', ',', t)
    return re.sub(r'\s+', ' ', t).strip(' ,')


def _coords_de_nominatim(rows, fallback_name):
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0] or {}
    try:
        lat = float(row.get('lat'))
        lng = float(row.get('lon'))
    except (TypeError, ValueError):
        return None
    return {
        'lat': lat,
        'lng': lng,
        'display_name': (row.get('display_name') or fallback_name)[:255],
    }


def _nominatim_hit(fetch, q):
    params = {
        'q': q,
        'format': 'json',
        'limit': '1',
        'countrycodes': 'br',
        'addressdetails': '0',
    }
    try:
        rows = fetch(params) or []
        hit = _coords_de_nominatim(rows, q)
        if hit:
            return hit
        params.pop('countrycodes', None)
        rows = fetch(params) or []
        return _coords_de_nominatim(rows, q)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        return None


def _consultar_cep(cep):
    url = 'https://brasilapi.com.br/api/cep/v2/' + cep
    req = urllib.request.Request(url, headers={'User-Agent': NOMINATIM_UA})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode('utf-8', errors='replace'))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        return None
    loc = ((payload.get('location') or {}).get('coordinates') or {})
    try:
        lat = float(str(loc.get('latitude')).replace(',', '.'))
        lng = float(str(loc.get('longitude')).replace(',', '.'))
    except (TypeError, ValueError):
        return None
    partes = [
        payload.get('street'),
        payload.get('neighborhood'),
        payload.get('city'),
        payload.get('state'),
        cep,
    ]
    display = ', '.join(p for p in partes if p)
    return {'lat': lat, 'lng': lng, 'display_name': (display or cep)[:255], 'cep': payload}


def geocodificar_endereco(endereco, search=None, cep_lookup=None):
    """Resolve endereço em lat/lng via Nominatim, com fallback pelo CEP."""
    raw = ' '.join((endereco or '').split())
    if len(raw) < 5:
        return None
    fetch = search or _nominatim_search
    lookup = cep_lookup or _consultar_cep
    cleaned = _limpar_endereco(raw)
    queries = []
    for q in (cleaned, raw):
        if q and q not in queries and len(q) >= 5:
            queries.append(q)
    for q in queries:
        hit = _nominatim_hit(fetch, q)
        if hit:
            return hit
    cep = _extrair_cep(raw)
    if not cep:
        return None
    cep_info = lookup(cep)
    if not cep_info:
        return None
    return {k: cep_info[k] for k in ('lat', 'lng', 'display_name')}


def seed_logistica():
    """Módulo começa vazio: o cadastro operacional fica nas telas."""
    return
