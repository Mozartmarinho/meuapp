"""Modelos do Sistema de Controle de Acesso — São Geraldo Service.

Estrutura alinhada ao banco de controle de acesso (users, empresas_acesso,
classificacao/departamento/setor/centro_custo, equipamentos, eventos…).
"""
from datetime import datetime, date, time
from models import db


class AcessoEmpresa(db.Model):
    __tablename__ = 'acesso_empresas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    cnpj = db.Column(db.String(18))
    ativo = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {'id': self.id, 'nome': self.nome, 'cnpj': self.cnpj or '', 'ativo': bool(self.ativo)}


class AcessoClassificacao(db.Model):
    __tablename__ = 'acesso_classificacoes'

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False, unique=True)
    mostrar_visitante = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'descricao': self.descricao,
            'mostrar_visitante': bool(self.mostrar_visitante),
        }


class AcessoDepartamento(db.Model):
    __tablename__ = 'acesso_departamentos'

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False, unique=True)

    def to_dict(self):
        return {'id': self.id, 'descricao': self.descricao}


class AcessoSetor(db.Model):
    __tablename__ = 'acesso_setores'

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False, unique=True)

    def to_dict(self):
        return {'id': self.id, 'descricao': self.descricao}


class AcessoCentroCusto(db.Model):
    __tablename__ = 'acesso_centros_custo'

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False, unique=True)

    def to_dict(self):
        return {'id': self.id, 'descricao': self.descricao}


class AcessoGrupo(db.Model):
    __tablename__ = 'acesso_grupos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    pessoas = db.relationship('AcessoPessoa', back_populates='grupo', lazy='dynamic')
    visitantes = db.relationship('AcessoVisitante', back_populates='grupo', lazy='dynamic')
    horarios = db.relationship('AcessoHorario', back_populates='grupo', cascade='all, delete-orphan')
    equipamentos = db.relationship(
        'AcessoEquipamento',
        secondary='acesso_grupo_equipamentos',
        back_populates='grupos',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao or '',
            'ativo': bool(self.ativo),
            'qtd_pessoas': self.pessoas.filter_by(ativo=True).count(),
            'qtd_equipamentos': len(self.equipamentos or []),
        }


class AcessoHorario(db.Model):
    __tablename__ = 'acesso_horarios'

    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('acesso_grupos.id'), nullable=False, index=True)
    dia_semana = db.Column(db.String(20), nullable=False, default='TODOS')
    hora_inicial = db.Column(db.Time, nullable=False, default=time(0, 0))
    hora_final = db.Column(db.Time, nullable=False, default=time(23, 59))

    grupo = db.relationship('AcessoGrupo', back_populates='horarios')

    def to_dict(self):
        return {
            'id': self.id,
            'grupo_id': self.grupo_id,
            'dia_semana': self.dia_semana,
            'hora_inicial': self.hora_inicial.strftime('%H:%M') if self.hora_inicial else '',
            'hora_final': self.hora_final.strftime('%H:%M') if self.hora_final else '',
        }


acesso_grupo_equipamentos = db.Table(
    'acesso_grupo_equipamentos',
    db.Column('grupo_id', db.Integer, db.ForeignKey('acesso_grupos.id'), primary_key=True),
    db.Column('equipamento_id', db.Integer, db.ForeignKey('acesso_equipamentos.id'), primary_key=True),
)


class AcessoEquipamento(db.Model):
    __tablename__ = 'acesso_equipamentos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    marca = db.Column(db.String(80), default='Control iD')
    modelo = db.Column(db.String(80), default='iDFace')
    ip = db.Column(db.String(45))
    device_id = db.Column(db.String(60), unique=True)
    usuario_disp = db.Column(db.String(80), default='admin')
    senha_disp = db.Column(db.String(120))
    controle_giro = db.Column(db.String(60), default='Ambos os lados')
    local = db.Column(db.String(120))
    online = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    last_alive = db.Column(db.DateTime)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    grupos = db.relationship(
        'AcessoGrupo',
        secondary=acesso_grupo_equipamentos,
        back_populates='equipamentos',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'marca': self.marca or '',
            'modelo': self.modelo or '',
            'ip': self.ip or '',
            'device_id': self.device_id or '',
            'controle_giro': self.controle_giro or '',
            'local': self.local or '',
            'online': bool(self.online),
            'ativo': bool(self.ativo),
            'last_alive': self.last_alive.isoformat(sep=' ', timespec='seconds') if self.last_alive else '',
        }


class AcessoPessoa(db.Model):
    """Colaboradores (equivalente à tabela users do banco de acesso)."""
    __tablename__ = 'acesso_pessoas'

    id = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(40), nullable=False, unique=True, index=True)
    nome = db.Column(db.String(120), nullable=False)
    cartao = db.Column(db.String(40), index=True)
    qr_code = db.Column(db.String(120), index=True)
    documento = db.Column(db.String(40))
    # campos legados (texto) — mantidos para compatibilidade
    departamento = db.Column(db.String(100))
    setor = db.Column(db.String(100))
    empresa = db.Column(db.String(120))
    # FKs organizacionais
    empresa_id = db.Column(db.Integer, db.ForeignKey('acesso_empresas.id'), index=True)
    classificacao_id = db.Column(db.Integer, db.ForeignKey('acesso_classificacoes.id'), index=True)
    departamento_id = db.Column(db.Integer, db.ForeignKey('acesso_departamentos.id'), index=True)
    setor_id = db.Column(db.Integer, db.ForeignKey('acesso_setores.id'), index=True)
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('acesso_centros_custo.id'), index=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('acesso_grupos.id'), index=True)
    data_inicial = db.Column(db.Date, default=date.today)
    hora_inicial = db.Column(db.Time, default=time(0, 0))
    data_final = db.Column(db.Date)
    hora_final = db.Column(db.Time)
    tipo_cartao = db.Column(db.String(20), default='wiegand')  # wiegand|mifare
    token = db.Column(db.String(100))
    equipamentos_ids = db.Column(db.String(255))  # ids separados por vírgula
    # Ativo | Inativo | Livre
    status = db.Column(db.String(20), default='Ativo', index=True)
    ativo = db.Column(db.Boolean, default=True)  # espelho: False quando Inativo
    foto = db.Column(db.String(255))
    observacao = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    grupo = db.relationship('AcessoGrupo', back_populates='pessoas')
    empresa_ref = db.relationship('AcessoEmpresa')
    classificacao_ref = db.relationship('AcessoClassificacao')
    departamento_ref = db.relationship('AcessoDepartamento')
    setor_ref = db.relationship('AcessoSetor')
    centro_custo_ref = db.relationship('AcessoCentroCusto')

    def sync_ativo_status(self):
        st = (self.status or 'Ativo').strip()
        if st not in ('Ativo', 'Inativo', 'Livre'):
            st = 'Ativo'
        self.status = st
        self.ativo = st != 'Inativo'

    def to_dict(self):
        return {
            'id': self.id,
            'matricula': self.matricula,
            'nome': self.nome,
            'cartao': self.cartao or '',
            'qr_code': self.qr_code or '',
            'documento': self.documento or '',
            'empresa_id': self.empresa_id,
            'empresa_nome': (
                self.empresa_ref.nome if self.empresa_ref else (self.empresa or '')
            ),
            'classificacao_id': self.classificacao_id,
            'classificacao': self.classificacao_ref.descricao if self.classificacao_ref else '',
            'departamento_id': self.departamento_id,
            'departamento': (
                self.departamento_ref.descricao if self.departamento_ref else (self.departamento or '')
            ),
            'setor_id': self.setor_id,
            'setor': self.setor_ref.descricao if self.setor_ref else (self.setor or ''),
            'centro_custo_id': self.centro_custo_id,
            'centro_custo': self.centro_custo_ref.descricao if self.centro_custo_ref else '',
            'grupo_id': self.grupo_id,
            'grupo_nome': self.grupo.nome if self.grupo else '',
            'data_inicial': self.data_inicial.isoformat() if self.data_inicial else '',
            'hora_inicial': self.hora_inicial.strftime('%H:%M') if self.hora_inicial else '',
            'data_final': self.data_final.isoformat() if self.data_final else '',
            'hora_final': self.hora_final.strftime('%H:%M') if self.hora_final else '',
            'tipo_cartao': self.tipo_cartao or 'wiegand',
            'token': self.token or '',
            'equipamentos_ids': self.equipamentos_ids or '',
            'status': self.status or ('Ativo' if self.ativo else 'Inativo'),
            'ativo': bool(self.ativo) if self.status != 'Inativo' else False,
            'foto': self.foto or '',
            'tem_foto': bool(self.foto),
            'observacao': self.observacao or '',
        }


class AcessoTipoDocumento(db.Model):
    """Tipos de documento do visitante (CPF, RG, etc.)."""
    __tablename__ = 'acesso_tipos_documento'

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(40), nullable=False, unique=True)
    digitos = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {'id': self.id, 'descricao': self.descricao, 'digitos': self.digitos or 0}


class AcessoVisitante(db.Model):
    """Visitantes — alinhado à tabela visitantes do banco de referência."""
    __tablename__ = 'acesso_visitantes'

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.String(40), nullable=False, unique=True, index=True)
    nome = db.Column(db.String(120), nullable=False)
    tipo_documento = db.Column(db.String(40), default='CPF')
    documento = db.Column(db.String(40), index=True)
    cpf = db.Column(db.String(14), index=True)
    rg = db.Column(db.String(20))
    empresa_id = db.Column(db.Integer, db.ForeignKey('acesso_empresas.id'), index=True)
    empresa_visitada = db.Column(db.String(120))  # legado texto
    classificacao_id = db.Column(db.Integer, db.ForeignKey('acesso_classificacoes.id'), index=True)
    anfitriao = db.Column(db.String(120))  # visitando quem
    motivo = db.Column(db.String(200))
    cartao = db.Column(db.String(40))
    tipo_cartao = db.Column(db.String(20), default='wiegand')
    qr_code = db.Column(db.String(120))
    token = db.Column(db.String(100))
    foto = db.Column(db.Text)  # data URL ou path
    grupo_id = db.Column(db.Integer, db.ForeignKey('acesso_grupos.id'), index=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('acesso_equipamentos.id'), index=True)
    local_acesso = db.Column(db.String(120))
    ident_modo = db.Column(db.String(20), default='foto')  # foto|qr|cartao
    data_inicial = db.Column(db.Date, nullable=False, default=date.today)
    hora_inicial = db.Column(db.Time, default=time(0, 0))
    data_final = db.Column(db.Date)
    hora_final = db.Column(db.Time)
    visita_unica = db.Column(db.Boolean, default=False)
    refeicao = db.Column(db.Boolean, default=False)
    refeicao_creditos = db.Column(db.Integer, default=0)
    imprimir_ao_salvar = db.Column(db.Boolean, default=False)
    baixar_qr_ao_salvar = db.Column(db.Boolean, default=False)
    impressora = db.Column(db.String(80))
    modelo_impressao = db.Column(db.String(80))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    grupo = db.relationship('AcessoGrupo', back_populates='visitantes')
    empresa_ref = db.relationship('AcessoEmpresa')
    classificacao_ref = db.relationship('AcessoClassificacao')
    equipamento_ref = db.relationship('AcessoEquipamento')

    def to_dict(self):
        return {
            'id': self.id,
            'visitor_id': self.visitor_id,
            'nome': self.nome,
            'tipo_documento': self.tipo_documento or 'CPF',
            'documento': self.documento or self.cpf or self.rg or '',
            'cpf': self.cpf or '',
            'rg': self.rg or '',
            'empresa_id': self.empresa_id,
            'empresa_nome': (
                self.empresa_ref.nome if self.empresa_ref else (self.empresa_visitada or '')
            ),
            'empresa_visitada': self.empresa_visitada or '',
            'classificacao_id': self.classificacao_id,
            'classificacao': self.classificacao_ref.descricao if self.classificacao_ref else '',
            'anfitriao': self.anfitriao or '',
            'motivo': self.motivo or '',
            'cartao': self.cartao or '',
            'tipo_cartao': self.tipo_cartao or 'wiegand',
            'qr_code': self.qr_code or '',
            'token': self.token or '',
            'foto': self.foto or '',
            'tem_foto': bool(self.foto),
            'grupo_id': self.grupo_id,
            'grupo_nome': self.grupo.nome if self.grupo else '',
            'equipamento_id': self.equipamento_id,
            'equipamento_nome': self.equipamento_ref.nome if self.equipamento_ref else '',
            'local_acesso': self.local_acesso or '',
            'ident_modo': self.ident_modo or 'foto',
            'data_inicial': self.data_inicial.isoformat() if self.data_inicial else '',
            'hora_inicial': self.hora_inicial.strftime('%H:%M') if self.hora_inicial else '',
            'data_final': self.data_final.isoformat() if self.data_final else '',
            'hora_final': self.hora_final.strftime('%H:%M') if self.hora_final else '',
            'visita_unica': bool(self.visita_unica),
            'refeicao': bool(self.refeicao),
            'refeicao_creditos': self.refeicao_creditos or 0,
            'imprimir_ao_salvar': bool(self.imprimir_ao_salvar),
            'baixar_qr_ao_salvar': bool(self.baixar_qr_ao_salvar),
            'impressora': self.impressora or '',
            'modelo_impressao': self.modelo_impressao or '',
            'ativo': bool(self.ativo),
            'data_criacao': self.data_criacao.isoformat(sep=' ', timespec='seconds') if self.data_criacao else '',
        }


class AcessoAmbiente(db.Model):
    """Lotação de ambientes (ambientes_controle do banco de referência)."""
    __tablename__ = 'acesso_ambientes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    descricao = db.Column(db.String(255))
    capacidade_maxima = db.Column(db.Integer, default=0)
    ocupacao_atual = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)

    def to_dict(self):
        cap = self.capacidade_maxima or 0
        occ = self.ocupacao_atual or 0
        pct = round((occ / cap) * 100, 1) if cap else 0
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao or '',
            'capacidade_maxima': cap,
            'ocupacao_atual': occ,
            'percentual': pct,
            'ativo': bool(self.ativo),
        }


class AcessoEvento(db.Model):
    __tablename__ = 'acesso_eventos'

    id = db.Column(db.Integer, primary_key=True)
    pessoa_ref = db.Column(db.String(40), index=True)
    nome = db.Column(db.String(120), nullable=False)
    tipo_pessoa = db.Column(db.String(20), default='PESSOA')
    status = db.Column(db.String(20), nullable=False, default='Liberado')
    direction = db.Column(db.String(40))
    event_type = db.Column(db.String(80))
    equipamento_id = db.Column(db.Integer, db.ForeignKey('acesso_equipamentos.id'), index=True)
    equipamento_nome = db.Column(db.String(100))
    cartao = db.Column(db.String(40))
    girou = db.Column(db.String(20))
    motivo = db.Column(db.String(120))
    data_hora = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    equipamento = db.relationship('AcessoEquipamento')

    def status_exibicao(self):
        if (self.girou or '').upper() == 'GIVE UP' or self.status == 'Desistência':
            return 'Desistência'
        return self.status or 'Liberado'

    def to_dict(self):
        nome = self.nome or '?'
        iniciais = ''.join(p[0] for p in nome.split()[:2]).upper() if nome else '?'
        status = self.status_exibicao()
        return {
            'id': self.id,
            'pessoa_ref': self.pessoa_ref or '',
            'nome': nome,
            'iniciais': iniciais[:2],
            'tipo_pessoa': self.tipo_pessoa or 'PESSOA',
            'tipo_label': 'User' if (self.tipo_pessoa or '').upper() == 'PESSOA' else (self.tipo_pessoa or 'User'),
            'status': status,
            'direction': self.direction or '',
            'event_type': self.event_type or '',
            'equipamento_id': self.equipamento_id,
            'equipamento_nome': self.equipamento_nome or (self.equipamento.nome if self.equipamento else ''),
            'cartao': self.cartao or '',
            'girou': self.girou or '',
            'motivo': self.motivo or '',
            'data_hora': self.data_hora.isoformat(sep=' ', timespec='seconds') if self.data_hora else '',
            'data_hora_fmt': self.data_hora.strftime('%d/%m %H:%M:%S') if self.data_hora else '',
        }
