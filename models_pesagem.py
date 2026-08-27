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


class PesagemCliente(db.Model):
    __tablename__ = 'pesagem_clientes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    imagem_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, imagem_url=''):
        return {
            'id': self.id,
            'nome': self.nome,
            'imagem_path': self.imagem_path or '',
            'imagem_url': imagem_url or '',
            'created_at': self.created_at.isoformat(sep=' ', timespec='seconds') if self.created_at else '',
        }


class PesagemLeitura(db.Model):
    __tablename__ = 'pesagem_leituras'

    id = db.Column(db.Integer, primary_key=True)
    balanca_id = db.Column(db.Integer, db.ForeignKey('pesagem_balancas.id'), nullable=True)
    balanca = db.relationship('PesagemBalanca', backref='leituras')

    balanca_codigo = db.Column(db.String(40), nullable=False, index=True)
    peso = db.Column(db.Float, nullable=False)
    unidade = db.Column(db.String(10), default='kg')
    tara = db.Column(db.Float)
    peso_bruto = db.Column(db.Float)
    peso_liquido = db.Column(db.Float)
    bruto_serial = db.Column(db.String(255))
    estavel = db.Column(db.Boolean, default=True)
    origem = db.Column(db.String(40), default='agente')  # agente | manual | teste
    computador = db.Column(db.String(120))
    porta_com = db.Column(db.String(20))
    observacao = db.Column(db.String(255))
    cliente_id = db.Column(db.Integer, db.ForeignKey('pesagem_clientes.id'), nullable=True)
    cliente = db.relationship('PesagemCliente', backref='leituras')
    cliente_nome = db.Column(db.String(120))
    data_leitura = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'balanca_id': self.balanca_id,
            'balanca_codigo': self.balanca_codigo,
            'peso': self.peso,
            'unidade': self.unidade or 'kg',
            'tara': self.tara if self.tara is not None else 0.0,
            'peso_bruto': self.peso_bruto if self.peso_bruto is not None else self.peso,
            'peso_liquido': self.peso_liquido if self.peso_liquido is not None else self.peso,
            'bruto_serial': self.bruto_serial or '',
            'estavel': bool(self.estavel),
            'origem': self.origem or 'agente',
            'computador': self.computador or '',
            'porta_com': self.porta_com or '',
            'observacao': self.observacao or '',
            'cliente_id': self.cliente_id,
            'cliente_nome': self.cliente_nome or '',
            'data_leitura': self.data_leitura.isoformat(sep=' ', timespec='seconds') if self.data_leitura else '',
        }


class PesagemWhatsAppDestino(db.Model):
    """Destinatário do relatório diário de pesagem via WhatsApp."""
    __tablename__ = 'pesagem_whatsapp_destinos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    hora = db.Column(db.Time, nullable=False)
    mensagem = db.Column(db.Text, nullable=False, default='')
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        hora = ''
        if self.hora:
            hora = self.hora.strftime('%H:%M')
        return {
            'id': self.id,
            'nome': self.nome,
            'telefone': self.telefone or '',
            'hora': hora,
            'mensagem': self.mensagem or '',
            'ativo': bool(self.ativo),
            'created_at': (
                self.created_at.isoformat(sep=' ', timespec='seconds')
                if self.created_at else ''
            ),
        }


class PesagemWhatsAppEnvio(db.Model):
    """Histórico de envios (agendado uma vez ao dia ou manual)."""
    __tablename__ = 'pesagem_whatsapp_envios'

    id = db.Column(db.Integer, primary_key=True)
    destino_id = db.Column(
        db.Integer, db.ForeignKey('pesagem_whatsapp_destinos.id'), nullable=False, index=True
    )
    destino = db.relationship('PesagemWhatsAppDestino', backref='envios')
    data_ref = db.Column(db.Date, nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False, default='agendado')  # agendado | manual
    enviado_em = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='ok')  # ok | erro
    erro = db.Column(db.String(255))
    corpo = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint(
            'destino_id', 'data_ref', 'tipo',
            name='uq_pesagem_wa_envio_destino_dia_tipo',
        ),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'destino_id': self.destino_id,
            'data_ref': self.data_ref.isoformat() if self.data_ref else '',
            'tipo': self.tipo,
            'enviado_em': (
                self.enviado_em.isoformat(sep=' ', timespec='seconds')
                if self.enviado_em else ''
            ),
            'status': self.status,
            'erro': self.erro or '',
        }
