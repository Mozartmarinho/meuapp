"""Preventiva automática e termo de responsabilidade de equipamentos."""
from __future__ import annotations

import base64
import json
import logging
import os
import random
import re
import secrets
import string
import threading
import time
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

from models import (
    FREQUENCIAS_PREVENTIVA_KEYS,
    STATUS_FECHADOS,
    Chamado,
    ChamadoSetor,
    Equipamento,
    EquipamentoPreventiva,
    EquipamentoTermo,
    Usuario,
    acessorios_sugeridos,
    aplicar_automacoes,
    db,
    MESA_PADRAO,
    mesa_padrao,
    mesa_por_nome,
    normalizar_acessorios,
    now_brasilia,
)

LOG = logging.getLogger('equipamento')

_UPLOAD_TERMOS = Path(__file__).resolve().parent / 'static' / 'uploads' / 'termos'
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
_SCHEDULER_INTERVAL = int(os.environ.get('EQ_PREVENTIVA_INTERVAL', '120') or 120)
_bg_lock = threading.Lock()
_bg_started = False

ACESORIOS_CHAVES = (
    ('equipamento', 'Equipamento'),
    ('fonte', 'Fonte/Carregador'),
    ('cabo', 'Cabo de alimentação'),
    ('teclado', 'Teclado'),
    ('mouse', 'Mouse'),
    ('outros', 'Outros'),
)


def acessorios_from_payload(raw):
    if raw is None:
        return [{'nome': 'Equipamento', 'qtd': '01', 'obs': ''}]
    return normalizar_acessorios(raw)


def add_months(d, months):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def avancar_data(d, frequencia):
    freq = (frequencia or 'mensal').strip().lower()
    if freq == 'semanal':
        return d + timedelta(days=7)
    if freq == 'quinzenal':
        return d + timedelta(days=14)
    if freq == 'trimestral':
        return add_months(d, 3)
    if freq == 'semestral':
        return add_months(d, 6)
    if freq == 'anual':
        return add_months(d, 12)
    return add_months(d, 1)


def ocorrencias_preventiva(prev, ano=None, limite=None, max_itens=36):
    if not prev or not prev.ativa or not prev.proxima_data:
        return []
    inicio = date(ano, 1, 1) if ano else date.today() - timedelta(days=14)
    fim = date(ano, 12, 31) if ano else (limite or (date.today() + timedelta(days=370)))
    d = prev.proxima_data
    # recua até cobrir o início do período visível
    guard = 0
    while d > inicio and guard < 48:
        anterior = _retroceder_data(d, prev.frequencia)
        if anterior >= d:
            break
        d = anterior
        guard += 1
    out = []
    while d <= fim and len(out) < max_itens:
        if d >= inicio:
            dur = max(1, int(prev.duracao_dias or 1))
            for i in range(dur):
                dia = d + timedelta(days=i)
                if inicio <= dia <= fim:
                    out.append(dia)
        d = avancar_data(d, prev.frequencia)
    return out


def _retroceder_data(d, frequencia):
    freq = (frequencia or 'mensal').strip().lower()
    if freq == 'semanal':
        return d - timedelta(days=7)
    if freq == 'quinzenal':
        return d - timedelta(days=14)
    if freq == 'trimestral':
        return add_months(d, -3)
    if freq == 'semestral':
        return add_months(d, -6)
    if freq == 'anual':
        return add_months(d, -12)
    return add_months(d, -1)


def _numero_os():
    for _ in range(30):
        num = 'OS' + ''.join(random.choices(string.digits, k=6))
        if not Chamado.query.filter_by(numero_chamado=num).first():
            return num
    return 'OS' + ''.join(random.choices(string.digits, k=8))


def _tecnico_preventiva(prev):
    if prev and prev.tecnico_id:
        user = Usuario.query.get(prev.tecnico_id)
        if user:
            return user
    return (
        Usuario.query.filter(
            db.or_(Usuario.is_master.is_(True), Usuario.tipo == 'admin')
        )
        .order_by(Usuario.id.asc())
        .first()
        or Usuario.query.order_by(Usuario.id.asc()).first()
    )


def mesa_preventiva_equipamento(eq):
    """Mesa que recebe o toque da preventiva, conforme o tipo do equipamento."""
    tipo = eq.tipo_equipamento_norm() if eq else 'ti'
    nome = 'Manutenção Nutrição' if tipo == 'nutricao' else MESA_PADRAO
    mesa = mesa_por_nome(nome)
    if mesa and getattr(mesa, 'ativa', True):
        return mesa
    return mesa_padrao()


def _setor_tecnico_id(eq):
    nome = (eq.setor or eq.localizacao or '').strip()
    if not nome:
        return None
    s = ChamadoSetor.query.filter(ChamadoSetor.nome == nome).first()
    return s.id if s else None


def _preventiva_aberta(eq_id):
    return (
        Chamado.query.filter(
            Chamado.equipamento_id == eq_id,
            Chamado.descricao.like('Preventiva:%'),
            db.not_(Chamado.status.in_(STATUS_FECHADOS)),
        )
        .order_by(Chamado.id.desc())
        .first()
    )


def abrir_chamado_preventiva(eq, prev, hoje=None):
    """Abre OS de preventiva se vencida e não houver ticket aberto do mesmo tipo."""
    hoje = hoje or date.today()
    if not eq or not prev or not prev.ativa or not prev.proxima_data:
        return None
    if prev.proxima_data > hoje:
        return None
    if _preventiva_aberta(eq.id):
        return None
    tecnico = _tecnico_preventiva(prev)
    if not tecnico:
        LOG.warning('Preventiva %s: nenhum usuário para técnico_id', eq.id)
        return None
    codigo = eq.patrimonio or '—'
    nome = eq.nome_equipamento or 'equipamento'
    dur = max(1, int(prev.duracao_dias or 1))
    periodo = prev.proxima_data.strftime('%d/%m/%Y')
    if dur > 1:
        fim = prev.proxima_data + timedelta(days=dur - 1)
        periodo = f'{periodo} a {fim.strftime("%d/%m/%Y")}'
    desc = (
        f'Preventiva: manutenção preventiva do equipamento {nome} '
        f'(patrimônio {codigo}). Período: {periodo}. '
        f'Frequência: {prev.frequencia}.'
    )
    mesa = mesa_preventiva_equipamento(eq)
    chamado = Chamado(
        numero_chamado=_numero_os(),
        cliente_id=eq.cliente_id,
        tipo_servico='Manutenção',
        descricao=desc,
        status='Pendente',
        prioridade='Normal',
        tecnico_id=tecnico.id,
        mesa_id=mesa.id if mesa else None,
        setor_tecnico_id=_setor_tecnico_id(eq),
        equipamento_id=eq.id,
        patrimonio=eq.patrimonio,
        equipamento=eq.nome_equipamento,
    )
    db.session.add(chamado)
    db.session.flush()
    aplicar_automacoes(chamado, 'criar', tecnico)
    prev.ultimo_chamado_id = chamado.id
    prev.ultimo_em = now_brasilia()
    proxima = avancar_data(prev.proxima_data, prev.frequencia)
    while proxima <= hoje:
        proxima = avancar_data(proxima, prev.frequencia)
    prev.proxima_data = proxima
    return chamado


def corrigir_mesas_preventivas_abertas():
    """Tickets de preventiva já abertos passam para a mesa do tipo do equipamento."""
    abertos = (
        Chamado.query.filter(
            Chamado.descricao.like('Preventiva:%'),
            db.not_(Chamado.status.in_(STATUS_FECHADOS)),
            Chamado.equipamento_id.isnot(None),
        )
        .all()
    )
    alterados = 0
    for chamado in abertos:
        eq = chamado.equipamento_cadastro or Equipamento.query.get(chamado.equipamento_id)
        mesa = mesa_preventiva_equipamento(eq) if eq else None
        if mesa and chamado.mesa_id != mesa.id:
            chamado.mesa_id = mesa.id
            alterados += 1
    if alterados:
        db.session.commit()
    return alterados


def processar_preventivas(hoje=None):
    hoje = hoje or date.today()
    corrigir_mesas_preventivas_abertas()
    criados = 0
    itens = (
        EquipamentoPreventiva.query.filter_by(ativa=True)
        .filter(EquipamentoPreventiva.proxima_data.isnot(None))
        .filter(EquipamentoPreventiva.proxima_data <= hoje)
        .all()
    )
    for prev in itens:
        eq = prev.equipamento
        if not eq:
            continue
        try:
            chamado = abrir_chamado_preventiva(eq, prev, hoje=hoje)
            if chamado:
                criados += 1
        except Exception:
            LOG.exception('Falha ao abrir preventiva do equipamento %s', prev.equipamento_id)
            db.session.rollback()
    if criados:
        db.session.commit()
    else:
        db.session.commit()
    return criados


def salvar_preventiva(eq, data, usuario):
    freq = (data.get('frequencia') or 'mensal').strip().lower()
    if freq not in FREQUENCIAS_PREVENTIVA_KEYS:
        raise ValueError('Frequência de preventiva inválida.')
    ativa = data.get('ativa') in (True, 1, '1', 'on', 'true', 'sim', 'True')
    raw_data = (data.get('proxima_data') or data.get('proxima') or '').strip()
    proxima = None
    if raw_data:
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                proxima = datetime.strptime(raw_data, fmt).date()
                break
            except ValueError:
                continue
        if proxima is None:
            raise ValueError('Data da próxima preventiva inválida.')
    if ativa and not proxima:
        raise ValueError('Informe a data da próxima preventiva.')
    try:
        duracao = int(data.get('duracao_dias') or 1)
    except (TypeError, ValueError):
        duracao = 1
    duracao = max(1, min(14, duracao))
    prev = eq.preventiva
    if not prev:
        prev = EquipamentoPreventiva(equipamento_id=eq.id)
        db.session.add(prev)
        eq.preventiva = prev
    prev.ativa = ativa
    prev.frequencia = freq
    prev.proxima_data = proxima
    prev.duracao_dias = duracao
    if usuario:
        prev.tecnico_id = usuario.id
    prev.atualizado_em = now_brasilia()
    db.session.flush()
    chamado = None
    if ativa:
        chamado = abrir_chamado_preventiva(eq, prev)
    db.session.commit()
    return prev, chamado


def novo_token_termo():
    return secrets.token_urlsafe(32)


def snapshot_equipamento(eq):
    return {
        'eq_nome': eq.nome_equipamento,
        'eq_marca': eq.marca or '',
        'eq_modelo': eq.modelo or '',
        'eq_patrimonio': eq.patrimonio or '',
        'eq_serie': eq.numero_serie or '',
        'eq_tipo': eq.tipo_equipamento_norm(),
    }


def _resolver_responsavel(data):
    nome = (data.get('responsavel_nome') or data.get('nome') or '').strip()
    email = (data.get('responsavel_email') or data.get('email') or '').strip()
    telefone = (data.get('responsavel_telefone') or data.get('telefone') or '').strip()
    uid_raw = data.get('responsavel_usuario_id') or data.get('usuario_id')
    uid = int(uid_raw) if str(uid_raw or '').isdigit() else None
    user_resp = Usuario.query.get(uid) if uid else None
    if user_resp:
        nome = (user_resp.nome or nome).strip()
        email = email or (user_resp.email or '')
        telefone = telefone or (user_resp.telefone or '')
    return nome, email, telefone, user_resp


def _aplicar_dados_termo(eq, termo, data, usuario, nome, email, telefone, user_resp):
    snap = snapshot_equipamento(eq)
    termo.responsavel_usuario_id = user_resp.id if user_resp else None
    termo.responsavel_nome = (nome or termo.responsavel_nome or 'A definir')[:120]
    termo.responsavel_email = (email or '')[:120] or None
    termo.responsavel_telefone = (telefone or '')[:20] or None
    termo.responsavel_setor = (data.get('responsavel_setor') or data.get('setor') or eq.setor or '')[:80] or None
    termo.responsavel_cargo = (data.get('responsavel_cargo') or data.get('cargo') or '')[:80] or None
    termo.responsavel_matricula = (data.get('responsavel_matricula') or data.get('matricula') or '')[:40] or None
    termo.eq_nome = snap['eq_nome']
    termo.eq_marca = snap['eq_marca']
    termo.eq_modelo = snap['eq_modelo']
    termo.eq_patrimonio = snap['eq_patrimonio']
    termo.eq_serie = snap['eq_serie']
    termo.eq_tipo = snap['eq_tipo']
    raw_entrega = (data.get('data_entrega') or '').strip()
    if raw_entrega:
        try:
            termo.data_entrega = datetime.strptime(raw_entrega[:10], '%Y-%m-%d').date()
        except ValueError:
            termo.data_entrega = termo.data_entrega or date.today()
    elif not termo.data_entrega:
        termo.data_entrega = date.today()
    if 'estado_geral' in data:
        termo.estado_geral = (data.get('estado_geral') or '')[:200] or None
    if 'observacoes' in data:
        termo.observacoes = (data.get('observacoes') or '') or None
    if 'local_assinatura' in data:
        termo.local_assinatura = (data.get('local_assinatura') or '')[:120] or None
    termo.gestor_nome = (data.get('gestor_nome') or '')[:120] or None
    if 'acessorios' in data or data.get('acessorios') is not None:
        termo.acessorios_json = json.dumps(
            acessorios_from_payload(data.get('acessorios')), ensure_ascii=False
        )
    if usuario and not termo.enviado_por_id:
        termo.enviado_por_id = usuario.id
    return termo


def _obter_termo_editavel(eq):
    atual = eq.termo_atual()
    if atual and atual.status != 'assinado':
        atual.token = atual.token or novo_token_termo()
        return atual
    termo = EquipamentoTermo(
        equipamento_id=eq.id,
        token=novo_token_termo(),
        status='pendente',
        responsavel_nome='A definir',
    )
    db.session.add(termo)
    return termo


def salvar_termo(eq, data, usuario):
    """Grava responsável e acessórios sem enviar e-mail/WhatsApp."""
    nome, email, telefone, user_resp = _resolver_responsavel(data)
    atual = eq.termo_atual()
    if atual:
        termo = atual
        termo.token = termo.token or novo_token_termo()
    else:
        termo = _obter_termo_editavel(eq)
    _aplicar_dados_termo(eq, termo, data, usuario, nome, email, telefone, user_resp)
    if not termo.status:
        termo.status = 'pendente'
    db.session.commit()
    return termo


def criar_ou_reenviar_termo(eq, data, usuario, link_builder):
    nome, email, telefone, user_resp = _resolver_responsavel(data)
    if not nome:
        raise ValueError('Informe o nome do responsável.')
    termo = _obter_termo_editavel(eq)
    _aplicar_dados_termo(eq, termo, data, usuario, nome, email, telefone, user_resp)
    termo.status = 'enviado'
    termo.enviado_em = now_brasilia()
    termo.enviado_por_id = usuario.id if usuario else None
    db.session.flush()
    link = link_builder(termo.token)
    canais = []
    erros = []
    enviar_email_flag = data.get('enviar_email') not in (False, 0, '0', 'false')
    enviar_wa_flag = data.get('enviar_whatsapp') in (True, 1, '1', 'on', 'true', 'sim')
    if enviar_email_flag and email:
        try:
            from email_service import enviar_termo_responsabilidade
            enviar_termo_responsabilidade(
                email, nome, eq.nome_equipamento, link, eq.tipo_equipamento_norm()
            )
            canais.append('email')
        except Exception as exc:
            erros.append(f'E-mail: {exc}')
    if enviar_wa_flag and telefone:
        try:
            from whatsapp_pesagem import send_whatsapp
            msg = (
                f'Olá, {nome}. Segue o Termo de Responsabilidade do equipamento '
                f'{eq.nome_equipamento}. Abra o link para assinar:\n{link}'
            )
            res = send_whatsapp(telefone, msg)
            if res.get('ok'):
                canais.append('whatsapp')
            else:
                erros.append(f'WhatsApp: {res.get("error") or "falha ao enviar"}')
        except Exception as exc:
            erros.append(f'WhatsApp: {exc}')
    if not canais and not erros:
        canais.append('link')
    termo.canal_envio = ','.join(canais) if canais else None
    db.session.commit()
    return termo, link, canais, erros


def salvar_assinatura_png(token, data_url):
    m = re.match(r'^data:image/png;base64,([A-Za-z0-9+/=\s]+)$', (data_url or '').strip())
    if not m:
        raise ValueError('Assinatura inválida. Desenhe no campo e tente de novo.')
    try:
        raw = base64.b64decode(m.group(1), validate=True)
    except Exception as exc:
        raise ValueError('Assinatura inválida.') from exc
    if len(raw) < 64 or len(raw) > 500_000:
        raise ValueError('Assinatura inválida ou muito grande.')
    if raw[:8] != _PNG_MAGIC:
        raise ValueError('Assinatura inválida.')
    _UPLOAD_TERMOS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[^A-Za-z0-9_-]', '', token)[:40] or 'termo'
    fname = f'{safe}.png'
    dest = _UPLOAD_TERMOS / fname
    dest.write_bytes(raw)
    return f'uploads/termos/{fname}'


def assinar_termo(termo, payload):
    if termo.status == 'assinado':
        raise ValueError('Este termo já foi assinado.')
    nome = (payload.get('responsavel_nome') or termo.responsavel_nome or '').strip()
    if not nome:
        raise ValueError('Informe o nome do responsável.')
    assinatura = payload.get('assinatura') or ''
    path = salvar_assinatura_png(termo.token, assinatura)
    termo.responsavel_nome = nome[:120]
    termo.responsavel_setor = (payload.get('responsavel_setor') or termo.responsavel_setor or '')[:80] or None
    termo.responsavel_cargo = (payload.get('responsavel_cargo') or termo.responsavel_cargo or '')[:80] or None
    termo.responsavel_matricula = (payload.get('responsavel_matricula') or termo.responsavel_matricula or '')[:40] or None
    termo.estado_geral = (payload.get('estado_geral') or termo.estado_geral or '')[:200] or None
    termo.observacoes = payload.get('observacoes') if payload.get('observacoes') is not None else termo.observacoes
    termo.local_assinatura = (payload.get('local_assinatura') or termo.local_assinatura or '')[:120] or None
    raw_entrega = (payload.get('data_entrega') or '').strip()
    if raw_entrega:
        try:
            termo.data_entrega = datetime.strptime(raw_entrega[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    if payload.get('acessorios'):
        termo.acessorios_json = json.dumps(
            acessorios_from_payload(payload.get('acessorios')), ensure_ascii=False
        )
    termo.assinatura_path = path
    termo.assinado_em = now_brasilia()
    termo.status = 'assinado'
    db.session.commit()
    return termo


def termo_para_api(termo, link=None):
    if not termo:
        return None
    return {
        'id': termo.id,
        'status': termo.status,
        'token': termo.token,
        'link': link,
        'responsavel_nome': termo.responsavel_nome or '',
        'responsavel_email': termo.responsavel_email or '',
        'responsavel_telefone': termo.responsavel_telefone or '',
        'responsavel_setor': termo.responsavel_setor or '',
        'responsavel_cargo': termo.responsavel_cargo or '',
        'responsavel_matricula': termo.responsavel_matricula or '',
        'responsavel_usuario_id': termo.responsavel_usuario_id,
        'eq_nome': termo.eq_nome or '',
        'eq_marca': termo.eq_marca or '',
        'eq_modelo': termo.eq_modelo or '',
        'eq_patrimonio': termo.eq_patrimonio or '',
        'eq_serie': termo.eq_serie or '',
        'eq_tipo': termo.tipo_norm(),
        'eq_tipo_label': termo.textos()['label'],
        'textos': termo.textos(),
        'sugeridos': acessorios_sugeridos(termo.tipo_norm()),
        'data_entrega': termo.data_entrega.strftime('%Y-%m-%d') if termo.data_entrega else None,
        'data_entrega_br': termo.data_entrega.strftime('%d/%m/%Y') if termo.data_entrega else None,
        'estado_geral': termo.estado_geral or '',
        'observacoes': termo.observacoes or '',
        'local_assinatura': termo.local_assinatura or '',
        'gestor_nome': termo.gestor_nome or '',
        'acessorios': termo.acessorios(),
        'assinado_em': termo.assinado_em.strftime('%d/%m/%Y %H:%M') if termo.assinado_em else None,
        'enviado_em': termo.enviado_em.strftime('%d/%m/%Y %H:%M') if termo.enviado_em else None,
        'assinatura_url': (
            f'/static/{termo.assinatura_path}' if termo.assinatura_path else None
        ),
        'entregue_por': termo.enviado_por.nome if termo.enviado_por else '',
    }


def _scheduler_loop(app):
    while True:
        time.sleep(max(30, _SCHEDULER_INTERVAL))
        try:
            with app.app_context():
                processar_preventivas()
        except Exception:
            LOG.exception('Erro no agendador de preventiva')


def start_preventiva_background(app):
    global _bg_started
    if app.config.get('TESTING'):
        return
    if os.environ.get('EQ_PREVENTIVA_DISABLE', '').strip() in ('1', 'true', 'yes'):
        return
    with _bg_lock:
        if _bg_started:
            return
        _bg_started = True
    t = threading.Thread(target=_scheduler_loop, args=(app,), name='eq-preventiva', daemon=True)
    t.start()
