from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 no Linux de produção
    from backports.zoneinfo import ZoneInfo

db = SQLAlchemy()

TZ_BRASILIA = ZoneInfo('America/Sao_Paulo')


def now_brasilia():
    """Horário atual em Brasília (naive), para gravar/exibir consistente no app."""
    return datetime.now(TZ_BRASILIA).replace(tzinfo=None)


def to_brasilia_naive(dt):
    """Normaliza datetime para Brasília naive (sem tzinfo).

    - Aware: converte para America/Sao_Paulo e remove tzinfo.
    - Naive: assume já estar em horário de Brasília (convenção do app após
      gravar com now_brasilia); não desloca de novo.
    """
    if dt is None:
        return None
    if getattr(dt, 'tzinfo', None) is not None:
        return dt.astimezone(TZ_BRASILIA).replace(tzinfo=None)
    return dt


def fmt_brasilia(dt, fmt='%d/%m/%Y %H:%M'):
    """Formata datetime em horário de Brasília; string vazia se ausente."""
    local = to_brasilia_naive(dt)
    return local.strftime(fmt) if local else ''

SETORES_CHAMADO = ('Informática', 'Elétrica', 'Obra', 'Compras')
SETORES_NUTRICAO = (
    'Nutricionista UAN',
    'Nutricionista Clínica',
    'Administrativo',
    'Técnico nutrição',
    'Gerente nutrição',
)
TIPO_SETOR_CHAMADOS = 'chamados'
TIPO_SETOR_NUTRICAO = 'nutricao'
SETOR_COMPRAS = 'Compras'
STATUS_AGUARDAR_PECA = 'Aguardar peça'
STATUS_ENCAMINHADO = 'Encaminhado'
STATUS_REAGENDADO = 'Reagendado'
STATUS_DEVOLVIDO = 'Devolvido'
STATUS_SILENCIA_TOQUE = (STATUS_AGUARDAR_PECA, STATUS_ENCAMINHADO, STATUS_REAGENDADO)
STATUS_ATENDIDO = 'Atendido'
STATUS_CONCLUIDO = 'Concluído'
STATUS_FECHADOS = (STATUS_ATENDIDO, STATUS_CONCLUIDO)
TIPO_HOP_ENCAMINHAR = 'encaminhar'
TIPO_HOP_DEVOLVER = 'devolver'
TIPO_HOP_PECA = 'peca'
MESA_PADRAO = 'Informática'
PASTA_CONHECIMENTO_PADRAO = 'Conhecimentos'
TIPOS_CONTRATO = (
    'Suporte',
    'Locação',
    'Projeto',
    'Manutenção',
    'Horas',
    'Mensalidade',
    'Avulso',
    'Personalizado',
)
CANAIS_MENSAGEM = ('E-mail', 'WhatsApp', 'Telefone', 'Chat')
CANAIS_ENVIO_LIVE = ('E-mail',)
PRIORIDADES_SLA = ('Alta', 'Normal', 'Baixa')
SLA_PADRAO_HORAS = {
    'Alta': (4, 8),
    'Normal': (8, 24),
    'Média': (8, 24),
    'Baixa': (24, 72),
}
SLA_CONTRATO_TIPO = {
    'Suporte': (8, 24),
    'Locação': (12, 48),
    'Projeto': (24, 72),
    'Manutenção': (8, 24),
    'Horas': (4, 16),
    'Mensalidade': (8, 24),
    'Avulso': (16, 48),
    'Personalizado': (8, 24),
}
SLA_ALERTA_HORAS = 2
TICKET_PARADO_HORAS = 24


def status_fechado(status):
    """Atendido (técnico finalizou) e Concluído são estados encerrados."""
    return (status or '').strip() in STATUS_FECHADOS


def _fold_setor(valor):
    raw = (valor or '').strip().lower()
    trans = str.maketrans({
        'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c',
    })
    return raw.translate(trans)


def setores_padrao(tipo):
    if tipo == TIPO_SETOR_NUTRICAO:
        return SETORES_NUTRICAO
    return SETORES_CHAMADO


def listar_setores(tipo):
    """Catálogo do dropdown: padrões sempre primeiro, depois extras cadastrados."""
    nomes = list(setores_padrao(tipo))
    seen = {_fold_setor(n) for n in nomes}
    try:
        rows = (
            SetorFuncao.query.filter_by(tipo=tipo)
            .order_by(SetorFuncao.id.asc())
            .all()
        )
        for row in rows:
            key = _fold_setor(row.nome)
            if key and key not in seen:
                nomes.append(row.nome)
                seen.add(key)
    except Exception:
        pass
    return nomes


def listar_setores_detalhe(tipo):
    """Lista setores cadastrados no banco (id, nome, padrao) para a grade."""
    if tipo not in (TIPO_SETOR_CHAMADOS, TIPO_SETOR_NUTRICAO):
        return []
    rows = (
        SetorFuncao.query.filter_by(tipo=tipo)
        .order_by(SetorFuncao.padrao.desc(), SetorFuncao.nome.asc(), SetorFuncao.id.asc())
        .all()
    )
    return [
        {
            'id': int(r.id),
            'nome': r.nome or '',
            'padrao': bool(r.padrao),
        }
        for r in rows
    ]


def normalizar_setor(tipo, valor):
    """Casa com o catálogo do tipo (padrões + extras), ignorando acento/caixa."""
    raw = (valor or '').strip()
    if not raw:
        return ''
    key = _fold_setor(raw)
    for nome in listar_setores(tipo):
        if _fold_setor(nome) == key:
            return nome
    if tipo == TIPO_SETOR_CHAMADOS:
        mapa = {
            'informatica': 'Informática',
            'obra': 'Obra',
            'eletrica': 'Elétrica',
            'compras': 'Compras',
        }
        return mapa.get(key, '')
    return ''


def normalizar_setor_chamado(valor):
    """Normaliza o setor de encaminhamento (padrões + extras de chamados)."""
    return normalizar_setor(TIPO_SETOR_CHAMADOS, valor)


def adicionar_setor(tipo, nome):
    """Inclui uma função/setor extra no catálogo do tipo. Não aceita vazio nem duplicata."""
    nome = (nome or '').strip()
    if not nome:
        raise ValueError('Informe o nome da função ou setor.')
    if len(nome) > 80:
        raise ValueError('Nome muito longo (máximo 80 caracteres).')
    if tipo not in (TIPO_SETOR_CHAMADOS, TIPO_SETOR_NUTRICAO):
        raise ValueError('Tipo de setor inválido.')
    if normalizar_setor(tipo, nome):
        raise ValueError('Essa função ou setor já existe.')
    row = SetorFuncao(tipo=tipo, nome=nome, padrao=False)
    db.session.add(row)
    db.session.commit()
    return row.nome


def atualizar_setor(setor_id, nome):
    """Renomeia um setor cadastrado (mesmo tipo, sem duplicar)."""
    row = SetorFuncao.query.get(int(setor_id))
    if not row:
        raise ValueError('Setor não encontrado.')
    nome = (nome or '').strip()
    if not nome:
        raise ValueError('Informe o nome da função ou setor.')
    if len(nome) > 80:
        raise ValueError('Nome muito longo (máximo 80 caracteres).')
    key = _fold_setor(nome)
    for c in SetorFuncao.query.filter(SetorFuncao.tipo == row.tipo, SetorFuncao.id != row.id).all():
        if _fold_setor(c.nome) == key:
            raise ValueError('Essa função ou setor já existe.')
    row.nome = nome
    db.session.commit()
    return row.nome


def excluir_setor(setor_id):
    """Remove setor extra. Setores padrão do sistema não podem ser excluídos."""
    row = SetorFuncao.query.get(int(setor_id))
    if not row:
        raise ValueError('Setor não encontrado.')
    if bool(row.padrao):
        raise ValueError('Setor padrão do sistema não pode ser excluído.')
    tipo = row.tipo
    db.session.delete(row)
    db.session.commit()
    return tipo


class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    endereco = db.Column(db.String(200))
    # Colunas do schema GitHub (criadas na migração Linux se faltarem)
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    responsavel = db.Column(db.String(100))
    telefone_responsavel = db.Column(db.String(20))
    ativo = db.Column(db.Boolean, default=True)
    # Flags de habilitação por sistema (cadastro unificado portal/chamados/nutrição)
    habilitado_chamados = db.Column(db.Boolean, default=True)
    habilitado_nutricao = db.Column(db.Boolean, default=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Cliente {self.nome}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'endereco': self.endereco,
            'telefone': self.telefone,
            'email': self.email,
            'responsavel': self.responsavel,
            'telefone_responsavel': self.telefone_responsavel,
            'habilitado_chamados': bool(self.habilitado_chamados),
            'habilitado_nutricao': bool(self.habilitado_nutricao),
            'ativo': bool(self.ativo),
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else None
        }


class Chamado(db.Model):
    __tablename__ = 'chamados'

    id = db.Column(db.Integer, primary_key=True)
    numero_chamado = db.Column(db.String(20), unique=True, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    cliente = db.relationship('Cliente', backref='chamados')
    tipo_servico = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text)
    status = db.Column(db.String(40), default='Pendente')
    prioridade = db.Column(db.String(10), default='Normal')
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesas.id'), index=True)
    mesa = db.relationship('MesaServico', foreign_keys=[mesa_id])
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), index=True)
    contrato = db.relationship('Contrato', foreign_keys=[contrato_id])
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_conclusao = db.Column(db.DateTime)
    data_inicio_atendimento = db.Column(db.DateTime, nullable=True)
    data_reagendamento = db.Column(db.Date, nullable=True)
    observacoes = db.Column(db.Text)
    equipamento = db.Column(db.String(100), nullable=True)
    patrimonio = db.Column(db.String(50), nullable=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamentos.id'), nullable=True)
    equipamento_cadastro = db.relationship('Equipamento', foreign_keys=[equipamento_id])
    # Obrigatório no MySQL deste servidor
    tecnico_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    tecnico = db.relationship('Usuario', foreign_keys=[tecnico_id], backref='chamados_tecnico')
    atendente_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    atendente = db.relationship('Usuario', foreign_keys=[atendente_id], backref='chamados_atendente')
    atendendo_em = db.Column(db.DateTime, nullable=True)
    atendimento_notas = db.Column(db.Text)
    setor_destino = db.Column(db.String(80))
    setor_origem = db.Column(db.String(80))
    setor_tecnico_id = db.Column(db.Integer, db.ForeignKey('chamado_setores.id'), nullable=True)
    setor_tecnico = db.relationship('ChamadoSetor', foreign_keys='[Chamado.setor_tecnico_id]')
    encaminhamento_instrucoes = db.Column(db.Text)
    encaminhado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    encaminhado_em = db.Column(db.DateTime)
    encaminhado_por = db.relationship('Usuario', foreign_keys=[encaminhado_por_id])
    canal_abertura = db.Column(db.String(20))
    contato_abertura = db.Column(db.String(120))
    atendimentos = db.relationship(
        'ChamadoAtendimento', backref='chamado', cascade='all, delete-orphan', lazy='dynamic'
    )
    fotos = db.relationship(
        'ChamadoFoto', backref='chamado', cascade='all, delete-orphan', lazy='dynamic'
    )
    encaminhamentos = db.relationship(
        'ChamadoEncaminhamento', backref='chamado', cascade='all, delete-orphan', lazy='dynamic'
    )
    mensagens = db.relationship(
        'ChamadoMensagem', backref='chamado', cascade='all, delete-orphan', lazy='dynamic'
    )

    def __repr__(self):
        return f'<Chamado {self.numero_chamado}>'

    def to_dict(self):
        return {
            'id': self.id,
            'numero_chamado': self.numero_chamado,
            'cliente': self.cliente.nome if self.cliente else None,
            'tipo_servico': self.tipo_servico,
            'descricao': self.descricao,
            'status': self.status,
            'prioridade': self.prioridade,
            'mesa_id': self.mesa_id,
            'mesa': self.mesa.nome if self.mesa else None,
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else None,
            'data_inicio_atendimento': fmt_brasilia(self.data_inicio_atendimento),
            'data_conclusao': self.data_conclusao.strftime('%d/%m/%Y %H:%M') if self.data_conclusao else None,
            'data_reagendamento': self.data_reagendamento.strftime('%d/%m/%Y') if self.data_reagendamento else None,
            'observacoes': self.observacoes,
            'equipamento': self.equipamento,
            'patrimonio': self.patrimonio,
            'equipamento_id': self.equipamento_id,
            'atendimento_notas': self.atendimento_notas,
            'atendente_id': self.atendente_id,
            'atendente': self.atendente.nome if self.atendente else None,
            'setor_destino': self.setor_destino,
            'setor_origem': self.setor_origem,
            'encaminhamento_instrucoes': self.encaminhamento_instrucoes,
            'canal_abertura': self.canal_abertura,
            'contato_abertura': self.contato_abertura,
        }


class Usuario(db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Login curto do Controle de Acesso (além do e-mail)
    usuario = db.Column(db.String(80), unique=True, index=True)
    # Banco legado usa senha_hash; atributo Python permanece "senha" (código GitHub)
    senha = db.Column('senha_hash', db.String(255), nullable=False)
    tipo = db.Column(db.String(20), default='operador')
    token = db.Column(db.String(64))
    reset_token = db.Column(db.String(80))
    reset_token_expira = db.Column(db.DateTime)
    ativo = db.Column(db.Boolean, default=True)
    is_master = db.Column(db.Boolean, default=False)
    perm_chamados = db.Column(db.Boolean, default=False)
    perm_nutricao = db.Column(db.Boolean, default=False)
    perm_pesagem = db.Column(db.Boolean, default=False)
    perm_logistica = db.Column(db.Boolean, default=False)
    perm_acesso = db.Column(db.Boolean, default=False)
    perm_portal = db.Column(db.Boolean, default=False)
    setor = db.Column(db.String(80))
    setor_nutricao = db.Column(db.String(80))
    telefone = db.Column(db.String(20))
    # Cliente do cadastro unificado (escopo Nutrição / vínculo operacional)
    # cliente_todos=True → vê todos os clientes; cliente_id=X → um cliente; ambos vazios → sem vínculo
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True, index=True)
    cliente_todos = db.Column(db.Boolean, default=False)
    cliente = db.relationship('Cliente', foreign_keys=[cliente_id], backref='usuarios')
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    menus = db.relationship('PermissaoMenu', backref='usuario', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<Usuario {self.email}>'

    def tem_sistema(self, sistema):
        if self.is_master or self.tipo == 'admin':
            return True
        return bool(getattr(self, f'perm_{sistema}', False))

    def tem_menu(self, sistema, menu_key):
        if self.is_master or self.tipo == 'admin':
            return True
        if not self.tem_sistema(sistema):
            return False
        perm = self.menus.filter_by(sistema=sistema, menu_key=menu_key).first()
        if perm is None:
            return True
        return bool(perm.permitido)

    def menus_liberados(self, sistema):
        return {p.menu_key: p.permitido for p in self.menus.filter_by(sistema=sistema).all()}

    def pode_gerenciar_acessos(self):
        """Compat: Acessos no portal (menu superior) ou legado perm_acesso / master."""
        return self.pode_opcao_portal('acessos')

    def pode_opcao_portal(self, menu_key):
        """Itens do menu Opções (canto superior direito) na home."""
        if self.is_master or self.tipo == 'admin':
            return True
        # Se já há permissões explícitas do portal, elas mandam
        tem_portal = self.menus.filter_by(sistema='portal').first() is not None
        if tem_portal or bool(getattr(self, 'perm_portal', False)):
            return self.tem_menu('portal', menu_key)
        # Legado: Alterar senha sempre; demais via perm_acesso
        if menu_key == 'alterar_senha':
            return True
        return bool(self.perm_acesso)


class SetorFuncao(db.Model):
    """Catálogo de funções/setores dos dropdowns de Acessos (chamados vs nutrição)."""
    __tablename__ = 'setores_funcao'

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, index=True)
    nome = db.Column(db.String(80), nullable=False)
    padrao = db.Column(db.Boolean, default=False, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('tipo', 'nome', name='uq_setores_funcao_tipo_nome'),
    )


class ChamadoSetor(db.Model):
    """Setores técnicos para vinculação de chamados."""
    __tablename__ = 'chamado_setores'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    tecnicos = db.relationship('ChamadoTecnico', backref='setor', lazy='dynamic')

    def __repr__(self):
        return f'<ChamadoSetor {self.nome}>'


FUNCOES_TECNICO = (
    ('assistente', 'Assistente'),
    ('tecnico', 'Técnico'),
    ('supervisor', 'Supervisor'),
    ('gestor', 'Gestor'),
)
FUNCOES_TECNICO_KEYS = {k for k, _ in FUNCOES_TECNICO}
FUNCOES_TECNICO_LABEL = dict(FUNCOES_TECNICO)
FUNCOES_MESA_MULTIPLA = frozenset({'supervisor', 'gestor'})


class ChamadoTecnico(db.Model):
    """Técnicos vinculados a setores e mesas de serviço."""
    __tablename__ = 'chamado_tecnicos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    whatsapp = db.Column(db.String(20))
    funcao = db.Column(db.String(20), nullable=True)
    setor_id = db.Column(db.Integer, db.ForeignKey('chamado_setores.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])
    mesas = db.relationship(
        'MesaServico',
        secondary='chamado_tecnico_mesas',
        lazy='selectin',
        order_by='MesaServico.nome',
    )

    @property
    def funcao_label(self):
        return FUNCOES_TECNICO_LABEL.get(self.funcao or '', self.funcao or '')

    @property
    def mesas_ids(self):
        try:
            return [int(m.id) for m in (self.mesas or []) if m is not None and getattr(m, 'id', None) is not None]
        except Exception:
            return []

    @property
    def mesas_label(self):
        try:
            return ', '.join(m.nome for m in (self.mesas or []) if m and m.nome)
        except Exception:
            return ''

    def dados_edicao(self):
        """Dict só com tipos JSON-serializáveis (evita Undefined no |tojson do template)."""
        return {
            'id': int(self.id) if self.id is not None else 0,
            'nome': self.nome or '',
            'email': self.email or '',
            'whatsapp': getattr(self, 'whatsapp', None) or '',
            'funcao': self.funcao or '',
            'mesa_ids': list(self.mesas_ids or []),
        }

    def __repr__(self):
        return f'<ChamadoTecnico {self.nome}>'


class PermissaoMenu(db.Model):
    __tablename__ = 'permissoes_menu'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    sistema = db.Column(db.String(30), nullable=False)
    menu_key = db.Column(db.String(50), nullable=False)
    permitido = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'sistema', 'menu_key', name='uq_usuario_sistema_menu'),
    )


class ConfiguracaoEmail(db.Model):
    __tablename__ = 'configuracao_email'

    id = db.Column(db.Integer, primary_key=True)
    servidor = db.Column(db.String(200), default='')
    porta = db.Column(db.Integer, default=587)
    usar_tls = db.Column(db.Boolean, default=True)
    usuario = db.Column(db.String(200), default='')
    senha = db.Column(db.String(255), default='')
    remetente = db.Column(db.String(200), default='')
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecursoGrupo(db.Model):
    """Grupo de recursos dentro de um cliente."""
    __tablename__ = 'recurso_grupos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False, index=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    cliente = db.relationship('Cliente', backref='recurso_grupos')

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'nome', name='uq_recurso_grupos_cliente_nome'),
    )


def grupo_recurso_padrao(cliente_id):
    if not cliente_id:
        return None
    row = RecursoGrupo.query.filter_by(cliente_id=cliente_id, nome=GRUPO_RECURSO_PADRAO).first()
    if row:
        return row
    row = RecursoGrupo(nome=GRUPO_RECURSO_PADRAO, cliente_id=int(cliente_id))
    db.session.add(row)
    db.session.flush()
    return row


TIPOS_EQUIPAMENTO = (
    ('ti', 'Equipamento de TI'),
    ('nutricao', 'Equipamento da manutenção de nutrição'),
)
TIPOS_EQUIPAMENTO_KEYS = {k for k, _ in TIPOS_EQUIPAMENTO}
ACESORIOS_SUGERIDOS_TI = (
    'Equipamento',
    'Fonte/Carregador',
    'Cabo de alimentação',
    'Teclado',
    'Mouse',
    'Monitor',
    'Headset',
    'Dock station',
    'Bolsa/Mochila',
)
ACESORIOS_SUGERIDOS_NUTRICAO = (
    'Equipamento',
    'Cabo de alimentação',
    'Manual do equipamento',
    'Kit de acessórios',
    'Peças de reposição',
    'Ferramentas',
)


def normalizar_tipo_eq(value):
    raw = (value or '').strip().lower()
    if raw in ('nutricao', 'nutrição', 'manutencao', 'manutenção', 'manutencao_nutricao'):
        return 'nutricao'
    return 'ti'


def label_tipo_eq(tipo):
    tipo = normalizar_tipo_eq(tipo)
    for chave, label in TIPOS_EQUIPAMENTO:
        if chave == tipo:
            return label
    return 'Equipamento de TI'


def textos_termo_eq(tipo):
    if normalizar_tipo_eq(tipo) == 'nutricao':
        return {
            'titulo': 'TERMO DE RESPONSABILIDADE PELO USO E GUARDA DE EQUIPAMENTO DE MANUTENÇÃO DE NUTRIÇÃO',
            'setor': 'Manutenção de Nutrição',
            'equipe': 'equipe de Manutenção de Nutrição',
            'label': 'Equipamento da manutenção de nutrição',
            'entrega': 'Responsável pela entrega – Nutrição',
        }
    return {
        'titulo': 'TERMO DE RESPONSABILIDADE PELO USO E GUARDA DE EQUIPAMENTO DE TI',
        'setor': 'Tecnologia da Informação',
        'equipe': 'equipe de Tecnologia da Informação',
        'label': 'Equipamento de TI',
        'entrega': 'Responsável pela entrega – TI',
    }


def acessorios_sugeridos(tipo):
    if normalizar_tipo_eq(tipo) == 'nutricao':
        return list(ACESORIOS_SUGERIDOS_NUTRICAO)
    return list(ACESORIOS_SUGERIDOS_TI)


class Equipamento(db.Model):
    __tablename__ = 'equipamentos'

    id = db.Column(db.Integer, primary_key=True)
    nome_equipamento = db.Column(db.String(100), nullable=False)
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    numero_serie = db.Column(db.String(50), unique=True)
    patrimonio = db.Column(db.String(50), unique=True)
    localizacao = db.Column(db.String(100))
    setor = db.Column(db.String(100))
    local = db.Column(db.String(200))
    ativo = db.Column(db.Boolean, default=True)
    em_estoque = db.Column(db.Boolean, default=False, nullable=False)
    data_compra = db.Column(db.Date)
    data_manutencao = db.Column(db.Date)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    cliente = db.relationship('Cliente', backref='equipamentos')
    tipo_recurso = db.Column(db.String(40), default='Estação')
    tipo_equipamento = db.Column(db.String(20), default='ti', nullable=False)
    grupo_id = db.Column(db.Integer, db.ForeignKey('recurso_grupos.id'), index=True)
    grupo = db.relationship('RecursoGrupo', foreign_keys=[grupo_id])
    usuario_equipamento = db.Column(db.String(120))
    ip = db.Column(db.String(45))
    is_agente = db.Column(db.Boolean, default=False, nullable=False)

    preventiva = db.relationship(
        'EquipamentoPreventiva',
        back_populates='equipamento',
        uselist=False,
        cascade='all, delete-orphan',
    )
    termos = db.relationship(
        'EquipamentoTermo',
        back_populates='equipamento',
        cascade='all, delete-orphan',
        lazy='select',
    )

    def __repr__(self):
        return f'<Equipamento {self.nome_equipamento}>'

    @property
    def equipamento(self):
        """Compat: o banco usa nome_equipamento; alguns DBs não têm a coluna legado."""
        return self.nome_equipamento

    @equipamento.setter
    def equipamento(self, value):
        self.nome_equipamento = value

    def to_dict(self):
        return {
            'id': self.id,
            'codigo': self.patrimonio,
            'nome_equipamento': self.nome_equipamento,
            'nome': self.nome_equipamento,
            'marca': self.marca or '',
            'modelo': self.modelo or '',
            'numero_serie': self.numero_serie or '',
            'patrimonio': self.patrimonio,
            'localizacao': self.localizacao,
            'setor': self.setor or self.localizacao,
            'local': self.local or '',
            'ativo': self.ativo,
            'em_estoque': bool(getattr(self, 'em_estoque', False)) or (self.setor or '').strip().lower() == 'estoque',
            'cliente_id': self.cliente_id,
            'cliente_nome': self.cliente.nome if self.cliente else None,
            'cliente_endereco': (self.cliente.endereco or '') if self.cliente else '',
            'data_compra': self.data_compra.strftime('%d/%m/%Y') if self.data_compra else None,
            'data_compra_iso': self.data_compra.strftime('%Y-%m-%d') if self.data_compra else None,
            'data_manutencao': self.data_manutencao.strftime('%d/%m/%Y') if self.data_manutencao else None,
            'tipo_recurso': self.tipo_recurso or 'Estação',
            'tipo_equipamento': self.tipo_equipamento_norm(),
            'tipo_equipamento_label': self.tipo_equipamento_label(),
            'grupo_id': self.grupo_id,
            'grupo_nome': self.grupo.nome if self.grupo else None,
            'usuario_equipamento': self.usuario_equipamento or '',
            'ip': self.ip or '',
            'is_agente': bool(self.is_agente),
            'atualizado_em': self.atualizado_em.strftime('%d/%m/%Y %H:%M') if self.atualizado_em else None,
            **self._dict_preventiva_termo(),
        }

    def tipo_equipamento_norm(self):
        return normalizar_tipo_eq(getattr(self, 'tipo_equipamento', None))

    def tipo_equipamento_label(self):
        return label_tipo_eq(self.tipo_equipamento_norm())

    def termo_atual(self):
        itens = list(self.termos or [])
        if not itens:
            return None
        return max(itens, key=lambda t: t.id)

    def _dict_preventiva_termo(self):
        prev = self.preventiva
        termo = self.termo_atual()
        return {
            'preventiva_ativa': bool(prev and prev.ativa),
            'preventiva_frequencia': (prev.frequencia if prev else '') or '',
            'preventiva_proxima': prev.proxima_data.strftime('%Y-%m-%d') if prev and prev.proxima_data else None,
            'preventiva_proxima_br': prev.proxima_data.strftime('%d/%m/%Y') if prev and prev.proxima_data else None,
            'preventiva_duracao_dias': int(prev.duracao_dias or 1) if prev else 1,
            'termo_id': termo.id if termo else None,
            'termo_status': (termo.status if termo else '') or '',
            'termo_responsavel': (termo.responsavel_nome if termo else '') or '',
            'termo_assinado_em': termo.assinado_em.strftime('%d/%m/%Y %H:%M') if termo and termo.assinado_em else None,
        }


FREQUENCIAS_PREVENTIVA = (
    ('semanal', 'Semanal'),
    ('quinzenal', 'Quinzenal'),
    ('mensal', 'Mensal'),
    ('trimestral', 'Trimestral'),
    ('semestral', 'Semestral'),
    ('anual', 'Anual'),
)
FREQUENCIAS_PREVENTIVA_KEYS = {k for k, _ in FREQUENCIAS_PREVENTIVA}


class EquipamentoPreventiva(db.Model):
    """Agenda de manutenção preventiva por patrimônio; a automação abre o chamado no vencimento."""
    __tablename__ = 'equipamento_preventivas'

    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(
        db.Integer, db.ForeignKey('equipamentos.id'), nullable=False, unique=True, index=True
    )
    ativa = db.Column(db.Boolean, default=False, nullable=False)
    frequencia = db.Column(db.String(20), default='mensal', nullable=False)
    proxima_data = db.Column(db.Date)
    duracao_dias = db.Column(db.Integer, default=1)
    ultimo_chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id', ondelete='SET NULL'))
    ultimo_em = db.Column(db.DateTime)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    equipamento = db.relationship('Equipamento', back_populates='preventiva')
    tecnico = db.relationship('Usuario', foreign_keys=[tecnico_id])
    ultimo_chamado = db.relationship('Chamado', foreign_keys=[ultimo_chamado_id])


class EquipamentoTermo(db.Model):
    """Termo de responsabilidade pelo uso e guarda do equipamento (link + assinatura)."""
    __tablename__ = 'equipamento_termos'

    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamentos.id'), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), default='pendente', nullable=False, index=True)
    responsavel_usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    responsavel_nome = db.Column(db.String(120), nullable=False)
    responsavel_email = db.Column(db.String(120))
    responsavel_telefone = db.Column(db.String(20))
    responsavel_setor = db.Column(db.String(80))
    responsavel_cargo = db.Column(db.String(80))
    responsavel_matricula = db.Column(db.String(40))
    eq_nome = db.Column(db.String(100))
    eq_marca = db.Column(db.String(100))
    eq_modelo = db.Column(db.String(100))
    eq_patrimonio = db.Column(db.String(50))
    eq_serie = db.Column(db.String(50))
    eq_tipo = db.Column(db.String(20), default='ti')
    data_entrega = db.Column(db.Date)
    estado_geral = db.Column(db.String(200))
    observacoes = db.Column(db.Text)
    local_assinatura = db.Column(db.String(120))
    acessorios_json = db.Column(db.Text)
    assinatura_path = db.Column(db.String(255))
    assinado_em = db.Column(db.DateTime)
    enviado_em = db.Column(db.DateTime)
    enviado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    canal_envio = db.Column(db.String(40))
    gestor_nome = db.Column(db.String(120))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    equipamento = db.relationship('Equipamento', back_populates='termos')
    responsavel_usuario = db.relationship('Usuario', foreign_keys=[responsavel_usuario_id])
    enviado_por = db.relationship('Usuario', foreign_keys=[enviado_por_id])

    def acessorios(self):
        import json
        try:
            data = json.loads(self.acessorios_json or '[]')
        except (TypeError, ValueError):
            data = []
        return normalizar_acessorios(data)

    def tipo_norm(self):
        if self.eq_tipo:
            return normalizar_tipo_eq(self.eq_tipo)
        eq = self.equipamento
        if eq is not None:
            return eq.tipo_equipamento_norm()
        return 'ti'

    def textos(self):
        return textos_termo_eq(self.tipo_norm())


def normalizar_acessorios(raw):
    """Converte lista nova ou dict legado em lista [{nome, qtd, obs}]."""
    out = []
    vistos = set()

    def _add(nome, qtd, obs):
        nome = str(nome or '').strip()[:80]
        if not nome:
            return
        chave = nome.casefold()
        if chave in vistos:
            return
        vistos.add(chave)
        out.append({
            'nome': nome,
            'qtd': str(qtd or '')[:20],
            'obs': str(obs or '')[:120],
        })

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                if item.get('selecionado') in (False, 0, '0', 'false', 'False'):
                    continue
                _add(item.get('nome') or item.get('item'), item.get('qtd'), item.get('obs'))
            elif isinstance(item, str):
                _add(item, '01', '')
        return out
    if isinstance(raw, dict):
        labels = {
            'equipamento': 'Equipamento',
            'fonte': 'Fonte/Carregador',
            'cabo': 'Cabo de alimentação',
            'teclado': 'Teclado',
            'mouse': 'Mouse',
            'outros': 'Outros',
        }
        for chave, label in labels.items():
            item = raw.get(chave) or {}
            if not isinstance(item, dict):
                item = {}
            qtd = str(item.get('qtd') or '').strip()
            obs = str(item.get('obs') or '').strip()
            if not qtd and not obs:
                continue
            _add(label, qtd, obs)
    return out


class ChamadoAtendimento(db.Model):
    __tablename__ = 'chamado_atendimentos'

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    o_que_foi_consertado = db.Column(db.Text)
    status = db.Column(db.String(40))
    setor_destino = db.Column(db.String(40))
    instrucoes = db.Column(db.Text)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    pendencia_aberta = db.Column(db.Boolean, default=True)
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])


TIPO_FOTO_CONSERTO = 'conserto'
TIPO_FOTO_ENCAMINHAMENTO = 'encaminhamento'
TIPOS_RECURSO = (
    'Access Point',
    'Celulares e Comunicação',
    'Estação',
    'Hardware',
    'Mobília',
    'Periférico',
    'Servidor Local',
    'Software',
)
GRUPO_RECURSO_PADRAO = 'Geral'


class ChamadoEncaminhamento(db.Model):
    """Histórico de hops: Informática → Elétrica → Compras ou devolver à origem."""
    __tablename__ = 'chamado_encaminhamentos'

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    atendimento_id = db.Column(db.Integer, db.ForeignKey('chamado_atendimentos.id'))
    de_setor = db.Column(db.String(40))
    para_setor = db.Column(db.String(40), nullable=False)
    notas = db.Column(db.Text)
    instrucoes = db.Column(db.Text)
    tipo = db.Column(db.String(20), default=TIPO_HOP_ENCAMINHAR)
    status = db.Column(db.String(40))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])
    atendimento = db.relationship('ChamadoAtendimento', foreign_keys=[atendimento_id])


class ChamadoFoto(db.Model):
    __tablename__ = 'chamado_fotos'

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False, index=True)
    atendimento_id = db.Column(db.Integer, db.ForeignKey('chamado_atendimentos.id'))
    caminho = db.Column(db.String(255), nullable=False)
    nome_original = db.Column(db.String(200))
    # conserto = o que foi consertado; encaminhamento = o que precisa fazer
    tipo = db.Column(db.String(20), default=TIPO_FOTO_CONSERTO)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    atendimento = db.relationship('ChamadoAtendimento', backref='fotos')


class ChamadoConhecimento(db.Model):
    """Base de conhecimentos (artigos) do módulo de chamados."""
    __tablename__ = 'chamado_conhecimentos'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    pasta = db.Column(db.String(80), default='Conhecimentos')
    tags = db.Column(db.String(255))
    catalogo = db.Column(db.String(80), default='Todos')
    corpo = db.Column(db.Text)
    arquivo = db.Column(db.String(255))
    arquivo_nome = db.Column(db.String(200))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])


class MesaServico(db.Model):
    """Mesa de serviço (ex.: Informática) — personalização da operação."""
    __tablename__ = 'mesas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)
    ativa = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)


class ChamadoTecnicoMesa(db.Model):
    """Vínculo N:N entre técnico/gestor e mesas de serviço."""
    __tablename__ = 'chamado_tecnico_mesas'

    tecnico_id = db.Column(db.Integer, db.ForeignKey('chamado_tecnicos.id'), primary_key=True)
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesas.id'), primary_key=True)


class SlaPrioridade(db.Model):
    """Prazo de atendimento e solução (horas) por prioridade."""
    __tablename__ = 'sla_prioridades'

    id = db.Column(db.Integer, primary_key=True)
    prioridade = db.Column(db.String(10), nullable=False, unique=True)
    prazo_atendimento_horas = db.Column(db.Integer, nullable=False, default=8)
    prazo_solucao_horas = db.Column(db.Integer, nullable=False, default=24)


class Contrato(db.Model):
    __tablename__ = 'contratos'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False, index=True)
    tipo = db.Column(db.String(40), nullable=False, default='Suporte')
    inicio = db.Column(db.Date)
    vencimento = db.Column(db.Date)
    dados_faturamento = db.Column(db.Text)
    valor = db.Column(db.Numeric(12, 2))
    observacao = db.Column(db.Text)
    sla_atendimento_horas = db.Column(db.Integer)
    sla_solucao_horas = db.Column(db.Integer)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    cliente = db.relationship('Cliente', backref='contratos')


class ChamadoMensagem(db.Model):
    """Comunicação do ticket: interno vs cliente, por canal."""
    __tablename__ = 'chamado_mensagens'

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    texto = db.Column(db.Text, nullable=False)
    canal = db.Column(db.String(20), default='Chat')
    visivel_cliente = db.Column(db.Boolean, default=True, nullable=False)
    enviada = db.Column(db.Boolean, default=False, nullable=False)
    origem = db.Column(db.String(20), default='usuario')
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])


class ChamadoAutomacao(db.Model):
    """Regras simples: ao criar (prioridade) ou ao mudar status → nota / mesa."""
    __tablename__ = 'chamado_automacoes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    gatilho = db.Column(db.String(20), nullable=False, default='criar')
    prioridade_quando = db.Column(db.String(10))
    status_quando = db.Column(db.String(40))
    acao = db.Column(db.String(20), nullable=False, default='mensagem')
    mensagem_padrao = db.Column(db.Text)
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesas.id'))
    ativa = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    mesa = db.relationship('MesaServico', foreign_keys=[mesa_id])


class WhatsAppChamadoConfig(db.Model):
    """Liga/desliga o atendimento de mensagens no número logado."""
    __tablename__ = 'whatsapp_chamado_config'

    id = db.Column(db.Integer, primary_key=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WhatsAppChamadoUsuario(db.Model):
    """Cadastro do contato que falou com o WhatsApp de chamados."""
    __tablename__ = 'whatsapp_chamado_usuarios'

    id = db.Column(db.Integer, primary_key=True)
    telefone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    nome = db.Column(db.String(120))
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), index=True)
    setor_id = db.Column(db.Integer, db.ForeignKey('chamado_setores.id'), index=True)
    etapa = db.Column(db.String(30), default='novo', nullable=False)
    lista_json = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cliente = db.relationship('Cliente', foreign_keys=[cliente_id])
    setor = db.relationship('ChamadoSetor', foreign_keys=[setor_id])

    def completo(self):
        return bool((self.nome or '').strip() and self.cliente_id and self.setor_id)

    def to_dict(self):
        return {
            'id': self.id,
            'telefone': self.telefone,
            'nome': self.nome or '',
            'cliente_id': self.cliente_id,
            'cliente': self.cliente.nome if self.cliente else '',
            'setor_id': self.setor_id,
            'setor': self.setor.nome if self.setor else '',
            'etapa': self.etapa or '',
            'atualizado_em': self.atualizado_em.strftime('%d/%m/%Y %H:%M') if self.atualizado_em else '',
        }


class WhatsAppChamadoLog(db.Model):
    """Últimas mensagens do bot de chamados (entrada/saída)."""
    __tablename__ = 'whatsapp_chamado_logs'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('whatsapp_chamado_usuarios.id'), index=True)
    telefone = db.Column(db.String(20), index=True)
    direcao = db.Column(db.String(8), nullable=False)
    texto = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    usuario = db.relationship('WhatsAppChamadoUsuario', foreign_keys=[usuario_id])


class ChamadoRamal(db.Model):
    """Telefones e ramais vinculados a setores técnicos."""
    __tablename__ = 'chamado_ramais'

    id = db.Column(db.Integer, primary_key=True)
    setor_id = db.Column(db.Integer, db.ForeignKey('chamado_setores.id'), nullable=False, index=True)
    nome_pessoa = db.Column(db.String(100), nullable=False)
    numero_ramal = db.Column(db.String(20), nullable=False)
    nome_equipamento = db.Column(db.String(100))
    login = db.Column(db.String(100))
    senha = db.Column(db.String(100))
    endereco_configuracao = db.Column(db.String(255))
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    setor = db.relationship('ChamadoSetor', foreign_keys=[setor_id])

    def __repr__(self):
        return f'<ChamadoRamal {self.numero_ramal} {self.nome_pessoa}>'

    def to_dict(self):
        return {
            'id': self.id,
            'setor_id': self.setor_id,
            'setor_nome': self.setor.nome if self.setor else '',
            'nome_pessoa': self.nome_pessoa,
            'numero_ramal': self.numero_ramal,
            'nome_equipamento': self.nome_equipamento or '',
            'login': self.login or '',
            'senha': self.senha or '',
            'endereco_configuracao': self.endereco_configuracao or '',
            'ativo': self.ativo,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else '',
        }


class ChamadoCamera(db.Model):
    """Cadastro de câmeras (nome, DVR, setor e imagem)."""
    __tablename__ = 'chamado_cameras'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    dvr = db.Column(db.String(100), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('chamado_setores.id'), nullable=False, index=True)
    imagem_path = db.Column(db.String(255))
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    setor = db.relationship('ChamadoSetor', foreign_keys=[setor_id])

    def __repr__(self):
        return f'<ChamadoCamera {self.nome}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'dvr': self.dvr or '',
            'setor_id': self.setor_id,
            'setor_nome': self.setor.nome if self.setor else '',
            'imagem_path': self.imagem_path or '',
            'imagem_url': f'/static/{self.imagem_path}' if self.imagem_path else '',
            'ativo': self.ativo,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else '',
        }


class ChamadoPortao(db.Model):
    """Cadastro de portões (local, setor, foto e observações)."""
    __tablename__ = 'chamado_portoes'

    id = db.Column(db.Integer, primary_key=True)
    local = db.Column(db.String(150), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('chamado_setores.id'), nullable=False, index=True)
    foto_path = db.Column(db.String(255))
    observacoes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    setor = db.relationship('ChamadoSetor', foreign_keys=[setor_id])

    def __repr__(self):
        return f'<ChamadoPortao {self.local}>'

    def to_dict(self):
        return {
            'id': self.id,
            'local': self.local,
            'setor_id': self.setor_id,
            'setor_nome': self.setor.nome if self.setor else '',
            'foto_path': self.foto_path or '',
            'foto_url': f'/static/{self.foto_path}' if self.foto_path else '',
            'observacoes': self.observacoes or '',
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else '',
        }


class ChamadoEstoque(db.Model):
    """Itens de estoque (produtos) do sistema de chamados."""
    __tablename__ = 'chamado_estoque'

    id = db.Column(db.Integer, primary_key=True)
    produto = db.Column(db.String(150), nullable=False)
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    quantidade = db.Column(db.Integer, default=0, nullable=False)
    data_aquisicao = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ChamadoEstoque {self.produto}>'

    def to_dict(self):
        return {
            'id': self.id,
            'produto': self.produto,
            'marca': self.marca or '',
            'modelo': self.modelo or '',
            'quantidade': int(self.quantidade or 0),
            'data_aquisicao': self.data_aquisicao.strftime('%Y-%m-%d') if self.data_aquisicao else '',
            'data_aquisicao_fmt': self.data_aquisicao.strftime('%d/%m/%Y') if self.data_aquisicao else '',
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else '',
        }


class ChamadoEstoqueUso(db.Model):
    """Produtos de estoque debitados ao finalizar um atendimento."""
    __tablename__ = 'chamado_estoque_usos'

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False, index=True)
    atendimento_id = db.Column(db.Integer, db.ForeignKey('chamado_atendimentos.id'), index=True)
    estoque_id = db.Column(db.Integer, db.ForeignKey('chamado_estoque.id'), nullable=False, index=True)
    quantidade = db.Column(db.Integer, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    created_at = db.Column(db.DateTime, default=now_brasilia)

    chamado = db.relationship('Chamado', foreign_keys=[chamado_id])
    atendimento = db.relationship('ChamadoAtendimento', foreign_keys=[atendimento_id])
    estoque = db.relationship('ChamadoEstoque', foreign_keys=[estoque_id])
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])

    def __repr__(self):
        return f'<ChamadoEstoqueUso chamado={self.chamado_id} estoque={self.estoque_id} qtd={self.quantidade}>'

    def to_saida_dict(self):
        est = self.estoque
        ch = self.chamado
        atendente = self.usuario
        abridor = ch.tecnico if ch else None
        setor_nome = ''
        if ch:
            if ch.setor_tecnico and ch.setor_tecnico.nome:
                setor_nome = ch.setor_tecnico.nome
            else:
                setor_nome = ch.setor_destino or ch.setor_origem or ''
        # created_at é gravado em horário de Brasília (naive) ao finalizar
        dt = self.created_at
        return {
            'id': self.id,
            'produto': est.produto if est else '',
            'marca': (est.marca or '') if est else '',
            'modelo': (est.modelo or '') if est else '',
            'quantidade': int(self.quantidade or 0),
            'data_saida': dt.strftime('%Y-%m-%d') if dt else '',
            'data_saida_fmt': dt.strftime('%d/%m/%Y %H:%M') if dt else '',
            'numero_chamado': ch.numero_chamado if ch else '',
            'chamado_id': self.chamado_id,
            'usuario_atendimento': atendente.nome if atendente else '',
            'usuario_abertura': abridor.nome if abridor else '',
            'setor': setor_nome,
        }


class ConhecimentoPasta(db.Model):
    __tablename__ = 'conhecimento_pastas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)


def normalizar_prioridade(valor):
    raw = (valor or '').strip()
    key = _fold_setor(raw)
    mapa = {
        'alta': 'Alta',
        'normal': 'Normal',
        'media': 'Média',
        'baixa': 'Baixa',
    }
    return mapa.get(key, 'Normal')


def sla_horas_prioridade(prioridade):
    pri = normalizar_prioridade(prioridade)
    try:
        row = SlaPrioridade.query.filter(
            db.func.lower(SlaPrioridade.prioridade) == pri.lower()
        ).first()
        if not row and pri == 'Média':
            row = SlaPrioridade.query.filter_by(prioridade='Normal').first()
        if row:
            return int(row.prazo_atendimento_horas or 8), int(row.prazo_solucao_horas or 24)
    except Exception:
        pass
    return SLA_PADRAO_HORAS.get(pri, SLA_PADRAO_HORAS['Normal'])


def sla_horas_tipo_contrato(tipo):
    return SLA_CONTRATO_TIPO.get((tipo or '').strip(), SLA_CONTRATO_TIPO['Suporte'])


def contrato_vigente(cliente_id, ref_date=None):
    if not cliente_id:
        return None
    ref = ref_date or now_brasilia().date()
    try:
        q = Contrato.query.filter_by(cliente_id=cliente_id).order_by(Contrato.id.desc())
        vigentes = []
        for c in q.all():
            ini = c.inicio or date.min
            fim = c.vencimento or date.max
            if ini <= ref <= fim:
                vigentes.append(c)
        if vigentes:
            return vigentes[0]
        return q.first()
    except Exception:
        return None


def sla_horas_contrato(contrato):
    if not contrato:
        return None
    at_h = contrato.sla_atendimento_horas
    sol_h = contrato.sla_solucao_horas
    if at_h and sol_h:
        return int(at_h), int(sol_h)
    padrao = sla_horas_tipo_contrato(contrato.tipo)
    return int(at_h or padrao[0]), int(sol_h or padrao[1])


def sla_do_chamado(chamado):
    criado = getattr(chamado, 'data_criacao', None)
    if not criado:
        return None
    fonte = 'prioridade'
    contrato = getattr(chamado, 'contrato', None)
    if contrato is None and getattr(chamado, 'contrato_id', None):
        try:
            contrato = Contrato.query.get(chamado.contrato_id)
        except Exception:
            contrato = None
    if contrato is None:
        contrato = contrato_vigente(
            getattr(chamado, 'cliente_id', None),
            criado.date() if hasattr(criado, 'date') else None,
        )
    horas_contrato = sla_horas_contrato(contrato)
    if horas_contrato:
        at_h, sol_h = horas_contrato
        fonte = 'contrato'
    else:
        at_h, sol_h = sla_horas_prioridade(getattr(chamado, 'prioridade', None))
    venc_at = criado + timedelta(hours=at_h)
    venc_sol = criado + timedelta(hours=sol_h)
    agora = datetime.utcnow()
    fechado = status_fechado(getattr(chamado, 'status', None))
    rest_at = (venc_at - agora).total_seconds() / 3600.0
    rest_sol = (venc_sol - agora).total_seconds() / 3600.0
    return {
        'prioridade': normalizar_prioridade(chamado.prioridade),
        'horas_atendimento': at_h,
        'horas_solucao': sol_h,
        'venc_atendimento': venc_at,
        'venc_solucao': venc_sol,
        'atendimento_vencido': (not fechado) and venc_at < agora,
        'solucao_vencida': (not fechado) and venc_sol < agora,
        'atendimento_proximo': (not fechado) and 0 <= rest_at <= SLA_ALERTA_HORAS,
        'solucao_proxima': (not fechado) and 0 <= rest_sol <= SLA_ALERTA_HORAS,
        'fechado': fechado,
        'fonte': fonte,
        'contrato': contrato,
        'contrato_tipo': contrato.tipo if contrato else None,
    }


def _bucket_sla(dt, hoje, agora, fechado):
    if not dt or fechado:
        return None
    if dt < agora:
        return 'vencido'
    d = dt.date() if hasattr(dt, 'date') else dt
    if d == hoje:
        return 'hoje'
    if d == hoje + timedelta(days=1):
        return 'amanha'
    if d > hoje:
        return 'depois'
    return None


def mesas_ativas():
    try:
        return MesaServico.query.filter_by(ativa=True).order_by(MesaServico.nome.asc()).all()
    except Exception:
        return []


def mesa_por_nome(nome):
    """Mesa cujo nome coincide ignorando acento e caixa (Informatica = Informática)."""
    key = _fold_setor(nome)
    if not key:
        return None
    try:
        for row in MesaServico.query.order_by(MesaServico.id.asc()).all():
            if _fold_setor(row.nome) == key:
                return row
    except Exception:
        return None
    return None


def mesa_padrao():
    try:
        row = mesa_por_nome(MESA_PADRAO)
        if row:
            return row
        row = MesaServico.query.filter_by(ativa=True).order_by(MesaServico.id.asc()).first()
        return row
    except Exception:
        return None


def migrar_mesa_suporte_para_informatica():
    """Apaga a mesa Suporte e passa chamados, técnicos e automações para Informática."""
    try:
        from sqlalchemy import inspect
        tabelas = set(inspect(db.engine).get_table_names())
    except Exception:
        return
    if 'mesas' not in tabelas or 'chamados' not in tabelas:
        return
    destino = mesa_por_nome(MESA_PADRAO)
    if not destino:
        destino = MesaServico(nome=MESA_PADRAO, ativa=True)
        db.session.add(destino)
        db.session.flush()
    origem = mesa_por_nome('Suporte')
    if origem and origem.id != destino.id:
        Chamado.query.filter(Chamado.mesa_id == origem.id).update(
            {Chamado.mesa_id: destino.id}, synchronize_session=False
        )
        if 'chamado_automacoes' in tabelas:
            ChamadoAutomacao.query.filter(ChamadoAutomacao.mesa_id == origem.id).update(
                {ChamadoAutomacao.mesa_id: destino.id}, synchronize_session=False
            )
        if 'chamado_tecnico_mesas' in tabelas:
            for link in ChamadoTecnicoMesa.query.filter_by(mesa_id=origem.id).all():
                ja = ChamadoTecnicoMesa.query.filter_by(
                    tecnico_id=link.tecnico_id, mesa_id=destino.id
                ).first()
                if ja:
                    db.session.delete(link)
                else:
                    link.mesa_id = destino.id
            db.session.flush()
        db.session.delete(origem)
    Chamado.query.filter(Chamado.mesa_id.is_(None)).update(
        {Chamado.mesa_id: destino.id}, synchronize_session=False
    )
    db.session.commit()


def preencher_inicio_atendimento_legado():
    """Copia o primeiro atendimento já gravado para chamados sem data de início."""
    try:
        from sqlalchemy import inspect, text
        tabelas = set(inspect(db.engine).get_table_names())
        if 'chamados' not in tabelas:
            return
        cols = {c['name'] for c in inspect(db.engine).get_columns('chamados')}
        if 'data_inicio_atendimento' not in cols:
            return
        if 'atendendo_em' in cols:
            Chamado.query.filter(
                Chamado.data_inicio_atendimento.is_(None),
                Chamado.atendendo_em.isnot(None),
            ).update(
                {Chamado.data_inicio_atendimento: Chamado.atendendo_em},
                synchronize_session=False,
            )
        if 'chamado_atendimentos' in tabelas:
            db.session.execute(text(
                'UPDATE chamados SET data_inicio_atendimento = ('
                ' SELECT MIN(data_criacao) FROM chamado_atendimentos'
                ' WHERE chamado_atendimentos.chamado_id = chamados.id'
                ') WHERE data_inicio_atendimento IS NULL'
                ' AND EXISTS ('
                ' SELECT 1 FROM chamado_atendimentos'
                ' WHERE chamado_atendimentos.chamado_id = chamados.id)'
            ))
            fechados = Chamado.query.filter(
                Chamado.atendente_id.is_(None),
                Chamado.status.in_(STATUS_FECHADOS),
            ).all()
            for chamado in fechados:
                ultimo = (
                    ChamadoAtendimento.query
                    .filter_by(chamado_id=chamado.id)
                    .order_by(ChamadoAtendimento.id.desc())
                    .first()
                )
                if ultimo and ultimo.usuario_id:
                    chamado.atendente_id = ultimo.usuario_id
        db.session.commit()
    except Exception:
        db.session.rollback()


def resolver_mesa_id(raw):
    if raw is not None and str(raw).strip().isdigit():
        mesa = MesaServico.query.get(int(raw))
        if mesa and mesa.ativa:
            return mesa.id
    padrao = mesa_padrao()
    return padrao.id if padrao else None


def parse_valor_faturamento(raw):
    txt = (raw or '').strip().replace('R$', '').replace(' ', '')
    if not txt:
        return None
    if ',' in txt and '.' in txt:
        txt = txt.replace('.', '').replace(',', '.')
    elif ',' in txt:
        txt = txt.replace(',', '.')
    try:
        return Decimal(txt)
    except (InvalidOperation, ValueError):
        return None


def aplicar_automacoes(chamado, evento, usuario, status_anterior=None):
    """evento: 'criar' | 'status'. Anexa nota na timeline e/ou muda a mesa."""
    try:
        regras = ChamadoAutomacao.query.filter_by(ativa=True).all()
    except Exception:
        return
    pri = normalizar_prioridade(getattr(chamado, 'prioridade', None))
    for regra in regras:
        ok = False
        if evento == 'criar' and (regra.gatilho or '') == 'criar':
            if not regra.prioridade_quando or normalizar_prioridade(regra.prioridade_quando) == pri:
                ok = True
        elif evento == 'status' and (regra.gatilho or '') == 'status':
            alvo = (regra.status_quando or '').strip()
            if alvo and (chamado.status or '').strip() == alvo and (status_anterior or '') != alvo:
                ok = True
        if not ok:
            continue
        if (regra.acao or '') == 'mesa' and regra.mesa_id:
            chamado.mesa_id = regra.mesa_id
        texto = (regra.mensagem_padrao or '').strip() or f'Automação: {regra.nome}'
        uid = usuario.id if usuario else chamado.tecnico_id
        db.session.add(ChamadoMensagem(
            chamado_id=chamado.id,
            usuario_id=uid,
            texto=texto,
            canal='Interno',
            visivel_cliente=False,
            enviada=False,
            origem='automacao',
        ))
