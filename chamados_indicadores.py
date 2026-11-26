"""Indicadores do dashboard de chamados.

Período, mesa de atendimento, serviço e tipo filtram evolução,
os dois rankings, a mediana, a execução e o prazo x início do atendimento.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median

MANUTENCAO_CORRETIVA = 'Manutenção corretiva'
MANUTENCAO_PREVENTIVA = 'Manutenção preventiva'
CLASSES_MANUTENCAO = (MANUTENCAO_CORRETIVA, MANUTENCAO_PREVENTIVA)
SERVICOS_CONHECIDOS = ('Manutenção', 'Instalação', 'Reparo', 'Configuração', 'Outro')
UNIDADES = (('ti', 'TI'), ('nutricao', 'Nutrição'))
TIPOS_ITEM = (
    'Access Point',
    'Celulares e Comunicação',
    'Estação',
    'Hardware',
    'Mobília',
    'Periférico',
    'Servidor Local',
    'Software',
)
LIMITE_DETALHE = 80
PRAZOS_HORAS = (4, 12, 24, 48, 72)


def _data(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.date()
    return dt


def _horas(inicio, fim):
    if not inicio or not fim:
        return None
    delta = (fim - inicio).total_seconds() / 3600.0
    if delta < 0:
        return None
    return delta


def _mediana(valores):
    if not valores:
        return None
    return float(median(valores))


def _txt_horas(horas):
    if horas is None:
        return '—'
    minutos = int(round(horas * 60))
    horas_cheias, resto = divmod(minutos, 60)
    if horas_cheias and resto:
        return f'{horas_cheias} h {resto} min'
    if horas_cheias:
        return f'{horas_cheias} h'
    return f'{resto} min'


def _pct(parte, total):
    if not total:
        return None
    return round(parte * 100.0 / total, 1)


def _fmt_dt(dt):
    if not dt:
        return '—'
    if isinstance(dt, datetime):
        return dt.strftime('%d/%m/%Y %H:%M')
    return dt.strftime('%d/%m/%Y')


def _buckets(inicio, fim):
    dias = (fim - inicio).days + 1
    if dias <= 31:
        def chave(dia):
            return dia

        def rotulo(dia):
            return dia.strftime('%d/%m')

        passo = timedelta(days=1)
        cursor = inicio
        buckets = []
        while cursor <= fim:
            buckets.append(cursor)
            cursor += passo
        return buckets, chave, rotulo
    if dias <= 120:
        def chave(dia):
            return dia - timedelta(days=dia.weekday())

        def rotulo(dia):
            return dia.strftime('%d/%m')

        cursor = inicio - timedelta(days=inicio.weekday())
        buckets = []
        while cursor <= fim:
            buckets.append(cursor)
            cursor += timedelta(days=7)
        return buckets, chave, rotulo

    def chave(dia):
        return dia.replace(day=1)

    def rotulo(dia):
        return dia.strftime('%m/%Y')

    cursor = inicio.replace(day=1)
    buckets = []
    while cursor <= fim:
        buckets.append(cursor)
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return buckets, chave, rotulo


def _no_prazo(item):
    if not item.get('fechado') or not item.get('conclusao') or not item.get('venc_solucao'):
        return None
    return item['conclusao'] <= item['venc_solucao']


def _detalhe(item):
    prazo = _no_prazo(item)
    if prazo is None:
        prazo_txt = '—'
    elif prazo:
        prazo_txt = 'Sim'
    else:
        prazo_txt = 'Não'
    return {
        'id': item.get('id'),
        'numero': item.get('numero') or '—',
        'status': item.get('status') or '—',
        'mantenedor': item.get('mantenedor') or 'Sem mantenedor',
        'servico': item.get('servico') or '—',
        'tipo': item.get('tipo') or 'Sem tipo',
        'abertura': _fmt_dt(item.get('criacao')),
        'conclusao': _fmt_dt(item.get('conclusao')),
        'prazo': prazo_txt,
    }


def _opcoes(conhecidos, presentes):
    vistos = set(conhecidos)
    extras = []
    for nome in presentes:
        nome = (nome or '').strip()
        if not nome or nome in vistos or nome == '—':
            continue
        vistos.add(nome)
        extras.append(nome)
    return list(conhecidos) + extras


def _classe_manutencao(item):
    """Abertura do sistema ou do WhatsApp é corretiva. Programada é preventiva."""
    if item.get('preventiva'):
        return MANUTENCAO_PREVENTIVA
    return MANUTENCAO_CORRETIVA


def _ranking_manutencao(filtrados):
    """Duas fatias fixas: corretiva (aberturas) e preventiva (programadas)."""
    if not filtrados:
        return []
    marcados = []
    for item in filtrados:
        copia = dict(item)
        copia['servico'] = _classe_manutencao(item)
        marcados.append(copia)
    linhas = _ranking(marcados, 'servico')
    por_nome = {linha['nome']: linha for linha in linhas}
    saida = []
    for nome in CLASSES_MANUTENCAO:
        linha = por_nome.get(nome) or {
            'nome': nome,
            'total': 0,
            'pct': 0,
            'detalhe': [],
            'ocultos': 0,
        }
        saida.append(linha)
    for pos, linha in enumerate(saida, start=1):
        linha['pos'] = pos
    return saida


def _ranking(filtrados, campo):
    grupos = defaultdict(list)
    for item in filtrados:
        grupos[item.get(campo) or '—'].append(item)
    base = len(filtrados)
    linhas = []
    for nome, grupo in grupos.items():
        grupo_ord = sorted(
            grupo,
            key=lambda item: item.get('criacao') or datetime.min,
            reverse=True,
        )
        linhas.append({
            'nome': nome,
            'total': len(grupo),
            'pct': round(len(grupo) * 100.0 / base, 1) if base else 0,
            'detalhe': [_detalhe(item) for item in grupo_ord[:LIMITE_DETALHE]],
            'ocultos': max(0, len(grupo) - LIMITE_DETALHE),
        })
    linhas.sort(key=lambda linha: (-linha['total'], linha['nome']))
    for pos, linha in enumerate(linhas, start=1):
        linha['pos'] = pos
    return linhas


def _por_mantenedor(filtrados):
    grupos = defaultdict(list)
    for item in filtrados:
        grupos[item.get('mantenedor') or 'Sem mantenedor'].append(item)
    tempos = []
    execucao = []
    for nome, grupo in grupos.items():
        respostas = []
        conclusoes = []
        no_prazo = fora_prazo = fechados = 0
        horas_tipo = defaultdict(list)
        qtd_tipo = Counter()
        for item in grupo:
            tipo_item = item.get('tipo') or 'Sem tipo'
            qtd_tipo[tipo_item] += 1
            resposta = _horas(item.get('criacao'), item.get('inicio'))
            if resposta is not None:
                respostas.append(resposta)
            if not item.get('fechado'):
                continue
            fechados += 1
            conclusao = _horas(item.get('criacao'), item.get('conclusao'))
            if conclusao is not None:
                conclusoes.append(conclusao)
                horas_tipo[tipo_item].append(conclusao)
            prazo = _no_prazo(item)
            if prazo is True:
                no_prazo += 1
            elif prazo is False:
                fora_prazo += 1
        med_resp = _mediana(respostas)
        med_conc = _mediana(conclusoes)
        tipos = []
        for tipo_nome, qtd in qtd_tipo.items():
            med = _mediana(horas_tipo.get(tipo_nome) or [])
            tipos.append({
                'tipo': tipo_nome,
                'mediana_txt': _txt_horas(med),
                'total': qtd,
            })
        tipos.sort(key=lambda linha: (-linha['total'], linha['tipo']))
        tempos.append({
            'nome': nome,
            'mediana_resposta': round(med_resp, 2) if med_resp is not None else None,
            'mediana_conclusao': round(med_conc, 2) if med_conc is not None else None,
            'mediana_resposta_txt': _txt_horas(med_resp),
            'mediana_conclusao_txt': _txt_horas(med_conc),
            'total': len(grupo),
        })
        execucao.append({
            'nome': nome,
            'pct_prazo': _pct(no_prazo, no_prazo + fora_prazo),
            'indice': _pct(fechados, len(grupo)),
            'total': len(grupo),
            'tipos': tipos,
        })
    tempos.sort(key=lambda linha: (-linha['total'], linha['nome']))
    execucao.sort(key=lambda linha: (-linha['total'], linha['nome']))
    return tempos, execucao


def _prazo_vs_inicio(filtrados):
    """Prazo do equipamento e mediana das horas até o início do atendimento."""
    grupos = {horas: [] for horas in PRAZOS_HORAS}
    sem_inicio = {horas: 0 for horas in PRAZOS_HORAS}
    for item in filtrados:
        prazo = item.get('prazo_horas')
        try:
            prazo = int(prazo)
        except (TypeError, ValueError):
            continue
        if prazo not in grupos:
            continue
        decorrido = _horas(item.get('criacao'), item.get('inicio'))
        if decorrido is None:
            sem_inicio[prazo] += 1
            continue
        grupos[prazo].append(decorrido)
    linhas = []
    for prazo in PRAZOS_HORAS:
        valores = grupos[prazo]
        if not valores and not sem_inicio[prazo]:
            continue
        med = _mediana(valores)
        dentro = sum(1 for horas in valores if horas <= prazo)
        linhas.append({
            'prazo': prazo,
            'label': '%s h' % prazo,
            'mediana': round(med, 2) if med is not None else None,
            'mediana_txt': _txt_horas(med),
            'total': len(valores) + sem_inicio[prazo],
            'com_inicio': len(valores),
            'sem_inicio': sem_inicio[prazo],
            'dentro': dentro,
            'pct_dentro': _pct(dentro, len(valores)),
        })
    return linhas


def _mesa_id(valor):
    txt = str(valor or '').strip()
    if not txt.isdigit():
        return None
    return int(txt)


def calcular_indicadores(itens, inicio, fim, unidade='', servico='', tipo='', mesa=''):
    """Monta evolução, rankings e séries de mantenedor já filtrados."""
    if inicio > fim:
        inicio, fim = fim, inicio
    unidade = (unidade or '').strip()
    servico = (servico or '').strip()
    tipo = (tipo or '').strip()
    mesa_id = _mesa_id(mesa)

    no_periodo = []
    for item in itens or []:
        dia = _data(item.get('criacao'))
        if dia is None or dia < inicio or dia > fim:
            continue
        no_periodo.append(item)

    filtrados = []
    for item in no_periodo:
        if unidade and (item.get('unidade') or '') != unidade:
            continue
        if servico and (item.get('servico') or '') != servico:
            continue
        if tipo and (item.get('tipo') or '') != tipo:
            continue
        if mesa_id is not None and item.get('mesa_id') != mesa_id:
            continue
        filtrados.append(item)

    buckets, chave, rotulo = _buckets(inicio, fim)
    abertos = Counter()
    concluidos = Counter()
    for item in filtrados:
        abertos[chave(_data(item.get('criacao')))] += 1
        if item.get('fechado') and item.get('conclusao'):
            dia_fim = _data(item['conclusao'])
            if dia_fim and inicio <= dia_fim <= fim:
                concluidos[chave(dia_fim)] += 1

    tempos, execucao = _por_mantenedor(filtrados)
    return {
        'filtros': {
            'de': inicio.isoformat(),
            'ate': fim.isoformat(),
            'unidade': unidade,
            'servico': servico,
            'tipo': tipo,
            'mesa': str(mesa_id) if mesa_id is not None else '',
        },
        'opcoes': {
            'unidades': [{'id': chave_u, 'nome': nome} for chave_u, nome in UNIDADES],
            'servicos': _opcoes(SERVICOS_CONHECIDOS, (item.get('servico') for item in no_periodo)),
            'tipos': _opcoes(TIPOS_ITEM, (item.get('tipo') for item in no_periodo)),
        },
        'evolucao': {
            'labels': [rotulo(bucket) for bucket in buckets],
            'abertos': [abertos.get(bucket, 0) for bucket in buckets],
            'concluidos': [concluidos.get(bucket, 0) for bucket in buckets],
        },
        'ranking_unidades': _ranking(filtrados, 'cliente'),
        'ranking_servicos': _ranking_manutencao(filtrados),
        'tempos': tempos,
        'execucao': execucao,
        'prazo_atendimento': _prazo_vs_inicio(filtrados),
        'total': len(filtrados),
    }
