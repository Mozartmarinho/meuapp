from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Numeric
from datetime import datetime

db = SQLAlchemy()

class Chamado(db.Model):
    __tablename__ = 'chamados'

    id = db.Column(db.Integer, primary_key=True)
    numero_chamado = db.Column(db.String(20), unique=True, nullable=False)
    cliente = db.Column(db.String(100), nullable=False)
    tipo_servico = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pendente')
    prioridade = db.Column(db.String(10), default='Normal')
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_conclusao = db.Column(db.DateTime)
    valor = db.Column(Numeric(10, 2))
    observacoes = db.Column(db.Text)

    def __repr__(self):
        return f'<Chamado {self.numero_chamado}>'

    def to_dict(self):
        return {
            'id': self.id,
            'numero_chamado': self.numero_chamado,
            'cliente': self.cliente,
            'tipo_servico': self.tipo_servico,
            'descricao': self.descricao,
            'status': self.status,
            'prioridade': self.prioridade,
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else None,
            'data_conclusao': self.data_conclusao.strftime('%d/%m/%Y %H:%M') if self.data_conclusao else None,
            'valor': float(self.valor) if self.valor else 0,
            'observacoes': self.observacoes
        }

class Usuario(db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(20), default='operador')
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Usuario {self.email}>'
 
