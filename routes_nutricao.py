from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, g, abort
from functools import wraps
from datetime import datetime, date
import json
import os

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from models import db
from models_nutricao import (
    NutClinica, NutGrupoClinica, NutEnfermaria, NutLeito, NutDieta, NutGrupoDieta, NutCategoriaDieta, NutPaciente, NutMapaRefeicao, NutCardapio,
    NutTabelaNutrientes, NutAlimento, NutAlimentoNutriente, NutPratoLiquido,
    NutEstoqueLocal, NutUnidadeMedida, NutGrupoProduto, NutProduto, NutFornecedor,
    NutEtiqueta, NutEtiquetaCampo, NutPrecoRefeicao, NutTipoRefeicao, NutPrecoDietaTipo,
    NutRefeicaoAcompanhante, NutRefeicaoFuncionario,
    NutViaAdministracao, NutUmaItem,
    CAMPOS_ITEM_CARDAPIO,
)
from nutricao_clinico import (
    LABORATORIO, REFEICOES_DIRETAS,
    avaliacao_dict, buscar_avaliacao, calcular_avaliacao, contexto_paciente,
    excluir_evolucao, excluir_totalizacao_direta, listar_evolucoes,
    listar_totalizacao_direta, macros_da_dieta, pacientes_do_mapa,
    salvar_avaliacao, salvar_evolucao, salvar_totalizacao_direta,
)
from nutricao_tenant import (
    resolve_nutricao_cliente,
    require_cliente_for_write,
    scoped_query,
    row_belongs_to_cliente,
    write_cliente_id,
    apply_cliente_filter,
    usuario_ve_todos_clientes,
    label_cliente_nutricao,
)
from nutricao_service import (
    seed_nutricao,
    paciente_from_payload,
    mapa_from_paciente,
    criar_lancamento_dieta_desde_linha,
    garantir_grupo_lancamento,
    garantir_mapa_do_dia,
    marcar_alteracao_mapa,
    leito_ocupado_no_mapa,
    MSG_LEITO_OCUPADO,
    list_leitos_vagos,
    montar_grade_leitos_mapa,
    listar_linhas_mapa_uma,
    separar_lancamentos_uma,
    aplicar_campos_uma_independentes,
    apagar_lancamento_uma,
    eh_lancamento_uma,
    invalidar_cache_cardapios,
    invalidar_cache_produtos_cardapio,
    excluir_paciente_cadastro,
    paciente_ativo_no_mapa,
    MSG_ACOMP_SO_SAIDA_MAPA,
    garantir_acompanhantes_do_dia,
    normalizar_tipo_lancamento,
    list_clinicas,
    list_grupos_clinica,
    nomes_clinicas_do_grupo,
    list_enfermarias,
    list_leitos,
    list_dietas,
    list_grupos_dieta,
    list_categorias_dieta,
    slug_categoria_dieta,
    codigo_categoria_unico,
    list_tipos_refeicao,
    normalizar_hora_limite,
    list_cardapios,
    excluir_dieta_e_cardapios,
    excluir_grupo_dieta,
    liberar_dieta_excluida,
    liberar_grupo_dieta_excluido,
    list_tabelas_nutrientes,
    list_alimentos,
    import_tabela_fdc,
    list_pratos_liquidos,
    list_vias,
    config_uma_dict,
    salvar_config_uma,
    colunas_faturamento_uma,
    list_uma_itens,
    gravar_uma_item,
    salvar_cadastro_uma,
    apagar_cadastro_lve,
    desvincular_lves_das_dietas,
    salvar_opcao_uma,
    listar_campo_uma,
    renomear_opcao_uma,
    remover_opcao_uma,
    list_estoques,
    list_unidades,
    list_grupos_produto,
    list_produtos,
    list_produtos_tema_cardapio,
    list_produtos_temas_cardapio,
    criar_produto_tema_cardapio,
    list_itens_tema_cardapio,
    list_itens_temas_cardapio,
    criar_item_cardapio,
    list_fornecedores,
    list_etiquetas,
    list_precos_refeicoes,
    matriz_precos_dieta_tipo,
    _seed_precos_dieta_tipo,
    ensure_precos_para_dieta,
    totalizar_mapa_uma,
    relatorio_faturamento,
    relatorio_faturamento_valores,
    totalizacao_dietas as gerar_totalizacao_dietas,
    totalizacao_dietas_refeicoes as gerar_totalizacao_dietas_refeicoes,
    totalizacao_substituicao_alimentos as gerar_totalizacao_substituicoes,
    totalizacao_consumo_alimentos as gerar_totalizacao_consumo,
    impressao_cardapio_servido as gerar_cardapio_servido,
    listar_avisos_alta_mapa,
    aplicar_avisos_alta_mapa,
    registrar_saida_mapa,
    list_modelos_etiqueta_impressao,
    gerar_impressao_etiquetas,
    gerar_impressao_mapa,
    gerar_impressao_mapa_distribuicao,
    list_tipos_refeicao_impressao,
    get_mapa_substituicoes,
    opcoes_itens_refeicao,
    save_mapa_substituicoes,
    importar_substituicoes_anteriores,
    listar_justificativas_anteriores,
    CARDAPIO_OPCOES,
    ESTADOS_BR,
    _parse_date,
)

nutricao = Blueprint('nutricao', __name__, template_folder='templates_nutricao')


def _chaves_menu_nutricao(path, method):
    """Menu(s) exigidos para a URL. None = sem trava extra."""
    path = (path or '').rstrip('/') or '/'
    gravar = method in ('POST', 'PUT', 'PATCH', 'DELETE')
    uma = (
        'cadastro_uma_formula', 'cadastro_uma_enteral',
        'cadastro_uma_suplemento', 'cadastro_uma_lve',
    )
    regras = (
        ('/nutricao/api/pacientes', ('cadastro_pacientes', 'mapa_refeicoes'), ('cadastro_pacientes', 'mapa_refeicoes')),
        ('/nutricao/pacientes', ('cadastro_pacientes',), ('cadastro_pacientes',)),
        ('/nutricao/api/refeicao-acompanhantes', ('refeicao_acompanhante', 'mapa_refeicoes'), ('refeicao_acompanhante', 'mapa_refeicoes')),
        ('/nutricao/refeicao-acompanhante', ('refeicao_acompanhante',), ('refeicao_acompanhante',)),
        ('/nutricao/api/refeicao-funcionarios', ('refeicoes_funcionarios',), ('refeicoes_funcionarios',)),
        ('/nutricao/refeicoes-funcionarios', ('refeicoes_funcionarios',), ('refeicoes_funcionarios',)),
        ('/nutricao/api/mapa', ('mapa_refeicoes',), ('mapa_refeicoes',)),
        ('/nutricao/mapa_refeicoes', ('mapa_refeicoes',), ('mapa_refeicoes',)),
        ('/nutricao/api/clinicas', ('cadastro_clinicas', 'mapa_refeicoes'), ('cadastro_clinicas',)),
        ('/nutricao/clinicas', ('cadastro_clinicas',), ('cadastro_clinicas',)),
        ('/nutricao/api/grupos-clinicas', ('cadastro_clinicas',), ('cadastro_clinicas',)),
        ('/nutricao/grupos-clinicas', ('cadastro_clinicas',), ('cadastro_clinicas',)),
        ('/nutricao/api/enfermarias', ('cadastro_enfermarias', 'mapa_refeicoes'), ('cadastro_enfermarias',)),
        ('/nutricao/enfermarias', ('cadastro_enfermarias',), ('cadastro_enfermarias',)),
        ('/nutricao/api/leitos', ('cadastro_leitos', 'mapa_refeicoes'), ('cadastro_leitos',)),
        ('/nutricao/leitos', ('cadastro_leitos',), ('cadastro_leitos',)),
        ('/nutricao/api/dietas', ('cadastro_dietas', 'mapa_refeicoes', 'cadastro_cardapios'), ('cadastro_dietas',)),
        ('/nutricao/dietas', ('cadastro_dietas',), ('cadastro_dietas',)),
        ('/nutricao/api/categorias', ('cadastro_categorias',), ('cadastro_categorias',)),
        ('/nutricao/categorias', ('cadastro_categorias',), ('cadastro_categorias',)),
        ('/nutricao/api/grupos-dietas', ('cadastro_grupos_dietas',), ('cadastro_grupos_dietas',)),
        ('/nutricao/grupos-dietas', ('cadastro_grupos_dietas',), ('cadastro_grupos_dietas',)),
        ('/nutricao/api/tipos-refeicao', ('cadastro_tipos_refeicao', 'mapa_refeicoes'), ('cadastro_tipos_refeicao',)),
        ('/nutricao/tipos-refeicao', ('cadastro_tipos_refeicao',), ('cadastro_tipos_refeicao',)),
        ('/nutricao/api/cardapio-itens', ('cadastro_cardapios',), ('cadastro_cardapios',)),
        ('/nutricao/api/cardapios', ('cadastro_cardapios',), ('cadastro_cardapios',)),
        ('/nutricao/cardapios', ('cadastro_cardapios',), ('cadastro_cardapios',)),
        ('/nutricao/api/tabelas-nutrientes', ('cadastro_nutricional',), ('cadastro_nutricional',)),
        ('/nutricao/api/alimentos', ('cadastro_nutricional',), ('cadastro_nutricional',)),
        ('/nutricao/nutricional', ('cadastro_nutricional',), ('cadastro_nutricional',)),
        ('/nutricao/api/pratos-liquidos', ('cadastro_pratos_liquidos',), ('cadastro_pratos_liquidos',)),
        ('/nutricao/pratos-liquidos', ('cadastro_pratos_liquidos',), ('cadastro_pratos_liquidos',)),
        ('/nutricao/api/vias', ('cadastro_vias', 'configuracoes'), ('cadastro_vias',)),
        ('/nutricao/vias', ('cadastro_vias',), ('cadastro_vias',)),
        ('/nutricao/api/uma-itens', None, None),
        ('/nutricao/api/cadastro-uma', None, None),
        ('/nutricao/cadastro-uma', None, None),
        ('/nutricao/api/config-uma', ('configuracoes',), ('configuracoes',)),
        ('/nutricao/configuracoes', ('configuracoes',), ('configuracoes',)),
        ('/nutricao/api/estoques', ('estoque', 'cadastro_produtos', 'configuracoes') + uma, ('estoque', 'cadastro_produtos')),
        ('/nutricao/api/unidades', ('estoque', 'cadastro_produtos', 'configuracoes') + uma, ('estoque', 'cadastro_produtos')),
        ('/nutricao/api/grupos-produto', ('estoque', 'cadastro_produtos'), ('estoque', 'cadastro_produtos')),
        ('/nutricao/api/cardapio-produtos', ('cadastro_produtos', 'cadastro_cardapios'), ('cadastro_produtos', 'cadastro_cardapios')),
        ('/nutricao/api/produtos', ('cadastro_produtos', 'estoque') + uma, ('cadastro_produtos', 'estoque')),
        ('/nutricao/api/estoque-produtos-legado', ('estoque',), ('estoque',)),
        ('/nutricao/produtos', ('cadastro_produtos',), ('cadastro_produtos',)),
        ('/nutricao/estoque', ('estoque',), ('estoque',)),
        ('/nutricao/api/fornecedores', ('cadastro_fornecedores', 'estoque'), ('cadastro_fornecedores',)),
        ('/nutricao/fornecedores', ('cadastro_fornecedores',), ('cadastro_fornecedores',)),
        ('/nutricao/api/etiquetas', ('cadastro_etiquetas', 'impressao_etiquetas'), ('cadastro_etiquetas',)),
        ('/nutricao/etiquetas', ('cadastro_etiquetas',), ('cadastro_etiquetas',)),
        ('/nutricao/impressao-etiquetas', ('impressao_etiquetas',), ('impressao_etiquetas',)),
        ('/nutricao/impressao-mapa-distribuicao', ('impressao_mapa_distribuicao',), ('impressao_mapa_distribuicao',)),
        ('/nutricao/impressao-mapa', ('impressao_mapa',), ('impressao_mapa',)),
        ('/nutricao/api/precos-refeicoes', ('cadastro_precos_refeicoes',), ('cadastro_precos_refeicoes',)),
        ('/nutricao/precos-refeicoes', ('cadastro_precos_refeicoes',), ('cadastro_precos_refeicoes',)),
        ('/nutricao/api/relatorio-mapa-uma', ('relatorio_mapa_uma',), ('relatorio_mapa_uma',)),
        ('/nutricao/relatorio-mapa-uma', ('relatorio_mapa_uma',), ('relatorio_mapa_uma',)),
        ('/nutricao/totalizacao-dietas-refeicoes', ('totalizacao_dietas_refeicoes',), ('totalizacao_dietas_refeicoes',)),
        ('/nutricao/totalizacao-dietas', ('totalizacao_dietas_refeicoes',), ('totalizacao_dietas_refeicoes',)),
        ('/nutricao/totalizacao-substituicoes', ('totalizacao_substituicoes',), ('totalizacao_substituicoes',)),
        ('/nutricao/totalizacao-consumo', ('totalizacao_consumo',), ('totalizacao_consumo',)),
        ('/nutricao/cardapio-servido', ('cardapio_servido',), ('cardapio_servido',)),
        ('/nutricao/faturamento-valores', ('faturamento_valores',), ('faturamento_valores',)),
        ('/nutricao/faturamento', ('faturamento',), ('faturamento',)),
        ('/nutricao/relatorios', ('relatorios',), ('relatorios',)),
        ('/nutricao/auditoria', ('auditoria',), ('auditoria',)),
        ('/nutricao/api/logs', ('auditoria',), ('auditoria',)),
        ('/nutricao/utilitarios', ('auditoria',), ('auditoria',)),
        ('/nutricao/api/analise-nutricional', ('analise_nutricional',), ('analise_nutricional',)),
        ('/nutricao/analise-nutricional', ('analise_nutricional',), ('analise_nutricional',)),
        ('/nutricao/api/evolucao', ('evolucao',), ('evolucao',)),
        ('/nutricao/evolucao', ('evolucao',), ('evolucao',)),
        ('/nutricao/api/totalizacao_direta', ('impressao_etiquetas',), ('impressao_etiquetas',)),
        ('/nutricao/totalizacao-direta', ('impressao_etiquetas',), ('impressao_etiquetas',)),
        ('/nutricao/api/autorizacoes_substituicao', ('mapa_refeicoes',), ('mapa_refeicoes',)),
        ('/nutricao/admin', (), ()),
        ('/nutricao/api/usuarios', (), ()),
        ('/nutricao', ('mapa_refeicoes',), ('mapa_refeicoes',)),
    )
    if path.startswith('/nutricao/api/uma-itens') or path.startswith('/nutricao/cadastro-uma') or path.startswith('/nutricao/api/cadastro-uma'):
        tipo = (request.args.get('tipo') or '').strip().lower()
        if not tipo:
            data = request.get_json(silent=True) or {}
            if isinstance(data, dict):
                tipo = (data.get('tipo') or request.form.get('tipo') or '').strip().lower()
        mapa = {
            'formula': 'cadastro_uma_formula',
            'enteral': 'cadastro_uma_enteral',
            'suplemento': 'cadastro_uma_suplemento',
            'lve': 'cadastro_uma_lve',
        }
        if path.startswith('/nutricao/api/uma-itens') and tipo not in mapa:
            return ('mapa_refeicoes', 'configuracoes') + uma
        return (mapa.get(tipo, 'cadastro_uma_formula'),)
    for prefix, ler, grav in regras:
        if prefix == '/nutricao':
            if path == '/nutricao':
                return grav if gravar else ler
            continue
        if path == prefix or path.startswith(prefix + '/'):
            return grav if gravar else ler
    return None


_NUTRICAO_ENTRADA = (
    ('mapa_refeicoes', 'nutricao.dashboard'),
    ('refeicao_acompanhante', 'nutricao.refeicao_acompanhante'),
    ('refeicoes_funcionarios', 'nutricao.refeicoes_funcionarios'),
    ('cadastro_pacientes', 'nutricao.pacientes'),
    ('cadastro_clinicas', 'nutricao.clinicas'),
    ('cadastro_enfermarias', 'nutricao.enfermarias'),
    ('cadastro_leitos', 'nutricao.leitos'),
    ('cadastro_categorias', 'nutricao.categorias_dietas'),
    ('cadastro_grupos_dietas', 'nutricao.grupos_dietas'),
    ('cadastro_dietas', 'nutricao.dietas'),
    ('cadastro_vias', 'nutricao.vias_administracao'),
    ('cadastro_uma_formula', 'nutricao.cadastro_uma'),
    ('cadastro_tipos_refeicao', 'nutricao.tipos_refeicao'),
    ('cadastro_cardapios', 'nutricao.cardapios'),
    ('cadastro_precos_refeicoes', 'nutricao.precos_refeicoes'),
    ('cadastro_nutricional', 'nutricao.nutricional'),
    ('cadastro_pratos_liquidos', 'nutricao.pratos_liquidos'),
    ('cadastro_produtos', 'nutricao.produtos'),
    ('cadastro_fornecedores', 'nutricao.fornecedores'),
    ('cadastro_etiquetas', 'nutricao.etiquetas'),
    ('estoque', 'nutricao.estoque'),
    ('analise_nutricional', 'nutricao.analise_nutricional'),
    ('evolucao', 'nutricao.evolucao_paciente'),
    ('relatorio_mapa_uma', 'nutricao.relatorio_mapa_uma'),
    ('impressao_etiquetas', 'nutricao.impressao_etiquetas'),
    ('impressao_mapa', 'nutricao.impressao_mapa'),
    ('impressao_mapa_distribuicao', 'nutricao.impressao_mapa_distribuicao'),
    ('totalizacao_dietas_refeicoes', 'nutricao.totalizacao_dietas_refeicoes'),
    ('totalizacao_substituicoes', 'nutricao.totalizacao_substituicoes'),
    ('totalizacao_consumo', 'nutricao.totalizacao_consumo'),
    ('cardapio_servido', 'nutricao.cardapio_servido'),
    ('relatorios', 'nutricao.relatorios'),
    ('faturamento', 'nutricao.faturamento'),
    ('faturamento_valores', 'nutricao.faturamento_valores'),
    ('configuracoes', 'nutricao.configuracoes_sistema'),
    ('auditoria', 'nutricao.auditoria'),
)


def _resposta_sem_menu_nutricao(user):
    if not user:
        return None
    chaves = _chaves_menu_nutricao(request.path, request.method)
    if chaves is None:
        return None
    if not chaves or any(user.tem_menu('nutricao', chave) for chave in chaves):
        return None
    wants_json = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in (request.headers.get('Accept') or '')
        or '/api/' in (request.path or '')
    )
    if wants_json:
        return jsonify({'ok': False, 'message': 'Você não tem permissão para este item da nutrição.'}), 403
    for chave, endpoint in _NUTRICAO_ENTRADA:
        if user.tem_menu('nutricao', chave):
            flash('Você não tem permissão para este item da nutrição.', 'error')
            if endpoint == 'nutricao.cadastro_uma':
                return redirect(url_for(endpoint, tipo='formula'))
            return redirect(url_for(endpoint))
    flash('Você não tem permissão para este item da nutrição.', 'error')
    return redirect(url_for('main.inicio'))


@nutricao.before_request
def _nutricao_tenant_gate():
    user, cliente, cid = resolve_nutricao_cliente()
    g.nutricao_usuario = user
    g.nutricao_cliente = cliente
    g.nutricao_cliente_id = cid
    if not user:
        return None
    # Non-master without linked client (or todos) cannot use nutrition
    if cid is None and not usuario_ve_todos_clientes(user):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') or request.path.startswith('/nutricao'):
            wants_json = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or 'application/json' in (request.headers.get('Accept') or '')
                or '/api/' in (request.path or '')
            )
            msg = 'Seu acesso não está vinculado a um cliente de nutrição. Peça ao administrador.'
            if wants_json:
                return jsonify({'ok': False, 'message': msg}), 403
            flash(msg, 'error')
            return redirect(url_for('main.inicio'))
    return _resposta_sem_menu_nutricao(user)


@nutricao.context_processor
def _inject_nutricao_cliente():
    from permissions_sistemas import NUTRICAO_GRUPOS
    cli = getattr(g, 'nutricao_cliente', None)
    user = getattr(g, 'nutricao_usuario', None)
    nome = label_cliente_nutricao(user) if user else ((cli.nome if cli else '') or '')

    def nut_ok(key, usuario=user):
        return bool(usuario and usuario.tem_menu('nutricao', key))

    def nut_grupo_ok(grupo, usuario=user):
        return bool(usuario and usuario.tem_algum_menu('nutricao', NUTRICAO_GRUPOS.get(grupo) or ()))

    return {
        'nutricao_cliente': cli,
        'nutricao_cliente_nome': nome,
        'nut_ok': nut_ok,
        'nut_grupo_ok': nut_grupo_ok,
    }


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


def _pacientes_somente_ativos(q=None, incluir_inativos=False):
    """Busca por nome traz também quem já teve alta. Lista inicial mostra só internados."""
    if incluir_inativos:
        return False
    return not (q or '').strip()


PACIENTES_POR_PAGINA = 50
PACIENTES_SALTO_PAGINAS = 10


def _query_pacientes(ativos_only=True, q=None):
    query = scoped_query(NutPaciente).filter(db.or_(
        NutPaciente.excluido.is_(None),
        NutPaciente.excluido.is_(False),
    ))
    if ativos_only:
        query = query.filter_by(ativo=True)
    termo = (q or '').strip()
    if termo:
        like = f'%{termo}%'
        query = query.filter(db.or_(
            NutPaciente.nome.ilike(like),
            NutPaciente.prontuario.ilike(like),
            NutPaciente.clinica.ilike(like),
            NutPaciente.enfermaria.ilike(like),
            NutPaciente.leito.ilike(like),
        ))
    return query, termo


def _ordenar_pacientes(query, termo=None):
    return query.order_by(NutPaciente.nome, NutPaciente.id)


def _list_pacientes_db(ativos_only=True, q=None, limit=50, offset=0):
    query, termo = _query_pacientes(ativos_only, q)
    query = _ordenar_pacientes(query, termo)
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)
    return [p.to_dict() for p in query.all()]


def _pagina_pacientes(ativos_only=True, q=None, page=1, page_size=None):
    """Página do cadastro. O tamanho da página é um grupo de pacientes."""
    try:
        tamanho = int(page_size or PACIENTES_POR_PAGINA)
    except (TypeError, ValueError):
        tamanho = PACIENTES_POR_PAGINA
    tamanho = min(max(tamanho, 1), 200)
    try:
        pagina = int(page or 1)
    except (TypeError, ValueError):
        pagina = 1
    pagina = max(pagina, 1)
    query, _termo = _query_pacientes(ativos_only, q)
    total = query.order_by(None).count()
    paginas = max(1, (total + tamanho - 1) // tamanho) if total else 1
    if pagina > paginas:
        pagina = paginas
    inicio = (pagina - 1) * tamanho
    return {
        'pacientes': _list_pacientes_db(ativos_only, q, limit=tamanho, offset=inicio),
        'page': pagina,
        'page_size': tamanho,
        'total': total,
        'pages': paginas,
        'salto': PACIENTES_SALTO_PAGINAS,
    }


def _usuario_sessao():
    nome = (
        session.get('user_name')
        or session.get('usuario_nome')
        or session.get('user_email')
        or ''
    )
    if not str(nome).strip() and session.get('user_id'):
        try:
            from models import Usuario
            user = Usuario.query.get(session['user_id'])
            if user:
                nome = user.nome or user.email or user.usuario or ''
        except Exception:
            pass
    nome = str(nome or '').strip()
    if not nome:
        nome = (os.environ.get('USERNAME') or os.environ.get('USER') or os.environ.get('LOGNAME') or '').strip()
    return (nome or 'sistema')[:80]


def _list_dietas_db(somente_ativas=True):
    rows = list_dietas(somente_ativas=somente_ativas)
    return rows


def _list_clinicas_db(somente_ativas=False):
    """Só o cadastro do cliente atual. Hospital sem clínicas fica vazio."""
    return list_clinicas(somente_ativas=somente_ativas)


def _mapa_linhas(data_ref, garantir=True):
    if garantir:
        garantir_mapa_do_dia(data_ref)
    rows = (
        apply_cliente_filter(
            NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True),
            NutMapaRefeicao,
        )
        .order_by(NutMapaRefeicao.clinica, NutMapaRefeicao.leito, NutMapaRefeicao.nome)
        .all()
    )
    return [r.to_dict() for r in rows]


def _get_scoped_or_404(model, pk):
    row = model.query.get(pk)
    if not row or not row_belongs_to_cliente(row):
        abort(404)
    return row


def _get_scoped(model, pk):
    row = model.query.get(pk)
    if not row or not row_belongs_to_cliente(row):
        return None
    return row


def _tag_cliente(obj):
    if obj is not None and hasattr(obj, 'cliente_id') and not obj.cliente_id:
        obj.cliente_id = write_cliente_id()
    return obj


# ---- DASHBOARD / MAPA DE PRODUÇÃO ----
@nutricao.route('/nutricao')
def dashboard():
    seed_nutricao()
    data_ref = date.today()
    # Grade só carrega no cliente após filtro de clínica
    return render_template(
        'nutricao_dashboard.html',
        mapa_linhas=[],
        data_mapa=data_ref.isoformat(),
        clinicas=_list_clinicas_db(somente_ativas=True),
        enfermarias=list_enfermarias(somente_ativas=True),
        dietas=_list_dietas_db(),
        total_pacientes=scoped_query(NutPaciente).filter_by(ativo=True).count(),
        total_dietas=scoped_query(NutDieta).filter_by(ativo=True).count(),
        total_clinicas=scoped_query(NutClinica).filter_by(ativo=True).count(),
        alertas_estoque=[],
        **active('dashboard')
    )


# ---- PACIENTES (CRUD MySQL) ----
@nutricao.route('/nutricao/pacientes')
def pacientes():
    seed_nutricao()
    clinicas = []
    rows = (
        scoped_query(NutClinica)
        .filter_by(ativo=True)
        .options(selectinload(NutClinica.enfermarias))
        .order_by(NutClinica.nome)
        .all()
    )
    for c in rows:
        item = c.to_dict()
        item['enfermarias'] = [
            {'id': e.id, 'nome': e.nome or ''}
            for e in sorted(c.enfermarias or [], key=lambda e: (e.nome or '').upper())
            if getattr(e, 'ativo', True)
        ]
        clinicas.append(item)
    q = (request.args.get('q') or '').strip()
    pagina = _pagina_pacientes(
        False,
        q=q,
        page=request.args.get('page', type=int) or 1,
        page_size=request.args.get('page_size', type=int) or PACIENTES_POR_PAGINA,
    )
    return render_template(
        'nutricao_pacientes.html',
        pacientes=pagina['pacientes'],
        paginacao=pagina,
        busca=q,
        clinicas=clinicas,
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
            clinica_m = (d.get('clinica') or p.clinica or '').strip()
            enfermaria_m = (d.get('enfermaria') or '').strip()
            leito_m = (d.get('leito') or p.leito or '').strip()
            if leito_ocupado_no_mapa(data_mapa, clinica_m, enfermaria_m, leito_m, paciente_id=p.id):
                db.session.rollback()
                return jsonify({'ok': False, 'error': MSG_LEITO_OCUPADO}), 400
            flags = {fl: bool(d.get(fl, True)) for fl in FLAG_FIELDS}
            extras = {
                'adm': _parse_date(d.get('admissao')) or p.admissao,
                'leito': d.get('leito'),
                'prontuario': d.get('prontuario'),
                'diagnostico': d.get('diagnostico'),
                'dieta': d.get('dieta'),
                'dieta_id': d.get('dieta_id'),
                'tipo_lancamento': 'principal',
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
            db.session.flush()
            garantir_grupo_lancamento(linha)
        db.session.commit()
        payload = {'ok': True, 'id': p.id, 'paciente': p.to_dict()}
        if linha:
            payload['linha'] = linha.to_dict()
        return jsonify(payload)
    q = request.args.get('q') or request.args.get('nome') or ''
    limit = request.args.get('page_size', type=int) or request.args.get('limit', type=int) or 40
    incluir = str(request.args.get('incluir_inativos') or '').lower() in ('1', 'true', 'sim')
    pagina = _pagina_pacientes(
        _pacientes_somente_ativos(q, incluir_inativos=incluir),
        q=q,
        page=request.args.get('page', type=int) or 1,
        page_size=limit,
    )
    return jsonify({
        'ok': True,
        'pacientes': pagina['pacientes'],
        'page': pagina['page'],
        'page_size': pagina['page_size'],
        'total': pagina['total'],
        'pages': pagina['pages'],
        'salto': pagina['salto'],
    })


@nutricao.route('/nutricao/api/pacientes/<int:pid>', methods=['PUT', 'DELETE'])
def api_paciente(pid):
    p = _get_scoped_or_404(NutPaciente, pid)
    if not p:
        return jsonify({'ok': False, 'error': 'Não encontrado'}), 404
    if request.method == 'DELETE':
        excluir_paciente_cadastro(p, usuario=_usuario_sessao())
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    paciente_from_payload(d, p)
    db.session.commit()
    # sincroniza snapshot cadastral de TODAS as linhas ativas de hoje (não sobrescreve dieta extra)
    hoje = date.today()
    linhas = scoped_query(NutMapaRefeicao).filter_by(
        data_refeicao=hoje, paciente_id=p.id, ativo=True
    ).all()
    for linha in linhas:
        linha.adm = p.admissao
        linha.leito = p.leito
        linha.prontuario = p.prontuario
        linha.nome = p.nome
        linha.idade = p.idade(hoje)
        linha.diagnostico = p.diagnostico
        linha.observacoes = p.observacoes
        linha.clinica = p.clinica
        linha.enfermaria = p.enfermaria
        tipo = (linha.tipo_lancamento or 'principal')
        if tipo == 'principal':
            linha.dieta = p.dieta
        marcar_alteracao_mapa(linha, _usuario_sessao())
    if linhas:
        db.session.commit()
    return jsonify({'ok': True, 'paciente': p.to_dict()})


# ---- REFEIÇÃO ACOMPANHANTE ----
def _resolve_dieta_refeicao(d):
    """Retorna (dieta_id, refeicao_nome) a partir de dieta_id e/ou refeicao/dieta texto."""
    dieta_id = d.get('dieta_id')
    refeicao = (d.get('refeicao') or d.get('dieta') or '').strip()
    dieta = None
    if dieta_id not in (None, ''):
        try:
            dieta = _get_scoped(NutDieta, int(dieta_id))
        except (TypeError, ValueError):
            dieta = None
    if not dieta and refeicao:
        dieta = scoped_query(NutDieta).filter(
            NutDieta.nome == refeicao,
            NutDieta.ativo.is_(True),
        ).first()
    if dieta:
        return dieta.id, dieta.nome
    return None, refeicao or None


def _list_acompanhantes_db(ativos_only=True, q=None, data_ref=None, paciente_id=None):
    if data_ref is not None:
        # Garante que o mapa do dia exista e acompanha os acompanhantes
        garantir_mapa_do_dia(data_ref)
        garantir_acompanhantes_do_dia(data_ref)
    query = scoped_query(NutRefeicaoAcompanhante)
    if ativos_only:
        query = query.filter_by(ativo=True)
    if paciente_id:
        try:
            query = query.filter(NutRefeicaoAcompanhante.paciente_id == int(paciente_id))
        except (TypeError, ValueError):
            pass
    if data_ref is not None:
        query = query.filter(db.or_(
            NutRefeicaoAcompanhante.data_refeicao == data_ref,
            NutRefeicaoAcompanhante.data_refeicao.is_(None),
        ))
    termo = (q or '').strip()
    if termo:
        like = f'%{termo}%'
        query = query.outerjoin(NutPaciente).filter(
            db.or_(
                NutRefeicaoAcompanhante.nome_acompanhante.ilike(like),
                NutRefeicaoAcompanhante.refeicao.ilike(like),
                NutPaciente.nome.ilike(like),
            )
        )
    query = query.order_by(NutRefeicaoAcompanhante.nome_acompanhante)
    rows = query.all()
    # Pré-calcula pacientes ainda no mapa (1 query) para bloquear exclusão na UI
    pids = {r.paciente_id for r in rows if r.paciente_id}
    no_mapa = set()
    if pids:
        no_mapa = {
            mid for (mid,) in (
                db.session.query(NutMapaRefeicao.paciente_id)
                .filter(
                    NutMapaRefeicao.paciente_id.in_(pids),
                    NutMapaRefeicao.ativo.is_(True),
                )
                .distinct()
                .all()
            )
        }
    return [r.to_dict(exclusao_bloqueada=(r.paciente_id in no_mapa)) for r in rows]


def _list_funcionarios_refeicao_db(ativos_only=True, q=None, data_ref=None):
    query = scoped_query(NutRefeicaoFuncionario)
    if ativos_only:
        query = query.filter_by(ativo=True)
    if data_ref is not None:
        query = query.filter(db.or_(
            NutRefeicaoFuncionario.data_refeicao == data_ref,
            NutRefeicaoFuncionario.data_refeicao.is_(None),
        ))
    termo = (q or '').strip()
    if termo:
        like = f'%{termo}%'
        query = query.filter(
            db.or_(
                NutRefeicaoFuncionario.nome.ilike(like),
                NutRefeicaoFuncionario.refeicao.ilike(like),
            )
        )
    query = query.order_by(NutRefeicaoFuncionario.nome)
    return [r.to_dict() for r in query.all()]


def _parse_bool_flag(d, key, default=True):
    if key not in d:
        return default
    v = d.get(key)
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).strip().lower() in ('1', 'true', 'sim', 'on', 'yes')


@nutricao.route('/nutricao/refeicao-acompanhante')
def refeicao_acompanhante():
    from nutricao_service import info_lancamento_refeicoes, mapa_horas_limite
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    return render_template(
        'nutricao_refeicao_acompanhante.html',
        acompanhantes=_list_acompanhantes_db(True, data_ref=data_ref),
        dietas=_list_dietas_db(somente_ativas=True),
        pacientes=_list_pacientes_db(True, limit=500),
        data_padrao=data_ref.isoformat(),
        horas_limite=mapa_horas_limite(),
        lancamento_info=info_lancamento_refeicoes(data_ref),
        **active('refeicao_acompanhante'),
    )


@nutricao.route('/nutricao/api/refeicao-acompanhantes', methods=['GET', 'POST'])
def api_refeicao_acompanhantes():
    from nutricao_service import resolver_partes_acompanhante
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome_acompanhante') or d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do acompanhante é obrigatório'}), 400
        paciente_id = d.get('paciente_id')
        try:
            paciente_id = int(paciente_id)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Paciente é obrigatório'}), 400
        pac = _get_scoped(NutPaciente, paciente_id)
        if not pac:
            return jsonify({'ok': False, 'error': 'Paciente não encontrado'}), 404
        dieta_id, refeicao = _resolve_dieta_refeicao(d)
        if not refeicao and not dieta_id:
            return jsonify({'ok': False, 'error': 'Selecione uma dieta/refeição'}), 400
        quantidade = _parse_quantidade_refeicao(d, default=1)
        if quantidade is None:
            return jsonify({'ok': False, 'error': 'Quantidade deve ser um número >= 1'}), 400
        data_ref = _parse_date(d.get('data_refeicao') or d.get('data')) or date.today()
        fl_almoco = _parse_bool_flag(d, 'fl_almoco', True)
        fl_jantar = _parse_bool_flag(d, 'fl_jantar', True)
        if not fl_almoco and not fl_jantar:
            return jsonify({'ok': False, 'error': 'Marque Almoço e/ou Jantar'}), 400

        partes = resolver_partes_acompanhante(data_ref, fl_almoco, fl_jantar)
        if not partes:
            return jsonify({'ok': False, 'error': 'Marque Almoço e/ou Jantar'}), 400

        criados = []
        avisos = []
        for parte in partes:
            row = NutRefeicaoAcompanhante(
                cliente_id=getattr(pac, 'cliente_id', None) or write_cliente_id(),
                nome_acompanhante=nome,
                paciente_id=pac.id,
                dieta_id=dieta_id,
                refeicao=refeicao,
                quantidade=quantidade,
                data_refeicao=parte['data_refeicao'],
                fl_almoco=bool(parte['fl_almoco']),
                fl_jantar=bool(parte['fl_jantar']),
                ativo=True,
            )
            db.session.add(row)
            db.session.flush()
            criados.append(row.to_dict())
            if parte.get('aviso'):
                avisos.append(parte['aviso'])

        db.session.commit()
        data_destino = partes[-1]['data_refeicao'].isoformat() if any(p.get('adiadas') for p in partes) else data_ref.isoformat()
        aviso = avisos[0] if len(avisos) == 1 else (
            'A refeição será lançada para o dia seguinte.' if avisos else ''
        )
        # se tudo foi adiado, aponta a data de destino para o front redirecionar
        so_adiado = all(p.get('adiadas') for p in partes)
        return jsonify({
            'ok': True,
            'id': criados[0]['id'] if criados else None,
            'acompanhante': criados[0] if criados else None,
            'acompanhantes': criados,
            'adiado': bool(avisos),
            'aviso': aviso or (
                'A refeição será lançada para o dia seguinte.' if so_adiado else ''
            ),
            'data_destino': data_destino if avisos else data_ref.isoformat(),
        })
    q = request.args.get('q') or ''
    ativos = str(request.args.get('ativos', '1')).lower() not in ('0', 'false', 'nao', 'não')
    data_ref = _parse_date(request.args.get('data'))
    paciente_id = request.args.get('paciente_id', type=int)
    return jsonify({
        'ok': True,
        'acompanhantes': _list_acompanhantes_db(ativos, q=q, data_ref=data_ref, paciente_id=paciente_id),
    })


@nutricao.route('/nutricao/api/refeicao-acompanhantes/<int:aid>', methods=['PUT', 'DELETE'])
def api_refeicao_acompanhante_ops(aid):
    from nutricao_service import resolver_partes_acompanhante
    row = _get_scoped_or_404(NutRefeicaoAcompanhante, aid)
    if not row:
        return jsonify({'ok': False, 'error': 'Não encontrado'}), 404
    if request.method == 'DELETE':
        # Lançado com paciente: só sai quando o paciente sair do mapa
        if row.paciente_id and paciente_ativo_no_mapa(row.paciente_id):
            return jsonify({
                'ok': False,
                'error': MSG_ACOMP_SO_SAIDA_MAPA,
                'exclusao_bloqueada': True,
            }), 409
        row.ativo = False
        row.data_saida = date.today()
        row.motivo_saida = 'Exclusão'
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome_acompanhante' in d or 'nome' in d:
        nome = (d.get('nome_acompanhante') or d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do acompanhante é obrigatório'}), 400
        row.nome_acompanhante = nome
    if 'paciente_id' in d and d.get('paciente_id') not in (None, ''):
        try:
            pid = int(d.get('paciente_id'))
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Paciente inválido'}), 400
        pac = _get_scoped(NutPaciente, pid)
        if not pac:
            return jsonify({'ok': False, 'error': 'Paciente não encontrado'}), 404
        row.paciente_id = pac.id
        if not row.cliente_id:
            row.cliente_id = getattr(pac, 'cliente_id', None) or write_cliente_id()
    if any(k in d for k in ('dieta_id', 'refeicao', 'dieta')):
        dieta_id, refeicao = _resolve_dieta_refeicao(d)
        if not refeicao and not dieta_id:
            return jsonify({'ok': False, 'error': 'Selecione uma dieta/refeição'}), 400
        row.dieta_id = dieta_id
        row.refeicao = refeicao
    if 'quantidade' in d:
        quantidade = _parse_quantidade_refeicao(d)
        if quantidade is None:
            return jsonify({'ok': False, 'error': 'Quantidade deve ser um número >= 1'}), 400
        row.quantidade = quantidade

    data_ref = row.data_refeicao or date.today()
    if 'data_refeicao' in d or 'data' in d:
        parsed = _parse_date(d.get('data_refeicao') or d.get('data'))
        if parsed:
            data_ref = parsed

    fl_almoco = row.fl_almoco if row.fl_almoco is not None else True
    fl_jantar = row.fl_jantar if row.fl_jantar is not None else True
    if 'fl_almoco' in d:
        fl_almoco = _parse_bool_flag(d, 'fl_almoco', True)
    if 'fl_jantar' in d:
        fl_jantar = _parse_bool_flag(d, 'fl_jantar', True)
    if not fl_almoco and not fl_jantar:
        return jsonify({'ok': False, 'error': 'Marque Almoço e/ou Jantar'}), 400

    partes = resolver_partes_acompanhante(data_ref, fl_almoco, fl_jantar)
    avisos = [p['aviso'] for p in partes if p.get('aviso')]

    # 1ª parte atualiza o registro; demais criam novos (ex.: A amanhã + J hoje)
    primeira = partes[0]
    row.data_refeicao = primeira['data_refeicao']
    row.fl_almoco = bool(primeira['fl_almoco'])
    row.fl_jantar = bool(primeira['fl_jantar'])
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))

    extras = []
    for parte in partes[1:]:
        novo = NutRefeicaoAcompanhante(
            cliente_id=row.cliente_id or write_cliente_id(),
            nome_acompanhante=row.nome_acompanhante,
            paciente_id=row.paciente_id,
            dieta_id=row.dieta_id,
            refeicao=row.refeicao,
            quantidade=row.quantidade,
            data_refeicao=parte['data_refeicao'],
            fl_almoco=bool(parte['fl_almoco']),
            fl_jantar=bool(parte['fl_jantar']),
            ativo=True,
        )
        db.session.add(novo)
        db.session.flush()
        extras.append(novo.to_dict())

    db.session.commit()
    aviso = avisos[0] if len(avisos) == 1 else (
        'A refeição será lançada para o dia seguinte.' if avisos else ''
    )
    return jsonify({
        'ok': True,
        'acompanhante': row.to_dict(),
        'acompanhantes_extra': extras,
        'adiado': bool(avisos),
        'aviso': aviso,
        'data_destino': (partes[-1]['data_refeicao'].isoformat() if avisos else data_ref.isoformat()),
    })

# ---- REFEIÇÕES FUNCIONÁRIOS ----
@nutricao.route('/nutricao/refeicoes-funcionarios')
def refeicoes_funcionarios():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    return render_template(
        'nutricao_refeicoes_funcionarios.html',
        funcionarios=_list_funcionarios_refeicao_db(True, data_ref=data_ref),
        dietas=_list_dietas_db(somente_ativas=True),
        data_padrao=data_ref.isoformat(),
        **active('refeicoes_funcionarios'),
    )


def _parse_quantidade_refeicao(d, default=1):
    raw = d.get('quantidade', default)
    try:
        qtd = int(raw)
    except (TypeError, ValueError):
        return None
    if qtd < 1:
        return None
    return qtd


@nutricao.route('/nutricao/api/refeicao-funcionarios', methods=['GET', 'POST'])
def api_refeicao_funcionarios():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome é obrigatório'}), 400
        dieta_id, refeicao = _resolve_dieta_refeicao(d)
        if not refeicao and not dieta_id:
            return jsonify({'ok': False, 'error': 'Informe a refeição/dieta'}), 400
        quantidade = _parse_quantidade_refeicao(d, default=1)
        if quantidade is None:
            return jsonify({'ok': False, 'error': 'Quantidade deve ser um número >= 1'}), 400
        data_ref = _parse_date(d.get('data_refeicao') or d.get('data')) or date.today()
        fl_almoco = _parse_bool_flag(d, 'fl_almoco', True)
        fl_jantar = _parse_bool_flag(d, 'fl_jantar', True)
        row = NutRefeicaoFuncionario(
            cliente_id=write_cliente_id(),
            nome=nome,
            dieta_id=dieta_id,
            refeicao=refeicao,
            quantidade=quantidade,
            data_refeicao=data_ref,
            fl_almoco=fl_almoco,
            fl_jantar=fl_jantar,
            ativo=True,
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'funcionario': row.to_dict()})
    q = request.args.get('q') or ''
    ativos = str(request.args.get('ativos', '1')).lower() not in ('0', 'false', 'nao', 'não')
    data_ref = _parse_date(request.args.get('data'))
    return jsonify({
        'ok': True,
        'funcionarios': _list_funcionarios_refeicao_db(ativos, q=q, data_ref=data_ref),
    })


@nutricao.route('/nutricao/api/refeicao-funcionarios/<int:fid>', methods=['PUT', 'DELETE'])
def api_refeicao_funcionario_ops(fid):
    row = _get_scoped_or_404(NutRefeicaoFuncionario, fid)
    if not row:
        return jsonify({'ok': False, 'error': 'Não encontrado'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome é obrigatório'}), 400
        row.nome = nome
    if any(k in d for k in ('dieta_id', 'refeicao', 'dieta')):
        dieta_id, refeicao = _resolve_dieta_refeicao(d)
        if not refeicao and not dieta_id:
            return jsonify({'ok': False, 'error': 'Informe a refeição/dieta'}), 400
        row.dieta_id = dieta_id
        row.refeicao = refeicao
    if 'quantidade' in d:
        quantidade = _parse_quantidade_refeicao(d)
        if quantidade is None:
            return jsonify({'ok': False, 'error': 'Quantidade deve ser um número >= 1'}), 400
        row.quantidade = quantidade
    if 'data_refeicao' in d or 'data' in d:
        data_ref = _parse_date(d.get('data_refeicao') or d.get('data'))
        if data_ref:
            row.data_refeicao = data_ref
    if 'fl_almoco' in d:
        row.fl_almoco = _parse_bool_flag(d, 'fl_almoco', True)
    if 'fl_jantar' in d:
        row.fl_jantar = _parse_bool_flag(d, 'fl_jantar', True)
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    db.session.commit()
    return jsonify({'ok': True, 'funcionario': row.to_dict()})


# ---- MAPA API ----
@nutricao.route('/nutricao/api/mapa', methods=['GET'])
def api_mapa_get():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    _seed_aviso_alta_demo(data_ref)
    uma = str(request.args.get('uma') or '').strip().lower() in ('1', 'true', 'sim', 'on')
    grupo = (request.args.get('grupo_clinica') or '').strip()
    clinica = (request.args.get('clinica') or '').strip()
    if uma:
        garantir_mapa_do_dia(data_ref)
        separar_lancamentos_uma(data_ref)
        return jsonify({
            'ok': True,
            'uma': True,
            'data': data_ref.isoformat(),
            'linhas': listar_linhas_mapa_uma(data_ref),
            'avisos_alta': listar_avisos_alta_mapa(data_ref, garantir=False),
        })
    # Clínica/grupo: a tela só usa a grade. Não serializa o hospital inteiro.
    if grupo or clinica:
        garantir_mapa_do_dia(data_ref)
        separar_lancamentos_uma(data_ref)
        if grupo == '__todas__' or clinica == '__todas__':
            grade = montar_grade_leitos_mapa(data_ref, clinica_nome='__todas__')
        elif grupo:
            gid = int(grupo) if grupo.isdigit() else None
            nomes = nomes_clinicas_do_grupo(grupo_id=gid, grupo_nome=None if gid else grupo)
            grade = montar_grade_leitos_mapa(data_ref, clinica_nomes=nomes)
        else:
            grade = montar_grade_leitos_mapa(data_ref, clinica_nome=clinica)
        return jsonify({
            'ok': True,
            'data': data_ref.isoformat(),
            'linhas': [],
            'grade': grade,
            'avisos_alta': listar_avisos_alta_mapa(data_ref, garantir=False),
        })
    linhas = _mapa_linhas(data_ref)
    return jsonify({
        'ok': True,
        'data': data_ref.isoformat(),
        'linhas': linhas,
        'grade': [],
        'clinicas': _list_clinicas_db(somente_ativas=True),
        'enfermarias': list_enfermarias(somente_ativas=True),
        'avisos_alta': listar_avisos_alta_mapa(data_ref, garantir=False),
    })


@nutricao.route('/nutricao/api/mapa/inserir', methods=['POST'])
def api_mapa_inserir():
    """Insere paciente existente (ou atualiza cadastro) no mapa do dia."""
    seed_nutricao()
    d = request.get_json(force=True) or {}
    paciente_id = d.get('paciente_id')
    p = _get_scoped_or_404(NutPaciente, paciente_id) if paciente_id else None
    if not p:
        return jsonify({'ok': False, 'error': 'Selecione um paciente cadastrado'}), 400

    # atualiza dados básicos do cadastro se enviados
    for campo in ('prontuario', 'diagnostico', 'dieta', 'observacoes', 'clinica', 'enfermaria', 'leito'):
        if campo in d and d.get(campo) is not None:
            setattr(p, campo, (str(d.get(campo)).strip() or None))
    if 'admissao' in d:
        p.admissao = _parse_date(d.get('admissao')) or p.admissao

    data_mapa = _parse_date(d.get('data_mapa')) or date.today()
    tipo = normalizar_tipo_lancamento(
        d.get('tipo_lancamento') or ('substituicao' if d.get('substituicao') else None),
        'principal',
    )
    nova_dieta = bool(d.get('nova_dieta') or d.get('substituicao') or tipo in ('adicional', 'substituicao'))
    existe = scoped_query(NutMapaRefeicao).filter_by(
        data_refeicao=data_mapa, paciente_id=p.id, ativo=True
    ).first()
    if existe and not nova_dieta:
        return jsonify({'ok': False, 'error': 'Paciente já está no mapa deste dia'}), 400
    if nova_dieta and not existe:
        return jsonify({'ok': False, 'error': 'Paciente ainda não está no mapa deste dia'}), 400

    clinica = (d.get('clinica') or '').strip() or (existe.clinica if existe else '')
    enfermaria = (d.get('enfermaria') or '').strip() or (existe.enfermaria if existe else '')
    leito = (d.get('leito') or '').strip() or (existe.leito if existe else '')
    if not nova_dieta:
        if not clinica:
            return jsonify({'ok': False, 'error': 'Informe a clínica'}), 400
        if not enfermaria:
            return jsonify({'ok': False, 'error': 'Informe a enfermaria'}), 400
        if not leito:
            return jsonify({'ok': False, 'error': 'Informe o leito'}), 400

    if leito_ocupado_no_mapa(data_mapa, clinica, enfermaria, leito, paciente_id=p.id):
        return jsonify({'ok': False, 'error': MSG_LEITO_OCUPADO}), 400

    if nova_dieta:
        src = existe
        origem_id = d.get('origem_mapa_id') or d.get('mapa_id')
        if origem_id:
            src = _get_scoped_or_404(NutMapaRefeicao, origem_id) or src
            if src and (src.paciente_id and int(src.paciente_id) != int(p.id)):
                return jsonify({'ok': False, 'error': 'Lançamento de origem não pertence a este paciente'}), 400
        flags = {fl: bool(d.get(fl, False)) for fl in FLAG_FIELDS}
        extras = {
            'dieta': d.get('dieta'),
            'dieta_id': d.get('dieta_id'),
            'observacoes': d.get('observacoes'),
            'obs_etiqueta': d.get('obs_etiqueta'),
            'extras': d.get('extras'),
            'suplementos': d.get('suplementos'),
            'enteral': d.get('enteral'),
            'formula_infantil': d.get('formula_infantil'),
            'lve': d.get('lve'),
        }
        linha = criar_lancamento_dieta_desde_linha(
            src, flags=flags, extras=extras, usuario=_usuario_sessao(), tipo_lancamento=tipo,
        )
        db.session.add(linha)
        db.session.flush()
        garantir_grupo_lancamento(linha)
        db.session.commit()
        return jsonify({'ok': True, 'linha': linha.to_dict(), 'paciente': p.to_dict(), 'novo_lancamento': True})

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
        'dieta_id': d.get('dieta_id'),
        'tipo_lancamento': 'principal',
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
    db.session.flush()
    garantir_grupo_lancamento(linha)
    db.session.commit()
    return jsonify({'ok': True, 'linha': linha.to_dict(), 'paciente': p.to_dict()})


@nutricao.route('/nutricao/api/mapa/<int:mid>/lancamento', methods=['POST'])
def api_mapa_novo_lancamento(mid):
    """Cria nova dieta ou substituição vinculada ao mesmo paciente/leito."""
    seed_nutricao()
    src = _get_scoped_or_404(NutMapaRefeicao, mid)
    if not src or not src.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    if not src.paciente_id:
        return jsonify({'ok': False, 'error': 'Lançamento sem paciente cadastrado'}), 400
    d = request.get_json(force=True) or {}
    tipo = normalizar_tipo_lancamento(
        d.get('tipo_lancamento') or ('substituicao' if d.get('substituicao') else 'adicional'),
        'adicional',
    )
    if tipo == 'principal':
        tipo = 'adicional'
    dieta_nome = (d.get('dieta') or '').strip()
    if not dieta_nome and not d.get('dieta_id'):
        return jsonify({'ok': False, 'error': 'Selecione a dieta do novo lançamento'}), 400
    flags = {fl: bool(d.get(fl, False)) for fl in FLAG_FIELDS}
    if not any(flags.values()):
        return jsonify({'ok': False, 'error': 'Marque ao menos uma refeição (D C A M J C)'}), 400
    extras = {
        'dieta': dieta_nome,
        'dieta_id': d.get('dieta_id'),
        'observacoes': d.get('observacoes'),
        'obs_etiqueta': d.get('obs_etiqueta'),
        'extras': d.get('extras'),
        'suplementos': d.get('suplementos'),
        'enteral': d.get('enteral'),
        'formula_infantil': d.get('formula_infantil'),
        'lve': d.get('lve'),
    }
    linha = criar_lancamento_dieta_desde_linha(
        src, flags=flags, extras=extras, usuario=_usuario_sessao(), tipo_lancamento=tipo,
    )
    db.session.add(linha)
    db.session.flush()
    garantir_grupo_lancamento(linha)
    db.session.commit()
    return jsonify({
        'ok': True,
        'linha': linha.to_dict(),
        'origem_id': src.id,
        'paciente_id': src.paciente_id,
        'novo_lancamento': True,
    })


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
    from nutricao_service import (
        info_lancamento_refeicoes, obter_ou_criar_linha_mapa_dia, MEAL_FLAG_FIELD,
        refeicao_apos_hora_limite, data_destino_lancamento,
    )
    row = _get_scoped_or_404(NutMapaRefeicao, mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    d = request.get_json(force=True) or {}

    def _campo_loc(nome):
        if nome in d:
            val = d.get(nome)
            return (str(val).strip() if val is not None else '') or None
        return getattr(row, nome, None)

    clinica_f = _campo_loc('clinica')
    enfermaria_f = _campo_loc('enfermaria')
    leito_f = _campo_loc('leito')
    if leito_ocupado_no_mapa(
        row.data_refeicao, clinica_f, enfermaria_f, leito_f,
        exclude_id=row.id, paciente_id=row.paciente_id,
    ):
        return jsonify({'ok': False, 'error': MSG_LEITO_OCUPADO}), 400

    campos_cadastro = (
        'leito', 'prontuario', 'nome', 'diagnostico', 'dieta', 'observacoes', 'clinica', 'enfermaria',
        'obs_etiqueta', 'extras', 'suplementos', 'enteral', 'formula_infantil', 'lve',
    )
    campos_uma = ('suplementos', 'enteral', 'formula_infantil', 'lve')
    if any(campo in d for campo in campos_uma):
        aplicar_campos_uma_independentes(
            row, d, usuario=_usuario_sessao(), apagar_vazio=bool(d.get('uma_explicito')),
        )
    for campo in campos_cadastro:
        if campo in campos_uma:
            continue
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

    avisos = []
    # flags por refeição: respeitam hora limite
    for fl in FLAG_FIELDS:
        if fl not in d:
            continue
        meal = next((m for m, f in MEAL_FLAG_FIELD.items() if f == fl), None)
        valor = bool(d.get(fl))
        if meal and refeicao_apos_hora_limite(meal, row.data_refeicao):
            dest = data_destino_lancamento(meal, row.data_refeicao)
            target = obter_ou_criar_linha_mapa_dia(row, dest, usuario=_usuario_sessao())
            if target:
                setattr(target, fl, valor)
                marcar_alteracao_mapa(target, _usuario_sessao())
                avisos.append(f'{meal} → {dest.strftime("%d/%m/%Y")}')
            continue
        setattr(row, fl, valor)

    marcar_alteracao_mapa(row, _usuario_sessao())

    # após qualquer hora limite, propaga cadastro (dieta etc.) para o dia seguinte
    lanc = info_lancamento_refeicoes(row.data_refeicao)
    if any(i.get('apos_limite') for i in lanc.values()) and any(c in d for c in campos_cadastro):
        # usa o maior data_destino entre refeições fechadas
        destinos = [
            date.fromisoformat(i['data_destino'])
            for i in lanc.values() if i.get('apos_limite')
        ]
        if destinos:
            dest = max(destinos)
            target = obter_ou_criar_linha_mapa_dia(row, dest, usuario=_usuario_sessao())
            if target:
                for campo in campos_cadastro:
                    if campo in campos_uma or campo not in d:
                        continue
                    setattr(target, campo, getattr(row, campo))
                if 'idade' in d:
                    target.idade = row.idade
                if 'adm' in d:
                    target.adm = row.adm
                marcar_alteracao_mapa(target, _usuario_sessao())
                avisos.append(
                    f'Cadastro também aplicado em {dest.strftime("%d/%m/%Y")} '
                    '(refeições após a hora limite).'
                )

    db.session.commit()
    return jsonify({
        'ok': True,
        'linha': row.to_dict(),
        'aviso': ' '.join(avisos) if avisos else '',
        'adiado': bool(avisos),
    })


@nutricao.route('/nutricao/api/mapa/<int:mid>/saida', methods=['POST'])
def api_mapa_saida(mid):
    """Alta médica, óbito ou transferência externa — baixa com histórico (não apaga a linha)."""
    seed_nutricao()
    row = _get_scoped_or_404(NutMapaRefeicao, mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    d = request.get_json(force=True) or {}
    tipo = (d.get('motivo') or d.get('tipo') or '').strip().lower()
    if not tipo:
        return jsonify({'ok': False, 'error': 'Selecione o motivo da saída'}), 400
    usuario = _usuario_sessao()
    if tipo in ('apagar_lancamento', 'apagar'):
        if not eh_lancamento_uma(row.tipo_lancamento):
            return jsonify({
                'ok': False,
                'error': 'Só dá para apagar lançamento de LVE, fórmula infantil, enteral ou suplemento.',
            }), 400
        apagar_lancamento_uma(row, usuario=usuario)
        db.session.commit()
        return jsonify({'ok': True, 'acao': 'apagar_lancamento'})
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
    from nutricao_service import (
        FLAG_TO_MEAL, data_destino_lancamento, obter_ou_criar_linha_mapa_dia,
        refeicao_apos_hora_limite, mapa_horas_limite, MEAL_LABELS,
    )
    row = _get_scoped_or_404(NutMapaRefeicao, mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    d = request.get_json(force=True) or {}
    campo = (d.get('campo') or '').strip()
    if campo not in FLAG_FIELDS:
        return jsonify({'ok': False, 'error': 'Campo inválido'}), 400

    meal = FLAG_TO_MEAL.get(campo)
    aviso = ''
    target = row
    if meal and refeicao_apos_hora_limite(meal, row.data_refeicao):
        dest = data_destino_lancamento(meal, row.data_refeicao)
        target = obter_ou_criar_linha_mapa_dia(row, dest, usuario=_usuario_sessao())
        if not target:
            return jsonify({'ok': False, 'error': 'Não foi possível lançar no dia seguinte'}), 400
        hora = mapa_horas_limite().get(meal) or ''
        aviso = (
            f'Após {hora}, {MEAL_LABELS.get(meal, meal)} foi lançado em '
            f'{dest.strftime("%d/%m/%Y")}.'
        )

    if 'valor' in d:
        setattr(target, campo, bool(d.get('valor')))
    else:
        setattr(target, campo, not bool(getattr(target, campo)))
    marcar_alteracao_mapa(target, _usuario_sessao())
    db.session.commit()
    # se adiou, a linha do dia atual permanece; devolve ambas infos
    resp = {'ok': True, 'linha': row.to_dict(), 'aviso': aviso}
    if target.id != row.id:
        resp['linha_destino'] = target.to_dict()
        resp['adiado'] = True
        # UI do dia atual: não muda o indicador de hoje
        resp['linha'] = row.to_dict()
    else:
        resp['linha'] = target.to_dict()
    return jsonify(resp)


@nutricao.route('/nutricao/api/mapa/<int:mid>/substituicoes', methods=['GET', 'PUT'])
def api_mapa_substituicoes(mid):
    """Cardápio padrão + substituições (cardápio personalizado) da linha do mapa."""
    seed_nutricao()
    row = _get_scoped_or_404(NutMapaRefeicao, mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404

    if request.method == 'GET':
        return jsonify(get_mapa_substituicoes(row))

    d = request.get_json(force=True) or {}
    result = save_mapa_substituicoes(row, d, usuario=_usuario_sessao())
    if isinstance(result, dict) and result.get('erro'):
        db.session.rollback()
        return jsonify({'ok': False, 'error': result['erro']}), 400
    db.session.commit()
    payload = get_mapa_substituicoes(row)
    if isinstance(result, dict):
        payload['meals_adiados'] = result.get('meals_adiados') or []
        payload['aviso_salvamento'] = result.get('aviso') or ''
    return jsonify(payload)


@nutricao.route('/nutricao/api/mapa/<int:mid>/substituicoes/opcoes', methods=['GET'])
def api_mapa_substituicoes_opcoes(mid):
    """Itens da dieta nesta refeição e produtos do setor correspondente. Uma aba por vez."""
    seed_nutricao()
    row = _get_scoped_or_404(NutMapaRefeicao, mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    meal = (request.args.get('meal') or '').strip().lower()
    payload = opcoes_itens_refeicao(row, meal)
    if payload.get('ok') is False:
        return jsonify(payload), 400
    return jsonify(payload)


@nutricao.route('/nutricao/api/mapa/<int:mid>/substituicoes/importar', methods=['POST'])
def api_mapa_substituicoes_importar(mid):
    """Importa pares ou justificativa do mapa anterior do mesmo paciente."""
    seed_nutricao()
    row = _get_scoped_or_404(NutMapaRefeicao, mid)
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


@nutricao.route('/nutricao/api/mapa/<int:mid>/substituicoes/justificativas', methods=['GET'])
def api_mapa_substituicoes_justificativas(mid):
    """Lista justificativas anteriores do mesmo paciente (para popup de importação)."""
    seed_nutricao()
    row = _get_scoped_or_404(NutMapaRefeicao, mid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Linha não encontrada'}), 404
    meal = (request.args.get('meal') or '').strip().lower() or None
    todas = str(request.args.get('todas', '0')).lower() in ('1', 'true', 'sim')
    items = listar_justificativas_anteriores(
        row,
        meal=None if todas else meal,
        limit=40,
    )
    return jsonify({'ok': True, 'justificativas': items, 'meal': meal})


def _filtro_nome_imprimir(imprimir_por, filtro_id, filtro_nome):
    filtro_nome = (filtro_nome or '').strip() or None
    if filtro_nome or not filtro_id:
        return filtro_nome
    try:
        filtro_id = int(filtro_id)
    except (TypeError, ValueError):
        return filtro_nome
    if imprimir_por == 'grupo_clinica':
        grp = _get_scoped(NutGrupoClinica, filtro_id)
        return (grp.nome if grp else None)
    if imprimir_por == 'clinica':
        cli = _get_scoped(NutClinica, filtro_id)
        return (cli.nome if cli else None)
    if imprimir_por == 'enfermaria':
        enf = _get_scoped(NutEnfermaria, filtro_id)
        return (enf.nome if enf else None)
    return filtro_nome


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
        if scoped_query(NutClinica).filter_by(nome=nome).first():
            return jsonify({'ok': False, 'error': 'Já existe clínica com este nome'}), 400
        row = NutClinica(
            cliente_id=write_cliente_id(),
            nome=nome,
            centro_custo=(d.get('centro_custo') or '').strip() or None,
            ativo=bool(d.get('ativo', True)),
        )
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'clinica': row.to_dict()})
    somente_ativas = str(request.args.get('ativas', '')).lower() in ('1', 'true', 'sim')
    return jsonify(_list_clinicas_db(somente_ativas=somente_ativas))


@nutricao.route('/nutricao/api/clinicas/<int:cid>', methods=['PUT', 'DELETE'])
def api_clinica_ops(cid):
    row = _get_scoped_or_404(NutClinica, cid)
    if not row:
        return jsonify({'ok': False, 'error': 'Clínica não encontrada'}), 404

    if request.method == 'DELETE':
        vinculadas = list(row.enfermarias or [])
        if vinculadas:
            nomes = [e.nome for e in vinculadas if (e.nome or '').strip()]
            lista = ', '.join(nomes[:8])
            if len(nomes) > 8:
                lista += f' (+{len(nomes) - 8})'
            qtd = len(nomes) or len(vinculadas)
            return jsonify({
                'ok': False,
                'bloqueado': True,
                'clinica_id': row.id,
                'enfermaria_ids': [e.id for e in vinculadas],
                'error': (
                    f'Não é possível excluir a clínica. Remova o vínculo de '
                    f'{qtd} enfermaria{"s" if qtd != 1 else ""}'
                    f'{(" (" + lista + ")") if lista else ""} '
                    f'em Cadastro → Enfermarias e tente de novo.'
                ),
            }), 409
        row.grupos_clinica = []
        db.session.delete(row)
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da clínica é obrigatório'}), 400
        outro = scoped_query(NutClinica).filter(
            NutClinica.nome == nome, NutClinica.id != cid
        ).first()
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
    clinica = _get_scoped_or_404(NutClinica, cid)
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

    # Replace the full set of links for this clínica (empty list unlinks all).
    selecionadas = scoped_query(NutEnfermaria).filter(
        NutEnfermaria.id.in_(ids),
        NutEnfermaria.ativo.is_(True),
    ).all() if ids else []
    clinica.enfermarias = selecionadas
    db.session.commit()
    return jsonify({'ok': True, 'clinica': clinica.to_dict(include_enfermarias=True)})


# ---- GRUPOS DE CLÍNICAS (removido) ----
def _grupo_clinica_removido():
    return jsonify({
        'ok': False,
        'error': 'O cadastro de grupo de clínicas foi removido. Use o cadastro de clínicas.',
    }), 410


@nutricao.route('/nutricao/grupos-clinicas')
def grupos_clinicas():
    return redirect(url_for('nutricao.clinicas'))


@nutricao.route('/nutricao/api/grupos-clinicas', methods=['GET', 'POST'])
def api_grupos_clinicas():
    return _grupo_clinica_removido()


@nutricao.route('/nutricao/api/grupos-clinicas/<int:gid>', methods=['GET', 'PUT', 'DELETE'])
def api_grupo_clinica_ops(gid):
    return _grupo_clinica_removido()


@nutricao.route('/nutricao/api/grupos-clinicas/<int:gid>/clinicas', methods=['GET', 'PUT'])
def api_grupo_clinica_clinicas(gid):
    return _grupo_clinica_removido()


@nutricao.route('/nutricao/enfermarias')
def enfermarias():
    seed_nutricao()
    clinica_id = request.args.get('clinica_id', type=int)
    return render_template(
        'nutricao_enfermarias.html',
        enfermarias=list_enfermarias(somente_ativas=False),
        clinicas=list_clinicas(somente_ativas=True),
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
        if scoped_query(NutEnfermaria).filter_by(nome=nome).first():
            return jsonify({'ok': False, 'error': 'Já existe enfermaria com este nome'}), 400
        row = NutEnfermaria(
            cliente_id=write_cliente_id(),
            nome=nome,
            ativo=bool(d.get('ativo', True)),
            nutriz=bool(d.get('nutriz', False)),
        )
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'enfermaria': row.to_dict()})
    somente_ativas = str(request.args.get('ativas', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_enfermarias(somente_ativas=somente_ativas))


@nutricao.route('/nutricao/api/enfermarias/<int:eid>', methods=['PUT', 'DELETE'])
def api_enfermaria_ops(eid):
    row = _get_scoped_or_404(NutEnfermaria, eid)
    if not row:
        return jsonify({'ok': False, 'error': 'Enfermaria não encontrada'}), 404

    if request.method == 'DELETE':
        leitos = list(row.leitos or [])
        if leitos:
            nomes = [(l.nome or str(l.numero or '')).strip() for l in leitos]
            nomes = [n for n in nomes if n]
            lista = ', '.join(nomes[:8])
            if len(nomes) > 8:
                lista += f' (+{len(nomes) - 8})'
            qtd = len(leitos)
            return jsonify({
                'ok': False,
                'bloqueado': True,
                'enfermaria_id': row.id,
                'leito_ids': [l.id for l in leitos],
                'error': (
                    f'Não é possível excluir a enfermaria. Exclua '
                    f'{qtd} leito{"s" if qtd != 1 else ""} vinculado{"s" if qtd != 1 else ""}'
                    f'{(" (" + lista + ")") if lista else ""} '
                    f'em Cadastro → Leitos e tente de novo.'
                ),
            }), 409
        row.clinicas = []
        db.session.delete(row)
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da enfermaria é obrigatório'}), 400
        outro = scoped_query(NutEnfermaria).filter(
            NutEnfermaria.nome == nome, NutEnfermaria.id != eid
        ).first()
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
    row = _get_scoped_or_404(NutEnfermaria, eid)
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
        enf = _get_scoped_or_404(NutEnfermaria, enfermaria_id)
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
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'leito': row.to_dict(), 'enfermaria': enf.to_dict()})

    # Leitos vagos no mapa do dia (cadastrados e sem paciente)
    if str(request.args.get('vagos', '')).lower() in ('1', 'true', 'sim'):
        data_ref = _parse_date(request.args.get('data')) or date.today()
        clinica = (request.args.get('clinica') or '').strip() or None
        enfermaria = (request.args.get('enfermaria') or '').strip() or None
        enfermaria_id = request.args.get('enfermaria_id', type=int)
        exclude_mapa_id = request.args.get('exclude_mapa_id', type=int)
        result = list_leitos_vagos(
            data_ref=data_ref,
            clinica=clinica,
            enfermaria=enfermaria,
            enfermaria_id=enfermaria_id,
            exclude_mapa_id=exclude_mapa_id,
        )
        return jsonify({'ok': True, **result})

    enfermaria_id = request.args.get('enfermaria_id', type=int)
    somente_ativos = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_leitos(enfermaria_id=enfermaria_id, somente_ativos=somente_ativos))


@nutricao.route('/nutricao/api/leitos/<int:lid>', methods=['PUT', 'DELETE'])
def api_leito_ops(lid):
    row = NutLeito.query.get(lid)
    enf = _get_scoped(NutEnfermaria, row.enfermaria_id) if row else None
    if not row or not enf:
        return jsonify({'ok': False, 'error': 'Leito não encontrado'}), 404

    if request.method == 'DELETE':
        enf_id = row.enfermaria_id
        db.session.delete(row)
        db.session.commit()
        enf = _get_scoped_or_404(NutEnfermaria, enf_id)
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
        if not _get_scoped(NutEnfermaria, nova_enf):
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
    categorias = list_categorias_dieta(somente_ativos=True)
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
        categorias=categorias,
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
        exists = scoped_query(NutDieta).filter_by(nome=nome).first()
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
            liberar_dieta_excluida(nome, getattr(exists, 'cliente_id', None))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'dieta': exists.to_dict()})
        row = NutDieta(
            cliente_id=write_cliente_id(),
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
        liberar_dieta_excluida(nome, row.cliente_id)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'dieta': row.to_dict()})
    somente_ativas = str(request.args.get('ativas', '')).lower() in ('1', 'true', 'sim')
    return jsonify(_list_dietas_db(somente_ativas=somente_ativas))


@nutricao.route('/nutricao/api/dietas/<int:did>', methods=['PUT', 'DELETE'])
def api_dieta_ops(did):
    row = _get_scoped_or_404(NutDieta, did)
    if not row:
        return jsonify({'ok': False, 'error': 'Dieta não encontrada'}), 404

    if request.method == 'DELETE':
        try:
            qtd_cardapios = excluir_dieta_e_cardapios(row)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({
                'ok': False,
                'error': 'Não foi possível excluir a dieta porque ela ainda está em uso.',
            }), 409
        return jsonify({'ok': True, 'cardapios': qtd_cardapios})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da dieta é obrigatório'}), 400
        outro = scoped_query(NutDieta).filter(
            NutDieta.nome == nome, NutDieta.id != did
        ).first()
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


# ---- CATEGORIAS DE DIETA ----
@nutricao.route('/nutricao/categorias')
def categorias_dietas():
    seed_nutricao()
    return render_template(
        'nutricao_categorias.html',
        categorias=list_categorias_dieta(somente_ativos=False),
        **active('cadastro_categorias')
    )


@nutricao.route('/nutricao/api/categorias', methods=['GET', 'POST'])
def api_categorias_dietas():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da categoria é obrigatório'}), 400
        exists = scoped_query(NutCategoriaDieta).filter(
            db.func.upper(NutCategoriaDieta.nome) == nome.upper()
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
            return jsonify({'ok': True, 'id': exists.id, 'categoria': exists.to_dict()})
        codigo = slug_categoria_dieta(d.get('codigo') or nome)
        if scoped_query(NutCategoriaDieta).filter(
            db.func.lower(NutCategoriaDieta.codigo) == codigo
        ).first():
            codigo = codigo_categoria_unico(nome)
        if ordem <= 0:
            last = scoped_query(NutCategoriaDieta).order_by(NutCategoriaDieta.ordem.desc()).first()
            ordem = (last.ordem + 10) if last else 10
        row = NutCategoriaDieta(
            nome=nome,
            codigo=codigo,
            ordem=ordem,
            ativo=bool(d.get('ativo', True)),
        )
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'categoria': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_categorias_dieta(somente_ativos=somente))


@nutricao.route('/nutricao/api/categorias/<int:cid>', methods=['PUT', 'DELETE'])
def api_categoria_dieta_ops(cid):
    row = _get_scoped_or_404(NutCategoriaDieta, cid)
    if not row:
        return jsonify({'ok': False, 'error': 'Categoria não encontrada'}), 404

    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da categoria é obrigatório'}), 400
        outro = scoped_query(NutCategoriaDieta).filter(
            db.func.upper(NutCategoriaDieta.nome) == nome.upper(),
            NutCategoriaDieta.id != cid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe categoria com este nome'}), 400
        row.nome = nome
    if 'codigo' in d:
        codigo = slug_categoria_dieta(d.get('codigo') or row.nome)
        if not codigo:
            return jsonify({'ok': False, 'error': 'Código da categoria é obrigatório'}), 400
        outro = scoped_query(NutCategoriaDieta).filter(
            db.func.lower(NutCategoriaDieta.codigo) == codigo,
            NutCategoriaDieta.id != cid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe categoria com este código'}), 400
        antigo = (row.codigo or '').strip()
        row.codigo = codigo
        if antigo and antigo != codigo:
            scoped_query(NutDieta).filter(
                db.func.lower(NutDieta.categoria) == antigo.lower()
            ).update({NutDieta.categoria: codigo}, synchronize_session=False)
    if 'ordem' in d:
        try:
            row.ordem = int(d.get('ordem') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Ordem inválida'}), 400
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    db.session.commit()
    return jsonify({'ok': True, 'categoria': row.to_dict()})


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
        exists = scoped_query(NutGrupoDieta).filter(
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
            liberar_grupo_dieta_excluido(nome, exists.cliente_id)
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'grupo': exists.to_dict()})
        if ordem <= 0:
            last = scoped_query(NutGrupoDieta).order_by(NutGrupoDieta.ordem.desc()).first()
            ordem = (last.ordem + 10) if last else 10
        row = NutGrupoDieta(
            nome=nome,
            ordem=ordem,
            ativo=bool(d.get('ativo', True)),
        )
        _tag_cliente(row)
        db.session.add(row)
        liberar_grupo_dieta_excluido(nome, row.cliente_id)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'grupo': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_grupos_dieta(somente_ativos=somente))


@nutricao.route('/nutricao/api/grupos-dietas/<int:gid>', methods=['PUT', 'DELETE'])
def api_grupo_dieta_ops(gid):
    row = _get_scoped_or_404(NutGrupoDieta, gid)
    if not row:
        return jsonify({'ok': False, 'error': 'Grupo não encontrado'}), 404

    if request.method == 'DELETE':
        try:
            excluir_grupo_dieta(row)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({
                'ok': False,
                'error': 'Não foi possível excluir o grupo porque ele ainda está em uso.',
            }), 409
        return jsonify({'ok': True})

    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome do grupo é obrigatório'}), 400
        outro = scoped_query(NutGrupoDieta).filter(
            db.func.upper(NutGrupoDieta.nome) == nome,
            NutGrupoDieta.id != gid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe grupo com este nome'}), 400
        antigo = (row.nome or '').strip().upper()
        row.nome = nome
        liberar_grupo_dieta_excluido(nome, row.cliente_id)
        # Mantém dieta.grupo (string) alinhado para preços/mapa
        if antigo and antigo != nome:
            scoped_query(NutDieta).filter(
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
        exists = scoped_query(NutTipoRefeicao).filter(
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
        if scoped_query(NutTipoRefeicao).filter(db.func.upper(NutTipoRefeicao.sigla) == sigla).first():
            return jsonify({'ok': False, 'error': 'Já existe tipo com esta sigla'}), 400
        try:
            ordem = int(d.get('ordem') or 0)
        except (TypeError, ValueError):
            ordem = 0
        if ordem <= 0:
            last = scoped_query(NutTipoRefeicao).order_by(NutTipoRefeicao.ordem.desc()).first()
            ordem = (last.ordem + 10) if last else 10
        row = NutTipoRefeicao(
            nome=nome,
            sigla=sigla,
            ordem=ordem,
            hora_limite=hora_limite,
            ativo=bool(d.get('ativo', True)),
        )
        _tag_cliente(row)
        db.session.add(row)
        db.session.flush()
        _seed_precos_dieta_tipo()
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'tipo': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_tipos_refeicao(somente_ativos=somente))


@nutricao.route('/nutricao/api/tipos-refeicao/<int:tid>', methods=['PUT', 'DELETE'])
def api_tipo_refeicao_ops(tid):
    row = _get_scoped_or_404(NutTipoRefeicao, tid)
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
        outro = scoped_query(NutTipoRefeicao).filter(
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
        outro = scoped_query(NutTipoRefeicao).filter(
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
    """Resolve dieta_id + nome. Se o id sumiu, recria a dieta pelo nome para o cardápio gravar."""
    dieta_id = d.get('dieta_id')
    dieta_nome = (d.get('dieta') or '').strip() or None
    try:
        dieta_id = int(dieta_id) if dieta_id not in (None, '', 0, '0') else None
    except (TypeError, ValueError):
        dieta_id = None
    row_dieta = _get_scoped(NutDieta, dieta_id) if dieta_id else None
    if row_dieta:
        return row_dieta.id, row_dieta.nome
    if dieta_nome:
        row_dieta = scoped_query(NutDieta).filter(
            db.func.upper(NutDieta.nome) == dieta_nome.upper()
        ).first()
        if row_dieta:
            return row_dieta.id, row_dieta.nome
        from nutricao_service import liberar_dieta_excluida
        cid = write_cliente_id()
        liberar_dieta_excluida(dieta_nome, cid)
        row_dieta = NutDieta(
            cliente_id=cid,
            nome=dieta_nome.upper(),
            categoria='basica',
            grupo='',
            ativo=True,
        )
        db.session.add(row_dieta)
        db.session.flush()
        return row_dieta.id, row_dieta.nome
    return None, None


def _texto_item(bruto):
    if isinstance(bruto, (list, tuple)):
        return str(bruto[0]).strip() if bruto else ''
    return str(bruto or '').strip()


def _aplicar_item_isolado(row, d, numero):
    """Grava só um item da refeição, sem apagar os outros do mesmo horário."""
    valor = _texto_item(d.get(f'item_{numero}')) or None
    setattr(row, f'item_{numero}', valor)
    data = {}
    if row.itens:
        try:
            bruto = json.loads(row.itens)
            if isinstance(bruto, dict):
                data = bruto
        except (TypeError, ValueError):
            data = {}
    chaves = CAMPOS_ITEM_CARDAPIO.get(row.tipo or '', ())
    if numero <= len(chaves):
        chave = chaves[numero - 1]
        if valor:
            data[chave] = valor
        else:
            data.pop(chave, None)
    row.itens = json.dumps(data, ensure_ascii=False)


def _dia_mes_cardapio(valor):
    """Dia do cardápio de 1 a 31, sem cortar pelo tamanho do mês corrente."""
    try:
        dia = int(valor or 1)
    except (TypeError, ValueError):
        dia = 1
    if dia < 1:
        return 1
    if dia > 31:
        return 31
    return dia


def _cardapio_from_payload(d, row=None):
    row = row or NutCardapio()
    row.tipo = (d.get('tipo') or 'grandes').strip()
    row.grupo_cardapio = (d.get('grupo_cardapio') or 'PRINCIPAL').strip()
    row.dia_mes = _dia_mes_cardapio(d.get('dia_mes'))
    row.dia_semana = (d.get('dia_semana') or '').strip() or None
    dieta_id, dieta_nome = _resolve_cardapio_dieta(d)
    row.dieta_id = dieta_id
    row.dieta = dieta_nome
    for hr in ('hr_desjejum', 'hr_colacao', 'hr_almoco', 'hr_merenda', 'hr_jantar', 'hr_ceia'):
        setattr(row, hr, bool(d.get(hr)))
    somente = d.get('somente_item')
    try:
        somente = int(somente) if somente not in (None, '') else None
    except (TypeError, ValueError):
        somente = None
    if somente and 1 <= somente <= 10 and (row.tipo or '') in ('pequenas', 'grandes'):
        _aplicar_item_isolado(row, d, somente)
    else:
        row.set_itens(d.get('itens') or {})
        for i in range(1, 11):
            chave = f'item_{i}'
            if chave not in d:
                continue
            setattr(row, chave, _texto_item(d.get(chave)) or None)
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


_HR_CARDAPIO = (
    'hr_desjejum', 'hr_colacao', 'hr_almoco', 'hr_merenda', 'hr_jantar', 'hr_ceia',
)


def _horario_marcado(d):
    ativos = [hr for hr in _HR_CARDAPIO if d.get(hr)]
    return ativos[0] if len(ativos) == 1 else None


def _horarios_da_linha(row):
    return [hr for hr in _HR_CARDAPIO if getattr(row, hr, None)]


def _query_cardapio_horario(d, dieta_id, ignorar_id=None):
    """Cardápio exclusivo deste horário. Outra refeição não entra na mesma linha."""
    tipo = (d.get('tipo') or 'grandes').strip()
    dia = _dia_mes_cardapio(d.get('dia_mes'))
    q = scoped_query(NutCardapio).filter_by(ativo=True, tipo=tipo, dia_mes=dia)
    if dieta_id:
        q = q.filter_by(dieta_id=int(dieta_id))
    hr = _horario_marcado(d)
    if hr:
        q = q.filter(getattr(NutCardapio, hr).is_(True))
        for outro in _HR_CARDAPIO:
            if outro == hr:
                continue
            q = q.filter(getattr(NutCardapio, outro).is_(False))
    elif tipo != 'liquidas':
        return None
    if ignorar_id:
        q = q.filter(NutCardapio.id != int(ignorar_id))
    return q


def _cardapio_mesmo_horario(d, dieta_id):
    q = _query_cardapio_horario(d, dieta_id)
    if q is None:
        return None
    return q.order_by(NutCardapio.id.desc()).first()


def _arquivar_cardapios_mesmo_horario(row, d, dieta_id):
    q = _query_cardapio_horario(d, dieta_id, ignorar_id=row.id)
    if q is None:
        return
    for other in q.all():
        other.ativo = False


def _soltar_horario_compartilhado(row, d, dieta_id):
    """Tira este horário de um cardápio que também serve outra refeição."""
    hr = _horario_marcado(d)
    if not hr:
        return
    tipo = (d.get('tipo') or 'grandes').strip()
    dia = _dia_mes_cardapio(d.get('dia_mes'))
    q = scoped_query(NutCardapio).filter(
        NutCardapio.ativo.is_(True),
        NutCardapio.tipo == tipo,
        NutCardapio.dia_mes == dia,
        NutCardapio.id != row.id,
        getattr(NutCardapio, hr).is_(True),
    )
    if dieta_id:
        q = q.filter(NutCardapio.dieta_id == int(dieta_id))
    for other in q.all():
        if any(h != hr and getattr(other, h) for h in _HR_CARDAPIO):
            setattr(other, hr, False)


@nutricao.route('/nutricao/cardapios')
def cardapios():
    seed_nutricao()
    dieta_id = request.args.get('dieta_id', type=int)
    dieta_sel = _get_scoped_or_404(NutDieta, dieta_id) if dieta_id else None
    dietas_list = _list_dietas_db(somente_ativas=True)
    return render_template(
        'nutricao_cardapios.html',
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
        row = _cardapio_mesmo_horario(d, dieta_id)
        if row is None:
            row = _cardapio_from_payload(d)
            _tag_cliente(row)
            db.session.add(row)
        else:
            _cardapio_from_payload(d, row)
        db.session.flush()
        _arquivar_cardapios_mesmo_horario(row, d, dieta_id)
        _soltar_horario_compartilhado(row, d, dieta_id)
        db.session.commit()
        invalidar_cache_cardapios()
        return jsonify({'ok': True, 'id': row.id, 'cardapio': row.to_dict()})
    tipo = (request.args.get('tipo') or '').strip() or None
    dieta_id = request.args.get('dieta_id', type=int)
    return jsonify(list_cardapios(tipo=tipo, dieta_id=dieta_id))


@nutricao.route('/nutricao/api/cardapios/<int:cid>', methods=['PUT', 'DELETE'])
def api_cardapio_ops(cid):
    row = _get_scoped_or_404(NutCardapio, cid)
    if not row or not row.ativo:
        return jsonify({'ok': False, 'error': 'Cardápio não encontrado'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        invalidar_cache_cardapios()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    hr = _horario_marcado(d)
    dono = _horarios_da_linha(row)
    if hr and dono and dono != [hr]:
        dieta_id = d.get('dieta_id') or row.dieta_id
        outro = _cardapio_mesmo_horario(d, dieta_id)
        if outro is None or outro.id == row.id:
            outro = NutCardapio()
            _tag_cliente(outro)
            db.session.add(outro)
        _cardapio_from_payload(d, outro)
        db.session.flush()
        _arquivar_cardapios_mesmo_horario(outro, d, dieta_id)
        _soltar_horario_compartilhado(outro, d, dieta_id)
        db.session.commit()
        invalidar_cache_cardapios()
        return jsonify({'ok': True, 'id': outro.id, 'cardapio': outro.to_dict()})
    _cardapio_from_payload(d, row)
    db.session.flush()
    _arquivar_cardapios_mesmo_horario(row, d, row.dieta_id)
    _soltar_horario_compartilhado(row, d, row.dieta_id)
    db.session.commit()
    invalidar_cache_cardapios()
    return jsonify({'ok': True, 'id': row.id, 'cardapio': row.to_dict()})


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
        exists = scoped_query(NutTabelaNutrientes).filter_by(nome=nome).first()
        if exists:
            if 'ativo' in d:
                exists.ativo = bool(d.get('ativo'))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'tabela': exists.to_dict()})
        row = NutTabelaNutrientes(nome=nome, ativo=bool(d.get('ativo', True)))
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'tabela': row.to_dict()})
    return jsonify(list_tabelas_nutrientes(somente_ativas=False))


@nutricao.route('/nutricao/api/tabelas-nutrientes/<int:tid>', methods=['PUT', 'DELETE'])
def api_tabela_nutrientes_ops(tid):
    row = _get_scoped(NutTabelaNutrientes, tid)
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
        outro = scoped_query(NutTabelaNutrientes).filter(
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
        if not _get_scoped(NutTabelaNutrientes, tabela_id):
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
    tabela = _get_scoped(NutTabelaNutrientes, row.tabela_id) if row else None
    if not row or not tabela:
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
        exists = scoped_query(NutPratoLiquido).filter_by(nome=nome).first()
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
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'prato': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_pratos_liquidos(somente_ativos=somente))


@nutricao.route('/nutricao/api/pratos-liquidos/<int:pid>', methods=['PUT', 'DELETE'])
def api_prato_liquido_ops(pid):
    row = _get_scoped_or_404(NutPratoLiquido, pid)
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
        outro = scoped_query(NutPratoLiquido).filter(
            NutPratoLiquido.nome == nome, NutPratoLiquido.id != pid
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe prato com este nome'}), 400
        row.nome = nome
    _prato_liquido_from_payload(d, row)
    db.session.commit()
    return jsonify({'ok': True, 'prato': row.to_dict()})


# ---- VIAS DE ADMINISTRAÇÃO E ITENS DA U.M.A. ----
@nutricao.route('/nutricao/vias')
def vias_administracao():
    seed_nutricao()
    return render_template(
        'nutricao_vias.html',
        vias=list_vias(somente_ativas=False),
        **active('cadastro_vias')
    )


def _via_from_payload(d, row=None):
    row = row or NutViaAdministracao()
    if 'nome' in d or row.nome is None:
        row.nome = (d.get('nome') or row.nome or '').strip().upper()
    if 'produto' in d:
        row.produto = (d.get('produto') or '').strip().upper()
    if 'via_oral' in d:
        row.via_oral = bool(d.get('via_oral'))
    if 'ativo' in d:
        row.ativo = bool(d.get('ativo'))
    return row


@nutricao.route('/nutricao/api/vias', methods=['GET', 'POST'])
def api_vias():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da embalagem é obrigatório'}), 400
        exists = scoped_query(NutViaAdministracao).filter_by(nome=nome).first()
        if exists:
            _via_from_payload(d, exists)
            exists.ativo = bool(d.get('ativo', True))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'via': exists.to_dict()})
        row = _via_from_payload(d)
        row.nome = nome
        if 'ativo' not in d:
            row.ativo = True
        _tag_cliente(row)
        db.session.add(row)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({'ok': False, 'error': 'Já existe via com este nome'}), 400
        return jsonify({'ok': True, 'id': row.id, 'via': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_vias(somente_ativas=somente))


@nutricao.route('/nutricao/api/vias/<int:vid>', methods=['PUT', 'DELETE'])
def api_via_ops(vid):
    row = _get_scoped_or_404(NutViaAdministracao, vid)
    if not row:
        return jsonify({'ok': False, 'error': 'Via não encontrada'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'nome' in d:
        nome = (d.get('nome') or '').strip().upper()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da embalagem é obrigatório'}), 400
        outro = scoped_query(NutViaAdministracao).filter(
            NutViaAdministracao.nome == nome,
            NutViaAdministracao.id != vid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Já existe via com este nome'}), 400
        row.nome = nome
    _via_from_payload(d, row)
    db.session.commit()
    return jsonify({'ok': True, 'via': row.to_dict()})


@nutricao.route('/nutricao/api/uma-itens', methods=['GET', 'POST'])
def api_uma_itens():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        try:
            row = gravar_uma_item(
                write_cliente_id(),
                d.get('tipo'),
                d.get('nome'),
                sistema=d.get('sistema') or '',
                papel=d.get('papel') or '',
                manipulado=bool(d.get('manipulado')),
                produto=d.get('produto') or '',
            )
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'item': row.to_dict()})
    manipulado = request.args.get('manipulado')
    if manipulado is None or manipulado == '':
        flag = None
    else:
        flag = str(manipulado).lower() in ('1', 'true', 'sim')
    disponivel = request.args.get('disponivel')
    somente_disp = str(disponivel or '').lower() in ('1', 'true', 'sim')
    return jsonify(list_uma_itens(
        tipo=request.args.get('tipo') or None,
        sistema=request.args.get('sistema') or None,
        papel=request.args.get('papel') or None,
        manipulado=flag,
        somente_ativos=str(request.args.get('ativos', '1')).lower() not in ('0', 'false', 'nao', 'não'),
        somente_disponiveis=somente_disp,
    ))


_CADASTRO_UMA = {
    'formula': ('Fórmula Infantil', 'cadastro_uma_formula'),
    'enteral': ('Enteral', 'cadastro_uma_enteral'),
    'suplemento': ('Suplemento', 'cadastro_uma_suplemento'),
    'lve': ('LVE', 'cadastro_uma_lve'),
}


def _tipo_cadastro_uma(valor):
    tipo = (valor or 'formula').strip().lower()
    return tipo if tipo in _CADASTRO_UMA else 'formula'


@nutricao.route('/nutricao/configuracoes', methods=['GET'])
def configuracoes_sistema():
    seed_nutricao()
    cfg = config_uma_dict()
    grupos = [g['nome'] for g in list_grupos_dieta(somente_ativos=True)]
    return render_template(
        'nutricao_config_uma.html',
        cfg=cfg,
        vias=list_vias(somente_ativas=True),
        produtos=list_produtos(somente_ativos=True),
        estoques=list_estoques(somente_ativos=True),
        colunas=colunas_faturamento_uma(grupos),
        **active('config_uma'),
    )


@nutricao.route('/nutricao/api/config-uma', methods=['GET', 'PUT'])
def api_config_uma():
    seed_nutricao()
    if request.method == 'GET':
        return jsonify(config_uma_dict())
    d = request.get_json(force=True) or {}
    try:
        cfg = salvar_config_uma(d)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    return jsonify({'ok': True, 'config': cfg})


@nutricao.route('/nutricao/cadastro-uma')
def cadastro_uma():
    seed_nutricao()
    tipo = _tipo_cadastro_uma(request.args.get('tipo'))
    if tipo == 'lve':
        desvincular_lves_das_dietas(write_cliente_id())
        db.session.commit()
    titulo, page = _CADASTRO_UMA[tipo]
    grupos = listar_campo_uma(tipo, 'grupo')
    colunas = listar_campo_uma(tipo, 'coluna')
    unidades = [
        u for u in list_unidades(somente_ativas=True)
        if u.get('flag_uma', True)
    ]
    cfg_uma = config_uma_dict()
    estoque_do_tipo = {
        'enteral': cfg_uma.get('estoque_enteral_id'),
        'suplemento': cfg_uma.get('estoque_suplemento_id'),
        'formula': cfg_uma.get('estoque_formula_id'),
        'lve': cfg_uma.get('estoque_lve_id'),
    }.get(tipo)
    produtos = [
        {
            'codigo': p.get('codigo') or '',
            'descricao': p.get('descricao') or '',
            'unidade': p.get('unidade') or '',
        }
        for p in list_produtos(estoque_id=estoque_do_tipo, somente_ativos=True)
        if p.get('formula')
    ]
    return render_template(
        'nutricao_cadastro_uma.html',
        tipo=tipo,
        titulo=titulo,
        itens=list_uma_itens(tipo=tipo, somente_ativos=False),
        unidades=unidades,
        produtos=produtos,
        grupos=grupos,
        colunas=colunas,
        **active(page),
    )


def _payload_cadastro_uma(d, tipo):
    d = dict(d or {})
    d['tipo'] = tipo
    return d


def _resposta_opcao_uma(tipo, campo, nome=None):
    return jsonify({
        'ok': True,
        'nome': nome,
        'campo': campo,
        'nomes': listar_campo_uma(tipo, campo),
    })


@nutricao.route('/nutricao/api/cadastro-uma/opcao', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api_cadastro_uma_opcao():
    seed_nutricao()
    if request.method == 'GET':
        tipo = _tipo_cadastro_uma(request.args.get('tipo'))
        campo = (request.args.get('campo') or '').strip().lower()
    else:
        d = request.get_json(force=True) or {}
        tipo = _tipo_cadastro_uma(d.get('tipo'))
        campo = (d.get('campo') or '').strip().lower()
    try:
        if request.method == 'GET':
            return _resposta_opcao_uma(tipo, campo)
        cid = write_cliente_id()
        if request.method == 'POST':
            nome = salvar_opcao_uma(cid, tipo, campo, d.get('nome'))
        elif request.method == 'PUT':
            nome = renomear_opcao_uma(cid, tipo, campo, d.get('nome'), d.get('nome_novo'))
        else:
            nome = remover_opcao_uma(cid, tipo, campo, d.get('nome'))
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Já existe um item com este nome'}), 400
    return _resposta_opcao_uma(tipo, campo, nome)


@nutricao.route('/nutricao/api/cadastro-uma', methods=['POST'])
def api_cadastro_uma():
    seed_nutricao()
    d = request.get_json(force=True) or {}
    tipo = _tipo_cadastro_uma(d.get('tipo'))
    try:
        row = salvar_cadastro_uma(write_cliente_id(), _payload_cadastro_uma(d, tipo))
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Já existe um item com este nome'}), 400
    return jsonify({'ok': True, 'id': row.id, 'item': row.to_dict()})


@nutricao.route('/nutricao/api/cadastro-uma/<int:iid>', methods=['PUT', 'DELETE'])
def api_cadastro_uma_ops(iid):
    row = _get_scoped_or_404(NutUmaItem, iid)
    if not row:
        return jsonify({'ok': False, 'error': 'Item não encontrado'}), 404
    if request.method == 'DELETE':
        if (row.tipo or '').strip().lower() == 'lve':
            apagar_cadastro_lve(row)
            db.session.commit()
            return jsonify({'ok': True, 'apagado': True})
        row.ativo = False
        row.produto_disponivel = False
        db.session.commit()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    tipo = _tipo_cadastro_uma(d.get('tipo') or row.tipo)
    if tipo != (row.tipo or ''):
        return jsonify({'ok': False, 'error': 'Tipo do item não confere'}), 400
    try:
        salvar_cadastro_uma(row.cliente_id, _payload_cadastro_uma(d, tipo), row=row)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Já existe um item com este nome'}), 400
    return jsonify({'ok': True, 'id': row.id, 'item': row.to_dict()})


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
    if 'formula' in d:
        row.formula = bool(d.get('formula'))
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
        exists = scoped_query(NutEstoqueLocal).filter_by(nome=nome).first()
        if exists:
            exists.ativo = bool(d.get('ativo', True))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'estoque': exists.to_dict()})
        row = NutEstoqueLocal(nome=nome, ativo=bool(d.get('ativo', True)))
        _tag_cliente(row)
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
                    exists = _get_scoped(NutUnidadeMedida, int(uid))
                if not exists:
                    exists = scoped_query(NutUnidadeMedida).filter_by(codigo=codigo).first()
                if exists:
                    outro = scoped_query(NutUnidadeMedida).filter(
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
                    _tag_cliente(row)
                    db.session.add(row)
                    db.session.flush()
                    salvos.append(row.to_dict())
            db.session.commit()
            return jsonify({'ok': True, 'unidades': salvos})
        codigo = (d.get('codigo') or '').strip().upper()
        if not codigo:
            return jsonify({'ok': False, 'error': 'Código da unidade é obrigatório'}), 400
        exists = scoped_query(NutUnidadeMedida).filter_by(codigo=codigo).first()
        if exists:
            _unidade_from_payload(d, exists)
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'unidade': exists.to_dict()})
        row = _unidade_from_payload(d)
        if 'ativo' not in d:
            row.ativo = True
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'unidade': row.to_dict()})
    return jsonify(list_unidades(somente_ativas=False))


@nutricao.route('/nutricao/api/unidades/<int:uid>', methods=['PUT', 'DELETE'])
def api_unidade_ops(uid):
    row = _get_scoped(NutUnidadeMedida, uid)
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
        outro = scoped_query(NutUnidadeMedida).filter(
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
        exists = scoped_query(NutGrupoProduto).filter_by(nome=nome).first()
        if exists:
            if 'ativo' in d:
                exists.ativo = bool(d.get('ativo'))
            db.session.commit()
            return jsonify({'ok': True, 'id': exists.id, 'grupo': exists.to_dict()})
        row = NutGrupoProduto(nome=nome, ativo=bool(d.get('ativo', True)))
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'grupo': row.to_dict()})
    return jsonify(list_grupos_produto(somente_ativos=False))


@nutricao.route('/nutricao/api/grupos-produto/<int:gid>', methods=['PUT', 'DELETE'])
def api_grupo_produto_ops(gid):
    row = _get_scoped(NutGrupoProduto, gid)
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
        outro = scoped_query(NutGrupoProduto).filter(
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
        if not _get_scoped(NutEstoqueLocal, estoque_id):
            return jsonify({'ok': False, 'error': 'Estoque não encontrado'}), 404
        if not _get_scoped(NutGrupoProduto, grupo_id):
            return jsonify({'ok': False, 'error': 'Grupo não encontrado'}), 404
        codigo = (d.get('codigo') or '').strip().upper()
        descricao = (d.get('descricao') or '').strip().upper()
        if not codigo or not descricao:
            return jsonify({'ok': False, 'error': 'Código e descrição são obrigatórios'}), 400
        exists = scoped_query(NutProduto).filter_by(estoque_id=estoque_id, codigo=codigo).first()
        if exists:
            _produto_from_payload(d, exists)
            exists.ativo = bool(d.get('ativo', True))
            db.session.commit()
            invalidar_cache_produtos_cardapio()
            return jsonify({'ok': True, 'id': exists.id, 'produto': exists.to_dict()})
        row = _produto_from_payload(d)
        row.estoque_id = estoque_id
        row.grupo_id = grupo_id
        row.codigo = codigo
        row.descricao = descricao
        if 'ativo' not in d:
            row.ativo = True
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        invalidar_cache_produtos_cardapio()
        return jsonify({'ok': True, 'id': row.id, 'produto': row.to_dict()})
    estoque_id = request.args.get('estoque_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    return jsonify(list_produtos(estoque_id=estoque_id, grupo_id=grupo_id, somente_ativos=False))


@nutricao.route('/nutricao/api/cardapio-itens', methods=['GET', 'POST'])
def api_cardapio_itens():
    """Itens do cardápio, separados do cadastro de produtos."""
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        grupo = (d.get('grupo') or d.get('tema') or '').strip()
        tipo = (d.get('tipo') or '').strip().lower()
        row, err = criar_item_cardapio(nome, grupo, tipo)
        if err:
            return jsonify({'ok': False, 'error': err}), 400
        _tag_cliente(row)
        db.session.commit()
        return jsonify({
            'ok': True,
            'id': row.id,
            'item': row.to_dict(),
            'itens': list_itens_tema_cardapio(grupo, tipo),
        })
    tipo = (request.args.get('tipo') or '').strip().lower()
    if not tipo:
        return jsonify({'ok': False, 'error': 'Informe o tipo do cardápio'}), 400
    tema = (request.args.get('grupo') or request.args.get('tema') or '').strip()
    if tema:
        return jsonify(list_itens_tema_cardapio(tema, tipo))
    raw = (request.args.get('temas') or '').strip()
    temas = [t.strip() for t in raw.split(',') if t.strip()]
    return jsonify(list_itens_temas_cardapio(temas, tipo))


@nutricao.route('/nutricao/api/cardapio-produtos', methods=['GET', 'POST'])
def api_cardapio_produtos():
    """Produtos do cardápio: grupo = tema do campo (Acompanhamento, Bebida, …)."""
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or d.get('descricao') or '').strip()
        grupo = (d.get('grupo') or d.get('tema') or '').strip()
        tipo_cardapio = (d.get('tipo') or '').strip().lower() or None
        row, err = criar_produto_tema_cardapio(nome, grupo, tipo=tipo_cardapio)
        if err:
            return jsonify({'ok': False, 'error': err}), 400
        _tag_cliente(row)
        if row.grupo is not None:
            _tag_cliente(row.grupo)
        db.session.commit()
        return jsonify({
            'ok': True,
            'id': row.id,
            'produto': {
                'id': row.id,
                'nome': row.descricao,
                'grupo': row.grupo.nome if row.grupo else grupo,
            },
            'itens': list_produtos_tema_cardapio(grupo, tipo=tipo_cardapio),
        })
    tema = (request.args.get('grupo') or request.args.get('tema') or '').strip()
    tipo_cardapio = (request.args.get('tipo') or '').strip().lower() or None
    if tema:
        return jsonify(list_produtos_tema_cardapio(tema, tipo=tipo_cardapio))
    raw = (request.args.get('temas') or '').strip()
    temas = [t.strip() for t in raw.split(',') if t.strip()]
    return jsonify(list_produtos_temas_cardapio(temas, tipo=tipo_cardapio))


@nutricao.route('/nutricao/api/produtos/<int:pid>', methods=['PUT', 'DELETE'])
def api_produto_cadastro_ops(pid):
    row = _get_scoped_or_404(NutProduto, pid)
    if not row:
        return jsonify({'ok': False, 'error': 'Produto não encontrado'}), 404
    if request.method == 'DELETE':
        row.ativo = False
        row.data_alteracao = datetime.utcnow()
        db.session.commit()
        invalidar_cache_produtos_cardapio()
        return jsonify({'ok': True})
    d = request.get_json(force=True) or {}
    if 'codigo' in d:
        codigo = (d.get('codigo') or '').strip().upper()
        if not codigo:
            return jsonify({'ok': False, 'error': 'Código obrigatório'}), 400
        outro = scoped_query(NutProduto).filter(
            NutProduto.estoque_id == row.estoque_id,
            NutProduto.codigo == codigo,
            NutProduto.id != pid,
        ).first()
        if outro:
            return jsonify({'ok': False, 'error': 'Código já existe neste estoque'}), 400
        row.codigo = codigo
    _produto_from_payload(d, row)
    db.session.commit()
    invalidar_cache_produtos_cardapio()
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
        _tag_cliente(row)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'fornecedor': row.to_dict()})
    somente = str(request.args.get('ativos', '')).lower() in ('1', 'true', 'sim')
    return jsonify(list_fornecedores(somente_ativos=somente))


@nutricao.route('/nutricao/api/fornecedores/<int:fid>', methods=['PUT', 'DELETE'])
def api_fornecedor_ops(fid):
    row = _get_scoped_or_404(NutFornecedor, fid)
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
        grupos_clinica=list_grupos_clinica(somente_ativos=True),
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
    imprimir_por = (request.args.get('imprimir_por') or 'clinica').strip()
    filtro_id = request.args.get('filtro_id', type=int)
    filtro_nome = _filtro_nome_imprimir(
        imprimir_por,
        filtro_id,
        (request.args.get('filtro_nome') or '').strip() or None,
    )
    ordenar = (request.args.get('ordenar') or 'grupo_dieta_data').strip()
    incluir_enfermaria = str(request.args.get('incluir_enfermaria', '')).lower() in ('1', 'true', 'sim')
    somente_alteradas = str(request.args.get('somente_alteradas', '')).lower() in ('1', 'true', 'sim')
    alteradas_desde = (request.args.get('alteradas_desde') or '').strip() or None
    modelo_id = (request.args.get('modelo') or '6080').strip()
    seq_inicio = request.args.get('seq_inicio', type=int) or 1

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


@nutricao.route('/nutricao/impressao-mapa')
def impressao_mapa():
    seed_nutricao()
    return render_template(
        'nutricao_impressao_mapa.html',
        clinicas=_list_clinicas_db(somente_ativas=True),
        data_padrao=date.today().isoformat(),
        **active('impressao_mapa')
    )


@nutricao.route('/nutricao/impressao-mapa/imprimir')
def impressao_mapa_imprimir():
    seed_nutricao()
    data_de = _parse_date(request.args.get('data_de')) or date.today()
    data_ate = _parse_date(request.args.get('data_ate')) or data_de
    clinica = (request.args.get('clinica') or '').strip()
    rel = gerar_impressao_mapa(
        data_de=data_de,
        data_ate=data_ate,
        clinica_nome=clinica or None,
    )
    return render_template(
        'nutricao_impressao_mapa_print.html',
        r=rel,
        **active('impressao_mapa')
    )


@nutricao.route('/nutricao/impressao-mapa-distribuicao')
def impressao_mapa_distribuicao():
    seed_nutricao()
    return render_template(
        'nutricao_impressao_mapa_distribuicao.html',
        clinicas=_list_clinicas_db(somente_ativas=True),
        tipos=list_tipos_refeicao_impressao(),
        data_padrao=date.today().isoformat(),
        **active('impressao_mapa_distribuicao')
    )


@nutricao.route('/nutricao/impressao-mapa-distribuicao/imprimir')
def impressao_mapa_distribuicao_imprimir():
    seed_nutricao()
    data_de = _parse_date(request.args.get('data_de')) or date.today()
    data_ate = _parse_date(request.args.get('data_ate')) or data_de
    tipo = (request.args.get('tipo') or request.args.get('tipo_refeicao') or 'almoco').strip()
    clinicas = [c.strip() for c in request.args.getlist('clinica') if (c or '').strip()]
    if not clinicas:
        unica = (request.args.get('clinicas') or '').strip()
        if unica:
            clinicas = [p.strip() for p in unica.split(',') if p.strip()]
    rel = gerar_impressao_mapa_distribuicao(
        data_de=data_de,
        data_ate=data_ate,
        clinica_nomes=clinicas or None,
        tipo_refeicao=tipo,
    )
    return render_template(
        'nutricao_impressao_mapa_distribuicao_print.html',
        r=rel,
        **active('impressao_mapa_distribuicao')
    )


@nutricao.route('/nutricao/api/etiquetas', methods=['GET', 'POST'])
def api_etiquetas():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        nome = (d.get('nome') or '').strip()
        if not nome:
            return jsonify({'ok': False, 'error': 'Nome da etiqueta é obrigatório'}), 400
        exists = scoped_query(NutEtiqueta).filter_by(nome=nome).first()
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
        _tag_cliente(row)
        db.session.add(row)
        db.session.flush()
        _sync_etiqueta_campos(row, d.get('campos'))
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id, 'etiqueta': row.to_dict()})
    return jsonify(list_etiquetas(somente_ativas=False))


@nutricao.route('/nutricao/api/etiquetas/<int:eid>', methods=['PUT', 'DELETE'])
def api_etiqueta_ops(eid):
    row = _get_scoped_or_404(NutEtiqueta, eid)
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
        outro = scoped_query(NutEtiqueta).filter(
            NutEtiqueta.nome == nome, NutEtiqueta.id != eid
        ).first()
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
            if row is not None and not _get_scoped(NutDieta, row.dieta_id):
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
                if not _get_scoped(NutDieta, dieta_id) or not _get_scoped(NutTipoRefeicao, tipo_id):
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
            dieta = _get_scoped_or_404(NutDieta, int(dieta_id))
        except (TypeError, ValueError):
            dieta = None
    nome_novo = (d.get('dieta_nome') or d.get('nome') or '').strip().upper()
    grupo = (d.get('grupo') or '').strip().upper() or GRUPO_POR_PAYER.get(coluna, 'LACTÁRIO')
    if not dieta and nome_novo:
        dieta = scoped_query(NutDieta).filter(db.func.upper(NutDieta.nome) == nome_novo).first()
        if not dieta:
            dieta = NutDieta(
                cliente_id=write_cliente_id(),
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
                    row_t = scoped_query(NutTipoRefeicao).filter(
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
    seed_nutricao()
    return jsonify(list_produtos(somente_ativos=False))

# (api fornecedores real está em /nutricao/api/fornecedores)

# ---- RELATÓRIOS ----
@nutricao.route('/nutricao/relatorios')
def relatorios():
    return render_template(
        'nutricao_relatorios.html',
        totalizacoes=[],
        consumo_mensal=[],
        faturamento_mapa=[],
        mapa_suplementos=[],
        **active('relatorios')
    )


@nutricao.route('/nutricao/relatorio-mapa-uma')
def relatorio_mapa_uma():
    seed_nutricao()
    hoje = date.today().isoformat()
    return render_template(
        'nutricao_relatorio_mapa_uma.html',
        clinicas=_list_clinicas_db(somente_ativas=False),
        grupos_clinica=list_grupos_clinica(somente_ativos=True),
        enfermarias=list_enfermarias(somente_ativas=True),
        data_padrao=hoje,
        **active('relatorio_mapa_uma')
    )


def _flag_uma(src, name):
    if not hasattr(src, 'get'):
        return None
    val = src.get(name, None)
    if val is None or val == '':
        return None
    return str(val).strip().lower() in ('1', 'true', 'sim', 'on', 'yes')


def _opcoes_mapa_uma(src):
    """Filtros da impressão de mapas da U.M.A. (tela e API)."""
    horarios_raw = src.get('horarios') or []
    if isinstance(horarios_raw, str):
        horarios_raw = [h for h in horarios_raw.split(',') if h.strip()]
    try:
        linhas_branco = int(src.get('linhas_em_branco') or 0)
    except (TypeError, ValueError):
        linhas_branco = 0
    grupo_id = src.get('grupo_id')
    try:
        grupo_id = int(grupo_id) if grupo_id not in (None, '', 'null') else None
    except (TypeError, ValueError):
        grupo_id = None
    coluna = (src.get('coluna_extra') or 'diagnostico').strip()
    if coluna not in ('diagnostico', 'grupo_dieta'):
        coluna = 'diagnostico'
    sistema = (src.get('sistema') or 'aberto').strip().lower()
    if sistema not in ('aberto', 'fechado', 'ambos'):
        sistema = 'aberto'
    tipo = (src.get('tipo_mapa') or 'trabalho').strip().lower()
    if tipo not in ('trabalho', 'cobranca'):
        tipo = 'trabalho'
    return {
        'horarios': horarios_raw,
        'selecionar_horarios': _flag_uma(src, 'selecionar_horarios'),
        'grupo_clinica_id': grupo_id,
        'grupo_clinica_nome': (src.get('grupo_nome') or '').strip() or None,
        'coluna_extra': coluna,
        'sistema': sistema,
        'tipo_mapa': tipo,
        'linhas_em_branco': linhas_branco,
        'separar_grupo': bool(_flag_uma(src, 'separar_grupo')),
        'nao_imprimir_produto': bool(_flag_uma(src, 'nao_imprimir_produto')),
    }


@nutricao.route('/nutricao/api/relatorio-mapa-uma', methods=['POST'])
def api_relatorio_mapa_uma():
    seed_nutricao()
    d = request.get_json(force=True) or {}
    data_ref = _parse_date(d.get('data')) or date.today()
    categoria = (d.get('categoria') or 'enteral').strip()
    imprimir_por = (d.get('imprimir_por') or 'clinica').strip()
    filtro_id = d.get('filtro_id')
    filtro_nome = _filtro_nome_imprimir(
        imprimir_por,
        filtro_id,
        (d.get('filtro_nome') or '').strip() or None,
    )
    amostra = None
    if d.get('imprimir_amostra'):
        amostra = d.get('amostra_valor', 50)

    resultado = totalizar_mapa_uma(
        data_ref=data_ref,
        categoria=categoria,
        imprimir_por=imprimir_por,
        filtro_id=filtro_id,
        filtro_nome=filtro_nome,
        amostra=amostra,
        **_opcoes_mapa_uma(d),
    )
    return jsonify({'ok': True, 'relatorio': resultado})


@nutricao.route('/nutricao/totalizacao-dietas')
def totalizacao_dietas():
    seed_nutricao()
    return render_template(
        'nutricao_totalizacao_dietas.html',
        clinicas=_list_clinicas_db(somente_ativas=False),
        grupos_clinica=list_grupos_clinica(somente_ativos=True),
        enfermarias=list_enfermarias(somente_ativas=True),
        data_padrao=date.today().isoformat(),
        **active('totalizacao_dietas')
    )


@nutricao.route('/nutricao/totalizacao-dietas/imprimir')
def totalizacao_dietas_imprimir():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    totalizacao_para = (request.args.get('totalizacao_para') or 'clinicas').strip()
    imprimir_por = (request.args.get('imprimir_por') or 'clinica').strip()
    filtros = [x for x in (request.args.get('filtros') or '').split('|') if x.strip()]
    horarios = [x for x in (request.args.get('horarios') or '').split(',') if x.strip()]
    metodo = (request.args.get('metodo') or 'mapa').strip()
    imprimir_total = str(request.args.get('imprimir_total_geral', '1')).lower() in ('1', 'true', 'sim')

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


@nutricao.route('/nutricao/totalizacao-dietas-refeicoes')
def totalizacao_dietas_refeicoes():
    seed_nutricao()
    return render_template(
        'nutricao_totalizacao_dietas_refeicoes.html',
        clinicas=_list_clinicas_db(somente_ativas=False),
        grupos_clinica=list_grupos_clinica(somente_ativos=True),
        enfermarias=list_enfermarias(somente_ativas=True),
        data_padrao=date.today().isoformat(),
        **active('totalizacao_dietas_refeicoes')
    )


@nutricao.route('/nutricao/totalizacao-dietas-refeicoes/imprimir')
def totalizacao_dietas_refeicoes_imprimir():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    totalizacao_para = (request.args.get('totalizacao_para') or 'clinicas').strip()
    imprimir_por = (request.args.get('imprimir_por') or 'clinica').strip()
    filtros = [x for x in (request.args.get('filtros') or '').split('|') if x.strip()]
    horarios = [x for x in (request.args.get('horarios') or '').split(',') if x.strip()]
    metodo = (request.args.get('metodo') or 'todas').strip()
    imprimir_total = str(request.args.get('imprimir_total_geral', '1')).lower() in ('1', 'true', 'sim')

    rel = gerar_totalizacao_dietas_refeicoes(
        data_ref=data_ref,
        totalizacao_para=totalizacao_para,
        imprimir_por=imprimir_por,
        filtros=filtros,
        horarios=horarios,
        metodo=metodo,
        imprimir_total_geral=imprimir_total,
    )
    return render_template(
        'nutricao_totalizacao_dietas_refeicoes_print.html',
        r=rel,
        **active('totalizacao_dietas_refeicoes')
    )


def _filtros_alimentos_ctx():
    return dict(
        clinicas=_list_clinicas_db(somente_ativas=False),
        enfermarias=list_enfermarias(somente_ativas=True),
        data_padrao=date.today().isoformat(),
    )


def _args_totalizacao_alimentos():
    data_ref = _parse_date(request.args.get('data')) or date.today()
    imprimir_por = (request.args.get('imprimir_por') or 'clinica').strip()
    filtros = [x for x in (request.args.get('filtros') or '').split('|') if x.strip()]
    horarios = [x for x in (request.args.get('horarios') or '').split(',') if x.strip()]
    return data_ref, imprimir_por, filtros, horarios


@nutricao.route('/nutricao/totalizacao-substituicoes')
def totalizacao_substituicoes():
    seed_nutricao()
    return render_template(
        'nutricao_totalizacao_alimentos.html',
        titulo='Totalização de substituição de alimentos',
        subtitulo='Só o que foi trocado no cardápio: o que entrou e o que saiu, por clínica ou enfermaria.',
        imprimir_url='/nutricao/totalizacao-substituicoes/imprimir',
        **_filtros_alimentos_ctx(),
        **active('totalizacao_substituicoes')
    )


@nutricao.route('/nutricao/totalizacao-substituicoes/imprimir')
def totalizacao_substituicoes_imprimir():
    seed_nutricao()
    data_ref, imprimir_por, filtros, horarios = _args_totalizacao_alimentos()
    rel = gerar_totalizacao_substituicoes(
        data_ref=data_ref,
        imprimir_por=imprimir_por,
        filtros=filtros,
        horarios=horarios,
    )
    return render_template(
        'nutricao_totalizacao_alimentos_print.html',
        r=rel,
        **active('totalizacao_substituicoes')
    )


@nutricao.route('/nutricao/totalizacao-consumo')
def totalizacao_consumo():
    seed_nutricao()
    return render_template(
        'nutricao_totalizacao_alimentos.html',
        titulo='Totalização do consumo (com substituição)',
        subtitulo='Tudo que foi servido ou gasto no dia, já com a substituição aplicada no cardápio.',
        imprimir_url='/nutricao/totalizacao-consumo/imprimir',
        **_filtros_alimentos_ctx(),
        **active('totalizacao_consumo')
    )


@nutricao.route('/nutricao/totalizacao-consumo/imprimir')
def totalizacao_consumo_imprimir():
    seed_nutricao()
    data_ref, imprimir_por, filtros, horarios = _args_totalizacao_alimentos()
    rel = gerar_totalizacao_consumo(
        data_ref=data_ref,
        imprimir_por=imprimir_por,
        filtros=filtros,
        horarios=horarios,
    )
    return render_template(
        'nutricao_totalizacao_alimentos_print.html',
        r=rel,
        **active('totalizacao_consumo')
    )


@nutricao.route('/nutricao/cardapio-servido')
def cardapio_servido():
    seed_nutricao()
    return render_template(
        'nutricao_cardapio_servido.html',
        clinicas=_list_clinicas_db(somente_ativas=False),
        enfermarias=list_enfermarias(somente_ativas=True),
        data_padrao=date.today().isoformat(),
        **active('cardapio_servido')
    )


@nutricao.route('/nutricao/cardapio-servido/imprimir')
def cardapio_servido_imprimir():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    clinicas = [x for x in (request.args.get('clinicas') or '').split('|') if x.strip()]
    enfermarias = [x for x in (request.args.get('enfermarias') or '').split('|') if x.strip()]
    horarios = [x for x in (request.args.get('horarios') or '').split(',') if x.strip()]
    rel = gerar_cardapio_servido(
        data_ref=data_ref,
        clinicas=clinicas,
        enfermarias=enfermarias,
        horarios=horarios,
    )
    return render_template(
        'nutricao_cardapio_servido_print.html',
        r=rel,
        **active('cardapio_servido')
    )


@nutricao.route('/nutricao/relatorio-mapa-uma/imprimir')
def relatorio_mapa_uma_imprimir():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    categoria = (request.args.get('categoria') or 'enteral').strip()
    imprimir_por = (request.args.get('imprimir_por') or 'clinica').strip()
    filtro_id = request.args.get('filtro_id', type=int)
    filtro_nome = _filtro_nome_imprimir(
        imprimir_por,
        filtro_id,
        (request.args.get('filtro_nome') or '').strip() or None,
    )
    amostra = None
    if str(request.args.get('imprimir_amostra', '')).lower() in ('1', 'true', 'sim'):
        try:
            amostra = float(request.args.get('amostra_valor') or 50)
        except (TypeError, ValueError):
            amostra = 50.0

    relatorio = totalizar_mapa_uma(
        data_ref=data_ref,
        categoria=categoria,
        imprimir_por=imprimir_por,
        filtro_id=filtro_id,
        filtro_nome=filtro_nome,
        amostra=amostra,
        **_opcoes_mapa_uma(request.args),
    )
    return render_template(
        'nutricao_relatorio_mapa_uma_print.html',
        r=relatorio,
        **active('relatorio_mapa_uma')
    )



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


@nutricao.route('/nutricao/faturamento-valores')
def faturamento_valores():
    seed_nutricao()
    data_de = _parse_date(request.args.get('data_de')) or date.today()
    data_ate = _parse_date(request.args.get('data_ate')) or data_de
    gerar = str(request.args.get('gerar', '')).lower() in ('1', 'true', 'sim')
    rel = relatorio_faturamento_valores(data_de, data_ate) if gerar else None
    return render_template(
        'nutricao_faturamento_valores.html',
        data_de=data_de.isoformat(),
        data_ate=data_ate.isoformat(),
        r=rel,
        **active('faturamento_valores')
    )


@nutricao.route('/nutricao/faturamento-valores/imprimir')
def faturamento_valores_imprimir():
    seed_nutricao()
    data_de = _parse_date(request.args.get('data_de')) or date.today()
    data_ate = _parse_date(request.args.get('data_ate')) or data_de
    rel = relatorio_faturamento_valores(data_de, data_ate)
    return render_template(
        'nutricao_faturamento_valores_print.html',
        r=rel,
        **active('faturamento_valores')
    )


@nutricao.route('/nutricao/faturamento-valores/exportar')
def faturamento_valores_exportar():
    import csv
    import io
    from flask import Response

    seed_nutricao()
    data_de = _parse_date(request.args.get('data_de')) or date.today()
    data_ate = _parse_date(request.args.get('data_ate')) or data_de
    rel = relatorio_faturamento_valores(data_de, data_ate)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Relatório', rel['titulo']])
    w.writerow(['Período', f"{rel['data_de_label']} a {rel['data_ate_label']}"])
    w.writerow([])
    w.writerow([
        'Data', 'Fonte', 'Pessoa', 'Clínica', 'Item', 'Refeição',
        'Qtd', 'Preço unit.', 'Total', 'Origem do preço',
    ])
    for row in rel['linhas']:
        w.writerow([
            row['data_label'], row['fonte'], row['pessoa'], row['clinica'],
            row['item'], row['refeicao'], row['quantidade'],
            f"{row['preco_unitario']:.2f}".replace('.', ','),
            f"{row['total']:.2f}".replace('.', ','),
            row['origem_preco'],
        ])
    w.writerow([])
    w.writerow(['TOTAL', '', '', '', '', '', rel['total_quantidade'], '', f"{rel['total_valor']:.2f}".replace('.', ',')])
    out = '\ufeff' + buf.getvalue()
    return Response(
        out,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=faturamento_valores.csv'},
    )


def _params_faturamento_from_request(src):
    data_de = _parse_date(src.get('data_de')) or date.today()
    data_ate = _parse_date(src.get('data_ate')) or data_de
    tipo = (src.get('tipo') or 'espelho_1').strip()
    por_grupo = str(src.get('por_grupo_clinica', '')).lower() in ('1', 'true', 'sim', 'on')
    sintetico = str(src.get('sintetico', '')).lower() in ('1', 'true', 'sim', 'on')
    return data_de, data_ate, tipo, por_grupo, sintetico


@nutricao.route('/nutricao/faturamento/imprimir')
def faturamento_imprimir():
    seed_nutricao()
    data_de, data_ate, tipo, por_grupo, sintetico = _params_faturamento_from_request(request.args)
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
        autorizacoes=[],
        logs=logs,
        **active('utilitarios')
    )

def _ctx_clinico():
    data_ref = _parse_date(request.values.get('data')) or date.today()
    mapa_id = request.values.get('mapa_id', type=int)
    paciente_id = request.values.get('paciente_id', type=int)
    ctx = contexto_paciente(mapa_id, paciente_id) if (mapa_id or paciente_id) else None
    return data_ref, ctx


@nutricao.route('/nutricao/analise-nutricional')
def analise_nutricional():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    mapa_id = request.args.get('mapa_id', type=int)
    garantir_mapa_do_dia(data_ref)
    opcoes = pacientes_do_mapa(data_ref, 'ambos')
    ctx = contexto_paciente(mapa_id) if mapa_id else None
    aval = None
    if ctx:
        row = buscar_avaliacao(ctx.get('paciente_id'), ctx.get('mapa_id'), data_ref)
        aval = avaliacao_dict(row, ctx) if row else None
    return render_template(
        'nutricao_analise_nutricional.html',
        data_padrao=data_ref.isoformat(),
        opcoes=opcoes,
        ctx=ctx,
        aval=aval,
        laboratorio=LABORATORIO,
        **active('analise_nutricional')
    )


@nutricao.route('/nutricao/api/analise-nutricional/calcular', methods=['POST'])
def api_analise_calcular():
    d = request.get_json(force=True) or {}
    _data_ref, ctx = _ctx_clinico()
    if ctx:
        d.setdefault('sexo', ctx.get('sexo'))
        d.setdefault('idade', ctx.get('idade'))
        d.setdefault('dieta', ctx.get('dieta'))
    return jsonify({
        'ok': True,
        'calculo': calcular_avaliacao(d),
        'macros': macros_da_dieta(d.get('dieta') or (ctx or {}).get('dieta'), d.get('volume_pct')),
    })


@nutricao.route('/nutricao/api/analise-nutricional', methods=['POST'])
def api_analise_salvar():
    seed_nutricao()
    d = request.get_json(force=True) or {}
    data_ref = _parse_date(d.get('data')) or date.today()
    ctx = contexto_paciente(d.get('mapa_id'), d.get('paciente_id'))
    if not ctx:
        return jsonify({'ok': False, 'error': 'Selecione um paciente do mapa'}), 400
    if ctx:
        d.setdefault('sexo', ctx.get('sexo'))
        d.setdefault('idade', ctx.get('idade'))
        d.setdefault('dieta', ctx.get('dieta'))
    row = salvar_avaliacao(d, data_ref, ctx)
    return jsonify({'ok': True, 'avaliacao': avaliacao_dict(row, ctx)})


@nutricao.route('/nutricao/evolucao')
def evolucao_paciente():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    mapa_id = request.args.get('mapa_id', type=int)
    modo = (request.args.get('modo') or 'ambos').strip().lower()
    if modo not in ('tne', 'oral', 'ambos'):
        modo = 'ambos'
    garantir_mapa_do_dia(data_ref)
    opcoes = pacientes_do_mapa(data_ref, modo)
    ctx = contexto_paciente(mapa_id) if mapa_id else None
    historico = []
    if ctx:
        historico = listar_evolucoes(ctx.get('paciente_id'), ctx.get('mapa_id'))
    return render_template(
        'nutricao_evolucao.html',
        data_padrao=data_ref.isoformat(),
        modo=modo,
        opcoes=opcoes,
        ctx=ctx,
        historico=historico,
        **active('evolucao')
    )


@nutricao.route('/nutricao/api/evolucao', methods=['POST'])
def api_evolucao_salvar():
    seed_nutricao()
    d = request.get_json(force=True) or {}
    data_ref = _parse_date(d.get('data')) or date.today()
    ctx = contexto_paciente(d.get('mapa_id'), d.get('paciente_id'))
    if not ctx:
        return jsonify({'ok': False, 'error': 'Selecione um paciente do mapa'}), 400
    item = salvar_evolucao(d, data_ref, ctx)
    return jsonify({'ok': True, 'evolucao': item})


@nutricao.route('/nutricao/api/evolucao/<int:evo_id>', methods=['DELETE'])
def api_evolucao_excluir(evo_id):
    if not excluir_evolucao(evo_id):
        return jsonify({'ok': False, 'error': 'Registro não encontrado'}), 404
    return jsonify({'ok': True})


@nutricao.route('/nutricao/totalizacao-direta')
def totalizacao_direta():
    seed_nutricao()
    data_ref = _parse_date(request.args.get('data')) or date.today()
    clinica = (request.args.get('clinica') or '').strip()
    linhas = listar_totalizacao_direta(data_ref, clinica or None)
    return render_template(
        'nutricao_totalizacao_direta.html',
        data_padrao=data_ref.isoformat(),
        clinica_sel=clinica,
        clinicas=_list_clinicas_db(somente_ativas=True),
        dietas=list_dietas(somente_ativas=True),
        refeicoes=REFEICOES_DIRETAS,
        linhas=linhas,
        **active('totalizacao_direta')
    )


@nutricao.route('/nutricao/api/totalizacao_direta', methods=['GET', 'POST'])
def api_totalizacao_direta():
    seed_nutricao()
    if request.method == 'POST':
        d = request.get_json(force=True) or {}
        data_ref = _parse_date(d.get('data')) or date.today()
        try:
            item = salvar_totalizacao_direta(d, data_ref)
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        return jsonify({'ok': True, 'id': item['id'], 'item': item})
    data_ref = _parse_date(request.args.get('data')) or date.today()
    clinica = (request.args.get('clinica') or '').strip()
    return jsonify(listar_totalizacao_direta(data_ref, clinica or None))


@nutricao.route('/nutricao/api/totalizacao_direta/<int:item_id>', methods=['DELETE'])
def api_totalizacao_direta_excluir(item_id):
    if not excluir_totalizacao_direta(item_id):
        return jsonify({'ok': False, 'error': 'Item não encontrado'}), 404
    return jsonify({'ok': True})

@nutricao.route('/nutricao/api/autorizacoes_substituicao', methods=['GET', 'POST', 'PUT'])
def api_autorizacoes_substituicao():
    return jsonify([])

@nutricao.route('/nutricao/api/logs', methods=['GET'])
def api_logs():
    from audit_service import listar_logs
    _, logs = listar_logs(modulo='nutricao', limit=100)
    return jsonify(logs)
