/* Formulários ligados ao Cadastro de Extras e Suplementos.
   A grade do mapa continua sendo a lista; Adicionar e Alterar abrem estas telas. */
var umaCache = { vias: null, produtos: null };
var umaForm = null;
var umaLoc = null;
var umaVia = null;
var umaMod = null;
var umaViaAlvo = 'via';

var UMA_TITULOS = {
  extras: 'Adicionar extra',
  suplementos: 'Adicionar Suplemento',
  enteral: 'Adicionar Enteral',
  formula: 'Adicionar Fórmula Infantil',
  lve: 'Adicionar LVE'
};

var UMA_NOME = {
  extras: { key: 'extra', label: 'Prato' },
  suplementos: { key: 'suplemento', label: 'Suplemento' },
  enteral: { key: 'dieta', label: 'Dieta' },
  formula: { key: 'formula', label: 'Fórmula Infantil' },
  lve: { key: 'lve', label: 'LVE' }
};

function umaEsc(s){
  return (typeof esc === 'function') ? esc(s) : String(s == null ? '' : s);
}

function umaNum(v){
  const s = String(v == null ? '' : v).trim();
  if (!s || s === '0' || s === '0,0' || s === '0,00' || s === '0.0' || s === '0.00') return '';
  return s;
}

function umaClonar(row){
  const copia = Object.assign({}, row || {});
  copia.modulos = (row && row.modulos || []).map(function(m){
    return { descricao: m.descricao || m.modulo || '', volume: m.volume || '' };
  });
  return copia;
}

function umaHorasHtml(prefix, row){
  let html = '<div class="uma-horas">';
  for (let c = 0; c < 8; c++){
    html += '<div class="uma-hora-col">';
    for (let r = 0; r < 3; r++){
      const h = r + 1 + c * 3;
      const key = prefix + h;
      html += '<label><input type="checkbox" data-hora="' + key + '"' + (row[key] ? ' checked' : '') + '> ' + h + '</label>';
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function umaViaSelect(key, valor){
  const vias = umaCache.vias || [];
  const opts = ['<option value="">Selecione</option>'].concat(vias.map(function(v){
    const sel = String(v.nome) === String(valor || '') ? ' selected' : '';
    return '<option value="' + umaEsc(v.nome) + '"' + sel + '>' + umaEsc(v.nome) + '</option>';
  }));
  return '<div class="uma-via-linha"><select class="form-control" data-k="' + key + '">' + opts.join('') + '</select>' +
    '<button type="button" class="btn btn-ghost btn-sm" data-uma-via="' + key + '" title="Cadastro de Via de Administração (F3)">...</button></div>';
}

function umaCampoNome(abaId, row){
  const meta = UMA_NOME[abaId];
  return '<div class="form-group uma-nome">' +
    '<label class="form-label">' + meta.label + ':</label>' +
    '<div class="uma-nome-linha">' +
      '<input class="form-control" data-k="' + meta.key + '" value="' + umaEsc(row[meta.key] || '') + '">' +
      '<button type="button" class="btn btn-ghost btn-sm" id="umaBtnBusca" title="Localizar (F2)"><i class="fas fa-search"></i></button>' +
      '<span class="uma-atalho">F2</span>' +
    '</div></div>';
}

function umaLocalHtml(row, travado){
  const dis = travado ? ' readonly' : '';
  return '<div class="uma-local">' +
    '<div class="form-group"><label class="form-label">Enfermaria:</label>' +
      '<input class="form-control" data-k="enfermaria" value="' + umaEsc(row.enfermaria || '') + '"' + dis + '></div>' +
    '<div class="form-group"><label class="form-label">Leito:</label>' +
      '<input class="form-control" data-k="leito" value="' + umaEsc(row.leito || '') + '"' + dis + '></div>' +
    '<button type="button" class="btn btn-ghost btn-sm" id="umaDesbloquear"><i class="fas fa-lock"></i> Desbloquear</button>' +
  '</div>';
}

function umaModulosHtml(mods){
  const linhas = (mods || []).map(function(m, i){
    return '<tr data-i="' + i + '"><td>' + umaEsc(m.descricao) + '</td><td>' + umaEsc(m.volume) + '</td></tr>';
  }).join('');
  return '<fieldset class="uma-box"><legend>Módulos</legend>' +
    '<table class="uma-mod-grid"><thead><tr><th>Descrição</th><th>Volume p/ etapa</th></tr></thead>' +
    '<tbody id="umaModBody">' + (linhas || '<tr class="uma-mod-vazio"><td colspan="2">Nenhum módulo</td></tr>') + '</tbody></table>' +
    '<div class="uma-mod-acoes">' +
      '<button type="button" class="btn btn-ghost btn-sm" id="umaModAdd"><i class="fas fa-plus"></i> Adicionar</button>' +
      '<button type="button" class="btn btn-ghost btn-sm" id="umaModDel"><i class="fas fa-minus"></i> Remover</button>' +
      '<button type="button" class="btn btn-ghost btn-sm" id="umaModEdit"><i class="fas fa-pen"></i> Editar</button>' +
    '</div></fieldset>';
}

function umaMontarForm(){
  const abaId = umaForm.abaId;
  const row = umaForm.draft;
  const nome = umaCampoNome(abaId, row);
  let miolo = '';
  if (abaId === 'enteral' || abaId === 'formula'){
    miolo = '<div class="uma-vols">' +
      '<div class="form-group"><label class="form-label">Vol. dieta:</label><input class="form-control" data-k="vol_dieta" value="' + umaEsc(row.vol_dieta || row.volume || '0,00') + '"></div>' +
      '<div class="form-group"><label class="form-label">Vol. água:</label><input class="form-control" data-k="vol_agua" value="' + umaEsc(row.vol_agua || '0,00') + '"></div>' +
    '</div>' +
    '<fieldset class="uma-box"><legend>Horários dieta</legend>' + umaHorasHtml('h', row) + '</fieldset>' +
    '<fieldset class="uma-box"><legend>Horários água</legend>' + umaHorasHtml('a', row) + '</fieldset>' +
    '<div class="uma-vias">' +
      '<div class="form-group"><label class="form-label">Via dieta: <span class="uma-atalho">F3</span></label>' + umaViaSelect('via_dieta', row.via_dieta || row.via) + '</div>' +
      '<div class="form-group"><label class="form-label">Quant. Via:</label><input class="form-control" data-k="quant_via_dieta" value="' + umaEsc(row.quant_via_dieta || '0') + '"></div>' +
      '<div class="form-group"><label class="form-label">Via água:</label>' + umaViaSelect('via_agua', row.via_agua) + '</div>' +
      '<div class="form-group"><label class="form-label">Quant. Via:</label><input class="form-control" data-k="quant_via_agua" value="' + umaEsc(row.quant_via_agua || '0') + '"></div>' +
    '</div>';
    if (abaId === 'enteral'){
      const tipo = row.tipo_admin || '';
      miolo += '<fieldset class="uma-box"><legend>Tipo de administração</legend><div class="uma-tipos">' +
        ['oral','bolos','continuo','intermitente'].map(function(v, i){
          const rot = ['Via Oral','Em bolos','Contínuo','Intermitente'][i];
          return '<label><input type="radio" name="umaTipo" value="' + v + '"' + (tipo === v ? ' checked' : '') + '> ' + rot + '</label>';
        }).join('') +
      '</div></fieldset>' +
      '<div class="uma-vols">' +
        '<div class="form-group"><label class="form-label">Gotejamento:</label><div class="uma-nome-linha"><input class="form-control" data-k="gotejamento" value="' + umaEsc(row.gotejamento || '0,00') + '"><span>h</span></div></div>' +
        '<div class="form-group"><label class="form-label">Horários de envio:</label><input class="form-control" data-k="horarios_envio" value="' + umaEsc(row.horarios_envio || '') + '"></div>' +
      '</div>';
    }
    miolo += '<input type="hidden" data-k="sistema" value="' + umaEsc(row.sistema || '') + '">';
    miolo += umaModulosHtml(row.modulos);
  } else {
    miolo = '<div class="form-group uma-vol-um"><label class="form-label">Volume p/ etapa:</label>' +
      '<input class="form-control" data-k="volume" value="' + umaEsc(row.volume || '0,00') + '"></div>' +
      '<fieldset class="uma-box"><legend>Horários</legend>' + umaHorasHtml('h', row) + '</fieldset>' +
      '<div class="uma-vias">' +
        '<div class="form-group"><label class="form-label">Via: <span class="uma-atalho">F3</span></label>' + umaViaSelect('via', row.via) + '</div>' +
        '<div class="form-group"><label class="form-label">Quant. Via:</label><input class="form-control" data-k="quant_via" value="' + umaEsc(row.quant_via || '0') + '"></div>' +
      '</div>';
  }
  document.getElementById('umaFormTitulo').textContent = UMA_TITULOS[abaId] || 'Adicionar';
  document.getElementById('umaFormBody').innerHTML = nome + miolo + umaLocalHtml(row, !umaForm.liberado);
  umaMarcarMods();
}

async function umaCarregarVias(force){
  if (umaCache.vias && !force) return umaCache.vias;
  const r = await fetch('/nutricao/api/vias?ativos=1');
  const j = await r.json();
  umaCache.vias = Array.isArray(j) ? j : [];
  return umaCache.vias;
}

function umaAbrirForm(row){
  if (typeof xcadState === 'undefined' || !xcadState) return;
  const aba = xcadAba(xcadState.aba);
  umaForm = {
    abaId: aba.id,
    idx: row ? xcadState.sel : -1,
    draft: row ? umaClonar(row) : xcadLinhaVazia(aba, xcadState.linha),
    liberado: false,
    modSel: -1
  };
  if (!Array.isArray(umaForm.draft.modulos)) umaForm.draft.modulos = [];
  umaCarregarVias(false).then(function(){
    umaMontarForm();
    const ov = document.getElementById('umaFormOverlay');
    if (ov) ov.hidden = false;
    const inp = document.querySelector('#umaFormBody input[data-k="' + UMA_NOME[aba.id].key + '"]');
    if (inp) inp.focus();
  }).catch(function(){
    showToast('Não foi possível carregar as vias', 'error');
  });
}

function umaFecharForm(){
  const ov = document.getElementById('umaFormOverlay');
  if (ov) ov.hidden = true;
  umaForm = null;
}

function umaLerForm(){
  const body = document.getElementById('umaFormBody');
  const draft = umaForm.draft;
  body.querySelectorAll('[data-k]').forEach(function(el){
    draft[el.dataset.k] = el.value;
  });
  body.querySelectorAll('input[data-hora]').forEach(function(el){
    draft[el.dataset.hora] = el.checked;
  });
  const tipo = body.querySelector('input[name="umaTipo"]:checked');
  draft.tipo_admin = tipo ? tipo.value : (draft.tipo_admin || '');
  draft.volume = umaNum(draft.volume);
  draft.vol_dieta = umaNum(draft.vol_dieta);
  draft.vol_agua = umaNum(draft.vol_agua);
  draft.gotejamento = umaNum(draft.gotejamento);
  if ((umaForm.abaId === 'enteral' || umaForm.abaId === 'formula') && draft.vol_dieta){
    draft.volume = draft.vol_dieta;
    if (!draft.unid) draft.unid = 'ML';
    if (!draft.unidade) draft.unidade = 'ML';
  }
  if (draft.via_dieta) draft.via = draft.via_dieta;
}

function umaConfirmarForm(){
  if (!umaForm || !xcadState) return;
  umaLerForm();
  const meta = UMA_NOME[umaForm.abaId];
  if (!String(umaForm.draft[meta.key] || '').trim()){
    showToast('Informe ' + meta.label.toLowerCase(), 'error');
    return;
  }
  const lista = xcadState.dados[umaForm.abaId];
  if (umaForm.idx >= 0 && lista[umaForm.idx]) lista[umaForm.idx] = umaForm.draft;
  else {
    lista.push(umaForm.draft);
    xcadState.sel = lista.length - 1;
  }
  xcadState.dirty = true;
  xcadRender();
  umaFecharForm();
}

function umaDesbloquear(){
  if (!umaForm) return;
  umaLerForm();
  umaForm.liberado = true;
  umaMontarForm();
}

function umaLocConfig(){
  const aba = umaForm.abaId;
  if (aba === 'extras'){
    return { titulo: 'Localizar Prato', dica: 'Digite o prato a localizar:', tipo: 'prato', simples: true };
  }
  if (aba === 'suplementos'){
    return { titulo: 'Localizar Suplemento', dica: 'Digite o texto a localizar:', tipo: 'suplemento', quant: true, manipulado: false };
  }
  if (aba === 'lve'){
    return { titulo: 'Localizar LVE', dica: 'Digite o texto a localizar:', tipo: 'lve', simples: true };
  }
  if (aba === 'formula'){
    return { titulo: 'Localizar Dieta', dica: 'Localizar Dieta:', tipo: 'formula', simples: true };
  }
  return {
    titulo: 'Localizar Dietas e Suplementos',
    dica: 'Digite o texto a localizar:',
    tipo: 'enteral',
    papel: 'dieta',
    sistema: 'aberto',
    enteral: true
  };
}

function umaAbrirLocDoForm(){
  if (!umaForm) return;
  umaLoc = umaLocConfig();
  umaLoc.sel = -1;
  umaLoc.itens = [];
  document.getElementById('umaLocTitulo').textContent = umaLoc.titulo;
  const dica = document.getElementById('umaLocDica');
  if (dica) dica.textContent = umaLoc.dica || 'Digite o texto a localizar:';
  const filtros = [];
  if (umaLoc.quant || umaLoc.manipulado === false){
    filtros.push('<div class="uma-radios"><span>Tipo</span>' +
      '<label><input type="radio" name="umaMan" value="0" checked> Suplementos</label>' +
      '<label><input type="radio" name="umaMan" value="1"> Suplementos manipulados</label></div>');
  }
  if (umaLoc.enteral){
    filtros.push('<div class="uma-radios"><span>Tipo</span>' +
      '<label><input type="radio" name="umaPapel" value="dieta" checked> Dietas</label>' +
      '<label><input type="radio" name="umaPapel" value="suplemento"> Suplementos</label></div>' +
      '<div class="uma-radios"><span>Tipo</span>' +
      '<label><input type="radio" name="umaSis" value="aberto" checked> Sistema aberto</label>' +
      '<label><input type="radio" name="umaSis" value="fechado"> Sistema fechado</label></div>');
  }
  document.getElementById('umaLocFiltros').innerHTML = filtros.join('');
  const meta = UMA_NOME[umaForm.abaId];
  document.getElementById('umaLocBusca').value = (umaForm.draft && meta) ? (umaForm.draft[meta.key] || '') : '';
  document.getElementById('umaLocOverlay').hidden = false;
  document.getElementById('umaLocBusca').focus();
  umaBuscarLoc();
}

function umaFecharLoc(){
  const ov = document.getElementById('umaLocOverlay');
  if (ov) ov.hidden = true;
  umaLoc = null;
}

function umaQueryLoc(){
  if (!umaLoc) return '';
  if (umaLoc.modo === 'produto') return '';
  const papelEl = document.querySelector('#umaLocFiltros input[name="umaPapel"]:checked');
  const sisEl = document.querySelector('#umaLocFiltros input[name="umaSis"]:checked');
  const manEl = document.querySelector('#umaLocFiltros input[name="umaMan"]:checked');
  if (umaLoc.enteral && papelEl && papelEl.value === 'suplemento'){
    umaLoc.tipo = 'suplemento';
    umaLoc.papel = '';
    umaLoc.sistema = '';
  } else if (umaLoc.enteral){
    umaLoc.tipo = 'enteral';
    umaLoc.papel = 'dieta';
    umaLoc.sistema = sisEl ? sisEl.value : 'aberto';
  }
  if (manEl) umaLoc.manipulado = manEl.value === '1';
  const q = new URLSearchParams();
  q.set('tipo', umaLoc.tipo);
  q.set('ativos', '1');
  if (umaLoc.sistema) q.set('sistema', umaLoc.sistema);
  if (umaLoc.papel) q.set('papel', umaLoc.papel);
  if (umaLoc.manipulado === true) q.set('manipulado', '1');
  if (umaLoc.manipulado === false && umaLoc.tipo === 'suplemento') q.set('manipulado', '0');
  q.set('disponivel', '1');
  return '/nutricao/api/uma-itens?' + q.toString();
}

async function umaBuscarLoc(){
  if (!umaLoc) return;
  const corpo = document.getElementById('umaLocLista');
  if (umaLoc.modo === 'produto'){
    if (!umaCache.produtos){
      const r = await fetch('/nutricao/api/produtos');
      const j = await r.json();
      umaCache.produtos = Array.isArray(j) ? j : [];
    }
    umaLoc.itens = umaCache.produtos.map(function(p){
      return { nome: p.descricao || p.codigo || '', quantidade: p.quantidade || 0 };
    });
  } else {
    const r = await fetch(umaQueryLoc());
    const j = await r.json();
    umaLoc.itens = Array.isArray(j) ? j : [];
  }
  umaFiltrarLoc();
  if (corpo) corpo.scrollTop = 0;
}

function umaFiltrarLoc(){
  if (!umaLoc) return;
  const q = (document.getElementById('umaLocBusca')?.value || '').trim().toUpperCase();
  const itens = (umaLoc.itens || []).filter(function(it){
    return !q || String(it.nome || '').toUpperCase().indexOf(q) >= 0;
  });
  umaLoc.visiveis = itens;
  if (umaLoc.sel >= itens.length) umaLoc.sel = itens.length ? 0 : -1;
  const quant = umaLoc.quant || umaLoc.modo === 'produto';
  const head = quant ? '<div class="uma-loc-head"><span>Descrição</span><span>Quant. Disp.</span></div>' : '';
  const linhas = itens.map(function(it, i){
    const qtd = (it.quantidade == null ? 0 : it.quantidade);
    const extra = quant ? '<span class="uma-qtd">' + umaEsc(qtd) + '</span>' : '';
    return '<button type="button" class="uma-loc-item' + (i === umaLoc.sel ? ' is-sel' : '') + '" data-i="' + i + '"><span>' + umaEsc(it.nome) + '</span>' + extra + '</button>';
  }).join('');
  document.getElementById('umaLocLista').innerHTML = head + (linhas || '<p class="uma-loc-vazio">Nenhum item cadastrado com este filtro.</p>');
  const btn = document.getElementById('umaLocCadastrar');
  if (btn){
    const existe = q && (umaLoc.itens || []).some(function(it){ return String(it.nome || '').toUpperCase() === q; });
    btn.hidden = umaLoc.modo === 'produto' || !q || existe;
  }
}

function umaEscolherLoc(){
  if (!umaLoc || umaLoc.sel < 0) return;
  const item = (umaLoc.visiveis || [])[umaLoc.sel];
  if (!item) return;
  if (umaLoc.modo === 'produto'){
    const inp = document.getElementById('umaViaProduto');
    if (inp) inp.value = item.nome || '';
    umaFecharLoc();
    return;
  }
  if (!umaForm) { umaFecharLoc(); return; }
  const meta = UMA_NOME[umaForm.abaId];
  umaForm.draft[meta.key] = item.nome || '';
  umaForm.draft.uma_item_id = item.id || '';
  if (item.sistema) umaForm.draft.sistema = item.sistema;
  if (item.unidade){
    umaForm.draft.unid = item.unidade;
    umaForm.draft.unidade = item.unidade;
  }
  if (item.diluicao) umaForm.draft.diluicao = item.diluicao;
  if (item.quant_padrao && (umaForm.abaId === 'suplementos' || !umaForm.draft.volume)){
    umaForm.draft.volume = String(item.quant_padrao);
  }
  if (item.coluna_faturamento) umaForm.draft.coluna_faturamento = item.coluna_faturamento;
  umaFecharLoc();
  umaMontarForm();
}

async function umaCadastrarLoc(){
  if (!umaLoc || umaLoc.modo === 'produto') return;
  const nome = (document.getElementById('umaLocBusca')?.value || '').trim();
  if (!nome){ showToast('Digite o nome para cadastrar', 'error'); return; }
  const papelEl = document.querySelector('#umaLocFiltros input[name="umaPapel"]:checked');
  const sisEl = document.querySelector('#umaLocFiltros input[name="umaSis"]:checked');
  const manEl = document.querySelector('#umaLocFiltros input[name="umaMan"]:checked');
  let tipo = umaLoc.tipo;
  let papel = umaLoc.papel || '';
  let sistema = umaLoc.sistema || '';
  let manipulado = !!umaLoc.manipulado;
  if (umaLoc.enteral && papelEl && papelEl.value === 'suplemento'){
    tipo = 'suplemento'; papel = ''; sistema = '';
  } else if (umaLoc.enteral){
    tipo = 'enteral'; papel = 'dieta'; sistema = sisEl ? sisEl.value : 'aberto';
  }
  if (manEl) manipulado = manEl.value === '1';
  const r = await fetch('/nutricao/api/uma-itens', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ tipo: tipo, nome: nome, papel: papel, sistema: sistema, manipulado: manipulado })
  });
  const j = await r.json();
  if (!r.ok || j.ok === false){ showToast((j && j.error) || 'Falha ao cadastrar', 'error'); return; }
  showToast('Item cadastrado', 'success');
  umaLoc.sel = 0;
  await umaBuscarLoc();
  const idx = (umaLoc.visiveis || []).findIndex(function(it){
    return String(it.nome || '').toUpperCase() === nome.toUpperCase();
  });
  if (idx >= 0) umaLoc.sel = idx;
  umaEscolherLoc();
}

function umaAbrirVia(alvo){
  umaViaAlvo = alvo || umaViaAlvo || 'via';
  umaVia = { itens: [], idx: 0, novo: false };
  document.getElementById('umaViaOverlay').hidden = false;
  umaRecarregarVias();
}

function umaFecharVia(){
  const ov = document.getElementById('umaViaOverlay');
  if (ov) ov.hidden = true;
  umaCarregarVias(true).then(function(){
    if (umaForm){
      umaLerForm();
      umaMontarForm();
    }
  });
}

async function umaRecarregarVias(){
  const r = await fetch('/nutricao/api/vias?ativos=0');
  const j = await r.json();
  umaVia.itens = (Array.isArray(j) ? j : []).filter(function(v){ return v.ativo !== false; });
  if (umaVia.idx >= umaVia.itens.length) umaVia.idx = Math.max(0, umaVia.itens.length - 1);
  umaPintarVia();
}

function umaPintarVia(){
  const item = umaVia && umaVia.itens[umaVia.idx];
  const nome = document.getElementById('umaViaNome');
  const prod = document.getElementById('umaViaProduto');
  const oral = document.getElementById('umaViaOral');
  if (!nome) return;
  if (umaVia.novo || !item){
    if (!umaVia.novo){
      nome.value = '';
      prod.value = '';
      oral.checked = false;
    }
    return;
  }
  nome.value = item.nome || '';
  prod.value = item.produto || '';
  oral.checked = !!item.via_oral;
}

function umaViaNav(dir){
  if (!umaVia || !umaVia.itens.length) return;
  umaVia.novo = false;
  if (dir === 'first') umaVia.idx = 0;
  else if (dir === 'prev') umaVia.idx = Math.max(0, umaVia.idx - 1);
  else if (dir === 'next') umaVia.idx = Math.min(umaVia.itens.length - 1, umaVia.idx + 1);
  else if (dir === 'last') umaVia.idx = umaVia.itens.length - 1;
  umaPintarVia();
}

function umaViaNova(){
  if (!umaVia) umaVia = { itens: [], idx: 0, novo: true };
  umaVia.novo = true;
  document.getElementById('umaViaNome').value = '';
  document.getElementById('umaViaProduto').value = '';
  document.getElementById('umaViaOral').checked = false;
  document.getElementById('umaViaNome').focus();
}

async function umaViaSalvar(){
  const nome = (document.getElementById('umaViaNome')?.value || '').trim();
  if (!nome){ showToast('Informe o nome da embalagem', 'error'); return; }
  const body = {
    nome: nome,
    produto: (document.getElementById('umaViaProduto')?.value || '').trim(),
    via_oral: !!document.getElementById('umaViaOral')?.checked,
    ativo: true
  };
  const atual = !umaVia.novo && umaVia.itens[umaVia.idx];
  const r = await fetch(atual ? '/nutricao/api/vias/' + atual.id : '/nutricao/api/vias', {
    method: atual ? 'PUT' : 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  const j = await r.json();
  if (!r.ok || j.ok === false){ showToast((j && j.error) || 'Falha ao salvar a via', 'error'); return; }
  showToast('Via salva', 'success');
  umaVia.novo = false;
  umaCache.vias = null;
  await umaRecarregarVias();
  const idx = umaVia.itens.findIndex(function(v){ return String(v.nome).toUpperCase() === nome.toUpperCase(); });
  if (idx >= 0) umaVia.idx = idx;
  umaPintarVia();
  if (umaForm && umaForm.draft) umaForm.draft[umaViaAlvo] = nome.toUpperCase();
}

async function umaViaExcluir(){
  const atual = umaVia && !umaVia.novo && umaVia.itens[umaVia.idx];
  if (!atual){ showToast('Selecione uma via', 'error'); return; }
  if (!window.confirm('Desativar esta via?')) return;
  const r = await fetch('/nutricao/api/vias/' + atual.id, { method: 'DELETE' });
  const j = await r.json();
  if (!r.ok || j.ok === false){ showToast((j && j.error) || 'Falha ao desativar', 'error'); return; }
  umaCache.vias = null;
  await umaRecarregarVias();
}

function umaAbrirProduto(){
  umaLoc = { modo: 'produto', titulo: 'Localizar produto', sel: -1, itens: [], quant: true };
  document.getElementById('umaLocTitulo').textContent = 'Localizar produto';
  const dicaProd = document.getElementById('umaLocDica');
  if (dicaProd) dicaProd.textContent = 'Digite o produto a localizar:';
  document.getElementById('umaLocFiltros').innerHTML = '';
  document.getElementById('umaLocBusca').value = '';
  document.getElementById('umaLocOverlay').hidden = false;
  umaBuscarLoc();
}

function umaAbrirMod(editar){
  if (!umaForm) return;
  umaMod = { edit: editar ? umaForm.modSel : -1 };
  const atual = editar && umaForm.draft.modulos[umaForm.modSel];
  document.getElementById('umaModVolume').value = atual ? (atual.volume || '0,00') : '0,00';
  document.getElementById('umaModOverlay').hidden = false;
  umaEncherModulos(atual ? atual.descricao : '');
}

async function umaEncherModulos(valor){
  const r = await fetch('/nutricao/api/uma-itens?tipo=modulo&ativos=1');
  const j = await r.json();
  const sel = document.getElementById('umaModNome');
  const itens = Array.isArray(j) ? j : [];
  sel.innerHTML = '<option value=""></option>' + itens.map(function(it){
    const on = String(it.nome) === String(valor || '') ? ' selected' : '';
    return '<option value="' + umaEsc(it.nome) + '"' + on + '>' + umaEsc(it.nome) + '</option>';
  }).join('');
  if (valor && !itens.some(function(it){ return it.nome === valor; })){
    sel.insertAdjacentHTML('beforeend', '<option value="' + umaEsc(valor) + '" selected>' + umaEsc(valor) + '</option>');
  }
}

function umaFecharMod(){
  const ov = document.getElementById('umaModOverlay');
  if (ov) ov.hidden = true;
  umaMod = null;
}

function umaConfirmarMod(){
  if (!umaForm || !umaMod) return;
  const nome = (document.getElementById('umaModNome')?.value || '').trim();
  if (!nome){ showToast('Informe o módulo', 'error'); return; }
  const volume = umaNum(document.getElementById('umaModVolume')?.value || '');
  const mod = { descricao: nome, volume: volume };
  if (umaMod.edit >= 0 && umaForm.draft.modulos[umaMod.edit]) umaForm.draft.modulos[umaMod.edit] = mod;
  else umaForm.draft.modulos.push(mod);
  umaForm.modSel = umaMod.edit >= 0 ? umaMod.edit : umaForm.draft.modulos.length - 1;
  umaFecharMod();
  umaLerForm();
  umaMontarForm();
}

function umaMarcarMods(){
  document.querySelectorAll('#umaModBody tr[data-i]').forEach(function(tr){
    tr.classList.toggle('is-sel', Number(tr.dataset.i) === umaForm.modSel);
  });
}

function umaTratarEscape(){
  if (!document.getElementById('umaModOverlay')?.hidden){ umaFecharMod(); return true; }
  if (!document.getElementById('umaLocOverlay')?.hidden){ umaFecharLoc(); return true; }
  if (!document.getElementById('umaViaOverlay')?.hidden){ umaFecharVia(); return true; }
  if (!document.getElementById('umaFormOverlay')?.hidden){ umaFecharForm(); return true; }
  return false;
}

function umaAtalho(key){
  if (!document.getElementById('umaFormOverlay') || document.getElementById('umaFormOverlay').hidden) return false;
  if (!document.getElementById('umaLocOverlay')?.hidden) return false;
  if (!document.getElementById('umaViaOverlay')?.hidden) return false;
  if (!document.getElementById('umaModOverlay')?.hidden) return false;
  if (key === 'F2'){ umaAbrirLocDoForm(); return true; }
  if (key === 'F3'){ umaAbrirVia(umaViaAlvo); return true; }
  return false;
}

document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('umaFormBody')?.addEventListener('input', function(e){
    if (!umaForm || !e.target) return;
    const meta = UMA_NOME[umaForm.abaId];
    if (meta && e.target.dataset && e.target.dataset.k === meta.key) umaForm.draft.uma_item_id = '';
  });

  document.getElementById('umaFormBody')?.addEventListener('click', function(e){
    const busca = e.target.closest('#umaBtnBusca');
    if (busca){ umaLerForm(); umaAbrirLocDoForm(); return; }
    const via = e.target.closest('[data-uma-via]');
    if (via){ umaViaAlvo = via.dataset.umaVia; umaLerForm(); umaAbrirVia(umaViaAlvo); return; }
    if (e.target.closest('#umaDesbloquear')) umaDesbloquear();
    if (e.target.closest('#umaModAdd')) umaAbrirMod(false);
    if (e.target.closest('#umaModDel')){
      if (!umaForm || umaForm.modSel < 0) return;
      umaForm.draft.modulos.splice(umaForm.modSel, 1);
      umaForm.modSel = Math.min(umaForm.modSel, umaForm.draft.modulos.length - 1);
      umaLerForm();
      umaMontarForm();
    }
    if (e.target.closest('#umaModEdit')){
      if (!umaForm || umaForm.modSel < 0){ showToast('Selecione um módulo', 'error'); return; }
      umaAbrirMod(true);
    }
    const tr = e.target.closest('#umaModBody tr[data-i]');
    if (tr && umaForm){ umaForm.modSel = Number(tr.dataset.i); umaMarcarMods(); }
  });

  document.getElementById('umaLocLista')?.addEventListener('click', function(e){
    const btn = e.target.closest('.uma-loc-item');
    if (!btn || !umaLoc) return;
    umaLoc.sel = Number(btn.dataset.i);
    umaFiltrarLoc();
  });
  document.getElementById('umaLocLista')?.addEventListener('dblclick', function(e){
    const btn = e.target.closest('.uma-loc-item');
    if (!btn || !umaLoc) return;
    umaLoc.sel = Number(btn.dataset.i);
    umaEscolherLoc();
  });
  document.getElementById('umaLocBusca')?.addEventListener('input', umaFiltrarLoc);
  document.getElementById('umaLocFiltros')?.addEventListener('change', umaBuscarLoc);

  document.getElementById('xcadTabela')?.addEventListener('dblclick', function(e){
    const tr = e.target.closest('tr[data-idx]');
    if (!tr || !xcadState) return;
    const idx = Number(tr.dataset.idx);
    xcadSelecionar(idx);
    const aba = xcadAba(xcadState.aba);
    umaAbrirForm(xcadState.dados[aba.id][idx]);
  });
});
