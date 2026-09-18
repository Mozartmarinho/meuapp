(function () {
    if (window.__sgCampanhaTicket) return;
    window.__sgCampanhaTicket = true;

    var KEY = 'sg-campanha-ticket-last-id';
    var URL = '/api/chamados/campanha';
    var INTERVALO = 8000;
    var fila = [];
    var aberto = false;
    var lastId = 0;
    var timer = null;
    var emVoo = false;
    var visto = {};

    try {
        lastId = parseInt(localStorage.getItem(KEY) || '0', 10) || 0;
    } catch (e) {
        lastId = 0;
    }

    function gravar(id) {
        if (!id || id <= lastId) return;
        lastId = id;
        try { localStorage.setItem(KEY, String(lastId)); } catch (e2) { /* ignore */ }
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
            '#sgCampanhaCard footer button.sg-campanha-sec{background:#e2e8f0;color:#1f2937;border:0}';
        document.head.appendChild(css);
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
    }

    function fechar() {
        var overlay = document.getElementById('sgCampanhaOverlay');
        if (overlay) overlay.classList.remove('is-open');
        aberto = false;
        if (fila.length) mostrar(fila.shift());
    }

    function enfileirar(itens) {
        if (!itens || !itens.length) return;
        itens.forEach(function (item) {
            if (!item || !item.id) return;
            gravar(item.id);
            if (visto[item.id]) return;
            visto[item.id] = true;
            fila.push(item);
        });
        if (!aberto && fila.length) mostrar(fila.shift());
    }

    function consultar() {
        if (document.visibilityState === 'hidden') return;
        if (emVoo) return;
        emVoo = true;
        var url = URL + '?after_id=' + encodeURIComponent(lastId);
        fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
            .then(function (r) {
                if (r.status === 401) return null;
                return r.json();
            })
            .then(function (data) {
                if (!data || !data.ok || !data.enabled) {
                    if (timer) { clearInterval(timer); timer = null; }
                    return;
                }
                if (lastId <= 0) {
                    gravar(data.latest_id || 0);
                    return;
                }
                if (data.campanhas && data.campanhas.length) {
                    enfileirar(data.campanhas.slice().reverse());
                }
                if (data.latest_id) gravar(data.latest_id);
            })
            .catch(function () { /* ignore */ })
            .then(function () { emVoo = false; });
    }

    function iniciar() {
        consultar();
        timer = setInterval(consultar, INTERVALO);
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible') consultar();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();
