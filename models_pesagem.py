"""Modelos do Sistema de Controle de Pesagem."""
from datetime import datetime
from models import db


class PesagemBalanca(db.Model):
    __tablename__ = 'pesagem_balancas'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), nullable=False, unique=True)
    nome = db.Column(db.String(120), nullable=False)
    local = db.Column(db.String(120))
    porta_com = db.Column(db.String(20))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'codigo': self.codigo,
            'nome': self.nome,
            'local': self.local or '',
            'porta_com': self.porta_com or '',
            'ativo': self.ativo,
        }


class PesagemLeitura(db.Model):
    __tablename__ = 'pesagem_leituras'

    id = db.Column(db.Integer, primary_key=True)
    balanca_id = db.Column(db.Integer, db.ForeignKey('pesagem_balancas.id'), nullable=True)
    balanca = db.relationship('PesagemBalanca', backref='leituras')

    balanca_codigo = db.Column(db.String(40), nullable=False, index=True)
    peso = db.Column(db.Float, nullable=False)
    unidade = db.Column(db.String(10), default='kg')
    bruto_serial = db.Column(db.String(255))
    estavel = db.Column(db.Boolean, default=True)
    origem = db.Column(db.String(40), default='agente')  # agente | manual | teste
    computador = db.Column(db.String(120))
    porta_com = db.Column(db.String(20))
    observacao = db.Column(db.String(255))
    data_leitura = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'balanca_id': self.balanca_id,
            'balanca_codigo': self.balanca_codigo,
            'peso': self.peso,
            'unidade': self.unidade or 'kg',
            'bruto_serial': self.bruto_serial or '',
            'estavel': bool(self.estavel),
            'origem': self.origem or 'agente',
            'computador': self.computador or '',
            'porta_com': self.porta_com or '',
            'observacao': self.observacao or '',
            'data_leitura': self.data_leitura.isoformat(sep=' ', timespec='seconds') if self.data_leitura else '',
        }
