from password_utils import generate_password_hash

MASTER_EMAIL = 'informatica@saogeraldoservice.com.br'
MASTER_SENHA = '230407'
MASTER_NOME = 'Informática São Geraldo'

SISTEMAS = {
    'chamados': {
        'nome': 'Sistema de Gestão de Chamados',
        'campo': 'perm_chamados',
        'endpoint': 'main.dashboard',
        'menus': [
            ('dashboard', 'Dashboard'),
            ('novo_chamado', 'Abrir novo ticket'),
            ('chamados', 'Tickets'),
            ('chats', 'Chats'),
            ('clientes', 'Clientes'),
            ('equipamentos', 'Equipamentos'),
            ('telefones_ramais', 'Telefones e Ramais'),
            ('cameras', 'Cadastro de Câmeras'),
            ('portoes', 'Cadastro de Portões'),
            ('tecnicos', 'Técnicos'),
            ('estoque', 'Estoque'),
            ('recursos', 'Recursos'),
            ('relatorios', 'Relatórios'),
            ('agenda', 'Agenda'),
            ('conhecimentos', 'Conhecimentos'),
            ('automacoes', 'Automações'),
            ('acesso_remoto', 'Acesso remoto'),
            ('whatsapp_mensagem', 'Conf. Mensagem WhatsApp'),
            ('auditoria', 'Auditoria'),
        ],
    },
    'nutricao': {
        'nome': 'Sistema Nutrição Hospitalar',
        'campo': 'perm_nutricao',
        'endpoint': 'nutricao.dashboard',
        'menus': [
            ('mapa_refeicoes', 'Mapa de Refeições Pacientes', 'Menu'),
            ('refeicao_acompanhante', 'Refeição acompanhante', 'Menu'),
            ('refeicoes_funcionarios', 'Refeições funcionários', 'Menu'),
            ('estoque', 'Estoque', 'Menu'),
            ('analise_nutricional', 'Análise nutricional', 'Menu'),
            ('evolucao', 'Evolução do paciente', 'Menu'),
            ('configuracoes', 'Configurações', 'Menu'),
            ('auditoria', 'Auditoria', 'Menu'),
            ('cadastro_pacientes', 'Pacientes', 'Cadastro'),
            ('cadastro_clinicas', 'Clínicas', 'Cadastro'),
            ('cadastro_enfermarias', 'Enfermarias', 'Cadastro'),
            ('cadastro_leitos', 'Leitos', 'Cadastro'),
            ('cadastro_categorias', 'Categoria', 'Cadastro'),
            ('cadastro_grupos_dietas', 'Grupos de Dietas', 'Cadastro'),
            ('cadastro_dietas', 'Dietas', 'Cadastro'),
            ('cadastro_vias', 'Vias de Administração', 'Cadastro'),
            ('cadastro_uma_formula', 'Fórmula Infantil', 'Cadastro'),
            ('cadastro_uma_enteral', 'Enteral', 'Cadastro'),
            ('cadastro_uma_suplemento', 'Suplemento', 'Cadastro'),
            ('cadastro_uma_lve', 'LVE', 'Cadastro'),
            ('cadastro_tipos_refeicao', 'Tipos de Refeição', 'Cadastro'),
            ('cadastro_cardapios', 'Cardápios', 'Cadastro'),
            ('cadastro_precos_refeicoes', 'Preços das Refeições', 'Cadastro'),
            ('cadastro_nutricional', 'Nutricional', 'Cadastro'),
            ('cadastro_pratos_liquidos', 'Dietas Líquidas', 'Cadastro'),
            ('cadastro_produtos', 'Produtos', 'Cadastro'),
            ('cadastro_fornecedores', 'Fornecedores', 'Cadastro'),
            ('cadastro_etiquetas', 'Etiquetas', 'Cadastro'),
            ('relatorio_mapa_uma', 'Mapa da U.M.A.', 'Impressões e Relatórios'),
            ('impressao_etiquetas', 'Impressão de etiquetas', 'Impressões e Relatórios'),
            ('impressao_mapa', 'Impressão mapa da nutrição', 'Impressões e Relatórios'),
            ('impressao_mapa_distribuicao', 'Impressão mapa distribuição', 'Impressões e Relatórios'),
            ('totalizacao_dietas_refeicoes', 'Totalização de dietas e refeições', 'Impressões e Relatórios'),
            ('totalizacao_substituicoes', 'Totalização de substituições', 'Impressões e Relatórios'),
            ('totalizacao_consumo', 'Totalização do consumo', 'Impressões e Relatórios'),
            ('cardapio_servido', 'Cardápio servido', 'Impressões e Relatórios'),
            ('relatorios', 'Análise de Custos', 'Financeiro'),
            ('faturamento', 'Faturamento', 'Financeiro'),
            ('faturamento_valores', 'Faturamento com valores', 'Financeiro'),
        ],
    },
    'pesagem': {
        'nome': 'Sistema de Controle de Pesagem',
        'campo': 'perm_pesagem',
        'endpoint': 'pesagem.dashboard',
        'menus': [
            ('dashboard', 'Leituras'),
            ('balancas', 'Balanças'),
            ('clientes', 'Cadastro de Cliente'),
            ('lancamento', 'Lançamento avulso'),
            ('whatsapp', 'Conf. WhatsApp'),
            ('agente', 'Agente pesagem (exe)'),
            ('auditoria', 'Auditoria'),
        ],
    },
    'logistica': {
        'nome': 'Sistema de Controle de Logística',
        'campo': 'perm_logistica',
        'endpoint': 'logistica.dashboard',
        'menus': [
            ('dashboard', 'Visão Geral'),
            ('lancamentos', 'Combustível e Pedágio'),
            ('manutencao', 'Notas e Manutenção'),
            ('frota', 'Frota'),
            ('dp', 'Departamento pessoal'),
            ('entregas', 'Expedição'),
            ('operacao', 'Operação Logística'),
            ('rotas', 'Operação — Grade de rotas'),
            ('revisoes', 'Operação — Revisões'),
            ('folgas', 'Operação — Folgas'),
            ('ociosidade', 'Operação — Ociosidade'),
            ('checklist', 'Operação — Check-list'),
            ('higiene', 'Operação — Higiene'),
            ('coletas', 'Controle de peso'),
            ('auditoria', 'Auditoria'),
        ],
    },
    'acesso': {
        'nome': 'Sistema de Controle de Acesso',
        'campo': 'perm_acesso',
        'endpoint': 'acesso.dashboard',
        'menus': [
            ('pessoas', 'Pessoas — Cadastros'),
            ('escalas', 'Pessoas — Escalas'),
            ('pessoas_veiculos', 'Pessoas — Veículos'),
            ('visitantes', 'Pessoas — Visitantes'),
            ('empresas', 'Pessoas — Empresas'),
            ('classificacoes', 'Hierarquia — Classificações'),
            ('cadastros_diversos', 'Hierarquia — Cadastros Diversos'),
            ('equipamentos', 'Acesso — Equipamentos'),
            ('grupos', 'Acesso — Horários & Grupos'),
            ('ambientes', 'Acesso — Gestão de Ambientes'),
            ('estacionamentos', 'Acesso — Estacionamentos'),
            ('impressoras', 'Acesso — Impressoras'),
            ('operacoes', 'Acesso — Operações'),
            ('limpeza', 'Acesso — Limpeza de Dados'),
            ('sync_offline', 'Acesso — Sincronizar Offline'),
            ('controle_adicional', 'Parâmetros — Controle Adicional'),
            ('param_refeicoes', 'Parâmetros — Refeições'),
            ('param_documentos', 'Parâmetros — Documentos'),
            ('dashboard', 'Relatórios — Dashboard'),
            ('eventos', 'Relatórios — Acessos'),
            ('veiculos', 'Relatórios — Veículos'),
            ('refeicoes', 'Relatórios — Refeições'),
            ('permanencia', 'Relatórios — Permanência'),
            ('auditoria', 'Relatórios — Auditoria'),
            ('usuarios', 'Administração — Usuários'),
            ('permissoes', 'Administração — Permissões'),
            ('backup', 'Administração — Backup'),
            ('documentacao', 'Administração — Documentação'),
            ('sobre', 'Sobre o Sistema'),
        ],
    },
    'portal': {
        'nome': 'Opções do portal (menu superior direito)',
        'campo': 'perm_portal',
        'endpoint': 'main.inicio',
        'oculto_inicio': True,
        'menus': [
            ('alterar_senha', 'Alterar senha'),
            ('acessos', 'Acessos'),
            ('clientes', 'Clientes'),
            ('configuracoes', 'Configurações'),
        ],
    },
}


NUTRICAO_GRUPOS = {
    'cadastro': (
        'cadastro_pacientes', 'cadastro_clinicas', 'cadastro_enfermarias', 'cadastro_leitos',
        'cadastro_categorias', 'cadastro_grupos_dietas', 'cadastro_dietas', 'cadastro_vias',
        'cadastro_uma_formula', 'cadastro_uma_enteral', 'cadastro_uma_suplemento', 'cadastro_uma_lve',
        'cadastro_tipos_refeicao', 'cadastro_cardapios', 'cadastro_precos_refeicoes',
        'cadastro_nutricional', 'cadastro_pratos_liquidos', 'cadastro_produtos',
        'cadastro_fornecedores', 'cadastro_etiquetas',
    ),
    'impressoes': (
        'relatorio_mapa_uma', 'impressao_etiquetas', 'impressao_mapa',
        'impressao_mapa_distribuicao', 'totalizacao_dietas_refeicoes',
        'totalizacao_substituicoes', 'totalizacao_consumo', 'cardapio_servido',
    ),
    'financeiro': (
        'relatorios', 'faturamento', 'faturamento_valores',
    ),
}


def chaves_menu(meta):
    for item in (meta or {}).get('menus') or []:
        yield item[0]


def heranca_menu_nutricao(menu_key):
    """Chaves antigas que ainda valem quando o item novo não tem linha própria."""
    pais = []
    if menu_key in NUTRICAO_GRUPOS['cadastro']:
        pais.append('cadastro')
    if menu_key == 'mapa_refeicoes':
        pais.append('dashboard')
    if menu_key == 'dashboard':
        pais.append('mapa_refeicoes')
    return pais


def _gravar_menu(usuario, sistema, menu_key, permitido):
    from models import db, PermissaoMenu
    from sqlalchemy.exc import IntegrityError
    perm = usuario.menus.filter_by(sistema=sistema, menu_key=menu_key).first()
    if perm:
        perm.permitido = permitido
        return
    try:
        with db.session.begin_nested():
            db.session.add(PermissaoMenu(
                usuario_id=usuario.id,
                sistema=sistema,
                menu_key=menu_key,
                permitido=permitido,
            ))
    except IntegrityError:
        perm = PermissaoMenu.query.filter_by(
            usuario_id=usuario.id, sistema=sistema, menu_key=menu_key
        ).first()
        if perm:
            perm.permitido = permitido


def permissoes_efetivas(usuario, sistema):
    meta = SISTEMAS.get(sistema) or {}
    return {chave: bool(usuario.tem_menu(sistema, chave)) for chave in chaves_menu(meta)}


def aplicar_permissoes_formulario(usuario, form):
    for sistema, meta in SISTEMAS.items():
        liberado = usuario.is_master or form.get(f'sistema_{sistema}') == 'on'
        setattr(usuario, meta['campo'], True if usuario.is_master else liberado)
        for menu_key in chaves_menu(meta):
            permitido = usuario.is_master or (
                liberado and form.get(f'menu_{sistema}_{menu_key}') == 'on'
            )
            _gravar_menu(usuario, sistema, menu_key, permitido)


def conceder_acesso_total(usuario):
    usuario.perm_chamados = True
    usuario.perm_nutricao = True
    usuario.perm_pesagem = True
    usuario.perm_logistica = True
    usuario.perm_acesso = True
    usuario.perm_portal = True
    for sistema, meta in SISTEMAS.items():
        for menu_key in chaves_menu(meta):
            _gravar_menu(usuario, sistema, menu_key, True)


def garantir_acesso_master():
    from models import db, Usuario
    usuario = Usuario.query.filter_by(email=MASTER_EMAIL).first()
    if not usuario:
        usuario = Usuario(
            nome=MASTER_NOME,
            email=MASTER_EMAIL,
            usuario='informatica',
            senha=generate_password_hash(MASTER_SENHA),
            tipo='admin',
            ativo=True,
            is_master=True,
        )
        db.session.add(usuario)
        db.session.flush()
    else:
        usuario.nome = MASTER_NOME
        usuario.ativo = True
        usuario.is_master = True
        usuario.tipo = 'admin'
    conceder_acesso_total(usuario)
    db.session.commit()
    ensure_portal_opcoes_legado()
    return usuario


def ensure_portal_opcoes_legado():
    """Garante perm_portal + menus do menu superior para quem já tinha Acessos."""
    from models import db, Usuario, PermissaoMenu
    menus = SISTEMAS.get('portal', {}).get('menus') or []
    if not menus:
        return
    q = Usuario.query.filter(
        db.or_(
            Usuario.is_master.is_(True),
            Usuario.perm_acesso.is_(True),
            Usuario.perm_portal.is_(True),
        )
    )
    for u in q.all():
        if not bool(getattr(u, 'perm_portal', False)):
            u.perm_portal = True
        if u.menus.filter_by(sistema='portal').first():
            continue
        for menu_key, _label in menus:
            db.session.add(PermissaoMenu(
                usuario_id=u.id,
                sistema='portal',
                menu_key=menu_key,
                permitido=True,
            ))
    db.session.commit()
