(function () {
  var cfg = window.LOGISTICA || {};
  var kind = cfg.kind;
  if (!kind) return;

  var specs = {
    frota: {
      url: '/api/logistica/veiculos',
      title: 'Veículo',
      columns: [
        ['placa', 'Placa'], ['modelo', 'Modelo'], ['ano', 'Ano'], ['renavam', 'Renavam'],
        ['capacidade', 'Capacidade'], ['unidade', 'Unidade'], ['valor_veiculo', 'Valor veículo'],
        ['ativo', 'Ativo']
      ],
      fields: [
        ['placa', 'Placa', 'text'], ['modelo', 'Modelo', 'text'], ['ano', 'Ano', 'text'],
        ['renavam', 'Renavam', 'text'], ['capacidade', 'Capacidade', 'text'],
        ['unidade', 'Unidade', 'text'], ['valor_veiculo', 'Valor veículo', 'number'],
        ['valor_carroceria', 'Valor carroceria', 'number'],
        ['valor_plataforma', 'Valor plataforma', 'number'],
        ['gaiolas', 'Gaiolas', 'number'], ['observacao', 'Observação', 'text', true]
      ]
    },
    lancamentos: {
      url: '/api/logistica/lancamentos',
      title: 'Lançamento',
      columns: [
        ['data', 'Data'], ['placa', 'Placa'], ['categoria', 'Categoria'], ['descricao', 'Descrição'],
        ['valor', 'Valor'], ['km', 'Km'], ['litros', 'Litros'], ['posto', 'Posto']
      ],
      fields: [
        ['data', 'Data', 'date'], ['veiculo_id', 'Veículo', 'veiculo'],
        ['categoria', 'Categoria', 'select-cat'], ['descricao', 'Descrição', 'text', true],
        ['valor', 'Valor', 'number'], ['km', 'Km', 'number'], ['litros', 'Litros', 'number'],
        ['posto', 'Posto', 'text'], ['observacao', 'Observação', 'text', true]
      ]
    },
    manutencao: {
      url: '/api/logistica/manutencoes',
      title: 'Nota / Manutenção',
      columns: [
        ['data', 'Data'], ['placa', 'Placa'], ['tipo_servico', 'Serviço'], ['nf', 'NF'],
        ['fornecedor', 'Fornecedor'], ['descricao', 'Descrição'], ['valor', 'Valor'],
        ['parcelas', 'Parcelas'], ['vencimento', 'Vencimento'], ['status', 'Status']
      ],
      fields: [
        ['data', 'Data', 'date'], ['veiculo_id', 'Veículo', 'veiculo'],
        ['tipo_servico', 'Tipo de serviço', 'select-extra'],
        ['categoria', 'Categoria', 'text'], ['responsavel', 'Responsável', 'text'],
        ['fornecedor', 'Fornecedor', 'text'], ['nf', 'Nota fiscal', 'text'],
        ['descricao', 'Descrição', 'text', true], ['valor', 'Valor', 'number'],
        ['parcelas', 'Parcelas', 'number'], ['parcelas_pagas', 'Parcelas pagas', 'number'],
        ['vencimento', 'Vencimento', 'date'], ['status', 'Status', 'select-cat'],
        ['observacao', 'Observação', 'text', true]
      ]
    },
    revisoes: {
      url: '/api/logistica/revisoes',
      title: 'Revisão',
      columns: [
        ['placa', 'Placa'], ['tipo', 'Tipo'], ['km_previsto', 'Km previsto'], ['data_prevista', 'Data prevista'],
        ['status', 'Status'], ['data_realizado', 'Realizado']
      ],
      fields: [
        ['veiculo_id', 'Veículo', 'veiculo'], ['tipo', 'Tipo', 'text'],
        ['km_previsto', 'Km previsto', 'number'], ['data_prevista', 'Data prevista', 'date'],
        ['km_realizado', 'Km realizado', 'number'], ['data_realizado', 'Data realizado', 'date'],
        ['status', 'Status', 'select-cat'], ['observacao', 'Observação', 'text', true]
      ]
    },
    rotas: {
      url: '/api/logistica/rotas',
      title: 'Rota',
      columns: [
        ['nome', 'Rota'], ['origem', 'Origem'], ['destino', 'Destino'],
        ['status', 'Status'], ['km', 'Km'], ['setor', 'Setor'],
        ['placa_padrao', 'Placa'], ['motorista', 'Motorista']
      ],
      fields: [
        ['origem_ponto_id', 'Ponto de origem', 'ponto'],
        ['destino_ponto_id', 'Ponto de destino', 'ponto'],
        ['status', 'Status', 'select-cat'],
        ['nome', 'Nome', 'text', true],
        ['setor', 'Setor', 'text'], ['km', 'Km', 'number'],
        ['placa_padrao', 'Placa padrão', 'text'],
        ['motorista', 'Motorista', 'text'], ['ajudante', 'Ajudante', 'text']
      ]
    },
    folgas: {
      url: '/api/logistica/folgas',
      title: 'Folga',
      columns: [
        ['colaborador', 'Colaborador'], ['setor', 'Setor'], ['rota', 'Rota'], ['dias_texto', 'Dias']
      ],
      fields: [
        ['colaborador_id', 'Colaborador', 'colaborador'],
        ['setor', 'Setor', 'text'], ['rota', 'Rota', 'text'],
        ['dias_texto', 'Dias do mês (ex: 1,8,15,22)', 'text', true]
      ]
    },
    ociosidade: {
      url: '/api/logistica/ociosidade',
      title: 'Ociosidade',
      columns: [
        ['data', 'Data'], ['placa', 'Placa'], ['horas', 'Horas'], ['motivo', 'Motivo'], ['valor', 'Valor']
      ],
      fields: [
        ['data', 'Data', 'date'], ['veiculo_id', 'Veículo', 'veiculo'],
        ['horas', 'Horas', 'number'], ['valor', 'Valor', 'number'],
        ['motivo', 'Motivo', 'text', true]
      ]
    },
    checklist: {
      url: '/api/logistica/checklists',
      title: 'Check-list',
      columns: [
        ['data', 'Data'], ['placa', 'Placa'], ['rota', 'Rota'], ['motorista', 'Motorista'],
        ['tipo', 'Tipo'], ['itens', 'Itens'], ['observacao', 'Observação']
      ],
      fields: [
        ['data', 'Data', 'date'], ['veiculo_id', 'Veículo', 'veiculo'],
        ['rota', 'Rota', 'text'], ['motorista', 'Motorista', 'text'],
        ['tipo', 'Tipo', 'select-cat'], ['itens', 'Itens conferidos', 'text', true],
        ['observacao', 'Observação', 'text', true]
      ]
    },
    higiene: {
      url: '/api/logistica/higiene',
      title: 'Higiene',
      columns: [
        ['data', 'Data'], ['placa', 'Placa'], ['tipo', 'Tipo'], ['responsavel', 'Responsável'],
        ['observacao', 'Observação']
      ],
      fields: [
        ['data', 'Data', 'date'], ['veiculo_id', 'Veículo', 'veiculo'],
        ['tipo', 'Tipo', 'text'], ['responsavel', 'Responsável', 'text'],
        ['observacao', 'Observação', 'text', true]
      ]
    },
    coletas: {
      url: '/api/logistica/coletas',
      title: 'Coleta / peso',
      columns: [
        ['data', 'Data'], ['cliente', 'Cliente'], ['rota', 'Rota'],
        ['peso_sujo', 'Peso sujo'], ['peso_limpo', 'Peso limpo'], ['diferenca', 'Diferença'],
        ['gaiolas', 'Gaiolas'], ['valor_kg', 'Valor/kg'], ['valor_recebido', 'Valor recebido']
      ],
      fields: [
        ['data', 'Data', 'date'], ['cliente', 'Cliente', 'text', true], ['rota', 'Rota', 'text'],
        ['peso_sujo', 'Peso sujo (kg)', 'number'], ['peso_limpo', 'Peso limpo (kg)', 'number'],
        ['gaiolas', 'Gaiolas', 'number'], ['valor_kg', 'Valor por kg', 'number'],
        ['observacao', 'Observação', 'text', true]
      ]
    }
  };

  var spec = specs[kind];
  if (!spec) return;

  function money(n) {
    return Number(n || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }
  function escapeHtml(str) {
    return String(str == null ? '' : str).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
    });
  }
  function val(row, key) {
    var moneyKeys = {
      valor: 1, valor_veiculo: 1, valor_kg: 1, valor_recebido: 1
    };
    if (moneyKeys[key]) return money(row[key]);
    if (key === 'ativo') return row[key] ? 'Sim' : 'Não';
    if (row[key] == null || row[key] === '') return '—';
    return row[key];
  }

  var thead = document.getElementById('theadRow');
  thead.innerHTML = spec.columns.map(function (c) {
    return '<th>' + c[1] + '</th>';
  }).join('') + '<th>Ações</th>';

  function listUrl() {
    if (kind === 'folgas' && cfg.mes) return spec.url + '?mes=' + encodeURIComponent(cfg.mes);
    return spec.url;
  }

  async function load() {
    var res = await fetch(listUrl());
    var data = await res.json();
    var rows = (data && data.rows) || [];
    var body = document.getElementById('tbodyCrud');
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="' + (spec.columns.length + 1) + '" style="text-align:center;padding:1.2rem;color:#64748b;">Nenhum registro.</td></tr>';
      return;
    }
    body.innerHTML = rows.map(function (row) {
      return '<tr>' + spec.columns.map(function (c) {
        return '<td>' + escapeHtml(val(row, c[0])) + '</td>';
      }).join('') +
        '<td><button class="btn btn-ghost btn-sm" type="button" data-edit=\'' + encodeURIComponent(JSON.stringify(row)) + '\'><i class="fas fa-edit"></i></button> ' +
        (row.id ? '<button class="btn btn-ghost btn-sm" type="button" data-del="' + row.id + '"><i class="fas fa-trash"></i></button>' : '') +
        '</td></tr>';
    }).join('');
  }

  function optionsVeiculo(selected) {
    return '<option value="">—</option>' + (cfg.veiculos || []).map(function (v) {
      var sel = String(v.id) === String(selected) ? ' selected' : '';
      return '<option value="' + v.id + '"' + sel + '>' + escapeHtml(v.placa + ' — ' + v.modelo) + '</option>';
    }).join('');
  }
  function optionsColab(selected) {
    return '<option value="">—</option>' + (cfg.colaboradores || []).map(function (c) {
      var sel = String(c.id) === String(selected) ? ' selected' : '';
      return '<option value="' + c.id + '"' + sel + '>' + escapeHtml(c.nome) + '</option>';
    }).join('');
  }
  function optionsCat(selected) {
    return (cfg.categorias || []).map(function (c) {
      var sel = c === selected ? ' selected' : '';
      return '<option value="' + escapeHtml(c) + '"' + sel + '>' + escapeHtml(c) + '</option>';
    }).join('');
  }
  function optionsExtra(selected) {
    return (cfg.extras || []).map(function (c) {
      var sel = c === selected ? ' selected' : '';
      return '<option value="' + escapeHtml(c) + '"' + sel + '>' + escapeHtml(c) + '</option>';
    }).join('');
  }
  function labelPonto(p) {
    var end = p.endereco ? ' — ' + p.endereco : '';
    return (p.nome || 'Ponto') + end;
  }
  function optionsPonto(selected) {
    return '<option value="">Selecione o ponto</option>' + (cfg.pontos || []).map(function (p) {
      var sel = String(p.id) === String(selected) ? ' selected' : '';
      return '<option value="' + p.id + '"' + sel + '>' + escapeHtml(labelPonto(p)) + '</option>';
    }).join('');
  }
  async function refreshPontos() {
    if (kind !== 'rotas') return;
    try {
      var res = await fetch('/api/logistica/entregas');
      var data = await res.json();
      cfg.pontos = (data && data.rows) || [];
    } catch (err) {
      cfg.pontos = cfg.pontos || [];
    }
  }
  function syncNomeRota() {
    if (kind !== 'rotas') return;
    var elNome = document.getElementById('f-nome');
    var o = document.getElementById('f-origem_ponto_id');
    var d = document.getElementById('f-destino_ponto_id');
    if (!elNome || !o || !d) return;
    if (elNome.dataset.manual === '1' && elNome.value.trim()) return;
    var oOpt = o.options[o.selectedIndex];
    var dOpt = d.options[d.selectedIndex];
    if (!o.value || !d.value || !oOpt || !dOpt) return;
    var oNome = (oOpt.text || '').split('—')[0].trim();
    var dNome = (dOpt.text || '').split('—')[0].trim();
    elNome.value = oNome + ' -> ' + dNome;
  }

  function fieldHtml(field, row) {
    var key = field[0], label = field[1], type = field[2], full = field[3];
    var value = row && row[key] != null ? row[key] : '';
    if (key === 'data' && !value) value = new Date().toISOString().slice(0, 10);
    var inner;
    if (type === 'veiculo') inner = '<select class="form-control" id="f-' + key + '">' + optionsVeiculo(value) + '</select>';
    else if (type === 'colaborador') inner = '<select class="form-control" id="f-' + key + '">' + optionsColab(value) + '</select>';
    else if (type === 'ponto') inner = '<select class="form-control" id="f-' + key + '">' + optionsPonto(value) + '</select>';
    else if (type === 'select-cat') inner = '<select class="form-control" id="f-' + key + '">' + optionsCat(value) + '</select>';
    else if (type === 'select-extra') inner = '<select class="form-control" id="f-' + key + '">' + optionsExtra(value) + '</select>';
    else inner = '<input class="form-control" id="f-' + key + '" type="' + type + '" value="' + escapeHtml(value) + '" step="any">';
    return '<div class="form-group' + (full ? ' full' : '') + '"><label class="form-label">' + label + '</label>' + inner + '</div>';
  }

  function readForm() {
    var out = {};
    spec.fields.forEach(function (field) {
      var el = document.getElementById('f-' + field[0]);
      if (!el) return;
      out[field[0]] = el.value;
    });
    if (cfg.mes && kind === 'folgas') out.mes = cfg.mes;
    var veiculoSel = document.getElementById('f-veiculo_id');
    if (veiculoSel && veiculoSel.selectedIndex >= 0) {
      var txt = veiculoSel.options[veiculoSel.selectedIndex].text || '';
      out.placa = txt.split('—')[0].trim();
    }
    return out;
  }

  function openForm(row) {
    row = row || {};
    if (kind === 'rotas' && !row.status) row.status = 'Pendente';
    if (kind === 'rotas' && !row.id && (cfg.pontos || []).length < 2) {
      showToast('Cadastre dois pontos no mapa de entregas antes de criar a rota.', 'error');
      return;
    }
    var html = '<div class="form-grid">' + spec.fields.map(function (f) { return fieldHtml(f, row); }).join('') + '</div>';
    if (kind === 'rotas') {
      html += '<p style="margin:0.4rem 0 0;font-size:0.82rem;color:#64748b;">A linha da rota aparece no mapa de entregas, seguindo as vias entre os dois pontos.</p>';
    }
    abrirModal((row.id ? 'Editar ' : 'Novo ') + spec.title, html, 'Gravar', async function () {
      var payload = readForm();
      var url = spec.url + (row.id ? '/' + row.id : '');
      var method = row.id ? 'PUT' : 'POST';
      var res = await fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      var data = await res.json();
      if (!data.ok) {
        showToast(data.error || 'Não foi possível gravar.', 'error');
        return;
      }
      fecharModal();
      showToast('Registro gravado.');
      load();
    });
    if (kind === 'rotas') {
      var elNome = document.getElementById('f-nome');
      var o = document.getElementById('f-origem_ponto_id');
      var d = document.getElementById('f-destino_ponto_id');
      if (elNome) {
        elNome.addEventListener('input', function () { elNome.dataset.manual = elNome.value.trim() ? '1' : '0'; });
        if (row.nome) elNome.dataset.manual = '1';
      }
      if (o) o.addEventListener('change', syncNomeRota);
      if (d) d.addEventListener('change', syncNomeRota);
      if (!row.nome) syncNomeRota();
    }
  }

  document.getElementById('btnNovo').addEventListener('click', async function () {
    await refreshPontos();
    openForm({});
  });
  document.getElementById('tbodyCrud').addEventListener('click', async function (ev) {
    var edit = ev.target.closest('[data-edit]');
    if (edit) {
      await refreshPontos();
      openForm(JSON.parse(decodeURIComponent(edit.getAttribute('data-edit'))));
      return;
    }
    var del = ev.target.closest('[data-del]');
    if (del) {
      if (!confirm('Excluir este registro?')) return;
      var res = await fetch(spec.url + '/' + del.getAttribute('data-del'), { method: 'DELETE' });
      var data = await res.json();
      if (!data.ok) {
        showToast(data.error || 'Não foi possível excluir.', 'error');
        return;
      }
      showToast('Registro excluído.');
      load();
    }
  });

  refreshPontos().then(load);
})();
