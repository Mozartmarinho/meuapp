(function () {
    if (window.__sgCampanhaTicket) return;
    window.__sgCampanhaTicket = true;

    var KEY = 'sg-campanha-ticket-last-id-v2';
    var KEY_PEND = 'sg-campanha-ticket-pendentes-v1';
    var KEY_SOM = 'sg-campanha-ticket-som-ok-v1';
    var URL = '/api/chamados/campanha';
    var INTERVALO = 4000;
    var INTERVALO_SOM = 1800;
    var fila = [];
    var aberto = false;
    var lastId = 0;
    var timer = null;
    var somTimer = null;
    var emVoo = false;
    var visto = {};
    var pendentes = {};
    var audioCtx = null;
    var somLiberado = false;
    var campanhaAtiva = false;
    var gestoBound = false;

    try {
        lastId = parseInt(localStorage.getItem(KEY) || '0', 10) || 0;
    } catch (e) {
        lastId = 0;
    }
    try {
        somLiberado = localStorage.getItem(KEY_SOM) === '1';
    } catch (eSom) {
        somLiberado = false;
    }
    try {
        var rawPend = sessionStorage.getItem(KEY_PEND);
        if (rawPend) {
            JSON.parse(rawPend).forEach(function (id) {
                var n = parseInt(id, 10);
                if (n) pendentes[n] = { id: n };
            });
        }
    } catch (e0) { /* ignore */ }

    function gravar(id) {
        if (!id || id <= lastId) return;
        lastId = id;
        try { localStorage.setItem(KEY, String(lastId)); } catch (e2) { /* ignore */ }
    }

    function idsPendentes() {
        return Object.keys(pendentes).map(function (k) { return parseInt(k, 10); }).filter(Boolean);
    }

    function persistirPendentes() {
        try { sessionStorage.setItem(KEY_PEND, JSON.stringify(idsPendentes())); } catch (e3) { /* ignore */ }
    }

    function aindaPendente(item) {
        return !item || !item.status || item.status === 'Pendente';
    }

    function marcarPendente(item) {
        if (!item || !item.id || !aindaPendente(item)) return;
        pendentes[item.id] = item;
        persistirPendentes();
        atualizarChip();
        if (!somLiberado) mostrarPedidoSom();
        garantirLembrete();
    }

    function limparPendente(id) {
        if (!id || !pendentes[id]) return;
        delete pendentes[id];
        persistirPendentes();
        atualizarChip();
        if (!idsPendentes().length) pararLembrete();
    }

    function sincronizarPendentes(vivos, consultados) {
        var mapa = {};
        var checados = {};
        (consultados || []).forEach(function (id) { checados[id] = true; });
        (vivos || []).forEach(function (item) {
            if (item && item.id && aindaPendente(item)) mapa[item.id] = item;
        });
        Object.keys(pendentes).forEach(function (id) {
            if (mapa[id]) {
                pendentes[id] = mapa[id];
                return;
            }
            if (!checados[id]) return;
            delete pendentes[id];
        });
        persistirPendentes();
        atualizarChip();
        if (!idsPendentes().length) pararLembrete();
        else {
            if (!somLiberado) mostrarPedidoSom();
            garantirLembrete();
        }
    }

    function tom(ctx, freq, start, dur, vol) {
        var o = ctx.createOscillator();
        var g = ctx.createGain();
        o.type = 'square';
        o.frequency.setValueAtTime(freq, ctx.currentTime + start);
        g.gain.setValueAtTime(0.0001, ctx.currentTime + start);
        g.gain.exponentialRampToValueAtTime(vol, ctx.currentTime + start + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + dur);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(ctx.currentTime + start);
        o.stop(ctx.currentTime + start + dur + 0.02);
    }

    function gravarSomLiberado() {
        somLiberado = true;
        try { localStorage.setItem(KEY_SOM, '1'); } catch (e5) { /* ignore */ }
    }

    function criarAudio() {
        var AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return null;
        try {
            if (!audioCtx) audioCtx = new AC();
        } catch (err) {
            return null;
        }
        return audioCtx;
    }

    function comAudioPronto(cb) {
        var ctx = criarAudio();
        if (!ctx) {
            cb(null);
            return;
        }
        if (ctx.state === 'suspended') {
            ctx.resume().then(function () { cb(ctx); }).catch(function () { cb(null); });
            return;
        }
        cb(ctx);
    }

    function ouvirGestoParaSom() {
        if (gestoBound || !somLiberado) return;
        gestoBound = true;
        function unlock() {
            if (!somLiberado) return;
            comAudioPronto(function (ctx) {
                if (ctx && idsPendentes().length) garantirLembrete();
            });
        }
        ['click', 'keydown', 'touchstart', 'pointerdown'].forEach(function (ev) {
            document.addEventListener(ev, unlock, true);
        });
    }

    function tocarCampainha(forcar) {
        if (!forcar && !idsPendentes().length) return;
        if (!somLiberado) {
            mostrarPedidoSom();
            return;
        }
        comAudioPronto(function (ctx) {
            if (!ctx) return;
            tom(ctx, 880, 0, 0.22, 0.28);
            tom(ctx, 1174.66, 0.12, 0.28, 0.24);
            tom(ctx, 659.25, 0.42, 0.38, 0.3);
            if (navigator.vibrate) {
                try { navigator.vibrate([180, 70, 180, 70, 320]); } catch (e4) { /* ignore */ }
            }
        });
    }

    function pararLembrete() {
        if (somTimer) {
            clearInterval(somTimer);
            somTimer = null;
        }
    }

    function garantirLembrete() {
        if (!idsPendentes().length) {
            pararLembrete();
            return;
        }
        if (!somLiberado) {
            mostrarPedidoSom();
            return;
        }
        ouvirGestoParaSom();
        if (somTimer) return;
        tocarCampainha();
        somTimer = setInterval(function () {
            if (!idsPendentes().length) {
                pararLembrete();
                return;
            }
            tocarCampainha();
        }, INTERVALO_SOM);
    }

    function garantirEstilo() {
        if (document.getElementById('sg-campanha-css')) return;
        var css = document.createElement('style');
        css.id = 'sg-campanha-css';
        css.textContent =
            '#sgCampanhaOverlay{position:fixed;inset:0;z-index:5600;display:none;align-items:center;justify-content:center;' +
            'padding:1rem;background:rgba(12,58,56,.45)}' +
            '#sgCampanhaOverlay.is-open{display:flex}' +
            '#sgCampanhaCard{width:min(420px,100%);background:#fff;border-radius:.7rem;box-shadow:0 18px 48px rgba(12,58,56,.28);' +
            'overflow:hidden;font-family:Manrope,system-ui,sans-serif;color:#2c3e50}' +
            '#sgCampanhaCard header{display:flex;align-items:center;justify-content:space-between;gap:.6rem;' +
            'padding:.85rem 1rem .55rem;background:linear-gradient(180deg,#0c3a38,#0a3332);color:#fff}' +
            '#sgCampanhaCard header h2{margin:0;font-size:.95rem;font-weight:800}' +
            '#sgCampanhaCard header button{background:none;border:0;color:#fff;font-size:1.35rem;line-height:1;cursor:pointer}' +
            '#sgCampanhaCard .sg-campanha-body{padding:.85rem 1rem 1rem}' +
            '#sgCampanhaCard .sg-campanha-os{margin:0 0 .2rem;font-size:1.05rem;font-weight:800;color:#0d9488}' +
            '#sgCampanhaCard .sg-campanha-cli{margin:0 0 .45rem;font-size:.82rem;color:#64748b}' +
            '#sgCampanhaCard .sg-campanha-txt{margin:0;font-size:.86rem;line-height:1.4;color:#334155}' +
            '#sgCampanhaCard footer{display:flex;gap:.45rem;justify-content:flex-end;padding:0 1rem 1rem}' +
            '#sgCampanhaCard footer a,#sgCampanhaCard footer button.sg-campanha-sec{display:inline-flex;align-items:center;' +
            'justify-content:center;padding:.48rem .9rem;border-radius:.35rem;font-size:.8rem;font-weight:700;text-decoration:none;cursor:pointer}' +
            '#sgCampanhaCard footer a{background:#0d9488;color:#fff;border:0}' +
            '#sgCampanhaCard footer button.sg-campanha-sec{background:#e2e8f0;color:#1f2937;border:0}' +
            '#sgCampanhaSomLock{position:fixed;inset:0;z-index:5800;display:none;align-items:center;justify-content:center;' +
            'padding:1rem;background:rgba(8,32,31,.62)}' +
            '#sgCampanhaSomLock.is-open{display:flex}' +
            '#sgCampanhaSomBox{width:min(440px,100%);background:#fff;border-radius:.85rem;box-shadow:0 22px 50px rgba(8,32,31,.35);' +
            'overflow:hidden;font-family:Manrope,system-ui,sans-serif;color:#1f2937}' +
            '#sgCampanhaSomBox header{padding:1rem 1.1rem .7rem;background:#0c3a38;color:#fff}' +
            '#sgCampanhaSomBox header h2{margin:0;font-size:1.05rem;font-weight:800}' +
            '#sgCampanhaSomBox .sg-campanha-body{padding:1rem 1.1rem;font-size:.9rem;line-height:1.45}' +
            '#sgCampanhaSomBox .sg-campanha-body p{margin:0 0 .7rem}' +
            '#sgCampanhaSomBox footer{display:flex;gap:.5rem;justify-content:flex-end;padding:0 1.1rem 1.1rem}' +
            '#sgCampanhaSomAtivar{background:#0d9488;color:#fff;border:0;border-radius:.4rem;padding:.62rem 1.1rem;' +
            'font-size:.9rem;font-weight:800;cursor:pointer}' +
            '#sgCampanhaChip{position:fixed;z-index:5590;right:1rem;bottom:1rem;display:none;align-items:center;gap:.45rem;' +
            'background:#0c3a38;color:#fff;border:0;border-radius:999px;padding:.45rem .9rem;font-size:.78rem;' +
            'font-weight:700;cursor:pointer;box-shadow:0 8px 24px rgba(12,58,56,.28);font-family:Manrope,system-ui,sans-serif}' +
            '#sgCampanhaChip.is-on{display:inline-flex}';
        document.head.appendChild(css);
    }

    function ocultarPedidoSom() {
        var lock = document.getElementById('sgCampanhaSomLock');
        if (lock) lock.classList.remove('is-open');
    }

    function mostrarPedidoSom() {
        if (somLiberado || !campanhaAtiva) return;
        garantirEstilo();
        var lock = document.getElementById('sgCampanhaSomLock');
        if (!lock) {
            lock = document.createElement('div');
            lock.id = 'sgCampanhaSomLock';
            lock.setAttribute('role', 'dialog');
            lock.setAttribute('aria-modal', 'true');
            lock.innerHTML =
                '<div id="sgCampanhaSomBox">' +
                '<header><h2>Ativar som de chamados</h2></header>' +
                '<div class="sg-campanha-body">' +
                '<p>O navegador bloqueia o som até você autorizar.</p>' +
                '<p>Clique em <strong>Ativar som</strong> para ouvir a campainha quando um chamado for aberto. ' +
                'O som continua até alguém atender.</p>' +
                '</div>' +
                '<footer><button type="button" id="sgCampanhaSomAtivar">Ativar som</button></footer>' +
                '</div>';
            document.body.appendChild(lock);
            document.getElementById('sgCampanhaSomAtivar').addEventListener('click', ativarSom);
        }
        lock.classList.add('is-open');
    }

    function ativarSom(ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        if (!criarAudio()) {
            window.alert('Este navegador não permite som. Use Chrome ou Edge.');
            return;
        }
        function pronto() {
            gravarSomLiberado();
            ocultarPedidoSom();
            ouvirGestoParaSom();
            tocarCampainha(true);
            garantirLembrete();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume().then(pronto).catch(function () {
                window.alert('O navegador recusou o som. Clique de novo em Ativar som.');
            });
            return;
        }
        pronto();
    }

    function atualizarChip() {
        garantirEstilo();
        var n = idsPendentes().length;
        var chip = document.getElementById('sgCampanhaChip');
        if (!chip) {
            chip = document.createElement('button');
            chip.id = 'sgCampanhaChip';
            chip.type = 'button';
            chip.addEventListener('click', function () {
                if (!somLiberado) {
                    mostrarPedidoSom();
                    return;
                }
                comAudioPronto(function () {
                    if (idsPendentes().length) garantirLembrete();
                });
                var ids = idsPendentes();
                if (!ids.length) return;
                var item = pendentes[ids[0]];
                if (item) mostrar(item);
            });
            document.body.appendChild(chip);
        }
        if (!n) {
            chip.classList.remove('is-on');
            return;
        }
        chip.textContent = n === 1 ? '1 chamado aguardando atendimento' : (n + ' chamados aguardando atendimento');
        chip.classList.add('is-on');
    }

    function garantirCard() {
        garantirEstilo();
        var overlay = document.getElementById('sgCampanhaOverlay');
        if (overlay) return overlay;
        overlay = document.createElement('div');
        overlay.id = 'sgCampanhaOverlay';
        overlay.setAttribute('role', 'presentation');
        overlay.innerHTML =
            '<div id="sgCampanhaCard" role="dialog" aria-modal="true" aria-labelledby="sgCampanhaTitle">' +
            '<header><h2 id="sgCampanhaTitle">Novo chamado aberto</h2>' +
            '<button type="button" id="sgCampanhaX" aria-label="Fechar">&times;</button></header>' +
            '<div class="sg-campanha-body">' +
            '<p class="sg-campanha-os" id="sgCampanhaOs"></p>' +
            '<p class="sg-campanha-cli" id="sgCampanhaCli"></p>' +
            '<p class="sg-campanha-txt" id="sgCampanhaTxt"></p>' +
            '</div>' +
            '<footer>' +
            '<button type="button" class="sg-campanha-sec" id="sgCampanhaFechar">Fechar</button>' +
            '<a id="sgCampanhaAtender" href="#">Atender</a>' +
            '</footer></div>';
        document.body.appendChild(overlay);
        overlay.addEventListener('click', function (ev) {
            if (ev.target === overlay) fechar();
        });
        document.getElementById('sgCampanhaX').addEventListener('click', fechar);
        document.getElementById('sgCampanhaFechar').addEventListener('click', fechar);
        document.getElementById('sgCampanhaAtender').addEventListener('click', function () {
            var href = this.getAttribute('href') || '';
            var match = href.match(/atender=(\d+)/);
            if (match) limparPendente(parseInt(match[1], 10));
        });
        return overlay;
    }

    function mostrar(item) {
        var overlay = garantirCard();
        document.getElementById('sgCampanhaOs').textContent = item.numero_chamado || '';
        document.getElementById('sgCampanhaCli').textContent = item.cliente || '';
        document.getElementById('sgCampanhaTxt').textContent = item.titulo || 'Um novo ticket foi aberto.';
        var link = document.getElementById('sgCampanhaAtender');
        link.href = item.url || '/chamados';
        overlay.classList.add('is-open');
        aberto = true;
        marcarPendente(item);
        if (!somLiberado) mostrarPedidoSom();
        else garantirLembrete();
    }

    function fechar() {
        var overlay = document.getElementById('sgCampanhaOverlay');
        if (overlay) overlay.classList.remove('is-open');
        aberto = false;
        if (fila.length) mostrar(fila.shift());
        else atualizarChip();
    }

    function enfileirar(itens) {
        if (!itens || !itens.length) return;
        itens.forEach(function (item) {
            if (!item || !item.id) return;
            gravar(item.id);
            marcarPendente(item);
            if (visto[item.id]) return;
            visto[item.id] = true;
            fila.push(item);
        });
        if (!aberto && fila.length) mostrar(fila.shift());
        else if (!somLiberado) mostrarPedidoSom();
        else garantirLembrete();
    }

    function consultar() {
        if (emVoo) return;
        emVoo = true;
        var ids = idsPendentes();
        var url = URL + '?after_id=' + encodeURIComponent(lastId);
        if (ids.length) url += '&ids=' + encodeURIComponent(ids.join(','));
        fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
            .then(function (r) {
                if (r.status === 401) return null;
                return r.json();
            })
            .then(function (data) {
                if (!data || !data.ok || !data.enabled) {
                    if (data && data.ok && data.enabled === false) {
                        campanhaAtiva = false;
                        ocultarPedidoSom();
                        if (timer) {
                            clearInterval(timer);
                            timer = null;
                        }
                        pararLembrete();
                    }
                    return;
                }
                campanhaAtiva = true;
                if (somLiberado) {
                    ouvirGestoParaSom();
                    if (idsPendentes().length) garantirLembrete();
                } else {
                    mostrarPedidoSom();
                }
                if (data.campanhas && data.campanhas.length) {
                    enfileirar(data.campanhas.slice().reverse());
                } else if (lastId <= 0 && data.latest_id) {
                    gravar(data.latest_id);
                }
                if (data.latest_id) gravar(data.latest_id);
                if (ids.length) sincronizarPendentes(data.pendentes || [], ids);
            })
            .catch(function () { /* ignore */ })
            .then(function () { emVoo = false; });
    }

    function iniciar() {
        if (somLiberado) ouvirGestoParaSom();
        consultar();
        timer = setInterval(consultar, INTERVALO);
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible') {
                consultar();
                if (somLiberado && idsPendentes().length) {
                    comAudioPronto(function (ctx) {
                        if (ctx) garantirLembrete();
                    });
                }
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();
