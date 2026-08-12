"""Cliente HTTP Control iD (iDFace / iDAccess / iDBlock) — São Geraldo Acesso.

Protocolo baseado na API pública Control iD (.fcgi) e no fluxo legível do
Sollus Access (`sicroniza_equipamento.py`: login + session + load_objects).

Credenciais vêm do cadastro do equipamento (usuario_disp / senha_disp) ou
das variáveis de ambiente CONTROLID_DEFAULT_USER / CONTROLID_DEFAULT_PASSWORD.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

import requests

LOG = logging.getLogger(__name__)

SESSION_TTL = int(os.environ.get('CONTROLID_SESSION_TTL', str(8 * 60)))
DEFAULT_LOGIN = os.environ.get('CONTROLID_DEFAULT_USER', 'admin')
DEFAULT_PASSWORD = os.environ.get('CONTROLID_DEFAULT_PASSWORD', 'admin')
REQUEST_TIMEOUT = float(os.environ.get('CONTROLID_TIMEOUT', '12'))
OFFLINE_PAGE_SIZE = int(os.environ.get('CONTROLID_OFFLINE_PAGE', '500'))
OFFLINE_MAX_PAGES = int(os.environ.get('CONTROLID_OFFLINE_MAX_PAGES', '10'))
MONITOR_PATH = os.environ.get('CONTROLID_MONITOR_PATH', 'acesso/controlid/notifications')
MONITOR_TIMEOUT_MS = os.environ.get('CONTROLID_MONITOR_TIMEOUT', '5000')
MONITOR_ALIVE_MS = os.environ.get('CONTROLID_MONITOR_ALIVE', '30000')

_session_cache: dict[str, dict[str, Any]] = {}
_session_lock = Lock()
_http_sessions: dict[str, requests.Session] = {}
_http_lock = Lock()


class ControlIDError(Exception):
    """Falha de comunicação ou resposta inválida do equipamento."""


@dataclass
class DeviceCreds:
    ip: str
    login: str = DEFAULT_LOGIN
    password: str = DEFAULT_PASSWORD
    porta: int = 80

    @property
    def cache_key(self) -> str:
        return f'{self.ip}:{int(self.porta or 80)}'

    @property
    def base(self) -> str:
        host = (self.ip or '').strip()
        if not host:
            raise ControlIDError('IP do equipamento não configurado')
        porta = int(self.porta or 80)
        if porta and porta != 80:
            return f'http://{host}:{porta}'
        return f'http://{host}'


def creds_from_equipamento(eq) -> DeviceCreds:
    """Monta DeviceCreds a partir de AcessoEquipamento (ou dict compatível)."""
    if isinstance(eq, dict):
        ip = (eq.get('ip') or '').strip()
        login = (eq.get('usuario_disp') or eq.get('usuario') or DEFAULT_LOGIN).strip() or DEFAULT_LOGIN
        senha = (eq.get('senha_disp') or eq.get('senha') or DEFAULT_PASSWORD)
        porta = int(eq.get('porta') or 80)
    else:
        ip = (getattr(eq, 'ip', None) or '').strip()
        login = (getattr(eq, 'usuario_disp', None) or DEFAULT_LOGIN).strip() or DEFAULT_LOGIN
        senha = getattr(eq, 'senha_disp', None) or DEFAULT_PASSWORD
        porta = int(getattr(eq, 'porta', None) or 80)
    if not senha:
        senha = DEFAULT_PASSWORD
    return DeviceCreds(ip=ip, login=login, password=str(senha), porta=porta)


def _http_session(key: str) -> requests.Session:
    with _http_lock:
        sess = _http_sessions.get(key)
        if sess is None:
            sess = requests.Session()
            try:
                sess.trust_env = False
            except Exception:
                pass
            _http_sessions[key] = sess
        return sess


def _cached_token(key: str) -> str | None:
    with _session_lock:
        item = _session_cache.get(key)
        if item and (time.time() - item['ts']) < SESSION_TTL:
            return item['token']
        return None


def _save_token(key: str, token: str) -> None:
    with _session_lock:
        _session_cache[key] = {'token': token, 'ts': time.time()}


def invalidate_session(creds: DeviceCreds) -> None:
    with _session_lock:
        _session_cache.pop(creds.cache_key, None)


def _session_invalid(resp: requests.Response | None) -> bool:
    if resp is None:
        return True
    if resp.status_code in (401, 403):
        return True
    try:
        txt = (resp.text or '').lower()
    except Exception:
        return False
    return 'invalid session' in txt or 'sessão inválida' in txt


def login(creds: DeviceCreds, force: bool = False, timeout: float | None = None) -> dict[str, Any]:
    """POST /login.fcgi → {session, device_id?}."""
    key = creds.cache_key
    if not force:
        tok = _cached_token(key)
        if tok:
            return {'session': tok, 'cached': True}

    sess = _http_session(key)
    payload = {'login': creds.login, 'password': creds.password}
    headers = {'Content-Type': 'application/json'}
    to = timeout if timeout is not None else REQUEST_TIMEOUT
    url = f'{creds.base}/login.fcgi'
    url_https = url.replace('http://', 'https://', 1)

    try:
        resp = sess.post(url, json=payload, headers=headers, timeout=to, allow_redirects=False)
        if resp is not None and 300 <= resp.status_code < 400:
            loc = resp.headers.get('Location', '')
            if loc.startswith('https://'):
                resp = sess.post(url_https, json=payload, headers=headers, timeout=to, verify=False)
    except requests.exceptions.SSLError:
        resp = sess.post(url_https, json=payload, headers=headers, timeout=to, verify=False)
    except requests.RequestException as exc:
        raise ControlIDError(f'Login falhou em {creds.ip}: {exc}') from exc

    if resp is None or resp.status_code != 200:
        sc = getattr(resp, 'status_code', None)
        tx = getattr(resp, 'text', '')[:200]
        raise ControlIDError(f'Login falhou em {creds.ip}: HTTP {sc} {tx}')

    try:
        data = resp.json()
    except Exception as exc:
        raise ControlIDError(f'Resposta de login inválida em {creds.ip}') from exc

    token = data.get('session')
    if not token:
        raise ControlIDError(f'Sessão não retornada por {creds.ip}')
    _save_token(key, token)
    LOG.info('ControlID login ok em %s', creds.ip)
    return {
        'session': token,
        'device_id': data.get('device_id'),
        'cached': False,
        'raw': data,
    }


def device_post(
    creds: DeviceCreds,
    endpoint: str,
    payload: dict | list | None = None,
    timeout: float | None = None,
    force_login: bool = False,
) -> requests.Response:
    """POST /{endpoint}?session=... com retry em sessão inválida."""
    endpoint = endpoint.lstrip('/')
    if not endpoint.endswith('.fcgi') and '.' not in endpoint:
        endpoint = f'{endpoint}.fcgi'

    info = login(creds, force=force_login)
    token = info['session']
    sess = _http_session(creds.cache_key)
    to = timeout if timeout is not None else REQUEST_TIMEOUT
    headers = {'Content-Type': 'application/json'}

    def _do(tok: str) -> requests.Response:
        url = f'{creds.base}/{endpoint}?session={tok}'
        return sess.post(url, json=payload if payload is not None else {}, headers=headers, timeout=to)

    try:
        resp = _do(token)
        if _session_invalid(resp):
            invalidate_session(creds)
            info = login(creds, force=True)
            resp = _do(info['session'])
        return resp
    except requests.RequestException as exc:
        raise ControlIDError(f'Falha em {creds.ip}/{endpoint}: {exc}') from exc


def device_json(
    creds: DeviceCreds,
    endpoint: str,
    payload: dict | list | None = None,
    timeout: float | None = None,
) -> Any:
    resp = device_post(creds, endpoint, payload, timeout=timeout)
    if resp.status_code >= 400:
        raise ControlIDError(
            f'{creds.ip}/{endpoint} → HTTP {resp.status_code}: {(resp.text or "")[:240]}'
        )
    try:
        return resp.json() if (resp.text or '').strip() else {}
    except Exception:
        return {'_raw': resp.text}


def probe(creds: DeviceCreds, timeout: float = 5.0) -> dict[str, Any]:
    """Testa reachability via login. Retorna device_id se disponível."""
    info = login(creds, force=True, timeout=timeout)
    return {
        'ok': True,
        'ip': creds.ip,
        'device_id': info.get('device_id'),
        'session': True,
    }


def system_information(creds: DeviceCreds) -> dict[str, Any]:
    data = device_json(creds, 'system_information.fcgi', {})
    return data if isinstance(data, dict) else {'_raw': data}


def puxar_device_id(creds: DeviceCreds) -> str:
    """Obtém device_id via login e/ou system_information."""
    info = login(creds, force=True)
    did = info.get('device_id')
    if did is not None and str(did).strip():
        return str(did)
    try:
        sysinfo = system_information(creds)
        for key in ('device_id', 'id', 'serial'):
            if sysinfo.get(key) is not None:
                return str(sysinfo[key])
        # alguns firmwares aninham em "network" / "general"
        for nest in ('network', 'general', 'device'):
            block = sysinfo.get(nest) or {}
            if isinstance(block, dict) and block.get('device_id') is not None:
                return str(block['device_id'])
    except ControlIDError:
        pass
    raise ControlIDError(f'Não foi possível obter device_id de {creds.ip}')


def set_system_time(creds: DeviceCreds, when: datetime | None = None) -> dict[str, Any]:
    """POST /set_system_time.fcgi com day/month/year/hour/minute/second."""
    dt = when or datetime.now()
    payload = {
        'day': int(dt.day),
        'month': int(dt.month),
        'year': int(dt.year),
        'hour': int(dt.hour),
        'minute': int(dt.minute),
        'second': int(dt.second),
    }
    return device_json(creds, 'set_system_time.fcgi', payload)


def parse_data_hora_ui(data_str: str, hora_str: str) -> datetime:
    """Aceita data DD/MM/YYYY ou YYYY-MM-DD e hora HH:MM[:SS]."""
    data_str = (data_str or '').strip()
    hora_str = (hora_str or '').strip()
    if not data_str or not hora_str:
        raise ControlIDError('Data e hora são obrigatórias')

    dt_date = None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            dt_date = datetime.strptime(data_str, fmt).date()
            break
        except ValueError:
            continue
    if dt_date is None:
        raise ControlIDError(f'Data inválida: {data_str}')

    tm = None
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            tm = datetime.strptime(hora_str, fmt).time()
            break
        except ValueError:
            continue
    if tm is None:
        raise ControlIDError(f'Hora inválida: {hora_str}')
    return datetime.combine(dt_date, tm)


def configurar_monitor(
    creds: DeviceCreds,
    hostname: str,
    porta: int | str = 80,
    path: str | None = None,
    request_timeout: str | None = None,
    alive_interval: str | None = None,
) -> dict[str, Any]:
    """Configura servidor de eventos (monitor) via set_configuration.fcgi."""
    host = (hostname or '').strip()
    if not host:
        raise ControlIDError('Host/IP do servidor é obrigatório')
    payload = {
        'monitor': {
            'request_timeout': str(request_timeout or MONITOR_TIMEOUT_MS),
            'hostname': host,
            'port': str(porta or 80),
            'path': (path or MONITOR_PATH).strip().strip('/'),
            'alive_interval': str(alive_interval or MONITOR_ALIVE_MS),
        }
    }
    return device_json(creds, 'set_configuration.fcgi', payload)


def ativar_modo_online_opcional(creds: DeviceCreds, server_id: int | str | None = None) -> dict[str, Any]:
    """Tenta habilitar online_client (Enterprise). Best-effort — nem todo firmware exige."""
    online_client: dict[str, Any] = {'server_id': str(server_id or '1')}
    payload = {
        'general': {'online': '0'},  # monitor standalone por padrão (server recebe eventos)
        'online_client': online_client,
    }
    try:
        return device_json(creds, 'set_configuration.fcgi', payload)
    except ControlIDError as exc:
        LOG.warning('ativar_modo_online_opcional %s: %s', creds.ip, exc)
        return {'ok': False, 'error': str(exc)}


def reiniciar_conexao(
    creds: DeviceCreds,
    hostname: str | None = None,
    porta: int | str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Reloga no device e reaplica monitor (equivalente Sollus 'reiniciar conexão')."""
    invalidate_session(creds)
    info = login(creds, force=True)
    result: dict[str, Any] = {
        'login': True,
        'device_id': info.get('device_id'),
        'monitor': None,
    }
    if hostname:
        result['monitor'] = configurar_monitor(creds, hostname, porta or 80, path=path)
    return result


def _extract_rows(data: Any, obj: str) -> list[dict]:
    if not isinstance(data, dict):
        return []
    rows = data.get(obj) or data.get('results') or []
    if not rows and isinstance(data.get('results'), list):
        for bucket in data['results']:
            if isinstance(bucket, dict) and obj in bucket:
                rows = bucket[obj]
                break
    return [r for r in (rows or []) if isinstance(r, dict)]


def load_objects(creds: DeviceCreds, payload: dict, timeout: float = 20.0) -> dict:
    return device_json(creds, 'load_objects.fcgi', payload, timeout=timeout)


def fetch_access_logs_page(
    creds: DeviceCreds,
    after_id: int = 0,
    limit: int = OFFLINE_PAGE_SIZE,
) -> tuple[list[dict], int]:
    """Busca página de access_logs (3 formatos de payload, como no Sollus)."""
    obj = 'access_logs'

    def _ff(field: str) -> dict:
        return {'object': obj, 'field': field}

    base_fields = [
        'id', 'time', 'event', 'user_id', 'device_id', 'portal_id',
        'identifier_id', 'qrcode_value', 'pin_value', 'card_value',
    ]
    payloads = [
        {
            'object': obj,
            'fields': [_ff(f) for f in base_fields],
            'where': [{'object': obj, 'field': 'id', 'operator': '>', 'value': int(after_id)}],
            'order': ['ascending', _ff('id')],
            'limit': int(limit),
        },
        {
            'object': obj,
            'fields': [_ff(f) for f in base_fields],
            'where': [{'object': obj, 'field': 'id', 'operator': '>', 'value': int(after_id)}],
            'order': ['ascending', _ff('id')],
            'limit': int(limit),
            'join': 'LEFT',
        },
        {
            'object': obj,
            'fields': list(base_fields),
            'where': [{'field': 'id', 'operator': '>', 'value': int(after_id)}],
            'order': [{'object': obj, 'field': 'id', 'type': 'ASC'}],
            'limit': int(limit),
        },
    ]

    last_err = None
    for payload in payloads:
        try:
            data = load_objects(creds, payload, timeout=20)
            rows = _extract_rows(data, obj)
            for r in rows:
                try:
                    if int(r.get('event', 0)) == 13:
                        r['_event_name'] = 'Cancel entry'
                except Exception:
                    pass
            if rows:
                return rows, int(rows[-1].get('id', after_id))
            return [], after_id
        except ControlIDError as exc:
            last_err = exc
            continue
    if last_err:
        raise last_err
    return [], after_id


def collect_access_logs(
    creds: DeviceCreds,
    after_id: int = 0,
    max_pages: int = OFFLINE_MAX_PAGES,
    page_size: int = OFFLINE_PAGE_SIZE,
) -> list[dict]:
    """Coleta várias páginas de access_logs a partir de after_id."""
    all_rows: list[dict] = []
    last_id = int(after_id or 0)
    for _ in range(max(1, max_pages)):
        rows, last_id = fetch_access_logs_page(creds, last_id, page_size)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
    return all_rows


def parse_access_log_time(row: dict) -> datetime:
    """Converte epoch (local, como Sollus) ou ISO para datetime naive."""
    v = row.get('time')
    if v is None:
        return datetime.now()
    try:
        iv = int(v)
        if iv > 10_000_000_000:
            iv = iv / 1000.0
        # Sollus: OFFLINE_ASSUME_EPOCH_IS_LOCAL → utcfromtimestamp
        return datetime.utcfromtimestamp(iv)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(str(v).replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def map_access_event(event_code: int | None, user_id: int | None = None, event_name: str | None = None) -> tuple[str, str]:
    """Retorna (status, event_type) alinhado ao mapeamento Sollus."""
    code = int(event_code or 0)
    en = (event_name or '').lower().strip()
    if code == 7:
        return 'Liberado', 'Sistema'
    if code == 11:
        return 'Liberado', 'REX'
    if code == 13:
        return 'Desistência', (event_name or 'Cancel entry')
    if code in (3, 6, 10):
        return 'Negado', (event_name or 'Acesso Negado')
    if 'not identified' in en or (user_id is not None and int(user_id) <= 0):
        return 'Negado', (event_name or 'Não identificado')
    return 'Negado', (event_name or 'Acesso Negado')


def create_objects(creds: DeviceCreds, object_name: str, values: list[dict]) -> dict:
    if not values:
        return {'ids': []}
    return device_json(creds, 'create_objects.fcgi', {'object': object_name, 'values': values})


def destroy_objects(creds: DeviceCreds, object_name: str, where: dict) -> dict:
    return device_json(creds, 'destroy_objects.fcgi', {'object': object_name, 'where': where})


def modify_objects(creds: DeviceCreds, object_name: str, values: dict, where: dict) -> dict:
    return device_json(
        creds,
        'modify_objects.fcgi',
        {'object': object_name, 'values': values, 'where': where},
    )


def load_users_by_registration(creds: DeviceCreds, registration: str) -> list[dict]:
    payload = {
        'object': 'users',
        'where': [
            {
                'object': 'users',
                'field': 'registration',
                'operator': '=',
                'value': str(registration),
            }
        ],
    }
    try:
        data = load_objects(creds, payload)
        return _extract_rows(data, 'users')
    except ControlIDError:
        # fallback formato simplificado
        payload2 = {
            'object': 'users',
            'where': {'users': {'registration': str(registration)}},
        }
        data = load_objects(creds, payload2)
        return _extract_rows(data, 'users')


def upsert_user(
    creds: DeviceCreds,
    *,
    user_id: int | None,
    name: str,
    registration: str,
) -> dict[str, Any]:
    """Cria ou atualiza usuário no device. Prefere id explícito (= matrícula numérica)."""
    name = (name or '').strip() or registration
    registration = str(registration or '').strip()
    if not registration:
        raise ControlIDError('registration/matrícula obrigatória')

    values: dict[str, Any] = {'name': name, 'registration': registration}
    if user_id is not None:
        values['id'] = int(user_id)

    # tenta create
    try:
        created = create_objects(creds, 'users', [values])
        ids = created.get('ids') or []
        return {'ok': True, 'action': 'create', 'ids': ids, 'user_id': ids[0] if ids else user_id}
    except ControlIDError as exc:
        msg = str(exc).lower()
        if 'exist' not in msg and 'duplicate' not in msg and 'já' not in msg and '409' not in msg:
            # ainda tenta modify por id/registration
            LOG.debug('create user falhou (%s); tentando modify', exc)

    target_id = user_id
    if target_id is None:
        existing = load_users_by_registration(creds, registration)
        if existing:
            try:
                target_id = int(existing[0].get('id'))
            except Exception:
                target_id = None

    if target_id is None:
        raise ControlIDError(f'Não foi possível criar/atualizar usuário {registration} em {creds.ip}')

    modify_objects(
        creds,
        'users',
        {'name': name, 'registration': registration},
        {'users': {'id': int(target_id)}},
    )
    return {'ok': True, 'action': 'modify', 'user_id': int(target_id)}


def _card_api_value(card: str) -> int | str:
    """Converte cartão legível para valor API (int se numérico)."""
    raw = (card or '').strip()
    if not raw:
        raise ControlIDError('cartão vazio')
    # remove espaços/hífens
    cleaned = raw.replace(' ', '').replace('-', '')
    if cleaned.isdigit():
        return int(cleaned)
    return cleaned


def upsert_card(creds: DeviceCreds, user_id: int, card: str) -> dict[str, Any]:
    value = _card_api_value(card)
    # remove cartões existentes do user (best-effort) e recria
    try:
        destroy_objects(creds, 'cards', {'cards': {'user_id': int(user_id)}})
    except ControlIDError:
        pass
    created = create_objects(creds, 'cards', [{'user_id': int(user_id), 'value': value}])
    return {'ok': True, 'ids': created.get('ids') or []}


def set_user_image(
    creds: DeviceCreds,
    user_id: int,
    image_bytes: bytes,
    timestamp: int | None = None,
) -> dict[str, Any]:
    """POST /user_set_image.fcgi com JPEG em base64."""
    if not image_bytes:
        raise ControlIDError('imagem vazia')
    b64 = base64.b64encode(image_bytes).decode('ascii')
    payload = {
        'user_id': int(user_id),
        'timestamp': int(timestamp if timestamp is not None else time.time()),
        'match': 0,
        'image': b64,
    }
    return device_json(creds, 'user_set_image.fcgi', payload, timeout=30)


def load_image_bytes(foto: str | None, static_root: Path | None = None) -> bytes | None:
    """Carrega bytes de foto a partir de data-URL, path web ou arquivo local."""
    if not foto:
        return None
    foto = str(foto).strip()
    if foto.startswith('data:') and ',' in foto:
        try:
            return base64.b64decode(foto.split(',', 1)[1])
        except Exception:
            return None

    # path tipo /static/acesso_fotos/123.jpg
    candidates: list[Path] = []
    if static_root is None:
        static_root = Path(__file__).resolve().parent / 'static'
    if foto.startswith('/static/'):
        candidates.append(Path(__file__).resolve().parent / foto.lstrip('/').replace('/', os.sep))
    elif foto.startswith('static/'):
        candidates.append(Path(__file__).resolve().parent / foto.replace('/', os.sep))
    else:
        candidates.append(Path(foto))
        candidates.append(static_root / 'acesso_fotos' / Path(foto).name)

    for path in candidates:
        try:
            if path.is_file():
                return path.read_bytes()
        except Exception:
            continue
    return None


def execute_door(creds: DeviceCreds, door: int = 1, actions: list[dict] | None = None) -> dict:
    """Abre porta via execute_actions.fcgi (door ou sec_box)."""
    if actions is None:
        actions = [{'action': 'door', 'parameters': f'door={int(door)}'}]
    return device_json(creds, 'execute_actions.fcgi', {'actions': actions})


def list_device_users(creds: DeviceCreds, limit: int = 200) -> list[dict]:
    payload = {
        'object': 'users',
        'limit': int(limit),
    }
    data = load_objects(creds, payload)
    return _extract_rows(data, 'users')
