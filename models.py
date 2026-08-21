from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

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
STATUS_DEVOLVIDO = 'Devolvido'
STATUS_ATENDIDO = 'Atendido'
STATUS_CONCLUIDO = 'Concluído'
STATUS_FECHADOS = (STATUS_ATENDIDO, STATUS_CONCLUIDO)
TIPO_HOP_ENCAMINHAR = 'encaminhar'
TIPO_HOP_DEVOLVER = 'devolver'
TIPO_HOP_PECA = 'peca'
MESA_PADRAO = 'Suporte'
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
    observacoes = db.Column(db.Text)
    equipamento = db.Column(db.String(100), nullable=True)
    patrimonio = db.Column(db.String(50), nullable=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamentos.id'), nullable=True)
    equipamento_cadastro = db.relationship('Equipamento', foreign_keys=[equipamento_id])
    # Obrigatório no MySQL deste servidor
    tecnico_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    tecnico = db.relationship('Usuario', foreign_keys=[tecnico_id], backref='chamados_tecnico')
    atendimento_notas = db.Column(db.Text)
    setor_destino = db.Column(db.String(80))
    setor_origem = db.Column(db.String(80))
    setor_tecnico_id = db.Column(db.Integer, db.ForeignKey('chamado_setores.id'), nullable=True)
    setor_tecnico = db.relationship('ChamadoSetor', foreign_keys='[Chamado.setor_tecnico_id]')
    encaminhamento_instrucoes = db.Column(db.Text)
    encaminhado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    encaminhado_em = db.Column(db.DateTime)
    encaminhado_por = db.relationship('Usuario', foreign_keys=[encaminhado_por_id])
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
            'data_conclusao': self.data_conclusao.strftime('%d/%m/%Y %H:%M') if self.data_conclusao else None,
            'observacoes': self.observacoes,
            'equipamento': self.equipamento,
            'patrimonio': self.patrimonio,
            'equipamento_id': self.equipamento_id,
            'atendimento_notas': self.atendimento_notas,
            'setor_destino': self.setor_destino,
            'setor_origem': self.setor_origem,
            'encaminhamento_instrucoes': self.encaminhamento_instrucoes,
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
    perm_acesso = db.Column(db.Boolean, default=False)
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
        """Acessos/Configurações na home: checkbox do sistema 'acesso' (perm_acesso) ou master."""
        return bool(self.is_master or self.perm_acesso)


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


class ChamadoTecnico(db.Model):
    """Técnicos vinculados a setores."""
    __tablename__ = 'chamado_tecnicos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    funcao = db.Column(db.String(20), nullable=True)
    setor_id = db.Column(db.Integer, db.ForeignKey('chamado_setores.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])

    @property
    def funcao_label(self):
        return FUNCOES_TECNICO_LABEL.get(self.funcao or '', self.funcao or '')

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


class Equipamento(db.Model):
    __tablename__ = 'equipamentos'

    id = db.Column(db.Integer, primary_key=True)
    # Coluna legada NOT NULL no MySQL; espelha o nome do equipamento
    equipamento = db.Column(db.String(100), nullable=False)
    nome_equipamento = db.Column(db.String(100), nullable=False)
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    numero_serie = db.Column(db.String(50), unique=True)
    patrimonio = db.Column(db.String(50), unique=True)
    localizacao = db.Column(db.String(100))
    setor = db.Column(db.String(100))
    local = db.Column(db.String(200))
    ativo = db.Column(db.Boolean, default=True)
    data_compra = db.Column(db.Date)
    data_manutencao = db.Column(db.Date)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    cliente = db.relationship('Cliente', backref='equipamentos')
    tipo_recurso = db.Column(db.String(40), default='Estação')
    grupo_id = db.Column(db.Integer, db.ForeignKey('recurso_grupos.id'), index=True)
    grupo = db.relationship('RecursoGrupo', foreign_keys=[grupo_id])
    usuario_equipamento = db.Column(db.String(120))
    ip = db.Column(db.String(45))
    is_agente = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<Equipamento {self.nome_equipamento}>'

    def to_dict(self):
        return {
            'id': self.id,
            'codigo': self.patrimonio,
            'nome_equipamento': self.nome_equipamento,
            'nome': self.nome_equipamento,
            'marca': self.marca or '',
            'modelo': self.modelo or '',
            'numero_serie': self.numero_serie,
            'patrimonio': self.patrimonio,
            'localizacao': self.localizacao,
            'setor': self.setor or self.localizacao,
            'local': self.local or '',
            'ativo': self.ativo,
            'cliente_id': self.cliente_id,
            'cliente_nome': self.cliente.nome if self.cliente else None,
            'data_compra': self.data_compra.strftime('%d/%m/%Y') if self.data_compra else None,
            'data_compra_iso': self.data_compra.strftime('%Y-%m-%d') if self.data_compra else None,
            'data_manutencao': self.data_manutencao.strftime('%d/%m/%Y') if self.data_manutencao else None,
            'tipo_recurso': self.tipo_recurso or 'Estação',
            'grupo_id': self.grupo_id,
            'grupo_nome': self.grupo.nome if self.grupo else None,
            'usuario_equipamento': self.usuario_equipamento or '',
            'ip': self.ip or '',
            'is_agente': bool(self.is_agente),
            'atualizado_em': self.atualizado_em.strftime('%d/%m/%Y %H:%M') if self.atualizado_em else None,
        }


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
    """Mesa de serviço (ex.: Suporte) — personalização da operação."""
    __tablename__ = 'mesas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)
    ativa = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)


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


def mesa_padrao():
    try:
        row = MesaServico.query.filter_by(nome=MESA_PADRAO).first()
        if row:
            return row
        row = MesaServico.query.filter_by(ativa=True).order_by(MesaServico.id.asc()).first()
        return row
    except Exception:
        return None


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
