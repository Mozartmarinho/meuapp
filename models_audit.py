from datetime import datetime
from models import db


class AuditLog(db.Model):
    """Registro de auditoria de ações no sistema."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow, index=True, nullable=False)

    usuario_id = db.Column(db.Integer, nullable=True, index=True)
    usuario_nome = db.Column(db.String(120))

    modulo = db.Column(db.String(40), index=True)  # chamados | nutricao | pesagem | auditoria | sistema
    acao = db.Column(db.String(40), index=True)  # criar | editar | excluir | login | logout | etc.
    entidade = db.Column(db.String(80))
    entidade_id = db.Column(db.String(40))

    metodo = db.Column(db.String(10))
    caminho = db.Column(db.String(255), index=True)
    status_http = db.Column(db.Integer)

    ip = db.Column(db.String(60))
    user_agent = db.Column(db.String(255))
    detalhe = db.Column(db.Text)
    sucesso = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'data_hora': self.data_hora.strftime('%d/%m/%Y %H:%M:%S') if self.data_hora else '',
            'data_hora_iso': self.data_hora.isoformat(sep=' ', timespec='seconds') if self.data_hora else '',
            'usuario_id': self.usuario_id,
            'usuario_nome': self.usuario_nome or 'sistema',
            'modulo': self.modulo or '',
            'acao': self.acao or '',
            'entidade': self.entidade or '',
            'entidade_id': self.entidade_id or '',
            'metodo': self.metodo or '',
            'caminho': self.caminho or '',
            'status_http': self.status_http,
            'ip': self.ip or '',
            'user_agent': self.user_agent or '',
            'detalhe': self.detalhe or '',
            'sucesso': bool(self.sucesso),
        }
