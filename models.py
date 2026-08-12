from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


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
    status = db.Column(db.String(20), default='Pendente')
    prioridade = db.Column(db.String(10), default='Normal')
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_conclusao = db.Column(db.DateTime)
    observacoes = db.Column(db.Text)
    equipamento = db.Column(db.String(100), nullable=True)
    # Obrigatório no MySQL deste servidor
    tecnico_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)

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
            'equipamento': self.equipamento
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
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Usuario {self.email}>'


class Equipamento(db.Model):
    __tablename__ = 'equipamentos'

    id = db.Column(db.Integer, primary_key=True)
    # Banco legado usa coluna "equipamento"
    nome_equipamento = db.Column('equipamento', db.String(100), nullable=False)
    modelo = db.Column(db.String(100))
    numero_serie = db.Column(db.String(50), unique=True)
    patrimonio = db.Column(db.String(50), unique=True)
    localizacao = db.Column(db.String(100))
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
            'nome_equipamento': self.nome_equipamento,
            'modelo': self.modelo,
            'numero_serie': self.numero_serie,
            'patrimonio': self.patrimonio,
            'localizacao': self.localizacao,
            'ativo': self.ativo,
            'data_compra': self.data_compra.strftime('%d/%m/%Y') if self.data_compra else None,
            'data_manutencao': self.data_manutencao.strftime('%d/%m/%Y') if self.data_manutencao else None
        }
