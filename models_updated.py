from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Numeric
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Tabela de associação para permissões de usuário
user_permissions = db.Table('user_permissions',
    db.Column('user_id', db.Integer, db.ForeignKey('usuarios.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True)
)

class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    endereco = db.Column(db.String(200))
    telefone_responsavel = db.Column(db.String(20))
    whatsapp_responsavel = db.Column(db.String(20))
    email_responsavel = db.Column(db.String(120))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    ativo = db.Column(db.Boolean, default=True)
    
    # Relacionamentos
    equipamentos = db.relationship('Equipamento', backref='cliente', lazy=True)
    chamados = db.relationship('Chamado', backref='cliente', lazy=True)

    def __repr__(self):
        return f'<Cliente {self.nome}>'

class Equipamento(db.Model):
    __tablename__ = 'equipamentos'

    id = db.Column(db.Integer, primary_key=True)
    equipamento = db.Column(db.String(100), nullable=False)
    modelo = db.Column(db.String(100))
    data_compra = db.Column(db.Date)
    patrimonio = db.Column(db.String(50), unique=True)
    observacoes = db.Column(db.Text)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    ativo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Equipamento {self.equipamento}>'

class Usuario(db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(20), default='tecnico')
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    permissions = db.relationship('Permission', secondary=user_permissions, lazy='subquery',
        backref=db.backref('usuarios', lazy=True))
    chamados = db.relationship('Chamado', backref='tecnico', lazy=True)

    def set_password(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_password(self, senha):
        return check_password_hash(self.senha_hash, senha)

    def has_permission(self, permission_name):
        return any(p.name == permission_name for p in self.permissions)

    def __repr__(self):
        return f'<Usuario {self.email}>'

class Permission(db.Model):
    __tablename__ = 'permissions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))

    def __repr__(self):
        return f'<Permission {self.name}>'

class Chamado(db.Model):
    __tablename__ = 'chamados'

    id = db.Column(db.Integer, primary_key=True)
    numero_chamado = db.Column(db.String(20), unique=True, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    tipo_servico = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pendente')
    prioridade = db.Column(db.String(10), default='Baixa')
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_atendimento = db.Column(db.DateTime)
    data_conclusao = db.Column(db.DateTime)
    observacoes = db.Column(db.Text)
    feito = db.Column(db.Text)  # Campo para o que foi realizado
    patrimonio = db.Column(db.String(50))
    equipamento = db.Column(db.String(100))
    tecnico_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    
    # Relacionamentos via backref

    def __repr__(self):
        return f'<Chamado {self.numero_chamado}>'

    def to_dict(self):
        return {
            'id': self.id,
            'numero_chamado': self.numero_chamado,
            'cliente': self.cliente.nome if self.cliente else '',
            'tipo_servico': self.tipo_servico,
            'descricao': self.descricao,
            'status': self.status,
            'prioridade': self.prioridade,
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else None,
            'data_atendimento': self.data_atendimento.strftime('%d/%m/%Y %H:%M') if self.data_atendimento else None,
            'data_conclusao': self.data_conclusao.strftime('%d/%m/%Y %H:%M') if self.data_conclusao else None,
            'observacoes': self.observacoes,
            'feito': self.feito,
            'tecnico': self.tecnico.nome if self.tecnico else '',
            'fotos': [{'filename': f.filename} for f in self.fotos]
        }

class ChamadoFoto(db.Model):
    __tablename__ = 'chamado_fotos'

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

    chamado = db.relationship('Chamado', backref=db.backref('fotos', lazy=True))

    def __repr__(self):
        return f'<ChamadoFoto {self.filename}>'
