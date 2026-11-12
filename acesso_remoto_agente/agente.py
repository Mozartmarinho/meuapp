"""Acesso remoto São Geraldo — fica ao lado do relógio do Windows."""
from __future__ import annotations

import io
import json
import os
import socket
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

APP_NOME = 'Acesso remoto São Geraldo'
APP_VERSION = '1.2.0'
RUN_NAME = 'AcessoRemotoSaoGeraldo'

_parar = threading.Event()
_estado = {
    'numero': '',
    'sessao_id': None,
    'senha_definida': False,
    'erro': '',
    'monitor': 0,
    'monitores': [],
    'virtual': None,
}


def pasta_config():
    base = os.environ.get('APPDATA') or str(Path.home())
    pasta = Path(base) / 'SaoGeraldoService' / 'AcessoRemoto'
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def caminho_config():
    return pasta_config() / 'config.json'


def carregar_config():
    try:
        data = json.loads(caminho_config().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data


def salvar_config(data):
    caminho_config().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def formatar_numero(numero):
    digitos = ''.join(ch for ch in (numero or '') if ch.isdigit())
    if len(digitos) != 9:
        return numero or '— — —'
    return '%s %s %s' % (digitos[:3], digitos[3:6], digitos[6:])


def normalizar_servidor(url):
    url = (url or '').strip().rstrip('/')
    if url and '://' not in url:
        url = 'http://' + url
    return url


def nome_pc():
    return (socket.gethostname() or 'Computador')[:120]


def _exe_atual():
    if getattr(sys, 'frozen', False):
        return '"%s"' % Path(sys.executable).resolve()
    return '"%s" "%s"' % (sys.executable, Path(__file__).resolve())


def definir_inicio_windows(ligado):
    if sys.platform != 'win32':
        return
    import winreg
    caminho = r'Software\Microsoft\Windows\CurrentVersion\Run'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho, 0, winreg.KEY_SET_VALUE) as chave:
        if ligado:
            winreg.SetValueEx(chave, RUN_NAME, 0, winreg.REG_SZ, _exe_atual())
        else:
            try:
                winreg.DeleteValue(chave, RUN_NAME)
            except FileNotFoundError:
                pass


def _pedido(config, caminho, metodo='POST', corpo=None, bruto=None, params=None):
    import requests
    servidor = normalizar_servidor(config.get('servidor'))
    if not servidor:
        raise RuntimeError('Informe o endereço do sistema.')
    headers = {'Accept': 'application/json'}
    token = (config.get('token') or '').strip()
    if token:
        headers['X-Agente-Token'] = token
    url = servidor + caminho
    if bruto is not None:
        headers['Content-Type'] = 'image/jpeg'
        resp = requests.post(url, data=bruto, headers=headers, params=params, timeout=8)
    elif corpo is not None:
        resp = requests.request(metodo, url, json=corpo, headers=headers, timeout=8)
    else:
        resp = requests.request(metodo, url, headers=headers, timeout=8)
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400:
        raise RuntimeError(data.get('message') or ('Falha %s' % resp.status_code))
    return data


def registrar(config):
    data = _pedido(config, '/api/acesso-remoto/agente/registrar', corpo={'nome': nome_pc()})
    config['token'] = data.get('token') or config.get('token')
    config['numero'] = data.get('numero') or config.get('numero')
    salvar_config(config)
    _estado['numero'] = config.get('numero') or ''
    _estado['senha_definida'] = bool(data.get('senha_definida'))
    return data


def salvar_senha(config, senha):
    _pedido(config, '/api/acesso-remoto/agente/senha', corpo={'senha': senha})
    _estado['senha_definida'] = True


def _vk(code, key):
    especiais = {
        'Enter': 0x0D, 'Backspace': 0x08, 'Tab': 0x09, 'Escape': 0x1B, 'Space': 0x20,
        'MetaLeft': 0x5B, 'MetaRight': 0x5C, 'OSLeft': 0x5B, 'OSRight': 0x5C,
        'ArrowLeft': 0x25, 'ArrowUp': 0x26, 'ArrowRight': 0x27, 'ArrowDown': 0x28,
        'Delete': 0x2E, 'Home': 0x24, 'End': 0x23, 'PageUp': 0x21, 'PageDown': 0x22,
        'Insert': 0x2D,
    }
    if code in especiais:
        return especiais[code]
    if code.startswith('F') and code[1:].isdigit():
        n = int(code[1:])
        if 1 <= n <= 12:
            return 0x70 + n - 1
    if code.startswith('Key') and len(code) == 4:
        return ord(code[3].upper())
    if code.startswith('Digit') and len(code) == 6:
        return ord(code[5])
    if key and len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if key and len(key) == 1 and key.isdigit():
        return ord(key)
    return None


def listar_monitores():
    if sys.platform != 'win32':
        return []
    import ctypes
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [
            ('left', ctypes.c_long), ('top', ctypes.c_long),
            ('right', ctypes.c_long), ('bottom', ctypes.c_long),
        ]

    achados = []

    def _enum(_hmon, _hdc, rect, _data):
        r = rect.contents
        largura = int(r.right - r.left)
        altura = int(r.bottom - r.top)
        if largura > 0 and altura > 0:
            achados.append({
                'left': int(r.left), 'top': int(r.top),
                'right': int(r.right), 'bottom': int(r.bottom),
            })
        return 1

    tipo = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_ssize_t
    )
    user32.EnumDisplayMonitors(None, None, tipo(_enum), 0)
    achados.sort(key=lambda item: (item['left'], item['top']))
    return achados


def atualizar_monitores_locais():
    monitores = listar_monitores()
    _estado['monitores'] = monitores
    if sys.platform == 'win32':
        import ctypes
        user32 = ctypes.windll.user32
        _estado['virtual'] = {
            'left': int(user32.GetSystemMetrics(76)),
            'top': int(user32.GetSystemMetrics(77)),
            'width': int(user32.GetSystemMetrics(78)),
            'height': int(user32.GetSystemMetrics(79)),
        }
    indice = int(_estado.get('monitor') or 0)
    if monitores and (indice < 0 or indice >= len(monitores)):
        _estado['monitor'] = 0
    return max(1, len(monitores))


def monitor_ativo():
    monitores = _estado.get('monitores') or []
    indice = int(_estado.get('monitor') or 0)
    if indice < 0 or indice >= len(monitores):
        return None
    return monitores[indice]


def ativar_dpi():
    if sys.platform != 'win32':
        return
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def ponto_pixel(frac_x, frac_y, monitor):
    if not monitor:
        return None
    largura = max(1, int(monitor['right']) - int(monitor['left']))
    altura = max(1, int(monitor['bottom']) - int(monitor['top']))
    fx = max(0.0, min(1.0, float(frac_x)))
    fy = max(0.0, min(1.0, float(frac_y)))
    px = int(round(monitor['left'] + fx * max(0, largura - 1)))
    py = int(round(monitor['top'] + fy * max(0, altura - 1)))
    return px, py


def ponto_no_monitor(frac_x, frac_y, monitor, virtual):
    if not monitor or not virtual or not virtual.get('width') or not virtual.get('height'):
        return int(float(frac_x) * 65535), int(float(frac_y) * 65535)
    largura = max(1, monitor['right'] - monitor['left'])
    altura = max(1, monitor['bottom'] - monitor['top'])
    px = monitor['left'] + float(frac_x) * largura
    py = monitor['top'] + float(frac_y) * altura
    ax = int(round((px - virtual['left']) * 65535 / max(1, virtual['width'] - 1)))
    ay = int(round((py - virtual['top']) * 65535 / max(1, virtual['height'] - 1)))
    return max(0, min(65535, ax)), max(0, min(65535, ay))


def aplicar_comando(comando):
    if (comando or {}).get('tipo') == 'monitor':
        try:
            indice = int(comando.get('indice') or 0)
        except (TypeError, ValueError):
            indice = 0
        _estado['monitor'] = max(0, indice)
        atualizar_monitores_locais()
        return
    if sys.platform != 'win32':
        return
    import ctypes
    user32 = ctypes.windll.user32
    extra = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', ctypes.c_ulong),
            ('dwFlags', ctypes.c_ulong), ('time', ctypes.c_ulong), ('dwExtraInfo', extra),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ('wVk', ctypes.c_ushort), ('wScan', ctypes.c_ushort), ('dwFlags', ctypes.c_ulong),
            ('time', ctypes.c_ulong), ('dwExtraInfo', extra),
        ]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT)]
        _anonymous_ = ('u',)
        _fields_ = [('type', ctypes.c_ulong), ('u', _U)]

    def enviar(item):
        user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item))

    tipo = comando.get('tipo')
    if tipo == 'mouse':
        acao = comando.get('acao')
        botao = comando.get('botao') or 'left'
        pixel = ponto_pixel(
            float(comando.get('x') or 0),
            float(comando.get('y') or 0),
            monitor_ativo(),
        )
        if pixel:
            user32.SetCursorPos(int(pixel[0]), int(pixel[1]))
        else:
            x, y = ponto_no_monitor(
                float(comando.get('x') or 0),
                float(comando.get('y') or 0),
                monitor_ativo(),
                _estado.get('virtual'),
            )
            item = INPUT(type=0)
            item.mi = MOUSEINPUT(x, y, 0, 0x8000 | 0x4000 | 0x0001, 0, 0)
            enviar(item)
        if acao == 'move':
            return
        if acao == 'wheel':
            data = ctypes.c_ulong(int(-int(comando.get('delta') or 0)) & 0xFFFFFFFF).value
            user32.mouse_event(0x0800, 0, 0, data, 0)
            return
        if acao == 'dblclick':
            down = 0x0008 if botao == 'right' else 0x0002
            up = 0x0010 if botao == 'right' else 0x0004
            time.sleep(0.05)
            user32.mouse_event(down, 0, 0, 0, 0)
            time.sleep(0.03)
            user32.mouse_event(up, 0, 0, 0, 0)
            return
        if acao == 'down':
            flag = 0x0008 if botao == 'right' else 0x0002
        elif acao == 'up':
            flag = 0x0010 if botao == 'right' else 0x0004
        else:
            return
        user32.mouse_event(flag, 0, 0, 0, 0)
        return
    if tipo != 'tecla':
        return
    vk = _vk(comando.get('code') or '', comando.get('key') or '')
    mods = []
    if comando.get('ctrl'):
        mods.append(0x11)
    if comando.get('alt'):
        mods.append(0x12)
    if comando.get('shift'):
        mods.append(0x10)

    def tecla(codigo, soltar):
        item = INPUT(type=1)
        item.ki = KEYBDINPUT(codigo, 0, 0x0002 if soltar else 0, 0, 0)
        enviar(item)

    for mod in mods:
        tecla(mod, False)
    if vk:
        tecla(vk, False)
        tecla(vk, True)
    for mod in reversed(mods):
        tecla(mod, True)


def capturar_jpeg():
    from PIL import ImageGrab
    atualizar_monitores_locais()
    monitor = monitor_ativo()
    bbox = None
    if monitor:
        bbox = (monitor['left'], monitor['top'], monitor['right'], monitor['bottom'])
    try:
        if bbox:
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
        else:
            img = ImageGrab.grab(all_screens=True)
    except TypeError:
        img = ImageGrab.grab(bbox=bbox) if bbox else ImageGrab.grab()
    if img.width > 1920 or img.height > 1080:
        img.thumbnail((1920, 1080))
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG', quality=85, subsampling=0)
    return buf.getvalue()


def _tratar_resposta(data, avisou):
    if not isinstance(data, dict):
        return avisou
    _estado['sessao_id'] = data.get('sessao_id')
    if data.get('senha_definida') is not None:
        _estado['senha_definida'] = bool(data.get('senha_definida'))
    if data.get('sessao_id') and not avisou[0]:
        avisou[0] = True
        try:
            from pystray import Icon
            if isinstance(getattr(_tratar_resposta, 'icone', None), Icon):
                _tratar_resposta.icone.notify('Sessão iniciada', APP_NOME)
        except Exception:
            pass
    if not data.get('sessao_id'):
        avisou[0] = False
    ultimo = None
    for comando in data.get('comandos') or []:
        try:
            if (
                ultimo and ultimo.get('tipo') == 'mouse' and ultimo.get('acao') == 'up'
                and comando.get('tipo') == 'mouse' and comando.get('acao') == 'down'
            ):
                time.sleep(0.07)
            aplicar_comando(comando)
            if comando.get('tipo') == 'mouse' and comando.get('acao') == 'down':
                time.sleep(0.03)
        except Exception:
            pass
        ultimo = comando
    return avisou


def loop_remoto(config, atualizar):
    avisou = [False]
    while not _parar.is_set():
        try:
            if not config.get('token'):
                registrar(config)
            sessao = _estado.get('sessao_id')
            if sessao:
                blob = capturar_jpeg()
                data = _pedido(
                    config,
                    '/api/acesso-remoto/agente/tela',
                    bruto=blob,
                    params={
                        'sessao_id': sessao,
                        'monitores': max(1, len(_estado.get('monitores') or [])),
                        'monitor': int(_estado.get('monitor') or 0),
                    },
                )
                _tratar_resposta(data, avisou)
                _estado['erro'] = ''
                atualizar()
                _parar.wait(0.35)
                continue
            quantidade = atualizar_monitores_locais()
            data = _pedido(config, '/api/acesso-remoto/agente/pulso', corpo={
                'nome': nome_pc(),
                'monitores': quantidade,
                'monitor': int(_estado.get('monitor') or 0),
            })
            _tratar_resposta(data, avisou)
            _estado['erro'] = ''
            atualizar()
        except Exception as exc:
            _estado['erro'] = str(exc)
            _estado['sessao_id'] = None
            atualizar()
        _parar.wait(2)


def _icone():
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (64, 64), '#0c3a38')
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, 58, 58), fill='#1ABC9C')
    draw.rectangle((24, 18, 40, 34), fill='#0c3a38')
    draw.rectangle((20, 34, 44, 40), fill='#0c3a38')
    return img


def iniciar_bandeja(root, janela_mostrar):
    try:
        import pystray
    except Exception:
        return None
    def abrir(_icon, _item):
        root.after(0, janela_mostrar)

    def sair(_icon, _item):
        _parar.set()
        _icon.stop()
        root.after(0, root.destroy)

    menu = pystray.Menu(
        pystray.MenuItem('Abrir Acesso remoto São Geraldo', abrir, default=True),
        pystray.MenuItem('Sair', sair),
    )
    icone = pystray.Icon(RUN_NAME, _icone(), APP_NOME, menu)
    _tratar_resposta.icone = icone
    threading.Thread(target=icone.run, daemon=True).start()
    return icone


def gerar_senha():
    import secrets
    alfabeto = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
    return ''.join(secrets.choice(alfabeto) for _ in range(8))


def main():
    ativar_dpi()
    config = carregar_config()
    _estado['numero'] = config.get('numero') or ''
    root = tk.Tk()
    root.title(APP_NOME)
    root.geometry('460x430')
    root.minsize(420, 400)
    root.configure(bg='#f4f7f6')

    topo = tk.Frame(root, bg='#0c3a38', height=72)
    topo.pack(fill='x')
    tk.Label(topo, text=APP_NOME, bg='#0c3a38', fg='white', font=('Segoe UI', 14, 'bold')).pack(anchor='w', padx=16, pady=(12, 0))
    tk.Label(topo, text='Ativo ao lado do relógio', bg='#0c3a38', fg='#b7e4dc', font=('Segoe UI', 9)).pack(anchor='w', padx=16, pady=(0, 10))

    corpo = tk.Frame(root, bg='#f4f7f6', padx=16, pady=12)
    corpo.pack(fill='both', expand=True)
    numero_var = tk.StringVar(value=formatar_numero(config.get('numero')))
    status_var = tk.StringVar(value='Informe o endereço do sistema e crie a senha.')
    tk.Label(corpo, textvariable=numero_var, bg='#f4f7f6', fg='#0c3a38', font=('Segoe UI', 28, 'bold')).pack(anchor='w')
    tk.Label(corpo, textvariable=status_var, bg='#f4f7f6', fg='#475569', font=('Segoe UI', 9), wraplength=410, justify='left').pack(anchor='w', pady=(0, 8))

    tk.Label(corpo, text='Endereço do sistema', bg='#f4f7f6').pack(anchor='w')
    servidor = ttk.Entry(corpo)
    servidor.insert(0, config.get('servidor') or '')
    servidor.pack(fill='x', pady=(0, 8))

    tk.Label(corpo, text='Senha deste equipamento', bg='#f4f7f6').pack(anchor='w')
    senha = ttk.Entry(corpo, show='*')
    senha.pack(fill='x', pady=(0, 8))

    iniciar = tk.BooleanVar(value=bool(config.get('iniciar_com_windows', True)))
    ttk.Checkbutton(corpo, text='Ficar ativo ao ligar o Windows', variable=iniciar).pack(anchor='w', pady=(0, 8))

    botoes = tk.Frame(corpo, bg='#f4f7f6')
    botoes.pack(fill='x')

    def atualizar():
        def aplicar():
            numero_var.set(formatar_numero(_estado.get('numero') or config.get('numero')))
            if _estado.get('erro'):
                status_var.set(_estado['erro'])
            elif _estado.get('sessao_id'):
                status_var.set('Em atendimento. Alguém conectou com a senha deste equipamento.')
            elif _estado.get('senha_definida'):
                status_var.set('Online. Aguardando conexão.')
            elif config.get('token'):
                status_var.set('Online. Crie a senha para liberar o acesso.')
            else:
                status_var.set('Informe o endereço do sistema e crie a senha.')
            try:
                icone = getattr(_tratar_resposta, 'icone', None)
                if icone:
                    icone.title = '%s — %s' % (APP_NOME, numero_var.get())
            except Exception:
                pass
        root.after(0, aplicar)

    def gravar():
        config['servidor'] = normalizar_servidor(servidor.get())
        config['iniciar_com_windows'] = bool(iniciar.get())
        if not config['servidor']:
            messagebox.showwarning(APP_NOME, 'Informe o endereço do sistema.')
            return
        try:
            registrar(config)
            texto = senha.get().strip()
            if texto:
                salvar_senha(config, texto)
                senha.delete(0, 'end')
            definir_inicio_windows(config['iniciar_com_windows'])
            salvar_config(config)
            atualizar()
            messagebox.showinfo(APP_NOME, 'Número %s salvo. O programa continua ao lado do relógio.' % formatar_numero(config.get('numero')))
        except Exception as exc:
            messagebox.showerror(APP_NOME, str(exc))

    def sugerir():
        senha.delete(0, 'end')
        senha.insert(0, gerar_senha())

    def copiar():
        root.clipboard_clear()
        root.clipboard_append(formatar_numero(config.get('numero')))

    ttk.Button(botoes, text='Salvar e ficar ativo', command=gravar).pack(side='left')
    ttk.Button(botoes, text='Gerar senha', command=sugerir).pack(side='left', padx=6)
    ttk.Button(botoes, text='Copiar número', command=copiar).pack(side='left')

    def mostrar():
        root.deiconify()
        root.lift()

    def ao_fechar():
        if getattr(_tratar_resposta, 'icone', None):
            root.withdraw()
            return
        _parar.set()
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', ao_fechar)
    icone = iniciar_bandeja(root, mostrar)
    if icone and config.get('token') and config.get('servidor'):
        root.withdraw()
        try:
            definir_inicio_windows(bool(config.get('iniciar_com_windows', True)))
        except Exception:
            pass
    threading.Thread(target=loop_remoto, args=(config, atualizar), daemon=True).start()
    atualizar()
    root.mainloop()
    _parar.set()


if __name__ == '__main__':
    main()
