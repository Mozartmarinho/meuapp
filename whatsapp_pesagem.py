"""WhatsApp da pesagem: totais do dia, QR (bridge Node) e envio agendado."""
from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path

import requests
from sqlalchemy import func

from models import db
from models_pesagem import PesagemLeitura, PesagemWhatsAppDestino, PesagemWhatsAppEnvio

logger = logging.getLogger('whatsapp_pesagem')

BRIDGE_DIR = Path(__file__).resolve().parent / 'whatsapp_bridge'
BRIDGE_PORT = int(os.environ.get('PESAGEM_WA_BRIDGE_PORT', '31085'))
BRIDGE_HOST = os.environ.get('PESAGEM_WA_BRIDGE_HOST', '127.0.0.1')
BRIDGE_URL = f'http://{BRIDGE_HOST}:{BRIDGE_PORT}'
SCHEDULER_INTERVAL = int(os.environ.get('PESAGEM_WA_SCHEDULER_SEC', '20'))

_bg_lock = threading.Lock()
_bg_started = False


def formatar_kg(valor):
    try:
        num = float(valor or 0)
    except (TypeError, ValueError):
        num = 0.0
    return ('%.3f' % num).replace('.', ',') + ' kg'


def normalizar_telefone(raw):
    digits = ''.join(ch for ch in str(raw or '') if ch.isdigit())
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('0'):
        digits = digits[1:]
    if 10 <= len(digits) <= 11:
        digits = '55' + digits
    return digits


def telefone_valido(raw):
    digits = normalizar_telefone(raw)
    return 12 <= len(digits) <= 15


def parse_hora(value):
    text = str(value or '').strip()
    if not text:
        return None
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def peso_bruto_expr():
    return func.coalesce(PesagemLeitura.peso_bruto, PesagemLeitura.peso, 0.0)


def totais_bruto_do_dia(dia=None):
    """Soma o peso bruto de cada cadastro no dia (ex.: 10 pesagens CCD → um total)."""
    dia = dia or date.today()
    inicio = datetime.combine(dia, dt_time.min)
    fim = datetime.combine(dia, dt_time.max).replace(microsecond=0)
    rows = (
        db.session.query(
            PesagemLeitura.cliente_id,
            PesagemLeitura.cliente_nome,
            func.sum(peso_bruto_expr()),
            func.count(PesagemLeitura.id),
        )
        .filter(
            PesagemLeitura.data_leitura >= inicio,
            PesagemLeitura.data_leitura <= fim,
        )
        .group_by(PesagemLeitura.cliente_id, PesagemLeitura.cliente_nome)
        .order_by(PesagemLeitura.cliente_nome)
        .all()
    )
    totais = []
    for cliente_id, nome, soma, qtd in rows:
        label = (nome or '').strip() or 'Sem cadastro'
        totais.append({
            'cliente_id': cliente_id,
            'nome': label,
            'total': float(soma or 0),
            'quantidade': int(qtd or 0),
        })
    return totais


def montar_linhas_totais(totais):
    if not totais:
        return 'Nenhuma pesagem registrada neste dia.'
    linhas = []
    for item in totais:
        linhas.append('%s --- total %s' % (item['nome'], formatar_kg(item['total'])))
    return '\n'.join(linhas)


def montar_mensagem(template, totais=None, dia=None):
    dia = dia or date.today()
    totais = totais if totais is not None else totais_bruto_do_dia(dia)
    cabeca = (template or '').strip()
    corpo = montar_linhas_totais(totais)
    if cabeca:
        return cabeca + '\n\n' + corpo
    return corpo


def _port_open(host, port, timeout=0.4):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _which_node():
    return shutil.which('node') or shutil.which('nodejs')


def _which_npm():
    return shutil.which('npm')


def ensure_bridge_installed():
    if (BRIDGE_DIR / 'node_modules' / '@whiskeysockets' / 'baileys').exists():
        return True
    npm = _which_npm()
    if not npm:
        return False
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [npm, 'install', '--omit=dev'],
            cwd=str(BRIDGE_DIR),
            capture_output=True,
            text=True,
            timeout=240,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning('npm install WhatsApp bridge falhou: %s', exc)
        return False
    if proc.returncode != 0:
        logger.warning('npm install WhatsApp bridge rc=%s: %s', proc.returncode, proc.stderr[-800:])
        return False
    return (BRIDGE_DIR / 'node_modules' / '@whiskeysockets' / 'baileys').exists()


def start_bridge_process():
    """Sobe o processo Node (QR + sessão) se a porta ainda não estiver em uso."""
    if _port_open(BRIDGE_HOST, BRIDGE_PORT):
        return True
    node = _which_node()
    if not node:
        return False
    if not ensure_bridge_installed():
        return False
    index_js = BRIDGE_DIR / 'index.js'
    if not index_js.is_file():
        return False
    (BRIDGE_DIR / 'auth').mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['PESAGEM_WA_BRIDGE_PORT'] = str(BRIDGE_PORT)
    env['PESAGEM_WA_BRIDGE_HOST'] = BRIDGE_HOST
    log_path = BRIDGE_DIR / 'bridge.log'
    try:
        log_f = open(log_path, 'a', encoding='utf-8')
        subprocess.Popen(
            [node, str(index_js)],
            cwd=str(BRIDGE_DIR),
            env=env,
            stdout=log_f,
            stderr=log_f,
            start_new_session=True,
        )
    except OSError as exc:
        logger.warning('Falha ao iniciar bridge WhatsApp: %s', exc)
        return False
    for _ in range(40):
        if _port_open(BRIDGE_HOST, BRIDGE_PORT):
            return True
        time.sleep(0.25)
    return _port_open(BRIDGE_HOST, BRIDGE_PORT)


def _disabled():
    return os.environ.get('PESAGEM_WA_DISABLE', '').strip().lower() in ('1', 'true', 'yes')


def _bridge_unavailable_reason():
    if _disabled():
        return 'WhatsApp desabilitado neste ambiente.'
    if not _which_node():
        return 'Instale o Node.js 18+ no servidor para o QR Code do WhatsApp.'
    if not (BRIDGE_DIR / 'index.js').is_file():
        return 'Arquivos da ponte WhatsApp não encontrados.'
    if not ensure_bridge_installed():
        return 'Não foi possível instalar a ponte WhatsApp (npm).'
    if not start_bridge_process():
        return 'A ponte WhatsApp não iniciou. Veja whatsapp_bridge/bridge.log.'
    return None


def _bridge_get(path, timeout=8):
    return requests.get(BRIDGE_URL + path, timeout=timeout)


def _bridge_post(path, payload=None, timeout=45):
    return requests.post(BRIDGE_URL + path, json=payload or {}, timeout=timeout)


def status_whatsapp(auto_start=True):
    reason = None
    if auto_start:
        reason = _bridge_unavailable_reason()
        if reason and not _port_open(BRIDGE_HOST, BRIDGE_PORT):
            return {
                'ok': True,
                'state': 'unavailable',
                'qr': None,
                'qr_image': None,
                'user': None,
                'error': reason,
            }
    try:
        resp = _bridge_get('/status')
        data = resp.json() if resp.content else {}
        data.setdefault('ok', resp.ok)
        return data
    except (requests.RequestException, ValueError) as exc:
        return {
            'ok': False,
            'state': 'unavailable',
            'qr': None,
            'qr_image': None,
            'user': None,
            'error': 'Ponte WhatsApp inacessível: %s' % exc,
        }


def logout_whatsapp():
    start_bridge_process()
    try:
        resp = _bridge_post('/logout', timeout=20)
        return resp.json() if resp.content else {'ok': resp.ok}
    except (requests.RequestException, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}


def send_whatsapp(telefone, texto):
    phone = normalizar_telefone(telefone)
    if not telefone_valido(phone):
        return {'ok': False, 'error': 'Telefone inválido'}
    texto = (texto or '').strip()
    if not texto:
        return {'ok': False, 'error': 'Mensagem vazia'}
    reason = _bridge_unavailable_reason()
    if reason and not _port_open(BRIDGE_HOST, BRIDGE_PORT):
        return {'ok': False, 'error': reason}
    st = status_whatsapp(auto_start=False)
    if st.get('state') != 'open':
        return {'ok': False, 'error': 'WhatsApp não está conectado. Leia o QR Code.'}
    try:
        resp = _bridge_post('/send', {'to': phone, 'text': texto}, timeout=45)
        data = resp.json() if resp.content else {}
        if not resp.ok:
            return {'ok': False, 'error': data.get('error') or ('HTTP %s' % resp.status_code)}
        return data if isinstance(data, dict) else {'ok': True}
    except (requests.RequestException, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}


def _ja_enviou(destino_id, dia, tipo):
    return (
        PesagemWhatsAppEnvio.query.filter_by(
            destino_id=destino_id, data_ref=dia, tipo=tipo,
        ).first()
        is not None
    )


def _gravar_envio(destino, dia, tipo, status, corpo, erro=None):
    row = PesagemWhatsAppEnvio(
        destino_id=destino.id,
        data_ref=dia,
        tipo=tipo,
        enviado_em=datetime.now(),
        status=status,
        erro=(erro or '')[:255] or None,
        corpo=corpo,
    )
    db.session.add(row)
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        logger.exception('Falha ao gravar envio WhatsApp destino=%s', destino.id)
        return False


def enviar_para_destino(destino, tipo='manual', dia=None, sender=None):
    dia = dia or date.today()
    sender = sender or send_whatsapp
    totais = totais_bruto_do_dia(dia)
    corpo = montar_mensagem(destino.mensagem, totais=totais, dia=dia)
    result = sender(destino.telefone, corpo)
    ok = bool(result and result.get('ok'))
    if tipo == 'agendado' and not ok:
        logger.warning(
            'Envio agendado WhatsApp destino=%s falhou: %s',
            destino.id,
            (result or {}).get('error'),
        )
        return {
            'ok': False,
            'error': (result or {}).get('error') or 'Falha no envio',
            'corpo': corpo,
            'totais': totais,
        }
    _gravar_envio(
        destino,
        dia,
        tipo,
        'ok' if ok else 'erro',
        corpo,
        None if ok else (result or {}).get('error'),
    )
    return {
        'ok': ok,
        'error': None if ok else (result or {}).get('error') or 'Falha no envio',
        'corpo': corpo,
        'totais': totais,
    }


def process_scheduled_sends(now=None, sender=None):
    """Envia uma vez ao dia no horário cadastrado de cada destinatário ativo."""
    now = now or datetime.now()
    dia = now.date()
    hora_min = now.strftime('%H:%M')
    enviados = []
    destinos = PesagemWhatsAppDestino.query.filter_by(ativo=True).all()
    for dest in destinos:
        if not dest.hora:
            continue
        if dest.hora.strftime('%H:%M') != hora_min:
            continue
        if _ja_enviou(dest.id, dia, 'agendado'):
            continue
        result = enviar_para_destino(dest, tipo='agendado', dia=dia, sender=sender)
        enviados.append({'destino_id': dest.id, **result})
    return enviados


def ultimo_envio_por_destino(destino_ids):
    if not destino_ids:
        return {}
    rows = (
        PesagemWhatsAppEnvio.query
        .filter(PesagemWhatsAppEnvio.destino_id.in_(destino_ids))
        .order_by(PesagemWhatsAppEnvio.enviado_em.desc())
        .all()
    )
    seen = {}
    for row in rows:
        if row.destino_id in seen:
            continue
        seen[row.destino_id] = row.to_dict()
    return seen


def _scheduler_loop(app):
    while True:
        time.sleep(max(5, SCHEDULER_INTERVAL))
        try:
            with app.app_context():
                process_scheduled_sends()
        except Exception:
            logger.exception('Erro no agendador WhatsApp da pesagem')


def start_background(app):
    """Inicia ponte Node + thread do horário (uma vez por processo)."""
    global _bg_started
    if app.config.get('TESTING'):
        return
    if os.environ.get('PESAGEM_WA_DISABLE', '').strip() in ('1', 'true', 'yes'):
        return
    with _bg_lock:
        if _bg_started:
            return
        _bg_started = True
    try:
        start_bridge_process()
    except Exception:
        logger.exception('Não foi possível iniciar a ponte WhatsApp')
    t = threading.Thread(target=_scheduler_loop, args=(app,), name='pesagem-whatsapp', daemon=True)
    t.start()
