(function (w) {
    'use strict';

    var cfg = {
        addUrl: '',
        idSelects: [],
        nomeSelects: [],
    };

    function $(id) {
        return document.getElementById(id);
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function acoesHtml(id) {
        return (
            '<button type="button" class="btn tec-btn-sm tec-btn-muted" onclick="ChamadoSetorCadastro.editar(' + id + ')">' +
            '<i class="fas fa-edit"></i> Editar</button> ' +
            '<button type="button" class="btn tec-btn-sm tec-btn-danger" onclick="ChamadoSetorCadastro.excluir(' + id + ')">' +
            '<i class="fas fa-trash"></i> Excluir</button>'
        );
    }

    function rowHtml(d) {
        var ativo = d.ativo !== false;
        return (
            '<tr id="setor-row-' + d.id + '" data-nome="' + esc(d.nome) + '">' +
            '<td>' + esc(d.nome) + '</td>' +
            '<td><span class="tec-badge ' + (ativo ? 'tec-badge-ok' : 'tec-badge-off') + '" id="setor-status-' + d.id + '">' +
            (ativo ? 'Ativo' : 'Inativo') + '</span></td>' +
            '<td class="setor-acoes">' + acoesHtml(d.id) + '</td></tr>'
        );
    }

    function selects(ids) {
        return (ids || []).map($).filter(Boolean);
    }

    function appendIdOption(sel, id, nome) {
        if (!sel) return;
        var exists = Array.from(sel.options).some(function (o) { return o.value === String(id); });
        if (exists) {
            Array.from(sel.options).forEach(function (o) {
                if (o.value === String(id)) o.textContent = nome;
            });
            return;
        }
        var opt = document.createElement('option');
        opt.value = id;
        opt.textContent = nome;
        sel.appendChild(opt);
    }

    function appendNomeOption(sel, nome, oldNome) {
        if (!sel || !nome) return;
        if (oldNome && oldNome !== nome) {
            Array.from(sel.options).forEach(function (o) {
                if (o.value === oldNome) {
                    o.value = nome;
                    o.textContent = nome;
                }
            });
        }
        var exists = Array.from(sel.options).some(function (o) { return o.value === nome; });
        if (exists) return;
        var opt = document.createElement('option');
        opt.value = nome;
        opt.textContent = nome;
        sel.appendChild(opt);
    }

    function removeIdOption(sel, id) {
        if (!sel) return;
        var opt = sel.querySelector('option[value="' + id + '"]');
        if (opt) opt.remove();
    }

    function removeNomeOption(sel, nome) {
        if (!sel || !nome) return;
        Array.from(sel.options).forEach(function (o) {
            if (o.value === nome) o.remove();
        });
    }

    function setTitle(text) {
        var el = $('modalSetorTitulo');
        if (el) el.textContent = text;
    }

    function showErro(msg) {
        var erro = $('setorErro');
        if (!erro) return;
        if (msg) {
            erro.textContent = msg;
            erro.style.display = '';
        } else {
            erro.textContent = '';
            erro.style.display = 'none';
        }
    }

    function abrirModal() {
        showErro('');
        var overlay = $('modalSetorOverlay');
        var modal = $('modalSetor');
        if (overlay) overlay.style.display = '';
        if (modal) modal.style.display = '';
        var input = $('setorNome');
        if (input) input.focus();
    }

    function fecharModal() {
        var overlay = $('modalSetorOverlay');
        var modal = $('modalSetor');
        if (overlay) overlay.style.display = 'none';
        if (modal) modal.style.display = 'none';
        showErro('');
    }

    function nomeDaLinha(id) {
        var row = $('setor-row-' + id);
        if (!row) return '';
        return (row.getAttribute('data-nome') || (row.cells[0] && row.cells[0].textContent) || '').trim();
    }

    function syncAdded(d) {
        selects(cfg.idSelects).forEach(function (sel) { appendIdOption(sel, d.id, d.nome); });
        selects(cfg.nomeSelects).forEach(function (sel) { appendNomeOption(sel, d.nome); });
    }

    function syncRenamed(d, oldNome) {
        selects(cfg.idSelects).forEach(function (sel) { appendIdOption(sel, d.id, d.nome); });
        selects(cfg.nomeSelects).forEach(function (sel) { appendNomeOption(sel, d.nome, oldNome); });
    }

    function syncDeleted(id, nome) {
        selects(cfg.idSelects).forEach(function (sel) { removeIdOption(sel, id); });
        selects(cfg.nomeSelects).forEach(function (sel) { removeNomeOption(sel, nome); });
    }

    function ensureTbody() {
        var tbody = document.querySelector('#tabSetores tbody');
        var vazio = $('setores-vazio');
        if (vazio) vazio.remove();
        return tbody;
    }

    function novo() {
        var hid = $('setorId');
        if (hid) hid.value = '';
        var input = $('setorNome');
        if (input) input.value = '';
        setTitle('Adicionar Setor');
        abrirModal();
    }

    function editar(id) {
        var hid = $('setorId');
        if (hid) hid.value = String(id);
        var input = $('setorNome');
        if (input) input.value = nomeDaLinha(id);
        setTitle('Editar Setor');
        abrirModal();
    }

    function salvar() {
        var nome = ($('setorNome') && $('setorNome').value || '').trim();
        if (!nome) {
            showErro('Informe o nome do setor.');
            return;
        }
        var id = ($('setorId') && $('setorId').value || '').trim();
        var url = id ? '/chamados/setores/' + id + '/editar' : cfg.addUrl;
        if (!url) {
            showErro('URL de cadastro não configurada.');
            return;
        }
        var fd = new FormData();
        fd.append('nome', nome);
        fetch(url, { method: 'POST', body: fd })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.ok) {
                    showErro(d.error || 'Erro ao salvar.');
                    return;
                }
                var oldNome = id ? nomeDaLinha(id) : '';
                fecharModal();
                if (id) {
                    var row = $('setor-row-' + id);
                    if (row) {
                        row.setAttribute('data-nome', d.nome);
                        if (row.cells[0]) row.cells[0].textContent = d.nome;
                    }
                    syncRenamed(d, oldNome);
                } else {
                    var tbody = ensureTbody();
                    if (tbody) tbody.insertAdjacentHTML('beforeend', rowHtml(d));
                    syncAdded(d);
                }
            })
            .catch(function () {
                showErro('Erro de comunicação.');
            });
    }

    function excluir(id) {
        var nome = nomeDaLinha(id);
        if (!w.confirm('Excluir o setor' + (nome ? ' "' + nome + '"' : '') + '?')) return;
        fetch('/chamados/setores/' + id + '/excluir', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.ok) {
                    w.alert(d.error || 'Não foi possível excluir.');
                    return;
                }
                var row = $('setor-row-' + id);
                if (row) row.remove();
                syncDeleted(id, nome);
                var tbody = document.querySelector('#tabSetores tbody');
                if (tbody && !tbody.querySelector('tr')) {
                    tbody.innerHTML = '<tr id="setores-vazio"><td colspan="3" style="text-align:center;color:var(--gray-500)">Nenhum setor cadastrado.</td></tr>';
                }
            })
            .catch(function () {
                w.alert('Erro de comunicação.');
            });
    }

    function init(options) {
        cfg = {
            addUrl: (options && options.addUrl) || '',
            idSelects: (options && options.idSelects) || [],
            nomeSelects: (options && options.nomeSelects) || [],
        };
        var input = $('setorNome');
        if (input && !input.dataset.enterBound) {
            input.dataset.enterBound = '1';
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    salvar();
                }
            });
        }
    }

    w.ChamadoSetorCadastro = {
        init: init,
        novo: novo,
        editar: editar,
        salvar: salvar,
        excluir: excluir,
        fechar: fecharModal,
        acoesHtml: acoesHtml,
        rowHtml: rowHtml,
    };
})(window);
