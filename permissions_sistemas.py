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
            ('recursos', 'Recursos'),
            ('relatorios', 'Relatórios'),
            ('agenda', 'Agenda'),
            ('conhecimentos', 'Conhecimentos'),
            ('automacoes', 'Automações'),
            ('auditoria', 'Auditoria'),
        ],
    },
    'nutricao': {
        'nome': 'Sistema Nutrição Hospitalar',
        'campo': 'perm_nutricao',
        'endpoint': 'nutricao.dashboard',
        'menus': [
            ('dashboard', 'Dashboard'),
            ('cadastro', 'Cadastro'),
            ('mapa_refeicoes', 'Mapa de Refeições'),
            ('estoque', 'Estoque'),
            ('faturamento', 'Faturamento'),
            ('auditoria', 'Auditoria'),
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
}


def aplicar_permissoes_formulario(usuario, form):
    from models import db, PermissaoMenu
    for sistema, meta in SISTEMAS.items():
        liberado = usuario.is_master or form.get(f'sistema_{sistema}') == 'on'
        setattr(usuario, meta['campo'], True if usuario.is_master else liberado)
        for menu_key, _label in meta['menus']:
            permitido = usuario.is_master or (
                liberado and form.get(f'menu_{sistema}_{menu_key}') == 'on'
            )
            perm = usuario.menus.filter_by(sistema=sistema, menu_key=menu_key).first()
            if not perm:
                db.session.add(PermissaoMenu(
                    usuario_id=usuario.id,
                    sistema=sistema,
                    menu_key=menu_key,
                    permitido=permitido,
                ))
            else:
                perm.permitido = permitido


def conceder_acesso_total(usuario):
    from models import db, PermissaoMenu
    usuario.perm_chamados = True
    usuario.perm_nutricao = True
    usuario.perm_pesagem = True
    usuario.perm_acesso = True
    for sistema, meta in SISTEMAS.items():
        for menu_key, _label in meta['menus']:
            perm = usuario.menus.filter_by(sistema=sistema, menu_key=menu_key).first()
            if not perm:
                db.session.add(PermissaoMenu(
                    usuario_id=usuario.id,
                    sistema=sistema,
                    menu_key=menu_key,
                    permitido=True,
                ))
            else:
                perm.permitido = True


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
    return usuario
