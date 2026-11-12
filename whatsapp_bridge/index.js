'use strict';

/**
 * Ponte local: abre o WhatsApp Web de verdade no Chrome/Edge deste servidor
 * (Puppeteer), para a sessão parecer um navegador e reduzir bloqueio.
 * Escuta só em 127.0.0.1. Sessão em ./auth.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const QRCode = require('qrcode');

const HOST = process.env.PESAGEM_WA_BRIDGE_HOST || '127.0.0.1';
const PORT = parseInt(process.env.PESAGEM_WA_BRIDGE_PORT || '31085', 10);
const AUTH_DIR = path.join(__dirname, 'auth');
const PID_FILE = path.join(__dirname, 'bridge.pid');
const HEADLESS = process.env.PESAGEM_WA_HEADLESS !== '0';

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

function chromeMajorVersion(chromePath) {
  const bin = chromePath || 'google-chrome';
  try {
    const out = execFileSync(bin, ['--version'], {
      encoding: 'utf8',
      timeout: 4000,
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    const match = String(out).match(/(\d+)\./);
    if (match) return match[1];
  } catch (err) {
    /* ignore */
  }
  return null;
}

function buildUserAgent(chromePath) {
  if (process.env.PESAGEM_WA_UA) return process.env.PESAGEM_WA_UA;
  const major = chromeMajorVersion(chromePath) || '131';
  return (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    + '(KHTML, like Gecko) Chrome/' + major + '.0.0.0 Safari/537.36'
  );
}

function toJid(phone) {
  const raw = String(phone || '').trim();
  if (raw.includes('@')) return raw;
  let n = raw.replace(/\D/g, '');
  if (n.startsWith('00')) n = n.slice(2);
  if (n.startsWith('0')) n = n.slice(1);
  if (n.length <= 11) n = '55' + n;
  return n + '@c.us';
}

function isDirectChat(jid) {
  const id = String(jid || '');
  if (!id || id.includes('status@') || id.endsWith('@broadcast')) return false;
  if (id.endsWith('@g.us') || id.endsWith('@newsletter')) return false;
  return (
    id.endsWith('@c.us')
    || id.endsWith('@s.whatsapp.net')
    || id.endsWith('@lid')
  );
}

function inboundToken() {
  if (process.env.PESAGEM_WA_INBOUND_TOKEN) return process.env.PESAGEM_WA_INBOUND_TOKEN;
  try {
    return fs.readFileSync(path.join(__dirname, '.token'), 'utf8').trim();
  } catch (err) {
    return '';
  }
}

async function resolvePhone(jid) {
  const id = String(jid || '');
  const userPart = id.split('@')[0].split(':')[0];
  if (id.endsWith('@c.us') || id.endsWith('@s.whatsapp.net')) return userPart;
  if (client && typeof client.getContactLidAndPhone === 'function') {
    try {
      const mapped = await client.getContactLidAndPhone([id]);
      const pn = mapped && mapped[0] && mapped[0].pn;
      if (pn) {
        const phone = String(pn).split('@')[0].split(':')[0];
        if (phone) return phone;
      }
    } catch (err) {
      console.error('lid->phone', err && err.message ? err.message : err);
    }
  }
  return userPart;
}

const inboundSeen = new Set();

async function handleIncoming(msg, source) {
  if (!msg || msg.fromMe || msg.isStatus) return;
  const id = msg.id && (msg.id._serialized || msg.id.id);
  if (id) {
    if (inboundSeen.has(id)) return;
    inboundSeen.add(id);
    if (inboundSeen.size > 400) inboundSeen.clear();
  }
  const jid = String(msg.from || '');
  if (!isDirectChat(jid)) {
    console.log('inbound ignorado', source, jid, msg.type || '');
    return;
  }
  const phone = await resolvePhone(jid);
  const text = String(msg.body || '').trim();
  console.log('inbound', source, jid, phone, (text || '').slice(0, 80));
  await postInbound({ from: phone, text: text, jid: jid });
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

function bindClientEvents(sock) {
  sock.on('qr', async (qr) => {
    state = 'qr';
    startError = null;
    qrText = qr;
    user = null;
    try {
      qrImage = await QRCode.toDataURL(qr, { margin: 1, width: 280, errorCorrectionLevel: 'M' });
    } catch (err) {
      qrImage = null;
      console.error('QR PNG falhou', err);
    }
    console.log('qr atualizado');
  });

  sock.on('ready', () => {
    console.log('whatsapp-web ready');
    markOpen(sock);
  });

  sock.on('change_state', (waState) => {
    if (waState === 'CONNECTED') markOpen(sock);
  });

  sock.on('authenticated', () => {
    console.log('whatsapp-web authenticated');
    startError = null;
    clearQr();
    if (state !== 'open') state = 'connecting';
    if (sock.info && sock.info.wid) markOpen(sock);
  });

  sock.on('auth_failure', (msg) => {
    startError = String(msg || 'Falha na autenticação do WhatsApp Web.');
    console.error('whatsapp-web auth_failure', startError);
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
      await handleIncoming(msg, 'message');
    } catch (err) {
      console.error('message inbound', err && err.message ? err.message : err);
    }
  });

  sock.on('message_create', async (msg) => {
    try {
      await handleIncoming(msg, 'create');
    } catch (err) {
      console.error('message_create inbound', err && err.message ? err.message : err);
    }
  });

  sock.on('message_ciphertext', (msg) => {
    console.log('inbound ciphertext', msg && msg.from);
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
    const userAgent = buildUserAgent(chromePath);
    console.log('chrome', chromePath || 'bundled', 'ua', userAgent);
    const puppeteerOpts = {
      headless: HEADLESS ? 'new' : false,
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
      userAgent: userAgent,
      authTimeoutMs: 0,
      qrMaxRetries: 0,
      takeoverOnConflict: false,
      webVersionCache: { type: 'none' },
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
  const token = inboundToken();
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
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        if (res.statusCode >= 400) {
          const raw = Buffer.concat(chunks).toString('utf8').slice(0, 300);
          console.error('inbound http', res.statusCode, raw);
        }
        resolve();
      });
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
