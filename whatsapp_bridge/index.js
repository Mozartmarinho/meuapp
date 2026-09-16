'use strict';

/**
 * Ponte local: abre o WhatsApp Web de verdade no Chrome/Edge deste servidor
 * (Puppeteer), para a sessão parecer um navegador e reduzir bloqueio.
 * Escuta só em 127.0.0.1. Sessão em ./auth.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');

const HOST = process.env.PESAGEM_WA_BRIDGE_HOST || '127.0.0.1';
const PORT = parseInt(process.env.PESAGEM_WA_BRIDGE_PORT || '31085', 10);
const AUTH_DIR = path.join(__dirname, 'auth');
const PID_FILE = path.join(__dirname, 'bridge.pid');
const HEADLESS = process.env.PESAGEM_WA_HEADLESS !== '0';
const USER_AGENT = process.env.PESAGEM_WA_UA || (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
  + '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
);

let Client = null;
let LocalAuth = null;
let puppeteer = null;
let client = null;
let state = 'connecting';
let qrText = null;
let qrImage = null;
let user = null;
let starting = false;
let loggingOut = false;
let startError = null;

function writePid() {
  try {
    fs.writeFileSync(PID_FILE, String(process.pid));
  } catch (err) {
    console.error('pid', err);
  }
}

function clearPid() {
  try {
    fs.unlinkSync(PID_FILE);
  } catch (err) {
    /* ignore */
  }
}

function loadLibs() {
  if (Client) return;
  const wweb = require('whatsapp-web.js');
  Client = wweb.Client;
  LocalAuth = wweb.LocalAuth;
  try {
    puppeteer = require('puppeteer');
  } catch (err) {
    puppeteer = null;
  }
}

function findChrome() {
  const envPath = process.env.PUPPETEER_EXECUTABLE_PATH
    || process.env.CHROME_PATH
    || process.env.PESAGEM_WA_CHROME;
  if (envPath && fs.existsSync(envPath)) return envPath;
  const localApp = process.env.LOCALAPPDATA || '';
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    localApp ? path.join(localApp, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/snap/bin/chromium',
  ];
  for (const p of candidates) {
    if (p && fs.existsSync(p)) return p;
  }
  try {
    if (puppeteer && typeof puppeteer.executablePath === 'function') {
      const bundled = puppeteer.executablePath();
      if (bundled && fs.existsSync(bundled)) return bundled;
    }
  } catch (err) {
    /* ignore */
  }
  return undefined;
}

function toJid(phone) {
  let n = String(phone || '').replace(/\D/g, '');
  if (n.startsWith('00')) n = n.slice(2);
  if (n.startsWith('0')) n = n.slice(1);
  if (n.length <= 11) n = '55' + n;
  return n + '@c.us';
}

function clearQr() {
  qrText = null;
  qrImage = null;
}

async function tryReadUserFromStore(sock) {
  const c = sock || client;
  const page = c && c.pupPage;
  if (!page) return null;
  try {
    const data = await page.evaluate(() => {
      if (typeof window.Store === 'undefined' || !window.Store.User) return null;
      const wid = window.Store.User.getMaybeMePnUser() || window.Store.User.getMaybeMeLidUser();
      let name = '';
      try {
        const conn = window.Store.Conn && window.Store.Conn.serialize
          ? window.Store.Conn.serialize()
          : {};
        name = conn.pushname || conn.name || '';
      } catch (e) { /* ignore */ }
      if (!wid) return name ? { number: '', name: name, id: '' } : null;
      return {
        number: String(wid.user || wid._serialized || ''),
        name: name,
        id: String(wid._serialized || wid.user || ''),
      };
    });
    if (data && (data.number || data.name)) {
      user = {
        id: data.id || data.number,
        number: String(data.number || '').split('@')[0].split(':')[0],
        name: data.name || '',
      };
      return user;
    }
  } catch (err) {
    /* Store ainda não injetado */
  }
  return null;
}

async function refreshUser(sock) {
  const c = sock || client;
  if (!c) return user;
  let number = '';
  let name = '';
  let id = '';
  try {
    const info = c.info || {};
    name = info.pushname || info.name || '';
    const wid = info.wid || info.me;
    if (wid) {
      id = wid._serialized || String(wid.user || '');
      number = String(wid.user || wid._serialized || '').split('@')[0].split(':')[0];
    }
  } catch (err) {
    /* ignore */
  }
  if (!number) {
    await tryReadUserFromStore(c);
    return user;
  }
  user = { id: id || number, number: number, name: name };
  return user;
}

function markOpen(sock) {
  state = 'open';
  startError = null;
  clearQr();
  refreshUser(sock || client).catch(() => {});
}

async function hydrateStatus() {
  if (loggingOut || !client) return;
  const fromStore = await tryReadUserFromStore(client);
  if (fromStore || (client.info && client.info.wid)) {
    markOpen(client);
    await refreshUser(client);
    return;
  }
  if (state === 'open') {
    await refreshUser(client);
  }
}

async function captureQrFromPage(qr) {
  try {
    const page = client && client.pupPage;
    if (page) {
      const handle = await page.$('canvas')
        || await page.$('div[data-ref] canvas')
        || await page.$('img[alt*="QR"]');
      if (handle) {
        const buf = await handle.screenshot({ encoding: 'base64', type: 'png' });
        if (buf) return 'data:image/png;base64,' + buf;
      }
    }
  } catch (err) {
    console.error('qr screenshot', err && err.message ? err.message : err);
  }
  return QRCode.toDataURL(qr, { margin: 1, width: 280 });
}

function bindClientEvents(sock) {
  sock.on('qr', async (qr) => {
    state = 'qr';
    startError = null;
    qrText = qr;
    user = null;
    try {
      qrImage = await captureQrFromPage(qr);
    } catch (err) {
      qrImage = null;
      console.error('QR PNG falhou', err);
    }
  });

  sock.on('ready', () => {
    markOpen(sock);
  });

  sock.on('change_state', (waState) => {
    if (waState === 'CONNECTED') markOpen(sock);
  });

  sock.on('authenticated', () => {
    startError = null;
    clearQr();
    if (state !== 'open') state = 'connecting';
    if (sock.info && sock.info.wid) markOpen(sock);
  });

  sock.on('auth_failure', (msg) => {
    startError = String(msg || 'Falha na autenticação do WhatsApp Web.');
    state = 'close';
    user = null;
    clearQr();
  });

  sock.on('disconnected', (reason) => {
    console.log('whatsapp-web disconnected', reason);
    user = null;
    clearQr();
    state = 'close';
    if (client === sock) client = null;
    sock.destroy().catch(() => {});
    if (loggingOut) return;
    setTimeout(() => {
      startClient().catch((err) => {
        startError = String(err && err.message ? err.message : err);
        state = 'close';
      });
    }, 1500);
  });

  sock.on('message', async (msg) => {
    try {
      if (!msg || msg.fromMe) return;
      const from = String(msg.from || '');
      if (!from.endsWith('@c.us')) return;
      const phone = from.split('@')[0].split(':')[0];
      const text = String(msg.body || '').trim();
      await postInbound({ from: phone, text: text });
    } catch (err) {
      console.error('message inbound', err && err.message ? err.message : err);
    }
  });
}

async function startClient() {
  if (starting || loggingOut) return;
  if (client) return;
  starting = true;
  state = 'connecting';
  startError = null;
  clearQr();
  user = null;
  try {
    loadLibs();
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    const chromePath = findChrome();
    const puppeteerOpts = {
      headless: HEADLESS,
      defaultViewport: { width: 1280, height: 900 },
      ignoreDefaultArgs: ['--enable-automation'],
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-blink-features=AutomationControlled',
        '--window-size=1280,900',
      ],
    };
    if (puppeteer) puppeteerOpts.puppeteer = puppeteer;
    if (chromePath) puppeteerOpts.executablePath = chromePath;
    if (!HEADLESS) {
      puppeteerOpts.args.push('--window-position=-2400,-2400');
    }

    const sock = new Client({
      authStrategy: new LocalAuth({
        clientId: 'pesagem',
        dataPath: AUTH_DIR,
      }),
      puppeteer: puppeteerOpts,
      userAgent: USER_AGENT,
      authTimeoutMs: 0,
      qrMaxRetries: 0,
      takeoverOnConflict: true,
      takeoverTimeoutMs: 8000,
      webVersionCache: { type: 'local' },
    });
    bindClientEvents(sock);
    client = sock;
    await sock.initialize();
    if (sock.pupPage) {
      try {
        await sock.pupPage.waitForFunction(
          'typeof window.Store !== "undefined" && window.Store.User',
          { timeout: 25000 }
        );
      } catch (err) {
        /* ready ainda pode disparar depois */
      }
    }
    await hydrateStatus();
  } catch (err) {
    const msg = String(err && err.message ? err.message : err);
    console.error('startClient', msg);
    startError = chromeMissingMessage(msg);
    state = 'close';
    client = null;
  } finally {
    starting = false;
  }
}

function chromeMissingMessage(msg) {
  const low = String(msg || '').toLowerCase();
  if (low.includes('could not find') || low.includes('chrome') || low.includes('browser')) {
    return 'Não foi possível abrir o Chrome/Edge para o WhatsApp Web interno. Instale o Google Chrome no servidor.';
  }
  return msg || 'Falha ao abrir o WhatsApp Web interno.';
}

async function wipeAuthDir() {
  for (let i = 0; i < 5; i++) {
    try {
      fs.rmSync(AUTH_DIR, { recursive: true, force: true });
      break;
    } catch (err) {
      console.error('limpar auth', err && err.message ? err.message : err);
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
  }
  try {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  } catch (err) {
    /* ignore */
  }
}

async function logoutAndRestart() {
  loggingOut = true;
  state = 'connecting';
  startError = null;
  user = null;
  clearQr();
  const sock = client;
  client = null;
  try {
    if (sock) {
      try {
        await sock.logout();
      } catch (err) {
        console.error('logout', err && err.message ? err.message : err);
      }
      try {
        await sock.destroy();
      } catch (err) {
        /* ignore */
      }
    }
  } finally {
    await new Promise((resolve) => setTimeout(resolve, 600));
    await wipeAuthDir();
    loggingOut = false;
  }
  await startClient();
}

function postInbound(payload) {
  const rawUrl = process.env.PESAGEM_WA_INBOUND_URL || 'http://127.0.0.1/api/chamados/whatsapp/inbound';
  const token = process.env.PESAGEM_WA_INBOUND_TOKEN || '';
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch (err) {
    console.error('inbound url', err && err.message);
    return Promise.resolve();
  }
  const body = JSON.stringify(payload || {});
  const lib = parsed.protocol === 'https:' ? require('https') : http;
  return new Promise((resolve) => {
    const req = lib.request({
      hostname: parsed.hostname,
      port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path: parsed.pathname + (parsed.search || ''),
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': Buffer.byteLength(body),
        'X-WA-Token': token,
      },
      timeout: 45000,
    }, (res) => {
      res.resume();
      resolve();
    });
    req.on('error', (err) => {
      console.error('inbound', err && err.message ? err.message : err);
      resolve();
    });
    req.on('timeout', () => {
      req.destroy();
      resolve();
    });
    req.write(body);
    req.end();
  });
}

function json(res, code, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

function statusPayload() {
  return {
    ok: true,
    engine: 'web',
    state: state,
    qr_image: qrImage,
    user: user,
    error: startError || undefined,
  };
}

const server = http.createServer(async (req, res) => {
  const url = (req.url || '/').split('?')[0];
  try {
    if (req.method === 'GET' && url === '/health') {
      return json(res, 200, { ok: true, engine: 'web', state: state });
    }
    if (req.method === 'GET' && url === '/status') {
      await hydrateStatus();
      return json(res, 200, statusPayload());
    }
    if (req.method === 'POST' && url === '/send') {
      const body = await readBody(req);
      await hydrateStatus();
      if (!client || state !== 'open') {
        return json(res, 409, { ok: false, error: 'WhatsApp não está conectado. Leia o QR Code.' });
      }
      const to = toJid(body.to);
      const text = String(body.text || '').trim();
      if (!text) return json(res, 400, { ok: false, error: 'Mensagem vazia' });
      const sent = await client.sendMessage(to, text);
      const id = sent && sent.id && (sent.id.id || sent.id._serialized);
      return json(res, 200, { ok: true, id: id || null });
    }
    if (req.method === 'POST' && url === '/logout') {
      await logoutAndRestart();
      return json(res, 200, { ok: true, engine: 'web', state: state });
    }
    json(res, 404, { ok: false, error: 'not found' });
  } catch (err) {
    json(res, 500, { ok: false, error: String(err && err.message ? err.message : err) });
  }
});

server.on('error', (err) => {
  if (err && err.code === 'EADDRINUSE') {
    process.exit(0);
  }
  console.error(err);
  process.exit(1);
});

function shutdown() {
  clearPid();
  process.exit(0);
}

process.on('exit', clearPid);
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

server.listen(PORT, HOST, () => {
  writePid();
  console.log('pesagem-whatsapp-web em http://' + HOST + ':' + PORT);
  startClient().catch((err) => {
    startError = String(err && err.message ? err.message : err);
    state = 'close';
    console.error('startClient', err);
  });
});
