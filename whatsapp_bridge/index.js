'use strict';

/**
 * Ponte local WhatsApp Web (Baileys) para o Controle de Pesagem.
 * Escuta só em 127.0.0.1. Sessão em ./auth.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const pino = require('pino');
const QRCode = require('qrcode');

const HOST = process.env.PESAGEM_WA_BRIDGE_HOST || '127.0.0.1';
const PORT = parseInt(process.env.PESAGEM_WA_BRIDGE_PORT || '31085', 10);
const AUTH_DIR = path.join(__dirname, 'auth');

const logger = pino({ level: process.env.PESAGEM_WA_LOG || 'silent' });

let sock = null;
let state = 'connecting';
let qrText = null;
let qrImage = null;
let user = null;
let starting = false;
let baileys = null;

function loadBaileys() {
  if (baileys) return baileys;
  const mod = require('@whiskeysockets/baileys');
  baileys = {
    makeWASocket: mod.default || mod.makeWASocket,
    useMultiFileAuthState: mod.useMultiFileAuthState,
    DisconnectReason: mod.DisconnectReason || {},
    fetchLatestBaileysVersion: mod.fetchLatestBaileysVersion,
  };
  return baileys;
}

function toJid(phone) {
  let n = String(phone || '').replace(/\D/g, '');
  if (n.startsWith('00')) n = n.slice(2);
  if (n.startsWith('0')) n = n.slice(1);
  if (n.length <= 11) n = '55' + n;
  return n + '@s.whatsapp.net';
}

async function startSock() {
  if (starting) return;
  starting = true;
  try {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    const { makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = loadBaileys();
    const { state: authState, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

    let version;
    try {
      const latest = await fetchLatestBaileysVersion();
      version = latest && latest.version;
    } catch (err) {
      logger.warn({ err: String(err) }, 'fetchLatestBaileysVersion falhou');
    }

    const opts = {
      auth: authState,
      logger,
      printQRInTerminal: false,
      browser: ['Sao Geraldo Pesagem', 'Chrome', '122.0.0'],
      markOnlineOnConnect: false,
      shouldSyncHistoryMessage: () => false,
    };
    if (version) opts.version = version;

    sock = makeWASocket(opts);
    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update || {};
      if (qr) {
        state = 'qr';
        qrText = qr;
        try {
          qrImage = await QRCode.toDataURL(qr, { margin: 1, width: 280 });
        } catch (err) {
          qrImage = null;
          logger.warn({ err: String(err) }, 'QR PNG falhou');
        }
        user = null;
      }
      if (connection === 'open') {
        state = 'open';
        qrText = null;
        qrImage = null;
        const id = (sock.user && (sock.user.id || sock.user.jid)) || '';
        const number = String(id).split('@')[0].split(':')[0];
        user = { id: id, number: number, name: (sock.user && sock.user.name) || '' };
      }
      if (connection === 'connecting') {
        if (state !== 'qr' && state !== 'open') state = 'connecting';
      }
      if (connection === 'close') {
        const statusCode = lastDisconnect && lastDisconnect.error && lastDisconnect.error.output
          ? lastDisconnect.error.output.statusCode
          : 0;
        const loggedOut = statusCode === (DisconnectReason.loggedOut || 401);
        sock = null;
        user = null;
        qrText = null;
        qrImage = null;
        state = loggedOut ? 'close' : 'connecting';
        if (loggedOut) {
          try {
            fs.rmSync(AUTH_DIR, { recursive: true, force: true });
            fs.mkdirSync(AUTH_DIR, { recursive: true });
          } catch (err) {
            logger.warn({ err: String(err) }, 'limpar auth');
          }
        }
        setTimeout(() => {
          starting = false;
          startSock().catch((err) => {
            starting = false;
            state = 'close';
            logger.error({ err: String(err) }, 'reconnect');
          });
        }, loggedOut ? 800 : 2500);
        return;
      }
    });
  } finally {
    starting = false;
  }
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

const server = http.createServer(async (req, res) => {
  const url = (req.url || '/').split('?')[0];
  try {
    if (req.method === 'GET' && url === '/health') {
      return json(res, 200, { ok: true, state: state });
    }
    if (req.method === 'GET' && url === '/status') {
      return json(res, 200, {
        ok: true,
        state: state,
        qr: qrText,
        qr_image: qrImage,
        user: user,
      });
    }
    if (req.method === 'POST' && url === '/send') {
      const body = await readBody(req);
      if (!sock || state !== 'open') {
        return json(res, 409, { ok: false, error: 'WhatsApp não está conectado. Leia o QR Code.' });
      }
      const to = toJid(body.to);
      const text = String(body.text || '').trim();
      if (!text) return json(res, 400, { ok: false, error: 'Mensagem vazia' });
      const sent = await sock.sendMessage(to, { text: text });
      return json(res, 200, { ok: true, id: sent && sent.key && sent.key.id });
    }
    if (req.method === 'POST' && url === '/logout') {
      try {
        if (sock) await sock.logout();
      } catch (err) {
        logger.warn({ err: String(err) }, 'logout');
      }
      sock = null;
      user = null;
      qrText = null;
      qrImage = null;
      state = 'close';
      try {
        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        fs.mkdirSync(AUTH_DIR, { recursive: true });
      } catch (err) {
        logger.warn({ err: String(err) }, 'limpar auth no logout');
      }
      setTimeout(() => {
        startSock().catch((err) => logger.error({ err: String(err) }, 'restart após logout'));
      }, 500);
      return json(res, 200, { ok: true });
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

server.listen(PORT, HOST, () => {
  console.log('pesagem-whatsapp-bridge em http://' + HOST + ':' + PORT);
  startSock().catch((err) => {
    state = 'close';
    console.error('startSock', err);
  });
});
