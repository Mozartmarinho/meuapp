"""Avaliação do atendimento e o panorama do dia no dashboard de chamados."""
from __future__ import annotations

import calendar
import re
import secrets
from datetime import datetime, time, timedelta

from models import (
    ChamadoAvaliacao,
    Cliente,
    Usuario,
    WhatsAppChamadoUsuario,
    db,
    now_brasilia,
    status_fechado,
)
from whatsapp_pesagem import normalizar_telefone, telefone_valido

NOTAS_AVALIACAO = (
    (1, 'pessimo', 'Péssimo'),
    (2, 'ruim', 'Ruim'),
    (3, 'bom', 'Bom'),
    (4, 'muito_bom', 'Muito bom'),
    (5, 'excelente', 'Excelente'),
)
_POR_NOTA = {nota: rotulo for nota, _slug, rotulo in NOTAS_AVALIACAO}
_ALIASES = {}
for nota, slug, rotulo in NOTAS_AVALIACAO:
    _ALIASES[str(nota)] = (nota, rotulo)
    _ALIASES[slug] = (nota, rotulo)
    _ALIASES[rotulo.lower()] = (nota, rotulo)
_ALIASES['péssimo'] = (1, 'Péssimo')
_ALIASES['muito bom'] = (4, 'Muito bom')
_ALIASES['muitobom'] = (4, 'Muito bom')
_ALIASES['muito-bom'] = (4, 'Muito bom')

_PULAR = {'0', 'agora nao', 'agora não', 'pular', 'depois', 'não', 'nao'}
_ETAPAS_LIVRES = {'idle', 'novo', '', 'wait_confirm', 'avaliacao'}
_MESES = (
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
)
_DIAS = ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')


def parse_nota_avaliacao(texto):
    """Aceita 1–5 ou o nome da nota. Frases longas não viram nota."""
    bruto = ' '.join((texto or '').strip().lower().split())
    if not bruto or len(bruto) > 24:
        return None
    if bruto in _ALIASES:
        return _ALIASES[bruto]
    match = re.match(r'^([1-5])(?:\s*[-–.]\s*\w+)?$', bruto)
    if match:
        return _ALIASES[match.group(1)]
    return None


def pedido_avaliacao_texto(link):
    linhas = [
        '',
        'O chamado está sendo encerrado. Avalie o atendimento respondendo com o número:',
        '1 - Péssimo',
        '2 - Ruim',
        '3 - Bom',
        '4 - Muito bom',
        '5 - Excelente',
        '0 - Agora não',
    ]
    if link:
        linhas.extend(['', 'Ou avalie neste link: %s' % link])
    return '\n'.join(linhas)


def telefone_do_chamado(chamado, canal, contato):
    """Telefone de quem abriu: o do WhatsApp ou o cadastro do solicitante."""
    if (canal or '') == 'WhatsApp' and telefone_valido(contato):
        return normalizar_telefone(contato)
    opener = getattr(chamado, 'tecnico', None)
    fone = getattr(opener, 'telefone', None) if opener else None
    if telefone_valido(fone):
        return normalizar_telefone(fone)
    return ''


def garantir_avaliacao(chamado, telefone=None, tecnico_id=None):
    """Uma avaliação pendente por chamado. Não apaga nota já dada."""
    if not chamado or not getattr(chamado, 'id', None):
        return None
    phone = normalizar_telefone(telefone) if telefone_valido(telefone) else ''
    tec = tecnico_id or getattr(chamado, 'atendente_id', None)
    row = ChamadoAvaliacao.query.filter_by(chamado_id=chamado.id).first()
    if row:
        if phone and not row.telefone:
            row.telefone = phone
        if tec and not row.tecnico_id:
            row.tecnico_id = tec
        if not row.cliente_id:
            row.cliente_id = chamado.cliente_id
        db.session.commit()
        return row
    row = ChamadoAvaliacao(
        chamado_id=chamado.id,
        tecnico_id=tec,
        cliente_id=getattr(chamado, 'cliente_id', None),
        telefone=phone or None,
        token=secrets.token_urlsafe(18),
        criada_em=now_brasilia(),
    )
    db.session.add(row)
    db.session.commit()
    return row


def preparar_etapa_whatsapp(telefone):
    """A próxima resposta livre desse número entra como avaliação."""
    phone = normalizar_telefone(telefone) if telefone_valido(telefone) else ''
    if not phone:
        return False
    usuario = WhatsAppChamadoUsuario.query.filter_by(telefone=phone).first()
    if not usuario:
        return False
    if (usuario.etapa or '') not in _ETAPAS_LIVRES:
        return False
    usuario.etapa = 'avaliacao'
    db.session.commit()
    return True


def _pendente_do_telefone(telefone):
    phone = normalizar_telefone(telefone) if telefone else ''
    if not phone:
        return None
    return (
        ChamadoAvaliacao.query
        .filter(ChamadoAvaliacao.telefone == phone, ChamadoAvaliacao.nota.is_(None))
        .order_by(ChamadoAvaliacao.id.desc())
        .first()
    )


def _aplicar_nota(row, nota, rotulo):
    if row.nota:
        return False
    row.nota = nota
    row.rotulo = rotulo
    row.avaliada_em = now_brasilia()
    db.session.commit()
    return True


def _msg_ja_avaliado(row):
    return 'Este atendimento já foi avaliado como %s.' % (row.rotulo or _POR_NOTA.get(row.nota) or 'registrado')


def tratar_resposta_avaliacao(telefone, texto, etapa):
    """Consome a resposta só quando há avaliação pendente e a pessoa não está no meio de outro passo."""
    bruto = ' '.join((texto or '').strip().lower().split())
    pendente = _pendente_do_telefone(telefone)
    em_avaliacao = (etapa or '') == 'avaliacao'
    if not pendente and not em_avaliacao:
        return False, None, None
    if em_avaliacao and not pendente:
        phone = normalizar_telefone(telefone) if telefone else ''
        ultima = (
            ChamadoAvaliacao.query.filter_by(telefone=phone).order_by(ChamadoAvaliacao.id.desc()).first()
            if phone else None
        )
        if ultima and ultima.nota:
            return True, _msg_ja_avaliado(ultima), 'idle'
    if bruto in _PULAR and (em_avaliacao or pendente):
        if (etapa or '') not in _ETAPAS_LIVRES and not em_avaliacao:
            return False, None, None
        return True, 'Avaliação deixada para depois. Quando quiser abrir um chamado, é só escrever.', 'idle'
    if (etapa or '') not in _ETAPAS_LIVRES and not em_avaliacao:
        return False, None, None
    nota = parse_nota_avaliacao(texto)
    if nota and pendente:
        if not _aplicar_nota(pendente, nota[0], nota[1]):
            return True, _msg_ja_avaliado(pendente), 'idle'
        return True, 'Obrigado. Sua avaliação do atendimento foi registrada: %s.' % nota[1], 'idle'
    if em_avaliacao:
        return True, (
            'Responda com o número da avaliação:\n'
            '1 - Péssimo\n2 - Ruim\n3 - Bom\n4 - Muito bom\n5 - Excelente\n0 - Agora não'
        ), None
    return False, None, None


def registrar_por_token(token, nota):
    row = ChamadoAvaliacao.query.filter_by(token=(token or '').strip()).first()
    if not row:
        return None, 'Link inválido.'
    if row.nota:
        return row, _msg_ja_avaliado(row)
    parsed = nota if isinstance(nota, tuple) else parse_nota_avaliacao(str(nota or ''))
    if not parsed:
        return row, 'Escolha uma das notas.'
    _aplicar_nota(row, parsed[0], parsed[1])
    return row, 'Obrigado. Sua avaliação foi registrada: %s.' % parsed[1]


def avaliacao_do_chamado(chamado_id):
    if not chamado_id:
        return None
    return ChamadoAvaliacao.query.filter_by(chamado_id=chamado_id).first()


def _hora(valor):
    if not valor:
        return '—'
    return valor.strftime('%d/%m %H:%M')


def _nome_rel(obj):
    nome = (getattr(obj, 'nome', None) or '').strip() if obj else ''
    return nome or '—'


def _toca_dia(chamado, dia):
    for valor in (
        getattr(chamado, 'data_criacao', None),
        getattr(chamado, 'data_inicio_atendimento', None),
        getattr(chamado, 'data_conclusao', None),
    ):
        if valor and getattr(valor, 'date', None) and valor.date() == dia:
            return True
    reag = getattr(chamado, 'data_reagendamento', None)
    return bool(reag and reag == dia)


def _acumulado(momentos, dia):
    horas = [0] * 24
    for momento in momentos:
        if not momento or momento.date() != dia:
            continue
        for hora in range(momento.hour, 24):
            horas[hora] += 1
    return horas


def montar_atendimento_dia(chamados, dia):
    """Chamados do dia com hora de abertura, atendimento e finalização."""
    do_dia = [c for c in chamados or [] if _toca_dia(c, dia)]
    abertos = [c for c in do_dia if c.data_criacao and c.data_criacao.date() == dia]
    em_atendimento = [
        c for c in do_dia
        if c.data_inicio_atendimento and c.data_inicio_atendimento.date() == dia
    ]
    finalizados = [c for c in do_dia if c.data_conclusao and c.data_conclusao.date() == dia]
    pendentes = [c for c in do_dia if not status_fechado(c.status)]
    linhas = []
    for chamado in sorted(do_dia, key=lambda c: (c.data_criacao or datetime.min, c.id or 0)):
        tecnico = getattr(chamado, 'atendente', None)
        linhas.append({
            'id': chamado.id,
            'numero': chamado.numero_chamado,
            'unidade': _nome_rel(getattr(chamado, 'cliente', None)),
            'tecnico': _nome_rel(tecnico),
            'status': chamado.status or '—',
            'tipo': chamado.tipo_servico or '—',
            'abertura': _hora(chamado.data_criacao),
            'atendimento': _hora(chamado.data_inicio_atendimento),
            'finalizacao': _hora(chamado.data_conclusao),
            'fechado': status_fechado(chamado.status),
        })
    anterior = dia - timedelta(days=1)
    seguinte = dia + timedelta(days=1)
    return {
        'dia': dia.isoformat(),
        'label': '%s, %s' % (_DIAS[dia.weekday()], dia.strftime('%d/%m/%Y')),
        'mes_label': '%s %s' % (_MESES[dia.month - 1].capitalize(), dia.year),
        'anterior': anterior.isoformat(),
        'seguinte': seguinte.isoformat(),
        'abertos': len(abertos),
        'em_atendimento': len(em_atendimento),
        'finalizados': len(finalizados),
        'pendentes': len(pendentes),
        'total': len(do_dia),
        'linhas': linhas,
        'chart': {
            'labels': ['%02dh' % hora for hora in range(24)],
            'abertos': _acumulado([c.data_criacao for c in abertos], dia),
            'atendimento': _acumulado([c.data_inicio_atendimento for c in em_atendimento], dia),
            'finalizados': _acumulado([c.data_conclusao for c in finalizados], dia),
        },
    }


def montar_calendario(dia, chamados, hoje=None):
    hoje = hoje or now_brasilia().date()
    contagem = {}
    for chamado in chamados or []:
        vistos = set()
        for valor in (
            getattr(chamado, 'data_criacao', None),
            getattr(chamado, 'data_inicio_atendimento', None),
            getattr(chamado, 'data_conclusao', None),
        ):
            if valor and valor.date() == valor.date() and valor.year == dia.year and valor.month == dia.month:
                chave = valor.date()
                if chave not in vistos:
                    contagem[chave] = contagem.get(chave, 0) + 1
                    vistos.add(chave)
        reag = getattr(chamado, 'data_reagendamento', None)
        if reag and reag.year == dia.year and reag.month == dia.month and reag not in vistos:
            contagem[reag] = contagem.get(reag, 0) + 1
    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(dia.year, dia.month):
        celulas = []
        for item in semana:
            celulas.append({
                'iso': item.isoformat(),
                'num': item.day,
                'fora': item.month != dia.month,
                'hoje': item == hoje,
                'sel': item == dia,
                'qtd': contagem.get(item, 0),
            })
        semanas.append(celulas)
    primeiro = dia.replace(day=1)
    anterior = (primeiro - timedelta(days=1)).replace(day=1)
    if dia.month == 12:
        seguinte = dia.replace(year=dia.year + 1, month=1, day=1)
    else:
        seguinte = dia.replace(month=dia.month + 1, day=1)
    return {
        'mes_label': '%s %s' % (_MESES[dia.month - 1].capitalize(), dia.year),
        'anterior': anterior.isoformat(),
        'seguinte': seguinte.isoformat(),
        'semanas': semanas,
        'hoje': hoje.isoformat(),
    }


def _vazio_relatorio(inicio, fim, tecnico_id, cliente_id):
    return {
        'de': inicio.isoformat() if inicio else '',
        'ate': fim.isoformat() if fim else '',
        'tecnico_id': tecnico_id,
        'cliente_id': cliente_id,
        'total': 0,
        'media': None,
        'media_txt': '—',
        'faixas': [
            {'nota': nota, 'rotulo': rotulo, 'total': 0, 'pct': 0}
            for nota, _slug, rotulo in NOTAS_AVALIACAO
        ],
        'linhas': [],
    }


def relatorio_avaliacoes(chamado_ids, inicio, fim, tecnico_id=None, cliente_id=None):
    """Notas já dadas, com filtro de período, técnico e unidade."""
    if chamado_ids is not None and len(chamado_ids) == 0:
        return _vazio_relatorio(inicio, fim, tecnico_id, cliente_id)
    consulta = ChamadoAvaliacao.query.filter(ChamadoAvaliacao.nota.isnot(None))
    if chamado_ids is not None:
        consulta = consulta.filter(ChamadoAvaliacao.chamado_id.in_(list(chamado_ids)))
    if inicio:
        consulta = consulta.filter(ChamadoAvaliacao.avaliada_em >= datetime.combine(inicio, time.min))
    if fim:
        consulta = consulta.filter(ChamadoAvaliacao.avaliada_em <= datetime.combine(fim, time.max))
    base = consulta.order_by(ChamadoAvaliacao.avaliada_em.desc(), ChamadoAvaliacao.id.desc()).all()
    if tecnico_id:
        linhas_fonte = [row for row in base if row.tecnico_id == tecnico_id]
    else:
        linhas_fonte = list(base)
    if cliente_id:
        linhas_fonte = [row for row in linhas_fonte if row.cliente_id == cliente_id]
    contagem = {nota: 0 for nota, _slug, _rotulo in NOTAS_AVALIACAO}
    for row in linhas_fonte:
        if row.nota in contagem:
            contagem[row.nota] += 1
    total = len(linhas_fonte)
    soma = sum(row.nota for row in linhas_fonte if row.nota)
    media = (soma / total) if total else None
    chamados = {}
    tecnicos = {}
    clientes = {}
    ids_chamado = {row.chamado_id for row in linhas_fonte}
    ids_tec = {row.tecnico_id for row in linhas_fonte if row.tecnico_id}
    ids_cli = {row.cliente_id for row in linhas_fonte if row.cliente_id}
    if ids_chamado:
        from models import Chamado
        for chamado in Chamado.query.filter(Chamado.id.in_(ids_chamado)).all():
            chamados[chamado.id] = chamado
    if ids_tec:
        for usuario in Usuario.query.filter(Usuario.id.in_(ids_tec)).all():
            tecnicos[usuario.id] = usuario.nome
    if ids_cli:
        for cliente in Cliente.query.filter(Cliente.id.in_(ids_cli)).all():
            clientes[cliente.id] = cliente.nome
    linhas = []
    for row in linhas_fonte[:200]:
        chamado = chamados.get(row.chamado_id)
        linhas.append({
            'chamado_id': row.chamado_id,
            'numero': chamado.numero_chamado if chamado else '—',
            'quando': row.avaliada_em.strftime('%d/%m/%Y %H:%M') if row.avaliada_em else '—',
            'tecnico': tecnicos.get(row.tecnico_id) or '—',
            'unidade': clientes.get(row.cliente_id) or '—',
            'nota': row.nota,
            'rotulo': row.rotulo or _POR_NOTA.get(row.nota) or '—',
        })
    return {
        'de': inicio.isoformat() if inicio else '',
        'ate': fim.isoformat() if fim else '',
        'tecnico_id': tecnico_id,
        'cliente_id': cliente_id,
        'total': total,
        'media': media,
        'media_txt': ('%.1f' % media).replace('.', ',') if media is not None else '—',
        'faixas': [
            {
                'nota': nota,
                'rotulo': rotulo,
                'total': contagem[nota],
                'pct': round(100.0 * contagem[nota] / total) if total else 0,
            }
            for nota, _slug, rotulo in NOTAS_AVALIACAO
        ],
        'linhas': linhas,
    }
