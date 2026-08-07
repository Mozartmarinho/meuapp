"""Modelos do módulo de Nutrição Hospitalar."""
from datetime import datetime, date
from models import db


class NutClinica(db.Model):
    __tablename__ = 'nut_clinicas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    centro_custo = db.Column(db.String(50))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'centro_custo': self.centro_custo or '',
            'ativo': self.ativo,
        }


class NutDieta(db.Model):
    __tablename__ = 'nut_dietas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False, unique=True)
    # basica | enteral | formula | lve | suplemento | outro
    categoria = db.Column(db.String(40), default='basica')
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'categoria': self.categoria or 'basica',
            'ativo': self.ativo,
        }


class NutPaciente(db.Model):
    __tablename__ = 'nut_pacientes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    sexo = db.Column(db.String(1))
    nascimento = db.Column(db.Date)
    prontuario = db.Column(db.String(40))
    clinica = db.Column(db.String(120))
    leito = db.Column(db.String(40))
    dieta = db.Column(db.String(200))
    diagnostico = db.Column(db.Text)
    observacoes = db.Column(db.Text)
    admissao = db.Column(db.Date)
    data_saida = db.Column(db.Date)
    altura_cm = db.Column(db.Float)
    peso_kg = db.Column(db.Float)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def idade(self, ref=None):
        if not self.nascimento:
            return None
        ref = ref or date.today()
        years = ref.year - self.nascimento.year
        if (ref.month, ref.day) < (self.nascimento.month, self.nascimento.day):
            years -= 1
        return years

    def imc(self):
        if not self.altura_cm or not self.peso_kg or self.altura_cm <= 0:
            return None
        h = self.altura_cm / 100.0
        return round(self.peso_kg / (h * h), 2)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'sexo': self.sexo or '',
            'nascimento': self.nascimento.isoformat() if self.nascimento else '',
            'prontuario': self.prontuario or '',
            'clinica': self.clinica or '',
            'leito': self.leito or '',
            'dieta': self.dieta or '',
            'diagnostico': self.diagnostico or '',
            'observacoes': self.observacoes or '',
            'admissao': self.admissao.isoformat() if self.admissao else '',
            'data_saida': self.data_saida.isoformat() if self.data_saida else '',
            'altura_cm': self.altura_cm,
            'peso_kg': self.peso_kg,
            'idade': self.idade(),
            'imc': self.imc(),
            'ativo': self.ativo,
        }


class NutMapaRefeicao(db.Model):
    """Linha do mapa de refeições do dia (produção/clínica)."""
    __tablename__ = 'nut_mapa_refeicoes'

    id = db.Column(db.Integer, primary_key=True)
    data_refeicao = db.Column(db.Date, nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('nut_pacientes.id'), nullable=True)
    paciente = db.relationship('NutPaciente', backref='mapas')

    # Snapshot operacional do dia (permite editar sem perder histórico)
    adm = db.Column(db.Date)
    leito = db.Column(db.String(40))
    prontuario = db.Column(db.String(40))
    nome = db.Column(db.String(150), nullable=False)
    idade = db.Column(db.Integer)
    diagnostico = db.Column(db.Text)
    dieta = db.Column(db.String(200))
    observacoes = db.Column(db.Text)
    clinica = db.Column(db.String(120))

    # Flags de refeição: D C A M J C (ceia)
    fl_desjejum = db.Column(db.Boolean, default=False)
    fl_colacao = db.Column(db.Boolean, default=False)
    fl_almoco = db.Column(db.Boolean, default=False)
    fl_merenda = db.Column(db.Boolean, default=False)
    fl_jantar = db.Column(db.Boolean, default=False)
    fl_ceia = db.Column(db.Boolean, default=False)

    data_saida = db.Column(db.Date)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'data_refeicao': self.data_refeicao.isoformat() if self.data_refeicao else '',
            'paciente_id': self.paciente_id,
            'adm': self.adm.isoformat() if self.adm else '',
            'leito': self.leito or '',
            'prontuario': self.prontuario or '',
            'nome': self.nome or '',
            'idade': self.idade,
            'diagnostico': self.diagnostico or '',
            'dieta': self.dieta or '',
            'observacoes': self.observacoes or '',
            'clinica': self.clinica or '',
            'fl_desjejum': bool(self.fl_desjejum),
            'fl_colacao': bool(self.fl_colacao),
            'fl_almoco': bool(self.fl_almoco),
            'fl_merenda': bool(self.fl_merenda),
            'fl_jantar': bool(self.fl_jantar),
            'fl_ceia': bool(self.fl_ceia),
            'data_saida': self.data_saida.isoformat() if self.data_saida else '',
            'ativo': self.ativo,
        }
