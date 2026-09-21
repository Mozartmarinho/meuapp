"""Atendimento WhatsApp da Gestão de Chamados (cadastro + abertura de ticket)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from models import (
    Chamado,
    ChamadoMensagem,
    ChamadoSetor,
    ChamadoTecnico,
    Cliente,
    Equipamento,
    MesaServico,
    Usuario,
    WhatsAppChamadoConfig,
    WhatsAppChamadoLog,
    WhatsAppChamadoUsuario,
    aplicar_automacoes,
    contrato_vigente,
    db,
    mesa_padrao,
    mesas_ativas,
)
from whatsapp_pesagem import normalizar_telefone, telefone_valido

logger = logging.getLogger('whatsapp_chamados')

ETAPA_NOVO = 'novo'
ETAPA_NOME = 'wait_nome'
ETAPA_CLIENTE = 'wait_cliente'
ETAPA_SETOR = 'wait_setor'
ETAPA_CONFIRM = 'wait_confirm'
ETAPA_EDIT_MENU = 'edit_menu'
ETAPA_EDIT_CLIENTE = 'edit_cliente'
ETAPA_EDIT_SETOR = 'edit_setor'
ETAPA_MESA = 'wait_mesa'
ETAPA_PATRIMONIO = 'wait_patrimonio'
ETAPA_IDLE = 'idle'
FUNCOES_AVISO_ABERTURA = ('supervisor', 'gestor')
MAX_DEFEITO_WHATSAPP = 400


def saudacao(agora=None):
    if agora is None:
        try:
            from zoneinfo import ZoneInfo
            agora = datetime.now(ZoneInfo('America/Sao_Paulo'))
        except Exception:
            agora = datetime.now()
    hora = agora.hour
    if 5 <= hora < 12:
        return 'Bom dia'
    if 12 <= hora < 18:
        return 'Boa tarde'
    return 'Boa noite'


def config_ativa():
    row = WhatsAppChamadoConfig.query.order_by(WhatsAppChamadoConfig.id.asc()).first()
    if not row:
        row = WhatsAppChamadoConfig(ativo=True)
        db.session.add(row)
        db.session.commit()
    return row


def listar_clientes():
    return (
        Cliente.query.filter(
            db.or_(Cliente.habilitado_chamados.is_(True), Cliente.habilitado_chamados.is_(None)),
            db.or_(Cliente.ativo.is_(True), Cliente.ativo.is_(None)),
        )
        .order_by(Cliente.nome.asc())
        .all()
    )


def listar_setores():
    return ChamadoSetor.query.filter_by(ativo=True).order_by(ChamadoSetor.nome.asc()).all()


def listar_mesas():
    return mesas_ativas()


def mesa_escolhida(usuario):
    ids = ler_lista(usuario, 'mesa_escolhida')
    if not ids:
        return mesa_padrao()
    mesa = MesaServico.query.get(ids[0])
    if mesa and mesa.ativa:
        return mesa
    return mesa_padrao()


def parse_indice(texto, maximo):
    raw = (texto or '').strip()
    match = re.match(r'^\s*(\d+)\b', raw)
    if not match:
        return None
    numero = int(match.group(1))
    if 1 <= numero <= maximo:
        return numero
    return None


def parse_sim_nao(texto):
    raw = (texto or '').strip().lower()
    if raw in ('1', 'sim', 's', 'yes'):
        return 1
    if raw in ('2', 'nao', 'não', 'n', 'no'):
        return 2
    return parse_indice(texto, 2)


def gravar_lista(usuario, tipo, ids):
    usuario.lista_json = json.dumps({'tipo': tipo, 'ids': ids})


def ler_lista(usuario, tipo):
    try:
        data = json.loads(usuario.lista_json or '{}')
    except (TypeError, ValueError):
        return []
    if data.get('tipo') != tipo:
        return []
    return [int(x) for x in (data.get('ids') or []) if str(x).isdigit()]


def formatar_lista(titulo, itens):
    linhas = [titulo]
    for i, nome in enumerate(itens, start=1):
        linhas.append('%s - %s' % (i, nome))
    return '\n'.join(linhas)


def primeiro_nome(nome):
    partes = (nome or '').strip().split()
    return partes[0] if partes else ''


def _log(usuario, direcao, texto):
    db.session.add(WhatsAppChamadoLog(
        usuario_id=usuario.id if usuario else None,
        telefone=usuario.telefone if usuario else None,
        direcao=direcao,
        texto=(texto or '')[:4000],
    ))


def obter_usuario(telefone):
    digits = normalizar_telefone(telefone)
    if not digits:
        return None
    row = WhatsAppChamadoUsuario.query.filter_by(telefone=digits).first()
    if not row:
        row = WhatsAppChamadoUsuario(telefone=digits, etapa=ETAPA_NOVO)
        db.session.add(row)
        db.session.flush()
    return row


def _tecnico_bot():
    return (
        Usuario.query.filter_by(is_master=True, ativo=True).first()
        or Usuario.query.filter_by(tipo='admin', ativo=True).first()
        or Usuario.query.filter_by(ativo=True).order_by(Usuario.id.asc()).first()
    )


def abrir_ticket(usuario, patrimonio):
    tecnico = _tecnico_bot()
    if not tecnico:
        return None, 'Não há usuário no sistema para assumir o ticket.'
    codigo = (patrimonio or '').strip()
    if not codigo:
        return None, None
    eq = Equipamento.query.filter_by(patrimonio=codigo).first()
    if not eq:
        eq = Equipamento.query.filter(Equipamento.patrimonio.ilike(codigo)).first()
    if not eq:
        return None, None
    mesa = mesa_escolhida(usuario)
    numero = _gerar_os()
    descricao = (
        'Abertura via WhatsApp para manutenção de equipamentos da São Geraldo Service.\n'
        'Solicitante: %s\n'
        'Telefone: %s\n'
        'Unidade: %s\n'
        'Setor: %s\n'
        'Mesa de serviço: %s\n'
        'Patrimônio: %s'
        % (
            usuario.nome or '',
            usuario.telefone,
            usuario.cliente.nome if usuario.cliente else '',
            usuario.setor.nome if usuario.setor else '',
            mesa.nome if mesa else '',
            codigo,
        )
    )
    if eq:
        descricao += '\nEquipamento: %s' % (eq.nome_equipamento or '')
    chamado = Chamado(
        numero_chamado=numero,
        cliente_id=usuario.cliente_id,
        tipo_servico='Manutenção',
        descricao=descricao,
        status='Pendente',
        prioridade='Normal',
        observacoes='Origem: WhatsApp',
        tecnico_id=tecnico.id,
        mesa_id=mesa.id if mesa else None,
        setor_tecnico_id=usuario.setor_id,
        setor_destino=usuario.setor.nome if usuario.setor else None,
        patrimonio=codigo,
        equipamento_id=eq.id if eq and eq.cliente_id == usuario.cliente_id else None,
        equipamento=(eq.nome_equipamento if eq else None),
    )
    vig = contrato_vigente(usuario.cliente_id)
    if vig:
        chamado.contrato_id = vig.id
    db.session.add(chamado)
    db.session.flush()
    aplicar_automacoes(chamado, 'criar', tecnico)
    db.session.add(ChamadoMensagem(
        chamado_id=chamado.id,
        usuario_id=tecnico.id,
        texto='Ticket aberto automaticamente pelo WhatsApp.',
        canal='WhatsApp',
        visivel_cliente=True,
        enviada=True,
        origem='whatsapp',
    ))
    return chamado, None


def _gerar_os():
    import random
    import string
    for _ in range(12):
        numero = 'OS' + ''.join(random.choices(string.digits, k=6))
        if not Chamado.query.filter_by(numero_chamado=numero).first():
            return numero
    return 'OS' + ''.join(random.choices(string.digits, k=6))


def _texto_ou_traco(valor):
    texto = ' '.join(str(valor or '').split())
    return texto or '—'


def montar_mensagem_abertura(chamado):
    unidade = chamado.cliente.nome if getattr(chamado, 'cliente', None) else ''
    setor = ''
    if getattr(chamado, 'setor_tecnico', None) and chamado.setor_tecnico.nome:
        setor = chamado.setor_tecnico.nome
    elif chamado.setor_destino:
        setor = chamado.setor_destino
    mesa = chamado.mesa.nome if getattr(chamado, 'mesa', None) else ''
    defeito = _texto_ou_traco(chamado.descricao)
    if len(defeito) > MAX_DEFEITO_WHATSAPP:
        defeito = defeito[: MAX_DEFEITO_WHATSAPP - 1] + '…'
    return (
        '*Abertura de chamado*\n'
        'Ticket: %s\n'
        'Unidade: %s\n'
        'Setor: %s\n'
        'Mesa de serviço: %s\n'
        'Patrimônio: %s\n'
        'Defeito: %s'
        % (
            _texto_ou_traco(chamado.numero_chamado),
            _texto_ou_traco(unidade),
            _texto_ou_traco(setor),
            _texto_ou_traco(mesa),
            _texto_ou_traco(chamado.patrimonio),
            defeito,
        )
    )


def destinos_aviso_abertura(chamado):
    rows = (
        ChamadoTecnico.query
        .filter(
            ChamadoTecnico.ativo == True,  # noqa: E712
            ChamadoTecnico.funcao.in_(FUNCOES_AVISO_ABERTURA),
        )
        .all()
    )
    setor_id = getattr(chamado, 'setor_tecnico_id', None)
    mesa_id = getattr(chamado, 'mesa_id', None)
    destinos = []
    vistos = set()
    for row in rows:
        phone = normalizar_telefone(row.whatsapp)
        if not telefone_valido(phone):
            continue
        mesas_ids = set(getattr(row, 'mesas_ids', None) or [])
        if mesas_ids:
            if mesa_id and mesa_id not in mesas_ids:
                continue
        elif setor_id and row.setor_id and row.setor_id != setor_id:
            continue
        if phone in vistos:
            continue
        vistos.add(phone)
        destinos.append(row)
    return destinos


def notificar_abertura_chamado(chamado, sender=None):
    """Avisa supervisores e gestores no WhatsApp. Não interrompe a abertura do ticket."""
    if not chamado:
        return []
    from whatsapp_pesagem import send_whatsapp
    sender = sender or send_whatsapp
    texto = montar_mensagem_abertura(chamado)
    enviados = []
    for dest in destinos_aviso_abertura(chamado):
        try:
            res = sender(dest.whatsapp, texto) or {}
            if res.get('ok'):
                enviados.append(normalizar_telefone(dest.whatsapp))
            else:
                logger.warning(
                    'WhatsApp abertura %s para %s: %s',
                    chamado.numero_chamado,
                    dest.whatsapp,
                    res.get('error') or 'falha',
                )
        except Exception as exc:
            logger.warning(
                'WhatsApp abertura %s para %s: %s',
                getattr(chamado, 'numero_chamado', ''),
                getattr(dest, 'whatsapp', ''),
                exc,
            )
    return enviados


def _pedir_clientes(usuario):
    clientes = listar_clientes()
    if not clientes:
        usuario.etapa = ETAPA_CLIENTE
        return ['Não há unidades cadastradas no sistema. Peça ao suporte para cadastrar um cliente.']
    gravar_lista(usuario, 'cliente', [c.id for c in clientes])
    usuario.etapa = ETAPA_CLIENTE
    return [formatar_lista(
        'Qual é a sua unidade? Responda com o número da lista:',
        [c.nome for c in clientes],
    )]


def _pedir_setores(usuario):
    setores = listar_setores()
    if not setores:
        usuario.etapa = ETAPA_SETOR
        return ['Não há setores cadastrados no sistema. Peça ao suporte para cadastrar um setor.']
    gravar_lista(usuario, 'setor', [s.id for s in setores])
    usuario.etapa = ETAPA_SETOR
    return [formatar_lista(
        'Qual é o seu setor? Responda com o número da lista:',
        [s.nome for s in setores],
    )]


def _pedir_mesas(usuario):
    mesas = listar_mesas()
    if not mesas:
        usuario.etapa = ETAPA_PATRIMONIO
        return [_msg_patrimonio()]
    gravar_lista(usuario, 'mesa', [m.id for m in mesas])
    usuario.etapa = ETAPA_MESA
    return [formatar_lista(
        'Qual mesa de serviço deve atender este chamado? Responda com o número da lista:',
        [m.nome for m in mesas],
    )]


def _msg_confirmacao(usuario):
    nome = primeiro_nome(usuario.nome) or (usuario.nome or '')
    cliente = usuario.cliente.nome if usuario.cliente else '—'
    setor = usuario.setor.nome if usuario.setor else '—'
    return (
        '%s, %s. Verifiquei no sistema o seu cadastro. '
        'Você ainda continua no "%s" e no setor "%s"? '
        'Se sim, envie 1. Se não, envie 2.'
        % (saudacao(), nome, cliente, setor)
    )


def _msg_patrimonio():
    return (
        'Vamos continuar com a abertura de ticket para manutenção de equipamentos '
        'da São Geraldo Service. Por favor me informe o número de patrimônio.'
    )


def _vincular_por_indice(usuario, texto, tipo):
    ids = ler_lista(usuario, tipo)
    if not ids:
        if tipo == 'cliente':
            return None, _pedir_clientes(usuario)
        return None, _pedir_setores(usuario)
    indice = parse_indice(texto, len(ids))
    if not indice:
        return None, ['Não entendi. Envie só o número da lista (1 a %s).' % len(ids)]
    alvo_id = ids[indice - 1]
    if tipo == 'cliente':
        cli = Cliente.query.get(alvo_id)
        if not cli:
            return None, ['Unidade inválida.'] + _pedir_clientes(usuario)
        usuario.cliente_id = cli.id
        return cli, None
    setor = ChamadoSetor.query.get(alvo_id)
    if not setor:
        return None, ['Setor inválido.'] + _pedir_setores(usuario)
    usuario.setor_id = setor.id
    return setor, None


def _vincular_mesa(usuario, texto):
    ids = ler_lista(usuario, 'mesa')
    if not ids:
        return None, _pedir_mesas(usuario)
    indice = parse_indice(texto, len(ids))
    if not indice:
        return None, ['Não entendi. Envie só o número da lista (1 a %s).' % len(ids)]
    mesa = MesaServico.query.get(ids[indice - 1])
    if not mesa or not mesa.ativa:
        return None, ['Mesa de serviço inválida.'] + _pedir_mesas(usuario)
    gravar_lista(usuario, 'mesa_escolhida', [mesa.id])
    return mesa, None


def process_inbound(telefone, texto, sender=None, agora=None):
    """Processa uma mensagem recebida no número logado. Retorna as respostas enviadas."""
    replies = []

    def send(msg):
        if not msg:
            return
        replies.append(msg)
        _log(usuario, 'out', msg)
        if sender:
            sender(telefone, msg)

    cfg = config_ativa()
    if not cfg.ativo:
        return {'ok': True, 'ignored': True, 'replies': []}

    usuario = obter_usuario(telefone)
    if not usuario:
        return {'ok': False, 'error': 'Telefone inválido', 'replies': []}

    texto = (texto or '').strip()
    _log(usuario, 'in', texto)
    usuario.atualizado_em = datetime.utcnow()

    if not texto:
        send('Por favor envie a resposta em texto.')
        db.session.commit()
        return {'ok': True, 'replies': replies}

    etapa = usuario.etapa or ETAPA_NOVO

    if not usuario.completo() and etapa in (ETAPA_NOVO, ETAPA_IDLE, ETAPA_CONFIRM, ''):
        usuario.etapa = ETAPA_NOME
        send(
            '%s, verifiquei no nosso sistema que seu número ainda não está cadastrado. '
            'Poderia por favor informar seu nome completo?'
            % saudacao(agora)
        )
        db.session.commit()
        return {'ok': True, 'replies': replies}

    if usuario.completo() and etapa in (ETAPA_NOVO, ETAPA_IDLE, '', ETAPA_CONFIRM):
        if etapa != ETAPA_CONFIRM:
            usuario.etapa = ETAPA_CONFIRM
            send(_msg_confirmacao(usuario))
            db.session.commit()
            return {'ok': True, 'replies': replies}

    if etapa == ETAPA_NOME:
        if len(texto) < 3:
            send('Informe seu nome completo, por favor.')
        else:
            usuario.nome = texto[:120]
            for msg in _pedir_clientes(usuario):
                send(msg)
        db.session.commit()
        return {'ok': True, 'replies': replies}

    if etapa in (ETAPA_CLIENTE, ETAPA_EDIT_CLIENTE):
        cli, extra = _vincular_por_indice(usuario, texto, 'cliente')
        if extra:
            for msg in extra:
                send(msg)
        elif etapa == ETAPA_EDIT_CLIENTE:
            usuario.etapa = ETAPA_CONFIRM
            send('Unidade atualizada para %s.' % cli.nome)
            send(_msg_confirmacao(usuario))
        else:
            for msg in _pedir_setores(usuario):
                send(msg)
        db.session.commit()
        return {'ok': True, 'replies': replies}

    if etapa in (ETAPA_SETOR, ETAPA_EDIT_SETOR):
        setor, extra = _vincular_por_indice(usuario, texto, 'setor')
        if extra:
            for msg in extra:
                send(msg)
        elif etapa == ETAPA_EDIT_SETOR:
            usuario.etapa = ETAPA_CONFIRM
            send('Setor atualizado para %s.' % setor.nome)
            send(_msg_confirmacao(usuario))
        else:
            send(
                'Cadastro salvo: %s, unidade %s, setor %s.'
                % (usuario.nome, usuario.cliente.nome if usuario.cliente else '', setor.nome)
            )
            for msg in _pedir_mesas(usuario):
                send(msg)
        db.session.commit()
        return {'ok': True, 'replies': replies}

    if etapa == ETAPA_CONFIRM:
        escolha = parse_sim_nao(texto)
        if escolha == 1:
            for msg in _pedir_mesas(usuario):
                send(msg)
        elif escolha == 2:
            usuario.etapa = ETAPA_EDIT_MENU
            send(
                'Para alterar o cadastro, envie:\n'
                '1 - Unidade (cliente)\n'
                '2 - Setor\n'
                '0 - Voltar'
            )
        else:
            send('Envie 1 para sim ou 2 para não.')
        db.session.commit()
        return {'ok': True, 'replies': replies}

    if etapa == ETAPA_EDIT_MENU:
        escolha = parse_indice(texto, 2)
        if texto.strip() == '0' or parse_indice(texto, 9) == 0:
            usuario.etapa = ETAPA_CONFIRM
            send(_msg_confirmacao(usuario))
        elif escolha == 1:
            for msg in _pedir_clientes(usuario):
                send(msg)
            usuario.etapa = ETAPA_EDIT_CLIENTE
        elif escolha == 2:
            for msg in _pedir_setores(usuario):
                send(msg)
            usuario.etapa = ETAPA_EDIT_SETOR
        else:
            send('Envie 1 para unidade, 2 para setor ou 0 para voltar.')
        db.session.commit()
        return {'ok': True, 'replies': replies}

    if etapa == ETAPA_MESA:
        mesa, extra = _vincular_mesa(usuario, texto)
        if extra:
            for msg in extra:
                send(msg)
        else:
            usuario.etapa = ETAPA_PATRIMONIO
            send('Mesa de serviço: %s.' % mesa.nome)
            send(_msg_patrimonio())
        db.session.commit()
        return {'ok': True, 'replies': replies}

    if etapa == ETAPA_PATRIMONIO:
        chamado, erro = abrir_ticket(usuario, texto)
        if erro:
            send(erro)
        elif not chamado:
            send('Não encontrei o patrimônio "%s". Confira o número e envie de novo.' % texto)
        else:
            usuario.etapa = ETAPA_IDLE
            send(
                'Ticket %s aberto para manutenção de equipamentos da São Geraldo Service, '
                'vinculado a %s / %s, mesa %s.'
                % (
                    chamado.numero_chamado,
                    usuario.cliente.nome if usuario.cliente else '—',
                    usuario.setor.nome if usuario.setor else '—',
                    chamado.mesa.nome if getattr(chamado, 'mesa', None) else '—',
                )
            )
        db.session.commit()
        if chamado:
            try:
                notificar_abertura_chamado(chamado)
            except Exception as exc:
                logger.warning('Falha ao notificar abertura WhatsApp: %s', exc)
        return {'ok': True, 'replies': replies, 'chamado_id': getattr(chamado, 'id', None)}

    usuario.etapa = ETAPA_CONFIRM if usuario.completo() else ETAPA_NOME
    if usuario.completo():
        send(_msg_confirmacao(usuario))
    else:
        send(
            '%s, verifiquei no nosso sistema que seu número ainda não está cadastrado. '
            'Poderia por favor informar seu nome completo?'
            % saudacao(agora)
        )
    db.session.commit()
    return {'ok': True, 'replies': replies}
