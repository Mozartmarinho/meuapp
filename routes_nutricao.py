from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from datetime import datetime, date
import json

from models import db
from models_nutricao import (
    NutClinica, NutEnfermaria, NutLeito, NutDieta, NutGrupoDieta, NutPaciente, NutMapaRefeicao, NutCardapio,
    NutTabelaNutrientes, NutAlimento, NutAlimentoNutriente, NutPratoLiquido,
    NutEstoqueLocal, NutUnidadeMedida, NutGrupoProduto, NutProduto, NutFornecedor,
    NutEtiqueta, NutEtiquetaCampo, NutPrecoRefeicao, NutTipoRefeicao, NutPrecoDietaTipo,
)
from nutricao_service import (
    seed_nutricao,
    paciente_from_payload,
    mapa_from_paciente,
    garantir_mapa_do_dia,
    marcar_alteracao_mapa,
    list_clinicas,
    list_enfermarias,
    list_leitos,
    list_dietas,
    list_grupos_dieta,
    list_tipos_refeicao,
    normalizar_hora_limite,
    list_cardapios,
    list_tabelas_nutrientes,
    list_alimentos,
    import_tabela_fdc,
    list_pratos_liquidos,
    list_estoques,
    list_unidades,
    list_grupos_produto,
    list_produtos,
    list_fornecedores,
    list_etiquetas,
    list_precos_refeicoes,
    matriz_precos_dieta_tipo,
    _seed_precos_dieta_tipo,
    ensure_precos_para_dieta,
    totalizar_mapa_uma,
    relatorio_faturamento,
    totalizacao_dietas as gerar_totalizacao_dietas,
    listar_avisos_alta_mapa,
    aplicar_avisos_alta_mapa,
    registrar_saida_mapa,
    list_modelos_etiqueta_impressao,
    gerar_impressao_etiquetas,
    get_mapa_substituicoes,
    save_mapa_substituicoes,
    importar_substituicoes_anteriores,
    CARDAPIO_OPCOES,
    ESTADOS_BR,
    _parse_date,
)

nutricao = Blueprint('nutricao', __name__, template_folder='templates_nutricao')

# ---- DADOS MOCKADOS (módulos ainda não migrados) ----
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
FUNCIONARIOS = [
    {'id':1,'nome':'Dr. Ricardo Almeida','cargo':'Médico','setor':'Clínica Médica','telefone':'(11)99999-0001','email':'ricardo@h.com','situacao':'ativo'},
    {'id':2,'nome':'Enf. Patricia Lima','cargo':'Enfermeira','setor':'CTI','telefone':'(11)99999-0002','email':'patricia@h.com','situacao':'ativo'},
    {'id':3,'nome':'Nut. Carla Souza','cargo':'Nutricionista','setor':'Nutrição','telefone':'(11)99999-0003','email':'carla@h.com','situacao':'ativo'},
    {'id':4,'nome':'Aux. João Costa','cargo':'Auxiliar','setor':'Oncologia','telefone':'(11)99999-0004','email':'joao@h.com','situacao':'ativo'},
    {'id':5,'nome':'Téc. Maria Fernanda','cargo':'Técnico','setor':'Pediatria','telefone':'(11)99999-0005','email':'mariaf@h.com','situacao':'inativo'},
]
FORNECEDORES = [{'id':1,'nome':'Distribuidora Alimentos Ltda','cnpj':'11.222.333/0001-44','contato':'Carlos','telefone':'(11)3333-0001','email':'carlos@dist.com'},{'id':2,'nome':'NutriSupply S.A.','cnpj':'55.666.777/0001-88','contato':'Ana','telefone':'(11)3333-0002','email':'ana@nutri.com'},{'id':3,'nome':'HospMedic','cnpj':'99.888.777/0001-55','contato':'José','telefone':'(11)3333-0003','email':'jose@hosp.com'}]
PRODUTOS = [
    {'id':1,'nome':'Arroz 5kg','categoria':'Alimentação','unidade':'Saco','estoque_min':10,'estoque_atual':45,'fornecedor_id':1,'valor_un':'R$22,50'},
    {'id':2,'nome':'Feijão Preto 1kg','categoria':'Alimentação','unidade':'Pacote','estoque_min':20,'estoque_atual':38,'fornecedor_id':1,'valor_un':'R$8,90'},
    {'id':3,'nome':'Suplemento Proteico 500g','categoria':'Suplemento','unidade':'Lata','estoque_min':5,'estoque_atual':12,'fornecedor_id':2,'valor_un':'R$89,00'},
    {'id':4,'nome':'Soro 500ml','categoria':'Medicamento','unidade':'Un','estoque_min':50,'estoque_atual':120,'fornecedor_id':3,'valor_un':'R$4,50'},
    {'id':5,'nome':'Creme de Leite 200g','categoria':'Alimentação','unidade':'Cx','estoque_min':15,'estoque_atual':8,'fornecedor_id':1,'valor_un':'R$6,30'},
]
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

FLAG_FIELDS = (
    'fl_desjejum', 'fl_colacao', 'fl_almoco', 'fl_merenda', 'fl_jantar', 'fl_ceia'
)


# ---- HELPERS ----
def active(page):
    return dict(active_page=page)


def fmt_data(d):
    if not d:
        return '-'
    if isinstance(d, date):
        return d.strftime('%d/%m/%Y')
    p = str(d).split('-')
    return f'{p[2]}/{p[1]}/{p[0]}' if len(p) == 3 else d


def _list_pacientes_db(ativos_only=True, q=None, limit=50):
    query = NutPaciente.query
    if ativos_only:
        query = query.filter_by(ativo=True)
    termo = (q or '').strip()
    if termo:
        query = query.filter(NutPaciente.nome.ilike(f'%{termo}%'))
    query = query.order_by(NutPaciente.nome)
    if limit:
        query = query.limit(limit)
    return [p.to_dict() for p in query.all()]


def _usuario_sessao():
    return (
        session.get('user_name')
        or session.get('usuario_nome')
        or session.get('user_email')
        or 'sistema'
    )[:80]


def _list_dietas_db(somente_ativas=True):
    rows = list_dietas(somente_ativas=somente_ativas)
    return rows


def _list_clinicas_db(somente_ativas=False):
    rows = list_clinicas(somente_ativas=somente_ativas)
    if rows:
        return rows
    return CLINICAS


def _mapa_linhas(data_ref):
    garantir_mapa_do_dia(data_ref)
    rows = (
        NutMapaRefeicao.query
        .filter_by(data_refeicao=data_ref, ativo=True)
        .order_by(NutMapaRefeicao.clinica, NutMapaRefeicao.leito, NutMapaRefeicao.nome)
        .all()
    )
    return [r.to_dict() for r in rows]


# ---- DASHBOARD / MAPA DE PRODUÇÃO ----
@nutricao.route('/nutricao')
def dashboard():
    seed_nutricao()
    data_ref = date.today()
    # Grade só carrega no cliente após filtro de clínica/enfermaria
    return render_template(
        'nutricao_dashboard.html',
        mapa_linhas=[],
        data_mapa=data_ref.isoformat(),
        clinicas=_list_clinicas_db(somente_ativas=True),
        enfermarias=list_enfermarias(somente_ativas=True),
        dietas=_list_dietas_db(),
        total_pacientes=NutPaciente.query.filter_by(ativo=True).count(),
        total_dietas=NutDieta.query.filter_by(ativo=True).count(),
        total_clinicas=NutClinica.query.filter_by(ativo=True).count() or len(CLINICAS),
        alertas_estoque=[p for p in PRODUTOS if p['estoque_atual'] <= p['estoque_min']],
        usuario_atual=_usuario_sessao(),
        **active('dashboard')
    )


# ---- PACIENTES (CRUD MySQL) ----
@nutricao.route('/nutricao/pacientes')
def pacientes():
    seed_nutricao()
    return render_template(
        'nutricao_pacientes.html',
        pacientes=_list_pacientes_db(False),
        clinicas=_list_clinicas_db(somente_ativas=True),
        dietas=_list_dietas_db(),
        **active('cadastro_pacientes')
    )


@nutricao.route('/nutricao/api/pacientes', methods=['GET', 'POST'])
def api_pacientes():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        if not (d.get('nome') or '').strip():
            return jsonify({'ok': False, 'error': 'Nome do paciente é obrigatório'}), 400
        p = paciente_from_payload(d)
        p.ativo = True
        if not p.admissao:
            p.admissao = date.today()
        db.session.add(p)
        db.session.flush()
        linha = None
        # Por padrão só cadastra; inclusão no mapa é via /api/mapa/inserir
        if d.get('adicionar_mapa'):
            data_mapa = _parse_date(d.get('admissao')) or _parse_date(d.get('data_mapa')) or date.today()
            flags = {fl: bool(d.get(fl, True)) for fl in FLAG_FIELDS}
            extras = {
                'adm': _parse_date(d.get('admissao')) or p.admissao,
                'leito': d.get('leito'),
                'prontuario': d.get('prontuario'),
                'diagnostico': d.get('diagnostico'),
                'dieta': d.get('dieta'),
                'observacoes': d.get('observacoes'),
                'clinica': d.get('clinica'),
                'enfermaria': d.get('enfermaria'),
                'obs_etiqueta': d.get('obs_etiqueta'),
                'extras': d.get('extras'),
                'suplementos': d.get('suplementos'),
                'enteral': d.get('enteral'),
                'formula_infantil': d.get('formula_infantil'),
                'lve': d.get('lve'),
            }
            linha = mapa_from_paciente(p, data_mapa, flags=flags, extras=extras, usuario=_usuario_sessao())
            db.session.add(linha)
        db.session.commit()
        payload = {'ok': True, 'id': p.id, 'paciente': p.to_dict()}
        if linha:
            payload['linha'] = linha.to_dict()
        return jsonify(payload)
    q = request.args.get('q') or request.args.get('nome') or ''
    limit = request.args.get('limit', type=int) or 40
    return jsonify({
        'ok': True,
        'pacientes': _list_pacientes_db(True, q=q, limit=limit),
    })


@nutricao.route('/nutricao/api/pacientes/<int:pid>', methods=['PUT', 'DELETE'])
def api_paciente(pid):
    p = NutPaciente.query.get(pid)
    if not p:
        return jsonify({'ok': False, 'error': 'Não encontrado'}), 404
    if request.method == 'DELETE':
        p.ativo = False
        p.data_saida = p.data_saida or date.today()
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    paciente_from_payload(d, p)
    db.session.commit()
    # sincroniza snapshot do mapa de hoje se existir
    hoje = date.today()
    linha = NutMapaRefeicao.query.filter_by(data_refeicao=hoje, paciente_id=p.id, ativo=True).first()
    if linha:
        linha.adm = p.admissao
        linha.leito = p.leito
        linha.prontuario = p.prontuario
        linha.nome = p.nome
        linha.idade = p.idade(hoje)
        linha.diagnostico = p.diagnostico
        linha.dieta = p.dieta
        linha.observacoes = p.observacoes
        linha.clinica = p.clinica
        marcar_alteracao_mapa(linha, _usuario_sessao())
        db.session.commit()
    return jsonify({'ok': True, 'paciente': p.to_dict()})


# ---- MAPA API ----
@nutricao.route('/nutricao/api/mapa', methods=['GET'])
def api_mapa_get():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    _seed_aviso_alta_demo(data_ref)
    return jsonify({
        'ok': True,
        'data': data_ref.isoformat(),
        'linhas': _mapa_linhas(data_ref),
        'clinicas': _list_clinicas_db(somente_ativas=True),
        'enfermarias': list_enfermarias(somente_ativas=True),
        'avisos_alta': listar_avisos_alta_mapa(data_ref),
    })


@nutricao.route('/nutricao/api/mapa/inserir', methods=['POST'])
def api_mapa_inserir():
    """Insere paciente existente (ou atualiza cadastro) no mapa do dia."""
    seed_nutricao()
    d = request.get_json(force=True) or {}
    paciente_id = d.get('paciente_id')
    p = NutPaciente.query.get(paciente_id) if paciente_id else None
    if not p:
        return jsonify({'ok': False, 'error': 'Selecione um paciente cadastrado'}), 400

    # atualiza dados básicos do cadastro se enviados
    for campo in ('prontuario', 'diagnostico', 'dieta', 'observacoes', 'clinica', 'leito'):
        if campo in d and d.get(campo) is not None:
            setattr(p, campo, (str(d.get(campo)).strip() or None))
    if 'admissao' in d:
        p.admissao = _parse_date(d.get('admissao')) or p.admissao

    data_mapa = _parse_date(d.get('data_mapa')) or date.today()
    existe = NutMapaRefeicao.query.filter_by(
        data_refeicao=data_mapa, paciente_id=p.id, ativo=True
    ).first()
    if existe:
        return jsonify({'ok': False, 'error': 'Paciente já está no mapa deste dia'}), 400

    clinica = (d.get('clinica') or '').strip()
    enfermaria = (d.get('enfermaria') or '').strip()
    leito = (d.get('leito') or '').strip()
    if not clinica:
        return jsonify({'ok': False, 'error': 'Informe a clínica'}), 400
    if not enfermaria:
        return jsonify({'ok': False, 'error': 'Informe a enfermaria'}), 400
    if not leito:
        return jsonify({'ok': False, 'error': 'Informe o leito'}), 400

    # Reinserção no mapa: limpa saída anterior para o paciente voltar a persistir nos dias seguintes
    p.ativo = True
    p.data_saida = None
    p.hora_saida = None
    p.motivo_saida = None

    flags = {fl: bool(d.get(fl, True)) for fl in FLAG_FIELDS}
    extras = {
        'adm': _parse_date(d.get('admissao')) or p.admissao,
        'leito': leito,
        'prontuario': d.get('prontuario', p.prontuario),
        'diagnostico': d.get('diagnostico', p.diagnostico),
        'dieta': d.get('dieta', p.dieta),
        'observacoes': d.get('observacoes', p.observacoes),
        'clinica': clinica,
        'enfermaria': enfermaria,
        'obs_etiqueta': d.get('obs_etiqueta'),
        'extras': d.get('extras'),
        'suplementos': d.get('suplementos'),
        'enteral': d.get('enteral'),
        'formula_infantil': d.get('formula_infantil'),
        'lve': d.get('lve'),
    }
    linha = mapa_from_paciente(p, data_mapa, flags=flags, extras=extras, usuario=_usuario_sessao())
    db.session.add(linha)
    db.session.commit()
    return jsonify({'ok': True, 'linha': linha.to_dict(), 'paciente': p.to_dict()})


@nutricao.route('/nutricao/api/mapa/avisos-alta', methods=['GET', 'POST'])
def api_mapa_avisos_alta():
    seed_nutricao()
    if request.method == 'GET':
        data_ref = _parse_date(request.args.get('data')) or date.today()
        _seed_aviso_alta_demo(data_ref)
        return jsonify({
            'ok': True,
            'data': data_ref.isoformat(),
            'avisos': listar_avisos_alta_mapa(data_ref),
        })
    d = request.get_json(force=True) or {}
    excluir_ids = d.get('excluir_ids') or []
    if not excluir_ids and d.get('itens'):
        excluir_ids = [it.get('mapa_id') for it in d['itens'] if it.get('excluir')]
    qtd = aplicar_avisos_alta_mapa(excluir_ids, usuario=_usuario_sessao())
    data_ref = _parse_date(d.get('data')) or date.today()
    return jsonify({
        'ok': True,
        'excluidos': qtd,
        'linhas': _mapa_linhas(data_ref),
        'avisos_alta': listar_avisos_alta_mapa(data_ref),
    })


def _seed_aviso_alta_demo(data_ref):
    """Demo desativada: não altera pacientes reais (evita sumiço indevido no mapa)."""
    return


@nutricao.route('/nutricao/api/mapa/<int:mid>', methods=['PUT'])
def api_mapa_put(mid):
    row = NutMapaRefeicao.query.get(mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    d = request.get_json(force=True) or {}
    for campo in (
        'leito', 'prontuario', 'nome', 'diagnostico', 'dieta', 'observacoes', 'clinica', 'enfermaria',
        'obs_etiqueta', 'extras', 'suplementos', 'enteral', 'formula_infantil', 'lve',
    ):
        if campo in d:
            val = d.get(campo)
            setattr(row, campo, (str(val).strip() if val is not None else '') or None)
    if 'idade' in d:
        try:
            row.idade = int(d['idade']) if d['idade'] not in (None, '') else None
        except (TypeError, ValueError):
            pass
    if 'adm' in d:
        row.adm = _parse_date(d.get('adm'))
    # data_saida do mapa só via Excluir (/saida); não permitir zerar/alterar por PUT genérico
    for fl in FLAG_FIELDS:
        if fl in d:
            setattr(row, fl, bool(d.get(fl)))
    marcar_alteracao_mapa(row, _usuario_sessao())
    db.session.commit()
    return jsonify({'ok': True, 'linha': row.to_dict()})


@nutricao.route('/nutricao/api/mapa/<int:mid>/saida', methods=['POST'])
def api_mapa_saida(mid):
    """Alta médica, óbito ou transferência externa — baixa com histórico (não apaga a linha)."""
    seed_nutricao()
    row = NutMapaRefeicao.query.get(mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    d = request.get_json(force=True) or {}
    tipo = (d.get('motivo') or d.get('tipo') or '').strip().lower()
    if not tipo:
        return jsonify({'ok': False, 'error': 'Selecione o motivo da saída'}), 400
    usuario = _usuario_sessao()
    data_ref = _parse_date(d.get('data_saida')) or row.data_refeicao or date.today()

    if tipo in ('alta_medica', 'alta', 'a'):
        registrar_saida_mapa(row, motivo='Alta médica', usuario=usuario, data_saida=data_ref)
        db.session.commit()
        return jsonify({'ok': True, 'acao': 'alta_medica', 'linha': row.to_dict()})

    if tipo in ('obito', 'óbito', 'o'):
        registrar_saida_mapa(row, motivo='Óbito', usuario=usuario, data_saida=data_ref)
        db.session.commit()
        return jsonify({'ok': True, 'acao': 'obito', 'linha': row.to_dict()})

    if tipo in ('transferencia', 'transferência', 't'):
        hospital = (
            d.get('hospital_transferencia')
            or d.get('hospital')
            or d.get('hospital_destino')
            or ''
        ).strip()
        if not hospital:
            return jsonify({'ok': False, 'error': 'Informe o hospital de transferência'}), 400
        registrar_saida_mapa(
            row,
            motivo='Transferência',
            usuario=usuario,
            data_saida=data_ref,
            hospital_transferencia=hospital,
        )
        db.session.commit()
        return jsonify({'ok': True, 'acao': 'transferencia', 'linha': row.to_dict()})

    return jsonify({'ok': False, 'error': 'Motivo inválido. Use alta_medica, obito ou transferencia'}), 400


@nutricao.route('/nutricao/api/mapa/<int:mid>/toggle', methods=['POST'])
def api_mapa_toggle(mid):
    row = NutMapaRefeicao.query.get(mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    d = request.get_json(force=True) or {}
    campo = (d.get('campo') or '').strip()
    if campo not in FLAG_FIELDS:
        return jsonify({'ok': False, 'error': 'Campo inválido'}), 400
    if 'valor' in d:
        setattr(row, campo, bool(d.get('valor')))
    else:
        setattr(row, campo, not bool(getattr(row, campo)))
    marcar_alteracao_mapa(row, _usuario_sessao())
    db.session.commit()
    return jsonify({'ok': True, 'linha': row.to_dict()})


@nutricao.route('/nutricao/api/mapa/<int:mid>/substituicoes', methods=['GET', 'PUT'])
def api_mapa_substituicoes(mid):
    """Cardápio padrão + substituições (cardápio personalizado) da linha do mapa."""
    seed_nutricao()
    row = NutMapaRefeicao.query.get(mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404

    if request.method == 'GET':
        return jsonify(get_mapa_substituicoes(row))

    d = request.get_json(force=True) or {}
    save_mapa_substituicoes(row, d, usuario=_usuario_sessao())
    db.session.commit()
    return jsonify(get_mapa_substituicoes(row))


@nutricao.route('/nutricao/api/mapa/<int:mid>/substituicoes/importar', methods=['POST'])
def api_mapa_substituicoes_importar(mid):
    """Importa pares ou justificativa do mapa anterior do mesmo paciente."""
    seed_nutricao()
    row = NutMapaRefeicao.query.get(mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    d = request.get_json(force=True) or {}
    meal = (d.get('meal') or '').strip().lower() or None
    so_just = bool(d.get('justificativa') or d.get('so_justificativa'))
    result = importar_substituicoes_anteriores(row, meal=meal, so_justificativa=so_just)
    if result is None:
        return jsonify({'ok': False, 'error': 'Nenhum mapa anterior encontrado para importar'}), 404
    marcar_alteracao_mapa(row, _usuario_sessao())
    db.session.commit()
    return jsonify(get_mapa_substituicoes(row))


# ---- CLINICAS (página) ----
@nutricao.route('/nutricao/clinicas')
def clinicas():
    seed_nutricao()
    return render_template(
        'nutricao_clinicas.html',
        clinicas=_list_clinicas_db(somente_ativas=False),
        **active('cadastro_clinicas')
    )


@nutricao.route('/nutricao/api/clinicas', methods=['GET', 'POST'])
def api_clinicas():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da clínica é obrigatório'}), 400
        if NutClinica.query.filter_by(nome=nome).first():
            return jsonify({'ok': False, 'error': 'Já existe clínica com este nome'}), 400
        row = NutClinica(
            nome=nome,
            centro_custo=(d.get('centro_custo') or '').strip() or None,
            ativo=bool(d.get('ativo', True)),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'clinica': row.to_dict()})
    somente_ativas = str(request.args.get('ativas', '')).lower() in ('1', 'true', 'sim')
    return jsonify(_list_clinicas_db(somente_ativas=somente_ativas))


@nutricao.route('/nutricao/api/clinicas/<int:cid>', methods=['PUT', 'DELETE'])
def api_clinica_ops(cid):
    row = NutClinica.query.get(cid)
    if not row:
        return jsonify({'ok': False, 'error': 'Clínica não encontrada'}), 404

    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da clínica é obrigatório'}), 400
        outro = NutClinica.query.filter(NutClinica.nome == nome, NutClinica.id != cid).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe clínica com este nome'}), 400
        row.nome = nome
    if 'centro_custo' in d:
        row.centro_custo = (d.get('centro_custo') or '').strip() or None
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    db.session.commit()
    return jsonify({'ok': True, 'clinica': row.to_dict()})


@nutricao.route('/nutricao/api/clinicas/<int:cid>/enfermarias', methods=['GET', 'PUT'])
def api_clinica_enfermarias(cid):
    seed_nutricao()
    clinica = NutClinica.query.get(cid)
    if not clinica:
        return jsonify({'ok': False, 'error': 'Clínica não encontrada'}), 404

    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'clinica': clinica.to_dict(include_enfermarias=True),
            'todas': list_enfermarias(somente_ativas=True),
        })

        d = request.get_json(force=True) or {}
    ids = d.get('enfermaria_ids')
    if ids is None:
        return jsonify({'ok': False, 'error': 'Informe enfermaria_ids'}), 400
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'enfermaria_ids inválido'}), 400

    selecionadas = NutEnfermaria.query.filter(
        NutEnfermaria.id.in_(ids),
        NutEnfermaria.ativo.is_(True),
    ).all() if ids else []
    clinica.enfermarias = selecionadas
    db.session.commit()
    return jsonify({'ok': True, 'clinica': clinica.to_dict(include_enfermarias=True)})


@nutricao.route('/nutricao/enfermarias')
def enfermarias():
    seed_nutricao()
    clinica_id = request.args.get('clinica_id', type=int)
    return render_template(
        'nutricao_enfermarias.html',
        enfermarias=list_enfermarias(somente_ativas=False),
        clinicas=list_clinicas(somente_ativas=False),
        clinica_id_inicial=clinica_id,
        **active('cadastro_enfermarias')
    )


@nutricao.route('/nutricao/api/enfermarias', methods=['GET', 'POST'])
def api_enfermarias():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da enfermaria é obrigatório'}), 400
        if NutEnfermaria.query.filter_by(nome=nome).first():
            return jsonify({'ok': False, 'error': 'Já existe enfermaria com este nome'}), 400
        row = NutEnfermaria(
            nome=nome,
            ativo=bool(d.get('ativo', True)),
            nutriz=bool(d.get('nutriz', False)),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'enfermaria': row.to_dict()})
    somente_ativas = str(request.args.get('ativas', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_enfermarias(somente_ativas=somente_ativas))


@nutricao.route('/nutricao/api/enfermarias/<int:eid>', methods=['PUT', 'DELETE'])
def api_enfermaria_ops(eid):
    row = NutEnfermaria.query.get(eid)
    if not row:
        return jsonify({'ok': False, 'error': 'Enfermaria não encontrada'}), 404

    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da enfermaria é obrigatório'}), 400
        outro = NutEnfermaria.query.filter(NutEnfermaria.nome == nome, NutEnfermaria.id != eid).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe enfermaria com este nome'}), 400
        row.nome = nome
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    if 'nutriz' in d:
        row.nutriz = bool(d.get('nutriz'))
    db.session.commit()
    return jsonify({'ok': True, 'enfermaria': row.to_dict()})


@nutricao.route('/nutricao/api/enfermarias/<int:eid>/leitos', methods=['GET'])
def api_enfermaria_leitos(eid):
    seed_nutricao()
    row = NutEnfermaria.query.get(eid)
    if not row:
        return jsonify({'ok': False, 'error': 'Enfermaria não encontrada'}), 404
    return jsonify({
        'ok': True,
        'enfermaria': row.to_dict(include_leitos=True),
        'leitos': list_leitos(enfermaria_id=eid),
    })


@nutricao.route('/nutricao/leitos')
def leitos():
    seed_nutricao()
    enf_id = request.args.get('enfermaria_id', type=int)
    return render_template(
        'nutricao_leitos.html',
        enfermarias=list_enfermarias(somente_ativas=False),
        enfermaria_id_inicial=enf_id,
        **active('cadastro_leitos')
    )


@nutricao.route('/nutricao/api/leitos', methods=['GET', 'POST'])
def api_leitos():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        try:
            enfermaria_id = int(d.get('enfermaria_id') or 0)
        except (TypeError, ValueError):
            enfermaria_id = 0
        nome = (d.get('nome') or d.get('nome_leito') or '').strip()
        if not enfermaria_id:
            return jsonify({'ok': False, 'error': 'Informe a enfermaria'}), 400
        enf = NutEnfermaria.query.get(enfermaria_id)
        if not enf:
            return jsonify({'ok': False, 'error': 'Enfermaria não encontrada'}), 404

        numero = d.get('numero')
        if numero in (None, ''):
            numero = d.get('numero_leito')
        try:
            numero = int(numero) if numero not in (None, '') else None
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Nº leito inválido'}), 400
        if numero is None:
            ultimo = (
                NutLeito.query
                .filter_by(enfermaria_id=enfermaria_id)
                .order_by(NutLeito.numero.desc())
                .first()
            )
            numero = (ultimo.numero + 1) if ultimo else 1
        if not nome:
            nome = str(numero).zfill(2)

        if NutLeito.query.filter_by(enfermaria_id=enfermaria_id, numero=numero).first():
            return jsonify({'ok': False, 'error': 'Já existe leito com este número nesta enfermaria'}), 400

        row = NutLeito(
            enfermaria_id=enfermaria_id,
            numero=numero,
            nome=nome,
            ativo=bool(d.get('ativo', True)),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'leito': row.to_dict(), 'enfermaria': enf.to_dict()})

    enfermaria_id = request.args.get('enfermaria_id', type=int)
    somente_ativos = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_leitos(enfermaria_id=enfermaria_id, somente_ativos=somente_ativos))


@nutricao.route('/nutricao/api/leitos/<int:lid>', methods=['PUT', 'DELETE'])
def api_leito_ops(lid):
    row = NutLeito.query.get(lid)
    if not row:
        return jsonify({'ok': False, 'error': 'Leito não encontrado'}), 404

    if request.method == 'DELETE':
        enf_id = row.enfermaria_id
        db.session.delete(row)
        db.session.commit()
        enf = NutEnfermaria.query.get(enf_id)
        return jsonify({'ok': True, 'enfermaria': enf.to_dict() if enf else None})

    d = request.get_json(force=True) or {}
    if 'nome' in d or 'nome_leito' in d:
        nome = (d.get('nome') if 'nome' in d else d.get('nome_leito') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do leito é obrigatório'}), 400
        row.nome = nome
    if 'numero' in d or 'numero_leito' in d:
        raw = d.get('numero') if 'numero' in d else d.get('numero_leito')
        try:
            numero = int(raw)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Nº leito inválido'}), 400
        outro = NutLeito.query.filter(
            NutLeito.enfermaria_id == row.enfermaria_id,
            NutLeito.numero == numero,
            NutLeito.id != lid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe leito com este número nesta enfermaria'}), 400
        row.numero = numero
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    if 'enfermaria_id' in d:
        try:
            nova_enf = int(d.get('enfermaria_id') or 0)
        except (TypeError, ValueError):
            nova_enf = 0
        if not NutEnfermaria.query.get(nova_enf):
            return jsonify({'ok': False, 'error': 'Enfermaria não encontrada'}), 404
        row.enfermaria_id = nova_enf
    db.session.commit()
    return jsonify({'ok': True, 'leito': row.to_dict()})


# ---- DIETAS ----
def _parse_precos_payload(d):
    """Extrai mapa de preços do JSON (precos / valores por tipo ou sigla)."""
    from nutricao_service import _normalize_precos_map
    raw = d.get('precos') or d.get('valores') or {}
    if isinstance(raw, dict) and raw:
        return _normalize_precos_map(raw)
    # aceita campos soltos: desjejum, colacao, ...
    soltos = {}
    for key in ('desjejum', 'colacao', 'colação', 'almoco', 'almoço', 'merenda', 'jantar', 'ceia',
                'DESJ', 'COL', 'ALM', 'MER', 'JAN', 'CEI',
                'DESJEJUM', 'COLAÇÃO', 'ALMOÇO', 'MERENDA', 'JANTAR', 'CEIA'):
        if key in d:
            soltos[key] = d.get(key)
    return _normalize_precos_map(soltos) if soltos else {}


@nutricao.route('/nutricao/dietas')
def dietas():
    seed_nutricao()
    from nutricao_service import list_tipos_refeicao, list_precos_dieta_tipo
    dietas_list = _list_dietas_db(somente_ativas=False)
    tipos = list_tipos_refeicao(somente_ativos=True)
    grupos = list_grupos_dieta(somente_ativos=True)
    # mapa dieta_id → {tipo_sigla: valor_empresa}
    precos_por_dieta = {}
    for p in list_precos_dieta_tipo(somente_ativas=False, somente_tipos_ativos=True):
        did = p.get('dieta_id')
        sigla = (p.get('tipo_sigla') or '').upper()
        if not did or not sigla:
            continue
        precos_por_dieta.setdefault(did, {})[sigla] = float(p.get('valor_empresa') or 0)
    return render_template(
        'nutricao_dietas.html',
        dietas=dietas_list,
        tipos=tipos,
        grupos=grupos,
        precos_por_dieta=precos_por_dieta,
        **active('cadastro_dietas')
    )


@nutricao.route('/nutricao/api/dietas', methods=['GET', 'POST'])
def api_dietas():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da dieta é obrigatório'}), 400
        categoria = (d.get('categoria') or 'basica').strip() or 'basica'
        grupo = (d.get('grupo') or '').strip().upper()
        precos = _parse_precos_payload(d)
        exists = NutDieta.query.filter_by(nome=nome).first()
        if exists:
            if 'ativo' in d:
                exists.ativo = bool(d.get('ativo'))
            else:
                exists.ativo = True
            exists.categoria = categoria
            if 'grupo' in d:
                exists.grupo = grupo
            if precos:
                ensure_precos_para_dieta(exists.id, aplicar_default=False, precos_map=precos, forcar=True)
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'dieta': exists.to_dict()})
        row = NutDieta(
            nome=nome,
            categoria=categoria,
            grupo=grupo,
            ativo=bool(d.get('ativo', True)),
        )
        db.session.add(row)
        db.session.flush()
        if precos:
            ensure_precos_para_dieta(row.id, aplicar_default=False, precos_map=precos, forcar=True)
        else:
            ensure_precos_para_dieta(row.id, aplicar_default=True)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'dieta': row.to_dict()})
    somente_ativas = str(request.args.get('ativas', '')).lower() in ('1', 'true', 'sim')
    return jsonify(_list_dietas_db(somente_ativas=somente_ativas))


@nutricao.route('/nutricao/api/dietas/<int:did>', methods=['PUT', 'DELETE'])
def api_dieta_ops(did):
    row = NutDieta.query.get(did)
    if not row:
        return jsonify({'ok': False, 'error': 'Dieta não encontrada'}), 404

    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da dieta é obrigatório'}), 400
        outro = NutDieta.query.filter(NutDieta.nome == nome, NutDieta.id != did).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe dieta com este nome'}), 400
        row.nome = nome
    if 'categoria' in d:
        row.categoria = (d.get('categoria') or 'basica').strip() or 'basica'
    if 'grupo' in d:
        row.grupo = (d.get('grupo') or '').strip().upper()
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    precos = _parse_precos_payload(d)
    if precos:
        ensure_precos_para_dieta(row.id, aplicar_default=False, precos_map=precos, forcar=True)
    db.session.commit()
    return jsonify({'ok': True, 'dieta': row.to_dict()})


# ---- GRUPOS DE DIETAS ----
@nutricao.route('/nutricao/grupos-dietas')
def grupos_dietas():
    seed_nutricao()
    return render_template(
        'nutricao_grupos_dietas.html',
        grupos=list_grupos_dieta(somente_ativos=False),
        **active('cadastro_grupos_dietas')
    )


@nutricao.route('/nutricao/api/grupos-dietas', methods=['GET', 'POST'])
def api_grupos_dietas():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do grupo é obrigatório'}), 400
        exists = NutGrupoDieta.query.filter(
            db.func.upper(NutGrupoDieta.nome) == nome
        ).first()
        try:
            ordem = int(d.get('ordem') or 0)
        except (TypeError, ValueError):
            ordem = 0
        if exists:
            exists.ativo = bool(d.get('ativo', True))
            if 'ordem' in d and ordem > 0:
                exists.ordem = ordem
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'grupo': exists.to_dict()})
        if ordem <= 0:
            last = NutGrupoDieta.query.order_by(NutGrupoDieta.ordem.desc()).first()
            ordem = (last.ordem + 10) if last else 10
        row = NutGrupoDieta(
            nome=nome,
            ordem=ordem,
            ativo=bool(d.get('ativo', True)),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'grupo': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_grupos_dieta(somente_ativos=somente))


@nutricao.route('/nutricao/api/grupos-dietas/<int:gid>', methods=['PUT', 'DELETE'])
def api_grupo_dieta_ops(gid):
    row = NutGrupoDieta.query.get(gid)
    if not row:
        return jsonify({'ok': False, 'error': 'Grupo não encontrado'}), 404

    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do grupo é obrigatório'}), 400
        outro = NutGrupoDieta.query.filter(
            db.func.upper(NutGrupoDieta.nome) == nome,
            NutGrupoDieta.id != gid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe grupo com este nome'}), 400
        antigo = (row.nome or '').strip().upper()
        row.nome = nome
        # Mantém dieta.grupo (string) alinhado para preços/mapa
        if antigo and antigo != nome:
            NutDieta.query.filter(
                db.func.upper(NutDieta.grupo) == antigo
            ).update({NutDieta.grupo: nome}, synchronize_session=False)
    if 'ordem' in d:
        try:
            row.ordem = int(d.get('ordem') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Ordem inválida'}), 400
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    db.session.commit()
    return jsonify({'ok': True, 'grupo': row.to_dict()})


# ---- TIPOS DE REFEIÇÃO ----
@nutricao.route('/nutricao/tipos-refeicao')
def tipos_refeicao():
    seed_nutricao()
    return render_template(
        'nutricao_tipos_refeicao.html',
        tipos=list_tipos_refeicao(somente_ativos=False),
        **active('cadastro_tipos_refeicao')
    )


@nutricao.route('/nutricao/api/tipos-refeicao', methods=['GET', 'POST'])
def api_tipos_refeicao():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip().upper()
        sigla = (d.get('sigla') or '').strip().upper()[:10]
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do tipo é obrigatório'}), 400
        if not sigla:
            sigla = nome[:4]
        exists = NutTipoRefeicao.query.filter(
            db.func.upper(NutTipoRefeicao.nome) == nome
        ).first()
        hora_limite = normalizar_hora_limite(d.get('hora_limite'))
        if exists:
            exists.ativo = bool(d.get('ativo', True))
            exists.sigla = sigla
            exists.hora_limite = hora_limite
            if 'ordem' in d:
                try:
                    exists.ordem = int(d.get('ordem') or 0)
                except (TypeError, ValueError):
                    pass
            db.session.flush()
            _seed_precos_dieta_tipo()
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'tipo': exists.to_dict()})
        if NutTipoRefeicao.query.filter(db.func.upper(NutTipoRefeicao.sigla) == sigla).first():
            return jsonify({'ok': False, 'error': 'Já existe tipo com esta sigla'}), 400
        try:
            ordem = int(d.get('ordem') or 0)
        except (TypeError, ValueError):
            ordem = 0
        if ordem <= 0:
            last = NutTipoRefeicao.query.order_by(NutTipoRefeicao.ordem.desc()).first()
            ordem = (last.ordem + 10) if last else 10
        row = NutTipoRefeicao(
            nome=nome,
            sigla=sigla,
            ordem=ordem,
            hora_limite=hora_limite,
            ativo=bool(d.get('ativo', True)),
        )
        db.session.add(row)
        db.session.flush()
        _seed_precos_dieta_tipo()
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'tipo': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_tipos_refeicao(somente_ativos=somente))


@nutricao.route('/nutricao/api/tipos-refeicao/<int:tid>', methods=['PUT', 'DELETE'])
def api_tipo_refeicao_ops(tid):
    row = NutTipoRefeicao.query.get(tid)
    if not row:
        return jsonify({'ok': False, 'error': 'Tipo de refeição não encontrado'}), 404

    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do tipo é obrigatório'}), 400
        outro = NutTipoRefeicao.query.filter(
            db.func.upper(NutTipoRefeicao.nome) == nome,
            NutTipoRefeicao.id != tid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe tipo com este nome'}), 400
        row.nome = nome
    if 'sigla' in d:
        sigla = (d.get('sigla') or '').strip().upper()[:10]
        if not sigla:
            return jsonify({'ok': False, 'error': 'Sigla é obrigatória'}), 400
        outro = NutTipoRefeicao.query.filter(
            db.func.upper(NutTipoRefeicao.sigla) == sigla,
            NutTipoRefeicao.id != tid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe tipo com esta sigla'}), 400
        row.sigla = sigla
    if 'ordem' in d:
        try:
            row.ordem = int(d.get('ordem') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Ordem inválida'}), 400
    if 'hora_limite' in d:
        row.hora_limite = normalizar_hora_limite(d.get('hora_limite'))
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    db.session.commit()
    return jsonify({'ok': True, 'tipo': row.to_dict()})


# ---- CARDÁPIOS ----
def _resolve_cardapio_dieta(d):
    """Resolve dieta_id + nome. Hook futuro: join NutPrecoDietaTipo via dieta_id × hr_*."""
    dieta_id = d.get('dieta_id')
    dieta_nome = (d.get('dieta') or '').strip() or None
    try:
        dieta_id = int(dieta_id) if dieta_id not in (None, '', 0, '0') else None
    except (TypeError, ValueError):
        dieta_id = None
    row_dieta = NutDieta.query.get(dieta_id) if dieta_id else None
    if row_dieta:
        return row_dieta.id, row_dieta.nome
    if dieta_nome:
        row_dieta = NutDieta.query.filter_by(nome=dieta_nome).first()
        if row_dieta:
            return row_dieta.id, row_dieta.nome
        return None, dieta_nome
    return None, None


def _cardapio_from_payload(d, row=None):
    row = row or NutCardapio()
    row.tipo = (d.get('tipo') or 'grandes').strip()
    row.grupo_cardapio = (d.get('grupo_cardapio') or 'PRINCIPAL').strip()
    try:
        row.dia_mes = int(d.get('dia_mes') or 1)
    except (TypeError, ValueError):
        row.dia_mes = 1
    row.dia_semana = (d.get('dia_semana') or '').strip() or None
    dieta_id, dieta_nome = _resolve_cardapio_dieta(d)
    row.dieta_id = dieta_id
    row.dieta = dieta_nome
    for hr in ('hr_desjejum', 'hr_colacao', 'hr_almoco', 'hr_merenda', 'hr_jantar', 'hr_ceia'):
        setattr(row, hr, bool(d.get(hr)))
    row.set_itens(d.get('itens') or {})
    try:
        row.vet = float(d.get('vet') or 0)
    except (TypeError, ValueError):
        row.vet = 0
    try:
        row.custo = float(d.get('custo') or 0)
    except (TypeError, ValueError):
        row.custo = 0
    row.organizar_por = (d.get('organizar_por') or 'Ord, Dieta, Horário').strip()
    row.usuario_alteracao = (d.get('usuario_alteracao') or session.get('usuario_nome') or 'sistema')[:80]
    row.data_alteracao = datetime.utcnow()
    row.ativo = bool(d.get('ativo', True))
    return row


@nutricao.route('/nutricao/cardapios')
def cardapios():
    seed_nutricao()
    dieta_id = request.args.get('dieta_id', type=int)
    dieta_sel = NutDieta.query.get(dieta_id) if dieta_id else None
    dietas_list = _list_dietas_db(somente_ativas=False)
    return render_template(
        'nutricao_cardapios.html',
        cardapios=list_cardapios(dieta_id=dieta_id) if dieta_id else list_cardapios(),
        dietas=dietas_list,
        dieta_sel=dieta_sel.to_dict() if dieta_sel else None,
        opcoes=CARDAPIO_OPCOES,
        **active('cadastro_cardapios')
    )


@nutricao.route('/nutricao/api/cardapios', methods=['GET', 'POST'])
def api_cardapios():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        dieta_id, dieta_nome = _resolve_cardapio_dieta(d)
        if not dieta_id and not dieta_nome:
            return jsonify({'ok': False, 'error': 'Informe a dieta'}), 400
        d['dieta_id'] = dieta_id
        d['dieta'] = dieta_nome
        row = _cardapio_from_payload(d)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'cardapio': row.to_dict()})
    tipo = (request.args.get('tipo') or '').strip() or None
    dieta_id = request.args.get('dieta_id', type=int)
    return jsonify(list_cardapios(tipo=tipo, dieta_id=dieta_id))


@nutricao.route('/nutricao/api/cardapios/<int:cid>', methods=['PUT', 'DELETE'])
def api_cardapio_ops(cid):
    row = NutCardapio.query.get(cid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Cardápio não encontrado'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    _cardapio_from_payload(d, row)
    db.session.commit()
    return jsonify({'ok': True, 'cardapio': row.to_dict()})


# ---- CADASTRO NUTRICIONAL ----
def _fnum(v, default=0.0):
    try:
        if v in (None, ''):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _alimento_from_payload(d, row=None, tabela_id=None):
    row = row or NutAlimento()
    if tabela_id is not None:
        row.tabela_id = tabela_id
    elif d.get('tabela_id'):
        row.tabela_id = int(d['tabela_id'])
    nome = (d.get('nome') or '').strip().upper()
    if nome:
        row.nome = nome
    row.cal_carboidratos = _fnum(d.get('cal_carboidratos'))
    row.cal_gordura = _fnum(d.get('cal_gordura'))
    row.cal_proteina = _fnum(d.get('cal_proteina'))
    cal_total = d.get('cal_total')
    if cal_total in (None, ''):
        row.cal_total = row.cal_carboidratos + row.cal_gordura + row.cal_proteina
    else:
        row.cal_total = _fnum(cal_total)
    row.qtd_carboidratos = _fnum(d.get('qtd_carboidratos'))
    row.qtd_gordura = _fnum(d.get('qtd_gordura'))
    row.qtd_proteina = _fnum(d.get('qtd_proteina'))
    row.ref_consumo = (d.get('ref_consumo') or '').strip() or None
    row.coeficiente_npu = _fnum(d.get('coeficiente_npu'))
    if 'gluten' in d:
        row.gluten = bool(d.get('gluten'))
    if 'fenilalanina' in d:
        row.fenilalanina = bool(d.get('fenilalanina'))
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    row.ultima_alteracao = datetime.utcnow()
    return row


def _sync_nutrientes(alimento, nutrientes):
    NutAlimentoNutriente.query.filter_by(alimento_id=alimento.id).delete()
    for n in (nutrientes or []):
        nome = (n.get('nutriente') or '').strip()
        if not nome:
            continue
        db.session.add(NutAlimentoNutriente(
            alimento_id=alimento.id,
            nutriente=nome,
            quantidade=_fnum(n.get('quantidade')),
            unidade=(n.get('unidade') or 'g').strip() or 'g',
            fator=_fnum(n.get('fator'), 1),
        ))


@nutricao.route('/nutricao/nutricional')
def nutricional():
    seed_nutricao()
    tabelas = list_tabelas_nutrientes(somente_ativas=False)
    # Prefer active (official) table as default
    ativas = [t for t in tabelas if t.get('ativo')]
    tabela_id = request.args.get('tabela_id', type=int)
    if not tabela_id and ativas:
        tabela_id = ativas[0]['id']
    elif not tabela_id and tabelas:
        tabela_id = tabelas[0]['id']
    # Omit nested nutrients in list payload (FDC tables are large); load on demand
    alimentos = (
        list_alimentos(tabela_id=tabela_id, somente_ativas=False, include_nutrientes=False)
        if tabela_id else []
    )
    return render_template(
        'nutricao_nutricional.html',
        tabelas=tabelas,
        alimentos=alimentos,
        tabela_id=tabela_id,
        **active('cadastro_nutricional')
    )


@nutricao.route('/nutricao/api/tabelas-nutrientes', methods=['GET', 'POST'])
def api_tabelas_nutrientes():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da tabela é obrigatório'}), 400
        exists = NutTabelaNutrientes.query.filter_by(nome=nome).first()
        if exists:
            if 'ativo' in d:
                exists.ativo = bool(d.get('ativo'))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'tabela': exists.to_dict()})
        row = NutTabelaNutrientes(nome=nome, ativo=bool(d.get('ativo', True)))
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'tabela': row.to_dict()})
    return jsonify(list_tabelas_nutrientes(somente_ativas=False))


@nutricao.route('/nutricao/api/tabelas-nutrientes/<int:tid>', methods=['PUT', 'DELETE'])
def api_tabela_nutrientes_ops(tid):
    row = NutTabelaNutrientes.query.get(tid)
    if not row:
        return jsonify({'ok': False, 'error': 'Tabela não encontrada'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da tabela é obrigatório'}), 400
        outro = NutTabelaNutrientes.query.filter(
            NutTabelaNutrientes.nome == nome, NutTabelaNutrientes.id != tid
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe tabela com este nome'}), 400
        row.nome = nome
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    db.session.commit()
    return jsonify({'ok': True, 'tabela': row.to_dict()})


@nutricao.route('/nutricao/api/tabelas-nutrientes/import-fdc', methods=['POST'])
def api_import_fdc_tabela():
    """Importa ZIP/JSON FoodData Central Foundation Foods (multipart file ou path)."""
    import io
    from nutricao_fdc_import import DEFAULT_TABELA_NOME

    seed_nutricao()
    tabela_nome = (request.form.get('tabela_nome') or request.args.get('tabela_nome') or '').strip()
    set_official = str(request.form.get('set_official', request.args.get('set_official', '1'))).lower() not in (
        '0', 'false', 'no', 'off'
    )
    path = (request.form.get('path') or request.args.get('path') or '').strip()
    upload = request.files.get('file') or request.files.get('arquivo')
    kwargs = {
        'tabela_nome': tabela_nome or DEFAULT_TABELA_NOME,
        'set_official': set_official,
    }
    try:
        if upload and upload.filename:
            raw = upload.read()
            if not raw:
                return jsonify({'ok': False, 'error': 'Arquivo vazio'}), 400
            buf = io.BytesIO(raw)
            buf.name = upload.filename
            result = import_tabela_fdc(buf, **kwargs)
        elif path:
            result = import_tabela_fdc(path, **kwargs)
        else:
            return jsonify({
                'ok': False,
                'error': 'Envie um arquivo ZIP/JSON (campo file) ou informe path no servidor',
            }), 400
        return jsonify(result)
    except FileNotFoundError as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': f'Falha na importação: {e}'}), 500


@nutricao.route('/nutricao/api/alimentos', methods=['GET', 'POST'])
def api_alimentos():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        try:
            tabela_id = int(d.get('tabela_id') or 0)
        except (TypeError, ValueError):
            tabela_id = 0
        if not NutTabelaNutrientes.query.get(tabela_id):
            return jsonify({'ok': False, 'error': 'Tabela não encontrada'}), 404
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do alimento é obrigatório'}), 400
        row = _alimento_from_payload(d, tabela_id=tabela_id)
        db.session.add(row)
        db.session.flush()
        _sync_nutrientes(row, d.get('nutrientes'))
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'alimento': row.to_dict()})
    tabela_id = request.args.get('tabela_id', type=int)
    include_nuts = str(request.args.get('include_nutrientes', '1')).lower() not in (
        '0', 'false', 'no', 'off'
    )
    return jsonify(list_alimentos(
        tabela_id=tabela_id,
        somente_ativas=False,
        include_nutrientes=include_nuts,
    ))


@nutricao.route('/nutricao/api/alimentos/<int:aid>', methods=['GET', 'PUT', 'DELETE'])
def api_alimento_ops(aid):
    row = NutAlimento.query.get(aid)
    if not row:
        return jsonify({'ok': False, 'error': 'Alimento não encontrado'}), 404
    if request.method == 'GET':
        return jsonify(row.to_dict())
    if request.method == 'DELETE':
        row.ativo = False
        row.ultima_alteracao = datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do alimento é obrigatório'}), 400
        row.nome = nome
    _alimento_from_payload(d, row)
    if 'nutrientes' in d:
        _sync_nutrientes(row, d.get('nutrientes'))
    db.session.commit()
    return jsonify({'ok': True, 'alimento': row.to_dict()})


# ---- PRATOS DIETAS LÍQUIDAS ----
def _prato_liquido_from_payload(d, row=None):
    row = row or NutPratoLiquido()
    nome = (d.get('nome') or '').strip().upper()
    if nome:
        row.nome = nome
    for g in ('principal', 'sobremesa', 'outros', 'bebida', 'gelado', 'extra'):
        key = f'grupo_{g}'
        if key in d:
            setattr(row, key, bool(d.get(key)))
    if 'fator_conv_tot' in d:
        try:
            row.fator_conv_tot = float(d.get('fator_conv_tot') if d.get('fator_conv_tot') not in (None, '') else 1)
        except (TypeError, ValueError):
            row.fator_conv_tot = 1
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    row.data_alteracao = datetime.utcnow()
    return row


@nutricao.route('/nutricao/pratos-liquidos')
def pratos_liquidos():
    seed_nutricao()
    return render_template(
        'nutricao_pratos_liquidos.html',
        pratos=list_pratos_liquidos(somente_ativos=False),
        **active('cadastro_pratos_liquidos')
    )


@nutricao.route('/nutricao/api/pratos-liquidos', methods=['GET', 'POST'])
def api_pratos_liquidos():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do prato é obrigatório'}), 400
        exists = NutPratoLiquido.query.filter_by(nome=nome).first()
        if exists:
            _prato_liquido_from_payload(d, exists)
            exists.ativo = bool(d.get('ativo', True))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'prato': exists.to_dict()})
        row = _prato_liquido_from_payload(d)
        if not row.nome:
            row.nome = nome
        if 'ativo' not in d:
            row.ativo = True
        if 'fator_conv_tot' not in d:
            row.fator_conv_tot = 1
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'prato': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_pratos_liquidos(somente_ativos=somente))


@nutricao.route('/nutricao/api/pratos-liquidos/<int:pid>', methods=['PUT', 'DELETE'])
def api_prato_liquido_ops(pid):
    row = NutPratoLiquido.query.get(pid)
    if not row:
        return jsonify({'ok': False, 'error': 'Prato não encontrado'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        row.data_alteracao = datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do prato é obrigatório'}), 400
        outro = NutPratoLiquido.query.filter(
            NutPratoLiquido.nome == nome, NutPratoLiquido.id != pid
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe prato com este nome'}), 400
        row.nome = nome
    _prato_liquido_from_payload(d, row)
    db.session.commit()
    return jsonify({'ok': True, 'prato': row.to_dict()})


# ---- CADASTRO DE PRODUTOS ----
def _fnum_prod(v, default=0.0):
    try:
        if v in (None, ''):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _produto_from_payload(d, row=None):
    row = row or NutProduto()
    if d.get('estoque_id'):
        row.estoque_id = int(d['estoque_id'])
    if d.get('grupo_id'):
        row.grupo_id = int(d['grupo_id'])
    if 'codigo' in d:
        row.codigo = (d.get('codigo') or '').strip().upper()
    if 'descricao' in d:
        row.descricao = (d.get('descricao') or '').strip().upper()
    for fld in ('quantidade', 'preco_medio', 'ult_preco', 'quant_min', 'quant_max', 'quant_liq'):
        if fld in d:
            setattr(row, fld, _fnum_prod(d.get(fld)))
    if 'unidade' in d:
        row.unidade = (d.get('unidade') or 'UN').strip().upper() or 'UN'
    if 'un_liq' in d:
        row.un_liq = (d.get('un_liq') or 'NC').strip().upper() or 'NC'
    if 'fc' in d:
        row.fc = bool(d.get('fc'))
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    row.data_alteracao = datetime.utcnow()
    return row


@nutricao.route('/nutricao/produtos')
def produtos():
    seed_nutricao()
    estoques = list_estoques(somente_ativos=False)
    estoque_id = request.args.get('estoque_id', type=int)
    if not estoque_id and estoques:
        matriz = next((e for e in estoques if e['nome'] == 'MATRIZ'), None)
        estoque_id = (matriz or estoques[0])['id']
    grupo_id = request.args.get('grupo_id', type=int)
    return render_template(
        'nutricao_produtos.html',
        estoques=estoques,
        unidades=list_unidades(somente_ativas=False),
        grupos=list_grupos_produto(somente_ativos=False),
        produtos=list_produtos(estoque_id=estoque_id, grupo_id=grupo_id, somente_ativos=False),
        estoque_id=estoque_id,
        grupo_id=grupo_id,
        **active('cadastro_produtos')
    )


@nutricao.route('/nutricao/api/estoques', methods=['GET', 'POST'])
def api_estoques():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do estoque é obrigatório'}), 400
        exists = NutEstoqueLocal.query.filter_by(nome=nome).first()
        if exists:
            exists.ativo = bool(d.get('ativo', True))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'estoque': exists.to_dict()})
        row = NutEstoqueLocal(nome=nome, ativo=bool(d.get('ativo', True)))
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'estoque': row.to_dict()})
    return jsonify(list_estoques(somente_ativos=False))


def _unidade_from_payload(d, row=None):
    row = row or NutUnidadeMedida()
    if 'codigo' in d:
        row.codigo = (d.get('codigo') or '').strip().upper()
    if 'descricao' in d:
        row.descricao = (d.get('descricao') or '').strip().upper() or None
    if 'unid_conversao' in d:
        row.unid_conversao = (d.get('unid_conversao') or '').strip().upper() or None
    if 'valor_conversao' in d:
        row.valor_conversao = _fnum_prod(d.get('valor_conversao'), 0.0)
    for fld in ('flag_nutrientes', 'flag_uma', 'flag_estoque', 'flag_pratos', 'ativo'):
        if fld in d:
            setattr(row, fld, bool(d.get(fld)))
    return row


@nutricao.route('/nutricao/api/unidades', methods=['GET', 'POST'])
def api_unidades():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        if isinstance(d.get('items'), list):
            salvos = []
            for item in d['items']:
                codigo = (item.get('codigo') or '').strip().upper()
                if not codigo:
                    continue
                exists = None
                uid = item.get('id')
                if uid:
                    exists = NutUnidadeMedida.query.get(int(uid))
                if not exists:
                    exists = NutUnidadeMedida.query.filter_by(codigo=codigo).first()
                if exists:
                    outro = NutUnidadeMedida.query.filter(
                        NutUnidadeMedida.codigo == codigo,
                        NutUnidadeMedida.id != exists.id,
                    ).first()
                    if outro:
                        return jsonify({'ok': False, 'error': f'Código já existe: {codigo}'}), 400
                    _unidade_from_payload(item, exists)
                    salvos.append(exists.to_dict())
                else:
                    row = _unidade_from_payload(item)
                    if 'ativo' not in item:
                        row.ativo = True
                    db.session.add(row)
                    db.session.flush()
                    salvos.append(row.to_dict())
            db.session.commit()
            return jsonify({'ok': True, 'unidades': salvos})
        codigo = (d.get('codigo') or '').strip().upper()
        if not codigo:
            return jsonify({'ok': False, 'error': 'Código da unidade é obrigatório'}), 400
        exists = NutUnidadeMedida.query.filter_by(codigo=codigo).first()
        if exists:
            _unidade_from_payload(d, exists)
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'unidade': exists.to_dict()})
        row = _unidade_from_payload(d)
        if 'ativo' not in d:
            row.ativo = True
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'unidade': row.to_dict()})
    return jsonify(list_unidades(somente_ativas=False))


@nutricao.route('/nutricao/api/unidades/<int:uid>', methods=['PUT', 'DELETE'])
def api_unidade_ops(uid):
    row = NutUnidadeMedida.query.get(uid)
    if not row:
        return jsonify({'ok': False, 'error': 'Unidade não encontrada'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'codigo' in d:
        codigo = (d.get('codigo') or '').strip().upper()
        if not codigo:
            return jsonify({'ok': False, 'error': 'Código obrigatório'}), 400
        outro = NutUnidadeMedida.query.filter(
            NutUnidadeMedida.codigo == codigo, NutUnidadeMedida.id != uid
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Código já existe'}), 400
    _unidade_from_payload(d, row)
    db.session.commit()
    return jsonify({'ok': True, 'unidade': row.to_dict()})


@nutricao.route('/nutricao/api/grupos-produto', methods=['GET', 'POST'])
def api_grupos_produto():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do grupo é obrigatório'}), 400
        exists = NutGrupoProduto.query.filter_by(nome=nome).first()
        if exists:
            if 'ativo' in d:
                exists.ativo = bool(d.get('ativo'))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'grupo': exists.to_dict()})
        row = NutGrupoProduto(nome=nome, ativo=bool(d.get('ativo', True)))
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'grupo': row.to_dict()})
    return jsonify(list_grupos_produto(somente_ativos=False))


@nutricao.route('/nutricao/api/grupos-produto/<int:gid>', methods=['PUT', 'DELETE'])
def api_grupo_produto_ops(gid):
    row = NutGrupoProduto.query.get(gid)
    if not row:
        return jsonify({'ok': False, 'error': 'Grupo não encontrado'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome obrigatório'}), 400
        outro = NutGrupoProduto.query.filter(
            NutGrupoProduto.nome == nome, NutGrupoProduto.id != gid
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Grupo já existe'}), 400
        row.nome = nome
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    db.session.commit()
    return jsonify({'ok': True, 'grupo': row.to_dict()})


@nutricao.route('/nutricao/api/produtos', methods=['GET', 'POST'])
def api_produtos_cadastro():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        try:
            estoque_id = int(d.get('estoque_id') or 0)
            grupo_id = int(d.get('grupo_id') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Estoque/grupo inválidos'}), 400
        if not NutEstoqueLocal.query.get(estoque_id):
            return jsonify({'ok': False, 'error': 'Estoque não encontrado'}), 404
        if not NutGrupoProduto.query.get(grupo_id):
            return jsonify({'ok': False, 'error': 'Grupo não encontrado'}), 404
        codigo = (d.get('codigo') or '').strip().upper()
        descricao = (d.get('descricao') or '').strip().upper()
        if not codigo or not descricao:
            return jsonify({'ok': False, 'error': 'Código e descrição são obrigatórios'}), 400
        exists = NutProduto.query.filter_by(estoque_id=estoque_id, codigo=codigo).first()
        if exists:
            _produto_from_payload(d, exists)
            exists.ativo = bool(d.get('ativo', True))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'produto': exists.to_dict()})
        row = _produto_from_payload(d)
        row.estoque_id = estoque_id
        row.grupo_id = grupo_id
        row.codigo = codigo
        row.descricao = descricao
        if 'ativo' not in d:
            row.ativo = True
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'produto': row.to_dict()})
    estoque_id = request.args.get('estoque_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    return jsonify(list_produtos(estoque_id=estoque_id, grupo_id=grupo_id, somente_ativos=False))


@nutricao.route('/nutricao/api/produtos/<int:pid>', methods=['PUT', 'DELETE'])
def api_produto_cadastro_ops(pid):
    row = NutProduto.query.get(pid)
    if not row:
        return jsonify({'ok': False, 'error': 'Produto não encontrado'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        row.data_alteracao = datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'codigo' in d:
        codigo = (d.get('codigo') or '').strip().upper()
        if not codigo:
            return jsonify({'ok': False, 'error': 'Código obrigatório'}), 400
        outro = NutProduto.query.filter(
            NutProduto.estoque_id == row.estoque_id,
            NutProduto.codigo == codigo,
            NutProduto.id != pid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Código já existe neste estoque'}), 400
        row.codigo = codigo
    _produto_from_payload(d, row)
    db.session.commit()
    return jsonify({'ok': True, 'produto': row.to_dict()})


# ---- CADASTRO DE FORNECEDORES ----
def _fornecedor_from_payload(d, row=None):
    row = row or NutFornecedor()
    if 'nome' in d:
        row.nome = (d.get('nome') or '').strip().upper()
    for fld in ('endereco', 'bairro', 'municipio', 'observacao'):
        if fld in d:
            val = (d.get(fld) or '').strip().upper()
            setattr(row, fld, val or None)
    for fld in ('cep', 'cnpj', 'inscricao_estadual', 'telefone', 'email', 'site'):
        if fld in d:
            val = (d.get(fld) or '').strip()
            setattr(row, fld, val or None)
    if 'estado' in d:
        row.estado = ((d.get('estado') or '').strip().upper()[:2] or None)
    if 'faturamento_dias' in d:
        try:
            row.faturamento_dias = int(d.get('faturamento_dias') or 0)
        except (TypeError, ValueError):
            row.faturamento_dias = 0
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    row.data_alteracao = datetime.utcnow()
    return row


@nutricao.route('/nutricao/fornecedores')
def fornecedores():
    seed_nutricao()
    return render_template(
        'nutricao_fornecedores.html',
        fornecedores=list_fornecedores(somente_ativos=False),
        estados=ESTADOS_BR,
        **active('cadastro_fornecedores')
    )


@nutricao.route('/nutricao/api/fornecedores', methods=['GET', 'POST'])
def api_fornecedores():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do fornecedor é obrigatório'}), 400
        row = _fornecedor_from_payload(d)
        row.nome = nome
        if 'ativo' not in d:
            row.ativo = True
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'fornecedor': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_fornecedores(somente_ativos=somente))


@nutricao.route('/nutricao/api/fornecedores/<int:fid>', methods=['PUT', 'DELETE'])
def api_fornecedor_ops(fid):
    row = NutFornecedor.query.get(fid)
    if not row:
        return jsonify({'ok': False, 'error': 'Fornecedor não encontrado'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        row.data_alteracao = datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome obrigatório'}), 400
        row.nome = nome
    _fornecedor_from_payload(d, row)
    db.session.commit()
    return jsonify({'ok': True, 'fornecedor': row.to_dict()})


# ---- CADASTRO DE ETIQUETAS ----
def _fnum_eti(v, default=0.0):
    try:
        if v in (None, ''):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _etiqueta_from_payload(d, row=None):
    row = row or NutEtiqueta()
    if 'nome' in d:
        row.nome = (d.get('nome') or '').strip()
    if 'ativa' in d:
        row.ativa = bool(d.get('ativa'))
    if 'tamanho_folha' in d:
        row.tamanho_folha = (d.get('tamanho_folha') or 'carta').strip().lower()
    if 'folha_altura_mm' in d:
        row.folha_altura_mm = _fnum_eti(d.get('folha_altura_mm'))
    if 'folha_largura_mm' in d:
        row.folha_largura_mm = _fnum_eti(d.get('folha_largura_mm'))
    if 'orientacao' in d:
        row.orientacao = (d.get('orientacao') or 'retrato').strip().lower()
    for fld in ('margem_esquerda', 'margem_direita', 'margem_superior', 'margem_inferior',
                'dist_colunas_mm', 'altura_etiqueta_mm'):
        if fld in d:
            setattr(row, fld, _fnum_eti(d.get(fld)))
    if 'num_colunas' in d:
        try:
            row.num_colunas = max(1, int(d.get('num_colunas') or 1))
        except (TypeError, ValueError):
            row.num_colunas = 1
    if 'tamanho_fonte' in d:
        try:
            row.tamanho_fonte = max(1, int(d.get('tamanho_fonte') or 7))
        except (TypeError, ValueError):
            row.tamanho_fonte = 7
    row.data_alteracao = datetime.utcnow()
    return row


def _sync_etiqueta_campos(etiqueta, campos):
    NutEtiquetaCampo.query.filter_by(etiqueta_id=etiqueta.id).delete()
    for c in (campos or []):
        nome = (c.get('nome') or '').strip().upper()
        if not nome:
            continue
        tipo = ((c.get('tipo') or 'D').strip().upper()[:1] or 'D')
        if tipo not in ('D', 'F'):
            tipo = 'D'
        db.session.add(NutEtiquetaCampo(
            etiqueta_id=etiqueta.id,
            tipo=tipo,
            nome=nome,
            texto=(c.get('texto') or '').strip() or None,
        ))


@nutricao.route('/nutricao/etiquetas')
def etiquetas():
    seed_nutricao()
    return render_template(
        'nutricao_etiquetas.html',
        etiquetas=list_etiquetas(somente_ativas=False),
        **active('cadastro_etiquetas')
    )


@nutricao.route('/nutricao/impressao-etiquetas')
def impressao_etiquetas():
    seed_nutricao()
    modelos = list_modelos_etiqueta_impressao()
    return render_template(
        'nutricao_impressao_etiquetas.html',
        clinicas=_list_clinicas_db(somente_ativas=False),
        enfermarias=list_enfermarias(somente_ativas=True),
        modelos=modelos,
        data_padrao=date.today().isoformat(),
        **active('impressao_etiquetas')
    )


@nutricao.route('/nutricao/impressao-etiquetas/imprimir')
def impressao_etiquetas_imprimir():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    horario = (request.args.get('horario') or 'desjejum').strip()
    modo = (request.args.get('modo') or 'mapa').strip()
    imprimir_por = (request.args.get('imprimir_por') or 'grupo_clinica').strip()
    filtro_id = request.args.get('filtro_id', type=int)
    filtro_nome = (request.args.get('filtro_nome') or '').strip() or None
    ordenar = (request.args.get('ordenar') or 'grupo_dieta_data').strip()
    incluir_enfermaria = str(request.args.get('incluir_enfermaria', '')).lower() in ('1', 'true', 'sim')
    somente_alteradas = str(request.args.get('somente_alteradas', '')).lower() in ('1', 'true', 'sim')
    alteradas_desde = (request.args.get('alteradas_desde') or '').strip() or None
    modelo_id = (request.args.get('modelo') or '6080').strip()
    seq_inicio = request.args.get('seq_inicio', type=int) or 1

    if not filtro_nome and filtro_id and imprimir_por in ('grupo_clinica', 'clinica'):
        cli = NutClinica.query.get(int(filtro_id))
        if cli:
            filtro_nome = cli.nome
    if not filtro_nome and filtro_id and imprimir_por == 'enfermaria':
        enf = NutEnfermaria.query.get(int(filtro_id))
        if enf:
            filtro_nome = enf.nome

    try:
        _seed_faturamento_demo(data_ref, data_ref)
    except Exception:
        garantir_mapa_do_dia(data_ref)

    rel = gerar_impressao_etiquetas(
        data_ref=data_ref,
        horario=horario,
        modo=modo,
        imprimir_por=imprimir_por,
        filtro_id=filtro_id,
        filtro_nome=filtro_nome,
        ordenar=ordenar,
        incluir_enfermaria=incluir_enfermaria,
        somente_alteradas=somente_alteradas,
        alteradas_desde=alteradas_desde,
        modelo_id=modelo_id,
        seq_inicio=seq_inicio,
    )
    return render_template(
        'nutricao_impressao_etiquetas_print.html',
        r=rel,
        **active('impressao_etiquetas')
    )


@nutricao.route('/nutricao/api/etiquetas', methods=['GET', 'POST'])
def api_etiquetas():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da etiqueta é obrigatório'}), 400
        exists = NutEtiqueta.query.filter_by(nome=nome).first()
        if exists:
            _etiqueta_from_payload(d, exists)
            if 'campos' in d:
                _sync_etiqueta_campos(exists, d.get('campos'))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'etiqueta': exists.to_dict()})
        row = _etiqueta_from_payload(d)
        row.nome = nome
        if 'ativa' not in d:
            row.ativa = True
        db.session.add(row)
        db.session.flush()
        _sync_etiqueta_campos(row, d.get('campos'))
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'etiqueta': row.to_dict()})
    return jsonify(list_etiquetas(somente_ativas=False))


@nutricao.route('/nutricao/api/etiquetas/<int:eid>', methods=['PUT', 'DELETE'])
def api_etiqueta_ops(eid):
    row = NutEtiqueta.query.get(eid)
    if not row:
        return jsonify({'ok': False, 'error': 'Etiqueta não encontrada'}), 404
    if request.method == 'DELETE':
        row.ativa = False
        row.data_alteracao = datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome obrigatório'}), 400
        outro = NutEtiqueta.query.filter(NutEtiqueta.nome == nome, NutEtiqueta.id != eid).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe etiqueta com este nome'}), 400
        row.nome = nome
    _etiqueta_from_payload(d, row)
    if 'campos' in d:
        _sync_etiqueta_campos(row, d.get('campos'))
    db.session.commit()
    return jsonify({'ok': True, 'etiqueta': row.to_dict()})


# ---- PREÇOS DAS REFEIÇÕES (Dieta × Tipo) ----
@nutricao.route('/nutricao/precos-refeicoes')
def precos_refeicoes():
    seed_nutricao()
    matriz = matriz_precos_dieta_tipo(somente_ativas=True, somente_tipos_ativos=True)
    return render_template(
        'nutricao_precos_refeicoes.html',
        tipos=matriz['tipos'],
        linhas=matriz['linhas'],
        dietas=_list_dietas_db(somente_ativas=True),
        **active('cadastro_precos_refeicoes')
    )


def _parse_money(val, fallback=0.0):
    if val in (None, ''):
        return float(fallback)
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(' ', '').replace(',', '.')
    return float(s)


@nutricao.route('/nutricao/api/precos-refeicoes', methods=['GET', 'PUT'])
def api_precos_refeicoes():
    seed_nutricao()
    if request.method == 'GET':
        return jsonify(matriz_precos_dieta_tipo(
            somente_ativas=str(request.args.get('ativas', '1')).lower() not in ('0', 'false', 'nao', 'não'),
            somente_tipos_ativos=True,
        ))

    d = request.get_json(force=True) or {}
    itens = d.get('itens') or d.get('celulas') or d.get('precos') or []
    if not isinstance(itens, list):
        return jsonify({'ok': False, 'error': 'Lista de preços inválida'}), 400

    def _parse_valor(item, *keys, fallback=0.0):
        for k in keys:
            if k in item and item.get(k) not in (None, ''):
                return _parse_money(item.get(k), fallback)
        return float(fallback)

    atualizados = 0
    for item in itens:
        if not isinstance(item, dict):
            continue
        row = None
        pid = item.get('id')
        if pid is not None:
            try:
                row = NutPrecoDietaTipo.query.get(int(pid))
            except (TypeError, ValueError):
                row = None
        if not row:
            try:
                dieta_id = int(item.get('dieta_id'))
                tipo_id = int(item.get('tipo_refeicao_id') or item.get('tipo_id'))
            except (TypeError, ValueError):
                continue
            row = NutPrecoDietaTipo.query.filter_by(
                dieta_id=dieta_id, tipo_refeicao_id=tipo_id
            ).first()
            if not row:
                if not NutDieta.query.get(dieta_id) or not NutTipoRefeicao.query.get(tipo_id):
                    continue
                row = NutPrecoDietaTipo(dieta_id=dieta_id, tipo_refeicao_id=tipo_id)
                db.session.add(row)
        try:
            if any(k in item for k in (
                'valor_empresa', 'valor_paciente', 'valor_acompanhante',
                'empresa', 'paciente', 'acompanhante',
            )):
                v_emp = _parse_valor(item, 'valor_empresa', 'empresa', fallback=row.valor_empresa or 0)
                v_pac = _parse_valor(item, 'valor_paciente', 'paciente', fallback=row.valor_paciente or 0)
                v_aco = _parse_valor(item, 'valor_acompanhante', 'acompanhante', fallback=row.valor_acompanhante or 0)
            else:
                v = _parse_valor(item, 'valor', fallback=0)
                v_emp = v_pac = v_aco = v
        except (TypeError, ValueError):
            dieta_nome = row.dieta.nome if row.dieta else str(row.dieta_id)
            return jsonify({'ok': False, 'error': f'Valor inválido ({dieta_nome})'}), 400
        if min(v_emp, v_pac, v_aco) < 0:
            return jsonify({'ok': False, 'error': 'Valor não pode ser negativo'}), 400
        row.valor_empresa = v_emp
        row.valor_paciente = v_pac
        row.valor_acompanhante = v_aco
        row.data_alteracao = datetime.utcnow()
        atualizados += 1

    db.session.commit()
    return jsonify({
        'ok': True,
        'atualizados': atualizados,
        'matriz': matriz_precos_dieta_tipo(somente_ativas=True, somente_tipos_ativos=True),
    })


@nutricao.route('/nutricao/api/precos-refeicoes/adicionar', methods=['POST'])
def api_precos_refeicoes_adicionar():
    """
    Adiciona/atualiza valores de refeição para uma dieta no contexto
    Empresa / Paciente / Acompanhante (opcionalmente replicando nas 3 colunas).
    """
    from nutricao_service import GRUPO_POR_PAYER, _normalize_precos_map

    seed_nutricao()
    d = request.get_json(force=True) or {}
    coluna = (d.get('coluna') or d.get('payer') or 'paciente').strip().lower()
    if coluna not in ('empresa', 'paciente', 'acompanhante'):
        return jsonify({'ok': False, 'error': 'Coluna inválida'}), 400
    replicar = bool(d.get('replicar') or d.get('replicar_tres'))
    payers = ('empresa', 'paciente', 'acompanhante') if replicar else (coluna,)

    dieta = None
    dieta_id = d.get('dieta_id')
    if dieta_id not in (None, '', 0, '0'):
        try:
            dieta = NutDieta.query.get(int(dieta_id))
        except (TypeError, ValueError):
            dieta = None
    nome_novo = (d.get('dieta_nome') or d.get('nome') or '').strip().upper()
    grupo = (d.get('grupo') or '').strip().upper() or GRUPO_POR_PAYER.get(coluna, 'LACTÁRIO')
    if not dieta and nome_novo:
        dieta = NutDieta.query.filter(db.func.upper(NutDieta.nome) == nome_novo).first()
        if not dieta:
            dieta = NutDieta(
                nome=nome_novo,
                categoria=(d.get('categoria') or 'basica').strip() or 'basica',
                grupo=grupo,
                ativo=True,
            )
            db.session.add(dieta)
            db.session.flush()
        else:
            dieta.ativo = True
            if not (dieta.grupo or '').strip():
                dieta.grupo = grupo
            elif coluna in ('empresa', 'acompanhante') and bool(d.get('criar_dieta') or d.get('nova_dieta')):
                # Nova dieta no contexto: se pediu criar e já existe nome, só retag se vazio
                pass
    if not dieta:
        return jsonify({'ok': False, 'error': 'Selecione ou informe a dieta'}), 400

    # Tag de contexto ao criar/atualizar pelo popup (Funcionário / Acompanhante)
    if coluna == 'acompanhante' and (dieta.grupo or '').upper() not in ('ACOMPANHANTE', 'ACOMPANHANTE E KITS'):
        if bool(d.get('criar_dieta') or d.get('nova_dieta') or d.get('ajustar_grupo', True)):
            if not dieta.grupo or (dieta.grupo or '').upper() in ('', 'LACTÁRIO') and bool(d.get('nova_dieta')):
                dieta.grupo = 'ACOMPANHANTE'
    if coluna == 'empresa' and bool(d.get('nova_dieta')):
        dieta.grupo = 'FUNCIONARIO'
    if coluna == 'paciente' and bool(d.get('nova_dieta')) and not (dieta.grupo or '').strip():
        dieta.grupo = 'LACTÁRIO'

    # Tipos + valores
    precos_map = _parse_precos_payload(d)
    tipos_sel = d.get('tipos') or d.get('tipos_refeicao') or []
    tipo_ids = []
    if isinstance(tipos_sel, list) and tipos_sel:
        for t in tipos_sel:
            if isinstance(t, dict):
                tid = t.get('id') or t.get('tipo_refeicao_id') or t.get('tipo_id')
                sigla = (t.get('sigla') or t.get('tipo') or t.get('nome') or '').strip()
                valor = t.get('valor', t.get('value'))
                if tid is not None:
                    try:
                        tipo_ids.append(int(tid))
                    except (TypeError, ValueError):
                        pass
                elif sigla:
                    row_t = NutTipoRefeicao.query.filter(
                        db.or_(
                            db.func.upper(NutTipoRefeicao.sigla) == sigla.upper(),
                            db.func.upper(NutTipoRefeicao.nome) == sigla.upper(),
                        )
                    ).first()
                    if row_t:
                        tipo_ids.append(row_t.id)
                        sigla = row_t.nome
                if valor is not None and sigla:
                    try:
                        precos_map[str(sigla).upper()] = _parse_money(valor)
                    except (TypeError, ValueError):
                        return jsonify({'ok': False, 'error': f'Valor inválido ({sigla})'}), 400
            else:
                try:
                    tipo_ids.append(int(t))
                except (TypeError, ValueError):
                    pass
    if d.get('tipo_ids'):
        for tid in d.get('tipo_ids') or []:
            try:
                tipo_ids.append(int(tid))
            except (TypeError, ValueError):
                pass
    tipo_ids = list(dict.fromkeys(tipo_ids))
    if not tipo_ids and not precos_map:
        return jsonify({'ok': False, 'error': 'Selecione ao menos um tipo de refeição'}), 400

    # Se há tipo_ids mas precos_map veio como dict por id
    raw_vals = d.get('valores') or d.get('precos') or {}
    if isinstance(raw_vals, dict):
        for k, v in raw_vals.items():
            try:
                precos_map[str(k).upper()] = _parse_money(v)
            except (TypeError, ValueError):
                return jsonify({'ok': False, 'error': f'Valor inválido ({k})'}), 400

    precos_map = _normalize_precos_map(precos_map)
    if not precos_map:
        return jsonify({'ok': False, 'error': 'Informe os valores das refeições'}), 400

    ensure_precos_para_dieta(
        dieta.id,
        aplicar_default=False,
        precos_map=precos_map,
        forcar=True,
        payers=payers,
        tipos_ids=tipo_ids or None,
    )
    db.session.commit()
    return jsonify({
        'ok': True,
        'dieta': dieta.to_dict(),
        'coluna': coluna,
        'payers': list(payers),
        'matriz': matriz_precos_dieta_tipo(somente_ativas=True, somente_tipos_ativos=True),
    })


# ---- MAPA REFEIÇÕES ----
@nutricao.route('/nutricao/mapa_refeicoes')
def mapa_refeicoes():
    seed_nutricao()
    return render_template('nutricao_mapa_refeicoes.html', dietas=_list_dietas_db(), clinicas=_list_clinicas_db(), **active('mapa_refeicoes'))

# ---- ESTOQUE ----
@nutricao.route('/nutricao/estoque')
def estoque():
    seed_nutricao()
    estoques = list_estoques(somente_ativos=False)
    estoque_id = request.args.get('estoque_id', type=int)
    if not estoque_id and estoques:
        matriz = next((e for e in estoques if e['nome'] == 'MATRIZ'), None)
        estoque_id = (matriz or estoques[0])['id']
    grupo_id = request.args.get('grupo_id', type=int)
    return render_template(
        'nutricao_estoque.html',
        estoques=estoques,
        unidades=list_unidades(somente_ativas=False),
        grupos=list_grupos_produto(somente_ativos=False),
        produtos=list_produtos(estoque_id=estoque_id, grupo_id=grupo_id, somente_ativos=False),
        fornecedores=list_fornecedores(somente_ativos=False),
        estados=ESTADOS_BR,
        estoque_id=estoque_id,
        grupo_id=grupo_id,
        **active('estoque')
    )

@nutricao.route('/nutricao/api/estoque-produtos-legado', methods=['GET','POST'])
def api_produtos_legado():
    if request.method=='POST':
        d = request.get_json(force=True)
        n = {'id':max(p['id'] for p in PRODUTOS)+1 if PRODUTOS else 1}
        for k in ['nome','categoria','unidade','estoque_min','estoque_atual','fornecedor_id','valor_un']:
            n[k]=d.get(k)
        PRODUTOS.append(n)
        return jsonify({'ok':True,'id':n['id']})
    return jsonify(PRODUTOS)

# (api fornecedores real está em /nutricao/api/fornecedores)

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


@nutricao.route('/nutricao/relatorio-mapa-uma')
def relatorio_mapa_uma():
    seed_nutricao()
    hoje = date.today().isoformat()
    return render_template(
        'nutricao_relatorio_mapa_uma.html',
        clinicas=_list_clinicas_db(somente_ativas=False),
        enfermarias=list_enfermarias(somente_ativas=True),
        data_padrao=hoje,
        **active('relatorio_mapa_uma')
    )


@nutricao.route('/nutricao/api/relatorio-mapa-uma', methods=['POST'])
def api_relatorio_mapa_uma():
    seed_nutricao()
    d = request.get_json(force=True) or {}
    data_ref = _parse_date(d.get('data')) or date.today()
    categoria = (d.get('categoria') or 'enteral').strip()
    imprimir_por = (d.get('imprimir_por') or 'grupo_clinica').strip()
    filtro_id = d.get('filtro_id')
    filtro_nome = (d.get('filtro_nome') or '').strip() or None
    horarios = d.get('horarios') or []
    amostra = None
    if d.get('imprimir_amostra'):
        amostra = d.get('amostra_valor', 50)

    # se filtro_id de clínica sem nome, resolve
    if not filtro_nome and filtro_id and imprimir_por in ('grupo_clinica', 'clinica'):
        cli = NutClinica.query.get(int(filtro_id))
        if cli:
            filtro_nome = cli.nome

    # garante alguns dados demo de U.M.A. no dia se ainda vazios
    _seed_mapa_uma_demo(data_ref)

    resultado = totalizar_mapa_uma(
        data_ref=data_ref,
        categoria=categoria,
        imprimir_por=imprimir_por,
        filtro_id=filtro_id,
        filtro_nome=filtro_nome,
        horarios=horarios,
        amostra=amostra,
    )
    return jsonify({'ok': True, 'relatorio': resultado})


@nutricao.route('/nutricao/totalizacao-dietas')
def totalizacao_dietas():
    seed_nutricao()
    return render_template(
        'nutricao_totalizacao_dietas.html',
        clinicas=_list_clinicas_db(somente_ativas=False),
        enfermarias=list_enfermarias(somente_ativas=True),
        data_padrao=date.today().isoformat(),
        **active('totalizacao_dietas')
    )


@nutricao.route('/nutricao/totalizacao-dietas/imprimir')
def totalizacao_dietas_imprimir():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    totalizacao_para = (request.args.get('totalizacao_para') or 'clinicas').strip()
    imprimir_por = (request.args.get('imprimir_por') or 'grupo_clinica').strip()
    filtros = [x for x in (request.args.get('filtros') or '').split('|') if x.strip()]
    horarios = [x for x in (request.args.get('horarios') or '').split(',') if x.strip()]
    metodo = (request.args.get('metodo') or 'mapa').strip()
    imprimir_total = str(request.args.get('imprimir_total_geral', '1')).lower() in ('1', 'true', 'sim')

    # reaproveita demo do faturamento para ter flags no mapa
    try:
        _seed_faturamento_demo(data_ref, data_ref)
    except Exception:
        garantir_mapa_do_dia(data_ref)

    rel = gerar_totalizacao_dietas(
        data_ref=data_ref,
        totalizacao_para=totalizacao_para,
        imprimir_por=imprimir_por,
        filtros=filtros,
        horarios=horarios,
        metodo=metodo,
        imprimir_total_geral=imprimir_total,
    )
    return render_template(
        'nutricao_totalizacao_dietas_print.html',
        r=rel,
        **active('totalizacao_dietas')
    )


@nutricao.route('/nutricao/relatorio-mapa-uma/imprimir')
def relatorio_mapa_uma_imprimir():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    categoria = (request.args.get('categoria') or 'enteral').strip()
    imprimir_por = (request.args.get('imprimir_por') or 'grupo_clinica').strip()
    filtro_id = request.args.get('filtro_id', type=int)
    filtro_nome = (request.args.get('filtro_nome') or '').strip() or None
    horarios = [h for h in (request.args.get('horarios') or '').split(',') if h.strip()]
    amostra = None
    if str(request.args.get('imprimir_amostra', '')).lower() in ('1', 'true', 'sim'):
        try:
            amostra = float(request.args.get('amostra_valor') or 50)
        except (TypeError, ValueError):
            amostra = 50.0

    if not filtro_nome and filtro_id and imprimir_por in ('grupo_clinica', 'clinica'):
        cli = NutClinica.query.get(filtro_id)
        if cli:
            filtro_nome = cli.nome

    _seed_mapa_uma_demo(data_ref)
    relatorio = totalizar_mapa_uma(
        data_ref=data_ref,
        categoria=categoria,
        imprimir_por=imprimir_por,
        filtro_id=filtro_id,
        filtro_nome=filtro_nome,
        horarios=horarios,
        amostra=amostra,
    )
    return render_template(
        'nutricao_relatorio_mapa_uma_print.html',
        r=relatorio,
        **active('relatorio_mapa_uma')
    )


def _seed_mapa_uma_demo(data_ref):
    """Preenche campos U.M.A. de exemplo se o mapa do dia estiver vazio nesses campos."""
    garantir_mapa_do_dia(data_ref)
    rows = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True).all()
    if not rows:
        return
    tem = any((r.enteral or r.suplementos or r.formula_infantil or r.lve) for r in rows)
    if tem:
        return
    demos = [
        {'enteral': 'NUTRI ENTERAL 1L', 'suplementos': 'FORTIDRINK BAUNILHA 200 ML', 'lve': ''},
        {'enteral': 'NUTRI ENTERAL 1L', 'suplementos': '', 'formula_infantil': 'FÓRMULA INFANTIL 200ML'},
        {'enteral': 'HIPERCALÓRICA 1.5 - NUTRI ENTERAL 1L', 'suplementos': 'FORTIDRINK BAUNILHA 200 ML', 'lve': 'LVE PADRÃO'},
    ]
    for i, row in enumerate(rows[:3]):
        d = demos[i % len(demos)]
        row.enteral = d.get('enteral') or None
        row.suplementos = d.get('suplementos') or None
        row.formula_infantil = d.get('formula_infantil') or None
        row.lve = d.get('lve') or None
    db.session.commit()


# ---- FATURAMENTO ----
@nutricao.route('/nutricao/faturamento')
def faturamento():
    seed_nutricao()
    hoje = date.today().isoformat()
    return render_template(
        'nutricao_faturamento.html',
        data_padrao=hoje,
        **active('faturamento')
    )


def _params_faturamento_from_request(src):
    data_de = _parse_date(src.get('data_de')) or date.today()
    data_ate = _parse_date(src.get('data_ate')) or data_de
    tipo = (src.get('tipo') or 'espelho_1').strip()
    por_grupo = str(src.get('por_grupo_clinica', '')).lower() in ('1', 'true', 'sim', 'on')
    sintetico = str(src.get('sintetico', '')).lower() in ('1', 'true', 'sim', 'on')
    if hasattr(src, 'getlist'):
        # form POST unused
        pass
    return data_de, data_ate, tipo, por_grupo, sintetico


@nutricao.route('/nutricao/faturamento/imprimir')
def faturamento_imprimir():
    seed_nutricao()
    data_de, data_ate, tipo, por_grupo, sintetico = _params_faturamento_from_request(request.args)
    # demo flags no mapa se necessário
    _seed_faturamento_demo(data_de, data_ate)
    rel = relatorio_faturamento(
        data_de=data_de,
        data_ate=data_ate,
        tipo=tipo,
        por_grupo_clinica=por_grupo,
        sintetico=sintetico,
    )
    return render_template('nutricao_faturamento_print.html', r=rel, **active('faturamento'))


@nutricao.route('/nutricao/faturamento/exportar')
def faturamento_exportar():
    import csv
    import io
    from flask import Response

    seed_nutricao()
    data_de, data_ate, tipo, por_grupo, sintetico = _params_faturamento_from_request(request.args)
    _seed_faturamento_demo(data_de, data_ate)
    rel = relatorio_faturamento(
        data_de=data_de,
        data_ate=data_ate,
        tipo=tipo,
        por_grupo_clinica=por_grupo,
        sintetico=sintetico,
    )
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Relatório', rel['tipo_label']])
    w.writerow(['Período', f"{rel['data_de_label']} a {rel['data_ate_label']}"])
    w.writerow([])

    if tipo in ('total_formulas',):
        w.writerow(['Item', 'Quantidade'])
        for f in rel['formulas']:
            w.writerow([f['item'], f['qtd']])
    elif tipo == 'total_complementares':
        w.writerow(['Item', 'Quantidade'])
        for f in rel['complementares']:
            w.writerow([f['item'], f['qtd']])
    else:
        w.writerow(['Data', 'Clínica', 'Categoria', 'Desjejum', 'Colação', 'Almoço', 'Merenda', 'Jantar', 'Ceia', 'Total'])
        for t in rel['tabelas']:
            for row in t['linhas']:
                w.writerow([
                    t['data_label'], t['clinica'], row['categoria'],
                    row['desjejum'], row['colacao'], row['almoco'],
                    row['merenda'], row['jantar'], row['ceia'], row['total'],
                ])
        w.writerow([])
        w.writerow(['RESUMO'])
        for row in rel['resumo_totais']:
            w.writerow([
                '', 'TOTAL', row['categoria'],
                row['desjejum'], row['colacao'], row['almoco'],
                row['merenda'], row['jantar'], row['ceia'], row['total'],
            ])

    out = '\ufeff' + buf.getvalue()
    return Response(
        out,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=faturamento.csv'},
    )


def _seed_faturamento_demo(data_de, data_ate):
    """Garante flags de refeição e mix de dietas para demonstrar o espelho."""
    cur = data_de
    while cur <= data_ate:
        garantir_mapa_do_dia(cur)
        rows = NutMapaRefeicao.query.filter_by(data_refeicao=cur, ativo=True).order_by(NutMapaRefeicao.id).all()
        if not rows:
            cur = date.fromordinal(cur.toordinal() + 1)
            continue

        nomes_demo = ['CABEÇA E PESCOÇO', 'CARDIOLOGIA', 'CIRURGIA GERAL A']
        clinicas_existentes = { (c.nome or '').upper(): c.nome for c in NutClinica.query.all() }
        demos = [
            {'clinica': 'CABEÇA E PESCOÇO', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CABEÇA E PESCOÇO', 'dieta': 'BRANDA SEM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CABEÇA E PESCOÇO', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CABEÇA E PESCOÇO', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CABEÇA E PESCOÇO', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CABEÇA E PESCOÇO', 'dieta': 'LIQUIDA SEM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CABEÇA E PESCOÇO', 'dieta': 'LIQUIDA SEM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CABEÇA E PESCOÇO', 'dieta': 'LIQUIDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'BRANDA COM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'LIQUIDA SEM SAL', 'enteral': None, 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'NORMOCALORICA E NORMOPROTEICA - NUTRI ENTERAL 1L',
             'enteral': 'NUTRI ENTERAL 1L', 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'NORMOCALORICA E HIPERPROTEICA - NUTRI ENTERAL 1L',
             'enteral': 'NUTRI ENTERAL 1L', 'formula_infantil': None},
            {'clinica': 'CARDIOLOGIA', 'dieta': 'HIPERCALORICA 1.5 E HIPERPROTEICA - NUTRI ENTERAL 1L',
             'enteral': 'NUTRI ENTERAL 1L', 'formula_infantil': None},
        ]

        # só aplica demo se ainda não houver distribuição típica (basicas+liquidas)
        cats = []
        from nutricao_service import _classificar_dieta_faturamento
        dieta_cat_map = {(d.nome or '').strip().upper(): (d.categoria or 'basica') for d in NutDieta.query.all()}
        for r in rows:
            cats.append(_classificar_dieta_faturamento(r, dieta_cat_map))
        clinicas_set = {(r.clinica or '') for r in rows}
        precisa = len(clinicas_set) < 2 or not ('basicas' in cats and 'liquidas' in cats)

        if precisa or not any(r.fl_almoco for r in rows):
            while len(rows) < len(demos):
                base = rows[0] if rows else None
                if not base:
                    break
                clone = NutMapaRefeicao(
                    data_refeicao=cur,
                    # Não vincular a paciente real — evita duplicar/ressuscitar no mapa de produção
                    paciente_id=None,
                    nome=f'DEMO {len(rows)+1}',
                    leito=f'D{len(rows)+1}',
                    clinica='CABEÇA E PESCOÇO',
                    dieta='BRANDA COM SAL',
                    ativo=True,
                    fl_desjejum=True, fl_colacao=True, fl_almoco=True,
                    fl_merenda=True, fl_jantar=True, fl_ceia=True,
                )
                db.session.add(clone)
                db.session.flush()
                rows.append(clone)

            for i, r in enumerate(rows[:len(demos)]):
                d = demos[i]
                alvo = d['clinica']
                if alvo.upper() in clinicas_existentes:
                    r.clinica = clinicas_existentes[alvo.upper()]
                else:
                    r.clinica = alvo
                r.dieta = d['dieta']
                r.enteral = d.get('enteral')
                r.formula_infantil = d.get('formula_infantil')
                r.fl_desjejum = True
                r.fl_colacao = True
                r.fl_almoco = True
                r.fl_merenda = True
                r.fl_jantar = True
                # ceia líquidas +1 no exemplo legado para cabeça/pescoço
                r.fl_ceia = True
            db.session.commit()

        cur = date.fromordinal(cur.toordinal() + 1)


# ---- AUDITORIA (layout Nutrição preservado) ----
@nutricao.route('/nutricao/auditoria')
def auditoria():
    """Auditoria dentro do layout de Nutrição Hospitalar (sidebar preservada)."""
    from datetime import timedelta
    from audit_service import listar_logs, ensure_audit_table

    ensure_audit_table()
    hoje = date.today()
    data_de = _parse_date(request.args.get('data_de')) or (hoje - timedelta(days=7))
    data_ate = _parse_date(request.args.get('data_ate')) or hoje
    if 'modulo' in request.args:
        modulo = (request.args.get('modulo') or '').strip() or None
    else:
        modulo = 'nutricao'
    usuario = (request.args.get('usuario') or '').strip() or None
    acao = (request.args.get('acao') or '').strip() or None
    q = (request.args.get('q') or '').strip() or None
    try:
        limit = min(int(request.args.get('limit') or 200), 500)
    except (TypeError, ValueError):
        limit = 200

    total, logs = listar_logs(
        modulo=modulo,
        usuario=usuario,
        acao=acao,
        q=q,
        data_de=data_de,
        data_ate=data_ate,
        limit=limit,
        offset=0,
    )
    return render_template(
        'nutricao_auditoria.html',
        logs=logs,
        total=total,
        filtros={
            'data_de': data_de.isoformat(),
            'data_ate': data_ate.isoformat(),
            'modulo': modulo or '',
            'usuario': usuario or '',
            'acao': acao or '',
            'q': q or '',
            'limit': limit,
        },
        **active('auditoria'),
    )


# ---- ADMIN (usuários centralizados em Acessos na home) ----
@nutricao.route('/nutricao/admin')
def admin():
    flash('Cadastro de usuários e permissões fica em Acessos, na tela principal do portal.', 'info')
    return redirect(url_for('nutricao.dashboard'))

@nutricao.route('/nutricao/api/usuarios', methods=['POST'])
def api_usuarios_create():
    return jsonify({
        'ok': False,
        'error': 'Cadastro de usuários da Nutrição fica em Acessos, na tela principal do portal.',
    }), 404

# ---- UTILITÁRIOS ----
@nutricao.route('/nutricao/utilitarios')
def utilitarios():
    from audit_service import listar_logs
    _, logs = listar_logs(modulo='nutricao', limit=50)
    return render_template(
        'nutricao_utilitarios.html',
        autorizacoes=AUTORIZACOES_SUBSTITUICAO,
        logs=logs,
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
    from audit_service import listar_logs
    _, logs = listar_logs(modulo='nutricao', limit=100)
    return jsonify(logs)
