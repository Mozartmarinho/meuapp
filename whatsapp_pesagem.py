"""WhatsApp da pesagem: totais do dia, QR (bridge Node) e envio agendado."""
from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
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
NODE_RUNTIME_DIR = BRIDGE_DIR / 'runtime' / 'node'
NODE_WIN_ZIP_URL = os.environ.get(
    'PESAGEM_WA_NODE_ZIP',
    'https://nodejs.org/dist/v20.19.5/node-v20.19.5-win-x64.zip',
)

_bg_lock = threading.Lock()
_bg_started = False
_node_provision_lock = threading.Lock()


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


def peso_liquido_expr():
    return func.coalesce(PesagemLeitura.peso_liquido, PesagemLeitura.peso, 0.0)


def totais_liquido_do_dia(dia=None):
    """Soma o peso líquido de cada cadastro no dia (ex.: 10 pesagens CCD → um total)."""
    dia = dia or date.today()
    inicio = datetime.combine(dia, dt_time.min)
    fim = datetime.combine(dia, dt_time.max).replace(microsecond=0)
    rows = (
        db.session.query(
            PesagemLeitura.cliente_id,
            PesagemLeitura.cliente_nome,
            func.sum(peso_liquido_expr()),
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
    totais = totais if totais is not None else totais_liquido_do_dia(dia)
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


def _portable_node():
    direct = NODE_RUNTIME_DIR / ('node.exe' if os.name == 'nt' else 'bin/node')
    if direct.is_file():
        return str(direct)
    runtime_root = BRIDGE_DIR / 'runtime'
    if not runtime_root.is_dir():
        return None
    name = 'node.exe' if os.name == 'nt' else 'node'
    for candidate in runtime_root.rglob(name):
        if candidate.is_file() and candidate.name == name:
            return str(candidate)
    return None


def _which_node():
    found = shutil.which('node') or shutil.which('nodejs')
    if found:
        return found
    extras = [
        Path(r'C:\Program Files\nodejs\node.exe'),
        Path(r'C:\Program Files (x86)\nodejs\node.exe'),
        Path('/usr/bin/node'),
        Path('/usr/local/bin/node'),
    ]
    for candidate in extras:
        if candidate.is_file():
            return str(candidate)
    return _portable_node()


def _which_npm():
    found = shutil.which('npm') or shutil.which('npm.cmd')
    if found:
        return found
    node = _which_node()
    if node:
        npm_name = 'npm.cmd' if os.name == 'nt' else 'npm'
        sibling = Path(node).parent / npm_name
        if sibling.is_file():
            return str(sibling)
    extras = [
        Path(r'C:\Program Files\nodejs\npm.cmd'),
        Path(r'C:\Program Files (x86)\nodejs\npm.cmd'),
        Path('/usr/bin/npm'),
        Path('/usr/local/bin/npm'),
    ]
    for candidate in extras:
        if candidate.is_file():
            return str(candidate)
    return None


def inbound_token():
    path = BRIDGE_DIR / '.token'
    try:
        if path.is_file():
            token = path.read_text(encoding='utf-8').strip()
            if token:
                return token
        token = secrets.token_hex(24)
        path.write_text(token, encoding='utf-8')
        return token
    except OSError:
        return os.environ.get('PESAGEM_WA_INBOUND_TOKEN', '')


def _inbound_url():
    if os.environ.get('PESAGEM_WA_INBOUND_URL'):
        return os.environ['PESAGEM_WA_INBOUND_URL']
    port = str(os.environ.get('PORT', '80') or '80')
    if port in ('80', '443'):
        return 'http://127.0.0.1/api/chamados/whatsapp/inbound'
    return 'http://127.0.0.1:%s/api/chamados/whatsapp/inbound' % port


def _bridge_env():
    env = os.environ.copy()
    node = _which_node()
    if node:
        node_dir = str(Path(node).parent)
        env['PATH'] = node_dir + os.pathsep + env.get('PATH', '')
    env['PESAGEM_WA_BRIDGE_PORT'] = str(BRIDGE_PORT)
    env['PESAGEM_WA_BRIDGE_HOST'] = BRIDGE_HOST
    env['PUPPETEER_SKIP_DOWNLOAD'] = '1'
    env['PESAGEM_WA_INBOUND_URL'] = _inbound_url()
    env['PESAGEM_WA_INBOUND_TOKEN'] = inbound_token()
    return env


def _npm_argv():
    node = _which_node()
    if node:
        cli = Path(node).parent / 'node_modules' / 'npm' / 'bin' / 'npm-cli.js'
        if cli.is_file():
            return [node, str(cli)]
    npm = _which_npm()
    if npm:
        return [npm]
    return None


def ensure_node_runtime():
    """Usa Node do sistema ou baixa um portátil (Windows) sem instalação de administrador."""
    if _which_node():
        return True
    if os.name != 'nt' or _disabled():
        return False
    with _node_provision_lock:
        if _which_node():
            return True
        NODE_RUNTIME_DIR.parent.mkdir(parents=True, exist_ok=True)
        zip_path = NODE_RUNTIME_DIR.parent / 'node.zip'
        extract_dir = NODE_RUNTIME_DIR.parent / 'node-extract'
        try:
            logger.info('Baixando Node.js portátil para o WhatsApp Web interno')
            req = urllib.request.Request(
                NODE_WIN_ZIP_URL,
                headers={'User-Agent': 'Mozilla/5.0 pesagem-whatsapp'},
            )
            with urllib.request.urlopen(req, timeout=180) as resp, open(zip_path, 'wb') as out:
                shutil.copyfileobj(resp, out)
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
            inner = None
            for child in extract_dir.iterdir():
                if child.is_dir() and (child / 'node.exe').is_file():
                    inner = child
                    break
            if NODE_RUNTIME_DIR.exists():
                shutil.rmtree(NODE_RUNTIME_DIR, ignore_errors=True)
            if inner:
                shutil.move(str(inner), str(NODE_RUNTIME_DIR))
            elif (extract_dir / 'node.exe').is_file():
                shutil.move(str(extract_dir), str(NODE_RUNTIME_DIR))
            else:
                logger.warning('Zip do Node.js sem node.exe')
                return False
            shutil.rmtree(extract_dir, ignore_errors=True)
            try:
                zip_path.unlink()
            except OSError:
                pass
        except (OSError, zipfile.BadZipFile, urllib.error.URLError) as exc:
            logger.warning('Falha ao baixar Node.js portátil: %s', exc)
            return False
        return bool(_portable_node())


def _kill_pid(pid):
    if not pid or pid <= 0:
        return
    try:
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/PID', str(pid), '/T', '/F'],
                capture_output=True,
                text=True,
                timeout=15,
            )
        else:
            os.kill(pid, 15)
    except (OSError, subprocess.SubprocessError):
        pass


def _pids_listening(port):
    pids = set()
    try:
        if os.name == 'nt':
            proc = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            needle = ':%s' % port
            for line in (proc.stdout or '').splitlines():
                if needle not in line:
                    continue
                upper = line.upper()
                if 'LISTENING' not in upper and 'OUVINDO' not in upper:
                    continue
                parts = line.split()
                if not parts:
                    continue
                try:
                    pids.add(int(parts[-1]))
                except ValueError:
                    continue
        else:
            proc = subprocess.run(
                ['lsof', '-t', '-iTCP:%s' % port, '-sTCP:LISTEN'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in (proc.stdout or '').splitlines():
                try:
                    pids.add(int(line.strip()))
                except ValueError:
                    continue
    except (OSError, subprocess.SubprocessError):
        return set()
    pids.discard(0)
    return pids


def _stop_bridge_process():
    pid_path = BRIDGE_DIR / 'bridge.pid'
    if pid_path.is_file():
        try:
            _kill_pid(int(pid_path.read_text(encoding='utf-8').strip()))
        except (OSError, ValueError):
            pass
        try:
            pid_path.unlink()
        except OSError:
            pass
    for pid in _pids_listening(BRIDGE_PORT):
        _kill_pid(pid)
    for _ in range(20):
        if not _port_open(BRIDGE_HOST, BRIDGE_PORT):
            return True
        time.sleep(0.2)
    return not _port_open(BRIDGE_HOST, BRIDGE_PORT)


def _bridge_health_engine():
    """'web', 'legacy' ou None se a porta ainda não responde HTTP."""
    try:
        resp = requests.get(BRIDGE_URL + '/health', timeout=1.2)
        data = resp.json() if resp.content else {}
        if data.get('engine') == 'web':
            return 'web'
        return 'legacy'
    except (requests.RequestException, ValueError):
        return None


def _web_lib_installed():
    return (BRIDGE_DIR / 'node_modules' / 'whatsapp-web.js').exists()


def ensure_bridge_installed():
    if _web_lib_installed():
        return True
    npm_argv = _npm_argv()
    if not npm_argv:
        return False
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            npm_argv + ['install', '--omit=dev'],
            cwd=str(BRIDGE_DIR),
            capture_output=True,
            text=True,
            timeout=600,
            env=_bridge_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning('npm install WhatsApp bridge falhou: %s', exc)
        return False
    if proc.returncode != 0:
        logger.warning('npm install WhatsApp bridge rc=%s: %s', proc.returncode, proc.stderr[-800:])
        return False
    return _web_lib_installed()


def start_bridge_process():
    """Sobe o processo Node (WhatsApp Web no Chrome) se a porta ainda não estiver em uso."""
    if _port_open(BRIDGE_HOST, BRIDGE_PORT):
        engine = _bridge_health_engine()
        if engine == 'web' or engine is None:
            return True
        logger.info('Reiniciando ponte WhatsApp para o motor Web interno')
        _stop_bridge_process()
    node = _which_node()
    if not node:
        ensure_node_runtime()
        node = _which_node()
    if not node:
        return False
    if not ensure_bridge_installed():
        return False
    index_js = BRIDGE_DIR / 'index.js'
    if not index_js.is_file():
        return False
    (BRIDGE_DIR / 'auth').mkdir(parents=True, exist_ok=True)
    env = _bridge_env()
    log_path = BRIDGE_DIR / 'bridge.log'
    try:
        log_f = open(log_path, 'a', encoding='utf-8')
        popen_kw = {
            'cwd': str(BRIDGE_DIR),
            'env': env,
            'stdout': log_f,
            'stderr': log_f,
        }
        if os.name == 'nt':
            popen_kw['creationflags'] = (
                getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            )
        else:
            popen_kw['start_new_session'] = True
        subprocess.Popen([node, str(index_js)], **popen_kw)
    except OSError as exc:
        logger.warning('Falha ao iniciar bridge WhatsApp: %s', exc)
        return False
    for _ in range(80):
        if _port_open(BRIDGE_HOST, BRIDGE_PORT):
            return True
        time.sleep(0.35)
    return _port_open(BRIDGE_HOST, BRIDGE_PORT)


def _disabled():
    return os.environ.get('PESAGEM_WA_DISABLE', '').strip().lower() in ('1', 'true', 'yes')


def _bridge_unavailable_reason():
    if _disabled():
        return 'WhatsApp desabilitado neste ambiente.'
    if not _which_node():
        ensure_node_runtime()
    if not _which_node():
        return 'Não foi possível preparar o Node.js para o WhatsApp Web interno.'
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
                'engine': 'web',
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
        data.setdefault('engine', 'web')
        if isinstance(data, dict):
            data.pop('qr', None)
        return data
    except (requests.RequestException, ValueError) as exc:
        return {
            'ok': False,
            'engine': 'web',
            'state': 'unavailable',
            'qr': None,
            'qr_image': None,
            'user': None,
            'error': 'Ponte WhatsApp inacessível: %s' % exc,
        }


def logout_whatsapp():
    if _disabled():
        return {'ok': False, 'error': 'WhatsApp desabilitado neste ambiente.'}
    reason = _bridge_unavailable_reason()
    if reason and not _port_open(BRIDGE_HOST, BRIDGE_PORT):
        return {'ok': False, 'error': reason}
    try:
        resp = _bridge_post('/logout', timeout=90)
        data = resp.json() if resp.content else {'ok': resp.ok}
        if isinstance(data, dict):
            data.setdefault('ok', resp.ok)
        return data
    except (requests.RequestException, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}


def send_whatsapp(telefone, texto):
    if _disabled():
        return {'ok': False, 'error': 'WhatsApp desabilitado neste ambiente.'}
    raw = str(telefone or '').strip()
    if '@' in raw:
        to = raw
        phone = raw.split('@')[0].split(':')[0]
        if not phone:
            return {'ok': False, 'error': 'Telefone inválido'}
    else:
        phone = normalizar_telefone(raw)
        if not telefone_valido(phone):
            return {'ok': False, 'error': 'Telefone inválido'}
        to = phone
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
        resp = _bridge_post('/send', {'to': to, 'text': texto}, timeout=45)
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
    totais = totais_liquido_do_dia(dia)
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
