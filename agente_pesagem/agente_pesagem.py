"""
Agente local de pesagem — aparência clássica (estilo Delphi/VCL).
Peso ao vivo da balança + menu Configuração para múltiplos controladores.
"""
from __future__ import annotations

import json
import queue
import re
import socket
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog

import requests

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
FONT_WEIGHT = ('Tahoma', 100, 'bold')  # ~10x maior que o texto padrão da UI
FONT_MONO = ('Courier New', 9)
CLR_WEIGHT = '#FF0000'

# Aceita formatos WT1000 e genéricos
# Contínuo completo: 0, 010.000, 000.200, 009.800
# Comando: ww010.000kg / Wn010.000kg
WEIGHT_RE = re.compile(
    r'(?P<sign>[-+])?\s*(?P<value>\d{1,6}(?:[.,]\d{1,4})?)\s*(?P<unit>kg|g|lb)?',
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


def app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_config() -> dict:
    return {
        'servidor_url': 'http://127.0.0.1',
        'api_key': 'saogeraldo-pesagem-2025',
        'balanca_codigo': 'BAL-01',
        'balanca_nome': 'WT1000',
        'balanca_local': 'Recepção / Expedição',
        'modelo': 'WT1000',
        # Adaptador USB Serial (FTDI) neste PC
        'porta_com': 'COM3',
        'baudrate': 9600,
        'bytesize': 8,
        'parity': 'N',
        'stopbits': 1,
        'timeout': 1.0,
        'modo_simulacao': False,
        'envio_automatico': False,
        'intervalo_envio_seg': 2.0,
        'peso_minimo': 0.001,
        'consultar_balanca': True,
        'comandos_consulta': ['R', 'R\r', 'R\n', 'R\r\n'],
        'intervalo_consulta_seg': 0.5,
    }


def load_config() -> dict:
    cfg_path = app_dir() / 'config.json'
    cfg = default_config()
    if cfg_path.exists():
        try:
            cfg.update(json.loads(cfg_path.read_text(encoding='utf-8')))
        except Exception:
            pass
    else:
        save_config(cfg)
    return cfg


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


def parse_peso(linha: str) -> tuple[float | None, str, bool]:
    raw = (linha or '').strip()
    if not raw:
        return None, raw, False

    # WT1000 contínuo completo: S, bruto, tara, liquido
    m = WT1000_CONTINUOUS_RE.search(raw.replace('\x00', ' '))
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
            unit = (m.group('unit') or 'kg').lower()
            if unit == 'lb':
                peso = peso * 0.45359237
            return peso, raw, True

    estavel = True
    low = raw.lower()
    if any(x in low for x in ('unst', 'unstable', 'instavel', 'mov', 'us')):
        estavel = False
    if any(x in low for x in ('stab', 'stable', 'estavel', 'st,', 'st ')):
        estavel = True
    if 'o l' in low or 'ol' == low.replace(' ', ''):
        return None, raw, estavel

    matches = list(WEIGHT_RE.finditer(raw.replace('\x00', ' ')))
    if not matches:
        cleaned = re.sub(r'[^\d.,+\-a-zA-Z ]', ' ', raw)
        matches = list(WEIGHT_RE.finditer(cleaned))
    if not matches:
        return None, raw, estavel

    m = matches[-1]
    try:
        peso = float(m.group('value').replace(',', '.'))
    except ValueError:
        return None, raw, estavel
    if m.group('sign') == '-':
        peso = -peso
    unit = (m.group('unit') or 'kg').lower()
    if unit == 'g':
        peso = peso / 1000.0
    if abs(peso) > 500000:
        return None, raw, estavel
    return peso, raw, estavel


def sunken(parent, **kw):
    f = tk.Frame(parent, bg=CLR_WHITE, highlightthickness=0, **kw)
    # borda estilo Windows sunken
    outer = tk.Frame(parent, bg=CLR_SHADOW, padx=1, pady=1)
    inner = tk.Frame(outer, bg=CLR_LIGHT, padx=1, pady=1)
    f = tk.Frame(inner, bg=CLR_WHITE)
    inner.pack(fill='both', expand=True)
    f.pack(fill='both', expand=True)
    return outer, f


class SerialReader(threading.Thread):
    def __init__(self, cfg: dict, out_q: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.cfg = dict(cfg)
        self.out_q = out_q
        self.stop_event = stop_event

    def run(self):
        if self.cfg.get('modo_simulacao'):
            self._run_sim()
            return
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
            parity_map = {'N': serial.PARITY_NONE, 'E': serial.PARITY_EVEN, 'O': serial.PARITY_ODD}
            ser = serial.Serial(
                port=porta,
                baudrate=baud,
                bytesize=int(self.cfg.get('bytesize', 8)),
                parity=parity_map.get(str(self.cfg.get('parity', 'N')).upper(), serial.PARITY_NONE),
                stopbits=float(self.cfg.get('stopbits', 1)),
                timeout=float(self.cfg.get('timeout', 1.0)),
            )
        except Exception as exc:
            msg = str(exc).lower()
            if 'permission' in msg or 'acesso negado' in msg or 'denied' in msg:
                self.out_q.put(('status', f'Porta {porta} ocupada. Feche outro programa e reabra.'))
            else:
                self.out_q.put(('status', f'Erro {porta}: {exc}'))
            return

        self.out_q.put(('status', f'Conectado {porta} @ {baud}'))
        buffer = ''
        last_poll = 0.0
        last_partial = 0.0
        cmd_idx = 0
        cmds = self.cfg.get('comandos_consulta') or ['R', 'R\r', 'R\n']
        poll_every = float(self.cfg.get('intervalo_consulta_seg', 0.5))
        consultar = bool(self.cfg.get('consultar_balanca', True))

        try:
            while not self.stop_event.is_set():
                agora = time.time()
                if consultar and (agora - last_poll) >= poll_every:
                    try:
                        cmd = cmds[cmd_idx % len(cmds)]
                        cmd_idx += 1
                        if isinstance(cmd, str):
                            cmd = cmd.encode('ascii', errors='ignore')
                        ser.write(cmd)
                    except Exception:
                        pass
                    last_poll = agora

                try:
                    chunk = ser.read(ser.in_waiting or 1)
                except Exception as exc:
                    self.out_q.put(('status', f'Erro leitura: {exc}'))
                    time.sleep(1)
                    continue

                if chunk:
                    text = chunk.decode('latin-1', errors='ignore')
                    buffer += text
                    # tenta extrair peso a cada pedaço recebido (atualização imediata)
                    self._emit(text, porta)
                    if text.strip():
                        preview = text.strip().replace('\n', ' ')[:80]
                        self.out_q.put(('raw', preview))

                while '\n' in buffer or '\r' in buffer:
                    for sep in ('\n', '\r'):
                        if sep in buffer:
                            linha, buffer = buffer.split(sep, 1)
                            break
                    else:
                        break
                    self._emit(linha, porta)

                # buffer contínuo sem quebra de linha
                if len(buffer) >= 4 and (agora - last_partial) >= 0.25:
                    self._emit(buffer[-80:], porta)
                    if len(buffer) > 200:
                        buffer = buffer[-100:]
                    last_partial = agora

                if not chunk:
                    time.sleep(0.03)
        finally:
            try:
                ser.close()
            except Exception:
                pass
            self.out_q.put(('status', 'Serial desconectada'))

    def _emit(self, linha: str, porta: str):
        peso, bruto, estavel = parse_peso(linha)
        if peso is None:
            return
        self.out_q.put(('peso', {
            'peso': peso, 'bruto': bruto, 'estavel': estavel, 'porta': porta
        }))

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


class ConfigDialog(tk.Toplevel):
    """Janela de configuração estilo Delphi."""

    def __init__(self, master, cfg: dict, on_save):
        super().__init__(master)
        self.cfg = dict(cfg)
        self.on_save = on_save
        self.title('Configuração — Controle de Pesagem')
        self.configure(bg=CLR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        # centraliza
        self.geometry('460x520')
        self.update_idletasks()
        x = master.winfo_rootx() + 40
        y = master.winfo_rooty() + 40
        self.geometry(f'+{x}+{y}')

        nb = tk.Frame(self, bg=CLR_BG, padx=10, pady=10)
        nb.pack(fill='both', expand=True)

        self._section(nb, 'Identificação da balança / local')
        self.var_codigo = self._field(nb, 'Código da balança', self.cfg.get('balanca_codigo', 'BAL-01'))
        self.var_nome = self._field(nb, 'Nome', self.cfg.get('balanca_nome', ''))
        self.var_local = self._field(nb, 'Localização', self.cfg.get('balanca_local', ''))

        self._section(nb, 'Porta serial (nativa da placa ou USB)')
        detalhes = listar_portas_detalhe()
        ports = [d for d, _ in detalhes] or ['COM1', 'COM2', 'COM3', 'COM4']
        porta_atual = self.cfg.get('porta_com', 'COM1')
        if porta_atual not in ports and porta_atual != 'AUTO':
            ports = [porta_atual] + ports
            detalhes = [(porta_atual, porta_atual)] + detalhes
        if 'AUTO' not in ports:
            ports = ['AUTO'] + ports
        self.var_porta = tk.StringVar(value=porta_atual)
        row = tk.Frame(nb, bg=CLR_BG)
        row.pack(fill='x', pady=2)
        tk.Label(row, text='Porta COM', width=18, anchor='w', bg=CLR_BG, font=FONT_UI).pack(side='left')
        self.cmb_porta = tk.OptionMenu(row, self.var_porta, *ports)
        self.cmb_porta.config(font=FONT_UI, bg=CLR_BTN)
        self.cmb_porta.pack(side='left', fill='x', expand=True)
        tk.Button(row, text='Atualizar', font=FONT_UI, bg=CLR_BTN, command=self._refresh_ports).pack(side='left', padx=4)

        self.var_baud = self._field(nb, 'Baud rate', str(self.cfg.get('baudrate', 9600)))
        self.var_sim = tk.BooleanVar(value=bool(self.cfg.get('modo_simulacao', False)))
        tk.Checkbutton(
            nb, text='Modo simulação (sem balança física)',
            variable=self.var_sim, bg=CLR_BG, font=FONT_UI, anchor='w'
        ).pack(fill='x', pady=4)

        self._section(nb, 'Servidor')
        self.var_url = self._field(nb, 'URL do servidor', self.cfg.get('servidor_url', ''))
        self.var_key = self._field(nb, 'API Key', self.cfg.get('api_key', ''))
        self.var_auto = tk.BooleanVar(value=bool(self.cfg.get('envio_automatico', False)))
        tk.Checkbutton(
            nb, text='Enviar automaticamente ao estabilizar o peso',
            variable=self.var_auto, bg=CLR_BG, font=FONT_UI, anchor='w'
        ).pack(fill='x', pady=4)

        btns = tk.Frame(self, bg=CLR_BG, padx=10, pady=10)
        btns.pack(fill='x')
        tk.Button(btns, text='OK', width=10, font=FONT_UI, bg=CLR_BTN, command=self._ok).pack(side='right', padx=4)
        tk.Button(btns, text='Cancelar', width=10, font=FONT_UI, bg=CLR_BTN, command=self.destroy).pack(side='right')

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
        self.cfg['balanca_codigo'] = self.var_codigo.get().strip().upper() or 'BAL-01'
        self.cfg['balanca_nome'] = self.var_nome.get().strip()
        self.cfg['balanca_local'] = self.var_local.get().strip()
        self.cfg['porta_com'] = self.var_porta.get().strip() or 'COM3'
        self.cfg['baudrate'] = baud
        self.cfg['modo_simulacao'] = bool(self.var_sim.get())
        self.cfg['servidor_url'] = self.var_url.get().strip().rstrip('/') or 'http://127.0.0.1'
        self.cfg['api_key'] = self.var_key.get().strip()
        self.cfg['envio_automatico'] = bool(self.var_auto.get())
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

        self._build_ui()
        self._start_reader()
        self.root.after(80, self._poll_queue)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _build_ui(self):
        self.root.title('Controle de Pesagem — São Geraldo Service')
        self.root.geometry('720x560')
        self.root.minsize(640, 500)
        self.root.configure(bg=CLR_BG)

        # Menu estilo Delphi
        menubar = tk.Menu(self.root)
        m_arquivo = tk.Menu(menubar, tearoff=0)
        m_arquivo.add_command(label='Configuração...', command=self._abrir_config, accelerator='F2')
        m_arquivo.add_separator()
        m_arquivo.add_command(label='Sair', command=self._on_close)
        menubar.add_cascade(label='Arquivo', menu=m_arquivo)

        m_balanca = tk.Menu(menubar, tearoff=0)
        m_balanca.add_command(label='Reconectar porta', command=self._reconectar)
        m_balanca.add_command(label='Testar servidor', command=self._test_server)
        m_balanca.add_separator()
        m_balanca.add_command(label='Modo simulação (ligar/desligar)', command=self._toggle_sim)
        menubar.add_cascade(label='Balança', menu=m_balanca)

        m_ajuda = tk.Menu(menubar, tearoff=0)
        m_ajuda.add_command(label='Sobre...', command=self._sobre)
        menubar.add_cascade(label='Ajuda', menu=m_ajuda)
        self.root.config(menu=menubar)
        self.root.bind('<F2>', lambda e: self._abrir_config())

        # Barra título painel
        top = tk.Frame(self.root, bg=CLR_NAVY, padx=8, pady=6)
        top.pack(fill='x')
        tk.Label(top, text='CONTROLE DE PESAGEM', font=('Tahoma', 11, 'bold'),
                 fg='white', bg=CLR_NAVY).pack(side='left')
        self.lbl_local_var = tk.StringVar(value='')
        self.lbl_local = tk.Label(top, textvariable=self.lbl_local_var, font=FONT_UI, fg='#A8C53A', bg=CLR_NAVY)
        self.lbl_local.pack(side='right')

        body = tk.Frame(self.root, bg=CLR_BG, padx=12, pady=10)
        body.pack(fill='both', expand=True)

        # GroupBox: Identificação
        grp = tk.LabelFrame(body, text=' Controlador / Local ', font=FONT_UI, bg=CLR_BG, fg=CLR_BLACK, padx=8, pady=6)
        grp.pack(fill='x', pady=(0, 8))
        self.info_var = tk.StringVar()
        tk.Label(grp, textvariable=self.info_var, font=FONT_UI, bg=CLR_BG, anchor='w', justify='left').pack(fill='x')

        # GroupBox: Peso
        grp2 = tk.LabelFrame(body, text=' Peso atual (ao vivo) ', font=FONT_UI, bg=CLR_BG, fg=CLR_BLACK, padx=8, pady=8)
        grp2.pack(fill='both', expand=True, pady=(0, 8))

        outer = tk.Frame(grp2, bg=CLR_SHADOW, padx=2, pady=2)
        outer.pack(fill='both', expand=True)
        inner = tk.Frame(outer, bg=CLR_BLACK, padx=2, pady=2)
        inner.pack(fill='both', expand=True)
        display = tk.Frame(inner, bg='#000000')
        display.pack(fill='both', expand=True)

        self.peso_var = tk.StringVar(value='0.000')
        tk.Label(
            display, textvariable=self.peso_var, font=FONT_WEIGHT,
            fg=CLR_WEIGHT, bg='#000000', pady=8
        ).pack(fill='both', expand=True)
        tk.Label(
            display, text='kg', font=('Tahoma', 22, 'bold'),
            fg=CLR_WEIGHT, bg='#000000'
        ).pack(pady=(0, 10))

        meta = tk.Frame(grp2, bg=CLR_BG)
        meta.pack(fill='x', pady=(6, 0))
        self.estavel_var = tk.StringVar(value='—')
        self.porta_var = tk.StringVar(value='')
        tk.Label(meta, textvariable=self.estavel_var, font=FONT_UI, bg=CLR_BG, anchor='w').pack(side='left')
        tk.Label(meta, textvariable=self.porta_var, font=FONT_UI, bg=CLR_BG, anchor='e').pack(side='right')

        # Botões estilo Delphi
        btn_row = tk.Frame(body, bg=CLR_BG)
        btn_row.pack(fill='x', pady=(0, 6))
        self.btn_enviar = tk.Button(
            btn_row, text='Enviar para o servidor', font=('Tahoma', 10, 'bold'),
            bg=CLR_BTN, relief='raised', width=22, height=2, command=self.enviar_peso
        )
        self.btn_enviar.pack(side='left')
        tk.Button(
            btn_row, text='Configuração (F2)', font=FONT_UI,
            bg=CLR_BTN, relief='raised', width=16, height=2, command=self._abrir_config
        ).pack(side='left', padx=8)
        tk.Button(
            btn_row, text='Reconectar', font=FONT_UI,
            bg=CLR_BTN, relief='raised', width=12, height=2, command=self._reconectar
        ).pack(side='left')

        # Status bar
        status_bar = tk.Frame(self.root, bg=CLR_STATUS, relief='sunken', bd=1)
        status_bar.pack(fill='x', side='bottom')
        self.status_var = tk.StringVar(value='Pronto.')
        tk.Label(status_bar, textvariable=self.status_var, font=FONT_UI,
                 bg=CLR_STATUS, anchor='w', padx=6, pady=2).pack(fill='x')

        self._refresh_info()

    def _refresh_info(self):
        self.info_var.set(
            f"Código: {self.cfg.get('balanca_codigo')}   |   "
            f"Nome: {self.cfg.get('balanca_nome') or '-'}   |   "
            f"Local: {self.cfg.get('balanca_local') or '-'}"
        )
        self.lbl_local_var.set(self.cfg.get('balanca_local') or self.cfg.get('balanca_codigo'))
        self.porta_var.set(f"COM: {self.cfg.get('porta_com')}")

    def _set_status(self, text: str):
        self.status_var.set(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    def _abrir_config(self):
        ConfigDialog(self.root, self.cfg, self._aplicar_config)

    def _aplicar_config(self, cfg: dict):
        self.cfg = cfg
        self._refresh_info()
        self._set_status('Configuração salva. Reconectando...')
        self._reconectar()

    def _reconectar(self):
        self.stop_event.set()
        time.sleep(0.15)
        self.stop_event = threading.Event()
        self._start_reader()

    def _start_reader(self):
        self.reader = SerialReader(self.cfg, self.q, self.stop_event)
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
                self.q.put(('status', 'Servidor online' if r.ok else f'Servidor HTTP {r.status_code}'))
            except requests.RequestException as exc:
                self.q.put(('status', f'Servidor inacessível: {exc}'))

        threading.Thread(target=work, daemon=True).start()

    def _sobre(self):
        messagebox.showinfo(
            'Sobre',
            'Controle de Pesagem\nSão Geraldo Service\n\n'
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
                    self.porta_var.set(f'COM: {self.porta_atual}')
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
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _update_peso(self, data: dict):
        peso = float(data['peso'])
        self.peso_atual = peso
        self.bruto_atual = data.get('bruto') or ''
        self.estavel_atual = bool(data.get('estavel', True))
        self.porta_atual = data.get('porta') or self.porta_atual

        self.peso_var.set(f'{peso:.3f}')
        self.estavel_var.set('Estável' if self.estavel_atual else 'Em movimento...')
        self.porta_var.set(f'COM: {self.porta_atual}')
        self._set_status(f'Peso: {peso:.3f} kg')

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
                    self.q.put(('envio_erro', f'HTTP {r.status_code}: {r.text[:180]}'))
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
    AgenteApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
