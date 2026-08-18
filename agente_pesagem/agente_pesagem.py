"""
Agente local de pesagem — aparência clássica (estilo Delphi/VCL).
Peso ao vivo da balança + menu Configuração para múltiplos controladores.
"""
from __future__ import annotations

import json
import queue
import re
import select
import socket
import sys
import threading
import time
import tkinter as tk
from io import BytesIO
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

import requests

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


# Cores / tipografia estilo Delphi / Windows clássico
CLR_BG = '#D4D0C8'
CLR_PANEL = '#D4D0C8'
CLR_WHITE = '#FFFFFF'
CLR_NAVY = '#000080'
CLR_BLACK = '#000000'
CLR_SHADOW = '#808080'
CLR_LIGHT = '#FFFFFF'
CLR_DARK = '#404040'
CLR_BTN = '#D4D0C8'
CLR_STATUS = '#C0C0C0'
FONT_UI = ('Tahoma', 9)
FONT_TITLE = ('Tahoma', 10, 'bold')
FONT_WEIGHT = ('Consolas', 72, 'bold')  # fallback se o visor 7 segmentos falhar
FONT_MONO = ('Courier New', 9)
FONT_LED_LABEL = ('Tahoma', 14, 'bold')
CLR_WEIGHT = '#FF1A1A'
CLR_LED_BG = '#050505'
CLR_LED_ON = '#FF1A1A'
CLR_LED_OFF = '#220505'
FOTO_MAX_W = 160
FOTO_MAX_H = 140
# RS-232 ao vivo (ACBr BALUrano, digital_scale, UDC, balanca-cli).
# Ethernet 33581 = Urano Connect: só envia ao [Imprimir] / [Modo Autom.] — escuta, não consulta.
CMD_URAN12 = b'\x04\x05 '   # EOT+ENQ+espaço (balanca-cli / UDC Uran12)
CMD_STD04 = b'\x05\n\r'     # ENQ+LF+CR (digital_scale STD04 / Urano POP)
CMD_ENQ = b'\x05'           # ACBr BALUrano
PROTOCOLOS_SERIAL = {
    'auto': 'Auto (Uran12 + STD04)',
    'uran12': 'Uran12 (EOT+ENQ)',
    'std04': 'STD04 (ENQ+LF+CR)',
}
HINT_TCP_CONNECT = (
    'Urano Connect: TCP 33581 + UDP 33583/33584. '
    'Pressione [Imprimir] ou ligue [Modo Autom.] para o peso. '
    'Visor ao vivo: use RS-232 (COM).'
)
HINT_SERIAL_SILENCIO = (
    'COM aberta, mas ZERO bytes. Confira cabo RS-232, '
    'protocolo Uran12 ou STD04 na balança e 9600 8N2.'
)
HINT_IMPRIMIR_SILENCIO = (
    'Imprimir não chegou nesta socket. Confira na BA37: '
    'destino da impressão = Ethernet/PC, não só a impressora. '
    'Specs de impressão/rede.'
)
HINT_CONEXAO = (
    'COM = visor ao vivo (Urano RS-232). '
    'Ethernet 33581/UDP 33583-33584 = etiqueta: só envia ao [Imprimir] ou [Modo Autom.].'
)
SERVIDOR_PADRAO = 'http://192.168.1.179'
# Linux Nginx (192.168.0.253) ainda não tem /api/pesagem/clientes — 404 HTML.
# O Cadastro de Cliente (ANGRA POOL, CPL, …) está neste Flask Windows.
# Urano BA37 Ethernet (manual spec):
#   166 porta modo servidor (a balança ESCUTA) = 33581
#   167 porta modo cliente  (a balança CONECTA no PC) = 33582
#   168 UDP listen = 33583 / 169 UDP broadcast = 33584
#   43  0=não conectado  1=modo comum (servidor)  2=modo cliente
#   154-157 IP do PC (modo cliente)
# Manual: [Imprimir] imprime etiqueta local. Export Ethernet = P42 ou spec 43=2.
# Não há handshake TCP público (cadastro/carga via Connect). NÃO enviar ENQ em loop.
# Outros modelos / conversor serial-Ethernet: 4001, 23, 2222, 8000, 9000.
PORTA_TCP_PADRAO = 33581
PORTA_ESCUTA_PADRAO = 33582
PORTA_UDP_LISTEN = 33583
PORTA_UDP_BROADCAST = 33584
# Frame vazio length-prefixed (2 bytes BE = 0): anúncio único no UDP listen da balança.
# Manual não documenta bytes de login TCP — só a topologia UDP 168/169.
HANDSHAKE_UDP_CONNECT = b'\x00\x00'
PORTAS_TCP_COMUNS = (33581, 4001, 23, 2222, 8000, 9000, 33582, 10001, 9100)
APP_VERSION = '1.2.0'
ICON_NAME = 'sao_geraldo.ico'

# Aceita formatos WT1000, Urano ST/GS e genéricos
# Contínuo completo: 0, 010.000, 000.200, 009.800
# Comando: ww010.000kg / Wn010.000kg
# Urano/Toledo contínuo: ST,GS,+0012.34kg
WEIGHT_RE = re.compile(
    r'(?P<sign>[-+])?\s*(?P<value>\d{1,6}(?:[.,]\d{1,4})?)\s*(?P<unit>kg|g|lb)?',
    re.IGNORECASE,
)
URANO_STGS_RE = re.compile(
    r'(?P<stab>ST|US|OL)\s*,\s*(?P<tipo>GS|NT|TR)\s*,\s*(?P<sign>[-+])?\s*(?P<value>\d+[.,]?\d*)\s*(?P<unit>kg|g|lb)?',
    re.IGNORECASE,
)
# ACBr / digital_scale: ...N0 1.542kg  ou  N001542kg
URANO_N0_RE = re.compile(
    r'N0\s*(?P<sign>[-+])?(?P<value>\d+[.,]?\d*)\s*(?P<unit>kg|g)?',
    re.IGNORECASE,
)
# UDC Std04 / Urano6 (LePeso modelo 1): 9 chars — estabilidade + sinal + 5 dígitos (gramas)
URANO9_RE = re.compile(
    r'^[\s*INS](?P<sign>[+\-\s])(?P<digits>\d{5})\s*$',
    re.IGNORECASE,
)
WT1000_CONTINUOUS_RE = re.compile(
    r'(?P<stab>[01])\s*,\s*(?P<bruto>[-+]?\d+[.,]?\d*)\s*,\s*(?P<tara>[-+]?\d+[.,]?\d*)\s*,\s*(?P<liq>[-+]?\d+[.,]?\d*)',
    re.IGNORECASE,
)
WT1000_CMD_RE = re.compile(
    r'(?P<tipo>ww|wn)\s*(?P<value>[-+]?\d+[.,]?\d*)\s*(?P<unit>kg|lb)?',
    re.IGNORECASE,
)
PESO_LABEL_RE = re.compile(
    r'PESO\s*L?\s*[:\s]\s*(?P<sign>[-+])?\s*(?P<value>\d+[.,]?\d*)\s*(?P<unit>kg|g)?',
    re.IGNORECASE,
)
# 000.00 / 00.000 / 12,34 sem texto extra
PESO_DECIMAL_RE = re.compile(
    r'(?P<sign>[-+])?\s*(?P<value>\d{1,4}[.,]\d{1,4})\s*(?P<unit>kg|g|lb)?',
    re.IGNORECASE,
)


def app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _ico_paths() -> list[Path]:
    return [
        _bundle_dir() / ICON_NAME,
        app_dir() / ICON_NAME,
        _bundle_dir() / 'sao_geraldo.png',
        app_dir() / 'sao_geraldo.png',
    ]


def _aplicar_icone(win) -> None:
    """Ícone São Geraldo no .exe, barra de título, config e barra de tarefas."""
    ico = next((p for p in _ico_paths() if p.suffix.lower() == '.ico' and p.is_file()), None)
    png = next((p for p in _ico_paths() if p.suffix.lower() == '.png' and p.is_file()), None)
    if ico is not None:
        try:
            win.iconbitmap(str(ico))
        except Exception:
            try:
                win.iconbitmap(default=str(ico))
            except Exception:
                pass
    if Image is None or ImageTk is None:
        return
    src = png if png is not None else ico
    if src is None:
        return
    try:
        im = Image.open(src).convert('RGBA')
        photos = [
            ImageTk.PhotoImage(im.resize((s, s), Image.Resampling.LANCZOS))
            for s in (16, 32, 48, 64)
        ]
        try:
            win.iconphoto(True, *photos)
        except Exception:
            win.iconphoto(True, photos[-1])
        win._icon_photos = photos  # noqa: SLF001 — impede o GC de dropar o ícone
    except Exception:
        pass


def _resumo_http_erro(resp, url: str) -> str:
    """Status HTTP sem despejar HTML do Flask (404 em inglês confundia o log)."""
    path = '/' + url.split('://', 1)[-1].split('/', 1)[-1] if '://' in url else url
    if resp.status_code == 404:
        return (
            f'HTTP 404: {path} não existe neste servidor. '
            'O Flask em execução precisa ser o meuapp atual (rotas /api/pesagem/...).'
        )
    ctype = (resp.headers.get('Content-Type') or '').lower()
    if 'json' in ctype:
        try:
            data = resp.json()
            err = data.get('error') or data.get('message') or resp.text[:80]
            return f'HTTP {resp.status_code}: {err}'
        except Exception:
            pass
    return f'HTTP {resp.status_code} em {path}'


def default_config() -> dict:
    return {
        'servidor_url': SERVIDOR_PADRAO,
        'api_key': 'saogeraldo-pesagem-2025',
        'balanca_codigo': 'BAL-01',
        'balanca_nome': 'BA37',
        'balanca_local': 'Recepção / Expedição',
        'modelo': 'BA37',
        # Adaptador USB Serial (FTDI) neste PC — peso ao vivo Urano RS-232
        'porta_com': 'COM3',
        'baudrate': 9600,
        'bytesize': 8,
        'parity': 'N',
        'stopbits': 2,  # digital_scale POP / UDC Uran12: 9600 8N2
        'timeout': 1.0,
        'protocolo_serial': 'auto',  # auto | uran12 | std04
        'conexao_tipo': 'serial',  # serial | rede | escuta
        'balanca_ip': '',
        'balanca_porta_tcp': PORTA_TCP_PADRAO,
        'modo_simulacao': False,
        'envio_automatico': False,
        'intervalo_envio_seg': 2.0,
        'peso_minimo': 0.001,
        'consultar_balanca': True,
        'intervalo_consulta_seg': 0.3,
    }


def _host_de_url(url: str) -> str:
    raw = (url or '').strip().lower()
    for pfx in ('http://', 'https://'):
        if raw.startswith(pfx):
            raw = raw[len(pfx):]
            break
    return raw.split('/')[0].split(':')[0]


def load_config() -> dict:
    cfg_path = app_dir() / 'config.json'
    cfg = default_config()
    if cfg_path.exists():
        try:
            saved = json.loads(cfg_path.read_text(encoding='utf-8'))
        except Exception:
            saved = {}
        if isinstance(saved, dict):
            cfg.update(saved)
    else:
        save_config(cfg)
    if not str(cfg.get('servidor_url') or '').strip():
        cfg['servidor_url'] = SERVIDOR_PADRAO
    cfg['servidor_url'] = str(cfg['servidor_url']).strip().rstrip('/')
    # serverlinux tem /api/pesagem/health mas NÃO tem /api/pesagem/clientes (404 HTML).
    if _host_de_url(cfg['servidor_url']) == '192.168.0.253':
        cfg['servidor_url'] = SERVIDOR_PADRAO
        try:
            save_config(cfg)
        except Exception:
            pass
    tipo = str(cfg.get('conexao_tipo') or 'serial').strip().lower()
    if tipo in ('escuta', 'listen', 'cliente', 'modo_cliente'):
        cfg['conexao_tipo'] = 'escuta'
    elif tipo in ('rede', 'ethernet', 'tcp', 'ip', 'network'):
        cfg['conexao_tipo'] = 'rede'
    else:
        cfg['conexao_tipo'] = 'serial'
    try:
        cfg['balanca_porta_tcp'] = int(cfg.get('balanca_porta_tcp') or PORTA_TCP_PADRAO)
    except (TypeError, ValueError):
        cfg['balanca_porta_tcp'] = PORTA_TCP_PADRAO
    cfg['balanca_ip'] = str(cfg.get('balanca_ip') or '').strip()
    proto = str(cfg.get('protocolo_serial') or 'auto').strip().lower()
    if proto in ('uran12', 'uran-12', 'udc', 'eot'):
        cfg['protocolo_serial'] = 'uran12'
    elif proto in ('std04', 'std-04', 'std4'):
        cfg['protocolo_serial'] = 'std04'
    else:
        cfg['protocolo_serial'] = 'auto'
    try:
        sb = float(cfg.get('stopbits') or 2)
    except (TypeError, ValueError):
        sb = 2
    cfg['stopbits'] = 2 if sb not in (1, 1.5, 2) else sb
    try:
        cfg['intervalo_consulta_seg'] = float(cfg.get('intervalo_consulta_seg') or 0.3)
    except (TypeError, ValueError):
        cfg['intervalo_consulta_seg'] = 0.3
    return cfg


def probe_tcp(ip: str, port: int, timeout: float = 1.8) -> tuple[str, str]:
    """Tenta TCP em ip:port. Retorna (codigo, mensagem_pt). codigo: aberta|recusada|timeout|erro."""
    sock = None
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
        return 'aberta', f'conectado {port}'
    except ConnectionRefusedError:
        return 'recusada', f'porta {port} recusada'
    except socket.timeout:
        return 'timeout', f'porta {port}: tempo esgotado'
    except OSError as exc:
        err = getattr(exc, 'winerror', None) or getattr(exc, 'errno', None)
        if err in (10061, 111):  # WSAECONNREFUSED / ECONNREFUSED
            return 'recusada', f'porta {port} recusada'
        if err in (10060, 110):  # WSAETIMEDOUT / ETIMEDOUT
            return 'timeout', f'porta {port}: tempo esgotado'
        return 'erro', f'porta {port}: {exc}'
    except Exception as exc:
        return 'erro', f'porta {port}: {exc}'
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def portas_para_testar(preferida: int) -> list[int]:
    seen = set()
    out = []
    for p in (preferida,) + PORTAS_TCP_COMUNS:
        try:
            n = int(p)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 65535 and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def save_config(cfg: dict) -> None:
    (app_dir() / 'config.json').write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8'
    )


def listar_portas_detalhe() -> list[tuple[str, str]]:
    """Retorna [(COMx, descricao), ...] incluindo serial nativa e USB."""
    if not list_ports:
        return [('COM1', 'Serial nativa (padrão)'), ('COM2', 'Serial nativa')]
    rows = []
    for p in list_ports.comports():
        desc = (p.description or '')
        mfg = (p.manufacturer or '')
        label = f'{desc}'
        if mfg:
            label += f' | {mfg}'
        # marca USB vs nativa de forma simples
        blob = f'{desc} {mfg} {p.hwid or ""}'.lower()
        if 'ftdi' in blob or 'usb' in blob or '0403' in blob or 'ch340' in blob or 'prolific' in blob:
            label = f'[USB] {label}'
        else:
            label = f'[PLACA/SERIAL] {label}'
        rows.append((p.device, label))
    # garante opções clássicas mesmo se o SO não listar
    existentes = {d for d, _ in rows}
    for n in ('COM1', 'COM2', 'COM3', 'COM4'):
        if n not in existentes:
            rows.append((n, f'[MANUAL] {n}'))
    rows.sort(key=lambda x: x[0])
    return rows


def listar_portas() -> list[str]:
    dets = listar_portas_detalhe()
    if dets:
        return [d for d, _ in dets]
    return ['COM1', 'COM2', 'COM3', 'COM4']


def detectar_porta(preferida: str) -> str | None:
    ports = listar_portas()
    if preferida and preferida.upper() != 'AUTO':
        return preferida
    if list_ports:
        for p in list_ports.comports():
            desc = f'{p.description} {p.manufacturer or ""}'.lower()
            if 'ft232' in desc or 'ftdi' in desc or 'uart' in desc:
                return p.device
        if ports:
            return ports[0]
    return None


def _preview_bytes(data: bytes, limite: int = 200) -> str:
    blob = data[:limite]
    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in blob)
    hex_part = ' '.join(f'{b:02X}' for b in blob)
    extra = ' …' if len(data) > limite else ''
    return f'hex={hex_part} ascii={ascii_part}{extra}'


def _log_rx(data: bytes, limite: int = 200) -> str:
    """Log imediato: recebido N bytes hex=... ascii=..."""
    blob = data[:limite]
    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in blob)
    hex_part = ' '.join(f'{b:02X}' for b in blob)
    extra = ' …' if len(data) > limite else ''
    return f'recebido {len(data)} bytes hex={hex_part}{extra} ascii={ascii_part}{extra}'


def _unwrap_connect_frames(data: bytes) -> list[bytes]:
    """Extrai payload de cabeçalho length-prefixed (2 ou 4 bytes, BE/LE) se fizer sentido."""
    out = [data]
    if not data:
        return out
    seen = {data}
    for hdr, endian in ((2, 'big'), (2, 'little'), (4, 'big'), (4, 'little')):
        if len(data) < hdr + 1:
            continue
        n = int.from_bytes(data[:hdr], endian)
        if 1 <= n <= 8192 and hdr + n <= len(data):
            payload = data[hdr:hdr + n]
            if payload and payload not in seen:
                seen.add(payload)
                out.append(payload)
    if b'\x02' in data and b'\x03' in data:
        inner = data.split(b'\x02', 1)[1].split(b'\x03', 1)[0]
        if inner and inner not in seen:
            out.append(inner)
    return out


def _peel_length_frames(buf: bytearray) -> list[bytes]:
    """Consome frames length-prefixed completos de um buffer TCP."""
    frames = []
    while len(buf) >= 2:
        peeled = False
        for hdr, endian in ((2, 'big'), (2, 'little'), (4, 'big'), (4, 'little')):
            if len(buf) < hdr:
                continue
            n = int.from_bytes(bytes(buf[:hdr]), endian)
            if 4 <= n <= 8192 and len(buf) >= hdr + n:
                frames.append(bytes(buf[hdr:hdr + n]))
                del buf[:hdr + n]
                peeled = True
                break
        if not peeled:
            break
    if len(buf) > 8192:
        del buf[: len(buf) - 1024]
    return frames


def _bytes_para_texto(data: bytes) -> str:
    text = bytes(b & 0x7F for b in data).decode('ascii', errors='ignore')
    if not text.strip('\x00'):
        text = data.decode('latin-1', errors='ignore')
    return text


def _comandos_protocolo(cfg: dict) -> list[bytes]:
    proto = str(cfg.get('protocolo_serial') or 'auto').strip().lower()
    if proto == 'uran12':
        return [CMD_URAN12]
    if proto == 'std04':
        return [CMD_STD04]
    return [CMD_URAN12, CMD_STD04, CMD_ENQ]


def _rotulo_protocolo(cfg: dict) -> str:
    return PROTOCOLOS_SERIAL.get(
        str(cfg.get('protocolo_serial') or 'auto').strip().lower(),
        PROTOCOLOS_SERIAL['auto'],
    )


def _aplicar_unidade(peso: float, unit: str | None, sign: str | None) -> float:
    if sign == '-':
        peso = -peso
    u = (unit or 'kg').lower()
    if u == 'g':
        peso = peso / 1000.0
    elif u == 'lb':
        peso = peso * 0.45359237
    return peso


def _peso_de_digitos(digits: str) -> float | None:
    """Campo só numérico (Prot 4 / STX…ETX sem ponto). BA37 visor 000.00."""
    if not digits.isdigit() or not (4 <= len(digits) <= 7):
        return None
    n = int(digits)
    if len(digits) >= 6:
        peso = n / 100.0
        if peso > 80:
            peso = n / 1000.0
    else:
        peso = n / 1000.0
    if abs(peso) > 500:
        return None
    return peso


def parse_peso(linha: str) -> tuple[float | None, str, bool]:
    original = linha or ''
    # 7-bit ASCII (algumas Urano/Toledo ligam o bit 7)
    raw = ''.join(chr(ord(c) & 0x7F) for c in original).replace('\x00', ' ')
    # Urano RS-232/TCP: STX ... ETX (pode vir sem CR/LF)
    if '\x02' in raw and '\x03' in raw:
        inner = raw.split('\x02', 1)[1].split('\x03', 1)[0]
        compact = inner.strip().upper()
        if compact in ('IIIII', 'IIIIII', 'NNNNN', 'NNNNNN', 'SSSSS', 'SSSSSS'):
            return None, original.strip(), False
        if inner.strip():
            compact_inner = inner.strip()
            only = re.sub(r'\D', '', compact_inner)
            if only and only == re.sub(r'\s+', '', compact_inner):
                peso = _peso_de_digitos(only)
                if peso is not None:
                    return peso, original.strip(), True
            peso, _, estavel = parse_peso(inner)
            if peso is not None:
                return peso, original.strip(), estavel
            peso = _peso_de_digitos(only)
            if peso is not None:
                return peso, original.strip(), True
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', raw).strip()
    if not raw:
        return None, original.strip(), False

    m = URANO_STGS_RE.search(raw)
    if m:
        stab = (m.group('stab') or '').upper()
        if stab == 'OL':
            return None, raw, False
        try:
            peso = float(m.group('value').replace(',', '.'))
        except ValueError:
            peso = None
        if peso is not None:
            peso = _aplicar_unidade(peso, m.group('unit'), m.group('sign'))
            return peso, original.strip(), stab == 'ST'

    m = URANO_N0_RE.search(raw)
    if m:
        try:
            peso = float(m.group('value').replace(',', '.'))
        except ValueError:
            peso = None
        if peso is not None:
            peso = _aplicar_unidade(peso, m.group('unit'), m.group('sign'))
            return peso, original.strip(), True

    compact9 = re.sub(r'[\r\n]', '', raw)
    m9 = URANO9_RE.match(compact9)
    if m9:
        try:
            gramas = int(m9.group('digits'))
            peso = gramas / 1000.0
            if m9.group('sign') == '-':
                peso = -peso
            if abs(peso) <= 500:
                return peso, original.strip(), compact9[:1] in ('*', ' ')
        except ValueError:
            pass

    m = PESO_LABEL_RE.search(raw)
    if m:
        try:
            peso = float(m.group('value').replace(',', '.'))
        except ValueError:
            peso = None
        if peso is not None:
            peso = _aplicar_unidade(peso, m.group('unit'), m.group('sign'))
            return peso, original.strip(), True

    # WT1000 contínuo completo: S, bruto, tara, liquido
    m = WT1000_CONTINUOUS_RE.search(raw)
    if m:
        try:
            peso = float(m.group('liq').replace(',', '.'))
        except ValueError:
            peso = None
        if peso is not None:
            estavel = m.group('stab') == '0'
            return peso, raw, estavel

    # WT1000 modo comando: ww010.000kg / Wn010.000kg
    m = WT1000_CMD_RE.search(raw)
    if m:
        try:
            peso = float(m.group('value').replace(',', '.'))
        except ValueError:
            peso = None
        if peso is not None:
            peso = _aplicar_unidade(peso, m.group('unit'), None)
            return peso, raw, True

    estavel = True
    low = raw.lower()
    if any(x in low for x in ('unst', 'unstable', 'instavel', 'mov')):
        estavel = False
    if any(x in low for x in ('stab', 'stable', 'estavel', 'st,', 'st ')):
        estavel = True
    if 'o l' in low or 'ol' == low.replace(' ', ''):
        return None, raw, estavel

    m = PESO_DECIMAL_RE.search(raw)
    if m:
        try:
            peso = float(m.group('value').replace(',', '.'))
        except ValueError:
            peso = None
        if peso is not None:
            peso = _aplicar_unidade(peso, m.group('unit'), m.group('sign'))
            if abs(peso) <= 500000:
                return peso, raw, estavel

    matches = list(WEIGHT_RE.finditer(raw.replace('\x00', ' ')))
    if not matches:
        cleaned = re.sub(r'[^\d.,+\-a-zA-Z ]', ' ', raw)
        matches = list(WEIGHT_RE.finditer(cleaned))
    if not matches:
        peso = _peso_de_digitos(re.sub(r'\D', '', raw))
        if peso is not None:
            return peso, raw, estavel
        return None, raw, estavel

    m = matches[-1]
    val = m.group('value') or ''
    unit = (m.group('unit') or '').lower()
    digits = re.sub(r'\D', '', val)
    if '.' not in val and ',' not in val and not unit:
        peso = _peso_de_digitos(digits)
        if peso is not None:
            return peso, raw, estavel
        if len(digits) < 4:
            peso = _peso_de_digitos(re.sub(r'\D', '', raw))
            if peso is not None:
                return peso, raw, estavel
            return None, raw, estavel
    try:
        peso = float(val.replace(',', '.'))
    except ValueError:
        return None, raw, estavel
    peso = _aplicar_unidade(peso, unit or 'kg', m.group('sign'))
    if abs(peso) > 500000:
        return None, raw, estavel
    return peso, raw, estavel


def formatar_peso_ui(peso: float | None) -> str:
    """Somente o visor: 3 dígitos inteiros + 2 decimais (000.00). Não altera o valor gravado."""
    if peso is None:
        return '000.00'
    try:
        p = float(peso)
    except (TypeError, ValueError):
        return '000.00'
    if p < 0:
        return f'-{abs(p):06.2f}'
    return f'{p:06.2f}'


# Segmentos LED: a=topo, b=dir-sup, c=dir-inf, d=base, e=esq-inf, f=esq-sup, g=meio
_SEG_MAP = {
    '0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
    '5': 'afgcd', '6': 'afgecd', '7': 'abc', '8': 'abcdefg', '9': 'abfgcd',
    '-': 'g', ' ': '',
}


class LedPesoDisplay(tk.Frame):
    """Visor estilo 7 segmentos da Urano: Peso | dígitos vermelhos | kg."""

    def __init__(self, parent):
        super().__init__(parent, bg=CLR_LED_BG)
        hdr = tk.Frame(self, bg=CLR_LED_BG)
        hdr.pack(fill='x', padx=12, pady=(10, 0))
        self._led_status = tk.Canvas(hdr, width=16, height=16, bg=CLR_LED_BG, highlightthickness=0, bd=0)
        self._led_status.pack(side='left', padx=(0, 10))
        self._led_status.create_oval(2, 2, 14, 14, fill=CLR_LED_ON, outline='#990000', tags='dot')
        tk.Label(hdr, text='Peso', font=FONT_LED_LABEL, fg=CLR_LED_ON, bg=CLR_LED_BG).pack(side='left')
        tk.Label(hdr, text='kg', font=FONT_LED_LABEL, fg=CLR_LED_ON, bg=CLR_LED_BG).pack(side='right')
        self.canvas = tk.Canvas(self, bg=CLR_LED_BG, highlightthickness=0, bd=0, height=260)
        self.canvas.pack(fill='both', expand=True, padx=10, pady=(6, 14))
        self.canvas.bind('<Configure>', lambda e: self._redraw())
        self._texto = '000.00'
        self._aceso = True

    def set_peso(self, peso: float | None, aceso: bool = True):
        self._texto = formatar_peso_ui(peso)
        self._aceso = bool(aceso)
        self._redraw()

    def _redraw(self, _evt=None):
        c = self.canvas
        c.delete('all')
        w = max(int(c.winfo_width()), 280)
        h = max(int(c.winfo_height()), 180)
        texto = self._texto or '000.00'
        on = CLR_LED_ON if self._aceso else '#CC1515'
        weights = [0.28 if ch == '.' else 1.0 for ch in texto]
        total = sum(weights) or 1.0
        unit = w / (total + 0.22)
        digit_w = unit * 0.90
        x = (w - total * unit) / 2
        y0 = h * 0.06
        dh = h * 0.88
        for ch, wt in zip(texto, weights):
            slot = wt * unit
            if ch == '.':
                r = max(7, min(unit, dh) * 0.09)
                cy = y0 + dh - r * 1.05
                cx = x + slot * 0.45
                c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=on, outline=on)
            else:
                self._draw_digit(c, x + (slot - digit_w) / 2, y0, digit_w, dh, ch, on)
            x += slot
        fill = on if self._aceso else '#5A0000'
        self._led_status.itemconfigure('dot', fill=fill, outline='#990000')

    def _draw_digit(self, c: tk.Canvas, x: float, y: float, w: float, h: float, ch: str, on: str):
        t = max(5.0, min(w, h) * 0.15)
        pad = t * 0.32
        lit = set(_SEG_MAP.get(ch, ''))
        segs = {
            'a': self._hseg(x + pad, y, w - 2 * pad, t),
            'g': self._hseg(x + pad, y + h / 2 - t / 2, w - 2 * pad, t),
            'd': self._hseg(x + pad, y + h - t, w - 2 * pad, t),
            'f': self._vseg(x, y + pad, t, h / 2 - pad),
            'b': self._vseg(x + w - t, y + pad, t, h / 2 - pad),
            'e': self._vseg(x, y + h / 2, t, h / 2 - pad),
            'c': self._vseg(x + w - t, y + h / 2, t, h / 2 - pad),
        }
        for name, pts in segs.items():
            color = on if name in lit else CLR_LED_OFF
            c.create_polygon(pts, fill=color, outline=color, smooth=False)

    @staticmethod
    def _hseg(x, y, w, t):
        n = t * 0.45
        return (
            x + n, y,
            x + w - n, y,
            x + w, y + t / 2,
            x + w - n, y + t,
            x + n, y + t,
            x, y + t / 2,
        )

    @staticmethod
    def _vseg(x, y, t, h):
        n = t * 0.45
        return (
            x + t / 2, y,
            x + t, y + n,
            x + t, y + h - n,
            x + t / 2, y + h,
            x, y + h - n,
            x, y + n,
        )


def sunken(parent, **kw):
    f = tk.Frame(parent, bg=CLR_WHITE, highlightthickness=0, **kw)
    # borda estilo Windows sunken
    outer = tk.Frame(parent, bg=CLR_SHADOW, padx=1, pady=1)
    inner = tk.Frame(outer, bg=CLR_LIGHT, padx=1, pady=1)
    f = tk.Frame(inner, bg=CLR_WHITE)
    inner.pack(fill='both', expand=True)
    f.pack(fill='both', expand=True)
    return outer, f


class BalancaReader(threading.Thread):
    """Lê peso via COM serial, TCP (balança de rede) ou simulação. Mesmo parse_peso."""

    def __init__(self, cfg: dict, out_q: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.cfg = dict(cfg)
        self.out_q = out_q
        self.stop_event = stop_event
        self._rx_ethernet = 0

    def run(self):
        if self.cfg.get('modo_simulacao'):
            self._run_sim()
            return
        tipo = str(self.cfg.get('conexao_tipo') or 'serial').strip().lower()
        if tipo == 'escuta':
            self._run_tcp_listen()
            return
        if tipo == 'rede':
            self._run_tcp()
            return
        self._run_serial()

    def _run_serial(self):
        if serial is None:
            self.out_q.put(('status', 'pyserial não instalado'))
            return

        porta = detectar_porta(self.cfg.get('porta_com', 'AUTO'))
        if not porta:
            self.out_q.put(('status', 'Nenhuma porta COM. Configure em Configuração.'))
            return

        self.out_q.put(('porta', porta))
        baud = int(self.cfg.get('baudrate', 9600))
        try:
            sb = float(self.cfg.get('stopbits', 2) or 2)
        except (TypeError, ValueError):
            sb = 2
        stop_map = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}
        try:
            parity_map = {'N': serial.PARITY_NONE, 'E': serial.PARITY_EVEN, 'O': serial.PARITY_ODD}
            ser = serial.Serial(
                port=porta,
                baudrate=baud,
                bytesize=int(self.cfg.get('bytesize', 8)),
                parity=parity_map.get(str(self.cfg.get('parity', 'N')).upper(), serial.PARITY_NONE),
                stopbits=stop_map.get(sb, serial.STOPBITS_TWO),
                timeout=0.05,
            )
        except Exception as exc:
            msg = str(exc).lower()
            if 'permission' in msg or 'acesso negado' in msg or 'denied' in msg:
                self.out_q.put(('status', f'Porta {porta} ocupada. Feche outro programa e reabra.'))
            else:
                self.out_q.put(('status', f'Erro {porta}: {exc}'))
            return

        proto = _rotulo_protocolo(self.cfg)
        self.out_q.put(('status', f'Conectado {porta} @ {baud} 8N{int(sb)} — peso ao vivo {proto}'))
        try:
            self._loop_bytes(
                origem=porta,
                write_fn=ser.write,
                read_fn=lambda: ser.read(ser.in_waiting or 1),
            )
        finally:
            try:
                ser.close()
            except Exception:
                pass
            self.out_q.put(('status', 'Serial desconectada'))

    def _run_tcp(self):
        ip = str(self.cfg.get('balanca_ip') or '').strip()
        try:
            port = int(self.cfg.get('balanca_porta_tcp') or PORTA_TCP_PADRAO)
        except (TypeError, ValueError):
            port = PORTA_TCP_PADRAO
        if not ip:
            self.out_q.put(('status', 'Informe o IP da balança em Configuração (F2).'))
            return
        if not (1 <= port <= 65535):
            self.out_q.put(('status', f'Porta TCP inválida: {port}'))
            return

        timeout = float(self.cfg.get('timeout', 1.0)) or 1.0
        portas = portas_para_testar(port)
        porta_ok = None
        udp_thread = threading.Thread(
            target=self._run_udp_listen, args=(ip,), daemon=True, name='udp-urano-connect',
        )
        udp_thread.start()

        while not self.stop_event.is_set():
            sock = None
            alvos = [porta_ok] if porta_ok else portas
            conectou = False
            for p in alvos:
                if self.stop_event.is_set():
                    break
                origem = f'{ip}:{p}'
                self.out_q.put(('porta', origem))
                self.out_q.put(('status', f'Tentando TCP {origem}...'))
                try:
                    sock = socket.create_connection((ip, p), timeout=2.5 if porta_ok is None else 8)
                    sock.settimeout(min(0.4, timeout) if timeout > 0 else 0.4)
                    try:
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    except OSError:
                        pass
                    porta_ok = p
                    conectou = True
                    self.out_q.put(('status', f'conectado {p} — {HINT_TCP_CONNECT}'))
                    self._loop_bytes_socket(sock, origem)
                    break
                except ConnectionRefusedError:
                    self.out_q.put(('status', f'porta {p} recusada'))
                except socket.timeout:
                    self.out_q.put(('status', f'porta {p}: tempo esgotado'))
                except OSError as exc:
                    self.out_q.put(('status', f'porta {p}: {exc}'))
                except Exception as exc:
                    self.out_q.put(('status', f'TCP {origem}: {exc}'))
                finally:
                    if sock is not None and not conectou:
                        try:
                            sock.close()
                        except Exception:
                            pass
                        sock = None
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            if not conectou:
                porta_ok = None
                self.out_q.put((
                    'status',
                    'Nenhuma porta TCP aberta. A BA37 pode estar em modo cliente — '
                    'em Configuração escolha “Balança conecta neste PC”.',
                ))
            if self.stop_event.wait(3.0):
                break
        self.out_q.put(('status', 'TCP desconectado'))

    def _run_tcp_paralelo(self, ip: str, port: int):
        """Spec 167 = 33582 (cliente). Tenta em paralelo se 33581 aceitar TCP sem bytes."""
        origem = f'{ip}:{port}'
        self.out_q.put((
            'status',
            f'Tentando também TCP {origem} (spec 166=33581 servidor / spec 167=33582 cliente)...',
        ))
        sock = None
        try:
            sock = socket.create_connection((ip, port), timeout=2.5)
            sock.settimeout(0.4)
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass
            self.out_q.put(('status', f'conectado {port} em paralelo — lendo bytes'))
            self._loop_bytes_socket(sock, origem)
        except ConnectionRefusedError:
            self.out_q.put((
                'status',
                f'porta {port} recusada — normal no modo servidor (33582 é a porta em que a balança conecta neste PC)',
            ))
        except socket.timeout:
            self.out_q.put(('status', f'porta {port}: tempo esgotado'))
        except Exception as exc:
            self.out_q.put(('status', f'TCP paralelo {origem}: {exc}'))
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def _abrir_udp(self, porta: int) -> socket.socket | None:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except OSError:
                pass
            udp.bind(('0.0.0.0', porta))
            udp.setblocking(False)
            return udp
        except OSError as exc:
            self.out_q.put(('status', f'UDP {porta}: não abriu ({exc}). Feche o Urano Connect ou permita o firewall.'))
            try:
                udp.close()
            except Exception:
                pass
            return None

    def _handshake_connect_udp(self, ip: str, socks: list[tuple[int, socket.socket]]):
        """Um anúncio UDP no listen da balança (spec 168=33583). Sem ENQ em loop."""
        if not ip:
            return
        remetente = None
        for porta, sock in socks:
            if porta == PORTA_UDP_BROADCAST:
                remetente = sock
                break
        if remetente is None and socks:
            remetente = socks[0][1]
        if remetente is None:
            return
        destinos = (
            (ip, PORTA_UDP_LISTEN),
            ('255.255.255.255', PORTA_UDP_LISTEN),
            (ip, PORTA_UDP_BROADCAST),
        )
        enviados = 0
        for dest in destinos:
            try:
                remetente.sendto(HANDSHAKE_UDP_CONNECT, dest)
                enviados += 1
            except OSError:
                pass
        if enviados:
            self.out_q.put((
                'status',
                f'handshake UDP único {enviados} destinos '
                f'(spec 168={PORTA_UDP_LISTEN} listen / spec 169={PORTA_UDP_BROADCAST} broadcast) '
                f'frame={HANDSHAKE_UDP_CONNECT.hex()} — sem ENQ',
            ))

    def _run_udp_listen(self, ip: str):
        """Escuta contínua UDP 33583 e 33584 (manual BA37 spec 168/169). Print pode ir UDP."""
        if self.stop_event.is_set():
            return
        socks: list[tuple[int, socket.socket]] = []
        for porta in (PORTA_UDP_LISTEN, PORTA_UDP_BROADCAST):
            udp = self._abrir_udp(porta)
            if udp is not None:
                socks.append((porta, udp))
                spec = '168' if porta == PORTA_UDP_LISTEN else '169'
                self.out_q.put(('status', f'UDP escutando 0.0.0.0:{porta} (spec {spec})'))
        if not socks:
            self.out_q.put(('status', 'UDP: nenhuma porta 33583/33584 aberta neste PC'))
            return
        self._handshake_connect_udp(ip, socks)
        try:
            while not self.stop_event.is_set():
                ready = [s for _, s in socks]
                try:
                    readable, _, _ = select.select(ready, [], [], 0.4)
                except (ValueError, OSError):
                    break
                for udp in readable:
                    try:
                        data, addr = udp.recvfrom(8192)
                    except (BlockingIOError, InterruptedError, OSError):
                        continue
                    if not data:
                        continue
                    porta_local = udp.getsockname()[1]
                    origem = f'UDP:{addr[0]}:{addr[1]}→{porta_local}'
                    self._tratar_bytes(data, origem)
        finally:
            for _, udp in socks:
                try:
                    udp.close()
                except Exception:
                    pass
            self.out_q.put(('status', 'UDP 33583/33584 encerrado'))

    def _run_tcp_listen(self):
        """BA37 spec 43=2 modo cliente: a balança conecta neste PC (spec 167 = 33582)."""
        try:
            port = int(self.cfg.get('balanca_porta_tcp') or PORTA_ESCUTA_PADRAO)
        except (TypeError, ValueError):
            port = PORTA_ESCUTA_PADRAO
        if not (1 <= port <= 65535):
            self.out_q.put(('status', f'Porta de escuta inválida: {port}'))
            return

        ports = [port]
        if port in (PORTA_TCP_PADRAO, PORTA_ESCUTA_PADRAO):
            for extra in (PORTA_TCP_PADRAO, PORTA_ESCUTA_PADRAO):
                if extra not in ports:
                    ports.append(extra)

        servers = []
        for p in ports:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(('0.0.0.0', p))
                srv.listen(4)
                srv.setblocking(False)
                servers.append((p, srv))
                self.out_q.put(('status', f'Escutando 0.0.0.0:{p} (balança conecta neste PC)'))
            except OSError as exc:
                self.out_q.put(('status', f'Não foi possível abrir a escuta na porta {p}: {exc}'))
                try:
                    srv.close()
                except Exception:
                    pass
        if not servers:
            self.out_q.put(('status', 'Falha ao escutar. Feche outro programa ou permita o firewall.'))
            return

        self.out_q.put(('porta', f'ESCUTA:{",".join(str(p) for p, _ in servers)}'))
        ip_balanca = str(self.cfg.get('balanca_ip') or '').strip()
        threading.Thread(
            target=self._run_udp_listen, args=(ip_balanca,), daemon=True, name='udp-urano-escuta',
        ).start()
        pc_ip = '192.168.1.179'
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('192.168.1.127', 80))
            pc_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass
        self.out_q.put((
            'status',
            f'Aguardando a balança conectar neste PC ({pc_ip}). '
            'Na BA37: spec 43 = modo cliente (2), specs 154-157 = IP deste computador, '
            'spec 167 = 33582. Se o Windows pedir firewall, permita o AgentePesagem.',
        ))
        try:
            while not self.stop_event.is_set():
                socks = [s for _, s in servers]
                try:
                    readable, _, _ = select.select(socks, [], [], 0.4)
                except (ValueError, OSError):
                    break
                for srv in readable:
                    conn = None
                    try:
                        conn, addr = srv.accept()
                    except OSError:
                        continue
                    porta_local = conn.getsockname()[1]
                    origem = f'{addr[0]}:{addr[1]}→{porta_local}'
                    self.out_q.put(('porta', origem))
                    self.out_q.put(('status', f'conectado {porta_local} (balança {addr[0]}:{addr[1]}) — escutando [Imprimir]/[Modo Autom.]'))
                    try:
                        conn.settimeout(0.4)
                        try:
                            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        except OSError:
                            pass
                        self._loop_bytes_socket(conn, origem)
                    except Exception as exc:
                        self.out_q.put(('status', f'TCP escuta: {exc}'))
                    finally:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        self.out_q.put(('status', 'Balança desconectou — aguardando nova conexão'))
        finally:
            for _, srv in servers:
                try:
                    srv.close()
                except Exception:
                    pass
            self.out_q.put(('status', 'Escuta TCP encerrada'))

    def _loop_bytes_socket(self, sock: socket.socket, origem: str):
        def _write(data: bytes):
            sock.sendall(data)

        def _read():
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                return b''
            if not chunk:
                raise ConnectionError('conexão encerrada pela balança')
            return chunk

        self._loop_bytes(
            origem=origem, write_fn=_write, read_fn=_read,
            eof_raises=True, modo_tcp=True,
        )

    def _tratar_bytes(self, raw_bytes: bytes, origem: str) -> None:
        """Qualquer datagrama/byte: log imediato + parse de peso (ASCII e frame length-prefixed)."""
        if not raw_bytes:
            return
        self.out_q.put(('status', _log_rx(raw_bytes)))
        self._rx_ethernet += 1
        for payload in _unwrap_connect_frames(raw_bytes):
            self._emit(_bytes_para_texto(payload), origem)

    def _loop_bytes(self, origem: str, write_fn, read_fn, eof_raises: bool = False, modo_tcp: bool = False):
        buffer = ''
        bin_buf = bytearray()
        last_poll = 0.0
        last_partial = 0.0
        last_rx = time.time()
        last_parse_log = 0.0
        cmd_idx = 0
        rx_count = 0
        hint_serial = False
        hint_imprimir = False
        dump_limite = 4
        if modo_tcp:
            consultar = False
            cmds: list[bytes] = []
            poll_every = 1.0
        else:
            consultar = True
            cmds = _comandos_protocolo(self.cfg)
            poll_every = float(self.cfg.get('intervalo_consulta_seg', 0.3) or 0.3)
            poll_every = min(max(poll_every, 0.2), 0.5)

        while not self.stop_event.is_set():
            agora = time.time()
            if consultar and cmds and (agora - last_poll) >= poll_every:
                try:
                    cmd = cmds[cmd_idx % len(cmds)]
                    cmd_idx += 1
                    write_fn(cmd)
                except Exception:
                    if eof_raises:
                        raise
                last_poll = agora

            try:
                chunk = read_fn()
            except Exception as exc:
                if eof_raises:
                    raise
                self.out_q.put(('status', f'Erro leitura: {exc}'))
                time.sleep(1)
                continue

            if chunk:
                last_rx = agora
                raw_bytes = bytes(chunk) if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode('latin-1', errors='ignore')
                if modo_tcp:
                    self._tratar_bytes(raw_bytes, origem)
                    bin_buf.extend(raw_bytes)
                    for frame in _peel_length_frames(bin_buf):
                        self._emit(_bytes_para_texto(frame), origem)
                else:
                    if rx_count < dump_limite:
                        self.out_q.put(('status', _log_rx(raw_bytes)))
                    self._emit(_bytes_para_texto(raw_bytes), origem)
                rx_count += 1
                buffer += _bytes_para_texto(raw_bytes)
                if b'\x02' in raw_bytes or b'\x03' in raw_bytes:
                    try:
                        write_fn(b'\x06')
                    except Exception:
                        if eof_raises:
                            raise

            while True:
                consumed = False
                i0, i1 = buffer.find('\x02'), buffer.find('\x03')
                if i0 >= 0 and i1 > i0:
                    self._emit(buffer[i0:i1 + 1], origem)
                    buffer = buffer[i1 + 1:]
                    consumed = True
                for sep in ('\n', '\r'):
                    if sep in buffer:
                        linha, buffer = buffer.split(sep, 1)
                        self._emit(linha, origem)
                        consumed = True
                        break
                if not consumed:
                    break

            if len(buffer) >= 4 and (agora - last_partial) >= 0.25:
                before = buffer
                self._emit(buffer[-120:], origem)
                if len(buffer) > 200:
                    buffer = buffer[-100:]
                last_partial = agora
                if modo_tcp and parse_peso(before[-120:])[0] is None and (agora - last_parse_log) >= 4.0:
                    last_parse_log = agora
                    self.out_q.put((
                        'status',
                        f'telegrama sem peso: {_preview_bytes(before[-80:].encode("latin-1", errors="ignore"))}',
                    ))

            if not modo_tcp and rx_count == 0 and (agora - last_rx) >= 5.0 and not hint_serial:
                hint_serial = True
                self.out_q.put(('status', HINT_SERIAL_SILENCIO))

            if modo_tcp and self._rx_ethernet == 0 and (agora - last_rx) >= 30.0 and not hint_imprimir:
                hint_imprimir = True
                self.out_q.put(('status', HINT_IMPRIMIR_SILENCIO))

            if not chunk:
                time.sleep(0.03)

    def _emit(self, linha: str, porta: str) -> bool:
        peso, bruto, estavel = parse_peso(linha)
        if peso is None:
            return False
        self.out_q.put(('peso', {
            'peso': peso, 'bruto': bruto, 'estavel': estavel, 'porta': porta
        }))
        return True

    def _run_sim(self):
        self.out_q.put(('porta', 'SIM'))
        self.out_q.put(('status', 'Simulação — peso muda sozinho'))
        n = 0
        while not self.stop_event.is_set():
            n += 1
            peso = round(5.0 + (n % 20) * 0.375, 3)
            self.out_q.put(('peso', {
                'peso': peso, 'bruto': f'SIM {peso:.3f} kg',
                'estavel': True, 'porta': 'SIM'
            }))
            time.sleep(0.9)


SerialReader = BalancaReader


class ConfigDialog(tk.Toplevel):
    """Janela de configuração estilo Delphi."""

    def __init__(self, master, cfg: dict, on_save):
        super().__init__(master)
        self.cfg = dict(cfg)
        self.on_save = on_save
        self.title('Configuração — Controle de Pesagem')
        self.configure(bg=CLR_BG)
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()
        _aplicar_icone(self)

        btns = tk.Frame(self, bg=CLR_BG, padx=10, pady=8)
        btns.pack(side='bottom', fill='x')
        tk.Button(
            btns, text='OK (salvar)', width=14, font=FONT_UI, bg=CLR_BTN, command=self._ok
        ).pack(side='right', padx=4)
        tk.Button(btns, text='Cancelar', width=10, font=FONT_UI, bg=CLR_BTN, command=self.destroy).pack(side='right')

        nb = tk.Frame(self, bg=CLR_BG, padx=10, pady=8)
        nb.pack(fill='both', expand=True)

        self._section(nb, 'Identificação da balança / local')
        self.var_codigo = self._field(nb, 'Código da balança', self.cfg.get('balanca_codigo', 'BAL-01'))
        self.var_nome = self._field(nb, 'Nome', self.cfg.get('balanca_nome', 'BA37'))
        self.var_local = self._field(nb, 'Localização', self.cfg.get('balanca_local', ''))

        self._section(nb, 'Tipo de conexão')
        tk.Label(
            nb, text=HINT_CONEXAO,
            font=('Tahoma', 8), fg=CLR_DARK, bg=CLR_BG, anchor='w', justify='left', wraplength=500,
        ).pack(fill='x', pady=(0, 4))
        tipo_ini = str(self.cfg.get('conexao_tipo') or 'serial').strip().lower()
        if tipo_ini not in ('serial', 'rede', 'escuta'):
            tipo_ini = 'serial'
        self.var_tipo = tk.StringVar(value=tipo_ini)
        row_tipo = tk.Frame(nb, bg=CLR_BG)
        row_tipo.pack(fill='x', pady=2)
        tk.Radiobutton(
            row_tipo, text='Peso ao vivo (Urano RS-232)', variable=self.var_tipo, value='serial',
            bg=CLR_BG, font=FONT_UI, command=self._mostrar_conexao, anchor='w'
        ).pack(side='left', padx=(0, 12))
        tk.Radiobutton(
            row_tipo, text='Ethernet (etiqueta)', variable=self.var_tipo, value='rede',
            bg=CLR_BG, font=FONT_UI, command=self._mostrar_conexao, anchor='w'
        ).pack(side='left', padx=(0, 12))
        tk.Radiobutton(
            row_tipo, text='Balança conecta neste PC', variable=self.var_tipo, value='escuta',
            bg=CLR_BG, font=FONT_UI, command=self._mostrar_conexao, anchor='w'
        ).pack(side='left')

        self.frm_conexao = tk.Frame(nb, bg=CLR_BG)
        self.frm_conexao.pack(fill='x')
        self.frm_serial = tk.Frame(self.frm_conexao, bg=CLR_BG)
        detalhes = listar_portas_detalhe()
        ports = [d for d, _ in detalhes] or ['COM1', 'COM2', 'COM3', 'COM4']
        porta_atual = self.cfg.get('porta_com', 'COM1')
        if porta_atual not in ports and porta_atual != 'AUTO':
            ports = [porta_atual] + ports
        if 'AUTO' not in ports:
            ports = ['AUTO'] + ports
        self.var_porta = tk.StringVar(value=porta_atual)
        row = tk.Frame(self.frm_serial, bg=CLR_BG)
        row.pack(fill='x', pady=2)
        tk.Label(row, text='Porta serial (COM)', width=18, anchor='w', bg=CLR_BG, font=FONT_UI).pack(side='left')
        self.cmb_porta = tk.OptionMenu(row, self.var_porta, *ports)
        self.cmb_porta.config(font=FONT_UI, bg=CLR_BTN)
        self.cmb_porta.pack(side='left', fill='x', expand=True)
        tk.Button(row, text='Atualizar', font=FONT_UI, bg=CLR_BTN, command=self._refresh_ports).pack(side='left', padx=4)
        proto_keys = list(PROTOCOLOS_SERIAL.keys())
        proto_labels = [PROTOCOLOS_SERIAL[k] for k in proto_keys]
        proto_atual = str(self.cfg.get('protocolo_serial') or 'auto').strip().lower()
        if proto_atual not in PROTOCOLOS_SERIAL:
            proto_atual = 'auto'
        self.var_proto = tk.StringVar(value=PROTOCOLOS_SERIAL[proto_atual])
        row_proto = tk.Frame(self.frm_serial, bg=CLR_BG)
        row_proto.pack(fill='x', pady=2)
        tk.Label(row_proto, text='Protocolo', width=18, anchor='w', bg=CLR_BG, font=FONT_UI).pack(side='left')
        self.cmb_proto = tk.OptionMenu(row_proto, self.var_proto, *proto_labels)
        self.cmb_proto.config(font=FONT_UI, bg=CLR_BTN)
        self.cmb_proto.pack(side='left', fill='x', expand=True)
        self.var_baud = self._field(self.frm_serial, 'Baud rate', str(self.cfg.get('baudrate', 9600)))
        self.var_stop = self._field(self.frm_serial, 'Stop bits', str(int(float(self.cfg.get('stopbits', 2) or 2))))
        self.lbl_serial_hint = tk.Label(
            self.frm_serial,
            text='Peso ao vivo: cabo RS-232 na COM, protocolo Uran12 ou STD04, 9600 8N2. '
                 'Ethernet não atualiza o visor — só etiqueta ao [Imprimir].',
            font=('Tahoma', 8), fg=CLR_DARK, bg=CLR_BG, anchor='w', justify='left', wraplength=460,
        )
        self.lbl_serial_hint.pack(fill='x', pady=(0, 4))

        self.frm_rede = tk.Frame(self.frm_conexao, bg=CLR_BG)
        self.var_ip = self._field(self.frm_rede, 'IP da balança', str(self.cfg.get('balanca_ip') or ''))
        self.var_porta_tcp = self._field(
            self.frm_rede, 'Porta TCP', str(self.cfg.get('balanca_porta_tcp') or PORTA_TCP_PADRAO)
        )
        self.lbl_rede_hint = tk.Label(
            self.frm_rede,
            text='',
            font=('Tahoma', 8), fg=CLR_DARK, bg=CLR_BG, anchor='w', justify='left', wraplength=460
        )
        self.lbl_rede_hint.pack(fill='x', pady=(0, 4))

        row_test = tk.Frame(self.frm_conexao, bg=CLR_BG)
        self.frm_test = row_test
        row_test.pack(fill='x', pady=(8, 2))
        self.btn_testar = tk.Button(
            row_test, text='Testar conexão', font=FONT_UI, bg=CLR_BTN,
            command=self._testar_conexao
        )
        self.btn_testar.pack(side='left')
        self.btn_scan = tk.Button(
            row_test, text='Testar todas as portas', font=FONT_UI, bg=CLR_BTN,
            command=self._testar_todas_portas
        )
        self.btn_scan.pack(side='left', padx=(8, 0))
        self.cnv_ind = tk.Canvas(
            row_test, width=20, height=20, bg=CLR_BG, highlightthickness=0, bd=0
        )
        self.cnv_ind.pack(side='left', padx=(10, 4))
        self.lbl_ind = tk.Label(
            row_test, text='-', font=('Tahoma', 16, 'bold'), bg=CLR_BG, width=2, anchor='w'
        )
        self.lbl_ind.pack(side='left')
        self.lbl_test_msg = tk.Label(
            row_test, text='', font=FONT_UI, bg=CLR_BG, anchor='w'
        )
        self.lbl_test_msg.pack(side='left', fill='x', expand=True)
        self._test_seq = 0
        self.var_tipo.trace_add('write', lambda *_: self._limpar_indicador())
        self.var_ip.trace_add('write', lambda *_: self._limpar_indicador())
        self.var_porta_tcp.trace_add('write', lambda *_: self._limpar_indicador())
        self.var_porta.trace_add('write', lambda *_: self._limpar_indicador())
        self._limpar_indicador()

        self.var_sim = tk.BooleanVar(value=bool(self.cfg.get('modo_simulacao', False)))
        tk.Checkbutton(
            nb, text='Modo simulação (sem balança física)',
            variable=self.var_sim, bg=CLR_BG, font=FONT_UI, anchor='w'
        ).pack(fill='x', pady=4)

        self._section(nb, 'Servidor')
        self.var_url = self._field(nb, 'URL do servidor', self.cfg.get('servidor_url', SERVIDOR_PADRAO))
        self.var_key = self._field(nb, 'API Key', self.cfg.get('api_key', ''))
        self.var_auto = tk.BooleanVar(value=bool(self.cfg.get('envio_automatico', False)))
        tk.Checkbutton(
            nb, text='Enviar automaticamente ao estabilizar o peso',
            variable=self.var_auto, bg=CLR_BG, font=FONT_UI, anchor='w'
        ).pack(fill='x', pady=4)

        self._mostrar_conexao()
        self.update_idletasks()
        w = max(600, self.winfo_reqwidth())
        h = max(self.winfo_reqheight(), 500)
        x = master.winfo_rootx() + 40
        y = master.winfo_rooty() + 40
        self.geometry(f'{w}x{h}+{x}+{y}')
        self.minsize(560, 420)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def _section(self, parent, title):
        tk.Label(parent, text=title, font=FONT_TITLE, fg=CLR_NAVY, bg=CLR_BG, anchor='w').pack(fill='x', pady=(10, 4))
        tk.Frame(parent, bg=CLR_SHADOW, height=1).pack(fill='x', pady=(0, 6))

    def _field(self, parent, label, value):
        row = tk.Frame(parent, bg=CLR_BG)
        row.pack(fill='x', pady=2)
        tk.Label(row, text=label, width=18, anchor='w', bg=CLR_BG, font=FONT_UI).pack(side='left')
        var = tk.StringVar(value=value)
        ent = tk.Entry(row, textvariable=var, font=FONT_UI, bg=CLR_WHITE, relief='sunken')
        ent.pack(side='left', fill='x', expand=True)
        return var

    def _mostrar_conexao(self):
        self.frm_serial.pack_forget()
        self.frm_rede.pack_forget()
        tipo = self.var_tipo.get()
        if tipo in ('rede', 'escuta'):
            self.frm_rede.pack(fill='x')
            if tipo == 'escuta':
                try:
                    atual = int(str(self.var_porta_tcp.get() or '').strip() or '0')
                except ValueError:
                    atual = 0
                if atual in (0, PORTA_TCP_PADRAO):
                    self.var_porta_tcp.set(str(PORTA_ESCUTA_PADRAO))
                self.lbl_rede_hint.configure(
                    text='BA37 modo cliente (spec 43=2): a balança liga neste PC na porta 33582 '
                    '(spec 167). Este programa escuta 33581 e 33582. IP da balança é opcional.'
                )
            else:
                self.lbl_rede_hint.configure(
                    text='Ethernet: TCP 33581 + UDP 33583/33584 (Urano Connect). '
                    'O TCP conecta, mas o peso só chega se [Imprimir] for enviado à rede/PC '
                    '(não só à impressora da balança). Spec 43=2 + IP deste PC (154-157) '
                    'ou P42 export Ethernet. Visor ao vivo: RS-232.'
                )
        else:
            self.frm_serial.pack(fill='x')
        if getattr(self, 'frm_test', None):
            self.frm_test.pack_forget()
            self.frm_test.pack(fill='x', pady=(8, 2))
        self._limpar_indicador()

    def _limpar_indicador(self):
        if not getattr(self, 'cnv_ind', None):
            return
        self.cnv_ind.delete('all')
        self.cnv_ind.create_oval(3, 3, 17, 17, fill='#C0C0C0', outline='#808080')
        self.lbl_ind.configure(text='-', fg='#808080')
        self.lbl_test_msg.configure(text='', fg=CLR_DARK)

    def _set_indicador(self, ok: bool | None, msg: str = ''):
        if not self.winfo_exists():
            return
        self.cnv_ind.delete('all')
        if ok is None:
            self.cnv_ind.create_oval(3, 3, 17, 17, fill='#808080', outline='#606060')
            self.lbl_ind.configure(text='…', fg='#606060')
            self.lbl_test_msg.configure(text=msg or 'Testando...', fg=CLR_DARK)
            return
        if ok:
            self.cnv_ind.create_oval(3, 3, 17, 17, fill='#22A312', outline='#1A7A0E')
            self.lbl_ind.configure(text='v', fg='#1A7A0E')
            self.lbl_test_msg.configure(text=msg or 'Conexão estabelecida', fg='#1A7A0E')
        else:
            self.cnv_ind.create_oval(3, 3, 17, 17, fill='#CC0000', outline='#990000')
            self.lbl_ind.configure(text='x', fg='#CC0000')
            self.lbl_test_msg.configure(text=msg or 'Conexão não estabelecida', fg='#CC0000')

    def _testar_conexao(self):
        tipo = (self.var_tipo.get() or 'serial').strip().lower()
        self._test_seq += 1
        seq = self._test_seq
        self.btn_testar.configure(state='disabled')
        if getattr(self, 'btn_scan', None):
            self.btn_scan.configure(state='disabled')
        self._set_indicador(None, 'Testando...')

        if tipo in ('rede', 'escuta'):
            ip = self.var_ip.get().strip()
            try:
                port = int(str(self.var_porta_tcp.get() or PORTA_TCP_PADRAO).strip())
            except ValueError:
                self._fim_teste()
                self._set_indicador(False, 'Porta TCP inválida')
                return
            if tipo == 'rede' and not ip:
                self._fim_teste()
                self._set_indicador(False, 'Informe o IP da balança')
                return
            if not (1 <= port <= 65535):
                self._fim_teste()
                self._set_indicador(False, 'Porta TCP inválida')
                return
            if tipo == 'escuta':
                threading.Thread(target=self._test_escuta, args=(port, seq), daemon=True).start()
            else:
                threading.Thread(target=self._test_tcp, args=(ip, port, seq), daemon=True).start()
            return

        porta = (self.var_porta.get() or '').strip()
        try:
            baud = int(self.var_baud.get().strip() or '9600')
        except ValueError:
            baud = 9600
        try:
            sb = float(str(self.var_stop.get() or '2').strip().replace(',', '.'))
        except (TypeError, ValueError, AttributeError):
            sb = 2
        threading.Thread(target=self._test_serial, args=(porta, baud, seq, sb), daemon=True).start()

    def _fim_teste(self):
        if not self.winfo_exists():
            return
        self.btn_testar.configure(state='normal')
        if getattr(self, 'btn_scan', None):
            self.btn_scan.configure(state='normal')

    def _aplicar_teste(self, seq: int, ok: bool | None, msg: str, porta_ok: int | None = None):
        def apply():
            if not self.winfo_exists() or seq != self._test_seq:
                return
            if ok is not None:
                self._fim_teste()
                if ok and porta_ok:
                    self.var_porta_tcp.set(str(porta_ok))
            self._set_indicador(ok, msg)
        try:
            self.after(0, apply)
        except Exception:
            pass

    def _test_tcp(self, ip: str, port: int, seq: int):
        for p in portas_para_testar(port):
            if seq != self._test_seq:
                return
            codigo, msg = probe_tcp(ip, p, timeout=1.8)
            self._aplicar_teste(seq, None, msg)
            if codigo == 'aberta':
                self._aplicar_teste(seq, True, f'conectado {p}', p)
                return
        extra = (
            ' Nenhuma porta TCP aberta. A BA37 pode estar em modo cliente — '
            'use “Balança conecta neste PC”.'
        )
        self._aplicar_teste(seq, False, 'Conexão não estabelecida.' + extra)

    def _test_escuta(self, port: int, seq: int):
        ports = [port]
        if port in (PORTA_TCP_PADRAO, PORTA_ESCUTA_PADRAO):
            for extra in (PORTA_TCP_PADRAO, PORTA_ESCUTA_PADRAO):
                if extra not in ports:
                    ports.append(extra)
        abertas = []
        falhas = []
        socks = []
        try:
            for p in ports:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    srv.bind(('0.0.0.0', p))
                    srv.listen(1)
                    socks.append(srv)
                    abertas.append(str(p))
                except OSError as exc:
                    falhas.append(f'{p} ({exc})')
                    try:
                        srv.close()
                    except Exception:
                        pass
            if abertas:
                msg = f'Escuta aberta nas portas {", ".join(abertas)}. Aguarde a balança conectar.'
                if falhas:
                    msg += f' Falha: {", ".join(falhas)}.'
                self._aplicar_teste(seq, True, msg)
            else:
                self._aplicar_teste(seq, False, 'Não foi possível escutar: ' + ('; '.join(falhas) or 'erro'))
        finally:
            for s in socks:
                try:
                    s.close()
                except Exception:
                    pass

    def _testar_todas_portas(self):
        tipo = (self.var_tipo.get() or '').strip().lower()
        if tipo == 'escuta':
            try:
                port = int(str(self.var_porta_tcp.get() or PORTA_ESCUTA_PADRAO).strip())
            except ValueError:
                port = PORTA_ESCUTA_PADRAO
            self._test_seq += 1
            seq = self._test_seq
            self.btn_testar.configure(state='disabled')
            self.btn_scan.configure(state='disabled')
            self._set_indicador(None, 'Abrindo escuta...')
            threading.Thread(target=self._test_escuta, args=(port, seq), daemon=True).start()
            return
        ip = self.var_ip.get().strip()
        if not ip:
            self._set_indicador(False, 'Informe o IP da balança')
            return
        try:
            port = int(str(self.var_porta_tcp.get() or PORTA_TCP_PADRAO).strip())
        except ValueError:
            port = PORTA_TCP_PADRAO
        self._test_seq += 1
        seq = self._test_seq
        self.btn_testar.configure(state='disabled')
        self.btn_scan.configure(state='disabled')
        self._set_indicador(None, 'Varrendo portas...')
        threading.Thread(target=self._scan_todas, args=(ip, port, seq), daemon=True).start()

    def _scan_todas(self, ip: str, port: int, seq: int):
        linhas = [f'Varredura TCP em {ip}:']
        aberta = None
        for p in portas_para_testar(port):
            if seq != self._test_seq:
                return
            codigo, msg = probe_tcp(ip, p, timeout=1.8)
            if codigo == 'aberta':
                linhas.append(f'  {p}: ABERTA — {msg}')
                if aberta is None:
                    aberta = p
            elif codigo == 'recusada':
                linhas.append(f'  {p}: FECHADA — {msg}')
            elif codigo == 'timeout':
                linhas.append(f'  {p}: FECHADA — {msg}')
            else:
                linhas.append(f'  {p}: {msg}')
        if aberta is None:
            linhas.append('')
            linhas.append(
                'Nenhuma porta aberta. Se a BA37 estiver em modo cliente (spec 43=2), '
                'use “Balança conecta neste PC” (escuta 33582 / 33581).'
            )
            resumo = 'Nenhuma porta TCP aberta'
        else:
            resumo = f'conectado {aberta}'
        texto = '\n'.join(linhas)

        def apply():
            if not self.winfo_exists() or seq != self._test_seq:
                return
            self._fim_teste()
            if aberta:
                self.var_porta_tcp.set(str(aberta))
                self._set_indicador(True, resumo)
            else:
                self._set_indicador(False, resumo)
            self._mostrar_scan(texto)

        try:
            self.after(0, apply)
        except Exception:
            pass

    def _mostrar_scan(self, texto: str):
        win = tk.Toplevel(self)
        win.title('Testar todas as portas')
        win.configure(bg=CLR_BG)
        win.transient(self)
        _aplicar_icone(win)
        tk.Label(
            win, text='Resultado da varredura (este PC → balança)',
            font=FONT_TITLE, fg=CLR_NAVY, bg=CLR_BG, anchor='w'
        ).pack(fill='x', padx=10, pady=(8, 4))
        txt = ScrolledText(win, height=16, width=64, font=FONT_MONO, bg=CLR_WHITE, relief='sunken')
        txt.pack(fill='both', expand=True, padx=10, pady=4)
        txt.insert('end', texto)
        txt.configure(state='disabled')
        tk.Button(win, text='Fechar', font=FONT_UI, bg=CLR_BTN, command=win.destroy).pack(pady=8)
        win.geometry('520x360')
        win.minsize(420, 280)

    def _test_serial(self, porta: str, baud: int, seq: int, stopbits: float = 2):
        if serial is None:
            self._aplicar_teste(seq, False, 'pyserial não instalado')
            return
        alvo = detectar_porta(porta or 'AUTO')
        if not alvo:
            self._aplicar_teste(seq, False, 'Conexão não estabelecida')
            return
        stop_map = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}
        ser = None
        try:
            ser = serial.Serial(
                port=alvo, baudrate=baud, timeout=1.0,
                stopbits=stop_map.get(stopbits, serial.STOPBITS_TWO),
            )
            self._aplicar_teste(seq, True, f'Conexão estabelecida ({alvo} @ {baud} 8N{int(stopbits)})')
        except Exception:
            self._aplicar_teste(seq, False, 'Conexão não estabelecida')
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    def _refresh_ports(self):
        ports = listar_portas() or ['COM1', 'COM2', 'COM3']
        ports = ['AUTO'] + ports
        menu = self.cmb_porta['menu']
        menu.delete(0, 'end')
        for p in ports:
            menu.add_command(label=p, command=lambda v=p: self.var_porta.set(v))
        if self.var_porta.get() not in ports:
            self.var_porta.set(ports[1] if len(ports) > 1 else 'AUTO')

    def _ok(self):
        try:
            baud = int(self.var_baud.get().strip())
        except ValueError:
            messagebox.showerror('Configuração', 'Baud rate inválido.', parent=self)
            return
        try:
            stopbits = float(str(self.var_stop.get() or '2').strip().replace(',', '.'))
        except ValueError:
            messagebox.showerror('Configuração', 'Stop bits inválido (use 1, 1.5 ou 2).', parent=self)
            return
        if stopbits not in (1, 1.5, 2):
            messagebox.showerror('Configuração', 'Stop bits deve ser 1, 1.5 ou 2.', parent=self)
            return
        tipo = self.var_tipo.get().strip() or 'serial'
        if tipo not in ('serial', 'rede', 'escuta'):
            tipo = 'serial'
        proto_label = (self.var_proto.get() or PROTOCOLOS_SERIAL['auto']).strip()
        proto_key = next((k for k, v in PROTOCOLOS_SERIAL.items() if v == proto_label), 'auto')
        try:
            porta_tcp = int(str(self.var_porta_tcp.get() or PORTA_TCP_PADRAO).strip())
        except ValueError:
            messagebox.showerror('Configuração', 'Porta TCP inválida.', parent=self)
            return
        if not (1 <= porta_tcp <= 65535):
            messagebox.showerror('Configuração', 'Porta TCP deve estar entre 1 e 65535.', parent=self)
            return
        ip = self.var_ip.get().strip()
        if tipo == 'rede' and not ip and not self.var_sim.get():
            messagebox.showerror('Configuração', 'Informe o IP da balança de rede.', parent=self)
            return
        self.cfg['balanca_codigo'] = self.var_codigo.get().strip().upper() or 'BAL-01'
        self.cfg['balanca_nome'] = self.var_nome.get().strip()
        self.cfg['balanca_local'] = self.var_local.get().strip()
        self.cfg['conexao_tipo'] = tipo
        self.cfg['porta_com'] = self.var_porta.get().strip() or 'COM3'
        self.cfg['baudrate'] = baud
        self.cfg['stopbits'] = stopbits
        self.cfg['protocolo_serial'] = proto_key
        self.cfg['balanca_ip'] = ip
        self.cfg['balanca_porta_tcp'] = porta_tcp
        self.cfg['modo_simulacao'] = bool(self.var_sim.get())
        self.cfg['servidor_url'] = self.var_url.get().strip().rstrip('/') or SERVIDOR_PADRAO
        self.cfg['api_key'] = self.var_key.get().strip()
        self.cfg['envio_automatico'] = bool(self.var_auto.get())
        if tipo == 'serial':
            self.cfg['consultar_balanca'] = True
            self.cfg['intervalo_consulta_seg'] = 0.3
        else:
            self.cfg['consultar_balanca'] = False
        save_config(self.cfg)
        self.on_save(self.cfg)
        self.destroy()


class AgenteApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.q: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.reader = None
        self.enviando = False
        self.ultimo_envio = 0.0
        self.ultimo_peso_enviado = None

        self.peso_atual = None
        self.bruto_atual = ''
        self.estavel_atual = False
        self.porta_atual = self.cfg.get('porta_com', 'COM3')
        self.clientes = []
        self.cliente_por_label = {}
        self._foto_cliente = None
        self._foto_orig = None
        self._foto_size = (0, 0)
        self._img_req_seq = 0

        self._build_ui()
        self._start_reader()
        self.root.after(80, self._poll_queue)
        self.root.after(250, self.carregar_clientes)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _build_ui(self):
        self.root.title('Controle de Pesagem — São Geraldo Service')
        self.root.geometry('1024x700')
        self.root.minsize(860, 560)
        self.root.configure(bg=CLR_BG)
        _aplicar_icone(self.root)

        # Menu estilo Delphi
        menubar = tk.Menu(self.root)
        m_arquivo = tk.Menu(menubar, tearoff=0)
        m_arquivo.add_command(label='Configuração...', command=self._abrir_config, accelerator='F2')
        m_arquivo.add_separator()
        m_arquivo.add_command(label='Sair', command=self._on_close)
        menubar.add_cascade(label='Arquivo', menu=m_arquivo)

        m_balanca = tk.Menu(menubar, tearoff=0)
        m_balanca.add_command(label='Reconectar', command=self._reconectar)
        m_balanca.add_command(label='Testar servidor', command=self._test_server)
        m_balanca.add_separator()
        m_balanca.add_command(label='Modo simulação (ligar/desligar)', command=self._toggle_sim)
        menubar.add_cascade(label='Balança', menu=m_balanca)

        m_ajuda = tk.Menu(menubar, tearoff=0)
        m_ajuda.add_command(label='Sobre...', command=self._sobre)
        menubar.add_cascade(label='Ajuda', menu=m_ajuda)
        self.root.config(menu=menubar)
        self.root.bind('<F2>', lambda e: self._abrir_config())

        status_bar = tk.Frame(self.root, bg=CLR_STATUS, relief='sunken', bd=1)
        status_bar.pack(fill='x', side='bottom')
        tk.Label(
            status_bar, text=f'Versão {APP_VERSION}', font=FONT_UI,
            bg=CLR_STATUS, fg=CLR_DARK, anchor='e', padx=8, pady=2,
        ).pack(side='right')
        tk.Frame(status_bar, bg='#808080', width=1).pack(side='right', fill='y', pady=2)
        self.status_var = tk.StringVar(value='Pronto.')
        tk.Label(
            status_bar, textvariable=self.status_var, font=FONT_UI,
            bg=CLR_STATUS, anchor='w', padx=6, pady=2,
        ).pack(side='left', fill='x', expand=True)

        # Barra título painel
        top = tk.Frame(self.root, bg=CLR_NAVY, padx=8, pady=4)
        top.pack(fill='x')
        tk.Label(top, text='CONTROLE DE PESAGEM  ·  URANO BA37', font=('Tahoma', 11, 'bold'),
                 fg='white', bg=CLR_NAVY).pack(side='left')
        self.lbl_local_var = tk.StringVar(value='')
        self.lbl_local = tk.Label(top, textvariable=self.lbl_local_var, font=FONT_UI, fg='#A8C53A', bg=CLR_NAVY)
        self.lbl_local.pack(side='right')

        body = tk.Frame(self.root, bg=CLR_BG, padx=12, pady=8)
        body.pack(fill='both', expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=5)
        body.grid_rowconfigure(3, weight=3)

        # GroupBox: Identificação
        grp = tk.LabelFrame(body, text=' Controlador / Local ', font=FONT_UI, bg=CLR_BG, fg=CLR_BLACK, padx=8, pady=6)
        grp.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        self.info_var = tk.StringVar()
        tk.Label(grp, textvariable=self.info_var, font=FONT_UI, bg=CLR_BG, anchor='w', justify='left').pack(fill='x')

        row_meio = tk.Frame(body, bg=CLR_BG)
        row_meio.grid(row=1, column=0, sticky='nsew', pady=(0, 6))
        row_meio.grid_columnconfigure(0, weight=5, minsize=520)
        row_meio.grid_columnconfigure(1, weight=0, minsize=250)
        row_meio.grid_rowconfigure(0, weight=1)

        # GroupBox: Peso (esquerda — visor dominante)
        grp2 = tk.LabelFrame(row_meio, text=' Peso atual (ao vivo) ', font=FONT_UI, bg=CLR_BG, fg=CLR_BLACK, padx=8, pady=8)
        grp2.grid(row=0, column=0, sticky='nsew', padx=(0, 8))

        outer = tk.Frame(grp2, bg=CLR_SHADOW, padx=2, pady=2)
        outer.pack(fill='both', expand=True)
        inner = tk.Frame(outer, bg=CLR_LED_BG, padx=2, pady=2)
        inner.pack(fill='both', expand=True)
        self.peso_var = tk.StringVar(value='000.00')
        self.led_peso = LedPesoDisplay(inner)
        self.led_peso.pack(fill='both', expand=True)
        self.led_peso.set_peso(0.0, aceso=True)

        meta = tk.Frame(grp2, bg=CLR_BG)
        meta.pack(fill='x', pady=(6, 0))
        self.estavel_var = tk.StringVar(value='—')
        self.porta_var = tk.StringVar(value='')
        tk.Label(meta, textvariable=self.estavel_var, font=FONT_UI, bg=CLR_BG, anchor='w').pack(side='left')
        tk.Label(meta, textvariable=self.porta_var, font=FONT_UI, bg=CLR_BG, anchor='e').pack(side='right')

        # GroupBox: combo + miniatura (não cresce no maximize)
        grp_cli = tk.LabelFrame(row_meio, text=' Cliente ', font=FONT_UI, bg=CLR_BG, fg=CLR_BLACK, padx=8, pady=6)
        grp_cli.grid(row=0, column=1, sticky='ne')
        row_cli = tk.Frame(grp_cli, bg=CLR_BG)
        row_cli.pack(fill='x')
        tk.Label(row_cli, text='Cliente', width=8, anchor='w', bg=CLR_BG, font=FONT_UI).pack(side='left')
        self.cliente_var = tk.StringVar(value='— Selecione o cliente —')
        self.cmb_cliente = ttk.Combobox(
            row_cli, textvariable=self.cliente_var, state='readonly', font=FONT_UI, width=18
        )
        self.cmb_cliente['values'] = ('— Selecione o cliente —',)
        self.cmb_cliente.pack(side='left', fill='x', expand=True, padx=(0, 6))
        self.cmb_cliente.bind('<<ComboboxSelected>>', self._on_cliente_sel)
        tk.Button(
            row_cli, text='Atualizar', font=FONT_UI, bg=CLR_BTN, command=self.carregar_clientes
        ).pack(side='left')
        self.lbl_cliente_nome = tk.Label(
            grp_cli, text='', font=FONT_TITLE, fg=CLR_NAVY, bg=CLR_BG, anchor='w'
        )
        self.lbl_cliente_nome.pack(fill='x', pady=(6, 0))

        img_outer = tk.Frame(grp_cli, bg=CLR_SHADOW, padx=1, pady=1, width=FOTO_MAX_W + 10, height=FOTO_MAX_H + 10)
        img_outer.pack(pady=(8, 2), anchor='n')
        img_outer.pack_propagate(False)
        img_inner = tk.Frame(img_outer, bg=CLR_WHITE, padx=2, pady=2)
        img_inner.pack(fill='both', expand=True)
        self.lbl_cliente_img = tk.Label(
            img_inner, text='Foto',
            font=FONT_UI, bg=CLR_WHITE, fg=CLR_DARK, wraplength=FOTO_MAX_W - 8
        )
        self.lbl_cliente_img.pack(fill='both', expand=True)
        self.lbl_cliente_img.bind('<Configure>', self._on_foto_resize)

        # Botões estilo Delphi
        btn_row = tk.Frame(body, bg=CLR_BG)
        btn_row.grid(row=2, column=0, sticky='ew', pady=(0, 6))
        self.btn_enviar = tk.Button(
            btn_row, text='Enviar para o servidor', font=('Tahoma', 10, 'bold'),
            bg=CLR_BTN, relief='raised', width=22, height=1, command=self.enviar_peso
        )
        self.btn_enviar.pack(side='left')
        tk.Button(
            btn_row, text='Configuração (F2)', font=FONT_UI,
            bg=CLR_BTN, relief='raised', width=16, height=1, command=self._abrir_config
        ).pack(side='left', padx=8)
        tk.Button(
            btn_row, text='Reconectar', font=FONT_UI,
            bg=CLR_BTN, relief='raised', width=12, height=1, command=self._reconectar
        ).pack(side='left')

        grp_log = tk.LabelFrame(body, text=' Registro ', font=FONT_UI, bg=CLR_BG, fg=CLR_BLACK, padx=6, pady=4)
        grp_log.grid(row=3, column=0, sticky='nsew')
        self.txt_log = ScrolledText(
            grp_log, height=6, font=FONT_MONO, bg=CLR_WHITE, fg=CLR_BLACK,
            relief='sunken', wrap='word', state='disabled'
        )
        self.txt_log.pack(fill='both', expand=True)

        self._refresh_info()

    def _rotulo_conexao(self, porta: str | None = None) -> str:
        if self.cfg.get('modo_simulacao'):
            return 'SIM'
        tipo = str(self.cfg.get('conexao_tipo') or 'serial').strip().lower()
        if tipo == 'escuta':
            origem = porta or f"0.0.0.0:{self.cfg.get('balanca_porta_tcp') or PORTA_ESCUTA_PADRAO}"
            return f'ESCUTA: {origem}'
        if tipo == 'rede':
            origem = porta or f"{self.cfg.get('balanca_ip') or '?'}:{self.cfg.get('balanca_porta_tcp') or PORTA_TCP_PADRAO}"
            return f'TCP: {origem}'
        return f"COM: {porta or self.cfg.get('porta_com') or '-'} · {_rotulo_protocolo(self.cfg)}"

    def _refresh_info(self):
        self.info_var.set(
            f"Código: {self.cfg.get('balanca_codigo')}   |   "
            f"Nome: {self.cfg.get('balanca_nome') or '-'}   |   "
            f"Local: {self.cfg.get('balanca_local') or '-'}"
        )
        self.lbl_local_var.set(self.cfg.get('balanca_local') or self.cfg.get('balanca_codigo'))
        self.porta_var.set(self._rotulo_conexao())

    def _placeholder_cliente(self):
        return '— Selecione o cliente —'

    def _label_cliente(self, cli: dict) -> str:
        nome = (cli.get('nome') or '').strip() or f"Cliente {cli.get('id')}"
        iguais = [c for c in self.clientes if (c.get('nome') or '').strip() == (cli.get('nome') or '').strip()]
        if len(iguais) > 1:
            return f"{nome}  [{cli.get('id')}]"
        return nome

    def _cliente_selecionado(self) -> dict | None:
        return self.cliente_por_label.get(self.cliente_var.get())

    def _url_imagem_cliente(self, cli: dict) -> str:
        """Foto do Cadastro de Cliente no servidor de pesagem (nunca Chamados / nunca localhost)."""
        base = (self.cfg.get('servidor_url') or SERVIDOR_PADRAO).rstrip('/')
        path = (cli.get('imagem_path') or '').replace('\\', '/').lstrip('/')
        if path:
            if path.startswith('static/'):
                return f'{base}/{path}'
            return f'{base}/static/{path}'
        url = (cli.get('imagem_url') or '').strip()
        if not url:
            return ''
        if url.startswith('/'):
            return base + url
        host = _host_de_url(url)
        if host in ('127.0.0.1', 'localhost', '::1'):
            slash = url.find('://')
            path_part = url[slash + 3:] if slash >= 0 else url
            slash2 = path_part.find('/')
            path_part = path_part[slash2:] if slash2 >= 0 else ''
            return base + path_part
        return url

    def _mostrar_placeholder_img(self, texto: str):
        self._foto_cliente = None
        self._foto_orig = None
        self._foto_size = (0, 0)
        self.lbl_cliente_img.configure(image='', text=texto, wraplength=FOTO_MAX_W - 8)

    def carregar_clientes(self):
        cfg = dict(self.cfg)

        def work():
            # Cadastro de Cliente da pesagem (pesagem_clientes), não clientes de Chamados
            primary = (cfg.get('servidor_url') or SERVIDOR_PADRAO).rstrip('/')
            bases = [primary]
            alt = SERVIDOR_PADRAO.rstrip('/')
            if _host_de_url(primary) != _host_de_url(alt):
                bases.append(alt)
            headers = {'X-API-Key': cfg.get('api_key', '')}
            params = {'api_key': cfg.get('api_key', '')}
            last_err = 'Falha ao listar clientes'
            for base in bases:
                url = base + '/api/pesagem/clientes'
                try:
                    r = requests.get(url, headers=headers, params=params, timeout=8)
                except requests.RequestException as exc:
                    last_err = f'Servidor inacessível ({base}): {exc}'
                    continue
                data = {}
                try:
                    data = r.json()
                except Exception:
                    data = {}
                if r.status_code == 200 and data.get('ok'):
                    if base != primary:
                        self.cfg['servidor_url'] = base
                    self.q.put(('clientes', data.get('clientes') or []))
                    return
                last_err = _resumo_http_erro(r, url)
            self.q.put(('clientes_erro', last_err))

        threading.Thread(target=work, daemon=True).start()
        self._set_status(f'Buscando Cadastro de Cliente em {cfg.get("servidor_url") or SERVIDOR_PADRAO}...')

    def _aplicar_lista_clientes(self, clientes: list):
        anterior = self.cliente_var.get()
        self.clientes = list(clientes or [])
        self.cliente_por_label = {}
        labels = [self._placeholder_cliente()]
        for cli in self.clientes:
            lab = self._label_cliente(cli)
            self.cliente_por_label[lab] = cli
            labels.append(lab)
        self.cmb_cliente['values'] = tuple(labels)
        if anterior in self.cliente_por_label:
            self.cliente_var.set(anterior)
        else:
            self.cliente_var.set(self._placeholder_cliente())
        self._on_cliente_sel()
        n = len(self.clientes)
        self._set_status(f'{n} cliente(s) do Cadastro de Cliente em {self.cfg.get("servidor_url")}')

    def _on_cliente_sel(self, _evt=None):
        cli = self._cliente_selecionado()
        if not cli:
            if hasattr(self, 'lbl_cliente_nome'):
                self.lbl_cliente_nome.configure(text='')
            self._mostrar_placeholder_img('Selecione um cliente para ver a foto cadastrada')
            return
        nome = (cli.get('nome') or '').strip()
        if hasattr(self, 'lbl_cliente_nome'):
            self.lbl_cliente_nome.configure(text=nome)
        url = self._url_imagem_cliente(cli)
        if not url:
            self._mostrar_placeholder_img('Cliente sem imagem cadastrada')
            return
        self._mostrar_placeholder_img('Carregando foto...')
        self._img_req_seq += 1
        seq = self._img_req_seq
        threading.Thread(target=self._baixar_imagem, args=(url, seq), daemon=True).start()

    def _baixar_imagem(self, url: str, seq: int):
        try:
            r = requests.get(url, timeout=8)
            if r.status_code != 200 or not r.content:
                self.q.put(('cliente_img_erro', (seq, 'Não foi possível carregar a imagem')))
                return
            self.q.put(('cliente_img', (seq, r.content)))
        except requests.RequestException as exc:
            self.q.put(('cliente_img_erro', (seq, f'Imagem: {exc}')))

    def _exibir_imagem_bytes(self, data: bytes):
        if Image is None or ImageTk is None:
            try:
                photo = tk.PhotoImage(data=data)
            except Exception:
                self._mostrar_placeholder_img('Imagem não suportada neste agente')
                return
            self._foto_orig = None
            self._foto_cliente = photo
            self.lbl_cliente_img.configure(image=photo, text='')
            return
        try:
            self._foto_orig = Image.open(BytesIO(data)).convert('RGBA')
        except Exception:
            self._mostrar_placeholder_img('Imagem não suportada neste agente')
            return
        self._foto_size = (0, 0)
        self._render_foto()

    def _on_foto_resize(self, evt):
        if evt.widget is not self.lbl_cliente_img:
            return
        self.lbl_cliente_img.configure(wraplength=max(60, FOTO_MAX_W - 12))
        if self._foto_orig is None:
            return
        self._render_foto()

    def _render_foto(self, w: int | None = None, h: int | None = None):
        if self._foto_orig is None or ImageTk is None:
            return
        tw, th = FOTO_MAX_W - 8, FOTO_MAX_H - 8
        im = self._foto_orig.copy()
        im.thumbnail((tw, th), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(im)
        self._foto_cliente = photo
        self._foto_size = (tw, th)
        self.lbl_cliente_img.configure(image=photo, text='')

    def _set_status(self, text: str):
        stamp = datetime.now().strftime('%H:%M:%S')
        msg = str(text).replace('\n', ' ').strip()
        self.status_var.set(f'[{stamp}] {msg}')
        log = getattr(self, 'txt_log', None)
        if log is None:
            return
        try:
            log.configure(state='normal')
            log.insert('end', f'[{stamp}] {msg}\n')
            log.see('end')
            # mantém o registro curto
            if float(log.index('end-1c').split('.')[0]) > 400:
                log.delete('1.0', '80.0')
            log.configure(state='disabled')
        except Exception:
            pass

    def _abrir_config(self):
        ConfigDialog(self.root, self.cfg, self._aplicar_config)

    def _aplicar_config(self, cfg: dict):
        self.cfg = cfg
        self._refresh_info()
        self._set_status('Configuração salva. Reconectando...')
        self._reconectar()
        self.carregar_clientes()

    def _reconectar(self):
        self.stop_event.set()
        time.sleep(0.15)
        self.stop_event = threading.Event()
        self._start_reader()

    def _start_reader(self):
        self.reader = BalancaReader(self.cfg, self.q, self.stop_event)
        self.reader.start()
        self._set_status('Iniciando leitura da balança...')

    def _toggle_sim(self):
        self.cfg['modo_simulacao'] = not bool(self.cfg.get('modo_simulacao'))
        save_config(self.cfg)
        self._set_status('Simulação ' + ('ON' if self.cfg['modo_simulacao'] else 'OFF'))
        self._reconectar()

    def _test_server(self):
        url = self.cfg['servidor_url'].rstrip('/') + '/api/pesagem/health'

        def work():
            try:
                r = requests.get(url, timeout=5)
                self.q.put((
                    'status',
                    'Servidor online' if r.ok else _resumo_http_erro(r, url),
                ))
            except requests.RequestException as exc:
                self.q.put(('status', f'Servidor inacessível: {exc}'))

        threading.Thread(target=work, daemon=True).start()

    def _sobre(self):
        messagebox.showinfo(
            'Sobre',
            f'Controle de Pesagem\nSão Geraldo Service\nVersão {APP_VERSION}\n\n'
            'Lê o peso da balança e envia ao servidor.',
            parent=self.root,
        )

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == 'status':
                    self._set_status(str(payload))
                elif kind == 'porta':
                    self.porta_atual = str(payload)
                    self.porta_var.set(self._rotulo_conexao(self.porta_atual))
                elif kind == 'raw':
                    pass
                elif kind == 'peso':
                    self._update_peso(payload)
                elif kind == 'envio_ok':
                    self.enviando = False
                    self.btn_enviar.configure(state='normal', text='Enviar para o servidor')
                    self._set_status(f'Enviado OK (id={payload})')
                    messagebox.showinfo('Enviado', f'Peso enviado ao servidor.\nID: {payload}', parent=self.root)
                elif kind == 'envio_erro':
                    self.enviando = False
                    self.btn_enviar.configure(state='normal', text='Enviar para o servidor')
                    self._set_status(str(payload))
                    messagebox.showerror('Falha', str(payload), parent=self.root)
                elif kind == 'clientes':
                    self._aplicar_lista_clientes(payload)
                elif kind == 'clientes_erro':
                    self._aplicar_lista_clientes([])
                    self._set_status(str(payload))
                elif kind == 'cliente_img':
                    seq, blob = payload
                    if seq == self._img_req_seq:
                        self._exibir_imagem_bytes(blob)
                elif kind == 'cliente_img_erro':
                    seq, msg = payload
                    if seq == self._img_req_seq:
                        self._mostrar_placeholder_img(str(msg))
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _update_peso(self, data: dict):
        peso = float(data['peso'])
        self.peso_atual = peso
        self.bruto_atual = data.get('bruto') or ''
        self.estavel_atual = bool(data.get('estavel', True))
        self.porta_atual = data.get('porta') or self.porta_atual

        self.peso_var.set(formatar_peso_ui(peso))
        if hasattr(self, 'led_peso'):
            self.led_peso.set_peso(peso, aceso=True)
        self.estavel_var.set('Estável' if self.estavel_atual else 'Em movimento...')
        self.porta_var.set(self._rotulo_conexao(self.porta_atual))
        visor = formatar_peso_ui(peso)
        agora_log = time.time()
        ultimo = getattr(self, '_ultimo_log_peso', None)
        if ultimo is None or abs(peso - ultimo[0]) >= 0.01 or (agora_log - ultimo[1]) >= 1.5:
            self._ultimo_log_peso = (peso, agora_log)
            self._set_status(f'peso {visor} kg')

        if self.cfg.get('envio_automatico') and self.estavel_atual and not self.enviando:
            agora = time.time()
            intervalo = float(self.cfg.get('intervalo_envio_seg', 2.0))
            mudou = self.ultimo_peso_enviado is None or abs(peso - self.ultimo_peso_enviado) >= 0.02
            if mudou and (agora - self.ultimo_envio) >= intervalo and abs(peso) >= float(self.cfg.get('peso_minimo', 0.01)):
                self.enviar_peso(silencioso=True)

    def enviar_peso(self, silencioso: bool = False):
        if self.enviando:
            return
        if self.peso_atual is None:
            if not silencioso:
                messagebox.showwarning('Sem peso', 'Aguarde o peso aparecer na tela.', parent=self.root)
            return

        peso = float(self.peso_atual)
        self.enviando = True
        self.btn_enviar.configure(state='disabled', text='Enviando...')
        self._set_status(f'Enviando {peso:.3f} kg...')

        cfg = dict(self.cfg)
        bruto = self.bruto_atual
        estavel = self.estavel_atual
        porta = self.porta_atual
        cliente = self._cliente_selecionado()

        def work():
            url = cfg['servidor_url'].rstrip('/') + '/api/pesagem/leituras'
            payload = {
                'peso': peso,
                'unidade': 'kg',
                'balanca_codigo': cfg.get('balanca_codigo', 'BAL-01'),
                'balanca_nome': cfg.get('balanca_nome') or '',
                'local': cfg.get('balanca_local') or '',
                'bruto_serial': bruto,
                'estavel': estavel,
                'origem': 'agente',
                'computador': socket.gethostname(),
                'porta_com': porta,
                'observacao': cfg.get('balanca_local') or '',
            }
            cli = cliente
            if cli:
                payload['cliente_id'] = cli.get('id')
                payload['cliente_nome'] = cli.get('nome') or ''
            headers = {'Content-Type': 'application/json', 'X-API-Key': cfg.get('api_key', '')}
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=8)
                data = {}
                try:
                    data = r.json()
                except Exception:
                    pass
                if r.status_code == 200 and data.get('ok'):
                    self.ultimo_envio = time.time()
                    self.ultimo_peso_enviado = peso
                    self.q.put(('envio_ok', data.get('id')))
                else:
                    self.q.put(('envio_erro', _resumo_http_erro(r, url)))
            except requests.RequestException as exc:
                self.q.put(('envio_erro', f'Erro de rede: {exc}'))

        threading.Thread(target=work, daemon=True).start()

    def _on_close(self):
        self.stop_event.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.2)
    except Exception:
        pass
    _aplicar_icone(root)
    AgenteApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
