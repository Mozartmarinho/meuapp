"""Acesso remoto São Geraldo: número do equipamento, senha e sessão."""
from __future__ import annotations

import hashlib
import secrets
import threading
from datetime import timedelta

from password_utils import check_password_hash, generate_password_hash
from models import db, now_brasilia

ONLINE_SEGUNDOS = 15
SESSAO_OCIOSA_SEGUNDOS = 25
SENHA_MIN = 4
FILA_MAX = 40
FRAME_MAX = 2_000_000

_lock = threading.Lock()
_frames = {}
_filas = {}


class AcessoRemotoEquipamento(db.Model):
    __tablename__ = 'acesso_remoto_equipamentos'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(12), unique=True, nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False, default='Computador')
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255))
    ultimo_visto = db.Column(db.DateTime)
    criado_em = db.Column(db.DateTime, default=now_brasilia)


class AcessoRemotoSessao(db.Model):
    __tablename__ = 'acesso_remoto_sessoes'

    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(
        db.Integer, db.ForeignKey('acesso_remoto_equipamentos.id'), nullable=False, index=True
    )
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    ativa = db.Column(db.Boolean, default=True, nullable=False)
    criada_em = db.Column(db.DateTime, default=now_brasilia)
    ultimo_viewer = db.Column(db.DateTime, default=now_brasilia)
    equipamento = db.relationship('AcessoRemotoEquipamento')


def formatar_numero(numero):
    digitos = ''.join(ch for ch in (numero or '') if ch.isdigit())
    if len(digitos) != 9:
        return numero or ''
    return '%s %s %s' % (digitos[:3], digitos[3:6], digitos[6:])


def normalizar_numero(numero):
    digitos = ''.join(ch for ch in (numero or '') if ch.isdigit())
    return digitos if len(digitos) == 9 else ''


def _hash_token(token):
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()


def _novo_numero():
    for _ in range(30):
        numero = str(secrets.randbelow(900_000_000) + 100_000_000)
        if not AcessoRemotoEquipamento.query.filter_by(numero=numero).first():
            return numero
    raise RuntimeError('Não foi possível gerar a numeração.')


def equipamento_por_token(token):
    if not token:
        return None
    return AcessoRemotoEquipamento.query.filter_by(token_hash=_hash_token(token)).first()


def online(equipamento, agora=None):
    if not equipamento or not equipamento.ultimo_visto:
        return False
    agora = agora or now_brasilia()
    return (agora - equipamento.ultimo_visto).total_seconds() <= ONLINE_SEGUNDOS


def registrar_equipamento(nome, token=None):
    nome = (nome or '').strip()[:120] or 'Computador'
    if token:
        atual = equipamento_por_token(token)
        if atual:
            atual.nome = nome
            atual.ultimo_visto = now_brasilia()
            db.session.commit()
            return atual, token
    token = secrets.token_urlsafe(32)
    row = AcessoRemotoEquipamento(
        numero=_novo_numero(),
        nome=nome,
        token_hash=_hash_token(token),
        ultimo_visto=now_brasilia(),
        criado_em=now_brasilia(),
    )
    db.session.add(row)
    db.session.commit()
    return row, token


def definir_senha(token, senha):
    row = equipamento_por_token(token)
    if not row:
        raise PermissionError('Programa não reconhecido. Abra de novo para gerar o número.')
    senha = (senha or '').strip()
    if len(senha) < SENHA_MIN:
        raise ValueError('A senha precisa ter pelo menos %s caracteres.' % SENHA_MIN)
    row.senha_hash = generate_password_hash(senha)
    row.ultimo_visto = now_brasilia()
    db.session.commit()
    return row


def _encerrar_ociosas(equipamento_id=None):
    agora = now_brasilia()
    limite = agora - timedelta(seconds=SESSAO_OCIOSA_SEGUNDOS)
    q = AcessoRemotoSessao.query.filter(
        AcessoRemotoSessao.ativa == True,  # noqa: E712
        AcessoRemotoSessao.ultimo_viewer < limite,
    )
    if equipamento_id:
        q = q.filter(AcessoRemotoSessao.equipamento_id == equipamento_id)
    mudou = False
    for sessao in q.all():
        sessao.ativa = False
        mudou = True
        with _lock:
            _frames.pop(sessao.id, None)
    if mudou:
        db.session.commit()


def sessao_ativa(equipamento):
    if not equipamento:
        return None
    _encerrar_ociosas(equipamento.id)
    return (
        AcessoRemotoSessao.query.filter_by(equipamento_id=equipamento.id, ativa=True)
        .order_by(AcessoRemotoSessao.id.desc())
        .first()
    )


def pulso(token):
    row = equipamento_por_token(token)
    if not row:
        raise PermissionError('Programa não reconhecido.')
    row.ultimo_visto = now_brasilia()
    db.session.commit()
    sessao = sessao_ativa(row)
    with _lock:
        comandos = _filas.pop(row.id, [])
    return {
        'ok': True,
        'numero': row.numero,
        'numero_formatado': formatar_numero(row.numero),
        'senha_definida': bool(row.senha_hash),
        'sessao_id': sessao.id if sessao else None,
        'comandos': comandos,
    }


def guardar_tela(token, sessao_id, blob):
    row = equipamento_por_token(token)
    if not row:
        raise PermissionError('Programa não reconhecido.')
    if not blob or len(blob) > FRAME_MAX:
        raise ValueError('Imagem da tela inválida.')
    try:
        sessao_id = int(sessao_id)
    except (TypeError, ValueError):
        raise ValueError('Sessão inválida.')
    sessao = AcessoRemotoSessao.query.get(sessao_id)
    if not sessao or not sessao.ativa or sessao.equipamento_id != row.id:
        return False
    row.ultimo_visto = now_brasilia()
    db.session.commit()
    with _lock:
        _frames[sessao.id] = blob
        comandos = _filas.pop(row.id, [])
    return comandos


def conectar(numero, senha, usuario_id):
    digitos = normalizar_numero(numero)
    if not digitos:
        raise ValueError('Informe o número do equipamento, com 9 dígitos.')
    row = AcessoRemotoEquipamento.query.filter_by(numero=digitos).first()
    if not row:
        raise ValueError('Nenhum equipamento com esse número.')
    if not online(row):
        raise ValueError('Equipamento offline. O programa precisa estar aberto ao lado do relógio.')
    if not row.senha_hash:
        raise ValueError('Ainda não há senha neste equipamento. Crie a senha no programa instalado.')
    if not check_password_hash(row.senha_hash, (senha or '').strip()):
        raise ValueError('Senha incorreta.')
    for antiga in AcessoRemotoSessao.query.filter_by(equipamento_id=row.id, ativa=True).all():
        antiga.ativa = False
        with _lock:
            _frames.pop(antiga.id, None)
    agora = now_brasilia()
    sessao = AcessoRemotoSessao(
        equipamento_id=row.id,
        usuario_id=usuario_id,
        ativa=True,
        criada_em=agora,
        ultimo_viewer=agora,
    )
    db.session.add(sessao)
    db.session.commit()
    return sessao


def tocar_viewer(sessao):
    if not sessao or not sessao.ativa:
        return None
    sessao.ultimo_viewer = now_brasilia()
    db.session.commit()
    with _lock:
        return _frames.get(sessao.id)


def enfileirar_comando(sessao, comando):
    if not sessao or not sessao.ativa:
        raise ValueError('A sessão não está mais ativa.')
    tipo = (comando or {}).get('tipo')
    if tipo not in ('mouse', 'tecla'):
        raise ValueError('Comando inválido.')
    limpo = {'tipo': tipo}
    if tipo == 'mouse':
        acao = (comando.get('acao') or '').strip()
        if acao not in ('move', 'down', 'up', 'wheel'):
            raise ValueError('Ação do mouse inválida.')
        limpo['acao'] = acao
        limpo['x'] = _frac(comando.get('x'))
        limpo['y'] = _frac(comando.get('y'))
        botao = (comando.get('botao') or 'left').strip()
        limpo['botao'] = botao if botao in ('left', 'right') else 'left'
        try:
            limpo['delta'] = int(comando.get('delta') or 0)
        except (TypeError, ValueError):
            limpo['delta'] = 0
        limpo['delta'] = max(-600, min(600, limpo['delta']))
    else:
        code = str(comando.get('code') or '')[:40]
        key = str(comando.get('key') or '')[:20]
        if not code and not key:
            raise ValueError('Tecla inválida.')
        limpo['code'] = code
        limpo['key'] = key
        limpo['ctrl'] = bool(comando.get('ctrl'))
        limpo['alt'] = bool(comando.get('alt'))
        limpo['shift'] = bool(comando.get('shift'))
    sessao.ultimo_viewer = now_brasilia()
    db.session.commit()
    with _lock:
        fila = _filas.setdefault(sessao.equipamento_id, [])
        fila.append(limpo)
        if len(fila) > FILA_MAX:
            del fila[: len(fila) - FILA_MAX]
    return limpo


def encerrar_sessao(sessao):
    if not sessao:
        return
    sessao.ativa = False
    db.session.commit()
    with _lock:
        _frames.pop(sessao.id, None)
        _filas.pop(sessao.equipamento_id, None)


def _frac(valor):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if n < 0:
        return 0.0
    if n > 1:
        return 1.0
    return n


def listar_equipamentos():
    _encerrar_ociosas()
    agora = now_brasilia()
    rows = AcessoRemotoEquipamento.query.order_by(AcessoRemotoEquipamento.ultimo_visto.desc()).all()
    saida = []
    for row in rows:
        sessao = (
            AcessoRemotoSessao.query.filter_by(equipamento_id=row.id, ativa=True)
            .order_by(AcessoRemotoSessao.id.desc())
            .first()
        )
        visto = row.ultimo_visto.strftime('%d/%m/%Y %H:%M') if row.ultimo_visto else '—'
        saida.append({
            'id': row.id,
            'numero': row.numero,
            'numero_formatado': formatar_numero(row.numero),
            'nome': row.nome,
            'online': online(row, agora),
            'senha_definida': bool(row.senha_hash),
            'em_atendimento': bool(sessao),
            'ultimo_visto': visto,
        })
    return saida
