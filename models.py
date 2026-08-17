from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

SETORES_CHAMADO = ('Obra', 'Elétrica', 'Compras')
STATUS_AGUARDAR_PECA = 'Aguardar peça'
STATUS_ENCAMINHADO = 'Encaminhado'
STATUS_ATENDIDO = 'Atendido'
STATUS_CONCLUIDO = 'Concluído'
STATUS_FECHADOS = (STATUS_ATENDIDO, STATUS_CONCLUIDO)


def status_fechado(status):
    """Atendido (técnico finalizou) e Concluído são estados encerrados."""
    return (status or '').strip() in STATUS_FECHADOS


def normalizar_setor_chamado(valor):
    """Normaliza o setor de encaminhamento (Obra, Elétrica, Compras)."""
    raw = (valor or '').strip()
    if not raw:
        return ''
    key = (
        raw.lower()
        .replace('é', 'e')
        .replace('á', 'a')
        .replace('í', 'i')
        .replace('ó', 'o')
        .replace('ú', 'u')
    )
    mapa = {
        'obra': 'Obra',
        'eletrica': 'Elétrica',
        'compras': 'Compras',
    }
    return mapa.get(key, '')


class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    endereco = db.Column(db.String(200))
    # Colunas do schema GitHub (criadas na migração Linux se faltarem)
    telefone = db.Column(db.String(20))
    responsavel = db.Column(db.String(100))
    telefone_responsavel = db.Column(db.String(20))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Cliente {self.nome}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'endereco': self.endereco,
            'telefone': self.telefone,
            'responsavel': self.responsavel,
            'telefone_responsavel': self.telefone_responsavel,
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
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_conclusao = db.Column(db.DateTime)
    observacoes = db.Column(db.Text)
    equipamento = db.Column(db.String(100), nullable=True)
    patrimonio = db.Column(db.String(50), nullable=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamentos.id'), nullable=True)
    equipamento_cadastro = db.relationship('Equipamento', foreign_keys=[equipamento_id])
    # Obrigatório no MySQL deste servidor
    tecnico_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    atendimento_notas = db.Column(db.Text)
    setor_destino = db.Column(db.String(40))
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
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else None,
            'data_conclusao': self.data_conclusao.strftime('%d/%m/%Y %H:%M') if self.data_conclusao else None,
            'observacoes': self.observacoes,
            'equipamento': self.equipamento,
            'patrimonio': self.patrimonio,
            'equipamento_id': self.equipamento_id,
            'atendimento_notas': self.atendimento_notas,
            'setor_destino': self.setor_destino,
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
    setor = db.Column(db.String(40))
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


class Equipamento(db.Model):
    __tablename__ = 'equipamentos'

    id = db.Column(db.Integer, primary_key=True)
    nome_equipamento = db.Column(db.String(100), nullable=False)
    modelo = db.Column(db.String(100))
    numero_serie = db.Column(db.String(50), unique=True)
    patrimonio = db.Column(db.String(50), unique=True)
    localizacao = db.Column(db.String(100))
    setor = db.Column(db.String(100))
    ativo = db.Column(db.Boolean, default=True)
    data_compra = db.Column(db.Date)
    data_manutencao = db.Column(db.Date)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    # Obrigatório no MySQL deste servidor
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    cliente = db.relationship('Cliente', backref='equipamentos')

    def __repr__(self):
        return f'<Equipamento {self.nome_equipamento}>'

    def to_dict(self):
        return {
            'id': self.id,
            'codigo': self.patrimonio,
            'nome_equipamento': self.nome_equipamento,
            'nome': self.nome_equipamento,
            'modelo': self.modelo,
            'numero_serie': self.numero_serie,
            'patrimonio': self.patrimonio,
            'localizacao': self.localizacao,
            'setor': self.setor or self.localizacao,
            'ativo': self.ativo,
            'cliente_id': self.cliente_id,
            'cliente_nome': self.cliente.nome if self.cliente else None,
            'data_compra': self.data_compra.strftime('%d/%m/%Y') if self.data_compra else None,
            'data_compra_iso': self.data_compra.strftime('%Y-%m-%d') if self.data_compra else None,
            'data_manutencao': self.data_manutencao.strftime('%d/%m/%Y') if self.data_manutencao else None
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
