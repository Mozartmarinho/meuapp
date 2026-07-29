from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from datetime import datetime, date
import json

nutricao = Blueprint('nutricao', __name__, template_folder='templates_nutricao')

# ---- DADOS MOCKADOS ----
PACIENTES = [
    {'id':1,'nome':'Maria Silva','sexo':'F','nascimento':'1985-03-15','prontuario':'12345','clinica':'Clínica Médica','leito':'101-A','dieta':'Branda','altura_cm':165,'peso_kg':72,'ativo':True},
    {'id':2,'nome':'João Santos','sexo':'M','nascimento':'1972-08-22','prontuario':'12346','clinica':'CTI','leito':'05','dieta':'Hiperproteica','altura_cm':175,'peso_kg':80,'ativo':True},
    {'id':3,'nome':'Ana Oliveira','sexo':'F','nascimento':'1990-12-01','prontuario':'12347','clinica':'Oncologia','leito':'210-B','dieta':'Líquida','altura_cm':160,'peso_kg':58,'ativo':True},
    {'id':4,'nome':'Carlos Pereira','sexo':'M','nascimento':'1965-06-10','prontuario':'12348','clinica':'Clínica Médica','leito':'102','dieta':'Branda','altura_cm':170,'peso_kg':85,'ativo':True},
    {'id':5,'nome':'Lucia Mendes','sexo':'F','nascimento':'1995-09-28','prontuario':'12349','clinica':'Maternidade','leito':'305','dieta':'Líquida','altura_cm':162,'peso_kg':65,'ativo':True},
]
CLINICAS = [
    {'id':1,'nome':'Clínica Médica','centro_custo':'CC-1001'},
    {'id':2,'nome':'CTI','centro_custo':'CC-1002'},
    {'id':3,'nome':'Oncologia','centro_custo':'CC-1003'},
    {'id':4,'nome':'Maternidade','centro_custo':'CC-1004'},
    {'id':5,'nome':'Pediatria','centro_custo':'CC-1005'},
    {'id':6,'nome':'Centro Cirúrgico','centro_custo':'CC-1006'}
]
ENFERMARIAS = [
    {'id':1,'clinica_id':1,'nome':'Enfermaria A','numero_leito':'1','nutriz':True,'ativo':True},
    {'id':2,'clinica_id':2,'nome':'Enfermaria CTI 1','numero_leito':'2','nutriz':False,'ativo':True},
    {'id':3,'clinica_id':3,'nome':'Enfermaria Onco','numero_leito':'3','nutriz':True,'ativo':True}
]
LEITOS = [
    {'id':1,'enfermaria_id':1,'numero_leito':'101-A','nome_leito':'Leito Janela','ativo':True},
    {'id':2,'enfermaria_id':1,'numero_leito':'101-B','nome_leito':'Leito Porta','ativo':True},
    {'id':3,'enfermaria_id':2,'numero_leito':'CTI-05','nome_leito':'Leito Monitorado','ativo':True},
    {'id':4,'enfermaria_id':3,'numero_leito':'ONC-210','nome_leito':'Leito Isolado','ativo':False}
]
DIETAS = [{'id':1,'nome':'BRANDA'},{'id':2,'nome':'BRANDA CONSTIPANTE'},{'id':3,'nome':'HIPERPROTEICA'},{'id':4,'nome':'LÍQUIDA'},{'id':5,'nome':'PASTOSA'},{'id':6,'nome':'HIPOSSÓDICA'},{'id':7,'nome':'DIABÉTICA'},{'id':8,'nome':'JEJUM'}]
FUNCIONARIOS = [
    {'id':1,'nome':'Dr. Ricardo Almeida','cargo':'Médico','setor':'Clínica Médica','telefone':'(11)99999-0001','email':'ricardo@h.com','situacao':'ativo'},
    {'id':2,'nome':'Enf. Patricia Lima','cargo':'Enfermeira','setor':'CTI','telefone':'(11)99999-0002','email':'patricia@h.com','situacao':'ativo'},
    {'id':3,'nome':'Nut. Carla Souza','cargo':'Nutricionista','setor':'Nutrição','telefone':'(11)99999-0003','email':'carla@h.com','situacao':'ativo'},
    {'id':4,'nome':'Aux. João Costa','cargo':'Auxiliar','setor':'Oncologia','telefone':'(11)99999-0004','email':'joao@h.com','situacao':'ativo'},
    {'id':5,'nome':'Téc. Maria Fernanda','cargo':'Técnico','setor':'Pediatria','telefone':'(11)99999-0005','email':'mariaf@h.com','situacao':'inativo'},
]
FORNECEDORES = [{'id':1,'nome':'Distribuidora Alimentos Ltda','cnpj':'11.222.333/0001-44','contato':'Carlos','telefone':'(11)3333-0001','email':'carlos@dist.com'},{'id':2,'nome':'NutriSupply S.A.','cnpj':'55.666.777/0001-88','contato':'Ana','telefone':'(11)3333-0002','email':'ana@nutri.com'},{'id':3,'nome':'HospMedic','cnpj':'99.888.777/0001-55','contato':'José','telefone':'(11)3333-0003','email':'jose@hosp.com'}]
PRODUTOS = [{'id':1,'nome':'Arroz 5kg','categoria':'Alimentação','unidade':'Saco','estoque_min':10,'estoque_atual':45,'fornecedor_id':1,'valor_un':'R$22,50'},{'id':2,'nome':'Feijão Preto 1kg','categoria':'Alimentação','unidade':'Pacote','estoque_min':20,'estoque_atual':38,'fornecedor_id':1,'valor_un':'R$8,90'},{'id':3,'nome':'Suplemento Proteico 500g','categoria':'Suplemento','unidade':'Lata','estoque_min':5,'estoque_atual':12,'fornecedor_id':2,'valor_un':'R$89,00'},{'id':4,'nome':'Soro 500ml','categoria':'Medicamento','unidade':'Un','estoque_min':50,'estoque_atual':120,'fornecedor_id':3,'valor_un':'R$4,50'},{'id':5,'nome':'Creme de Leite 200g','categoria':'Alimentação','unidade':'Cx','estoque_min':15,'estoque_atual':8,'fornecedor_id':1,'valor_un':'R$6,30'}]
UTILIZADORES = [
    {'id':1,'nome':'Admin','usuario':'admin','email':'admin@nutricao.com','setor':'Administração','cargo':'Administrador','tipo':'admin','ativo':True,'permissoes':['*']},
    {'id':2,'nome':'Carla Nutrição','usuario':'carla.nutri','email':'carla@nutricao.com','setor':'Nutrição','cargo':'Nutricionista','tipo':'nutricionista','ativo':True,'permissoes':['cadastro.usuarios','mapa.pacientes']},
    {'id':3,'nome':'João Estoque','usuario':'joao.estoque','email':'joao@nutricao.com','setor':'Estoque','cargo':'Almoxarife','tipo':'almoxarife','ativo':False,'permissoes':['estoque.entrada_notas','estoque.visualizar_produtos']}
]

TOTALIZACAO_DIRETA = [
    {'id': 1, 'data': '2025-01-20', 'clinica': 'CTI', 'dieta': 'HIPERPROTEICA', 'horario': 'Almoço', 'quantidade': 12, 'observacao': 'Totalização direta de suporte'},
    {'id': 2, 'data': '2025-01-20', 'clinica': 'Clínica Médica', 'dieta': 'BRANDA', 'horario': 'Jantar', 'quantidade': 18, 'observacao': 'Entrada manual por contingência'},
]

AUTORIZACOES_SUBSTITUICAO = [
    {'id': 1, 'data': '2025-01-20 10:22', 'paciente': 'Maria Silva', 'leito': '101-A', 'dieta_origem': 'BRANDA', 'dieta_substituta': 'PASTOSA', 'motivo': 'Disfagia', 'status': 'Aprovada', 'autorizado_por': 'Carla Nutrição'},
    {'id': 2, 'data': '2025-01-20 11:10', 'paciente': 'João Santos', 'leito': '05', 'dieta_origem': 'HIPERPROTEICA', 'dieta_substituta': 'LÍQUIDA', 'motivo': 'Pré-procedimento', 'status': 'Pendente', 'autorizado_por': '-'},
]

LOG_ACOES = [
    {'id': 1, 'data': '2025-01-20 08:01', 'usuario': 'admin', 'acao': 'login', 'detalhe': 'Acesso ao sistema'},
    {'id': 2, 'data': '2025-01-20 08:25', 'usuario': 'carla.nutri', 'acao': 'mapa_refeicoes', 'detalhe': 'Atualizou dieta do leito 101-A'},
    {'id': 3, 'data': '2025-01-20 09:12', 'usuario': 'joao.estoque', 'acao': 'estoque', 'detalhe': 'Entrada de nota no estoque principal'},
]

CONSUMO_MENSAL_DIETAS = [
    {'dieta': 'BRANDA', 'total_mes': 420, 'media_dia': 14},
    {'dieta': 'HIPERPROTEICA', 'total_mes': 210, 'media_dia': 7},
    {'dieta': 'LÍQUIDA', 'total_mes': 180, 'media_dia': 6},
]

FATURAMENTO_X_MAPA = [
    {'clinica': 'Clínica Médica', 'mapa': 52300, 'faturado': 51500, 'diferenca': -800},
    {'clinica': 'CTI', 'mapa': 38700, 'faturado': 39100, 'diferenca': 400},
    {'clinica': 'Oncologia', 'mapa': 31500, 'faturado': 30950, 'diferenca': -550},
]

MAPA_SUPLEMENTOS = [
    {'clinica': 'CTI', 'suplemento': 'FORTIDRINK BAUNILHA 200ML', 'volume_total_ml': 2400},
    {'clinica': 'Pediatria', 'suplemento': 'FORTINI MULTI FIBER 200ML', 'volume_total_ml': 1600},
]

# ---- HELPERS ----
def active(page):
    return dict(active_page=page)

def fmt_data(d):
    if not d: return '-'
    p = d.split('-')
    return f'{p[2]}/{p[1]}/{p[0]}' if len(p)==3 else d

# ---- DASHBOARD ----
@nutricao.route('/nutricao')
def dashboard():
    total_pac = len([p for p in PACIENTES if p.get('ativo',True)])
    return render_template('nutricao_dashboard.html',
        total_pacientes=total_pac, total_dietas=len(DIETAS),
        total_clinicas=len(CLINICAS), alertas_estoque=[p for p in PRODUTOS if p['estoque_atual']<=p['estoque_min']],
        **active('dashboard'))

# ---- PACIENTES (CRUD) ----
@nutricao.route('/nutricao/pacientes')
def pacientes():
    return render_template('nutricao_pacientes.html', pacientes=PACIENTES, clinicas=CLINICAS, dietas=DIETAS, **active('pacientes'))

@nutricao.route('/nutricao/api/pacientes', methods=['GET','POST'])
def api_pacientes():
    if request.method=='POST':
        d = request.get_json(force=True)
        novo = {'id':max(p['id'] for p in PACIENTES)+1 if PACIENTES else 1}
        for k in ['nome','sexo','nascimento','prontuario','clinica','leito','dieta','altura_cm','peso_kg']:
            novo[k] = d.get(k)
        novo['ativo']=True
        PACIENTES.append(novo)
        return jsonify({'ok':True,'id':novo['id']})
    return jsonify(PACIENTES)

@nutricao.route('/nutricao/api/pacientes/<int:pid>', methods=['PUT','DELETE'])
def api_paciente(pid):
    p = next((x for x in PACIENTES if x['id']==pid), None)
    if not p: return jsonify({'error':'Não encontrado'}),404
    if request.method=='DELETE':
        p['ativo']=False
        return jsonify({'ok':True})
    d = request.get_json(force=True)
    for k in ['nome','sexo','nascimento','prontuario','clinica','leito','dieta','altura_cm','peso_kg']:
        if k in d: p[k]=d[k]
    return jsonify({'ok':True})

# ---- CLINICAS ----
@nutricao.route('/nutricao/clinicas')
def clinicas():
    return render_template(
        'nutricao_clinicas.html',
        clinicas=CLINICAS,
        enfermarias=ENFERMARIAS,
        leitos=LEITOS,
        **active('pacientes')
    )

@nutricao.route('/nutricao/api/clinicas', methods=['GET','POST'])
def api_clinicas():
    if request.method=='POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        centro_custo = (d.get('centro_custo') or '').strip()

        if not nome or not centro_custo:
            return jsonify({'ok':False,'error':'Campos obrigatórios: nome e centro_custo'}),400

        n = {
            'id':max(c['id'] for c in CLINICAS)+1 if CLINICAS else 1,
            'nome':nome,
            'centro_custo':centro_custo
        }
        CLINICAS.append(n)
        return jsonify({'ok':True,'id':n['id']})
    return jsonify(CLINICAS)

@nutricao.route('/nutricao/api/clinicas/<int:cid>', methods=['PUT','DELETE'])
def api_clinica_ops(cid):
    global CLINICAS, ENFERMARIAS, LEITOS
    c = next((x for x in CLINICAS if x['id']==cid), None)
    if not c:
        return jsonify({'ok':False,'error':'Clínica não encontrada'}),404

    if request.method=='DELETE':
        enfermarias_ids = [e['id'] for e in ENFERMARIAS if e['clinica_id']==cid]
        CLINICAS = [x for x in CLINICAS if x['id']!=cid]
        ENFERMARIAS = [e for e in ENFERMARIAS if e['clinica_id']!=cid]
        LEITOS = [l for l in LEITOS if l['enfermaria_id'] not in enfermarias_ids]
        return jsonify({'ok':True})

    d = request.get_json(force=True) or {}
    c['nome'] = d.get('nome', c['nome']).strip()
    c['centro_custo'] = d.get('centro_custo', c.get('centro_custo','')).strip()
    return jsonify({'ok':True})

@nutricao.route('/nutricao/api/enfermarias', methods=['GET','POST'])
def api_enfermarias():
    if request.method=='POST':
        d = request.get_json(force=True) or {}
        clinica_id = int(d.get('clinica_id',0) or 0)
        nome = (d.get('nome') or '').strip()
        numero_leito = (d.get('numero_leito') or '').strip()

        if not clinica_id or not nome or not numero_leito:
            return jsonify({'ok':False,'error':'Campos obrigatórios: clinica_id, nome e numero_leito'}),400

        if not any(c['id'] == clinica_id for c in CLINICAS):
            return jsonify({'ok':False,'error':'Clínica não encontrada'}),404

        n = {
            'id':max(e['id'] for e in ENFERMARIAS)+1 if ENFERMARIAS else 1,
            'clinica_id':clinica_id,
            'nome':nome,
            'numero_leito':numero_leito,
            'nutriz':bool(d.get('nutriz',False)),
            'ativo':bool(d.get('ativo',True))
        }
        ENFERMARIAS.append(n)
        return jsonify({'ok':True,'id':n['id']})
    return jsonify(ENFERMARIAS)

@nutricao.route('/nutricao/api/enfermarias/<int:eid>', methods=['PUT','DELETE'])
def api_enfermaria_ops(eid):
    global ENFERMARIAS, LEITOS
    e = next((x for x in ENFERMARIAS if x['id']==eid), None)
    if not e:
        return jsonify({'ok':False,'error':'Enfermaria não encontrada'}),404

    if request.method=='DELETE':
        ENFERMARIAS = [x for x in ENFERMARIAS if x['id']!=eid]
        LEITOS = [l for l in LEITOS if l['enfermaria_id']!=eid]
        return jsonify({'ok':True})

    d = request.get_json(force=True) or {}
    e['clinica_id'] = int(d.get('clinica_id', e['clinica_id']) or 0)
    e['nome'] = d.get('nome', e['nome']).strip()
    e['numero_leito'] = d.get('numero_leito', e['numero_leito']).strip()
    e['nutriz'] = bool(d.get('nutriz', e['nutriz']))
    e['ativo'] = bool(d.get('ativo', e['ativo']))
    return jsonify({'ok':True})

@nutricao.route('/nutricao/api/leitos', methods=['GET','POST'])
def api_leitos():
    if request.method=='POST':
        d = request.get_json(force=True) or {}
        enfermaria_id = int(d.get('enfermaria_id',0) or 0)
        numero_leito = (d.get('numero_leito') or '').strip()
        nome_leito = (d.get('nome_leito') or '').strip()

        if not enfermaria_id or not numero_leito or not nome_leito:
            return jsonify({'ok':False,'error':'Campos obrigatórios: enfermaria_id, numero_leito e nome_leito'}),400

        if not any(e['id'] == enfermaria_id for e in ENFERMARIAS):
            return jsonify({'ok':False,'error':'Enfermaria não encontrada'}),404

        n = {
            'id':max(l['id'] for l in LEITOS)+1 if LEITOS else 1,
            'enfermaria_id':enfermaria_id,
            'numero_leito':numero_leito,
            'nome_leito':nome_leito,
            'ativo':bool(d.get('ativo',True))
        }
        LEITOS.append(n)
        return jsonify({'ok':True,'id':n['id']})
    return jsonify(LEITOS)

@nutricao.route('/nutricao/api/leitos/<int:lid>', methods=['PUT','DELETE'])
def api_leito_ops(lid):
    global LEITOS
    l = next((x for x in LEITOS if x['id']==lid), None)
    if not l:
        return jsonify({'ok':False,'error':'Leito não encontrado'}),404

    if request.method=='DELETE':
        LEITOS = [x for x in LEITOS if x['id']!=lid]
        return jsonify({'ok':True})

    d = request.get_json(force=True) or {}
    l['enfermaria_id'] = int(d.get('enfermaria_id', l['enfermaria_id']) or 0)
    l['numero_leito'] = d.get('numero_leito', l['numero_leito']).strip()
    l['nome_leito'] = d.get('nome_leito', l['nome_leito']).strip()
    l['ativo'] = bool(d.get('ativo', l['ativo']))
    return jsonify({'ok':True})

# ---- DIETAS ----
@nutricao.route('/nutricao/api/dietas', methods=['GET','POST'])
def api_dietas():
    if request.method=='POST':
        d = request.get_json(force=True)
        n = {'id':max(dd['id'] for dd in DIETAS)+1 if DIETAS else 1,'nome':d.get('nome','').upper()}
        DIETAS.append(n)
        return jsonify({'ok':True,'id':n['id']})
    return jsonify(DIETAS)

@nutricao.route('/nutricao/api/dietas/<int:did>', methods=['DELETE'])
def api_dieta_delete(did):
    global DIETAS
    DIETAS = [d for d in DIETAS if d['id']!=did]
    return jsonify({'ok':True})

# ---- MAPA REFEIÇÕES ----
@nutricao.route('/nutricao/mapa_refeicoes')
def mapa_refeicoes():
    return render_template('nutricao_mapa_refeicoes.html', dietas=DIETAS, clinicas=CLINICAS, **active('mapa_refeicoes'))

# ---- ESTOQUE ----
@nutricao.route('/nutricao/estoque')
def estoque():
    return render_template('nutricao_estoque.html', produtos=PRODUTOS, fornecedores=FORNECEDORES, **active('estoque'))

@nutricao.route('/nutricao/api/produtos', methods=['GET','POST'])
def api_produtos():
    if request.method=='POST':
        d = request.get_json(force=True)
        n = {'id':max(p['id'] for p in PRODUTOS)+1 if PRODUTOS else 1}
        for k in ['nome','categoria','unidade','estoque_min','estoque_atual','fornecedor_id','valor_un']:
            n[k]=d.get(k)
        PRODUTOS.append(n)
        return jsonify({'ok':True,'id':n['id']})
    return jsonify(PRODUTOS)

@nutricao.route('/nutricao/api/fornecedores', methods=['GET','POST'])
def api_fornecedores():
    if request.method=='POST':
        d=request.get_json(force=True)
        n={'id':max(f['id'] for f in FORNECEDORES)+1 if FORNECEDORES else 1}
        for k in ['nome','cnpj','contato','telefone','email']: n[k]=d.get(k)
        FORNECEDORES.append(n)
        return jsonify({'ok':True,'id':n['id']})
    return jsonify(FORNECEDORES)

# ---- RELATÓRIOS ----
@nutricao.route('/nutricao/relatorios')
def relatorios():
    totalizacoes = [
        {'clinica':'Clínica Médica','dieta':'BRANDA','desjejum':8,'colacao':6,'almoco':10,'merenda':5,'jantar':9,'ceia':4},
        {'clinica':'CTI','dieta':'HIPERPROTEICA','desjejum':3,'colacao':2,'almoco':4,'merenda':2,'jantar':3,'ceia':1},
        {'clinica':'Oncologia','dieta':'LÍQUIDA','desjejum':5,'colacao':3,'almoco':6,'merenda':4,'jantar':5,'ceia':2},
    ]
    return render_template(
        'nutricao_relatorios.html',
        totalizacoes=totalizacoes,
        consumo_mensal=CONSUMO_MENSAL_DIETAS,
        faturamento_mapa=FATURAMENTO_X_MAPA,
        mapa_suplementos=MAPA_SUPLEMENTOS,
        **active('relatorios')
    )

# ---- FATURAMENTO ----
@nutricao.route('/nutricao/faturamento')
def faturamento():
    return render_template('nutricao_faturamento.html', **active('faturamento'))

# ---- ADMIN ----
@nutricao.route('/nutricao/admin')
def admin():
    return render_template('nutricao_admin.html', usuarios=UTILIZADORES, **active('admin'))

@nutricao.route('/nutricao/api/usuarios', methods=['POST'])
def api_usuarios_create():
    d = request.get_json(force=True) or {}

    nome = (d.get('nome') or '').strip()
    usuario = (d.get('usuario') or '').strip()
    setor = (d.get('setor') or '').strip()
    cargo = (d.get('cargo') or '').strip()
    senha = d.get('senha') or ''
    confirmar_senha = d.get('confirmar_senha') or ''
    ativo = bool(d.get('ativo', True))
    permissoes = d.get('permissoes') or []

    if not nome or not usuario or not setor or not cargo:
        return jsonify({'ok': False, 'error': 'Campos obrigatórios: nome, usuário, setor e cargo.'}), 400

    if not senha:
        return jsonify({'ok': False, 'error': 'Senha é obrigatória.'}), 400

    if senha != confirmar_senha:
        return jsonify({'ok': False, 'error': 'Senha e confirmação não conferem.'}), 400

    if any((u.get('usuario', '').lower() == usuario.lower()) for u in UTILIZADORES):
        return jsonify({'ok': False, 'error': 'Nome de usuário já existe.'}), 409

    novo = {
        'id': max([u['id'] for u in UTILIZADORES], default=0) + 1,
        'nome': nome,
        'usuario': usuario,
        'email': d.get('email', ''),
        'setor': setor,
        'cargo': cargo,
        'tipo': d.get('tipo', 'operador'),
        'ativo': ativo,
        'permissoes': permissoes
    }
    UTILIZADORES.append(novo)
    return jsonify({'ok': True, 'id': novo['id']})

# ---- UTILITÁRIOS ----
@nutricao.route('/nutricao/utilitarios')
def utilitarios():
    return render_template(
        'nutricao_utilitarios.html',
        autorizacoes=AUTORIZACOES_SUBSTITUICAO,
        logs=LOG_ACOES,
        **active('utilitarios')
    )

@nutricao.route('/nutricao/api/totalizacao_direta', methods=['GET', 'POST'])
def api_totalizacao_direta():
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        novo = {
            'id': max([x['id'] for x in TOTALIZACAO_DIRETA], default=0) + 1,
            'data': d.get('data', date.today().isoformat()),
            'clinica': d.get('clinica', ''),
            'dieta': d.get('dieta', ''),
            'horario': d.get('horario', ''),
            'quantidade': int(d.get('quantidade', 0) or 0),
            'observacao': d.get('observacao', '')
        }
        TOTALIZACAO_DIRETA.append(novo)
        return jsonify({'ok': True, 'id': novo['id']})
    return jsonify(TOTALIZACAO_DIRETA)

@nutricao.route('/nutricao/api/autorizacoes_substituicao', methods=['GET', 'POST', 'PUT'])
def api_autorizacoes_substituicao():
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        novo = {
            'id': max([x['id'] for x in AUTORIZACOES_SUBSTITUICAO], default=0) + 1,
            'data': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'paciente': d.get('paciente', ''),
            'leito': d.get('leito', ''),
            'dieta_origem': d.get('dieta_origem', ''),
            'dieta_substituta': d.get('dieta_substituta', ''),
            'motivo': d.get('motivo', ''),
            'status': 'Pendente',
            'autorizado_por': '-'
        }
        AUTORIZACOES_SUBSTITUICAO.append(novo)
        return jsonify({'ok': True, 'id': novo['id']})

    if request.method == 'PUT':
        d = request.get_json(force=True) or {}
        aid = int(d.get('id', 0) or 0)
        item = next((x for x in AUTORIZACOES_SUBSTITUICAO if x['id'] == aid), None)
        if not item:
            return jsonify({'ok': False, 'error': 'Autorização não encontrada'}), 404
        item['status'] = d.get('status', item['status'])
        item['autorizado_por'] = d.get('autorizado_por', item['autorizado_por'])
        return jsonify({'ok': True})

    return jsonify(AUTORIZACOES_SUBSTITUICAO)

@nutricao.route('/nutricao/api/logs', methods=['GET'])
def api_logs():
    return jsonify(LOG_ACOES)
