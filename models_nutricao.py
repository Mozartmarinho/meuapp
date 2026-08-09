"""Modelos do módulo de Nutrição Hospitalar."""
from datetime import datetime, date
from models import db


nut_clinica_enfermarias = db.Table(
    'nut_clinica_enfermarias',
    db.Column('clinica_id', db.Integer, db.ForeignKey('nut_clinicas.id'), primary_key=True),
    db.Column('enfermaria_id', db.Integer, db.ForeignKey('nut_enfermarias.id'), primary_key=True),
)


class NutClinica(db.Model):
    """Clínica (unidade/setor) usada no mapa e nos cadastros."""
    __tablename__ = 'nut_clinicas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False, unique=True)
    centro_custo = db.Column(db.String(50))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    enfermarias = db.relationship(
        'NutEnfermaria',
        secondary=nut_clinica_enfermarias,
        lazy='select',
        back_populates='clinicas',
        order_by='NutEnfermaria.nome',
    )

    def to_dict(self, include_enfermarias=False):
        data = {
            'id': self.id,
            'nome': self.nome,
            'centro_custo': self.centro_custo or '',
            'ativo': bool(self.ativo),
        }
        if include_enfermarias:
            data['enfermaria_ids'] = [e.id for e in self.enfermarias]
            data['enfermarias'] = [e.to_dict() for e in self.enfermarias]
        return data


class NutEnfermaria(db.Model):
    """Enfermaria/unidade física vinculável a uma ou mais clínicas."""
    __tablename__ = 'nut_enfermarias'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False, unique=True)
    nutriz = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    clinicas = db.relationship(
        'NutClinica',
        secondary=nut_clinica_enfermarias,
        lazy='select',
        back_populates='enfermarias',
    )
    leitos = db.relationship(
        'NutLeito',
        back_populates='enfermaria',
        lazy='select',
        cascade='all, delete-orphan',
        order_by='NutLeito.numero',
    )

    def to_dict(self, include_leitos=False, num_leitos=None):
        data = {
            'id': self.id,
            'nome': self.nome,
            'nutriz': bool(self.nutriz),
            'ativo': bool(self.ativo),
            'num_leitos': num_leitos if num_leitos is not None else len(self.leitos or []),
        }
        if include_leitos:
            data['leitos'] = [l.to_dict() for l in self.leitos]
        return data


class NutLeito(db.Model):
    """Leito vinculado a uma enfermaria."""
    __tablename__ = 'nut_leitos'

    id = db.Column(db.Integer, primary_key=True)
    enfermaria_id = db.Column(db.Integer, db.ForeignKey('nut_enfermarias.id'), nullable=False, index=True)
    enfermaria = db.relationship('NutEnfermaria', back_populates='leitos')
    numero = db.Column(db.Integer, nullable=False, default=1)
    nome = db.Column(db.String(80), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('enfermaria_id', 'numero', name='uq_leito_enfermaria_numero'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'enfermaria_id': self.enfermaria_id,
            'numero': self.numero,
            'nome': self.nome or '',
            'ativo': bool(self.ativo),
        }


class NutDieta(db.Model):
    __tablename__ = 'nut_dietas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False, unique=True)
    # basica | enteral | formula | lve | suplemento | outro
    categoria = db.Column(db.String(40), default='basica')
    # Agrupamento visual (ex.: DIETAS ORAIS, NUTRICAO ENTERAL)
    grupo = db.Column(db.String(80), default='')
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'categoria': self.categoria or 'basica',
            'grupo': self.grupo or '',
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
    hora_saida = db.Column(db.String(20))
    motivo_saida = db.Column(db.String(40))
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
            'hora_saida': self.hora_saida or '',
            'motivo_saida': self.motivo_saida or '',
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
    enfermaria = db.Column(db.String(120))

    # Flags de refeição: D C A M J C (ceia)
    fl_desjejum = db.Column(db.Boolean, default=False)
    fl_colacao = db.Column(db.Boolean, default=False)
    fl_almoco = db.Column(db.Boolean, default=False)
    fl_merenda = db.Column(db.Boolean, default=False)
    fl_jantar = db.Column(db.Boolean, default=False)
    fl_ceia = db.Column(db.Boolean, default=False)

    # Campos extras do mapa de produção
    obs_etiqueta = db.Column(db.Text)
    extras = db.Column(db.Text)
    suplementos = db.Column(db.Text)
    enteral = db.Column(db.Text)
    formula_infantil = db.Column(db.Text)
    lve = db.Column(db.Text)
    # Cardápio personalizado por refeição (JSON): { meal: { pares, justificativa } }
    substituicoes = db.Column(db.Text)
    data_inclusao = db.Column(db.DateTime, default=datetime.utcnow)
    usuario_alteracao = db.Column(db.String(80))

    data_saida = db.Column(db.Date)
    motivo_saida = db.Column(db.String(40))
    hospital_transferencia = db.Column(db.String(200))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_substituicoes(self):
        import json
        if not self.substituicoes:
            return {}
        try:
            data = json.loads(self.substituicoes)
            return data if isinstance(data, dict) else {}
        except (TypeError, ValueError):
            return {}

    def set_substituicoes(self, data):
        import json
        self.substituicoes = json.dumps(data or {}, ensure_ascii=False)

    def to_dict(self):
        inclusao = self.data_inclusao or self.data_criacao
        alteracao = self.data_atualizacao or inclusao
        usuario = (self.usuario_alteracao or '').strip()
        ultima = ''
        if alteracao:
            ultima = alteracao.strftime('%d/%m/%y %H:%M:%S')
            if usuario:
                ultima = f'{usuario} — {ultima}'
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
            'enfermaria': self.enfermaria or '',
            'fl_desjejum': bool(self.fl_desjejum),
            'fl_colacao': bool(self.fl_colacao),
            'fl_almoco': bool(self.fl_almoco),
            'fl_merenda': bool(self.fl_merenda),
            'fl_jantar': bool(self.fl_jantar),
            'fl_ceia': bool(self.fl_ceia),
            'obs_etiqueta': self.obs_etiqueta or '',
            'extras': self.extras or '',
            'suplementos': self.suplementos or '',
            'enteral': self.enteral or '',
            'formula_infantil': self.formula_infantil or '',
            'lve': self.lve or '',
            'substituicoes': self.get_substituicoes(),
            'data_inclusao': inclusao.strftime('%d/%m/%y %H:%M:%S') if inclusao else '',
            'usuario_alteracao': usuario,
            'ultima_alteracao': ultima,
            'data_saida': self.data_saida.isoformat() if self.data_saida else '',
            'motivo_saida': self.motivo_saida or '',
            'hospital_transferencia': self.hospital_transferencia or '',
            'ativo': self.ativo,
        }


class NutCardapio(db.Model):
    """Cardápio diário por tipo de dieta (grandes / pequenas / líquidas)."""
    __tablename__ = 'nut_cardapios'

    id = db.Column(db.Integer, primary_key=True)
    # grandes | pequenas | liquidas
    tipo = db.Column(db.String(20), nullable=False, index=True)
    grupo_cardapio = db.Column(db.String(80), default='PRINCIPAL')
    dia_mes = db.Column(db.Integer, default=1)
    dia_semana = db.Column(db.String(20))
    dieta = db.Column(db.String(200))

    hr_desjejum = db.Column(db.Boolean, default=False)
    hr_colacao = db.Column(db.Boolean, default=False)
    hr_almoco = db.Column(db.Boolean, default=False)
    hr_merenda = db.Column(db.Boolean, default=False)
    hr_jantar = db.Column(db.Boolean, default=False)
    hr_ceia = db.Column(db.Boolean, default=False)

    # campos específicos da aba (JSON/Text)
    itens = db.Column(db.Text)

    vet = db.Column(db.Float, default=0)
    custo = db.Column(db.Float, default=0)
    organizar_por = db.Column(db.String(40), default='Dia;Dieta;Horário')
    usuario_alteracao = db.Column(db.String(80))
    data_alteracao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def get_itens(self):
        import json
        if not self.itens:
            return {}
        try:
            return json.loads(self.itens)
        except (TypeError, ValueError):
            return {}

    def set_itens(self, data):
        import json
        self.itens = json.dumps(data or {}, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'tipo': self.tipo,
            'grupo_cardapio': self.grupo_cardapio or 'PRINCIPAL',
            'dia_mes': self.dia_mes or 1,
            'dia_semana': self.dia_semana or '',
            'dieta': self.dieta or '',
            'hr_desjejum': bool(self.hr_desjejum),
            'hr_colacao': bool(self.hr_colacao),
            'hr_almoco': bool(self.hr_almoco),
            'hr_merenda': bool(self.hr_merenda),
            'hr_jantar': bool(self.hr_jantar),
            'hr_ceia': bool(self.hr_ceia),
            'itens': self.get_itens(),
            'vet': self.vet or 0,
            'custo': self.custo or 0,
            'organizar_por': self.organizar_por or 'Dia;Dieta;Horário',
            'usuario_alteracao': self.usuario_alteracao or '',
            'data_alteracao': self.data_alteracao.strftime('%d/%m/%Y %H:%M:%S') if self.data_alteracao else '',
            'ativo': bool(self.ativo),
        }


class NutTabelaNutrientes(db.Model):
    """Tabela de nutrientes (ex.: Tabela Padrão / TACO)."""
    __tablename__ = 'nut_tabelas_nutrientes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False, unique=True)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    alimentos = db.relationship(
        'NutAlimento',
        back_populates='tabela',
        lazy='select',
        cascade='all, delete-orphan',
        order_by='NutAlimento.nome',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'ativo': bool(self.ativo),
            'qtd_alimentos': len(self.alimentos or []),
        }


class NutAlimento(db.Model):
    """Alimento de uma tabela nutricional."""
    __tablename__ = 'nut_alimentos'

    id = db.Column(db.Integer, primary_key=True)
    tabela_id = db.Column(db.Integer, db.ForeignKey('nut_tabelas_nutrientes.id'), nullable=False, index=True)
    tabela = db.relationship('NutTabelaNutrientes', back_populates='alimentos')
    nome = db.Column(db.String(200), nullable=False)

    cal_carboidratos = db.Column(db.Float, default=0)
    cal_gordura = db.Column(db.Float, default=0)
    cal_proteina = db.Column(db.Float, default=0)
    cal_total = db.Column(db.Float, default=0)

    qtd_carboidratos = db.Column(db.Float, default=0)
    qtd_gordura = db.Column(db.Float, default=0)
    qtd_proteina = db.Column(db.Float, default=0)

    ref_consumo = db.Column(db.String(80))
    coeficiente_npu = db.Column(db.Float, default=0)
    gluten = db.Column(db.Boolean, default=False)
    fenilalanina = db.Column(db.Boolean, default=False)

    ultima_alteracao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    nutrientes = db.relationship(
        'NutAlimentoNutriente',
        back_populates='alimento',
        lazy='joined',
        cascade='all, delete-orphan',
        order_by='NutAlimentoNutriente.id',
    )

    def to_dict(self, include_nutrientes=True):
        data = {
            'id': self.id,
            'tabela_id': self.tabela_id,
            'nome': self.nome,
            'cal_carboidratos': self.cal_carboidratos or 0,
            'cal_gordura': self.cal_gordura or 0,
            'cal_proteina': self.cal_proteina or 0,
            'cal_total': self.cal_total or 0,
            'qtd_carboidratos': self.qtd_carboidratos or 0,
            'qtd_gordura': self.qtd_gordura or 0,
            'qtd_proteina': self.qtd_proteina or 0,
            'ref_consumo': self.ref_consumo or '',
            'coeficiente_npu': self.coeficiente_npu or 0,
            'gluten': bool(self.gluten),
            'fenilalanina': bool(self.fenilalanina),
            'ultima_alteracao': self.ultima_alteracao.strftime('%d/%m/%Y %H:%M:%S') if self.ultima_alteracao else '',
            'ativo': bool(self.ativo),
        }
        if include_nutrientes:
            data['nutrientes'] = [n.to_dict() for n in (self.nutrientes or [])]
        return data


class NutAlimentoNutriente(db.Model):
    """Nutriente do alimento (valores por 100g/100ml)."""
    __tablename__ = 'nut_alimento_nutrientes'

    id = db.Column(db.Integer, primary_key=True)
    alimento_id = db.Column(db.Integer, db.ForeignKey('nut_alimentos.id'), nullable=False, index=True)
    alimento = db.relationship('NutAlimento', back_populates='nutrientes')
    nutriente = db.Column(db.String(120), nullable=False)
    quantidade = db.Column(db.Float, default=0)
    unidade = db.Column(db.String(20), default='g')
    fator = db.Column(db.Float, default=1)

    def to_dict(self):
        return {
            'id': self.id,
            'alimento_id': self.alimento_id,
            'nutriente': self.nutriente,
            'quantidade': self.quantidade or 0,
            'unidade': self.unidade or 'g',
            'fator': self.fator or 1,
        }


class NutPratoLiquido(db.Model):
    """Prato do cadastro de dietas líquidas."""
    __tablename__ = 'nut_pratos_liquidos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False, unique=True)

    grupo_principal = db.Column(db.Boolean, default=False)
    grupo_sobremesa = db.Column(db.Boolean, default=False)
    grupo_outros = db.Column(db.Boolean, default=False)
    grupo_bebida = db.Column(db.Boolean, default=False)
    grupo_gelado = db.Column(db.Boolean, default=False)
    grupo_extra = db.Column(db.Boolean, default=False)

    fator_conv_tot = db.Column(db.Float, default=1)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_alteracao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'grupo_principal': bool(self.grupo_principal),
            'grupo_sobremesa': bool(self.grupo_sobremesa),
            'grupo_outros': bool(self.grupo_outros),
            'grupo_bebida': bool(self.grupo_bebida),
            'grupo_gelado': bool(self.grupo_gelado),
            'grupo_extra': bool(self.grupo_extra),
            'fator_conv_tot': self.fator_conv_tot if self.fator_conv_tot is not None else 1,
            'ativo': bool(self.ativo),
        }


class NutEstoqueLocal(db.Model):
    """Local de estoque (ex.: MATRIZ)."""
    __tablename__ = 'nut_estoques'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {'id': self.id, 'nome': self.nome, 'ativo': bool(self.ativo)}


class NutUnidadeMedida(db.Model):
    """Unidade de medida do cadastro de produtos."""
    __tablename__ = 'nut_unidades'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True)
    descricao = db.Column(db.String(120))
    unid_conversao = db.Column(db.String(20))
    valor_conversao = db.Column(db.Float, default=0)
    flag_nutrientes = db.Column(db.Boolean, default=True)
    flag_uma = db.Column(db.Boolean, default=True)
    flag_estoque = db.Column(db.Boolean, default=True)
    flag_pratos = db.Column(db.Boolean, default=True)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'codigo': self.codigo,
            'descricao': self.descricao or '',
            'unid_conversao': self.unid_conversao or '',
            'valor_conversao': self.valor_conversao or 0,
            'flag_nutrientes': bool(self.flag_nutrientes),
            'flag_uma': bool(self.flag_uma),
            'flag_estoque': bool(self.flag_estoque),
            'flag_pratos': bool(self.flag_pratos),
            'ativo': bool(self.ativo),
        }


class NutGrupoProduto(db.Model):
    """Grupo de produtos (ex.: BEBIDAS)."""
    __tablename__ = 'nut_grupos_produto'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    produtos = db.relationship('NutProduto', back_populates='grupo', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'ativo': bool(self.ativo),
            'qtd_produtos': self.produtos.filter_by(ativo=True).count() if self.produtos is not None else 0,
        }


class NutProduto(db.Model):
    """Produto do estoque / cadastro de produtos."""
    __tablename__ = 'nut_produtos'

    id = db.Column(db.Integer, primary_key=True)
    estoque_id = db.Column(db.Integer, db.ForeignKey('nut_estoques.id'), nullable=False, index=True)
    estoque = db.relationship('NutEstoqueLocal')
    grupo_id = db.Column(db.Integer, db.ForeignKey('nut_grupos_produto.id'), nullable=False, index=True)
    grupo = db.relationship('NutGrupoProduto', back_populates='produtos')

    codigo = db.Column(db.String(40), nullable=False, index=True)
    descricao = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.Float, default=0)
    unidade = db.Column(db.String(20), default='UN')
    preco_medio = db.Column(db.Float, default=0)
    ult_preco = db.Column(db.Float, default=0)
    quant_min = db.Column(db.Float, default=0)
    quant_max = db.Column(db.Float, default=0)
    quant_liq = db.Column(db.Float, default=0)
    un_liq = db.Column(db.String(20), default='NC')
    fc = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_alteracao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('estoque_id', 'codigo', name='uq_produto_estoque_codigo'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'estoque_id': self.estoque_id,
            'estoque': self.estoque.nome if self.estoque else '',
            'grupo_id': self.grupo_id,
            'grupo': self.grupo.nome if self.grupo else '',
            'codigo': self.codigo,
            'descricao': self.descricao,
            'quantidade': self.quantidade or 0,
            'unidade': self.unidade or 'UN',
            'preco_medio': self.preco_medio or 0,
            'ult_preco': self.ult_preco or 0,
            'quant_min': self.quant_min or 0,
            'quant_max': self.quant_max or 0,
            'quant_liq': self.quant_liq or 0,
            'un_liq': self.un_liq or 'NC',
            'fc': bool(self.fc),
            'ativo': bool(self.ativo),
        }


class NutFornecedor(db.Model):
    """Cadastro de fornecedores."""
    __tablename__ = 'nut_fornecedores'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    endereco = db.Column(db.String(255))
    bairro = db.Column(db.String(120))
    municipio = db.Column(db.String(120))
    cep = db.Column(db.String(20))
    estado = db.Column(db.String(2))
    cnpj = db.Column(db.String(20))
    inscricao_estadual = db.Column(db.String(40))
    telefone = db.Column(db.String(40))
    email = db.Column(db.String(160))
    faturamento_dias = db.Column(db.Integer, default=0)
    site = db.Column(db.String(200))
    observacao = db.Column(db.String(500))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_alteracao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome or '',
            'endereco': self.endereco or '',
            'bairro': self.bairro or '',
            'municipio': self.municipio or '',
            'cep': self.cep or '',
            'estado': self.estado or '',
            'cnpj': self.cnpj or '',
            'inscricao_estadual': self.inscricao_estadual or '',
            'telefone': self.telefone or '',
            'email': self.email or '',
            'faturamento_dias': self.faturamento_dias or 0,
            'site': self.site or '',
            'observacao': self.observacao or '',
            'ativo': bool(self.ativo),
            # compat estoque legado
            'contato': '',
        }


class NutEtiqueta(db.Model):
    """Configuração de etiqueta (folha)."""
    __tablename__ = 'nut_etiquetas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False, unique=True)
    ativa = db.Column(db.Boolean, default=True)

    # carta | a4 | outros
    tamanho_folha = db.Column(db.String(20), default='carta')
    folha_altura_mm = db.Column(db.Float, default=0)
    folha_largura_mm = db.Column(db.Float, default=0)
    # retrato | paisagem
    orientacao = db.Column(db.String(20), default='retrato')

    margem_esquerda = db.Column(db.Float, default=0)
    margem_direita = db.Column(db.Float, default=0)
    margem_superior = db.Column(db.Float, default=0)
    margem_inferior = db.Column(db.Float, default=0)

    num_colunas = db.Column(db.Integer, default=1)
    dist_colunas_mm = db.Column(db.Float, default=0)
    altura_etiqueta_mm = db.Column(db.Float, default=0)
    tamanho_fonte = db.Column(db.Integer, default=7)

    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_alteracao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campos = db.relationship(
        'NutEtiquetaCampo',
        back_populates='etiqueta',
        lazy='joined',
        cascade='all, delete-orphan',
        order_by='NutEtiquetaCampo.id',
    )

    def to_dict(self, include_campos=True):
        data = {
            'id': self.id,
            'nome': self.nome,
            'ativa': bool(self.ativa),
            'tamanho_folha': self.tamanho_folha or 'carta',
            'folha_altura_mm': self.folha_altura_mm or 0,
            'folha_largura_mm': self.folha_largura_mm or 0,
            'orientacao': self.orientacao or 'retrato',
            'margem_esquerda': self.margem_esquerda or 0,
            'margem_direita': self.margem_direita or 0,
            'margem_superior': self.margem_superior or 0,
            'margem_inferior': self.margem_inferior or 0,
            'num_colunas': self.num_colunas or 1,
            'dist_colunas_mm': self.dist_colunas_mm or 0,
            'altura_etiqueta_mm': self.altura_etiqueta_mm or 0,
            'tamanho_fonte': self.tamanho_fonte or 7,
        }
        if include_campos:
            data['campos'] = [c.to_dict() for c in (self.campos or [])]
        return data


class NutEtiquetaCampo(db.Model):
    """Campo da etiqueta (D=Dieta, F=Fórmula)."""
    __tablename__ = 'nut_etiqueta_campos'

    id = db.Column(db.Integer, primary_key=True)
    etiqueta_id = db.Column(db.Integer, db.ForeignKey('nut_etiquetas.id'), nullable=False, index=True)
    etiqueta = db.relationship('NutEtiqueta', back_populates='campos')
    tipo = db.Column(db.String(1), default='D')  # D | F
    nome = db.Column(db.String(120), nullable=False)
    texto = db.Column(db.String(255))

    def to_dict(self):
        return {
            'id': self.id,
            'etiqueta_id': self.etiqueta_id,
            'tipo': (self.tipo or 'D').upper()[:1],
            'nome': self.nome or '',
            'texto': self.texto or '',
        }


class NutPrecoRefeicao(db.Model):
    """Legado: catálogo plano dieta/item (não é o modelo principal de preços)."""
    __tablename__ = 'nut_precos_refeicoes'

    id = db.Column(db.Integer, primary_key=True)
    refeicao = db.Column(db.String(160), nullable=False, unique=True)
    grupo = db.Column(db.String(80), default='')
    valor = db.Column(db.Float, default=0)  # espelho de valor_empresa (compat)
    valor_empresa = db.Column(db.Float, default=0)
    valor_paciente = db.Column(db.Float, default=0)
    valor_acompanhante = db.Column(db.Float, default=0)
    ordem = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_alteracao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        emp = float(self.valor_empresa if self.valor_empresa is not None else (self.valor or 0))
        pac = float(self.valor_paciente or 0)
        aco = float(self.valor_acompanhante or 0)
        return {
            'id': self.id,
            'refeicao': self.refeicao or '',
            'grupo': self.grupo or '',
            'valor': emp,
            'valor_empresa': emp,
            'valor_paciente': pac,
            'valor_acompanhante': aco,
            'total': round(emp + pac + aco, 2),
            'ordem': int(self.ordem or 0),
            'ativo': bool(self.ativo),
        }


class NutTipoRefeicao(db.Model):
    """Tipo de refeição do dia (Desjejum, Colação, Almoço, …)."""
    __tablename__ = 'nut_tipos_refeicao'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)
    sigla = db.Column(db.String(10), nullable=False, unique=True)
    ordem = db.Column(db.Integer, default=0)
    hora_limite = db.Column(db.String(5), default='')  # HH:MM
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome or '',
            'sigla': self.sigla or '',
            'ordem': int(self.ordem or 0),
            'hora_limite': (self.hora_limite or '')[:5],
            'ativo': bool(self.ativo),
        }


class NutPrecoDietaTipo(db.Model):
    """Preço por combinação Dieta × Tipo de Refeição (Empresa / Paciente / Acompanhante)."""
    __tablename__ = 'nut_precos_dieta_tipo'

    id = db.Column(db.Integer, primary_key=True)
    dieta_id = db.Column(db.Integer, db.ForeignKey('nut_dietas.id'), nullable=False, index=True)
    tipo_refeicao_id = db.Column(db.Integer, db.ForeignKey('nut_tipos_refeicao.id'), nullable=False, index=True)
    dieta = db.relationship('NutDieta', lazy='joined')
    tipo_refeicao = db.relationship('NutTipoRefeicao', lazy='joined')
    valor_empresa = db.Column(db.Float, default=0)
    valor_paciente = db.Column(db.Float, default=0)
    valor_acompanhante = db.Column(db.Float, default=0)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_alteracao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('dieta_id', 'tipo_refeicao_id', name='uq_preco_dieta_tipo'),
    )

    def to_dict(self):
        emp = float(self.valor_empresa or 0)
        pac = float(self.valor_paciente or 0)
        aco = float(self.valor_acompanhante or 0)
        dieta = self.dieta
        tipo = self.tipo_refeicao
        return {
            'id': self.id,
            'dieta_id': self.dieta_id,
            'dieta': dieta.nome if dieta else '',
            'dieta_categoria': (dieta.categoria if dieta else '') or 'basica',
            'tipo_refeicao_id': self.tipo_refeicao_id,
            'tipo': tipo.nome if tipo else '',
            'tipo_sigla': tipo.sigla if tipo else '',
            'tipo_ordem': int(tipo.ordem or 0) if tipo else 0,
            'valor_empresa': emp,
            'valor_paciente': pac,
            'valor_acompanhante': aco,
            'valor': emp,
            'total': round(emp + pac + aco, 2),
        }
