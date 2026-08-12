"""Modelos do Sistema de Controle de Acesso — São Geraldo Service.

Estrutura alinhada ao banco de controle de acesso (users, empresas_acesso,
classificacao/departamento/setor/centro_custo, equipamentos, eventos…).
"""
import json
from datetime import datetime, date, time
from models import db


class AcessoEmpresa(db.Model):
    __tablename__ = 'acesso_empresas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    cnpj = db.Column(db.String(18))
    logo_path = db.Column(db.String(255))  # relativo a static/ (ex: acesso_empresas/logo_1.png)
    ativo = db.Column(db.Boolean, default=True)

    def to_dict(self):
        logo = (self.logo_path or '').strip()
        return {
            'id': self.id,
            'nome': self.nome,
            'cnpj': self.cnpj or '',
            'logo_path': logo,
            'logo_url': f'/static/{logo}' if logo else '',
            'ativo': bool(self.ativo),
        }


class AcessoClassificacao(db.Model):
    __tablename__ = 'acesso_classificacoes'

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False, unique=True)
    mostrar_visitante = db.Column(db.Boolean, default=False)
    perfil_fixo = db.Column(db.String(40), nullable=True)

    def to_dict(self):
        perfil = (self.perfil_fixo or '').strip() or None
        return {
            'id': self.id,
            'descricao': self.descricao,
            'mostrar_visitante': bool(self.mostrar_visitante),
            'perfil_fixo': perfil,
            'perfil': perfil,
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


class AcessoLocal(db.Model):
    """Locais de acesso (portarias, áreas, pontos físicos)."""
    __tablename__ = 'acesso_locais'

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
    entradas = db.Column(db.Integer, default=1)
    saidas = db.Column(db.Integer, default=1)
    livre = db.Column(db.Boolean, default=True)
    por_equipamento = db.Column(db.Boolean, default=False)

    grupo = db.relationship('AcessoGrupo', back_populates='horarios')

    def to_dict(self):
        return {
            'id': self.id,
            'grupo_id': self.grupo_id,
            'dia_semana': self.dia_semana,
            'hora_inicial': self.hora_inicial.strftime('%H:%M') if self.hora_inicial else '',
            'hora_final': self.hora_final.strftime('%H:%M') if self.hora_final else '',
            'entradas': int(self.entradas if self.entradas is not None else 1),
            'saidas': int(self.saidas if self.saidas is not None else 1),
            'livre': bool(self.livre) if self.livre is not None else True,
            'por_equipamento': bool(self.por_equipamento) if self.por_equipamento is not None else False,
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

    def to_dict(self, incluir_senha=False):
        d = {
            'id': self.id,
            'nome': self.nome,
            'marca': self.marca or '',
            'modelo': self.modelo or '',
            'ip': self.ip or '',
            'device_id': self.device_id or '',
            'usuario_disp': self.usuario_disp or 'admin',
            'tem_senha': bool(self.senha_disp),
            'controle_giro': self.controle_giro or '',
            'local': self.local or '',
            'online': bool(self.online),
            'ativo': bool(self.ativo),
            'last_alive': self.last_alive.isoformat(sep=' ', timespec='seconds') if self.last_alive else '',
        }
        if incluir_senha:
            d['senha_disp'] = self.senha_disp or ''
        return d


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
    foto = db.Column(db.Text)  # data URL ou path
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

    def to_dict(self, vinculos=None):
        data = {
            'id': self.id,
            'descricao': self.descricao,
            'nome': self.descricao,
            'digitos': self.digitos or 0,
        }
        if vinculos is not None:
            data['vinculos'] = int(vinculos or 0)
        return data


class AcessoPessoaDocumento(db.Model):
    """Vínculo de documento a uma pessoa (colaborador)."""
    __tablename__ = 'acesso_pessoa_documentos'

    id = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey('acesso_pessoas.id'), nullable=False, index=True)
    tipo_documento_id = db.Column(
        db.Integer, db.ForeignKey('acesso_tipos_documento.id'), nullable=False, index=True
    )
    numero = db.Column(db.String(60))
    validade = db.Column(db.Date)
    valido = db.Column(db.Boolean, default=True, nullable=False)
    arquivo = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    pessoa = db.relationship('AcessoPessoa')
    tipo_documento = db.relationship('AcessoTipoDocumento')

    def is_valido_efetivo(self):
        if not self.valido:
            return False
        if self.validade and self.validade < date.today():
            return False
        return True

    def to_dict(self):
        tipo = self.tipo_documento
        efetivo = self.is_valido_efetivo()
        arquivo = (self.arquivo or '').strip()
        return {
            'id': self.id,
            'pessoa_id': self.pessoa_id,
            'tipo_documento_id': self.tipo_documento_id,
            'tipo_descricao': tipo.descricao if tipo else '',
            'numero': self.numero or '',
            'validade': self.validade.isoformat() if self.validade else '',
            'validade_fmt': self.validade.strftime('%d/%m/%Y') if self.validade else '—',
            'valido': bool(self.valido),
            'valido_efetivo': efetivo,
            'arquivo': arquivo,
            'arquivo_url': f'/static/acesso_documentos/{arquivo}' if arquivo else '',
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else '',
        }


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
    descricao = db.Column(db.Text)
    capacidade_maxima = db.Column(db.Integer, default=10)
    ocupacao_atual = db.Column(db.Integer, default=0)
    vigencia_tipo = db.Column(db.String(20), default='definitivo')  # definitivo | temporario
    data_fim = db.Column(db.Date)
    publico = db.Column(db.String(255), default='')  # csv: funcionarios,alunos,visitantes,responsaveis
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    equipamentos_vinculos = db.relationship(
        'AcessoAmbienteEquipamento',
        back_populates='ambiente',
        cascade='all, delete-orphan',
        lazy='selectin',
    )

    def publico_list(self):
        raw = (self.publico or '').strip()
        if not raw:
            return []
        if raw.startswith('['):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return [str(x).strip() for x in data if str(x).strip()]
            except Exception:
                pass
        return [p.strip() for p in raw.split(',') if p.strip()]

    def to_dict(self, detalhe=False):
        cap = self.capacidade_maxima or 0
        occ = self.ocupacao_atual or 0
        pct = round((occ / cap) * 100, 1) if cap else 0
        vigencia = (self.vigencia_tipo or 'definitivo').strip().lower()
        data = {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao or '',
            'capacidade_maxima': cap,
            'ocupacao_atual': occ,
            'percentual': pct,
            'vigencia_tipo': vigencia,
            'data_fim': self.data_fim.isoformat() if self.data_fim else '',
            'publico': self.publico_list(),
            'ativo': bool(self.ativo),
            'qtd_equipamentos': len(self.equipamentos_vinculos or []),
        }
        if detalhe:
            data['equipamentos'] = [v.to_dict() for v in (self.equipamentos_vinculos or [])]
        return data


class AcessoAmbienteEquipamento(db.Model):
    """Vínculo ambiente ↔ equipamento com fluxo (entrada/saida/ambos)."""
    __tablename__ = 'acesso_ambiente_equipamentos'
    __table_args__ = (
        db.UniqueConstraint('ambiente_id', 'equipamento_id', name='uq_acesso_amb_eq'),
    )

    id = db.Column(db.Integer, primary_key=True)
    ambiente_id = db.Column(db.Integer, db.ForeignKey('acesso_ambientes.id'), nullable=False, index=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('acesso_equipamentos.id'), nullable=False, index=True)
    fluxo = db.Column(db.String(20), default='entrada')  # entrada | saida | ambos

    ambiente = db.relationship('AcessoAmbiente', back_populates='equipamentos_vinculos')
    equipamento = db.relationship('AcessoEquipamento')

    def to_dict(self):
        eq = self.equipamento
        return {
            'id': self.id,
            'ambiente_id': self.ambiente_id,
            'equipamento_id': self.equipamento_id,
            'equipamento_nome': eq.nome if eq else '',
            'equipamento_ip': (eq.ip or '') if eq else '',
            'fluxo': (self.fluxo or 'entrada').lower(),
        }


class AcessoUsuarioPermissao(db.Model):
    """Permissões do módulo Controle de Acesso por usuário do sistema."""
    __tablename__ = 'acesso_usuario_permissoes'
    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'chave', name='uq_acesso_perm_usuario_chave'),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    chave = db.Column(db.String(80), nullable=False, index=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'chave': self.chave,
        }


class AcessoPerfilPermissao(db.Model):
    """Permissões do módulo Controle de Acesso por perfil/tipo de usuário."""
    __tablename__ = 'acesso_perfil_permissoes'
    __table_args__ = (
        db.UniqueConstraint('perfil', 'chave', name='uq_acesso_perm_perfil_chave'),
    )

    id = db.Column(db.Integer, primary_key=True)
    perfil = db.Column(db.String(40), nullable=False, index=True)
    chave = db.Column(db.String(80), nullable=False, index=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'perfil': self.perfil,
            'chave': self.chave,
        }


class AcessoBackupLog(db.Model):
    """Histórico de backups gerados no módulo de acesso."""
    __tablename__ = 'acesso_backup_logs'

    id = db.Column(db.Integer, primary_key=True)
    arquivo = db.Column(db.String(255), nullable=False)
    tamanho_bytes = db.Column(db.Integer, default=0)
    tabelas = db.Column(db.Integer, default=0)
    usuario_nome = db.Column(db.String(120))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'arquivo': self.arquivo,
            'tamanho_bytes': self.tamanho_bytes or 0,
            'tabelas': self.tabelas or 0,
            'usuario_nome': self.usuario_nome or '',
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M:%S') if self.data_criacao else '',
        }


class AcessoBackupConfig(db.Model):
    """Configuração de backup agendado (execução pelo job/serviço futuro)."""
    __tablename__ = 'acesso_backup_config'

    id = db.Column(db.Integer, primary_key=True)
    ativo = db.Column(db.Boolean, default=False, nullable=False)
    frequencia = db.Column(db.String(20), default='Diário', nullable=False)
    horario = db.Column(db.String(5), default='02:00', nullable=False)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'ativo': bool(self.ativo),
            'frequencia': self.frequencia or 'Diário',
            'horario': self.horario or '02:00',
            'atualizado_em': self.atualizado_em.strftime('%d/%m/%Y %H:%M') if self.atualizado_em else '',
        }


class AcessoRefeicao(db.Model):
    """Registro de refeição no controle de acesso (colaborador/visitante)."""
    __tablename__ = 'acesso_refeicoes'

    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow, index=True, nullable=False)
    pessoa_nome = db.Column(db.String(120), nullable=False, default='')
    matricula = db.Column(db.String(40), index=True)
    setor_empresa = db.Column(db.String(160))
    tipo_refeicao = db.Column(db.String(60), default='')
    valor = db.Column(db.Numeric(10, 2), default=0)
    tipo_pessoa = db.Column(db.String(20), default='interno', index=True)  # interno | visitante
    classificacao = db.Column(db.String(80))
    empresa = db.Column(db.String(120))
    setor = db.Column(db.String(120))

    def to_dict(self):
        valor = float(self.valor or 0)
        return {
            'id': self.id,
            'data_hora': self.data_hora.isoformat(sep=' ', timespec='seconds') if self.data_hora else '',
            'data_hora_fmt': self.data_hora.strftime('%d/%m/%Y %H:%M') if self.data_hora else '',
            'pessoa_nome': self.pessoa_nome or '',
            'matricula': self.matricula or '',
            'setor_empresa': self.setor_empresa or '',
            'tipo_refeicao': self.tipo_refeicao or '',
            'valor': valor,
            'valor_fmt': f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
            'tipo_pessoa': (self.tipo_pessoa or 'interno').lower(),
            'classificacao': self.classificacao or '',
            'empresa': self.empresa or '',
            'setor': self.setor or '',
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


class AcessoControleAdicional(db.Model):
    """Bloqueio ou liberação temporária de acesso por período."""
    __tablename__ = 'acesso_controles_adicionais'

    id = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey('acesso_pessoas.id'), nullable=True, index=True)
    nome = db.Column(db.String(120), nullable=False, default='')
    tipo = db.Column(db.String(20), nullable=False, default='bloqueio', index=True)  # bloqueio|liberacao
    data_inicio = db.Column(db.Date, nullable=False, index=True)
    data_fim = db.Column(db.Date, nullable=True, index=True)
    motivo = db.Column(db.String(255))
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    pessoa = db.relationship('AcessoPessoa')

    def expirado(self, ref=None):
        hoje = ref or date.today()
        return bool(self.data_fim and self.data_fim < hoje)

    def to_dict(self):
        tipo = (self.tipo or 'bloqueio').lower()
        return {
            'id': self.id,
            'pessoa_id': self.pessoa_id,
            'nome': self.nome or '',
            'tipo': tipo,
            'tipo_label': 'Bloqueio' if tipo == 'bloqueio' else 'Liberação',
            'data_inicio': self.data_inicio.isoformat() if self.data_inicio else '',
            'data_inicio_fmt': self.data_inicio.strftime('%d/%m/%Y') if self.data_inicio else '',
            'data_fim': self.data_fim.isoformat() if self.data_fim else '',
            'data_fim_fmt': self.data_fim.strftime('%d/%m/%Y') if self.data_fim else '—',
            'motivo': self.motivo or '',
            'ativo': bool(self.ativo),
            'expirado': self.expirado(),
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else '',
        }


class AcessoGrupoRefeicao(db.Model):
    """Grupo de refeições (parâmetros): agrupa itens e vínculos de usuários."""
    __tablename__ = 'acesso_grupos_refeicao'

    TIPOS_COBRANCA = ('MENSAL', 'DIARIO', 'POR_REFEICAO', 'SEMANAL', 'ISENTO')

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    tipo_cobranca = db.Column(db.String(40), nullable=False, default='MENSAL')
    observacoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    exibir_visitantes = db.Column(db.Boolean, default=False, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    itens = db.relationship(
        'AcessoItemRefeicao',
        back_populates='grupo',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )
    vinculos = db.relationship(
        'AcessoVinculoRefeicao',
        back_populates='grupo',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )

    def to_dict(self, detalhe=False):
        tipo = (self.tipo_cobranca or 'MENSAL').upper()
        data = {
            'id': self.id,
            'nome': self.nome or '',
            'tipo_cobranca': tipo,
            'observacoes': self.observacoes or '',
            'ativo': bool(self.ativo),
            'exibir_visitantes': bool(self.exibir_visitantes),
            'qtd_itens': self.itens.count(),
            'qtd_vinculos': self.vinculos.count(),
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else '',
        }
        if detalhe:
            data['itens'] = [i.to_dict() for i in self.itens.order_by(AcessoItemRefeicao.nome).all()]
            data['vinculos'] = [v.to_dict() for v in self.vinculos.order_by(AcessoVinculoRefeicao.pessoa_nome).all()]
        return data


class AcessoItemRefeicao(db.Model):
    """Item de refeição vinculado a um grupo (nome, horário, preço)."""
    __tablename__ = 'acesso_itens_refeicao'

    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('acesso_grupos_refeicao.id'), nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False)
    hora_inicio = db.Column(db.Time)
    hora_fim = db.Column(db.Time)
    valor = db.Column(db.Numeric(10, 2), default=0, nullable=False)  # preço mensal
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    grupo = db.relationship('AcessoGrupoRefeicao', back_populates='itens')

    def to_dict(self):
        valor = float(self.valor or 0)
        hi = self.hora_inicio.strftime('%H:%M') if self.hora_inicio else ''
        hf = self.hora_fim.strftime('%H:%M') if self.hora_fim else ''
        horario = f'{hi} – {hf}' if hi and hf else (hi or hf or '—')
        return {
            'id': self.id,
            'grupo_id': self.grupo_id,
            'nome': self.nome or '',
            'hora_inicio': hi,
            'hora_fim': hf,
            'horario': horario,
            'valor': valor,
            'preco_mensal': valor,
            'valor_fmt': f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
            'preco_mensal_fmt': f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
            'ativo': bool(self.ativo),
        }


class AcessoVinculoRefeicao(db.Model):
    """Vínculo de pessoa/usuário a um grupo de refeição."""
    __tablename__ = 'acesso_vinculos_refeicao'

    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('acesso_grupos_refeicao.id'), nullable=False, index=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey('acesso_pessoas.id'), nullable=True, index=True)
    pessoa_nome = db.Column(db.String(120), nullable=False, default='')
    matricula = db.Column(db.String(40), index=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    grupo = db.relationship('AcessoGrupoRefeicao', back_populates='vinculos')
    pessoa = db.relationship('AcessoPessoa')

    def to_dict(self):
        return {
            'id': self.id,
            'grupo_id': self.grupo_id,
            'pessoa_id': self.pessoa_id,
            'pessoa_nome': self.pessoa_nome or '',
            'matricula': self.matricula or '',
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else '',
        }


class AcessoEstacionamento(db.Model):
    """Gestão de estacionamentos (lotação, equipamentos e permissões)."""
    __tablename__ = 'acesso_estacionamentos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    capacidade_total = db.Column(db.Integer, default=50)
    ocupacao_atual = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    hora_inicio = db.Column(db.Time)
    hora_fim = db.Column(db.Time)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    equipamentos_vinculos = db.relationship(
        'AcessoEstacionamentoEquipamento',
        back_populates='estacionamento',
        cascade='all, delete-orphan',
        lazy='joined',
    )
    permissoes_vinculos = db.relationship(
        'AcessoEstacionamentoPermissao',
        back_populates='estacionamento',
        cascade='all, delete-orphan',
        lazy='joined',
    )

    def to_dict(self, detalhe=False):
        cap = self.capacidade_total if self.capacidade_total is not None else 50
        occ = self.ocupacao_atual or 0
        pct = round((occ / cap) * 100, 1) if cap else 0
        data = {
            'id': self.id,
            'nome': self.nome,
            'capacidade_total': cap,
            'ocupacao_atual': occ,
            'percentual': pct,
            'ilimitado': cap == 0,
            'ativo': bool(self.ativo),
            'hora_inicio': self.hora_inicio.strftime('%H:%M') if self.hora_inicio else '',
            'hora_fim': self.hora_fim.strftime('%H:%M') if self.hora_fim else '',
            'qtd_equipamentos': len(self.equipamentos_vinculos or []),
            'qtd_permissoes': len(self.permissoes_vinculos or []),
        }
        if detalhe:
            data['equipamentos'] = [v.to_dict() for v in (self.equipamentos_vinculos or [])]
            data['permissoes'] = [v.to_dict() for v in (self.permissoes_vinculos or [])]
        return data


class AcessoEstacionamentoEquipamento(db.Model):
    """Vínculo estacionamento ↔ equipamento com fluxo (entrada/saida)."""
    __tablename__ = 'acesso_estacionamento_equipamentos'
    __table_args__ = (
        db.UniqueConstraint('estacionamento_id', 'equipamento_id', name='uq_acesso_est_eq'),
    )

    id = db.Column(db.Integer, primary_key=True)
    estacionamento_id = db.Column(
        db.Integer, db.ForeignKey('acesso_estacionamentos.id'), nullable=False, index=True,
    )
    equipamento_id = db.Column(
        db.Integer, db.ForeignKey('acesso_equipamentos.id'), nullable=False, index=True,
    )
    fluxo = db.Column(db.String(20), default='entrada')  # entrada | saida

    estacionamento = db.relationship('AcessoEstacionamento', back_populates='equipamentos_vinculos')
    equipamento = db.relationship('AcessoEquipamento')

    def to_dict(self):
        eq = self.equipamento
        return {
            'id': self.id,
            'estacionamento_id': self.estacionamento_id,
            'equipamento_id': self.equipamento_id,
            'equipamento_nome': eq.nome if eq else '',
            'equipamento_ip': (eq.ip or '') if eq else '',
            'fluxo': (self.fluxo or 'entrada').lower(),
        }


class AcessoEstacionamentoPermissao(db.Model):
    """Permissão/cota de vagas por tipo ou grupo no estacionamento."""
    __tablename__ = 'acesso_estacionamento_permissoes'
    __table_args__ = (
        db.UniqueConstraint('estacionamento_id', 'chave', name='uq_acesso_est_perm'),
    )

    id = db.Column(db.Integer, primary_key=True)
    estacionamento_id = db.Column(
        db.Integer, db.ForeignKey('acesso_estacionamentos.id'), nullable=False, index=True,
    )
    chave = db.Column(db.String(80), nullable=False)  # funcionarios | visitantes | grupo:3 …
    label = db.Column(db.String(120), nullable=False, default='')
    grupo_id = db.Column(db.Integer, db.ForeignKey('acesso_grupos.id'), nullable=True, index=True)
    vagas = db.Column(db.Integer, default=1)  # vagas/prioridade

    estacionamento = db.relationship('AcessoEstacionamento', back_populates='permissoes_vinculos')
    grupo = db.relationship('AcessoGrupo')

    def to_dict(self):
        return {
            'id': self.id,
            'estacionamento_id': self.estacionamento_id,
            'chave': self.chave,
            'label': self.label or self.chave,
            'grupo_id': self.grupo_id,
            'vagas': self.vagas if self.vagas is not None else 1,
        }


class AcessoEscala(db.Model):
    """Escala de trabalho/acesso do colaborador (ciclos, horários e exceções)."""
    __tablename__ = 'acesso_escalas'

    id = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey('acesso_pessoas.id'), nullable=True, index=True)
    nome_pessoa = db.Column(db.String(120), nullable=False, default='')
    tipo = db.Column(db.String(40), nullable=False, default='5x2')  # espelho de dias_trabalho x dias_folga
    data_inicio = db.Column(db.Date, nullable=False, index=True)
    data_fim = db.Column(db.Date, nullable=True, index=True)
    dias_trabalho = db.Column(db.Integer, nullable=False, default=5)
    dias_folga = db.Column(db.Integer, nullable=False, default=2)
    hora_entrada = db.Column(db.Time, nullable=True)
    hora_saida = db.Column(db.Time, nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    pessoa = db.relationship('AcessoPessoa')

    def sync_tipo(self):
        dt = self.dias_trabalho if self.dias_trabalho is not None else 5
        df = self.dias_folga if self.dias_folga is not None else 2
        self.tipo = f'{dt}x{df}'
        return self.tipo

    @property
    def tipo_label(self):
        return self.tipo or self.sync_tipo()

    def to_dict(self):
        tipo = self.tipo_label
        return {
            'id': self.id,
            'pessoa_id': self.pessoa_id,
            'nome_pessoa': self.nome_pessoa or '',
            'tipo': tipo,
            'data_inicio': self.data_inicio.isoformat() if self.data_inicio else '',
            'data_inicio_fmt': self.data_inicio.strftime('%d/%m/%Y') if self.data_inicio else '',
            'data_fim': self.data_fim.isoformat() if self.data_fim else '',
            'data_fim_fmt': self.data_fim.strftime('%d/%m/%Y') if self.data_fim else 'Indeterminado',
            'dias_trabalho': self.dias_trabalho if self.dias_trabalho is not None else 5,
            'dias_folga': self.dias_folga if self.dias_folga is not None else 2,
            'hora_entrada': self.hora_entrada.strftime('%H:%M') if self.hora_entrada else '',
            'hora_saida': self.hora_saida.strftime('%H:%M') if self.hora_saida else '',
            'ativo': bool(self.ativo),
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else '',
        }


class AcessoVeiculo(db.Model):
    """Veículo cadastrado e vinculado a um colaborador (proprietário)."""
    __tablename__ = 'acesso_veiculos'

    id = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey('acesso_pessoas.id'), nullable=False, index=True)
    placa = db.Column(db.String(20), nullable=False, index=True)
    modelo = db.Column(db.String(80), nullable=False, default='')
    cor = db.Column(db.String(40), nullable=False, default='')
    tag_uhf = db.Column(db.String(60), nullable=True, index=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    pessoa = db.relationship('AcessoPessoa')

    def to_dict(self):
        return {
            'id': self.id,
            'pessoa_id': self.pessoa_id,
            'placa': (self.placa or '').upper(),
            'modelo': self.modelo or '',
            'cor': self.cor or '',
            'tag_uhf': self.tag_uhf or '',
            'ativo': bool(self.ativo),
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else '',
        }


class AcessoVeiculoEvento(db.Model):
    """Evento de circulação veicular (placa / tag UHF)."""
    __tablename__ = 'acesso_veiculo_eventos'

    id = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(20), index=True)
    usuario_nome = db.Column(db.String(120), nullable=False, default='')
    equipamento = db.Column(db.String(100))  # catraca / leitor
    sentido = db.Column(db.String(40))  # Entrada | Saída
    status = db.Column(db.String(20), nullable=False, default='Liberado')
    data_hora = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        st = self.status or 'Liberado'
        return {
            'id': self.id,
            'placa': (self.placa or '').upper(),
            'usuario_nome': self.usuario_nome or '—',
            'equipamento': self.equipamento or '—',
            'sentido': self.sentido or '',
            'status': st,
            'data_hora': self.data_hora.isoformat(sep=' ', timespec='seconds') if self.data_hora else '',
            'data_hora_fmt': self.data_hora.strftime('%d/%m/%Y %H:%M:%S') if self.data_hora else '—',
        }


class AcessoImpressora(db.Model):
    """Impressoras de comprovantes / vouchers do Controle de Acesso."""
    __tablename__ = 'acesso_impressoras'

    TIPOS = (
        'ControliD Print ID Touch (TCP)',
        'ControliD iDPrint (TCP)',
        'Genérica ESC/POS TCP',
        'Genérica ESC/POS USB',
        'Epson TM (ESC/POS TCP)',
    )

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    ip = db.Column(db.String(45), nullable=False, default='')
    porta = db.Column(db.Integer, nullable=False, default=9100)
    tipo = db.Column(db.String(80), nullable=False, default='Genérica ESC/POS TCP')
    ativo = db.Column(db.Boolean, default=True)
    padrao_voucher = db.Column(db.Boolean, default=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome or '',
            'ip': self.ip or '',
            'porta': self.porta if self.porta is not None else 9100,
            'tipo': self.tipo or 'Genérica ESC/POS TCP',
            'ativo': bool(self.ativo),
            'padrao_voucher': bool(self.padrao_voucher),
            'data_criacao': self.data_criacao.isoformat(sep=' ', timespec='seconds') if self.data_criacao else '',
        }
