"""Modelos do Sistema de Controle de Logística."""
import json
from datetime import datetime

from models import db


class LogisticaVeiculo(db.Model):
    __tablename__ = 'logistica_veiculos'

    id = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(12), nullable=False, unique=True, index=True)
    renavam = db.Column(db.String(20))
    modelo = db.Column(db.String(120), nullable=False)
    ano = db.Column(db.String(20))
    capacidade = db.Column(db.String(40))
    valor_veiculo = db.Column(db.Float)
    valor_carroceria = db.Column(db.Float)
    valor_plataforma = db.Column(db.Float)
    gaiolas = db.Column(db.Integer)
    unidade = db.Column(db.String(80))
    observacao = db.Column(db.String(255))
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'placa': self.placa or '',
            'renavam': self.renavam or '',
            'modelo': self.modelo or '',
            'ano': self.ano or '',
            'capacidade': self.capacidade or '',
            'valor_veiculo': self.valor_veiculo if self.valor_veiculo is not None else 0,
            'valor_carroceria': self.valor_carroceria if self.valor_carroceria is not None else 0,
            'valor_plataforma': self.valor_plataforma if self.valor_plataforma is not None else 0,
            'gaiolas': self.gaiolas if self.gaiolas is not None else 0,
            'unidade': self.unidade or '',
            'observacao': self.observacao or '',
            'ativo': bool(self.ativo),
        }


class LogisticaLancamento(db.Model):
    """Custos operacionais: abastecimento, pedágio e outros."""
    __tablename__ = 'logistica_lancamentos'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('logistica_veiculos.id'), nullable=True, index=True)
    veiculo = db.relationship('LogisticaVeiculo', backref='lancamentos')
    placa = db.Column(db.String(12), index=True)
    categoria = db.Column(db.String(40), nullable=False, index=True)
    descricao = db.Column(db.String(255))
    valor = db.Column(db.Float, nullable=False, default=0)
    km = db.Column(db.Float)
    litros = db.Column(db.Float)
    posto = db.Column(db.String(120))
    observacao = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'data': self.data.isoformat() if self.data else '',
            'veiculo_id': self.veiculo_id,
            'placa': self.placa or '',
            'categoria': self.categoria or '',
            'descricao': self.descricao or '',
            'valor': float(self.valor or 0),
            'km': float(self.km) if self.km is not None else None,
            'litros': float(self.litros) if self.litros is not None else None,
            'posto': self.posto or '',
            'observacao': self.observacao or '',
        }


class LogisticaManutencao(db.Model):
    __tablename__ = 'logistica_manutencoes'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('logistica_veiculos.id'), nullable=True, index=True)
    veiculo = db.relationship('LogisticaVeiculo', backref='manutencoes')
    placa = db.Column(db.String(12), index=True)
    categoria = db.Column(db.String(80))
    tipo_servico = db.Column(db.String(80))
    responsavel = db.Column(db.String(120))
    fornecedor = db.Column(db.String(160))
    nf = db.Column(db.String(80))
    descricao = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Float, default=0)
    parcelas = db.Column(db.Integer, default=1)
    parcelas_pagas = db.Column(db.Integer, default=0)
    vencimento = db.Column(db.Date)
    status = db.Column(db.String(40), default='Aberto')
    observacao = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'data': self.data.isoformat() if self.data else '',
            'veiculo_id': self.veiculo_id,
            'placa': self.placa or '',
            'categoria': self.categoria or '',
            'tipo_servico': self.tipo_servico or '',
            'responsavel': self.responsavel or '',
            'fornecedor': self.fornecedor or '',
            'nf': self.nf or '',
            'descricao': self.descricao or '',
            'valor': float(self.valor or 0),
            'parcelas': int(self.parcelas or 1),
            'parcelas_pagas': int(self.parcelas_pagas or 0),
            'vencimento': self.vencimento.isoformat() if self.vencimento else '',
            'status': self.status or '',
            'observacao': self.observacao or '',
        }


class LogisticaRevisao(db.Model):
    __tablename__ = 'logistica_revisoes'

    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('logistica_veiculos.id'), nullable=True, index=True)
    veiculo = db.relationship('LogisticaVeiculo', backref='revisoes')
    placa = db.Column(db.String(12), index=True)
    tipo = db.Column(db.String(80), nullable=False)
    km_previsto = db.Column(db.Float)
    data_prevista = db.Column(db.Date)
    km_realizado = db.Column(db.Float)
    data_realizado = db.Column(db.Date)
    status = db.Column(db.String(40), default='Pendente')
    observacao = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'veiculo_id': self.veiculo_id,
            'placa': self.placa or '',
            'tipo': self.tipo or '',
            'km_previsto': float(self.km_previsto) if self.km_previsto is not None else None,
            'data_prevista': self.data_prevista.isoformat() if self.data_prevista else '',
            'km_realizado': float(self.km_realizado) if self.km_realizado is not None else None,
            'data_realizado': self.data_realizado.isoformat() if self.data_realizado else '',
            'status': self.status or '',
            'observacao': self.observacao or '',
        }


class LogisticaRota(db.Model):
    __tablename__ = 'logistica_rotas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    setor = db.Column(db.String(80))
    origem = db.Column(db.String(120))
    destino = db.Column(db.String(120))
    origem_ponto_id = db.Column(db.Integer, index=True)
    destino_ponto_id = db.Column(db.Integer, index=True)
    km = db.Column(db.Float)
    placa_padrao = db.Column(db.String(12))
    motorista = db.Column(db.String(120))
    ajudante = db.Column(db.String(120))
    status = db.Column(db.String(40), default='Pendente')
    polyline = db.Column(db.Text)
    ativa = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def polyline_coords(self):
        if not self.polyline:
            return []
        try:
            data = json.loads(self.polyline)
        except (TypeError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome or '',
            'setor': self.setor or '',
            'origem': self.origem or '',
            'destino': self.destino or '',
            'origem_ponto_id': self.origem_ponto_id,
            'destino_ponto_id': self.destino_ponto_id,
            'km': float(self.km) if self.km is not None else None,
            'placa_padrao': self.placa_padrao or '',
            'motorista': self.motorista or '',
            'ajudante': self.ajudante or '',
            'status': self.status or 'Pendente',
            'polyline': self.polyline_coords(),
            'ativa': bool(self.ativa),
        }


class LogisticaEntrega(db.Model):
    __tablename__ = 'logistica_entregas'

    id = db.Column(db.Integer, primary_key=True)
    rota_id = db.Column(db.Integer, db.ForeignKey('logistica_rotas.id'), nullable=True, index=True)
    rota = db.relationship('LogisticaRota', backref='entregas')
    cliente_id = db.Column(db.Integer, index=True)
    nome = db.Column(db.String(160), nullable=False)
    endereco = db.Column(db.String(255))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    status = db.Column(db.String(40), default='Pendente')
    observacao = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'rota_id': self.rota_id,
            'rota': self.rota.nome if self.rota else '',
            'cliente_id': self.cliente_id,
            'nome': self.nome or '',
            'endereco': self.endereco or '',
            'lat': float(self.lat) if self.lat is not None else None,
            'lng': float(self.lng) if self.lng is not None else None,
            'status': self.status or '',
            'observacao': self.observacao or '',
        }


class LogisticaColaborador(db.Model):
    __tablename__ = 'logistica_colaboradores'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    funcao = db.Column(db.String(80))
    setor = db.Column(db.String(80))
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome or '',
            'funcao': self.funcao or '',
            'setor': self.setor or '',
            'ativo': bool(self.ativo),
        }


class LogisticaFolha(db.Model):
    __tablename__ = 'logistica_folhas'

    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(
        db.Integer, db.ForeignKey('logistica_colaboradores.id'), nullable=False, index=True
    )
    colaborador = db.relationship('LogisticaColaborador', backref='folhas')
    mes = db.Column(db.String(7), nullable=False, index=True)  # YYYY-MM
    salario = db.Column(db.Float, default=0)
    insalubridade = db.Column(db.Float, default=0)
    noturno = db.Column(db.Float, default=0)
    hora_extra = db.Column(db.Float, default=0)
    hora_extra_100 = db.Column(db.Float, default=0)
    hora_extra_50 = db.Column(db.Float, default=0)
    repouso = db.Column(db.Float, default=0)
    feriado = db.Column(db.Float, default=0)
    adicional = db.Column(db.Float, default=0)
    alimentacao = db.Column(db.Float, default=0)
    refeicao = db.Column(db.Float, default=0)
    vale_transporte = db.Column(db.Float, default=0)
    faltas = db.Column(db.Float, default=0)
    pensao = db.Column(db.Float, default=0)
    vale = db.Column(db.Float, default=0)
    emprestimo = db.Column(db.Float, default=0)
    inss = db.Column(db.Float, default=0)
    beneficios = db.Column(db.Float, default=0)
    encargos = db.Column(db.Float, default=0)
    outros_empresa = db.Column(db.Float, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('colaborador_id', 'mes', name='uq_logistica_folha_colab_mes'),
    )

    def to_dict(self):
        from logistica_service import totais_folha
        totais = totais_folha(self)
        return {
            'id': self.id,
            'colaborador_id': self.colaborador_id,
            'colaborador': self.colaborador.nome if self.colaborador else '',
            'funcao': self.colaborador.funcao if self.colaborador else '',
            'setor': self.colaborador.setor if self.colaborador else '',
            'mes': self.mes or '',
            'salario': float(self.salario or 0),
            'insalubridade': float(self.insalubridade or 0),
            'noturno': float(self.noturno or 0),
            'hora_extra': float(self.hora_extra or 0),
            'hora_extra_100': float(self.hora_extra_100 or 0),
            'hora_extra_50': float(self.hora_extra_50 or 0),
            'repouso': float(self.repouso or 0),
            'feriado': float(self.feriado or 0),
            'adicional': float(self.adicional or 0),
            'alimentacao': float(self.alimentacao or 0),
            'refeicao': float(self.refeicao or 0),
            'vale_transporte': float(self.vale_transporte or 0),
            'faltas': float(self.faltas or 0),
            'pensao': float(self.pensao or 0),
            'vale': float(self.vale or 0),
            'emprestimo': float(self.emprestimo or 0),
            'inss': float(self.inss or 0),
            'beneficios': float(self.beneficios or 0),
            'encargos': float(self.encargos or 0),
            'outros_empresa': float(self.outros_empresa or 0),
            'proventos': totais['proventos'],
            'descontos': totais['descontos'],
            'liquido': totais['liquido'],
            'custo_empresa': totais['custo_empresa'],
        }


class LogisticaFolga(db.Model):
    __tablename__ = 'logistica_folgas'

    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(
        db.Integer, db.ForeignKey('logistica_colaboradores.id'), nullable=False, index=True
    )
    colaborador = db.relationship('LogisticaColaborador', backref='folgas')
    mes = db.Column(db.String(7), nullable=False, index=True)
    setor = db.Column(db.String(80))
    rota = db.Column(db.String(120))
    dias = db.Column(db.String(255), default='')  # "1,8,15,22"
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('colaborador_id', 'mes', name='uq_logistica_folga_colab_mes'),
    )

    def to_dict(self):
        dias = [d for d in (self.dias or '').split(',') if d.strip()]
        return {
            'id': self.id,
            'colaborador_id': self.colaborador_id,
            'colaborador': self.colaborador.nome if self.colaborador else '',
            'funcao': self.colaborador.funcao if self.colaborador else '',
            'mes': self.mes or '',
            'setor': self.setor or '',
            'rota': self.rota or '',
            'dias': dias,
            'dias_texto': self.dias or '',
        }


class LogisticaOciosidade(db.Model):
    __tablename__ = 'logistica_ociosidade'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('logistica_veiculos.id'), nullable=True, index=True)
    veiculo = db.relationship('LogisticaVeiculo', backref='ociosidade')
    placa = db.Column(db.String(12), index=True)
    horas = db.Column(db.Float, nullable=False, default=0)
    motivo = db.Column(db.String(255))
    valor = db.Column(db.Float, default=0)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'data': self.data.isoformat() if self.data else '',
            'veiculo_id': self.veiculo_id,
            'placa': self.placa or '',
            'horas': float(self.horas or 0),
            'motivo': self.motivo or '',
            'valor': float(self.valor or 0),
        }


class LogisticaChecklist(db.Model):
    __tablename__ = 'logistica_checklists'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('logistica_veiculos.id'), nullable=True, index=True)
    veiculo = db.relationship('LogisticaVeiculo', backref='checklists')
    placa = db.Column(db.String(12), index=True)
    rota = db.Column(db.String(120))
    motorista = db.Column(db.String(120))
    tipo = db.Column(db.String(20), default='Saída')
    itens = db.Column(db.String(255))
    observacao = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'data': self.data.isoformat() if self.data else '',
            'veiculo_id': self.veiculo_id,
            'placa': self.placa or '',
            'rota': self.rota or '',
            'motorista': self.motorista or '',
            'tipo': self.tipo or 'Saída',
            'itens': self.itens or '',
            'observacao': self.observacao or '',
        }


class LogisticaHigiene(db.Model):
    __tablename__ = 'logistica_higiene'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('logistica_veiculos.id'), nullable=True, index=True)
    veiculo = db.relationship('LogisticaVeiculo', backref='higiene')
    placa = db.Column(db.String(12), index=True)
    tipo = db.Column(db.String(80))
    responsavel = db.Column(db.String(120))
    observacao = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'data': self.data.isoformat() if self.data else '',
            'veiculo_id': self.veiculo_id,
            'placa': self.placa or '',
            'tipo': self.tipo or '',
            'responsavel': self.responsavel or '',
            'observacao': self.observacao or '',
        }


class LogisticaColeta(db.Model):
    __tablename__ = 'logistica_coletas'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    cliente = db.Column(db.String(160))
    rota = db.Column(db.String(120))
    peso_sujo = db.Column(db.Float, default=0)
    peso_limpo = db.Column(db.Float, default=0)
    gaiolas = db.Column(db.Integer, default=0)
    valor_kg = db.Column(db.Float, default=0)
    observacao = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        sujo = float(self.peso_sujo or 0)
        limpo = float(self.peso_limpo or 0)
        kg = float(self.valor_kg or 0)
        return {
            'id': self.id,
            'data': self.data.isoformat() if self.data else '',
            'cliente': self.cliente or '',
            'rota': self.rota or '',
            'peso_sujo': sujo,
            'peso_limpo': limpo,
            'diferenca': round(sujo - limpo, 3),
            'gaiolas': int(self.gaiolas or 0),
            'valor_kg': kg,
            'valor_recebido': round(limpo * kg, 2),
            'observacao': self.observacao or '',
        }
