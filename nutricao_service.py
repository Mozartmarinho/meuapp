"""Seed inicial e helpers do módulo de nutrição."""
from datetime import date, datetime, timedelta
from models import db
from models_nutricao import (
    NutClinica, NutEnfermaria, NutLeito, NutDieta, NutGrupoDieta, NutPaciente, NutMapaRefeicao, NutCardapio,
    NutTabelaNutrientes, NutAlimento, NutAlimentoNutriente, NutPratoLiquido,
    NutEstoqueLocal, NutUnidadeMedida, NutGrupoProduto, NutProduto, NutFornecedor,
    NutEtiqueta, NutEtiquetaCampo, NutPrecoRefeicao, NutTipoRefeicao, NutPrecoDietaTipo,
)
from nutricao_seed_enfermarias import ENFERMARIAS_SEED, VINCULOS_CLINICA_ENFERMARIA_SEED
from nutricao_seed_dietas import (
    DIETAS_SEED,
    DIETAS_PRECOS_SEED,
    DIETAS_CATALOGO_FOTO,
    DIETAS_CATALOGO_PRECOS,
    DIETAS_CATALOGO_LACTARIO,
    DIETAS_LACTARIO_NOMES,
    DIETAS_PRECOS_POR_NOME,
    DIETAS_ALIAS_PARA_FOTO,
    TIPOS_PRECO_ORDEM,
    P_ORAL,
    GRUPO_POR_PAYER,
    GRUPOS_DIETA_SEED,
    precos_dict_da_tupla,
)
from nutricao_seed_cardapios import CARDAPIOS_SEED, CARDAPIO_OPCOES
from nutricao_seed_nutricional import ALIMENTOS_SEED, NUTRIENTES_PADRAO
from nutricao_seed_pratos_liquidos import PRATOS_LIQUIDOS_SEED
from nutricao_seed_produtos import (
    ESTOQUES_SEED, UNIDADES_SEED, GRUPOS_PRODUTO_SEED, PRODUTOS_SEED,
)
from nutricao_seed_fornecedores import FORNECEDORES_SEED, ESTADOS_BR
from nutricao_seed_etiquetas import ETIQUETAS_SEED


# Cadastro de Clínicas (legado "Grupo") — nome, ativo
CLINICAS_SEED = [
    ('3º CM + VASCULAR', True),
    ('4º/5º MATERNIDADE', False),
    ('BRONCO OFTALMO', False),
    ('CABEÇA E PESCOÇO', True),
    ('CARDIO', False),
    ('CARDIO + UC', True),
    ('CARDIOLOGIA', True),
    ('CETIP + CIPE + PEDIATRIA', True),
    ('CIR. A1', False),
    ('CIR. A2', False),
    ('CIRURGIA A1', False),
    ('CIRURGIA A2', False),
    ('CIRURGIA B + NEURO', False),
    ('CIRURGIA G. A', False),
    ('CIRURGIA GERAL A', True),
    ('CIRURGIA GERAL B', True),
    ('CIRURGIA PEDIATRICA', False),
    ('CLÍNICA MÉDICA A', True),
    ('CLÍNICA MÉDICA B', True),
    ('CLÍNICA MÉDICA C', True),
    ('CRECHE', False),
    ('CTI - 1', True),
    ('CTI - 2', True),
    ('CTI + ORTO + VASC', False),
    ('CTI 1 + CTI 2 (FATURAMENTO)', True),
    ('CTI PED (PRÉDIO 1)', False),
    ('CTI PEDIÁTRICO', False),
    ('CTI TOTALIZAÇÃO', False),
    ('CTI2', False),
    ('DP + UTR', True),
    ('EMERG. (FATURAMENTO)', True),
    ('EMERGÊNCIA (MASC. E FEM.)', True),
    ('EMERGÊNCIA 1', False),
    ('EMERGÊNCIA 2', True),
    ('EMERGÊNCIA CORREDOR', True),
    ('EMERGÊNCIA CURTA PERMANÊNCIA', True),
    ('EMERGÊNCIA MASCULINA', False),
    ('ENTERAL', False),
    ('ENTERAL A', False),
    ('ENTERAL B', False),
    ('GINECO', True),
    ('HEMODIÁLISE', False),
    ('HOSPITAL DIA', True),
    ('MATERNIDADE', False),
    ('MATERNIDADE A', False),
    ('MATERNIDADE ALA A', True),
    ('MATERNIDADE ALA A + B', True),
    ('MATERNIDADE ALA B', False),
    ('MATERNIDADE B', True),
    ('MATERNIDADE LACTÁRIO', False),
    ('MATERNIDADE/SALA DE PARTO', False),
    ('NEFRO', True),
    ('NEFRO + UTR + DP', True),
    ('NEFRO+DP+UTR+CTI (FATURAMENTO)', False),
    ('NEURO', True),
    ('OFTALMO + OTORRINO + PLÁSTICA', True),
    ('OFTALMO+OTORRINO+PLÁSTICA', True),
    ('ONCO', True),
    ('ORTOPEDIA', True),
    ('OTORRINO', False),
    ('PED + CTI PED', True),
    ('PEDIATRIA + CIR. INFANTIL', False),
    ('PEDIATRIA ALA B', False),
    ('PEDIATRIA C/ CIRURGIA', False),
    ('PEDIATRIA S/ CIRURGIA', False),
    ('PÓS OP.', False),
    ('PU', False),
    ('PU (T.C.)', False),
    ('PU PED (T.C.)', False),
    ('PU PED-UPG', False),
    ('SALA DE ESTABILIZAÇÃO', True),
    ('SALA DE RECUPERAÇÃO ANESTÉSICA', True),
    ('TESTE', False),
    ('TODOS', True),
    ('UCO', True),
    ('UI NEO', True),
    ('UROLOGIA', True),
    ('USE', True),
    ('USE (FEM E MASC)', False),
    ('USE (TOT)', False),
    ('UTI NEO NATAL', True),
    ('UTO + UC', False),
    ('VASCULAR', True),
    ('VASCULAR + ONCO', False),
]


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return None


def list_dietas(somente_ativas=False):
    q = NutDieta.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [
        d.to_dict()
        for d in q.order_by(NutDieta.grupo, NutDieta.nome).all()
    ]


def list_grupos_dieta(somente_ativos=False):
    q = NutGrupoDieta.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [
        g.to_dict()
        for g in q.order_by(NutGrupoDieta.ordem, NutGrupoDieta.nome).all()
    ]


def _seed_grupos_dieta():
    """Garante grupos de dieta padrão + valores já usados em NutDieta.grupo."""
    nomes_seed = []
    for item in GRUPOS_DIETA_SEED:
        if isinstance(item, (list, tuple)):
            nome = (item[0] or '').strip().upper()
            try:
                ordem = int(item[1] if len(item) > 1 else 0)
            except (TypeError, ValueError):
                ordem = 0
        else:
            nome = (item or '').strip().upper()
            ordem = 0
        if nome:
            nomes_seed.append((nome, ordem))

    for nome, ordem in nomes_seed:
        row = NutGrupoDieta.query.filter(
            db.func.upper(NutGrupoDieta.nome) == nome
        ).first()
        if not row:
            db.session.add(NutGrupoDieta(nome=nome, ordem=ordem or 0, ativo=True))
        elif ordem and not (row.ordem or 0):
            row.ordem = ordem

    # Absorve grupos já gravados nas dietas (idempotente)
    existentes = (
        db.session.query(NutDieta.grupo)
        .filter(NutDieta.grupo.isnot(None), NutDieta.grupo != '')
        .distinct()
        .all()
    )
    last = NutGrupoDieta.query.order_by(NutGrupoDieta.ordem.desc()).first()
    next_ordem = ((last.ordem or 0) + 10) if last else 110
    for (grupo,) in existentes:
        nome = (grupo or '').strip().upper()
        if not nome:
            continue
        if NutGrupoDieta.query.filter(db.func.upper(NutGrupoDieta.nome) == nome).first():
            continue
        db.session.add(NutGrupoDieta(nome=nome, ordem=next_ordem, ativo=True))
        next_ordem += 10
    db.session.flush()


def list_tipos_refeicao(somente_ativos=False):
    q = NutTipoRefeicao.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [t.to_dict() for t in q.order_by(NutTipoRefeicao.ordem, NutTipoRefeicao.id).all()]


def list_clinicas(somente_ativas=False):
    q = NutClinica.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [c.to_dict() for c in q.order_by(NutClinica.nome).all()]


def list_enfermarias(somente_ativas=False):
    from sqlalchemy import func
    q = NutEnfermaria.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    rows = q.order_by(NutEnfermaria.nome).all()
    counts = dict(
        db.session.query(NutLeito.enfermaria_id, func.count(NutLeito.id))
        .group_by(NutLeito.enfermaria_id)
        .all()
    )
    return [e.to_dict(num_leitos=counts.get(e.id, 0)) for e in rows]


def list_leitos(enfermaria_id=None, somente_ativos=False):
    q = NutLeito.query
    if enfermaria_id:
        q = q.filter_by(enfermaria_id=enfermaria_id)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [l.to_dict() for l in q.order_by(NutLeito.numero, NutLeito.nome).all()]


def _ensure_nutricao_columns():
    """Adiciona colunas novas em tabelas já existentes (create_all não altera)."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'nut_enfermarias' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_enfermarias')}
            if 'nutriz' not in cols:
                db.session.execute(text('ALTER TABLE nut_enfermarias ADD COLUMN nutriz BOOLEAN DEFAULT 0'))
                db.session.commit()
        if 'nut_mapa_refeicoes' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_mapa_refeicoes')}
            alteracoes = {
                'obs_etiqueta': 'TEXT',
                'extras': 'TEXT',
                'suplementos': 'TEXT',
                'enteral': 'TEXT',
                'formula_infantil': 'TEXT',
                'lve': 'TEXT',
                'substituicoes': 'TEXT',
                'data_inclusao': 'DATETIME',
                'enfermaria': 'VARCHAR(120)',
                'usuario_alteracao': 'VARCHAR(80)',
                'motivo_saida': 'VARCHAR(40)',
                'hospital_transferencia': 'VARCHAR(200)',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE nut_mapa_refeicoes ADD COLUMN {col} {tipo}'))
            db.session.commit()
        if 'nut_pacientes' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_pacientes')}
            if 'hora_saida' not in cols:
                db.session.execute(text("ALTER TABLE nut_pacientes ADD COLUMN hora_saida VARCHAR(20)"))
            if 'motivo_saida' not in cols:
                db.session.execute(text("ALTER TABLE nut_pacientes ADD COLUMN motivo_saida VARCHAR(40)"))
            db.session.commit()
        if 'nut_produtos' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_produtos')}
            alteracoes = {
                'codigo': 'VARCHAR(40)',
                'descricao': 'VARCHAR(200)',
                'quantidade': 'FLOAT DEFAULT 0',
                'unidade': "VARCHAR(20) DEFAULT 'UN'",
                'preco_medio': 'FLOAT DEFAULT 0',
                'ult_preco': 'FLOAT DEFAULT 0',
                'quant_min': 'FLOAT DEFAULT 0',
                'quant_max': 'FLOAT DEFAULT 0',
                'quant_liq': 'FLOAT DEFAULT 0',
                'un_liq': "VARCHAR(20) DEFAULT 'NC'",
                'fc': 'BOOLEAN DEFAULT 0',
                'ativo': 'BOOLEAN DEFAULT 1',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE nut_produtos ADD COLUMN {col} {tipo}'))
            db.session.commit()
        if 'nut_grupos_produto' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_grupos_produto')}
            if 'ativo' not in cols:
                db.session.execute(text('ALTER TABLE nut_grupos_produto ADD COLUMN ativo BOOLEAN DEFAULT 1'))
                db.session.commit()
        if 'nut_unidades' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_unidades')}
            alteracoes = {
                'unid_conversao': 'VARCHAR(20)',
                'valor_conversao': 'FLOAT DEFAULT 0',
                'flag_nutrientes': 'BOOLEAN DEFAULT 1',
                'flag_uma': 'BOOLEAN DEFAULT 1',
                'flag_estoque': 'BOOLEAN DEFAULT 1',
                'flag_pratos': 'BOOLEAN DEFAULT 1',
                'ativo': 'BOOLEAN DEFAULT 1',
                'descricao': 'VARCHAR(120)',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE nut_unidades ADD COLUMN {col} {tipo}'))
            db.session.commit()
        if 'nut_fornecedores' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_fornecedores')}
            alteracoes = {
                'endereco': 'VARCHAR(255)',
                'bairro': 'VARCHAR(120)',
                'municipio': 'VARCHAR(120)',
                'cep': 'VARCHAR(20)',
                'estado': 'VARCHAR(2)',
                'cnpj': 'VARCHAR(20)',
                'inscricao_estadual': 'VARCHAR(40)',
                'telefone': 'VARCHAR(40)',
                'email': 'VARCHAR(160)',
                'faturamento_dias': 'INTEGER DEFAULT 0',
                'site': 'VARCHAR(200)',
                'observacao': 'VARCHAR(500)',
                'ativo': 'BOOLEAN DEFAULT 1',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE nut_fornecedores ADD COLUMN {col} {tipo}'))
            db.session.commit()
        if 'nut_precos_refeicoes' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_precos_refeicoes')}
            alteracoes = {
                'grupo': "VARCHAR(80) DEFAULT ''",
                'valor_empresa': 'FLOAT DEFAULT 0',
                'valor_paciente': 'FLOAT DEFAULT 0',
                'valor_acompanhante': 'FLOAT DEFAULT 0',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE nut_precos_refeicoes ADD COLUMN {col} {tipo}'))
            db.session.commit()
        if 'nut_dietas' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_dietas')}
            if 'grupo' not in cols:
                db.session.execute(text("ALTER TABLE nut_dietas ADD COLUMN grupo VARCHAR(80) NULL"))
                db.session.commit()
                insp.clear_cache()
        if 'nut_tipos_refeicao' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_tipos_refeicao')}
            if 'hora_limite' not in cols:
                db.session.execute(text("ALTER TABLE nut_tipos_refeicao ADD COLUMN hora_limite VARCHAR(5) NULL"))
                db.session.commit()
                insp.clear_cache()
        if 'nut_cardapios' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_cardapios')}
            if 'dieta_id' not in cols:
                db.session.execute(text('ALTER TABLE nut_cardapios ADD COLUMN dieta_id INTEGER NULL'))
                db.session.commit()
                insp.clear_cache()
        if 'nut_alimentos' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_alimentos')}
            if 'fdc_id' not in cols:
                db.session.execute(text('ALTER TABLE nut_alimentos ADD COLUMN fdc_id INTEGER NULL'))
                db.session.commit()
                insp.clear_cache()
            try:
                db.session.execute(text(
                    'CREATE UNIQUE INDEX uq_nut_alimento_tabela_fdc '
                    'ON nut_alimentos (tabela_id, fdc_id)'
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception:
        db.session.rollback()

    # Retries isolados (falha em ALTER anterior não pode bloquear estas colunas)
    for table, col, ddl in (
        ('nut_dietas', 'grupo', "ALTER TABLE nut_dietas ADD COLUMN grupo VARCHAR(80) NULL"),
        ('nut_tipos_refeicao', 'hora_limite', "ALTER TABLE nut_tipos_refeicao ADD COLUMN hora_limite VARCHAR(5) NULL"),
        ('nut_cardapios', 'dieta_id', 'ALTER TABLE nut_cardapios ADD COLUMN dieta_id INTEGER NULL'),
        ('nut_alimentos', 'fdc_id', 'ALTER TABLE nut_alimentos ADD COLUMN fdc_id INTEGER NULL'),
    ):
        try:
            insp = inspect(db.engine)
            insp.clear_cache()
            if table not in set(insp.get_table_names()):
                continue
            cols = {c['name'] for c in insp.get_columns(table)}
            if col not in cols:
                db.session.execute(text(ddl))
                db.session.commit()
                insp.clear_cache()
        except Exception:
            db.session.rollback()

    _backfill_cardapio_dieta_id()


def _backfill_cardapio_dieta_id():
    """Preenche dieta_id a partir do nome denormalizado (idempotente)."""
    def _n(s):
        return ' '.join(str(s or '').strip().upper().split())
    try:
        from sqlalchemy import inspect
        insp = inspect(db.engine)
        if 'nut_cardapios' not in set(insp.get_table_names()):
            return
        cols = {c['name'] for c in insp.get_columns('nut_cardapios')}
        if 'dieta_id' not in cols:
            return
        dietas = { _n(d.nome): d.id for d in NutDieta.query.all() if d.nome }
        if not dietas:
            return
        changed = False
        for row in NutCardapio.query.filter(
            NutCardapio.dieta_id.is_(None),
            NutCardapio.dieta.isnot(None),
        ).all():
            did = dietas.get(_n(row.dieta))
            if did:
                row.dieta_id = did
                changed = True
        if changed:
            db.session.commit()
    except Exception:
        db.session.rollback()


def _seed_enfermarias():
    for nome in ENFERMARIAS_SEED:
        nome = (nome or '').strip()
        if not nome:
            continue
        if not NutEnfermaria.query.filter_by(nome=nome).first():
            db.session.add(NutEnfermaria(nome=nome, ativo=True, nutriz=False))
    db.session.flush()

    # vínculos iniciais só se a clínica ainda não tiver nenhuma enfermaria
    for clinica_nome, nomes in VINCULOS_CLINICA_ENFERMARIA_SEED.items():
        clinica = NutClinica.query.filter_by(nome=clinica_nome).first()
        if not clinica:
            continue
        if clinica.enfermarias:
            continue
        for nome_enf in nomes:
            enf = NutEnfermaria.query.filter_by(nome=nome_enf).first()
            if enf and enf not in clinica.enfermarias:
                clinica.enfermarias.append(enf)


def list_cardapios(tipo=None, dieta_id=None):
    q = NutCardapio.query.filter_by(ativo=True)
    if tipo:
        q = q.filter_by(tipo=tipo)
    if dieta_id:
        q = q.filter_by(dieta_id=int(dieta_id))
    return [
        c.to_dict()
        for c in q.order_by(NutCardapio.dia_mes, NutCardapio.dieta, NutCardapio.id).all()
    ]


MEALS_SUBST = (
    'desjejum', 'colacao', 'almoco', 'merenda', 'jantar', 'ceia'
)
MEAL_HR_FIELD = {
    'desjejum': 'hr_desjejum',
    'colacao': 'hr_colacao',
    'almoco': 'hr_almoco',
    'merenda': 'hr_merenda',
    'jantar': 'hr_jantar',
    'ceia': 'hr_ceia',
}
MEAL_LABELS = {
    'desjejum': 'Desjejum',
    'colacao': 'Colação',
    'almoco': 'Almoço',
    'merenda': 'Merenda',
    'jantar': 'Jantar',
    'ceia': 'Ceia',
}
_ITENS_ORDEM = {
    'grandes': [
        'acompanhamento', 'prato_base', 'proteina_opcional', 'proteico_opcional',
        'guarnicao', 'docinho_salada', 'diversos_salada', 'sobremesa', 'fruta',
        'suco', 'vitamina_suco', 'entrada_sopa', 'bebida', 'molhos', 'outros',
    ],
    'pequenas': [
        'bebida', 'prato1', 'prato2', 'prato3', 'prato4', 'prato5', 'prato6', 'prato7', 'sobremesa',
    ],
    'liquidas': [
        'principal', 'bebida', 'sobremesa', 'gelado', 'outros',
    ],
}
_ITENS_SKIP = {
    'entrada_tipo', 'proteico_tipo', 'proteina_tipo',
    'conv_bebida_coluna', 'conv_bebida_quant',
    'conv_gelado_coluna', 'conv_gelado_quant',
}


def _norm_txt(s):
    return ' '.join(str(s or '').strip().upper().split())


def _dieta_match_score(paciente_dieta, cardapio_dieta):
    p = _norm_txt(paciente_dieta)
    c = _norm_txt(cardapio_dieta)
    if not p or not c:
        return 0
    if p == c:
        return 100
    if p.startswith(c + ' ') or c.startswith(p + ' '):
        return 85
    if p.startswith(c) or c.startswith(p):
        return 75
    pt, ct = set(p.split()), set(c.split())
    if not ct:
        return 0
    overlap = len(pt & ct) / len(ct)
    if overlap >= 0.6:
        return int(50 + overlap * 20)
    return 0


def pratos_from_itens(itens, tipo=None):
    """Extrai lista ordenada de pratos a partir do JSON de itens do cardápio."""
    itens = itens or {}
    if not isinstance(itens, dict):
        return []
    ordem = list(_ITENS_ORDEM.get(tipo or '', []))
    for k in itens.keys():
        if k not in ordem and k not in _ITENS_SKIP and not str(k).startswith('conv_'):
            ordem.append(k)
    seen = set()
    out = []
    for key in ordem:
        if key in _ITENS_SKIP or str(key).endswith('_tipo'):
            continue
        val = itens.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if not text:
            continue
        up = _norm_txt(text)
        if up in seen:
            continue
        # ignora rótulos de tipo (Salada/Sopa/Aves...)
        if key.endswith('_tipo'):
            continue
        seen.add(up)
        out.append(text)
    return out


def normalize_substituicoes(raw):
    """Normaliza JSON de substituições para as 6 refeições."""
    data = raw if isinstance(raw, dict) else {}
    out = {}
    for meal in MEALS_SUBST:
        bloco = data.get(meal) or {}
        if not isinstance(bloco, dict):
            bloco = {}
        pares_in = bloco.get('pares') or []
        pares = []
        if isinstance(pares_in, list):
            for p in pares_in:
                if not isinstance(p, dict):
                    continue
                rem = str(p.get('remover') or '').strip()
                add = str(p.get('adicionar') or '').strip()
                if rem or add:
                    pares.append({'remover': rem, 'adicionar': add})
        out[meal] = {
            'pares': pares,
            'justificativa': str(bloco.get('justificativa') or '').strip(),
        }
    return out


def cardapio_personalizado(pratos_padrao, pares):
    """Aplica Remover/Adicionar sobre o cardápio padrão."""
    rem_set = {_norm_txt(p.get('remover')) for p in (pares or []) if (p.get('remover') or '').strip()}
    result = [p for p in (pratos_padrao or []) if _norm_txt(p) not in rem_set]
    for p in (pares or []):
        add = str(p.get('adicionar') or '').strip()
        if add and _norm_txt(add) not in {_norm_txt(x) for x in result}:
            result.append(add)
    return result


def find_cardapio_for_meal(dieta, meal, data_ref=None, dieta_id=None):
    """Melhor NutCardapio para dieta + horário (opcionalmente dia do mês).

    Preferência por dieta_id (FK) quando disponível — alinha com join futuro
    em NutPrecoDietaTipo (dieta × tipo_refeicao / hr_*).
    """
    hr = MEAL_HR_FIELD.get(meal)
    if not hr:
        return None
    dia = data_ref.day if data_ref else None
    q = NutCardapio.query.filter_by(ativo=True).filter(getattr(NutCardapio, hr).is_(True))
    candidatos = []
    for row in q.all():
        if dieta_id and row.dieta_id and int(row.dieta_id) == int(dieta_id):
            score = 110
        else:
            score = _dieta_match_score(dieta, row.dieta)
        if score <= 0:
            continue
        dia_bonus = 10 if (dia and row.dia_mes == dia) else 0
        candidatos.append((score + dia_bonus, score, row))
    if not candidatos:
        # fallback: qualquer cardápio do horário, priorizando dia
        for row in NutCardapio.query.filter_by(ativo=True).filter(getattr(NutCardapio, hr).is_(True)).all():
            dia_bonus = 10 if (dia and row.dia_mes == dia) else 0
            candidatos.append((dia_bonus, 0, row))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: (x[0], x[1], -(x[2].id or 0)), reverse=True)
    return candidatos[0][2]


def get_mapa_substituicoes(mapa_row):
    """Monta payload completo do diálogo Substituições para uma linha do mapa."""
    dieta = (mapa_row.dieta or '').strip()
    data_ref = mapa_row.data_refeicao
    subs = normalize_substituicoes(mapa_row.get_substituicoes())
    refeicoes = {}
    for meal in MEALS_SUBST:
        card = find_cardapio_for_meal(dieta, meal, data_ref)
        pratos = pratos_from_itens(card.get_itens() if card else {}, card.tipo if card else None)
        pares = subs[meal]['pares']
        refeicoes[meal] = {
            'label': MEAL_LABELS[meal],
            'cardapio_id': card.id if card else None,
            'cardapio_dieta': (card.dieta if card else '') or '',
            'cardapio_tipo': (card.tipo if card else '') or '',
            'pratos': pratos,
            'pares': pares,
            'justificativa': subs[meal]['justificativa'],
            'cardapio_personalizado': cardapio_personalizado(pratos, pares),
        }
    local = '/'.join(
        x for x in [(mapa_row.clinica or '').strip(), (mapa_row.enfermaria or '').strip()] if x
    )
    leito = (mapa_row.leito or '').strip()
    local_leito = f'{local}-{leito}' if local and leito else (local or leito)
    header = ' :: '.join(
        x for x in [
            data_ref.strftime('%d/%m/%Y') if data_ref else '',
            local_leito,
            (mapa_row.prontuario or '').strip(),
            (mapa_row.nome or '').strip(),
        ] if x
    )
    return {
        'ok': True,
        'mapa_id': mapa_row.id,
        'header': header,
        'dieta': dieta,
        'data_refeicao': data_ref.isoformat() if data_ref else '',
        'paciente_id': mapa_row.paciente_id,
        'refeicoes': refeicoes,
        'substituicoes': subs,
    }


def save_mapa_substituicoes(mapa_row, payload, usuario=None):
    """Persiste substituições (todas as refeições ou merge parcial)."""
    atual = normalize_substituicoes(mapa_row.get_substituicoes())
    incoming = None
    if isinstance(payload, dict):
        if isinstance(payload.get('substituicoes'), dict):
            incoming = payload['substituicoes']
        elif any(k in payload for k in MEALS_SUBST):
            incoming = {k: payload[k] for k in MEALS_SUBST if k in payload}
        elif payload.get('meal'):
            meal = str(payload.get('meal')).strip().lower()
            if meal in MEALS_SUBST:
                incoming = {meal: {
                    'pares': payload.get('pares') or [],
                    'justificativa': payload.get('justificativa') or '',
                }}
    if not isinstance(incoming, dict):
        incoming = {}
    merged = {k: dict(v) for k, v in atual.items()}
    for meal in MEALS_SUBST:
        if meal not in incoming or not isinstance(incoming[meal], dict):
            continue
        bloco = incoming[meal]
        norm = normalize_substituicoes({meal: bloco})[meal]
        if 'pares' in bloco:
            merged[meal]['pares'] = norm['pares']
        if 'justificativa' in bloco:
            merged[meal]['justificativa'] = norm['justificativa']
    mapa_row.set_substituicoes(merged)
    marcar_alteracao_mapa(mapa_row, usuario=usuario)
    return merged


def importar_substituicoes_anteriores(mapa_row, meal=None, so_justificativa=False):
    """Copia pares/justificativa do mapa anterior do mesmo paciente."""
    if not mapa_row.paciente_id and not (mapa_row.prontuario or '').strip():
        return None
    q = NutMapaRefeicao.query.filter(
        NutMapaRefeicao.id != mapa_row.id,
        NutMapaRefeicao.ativo.is_(True),
        NutMapaRefeicao.data_refeicao < (mapa_row.data_refeicao or date.today()),
    )
    if mapa_row.paciente_id:
        q = q.filter(NutMapaRefeicao.paciente_id == mapa_row.paciente_id)
    else:
        q = q.filter(NutMapaRefeicao.prontuario == mapa_row.prontuario)
    prev = q.order_by(NutMapaRefeicao.data_refeicao.desc(), NutMapaRefeicao.id.desc()).first()
    if not prev:
        return None
    prev_subs = normalize_substituicoes(prev.get_substituicoes())
    atual = normalize_substituicoes(mapa_row.get_substituicoes())
    meals = [meal] if meal in MEALS_SUBST else list(MEALS_SUBST)
    for m in meals:
        if so_justificativa:
            atual[m]['justificativa'] = prev_subs[m]['justificativa']
        else:
            atual[m]['pares'] = list(prev_subs[m]['pares'])
    mapa_row.set_substituicoes(atual)
    return atual


def _cardapio_seed_signature(item):
    hrs = tuple(bool(item.get(f'hr_{m}')) for m in MEALS_SUBST)
    return (
        (item.get('tipo') or '').strip().lower(),
        _norm_txt(item.get('dieta')),
        int(item.get('dia_mes') or 1),
        hrs,
    )


def _seed_cardapios():
    dietas_by_nome = { _norm_txt(d.nome): d.id for d in NutDieta.query.all() if d.nome }
    existentes = {
        (
            (c.tipo or '').strip().lower(),
            _norm_txt(c.dieta),
            int(c.dia_mes or 1),
            tuple(bool(getattr(c, f'hr_{m}')) for m in MEALS_SUBST),
        )
        for c in NutCardapio.query.all()
    }
    for item in CARDAPIOS_SEED:
        sig = _cardapio_seed_signature(item)
        if sig in existentes:
            continue
        dieta_nome = item.get('dieta', '') or ''
        row = NutCardapio(
            tipo=item['tipo'],
            grupo_cardapio=item.get('grupo_cardapio', 'PRINCIPAL'),
            dia_mes=item.get('dia_mes', 1),
            dia_semana=item.get('dia_semana', ''),
            dieta=dieta_nome,
            dieta_id=dietas_by_nome.get(_norm_txt(dieta_nome)),
            hr_desjejum=bool(item.get('hr_desjejum')),
            hr_colacao=bool(item.get('hr_colacao')),
            hr_almoco=bool(item.get('hr_almoco')),
            hr_merenda=bool(item.get('hr_merenda')),
            hr_jantar=bool(item.get('hr_jantar')),
            hr_ceia=bool(item.get('hr_ceia')),
            vet=float(item.get('vet') or 0),
            custo=float(item.get('custo') or 0),
            organizar_por=item.get('organizar_por', 'Ord, Dieta, Horário'),
            usuario_alteracao=item.get('usuario_alteracao', 'sistema'),
            data_alteracao=datetime(2026, 1, 5, 11, 43, 16),
            ativo=True,
        )
        row.set_itens(item.get('itens') or {})
        db.session.add(row)
        existentes.add(sig)


def list_tabelas_nutrientes(somente_ativas=True):
    q = NutTabelaNutrientes.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [t.to_dict() for t in q.order_by(NutTabelaNutrientes.nome).all()]


def list_alimentos(tabela_id=None, somente_ativas=True, include_nutrientes=True):
    q = NutAlimento.query
    if tabela_id:
        q = q.filter_by(tabela_id=tabela_id)
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [
        a.to_dict(include_nutrientes=include_nutrientes)
        for a in q.order_by(NutAlimento.nome, NutAlimento.id).all()
    ]


def import_tabela_fdc(source, **kwargs):
    """Proxy para import USDA FDC Foundation Foods (zip/json path ou file-like)."""
    from nutricao_fdc_import import import_fdc_foundation_foods
    return import_fdc_foundation_foods(source, **kwargs)


def _seed_nutricional():
    if NutTabelaNutrientes.query.count() > 0:
        return
    tabelas = {}
    for item in ALIMENTOS_SEED:
        nome_tab = (item.get('tabela') or 'Tabela Padrão').strip()
        if nome_tab not in tabelas:
            tab = NutTabelaNutrientes(nome=nome_tab, ativo=True)
            db.session.add(tab)
            db.session.flush()
            tabelas[nome_tab] = tab
        tab = tabelas[nome_tab]
        alim = NutAlimento(
            tabela_id=tab.id,
            nome=(item.get('nome') or '').strip().upper(),
            cal_carboidratos=float(item.get('cal_carboidratos') or 0),
            cal_gordura=float(item.get('cal_gordura') or 0),
            cal_proteina=float(item.get('cal_proteina') or 0),
            cal_total=float(item.get('cal_total') or 0),
            qtd_carboidratos=float(item.get('qtd_carboidratos') or 0),
            qtd_gordura=float(item.get('qtd_gordura') or 0),
            qtd_proteina=float(item.get('qtd_proteina') or 0),
            ref_consumo=item.get('ref_consumo') or '',
            coeficiente_npu=float(item.get('coeficiente_npu') or 0),
            gluten=bool(item.get('gluten')),
            fenilalanina=bool(item.get('fenilalanina')),
            ativo=True,
        )
        db.session.add(alim)
        db.session.flush()
        nuts = item.get('nutrientes') or []
        if not nuts:
            nuts = [(n, 0, u, f) for n, u, f in NUTRIENTES_PADRAO]
        for nome_n, qtd, un, fator in nuts:
            db.session.add(NutAlimentoNutriente(
                alimento_id=alim.id,
                nutriente=nome_n,
                quantidade=float(qtd or 0),
                unidade=un or 'g',
                fator=float(fator or 1),
            ))


def list_pratos_liquidos(somente_ativos=True):
    q = NutPratoLiquido.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [p.to_dict() for p in q.order_by(NutPratoLiquido.nome, NutPratoLiquido.id).all()]


def _seed_pratos_liquidos():
    if NutPratoLiquido.query.count() > 0:
        return
    for (
        nome, principal, sobremesa, outros, bebida, gelado, extra, fator, ativo
    ) in PRATOS_LIQUIDOS_SEED:
        db.session.add(NutPratoLiquido(
            nome=(nome or '').strip().upper(),
            grupo_principal=bool(principal),
            grupo_sobremesa=bool(sobremesa),
            grupo_outros=bool(outros),
            grupo_bebida=bool(bebida),
            grupo_gelado=bool(gelado),
            grupo_extra=bool(extra),
            fator_conv_tot=float(fator or 1),
            ativo=bool(ativo),
        ))


def list_estoques(somente_ativos=True):
    q = NutEstoqueLocal.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [e.to_dict() for e in q.order_by(NutEstoqueLocal.nome).all()]


def list_unidades(somente_ativas=True):
    q = NutUnidadeMedida.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [u.to_dict() for u in q.order_by(NutUnidadeMedida.codigo).all()]


def list_grupos_produto(somente_ativos=True):
    q = NutGrupoProduto.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [g.to_dict() for g in q.order_by(NutGrupoProduto.nome).all()]


def list_produtos(estoque_id=None, grupo_id=None, somente_ativos=True):
    q = NutProduto.query.outerjoin(NutGrupoProduto)
    if estoque_id:
        q = q.filter(NutProduto.estoque_id == estoque_id)
    if grupo_id:
        q = q.filter(NutProduto.grupo_id == grupo_id)
    if somente_ativos:
        q = q.filter(NutProduto.ativo.is_(True))
    return [
        p.to_dict()
        for p in q.order_by(NutGrupoProduto.nome, NutProduto.codigo, NutProduto.id).all()
    ]


def _seed_produtos():
    for nome in ESTOQUES_SEED:
        if not NutEstoqueLocal.query.filter_by(nome=nome).first():
            db.session.add(NutEstoqueLocal(nome=nome, ativo=True))
    for item in UNIDADES_SEED:
        codigo = (item[0] or '').strip().upper()
        if not codigo:
            continue
        descricao = (item[1] or '').strip().upper() or None
        unid_conv = (item[2] or '').strip().upper() or None
        valor_conv = float(item[3] or 0)
        fnut, fuma, fest, fprat, ativo = (
            bool(item[4]), bool(item[5]), bool(item[6]), bool(item[7]), bool(item[8]),
        )
        row = NutUnidadeMedida.query.filter_by(codigo=codigo).first()
        if not row:
            db.session.add(NutUnidadeMedida(
                codigo=codigo,
                descricao=descricao,
                unid_conversao=unid_conv,
                valor_conversao=valor_conv,
                flag_nutrientes=fnut,
                flag_uma=fuma,
                flag_estoque=fest,
                flag_pratos=fprat,
                ativo=ativo,
            ))
        else:
            if not row.descricao and descricao:
                row.descricao = descricao
            if not row.unid_conversao and unid_conv:
                row.unid_conversao = unid_conv
                row.valor_conversao = valor_conv
    for nome in GRUPOS_PRODUTO_SEED:
        if not NutGrupoProduto.query.filter_by(nome=nome).first():
            db.session.add(NutGrupoProduto(nome=nome, ativo=True))
    db.session.flush()

    if NutProduto.query.count() > 0:
        return
    for (
        estoque_nome, grupo_nome, codigo, descricao, qtd, un,
        preco_med, ult_preco, qmin, qmax, qliq, un_liq, fc
    ) in PRODUTOS_SEED:
        est = NutEstoqueLocal.query.filter_by(nome=estoque_nome).first()
        grp = NutGrupoProduto.query.filter_by(nome=grupo_nome).first()
        if not est or not grp:
            continue
        db.session.add(NutProduto(
            estoque_id=est.id,
            grupo_id=grp.id,
            codigo=(codigo or '').strip().upper(),
            descricao=(descricao or '').strip().upper(),
            quantidade=float(qtd or 0),
            unidade=(un or 'UN').strip().upper(),
            preco_medio=float(preco_med or 0),
            ult_preco=float(ult_preco or 0),
            quant_min=float(qmin or 0),
            quant_max=float(qmax or 0),
            quant_liq=float(qliq or 0),
            un_liq=(un_liq or 'NC').strip().upper(),
            fc=bool(fc),
            ativo=True,
        ))


def list_fornecedores(somente_ativos=True):
    q = NutFornecedor.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [f.to_dict() for f in q.order_by(NutFornecedor.nome, NutFornecedor.id).all()]


def _seed_fornecedores():
    if NutFornecedor.query.count() > 0:
        return
    for item in FORNECEDORES_SEED:
        db.session.add(NutFornecedor(
            nome=(item.get('nome') or '').strip().upper(),
            endereco=(item.get('endereco') or '').strip().upper() or None,
            bairro=(item.get('bairro') or '').strip().upper() or None,
            municipio=(item.get('municipio') or '').strip().upper() or None,
            cep=(item.get('cep') or '').strip() or None,
            estado=(item.get('estado') or '').strip().upper() or None,
            cnpj=(item.get('cnpj') or '').strip() or None,
            inscricao_estadual=(item.get('inscricao_estadual') or '').strip() or None,
            telefone=(item.get('telefone') or '').strip() or None,
            email=(item.get('email') or '').strip() or None,
            faturamento_dias=int(item.get('faturamento_dias') or 0),
            site=(item.get('site') or '').strip() or None,
            observacao=(item.get('observacao') or '').strip() or None,
            ativo=True,
        ))


def list_etiquetas(somente_ativas=False):
    q = NutEtiqueta.query
    if somente_ativas:
        q = q.filter_by(ativa=True)
    return [e.to_dict() for e in q.order_by(NutEtiqueta.nome, NutEtiqueta.id).all()]


def _seed_etiquetas():
    if NutEtiqueta.query.count() > 0:
        return
    for item in ETIQUETAS_SEED:
        row = NutEtiqueta(
            nome=(item.get('nome') or '').strip(),
            ativa=bool(item.get('ativa', True)),
            tamanho_folha=(item.get('tamanho_folha') or 'carta').strip().lower(),
            folha_altura_mm=float(item.get('folha_altura_mm') or 0),
            folha_largura_mm=float(item.get('folha_largura_mm') or 0),
            orientacao=(item.get('orientacao') or 'retrato').strip().lower(),
            margem_esquerda=float(item.get('margem_esquerda') or 0),
            margem_direita=float(item.get('margem_direita') or 0),
            margem_superior=float(item.get('margem_superior') or 0),
            margem_inferior=float(item.get('margem_inferior') or 0),
            num_colunas=int(item.get('num_colunas') or 1),
            dist_colunas_mm=float(item.get('dist_colunas_mm') or 0),
            altura_etiqueta_mm=float(item.get('altura_etiqueta_mm') or 0),
            tamanho_fonte=int(item.get('tamanho_fonte') or 7),
        )
        db.session.add(row)
        db.session.flush()
        for c in (item.get('campos') or []):
            db.session.add(NutEtiquetaCampo(
                etiqueta_id=row.id,
                tipo=((c.get('tipo') or 'D').strip().upper()[:1] or 'D'),
                nome=(c.get('nome') or '').strip().upper(),
                texto=(c.get('texto') or '').strip() or None,
            ))


# Catálogo de preços (Dieta/Item | Empresa | Paciente | Acomp.) — valores do legado visual
# Tupla: (nome, grupo, ordem, empresa, paciente, acompanhante)
_G_DIETAS = 'Dietas Gerais/Especiais'
_G_REFEICOES = 'Refeições/Lanches'
_G_ENT_FEC = 'Enterais Sistema Fechado (~1000ml)'
_G_ENT_ABE = 'Enterais Sistema Aberto'
_G_INFANTIS = 'Fórmulas Infantis 400g'
_G_SUPLEM = 'Suplementos/Módulos'
_G_OUTROS = 'Outros'

def _p3(v):
    """Mesmo preço nas três colunas."""
    return (float(v), float(v), float(v))


PRECOS_REFEICOES_SEED = [
    # Dietas gerais/especiais
    ('Livre', _G_DIETAS, 10, *_p3(11.50)),
    ('Branda', _G_DIETAS, 20, *_p3(11.50)),
    ('Leve', _G_DIETAS, 30, *_p3(11.50)),
    ('Pastosa', _G_DIETAS, 40, *_p3(11.50)),
    ('Pastosa Liquidificada', _G_DIETAS, 50, *_p3(11.50)),
    ('Líquida Completa', _G_DIETAS, 60, *_p3(11.50)),
    ('Semi-Líquida', _G_DIETAS, 70, *_p3(11.50)),
    ('Líquida Restrita', _G_DIETAS, 80, *_p3(11.50)),
    ('Diabética', _G_DIETAS, 90, *_p3(11.50)),
    ('Hipossódica', _G_DIETAS, 100, *_p3(11.50)),
    ('Hipogordurosa', _G_DIETAS, 110, *_p3(11.50)),
    ('Sem Resíduos', _G_DIETAS, 120, *_p3(11.50)),
    ('Sem Lactose', _G_DIETAS, 130, *_p3(11.50)),
    ('Sem Glúten', _G_DIETAS, 140, *_p3(11.50)),
    ('Nefropata', _G_DIETAS, 150, *_p3(11.50)),
    ('Hepatopata', _G_DIETAS, 160, *_p3(11.50)),
    # Refeições/lanches
    ('Almoço / Jantar', _G_REFEICOES, 200, *_p3(11.50)),
    ('Desjejum / Colação', _G_REFEICOES, 210, *_p3(4.00)),
    ('Lanche da Tarde / Ceia', _G_REFEICOES, 220, *_p3(4.00)),
    ('Lanche Específico', _G_REFEICOES, 230, *_p3(6.00)),
    ('Sopa Extra', _G_REFEICOES, 240, *_p3(7.00)),
    # Enterais sistema fechado
    ('Tropic 1.0', _G_ENT_FEC, 300, *_p3(85.00)),
    ('Tropic 1.2', _G_ENT_FEC, 310, *_p3(95.00)),
    ('Tropic 1.5', _G_ENT_FEC, 320, *_p3(110.00)),
    ('Tropic Fiber 1.2', _G_ENT_FEC, 330, *_p3(105.00)),
    ('Diason 1.0', _G_ENT_FEC, 340, *_p3(98.00)),
    ('Isovia', _G_ENT_FEC, 350, *_p3(80.00)),
    ('Peptamen 1.5', _G_ENT_FEC, 360, *_p3(160.00)),
    ('Novasource Renal', _G_ENT_FEC, 370, *_p3(155.00)),
    # Enterais sistema aberto
    ('Tropic 1.0 400g', _G_ENT_ABE, 400, *_p3(45.00)),
    ('Tropic Fiber 400g', _G_ENT_ABE, 410, *_p3(55.00)),
    ('Diason 400g', _G_ENT_ABE, 420, *_p3(60.00)),
    ('Nutren Senior 400g', _G_ENT_ABE, 430, *_p3(65.00)),
    ('Isosource 1.5 250ml', _G_ENT_ABE, 440, *_p3(25.00)),
    # Fórmulas infantis
    ('Nan Comfor 1/2', _G_INFANTIS, 500, *_p3(48.00)),
    ('Nan S.L.', _G_INFANTIS, 510, *_p3(75.00)),
    ('Pre-Nan', _G_INFANTIS, 520, *_p3(85.00)),
    ('Nestogeno 1/2', _G_INFANTIS, 530, *_p3(38.00)),
    ('Aptamil 1/2', _G_INFANTIS, 540, *_p3(50.00)),
    ('Pregomin Pepti', _G_INFANTIS, 550, *_p3(165.00)),
    # Suplementos/módulos
    ('Nutrison Protein Plus 200ml', _G_SUPLEM, 600, *_p3(18.00)),
    ('Cubitan 200ml', _G_SUPLEM, 610, *_p3(22.00)),
    ('Fortifit 200ml', _G_SUPLEM, 620, *_p3(20.00)),
    ('Nutren 1.0/1.5 200ml', _G_SUPLEM, 630, *_p3(15.00)),
    ('Thicken Up Clear 125g', _G_SUPLEM, 640, *_p3(85.00)),
    ('Glutamina 5g', _G_SUPLEM, 650, *_p3(4.50)),
    ('Caseinato de Cálcio 400g', _G_SUPLEM, 660, *_p3(95.00)),
    ('Módulo de Fibras', _G_SUPLEM, 670, *_p3(70.00)),
    ('Módulo de Carboidratos', _G_SUPLEM, 680, *_p3(40.00)),
    # Outros
    ('Kit Descartável', _G_OUTROS, 700, *_p3(12.00)),
    ('Seringa 20ml', _G_OUTROS, 710, *_p3(1.50)),
    ('Seringa 60ml', _G_OUTROS, 720, *_p3(3.50)),
    ('Água Mineral 500ml', _G_OUTROS, 730, *_p3(2.50)),
]

# Antigos tipos de refeição (substituídos pelo catálogo da tela legada)
PRECOS_REFEICOES_LEGACY = {
    'DESJEJUM', 'ALMOÇO', 'LANCHE', 'JANTAR', 'CEIA', 'LANCHE NOTURNO',
}


# Tipos de refeição (foto) — nome, sigla, ordem, hora_limite HH:MM
TIPOS_REFEICAO_SEED = [
    ('DESJEJUM', 'DESJ', 10, '07:00'),
    ('COLAÇÃO', 'COL', 20, '09:30'),
    ('ALMOÇO', 'ALM', 30, '12:00'),
    ('MERENDA', 'MER', 40, '15:00'),
    ('JANTAR', 'JAN', 50, '18:00'),
    ('CEIA', 'CEI', 60, '21:00'),
]


def normalizar_hora_limite(valor):
    """Aceita HH:MM / HHMM / time; devolve 'HH:MM' ou ''."""
    if valor is None:
        return ''
    if hasattr(valor, 'strftime'):
        try:
            return valor.strftime('%H:%M')
        except Exception:
            return ''
    s = str(valor).strip()
    if not s:
        return ''
    digits = ''.join(c for c in s if c.isdigit())
    if len(digits) >= 4:
        hh, mm = int(digits[:2]), int(digits[2:4])
    elif ':' in s:
        parts = s.split(':')
        try:
            hh, mm = int(parts[0]), int(parts[1] if len(parts) > 1 else 0)
        except (TypeError, ValueError):
            return ''
    else:
        return ''
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return ''
    return f'{hh:02d}:{mm:02d}'

# Valores padrão por tipo (dieta oral da foto) — Empresa/Paciente/Acomp = mesmo valor
PRECOS_POR_TIPO_DEFAULT = precos_dict_da_tupla(P_ORAL)

# Dietas do catálogo da foto (entram na matriz e recebem upsert de preços)
DIETAS_PRECO_MATRIX_NOMES = {n.strip().upper() for n, _c, _a in DIETAS_PRECOS_SEED}


def list_precos_refeicoes(somente_ativos=True):
    """Legado: catálogo plano (mantido inativo; não é a tela principal)."""
    q = NutPrecoRefeicao.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [
        r.to_dict()
        for r in q.order_by(NutPrecoRefeicao.ordem, NutPrecoRefeicao.id).all()
    ]


def list_precos_dieta_tipo(somente_ativas=True, somente_tipos_ativos=True):
    """Lista preços dieta × tipo (linhas planas)."""
    q = NutPrecoDietaTipo.query.join(NutDieta).join(NutTipoRefeicao)
    if somente_ativas:
        q = q.filter(NutDieta.ativo.is_(True))
    if somente_tipos_ativos:
        q = q.filter(NutTipoRefeicao.ativo.is_(True))
    rows = q.order_by(NutDieta.nome, NutTipoRefeicao.ordem, NutTipoRefeicao.id).all()
    return [r.to_dict() for r in rows]


def matriz_precos_dieta_tipo(somente_ativas=True, somente_tipos_ativos=True):
    """
    Grade Dieta × Tipo de Refeição para a tela de preços.
    Cada célula traz Empresa / Paciente / Acompanhante.
    """
    tipos = list_tipos_refeicao(somente_ativos=somente_tipos_ativos)
    dietas_q = NutDieta.query
    if somente_ativas:
        dietas_q = dietas_q.filter_by(ativo=True)
    ordem_catalogo = {
        nome.strip().upper(): i
        for i, (nome, *_rest) in enumerate(DIETAS_CATALOGO_PRECOS)
    }
    dietas = dietas_q.order_by(NutDieta.grupo, NutDieta.nome).all()
    dietas_preco = [d for d in dietas if (d.nome or '').upper() in DIETAS_PRECO_MATRIX_NOMES]
    dietas_preco.sort(key=lambda d: (
        0 if (getattr(d, 'grupo', None) or '').upper() == 'LACTÁRIO' else 1,
        ordem_catalogo.get((d.nome or '').upper(), 9999),
        d.nome or '',
    ))
    dietas_outras = [d for d in dietas if (d.nome or '').upper() not in DIETAS_PRECO_MATRIX_NOMES]
    precos = {
        (p.dieta_id, p.tipo_refeicao_id): p
        for p in NutPrecoDietaTipo.query.all()
    }
    dietas_matriz = dietas_preco + [
        d for d in dietas_outras
        if any(k[0] == d.id for k in precos.keys())
    ]

    linhas = []
    for d in dietas_matriz:
        celulas = {}
        for t in tipos:
            p = precos.get((d.id, t['id']))
            if p:
                celulas[t['id']] = {
                    'id': p.id,
                    'valor_empresa': float(p.valor_empresa or 0),
                    'valor_paciente': float(p.valor_paciente or 0),
                    'valor_acompanhante': float(p.valor_acompanhante or 0),
                    'valor': float(p.valor_empresa or 0),
                }
            else:
                celulas[t['id']] = {
                    'id': None,
                    'valor_empresa': 0.0,
                    'valor_paciente': 0.0,
                    'valor_acompanhante': 0.0,
                    'valor': 0.0,
                }
        linhas.append({
            'dieta_id': d.id,
            'dieta': d.nome,
            'categoria': d.categoria or 'basica',
            'grupo': getattr(d, 'grupo', None) or '',
            'ativo': bool(d.ativo),
            'celulas': celulas,
        })
    return {'tipos': tipos, 'linhas': linhas}


def _seed_tipos_refeicao():
    try:
        NutTipoRefeicao.__table__.create(db.engine, checkfirst=True)
    except Exception:
        pass
    existentes = {
        (t.nome or '').strip().upper(): t
        for t in NutTipoRefeicao.query.all()
    }
    for nome, sigla, ordem, hora_limite in TIPOS_REFEICAO_SEED:
        key = nome.strip().upper()
        if key in existentes:
            row = existentes[key]
            row.sigla = sigla
            row.ordem = ordem
            row.ativo = True
            if not (row.hora_limite or '').strip():
                row.hora_limite = hora_limite
            continue
        # sigla pode já existir com outro nome
        by_sigla = NutTipoRefeicao.query.filter(
            db.func.upper(NutTipoRefeicao.sigla) == sigla.upper()
        ).first()
        if by_sigla:
            by_sigla.nome = nome
            by_sigla.ordem = ordem
            by_sigla.ativo = True
            if not (by_sigla.hora_limite or '').strip():
                by_sigla.hora_limite = hora_limite
            continue
        db.session.add(NutTipoRefeicao(
            nome=nome, sigla=sigla, ordem=ordem, hora_limite=hora_limite, ativo=True
        ))
    db.session.flush()


def _normalize_precos_map(precos_map=None):
    """Aceita dict por nome/sigla de tipo → float; devolve dict nome_tipo UPPER → float."""
    if not precos_map:
        return {}
    out = {}
    alias = {
        'DESJ': 'DESJEJUM', 'DESJEJUM': 'DESJEJUM',
        'COL': 'COLAÇÃO', 'COLACAO': 'COLAÇÃO', 'COLAÇÃO': 'COLAÇÃO',
        'ALM': 'ALMOÇO', 'ALMOCO': 'ALMOÇO', 'ALMOÇO': 'ALMOÇO',
        'MER': 'MERENDA', 'MERENDA': 'MERENDA',
        'JAN': 'JANTAR', 'JANTAR': 'JANTAR',
        'CEI': 'CEIA', 'CEIA': 'CEIA',
    }
    for k, v in dict(precos_map).items():
        key = alias.get(str(k).strip().upper(), str(k).strip().upper())
        try:
            out[key] = float(v or 0)
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def _payer_fields(payers=None):
    """Normaliza lista de colunas: empresa / paciente / acompanhante."""
    alias = {
        'empresa': 'empresa', 'emp': 'empresa',
        'paciente': 'paciente', 'pac': 'paciente',
        'acompanhante': 'acompanhante', 'aco': 'acompanhante', 'acomp': 'acompanhante',
    }
    if payers is None:
        return ('empresa', 'paciente', 'acompanhante')
    if isinstance(payers, str):
        payers = [payers]
    out = []
    for p in payers:
        key = alias.get(str(p or '').strip().lower())
        if key and key not in out:
            out.append(key)
    return tuple(out) or ('paciente',)


def ensure_precos_para_dieta(
    dieta_id,
    aplicar_default=True,
    precos_map=None,
    forcar=False,
    payers=None,
    tipos_ids=None,
):
    """
    Cria/atualiza células dieta × tipos ativos.
    - precos_map: valores explícitos por tipo (foto / formulário)
    - forcar=True: sobrescreve as colunas em `payers` com precos_map/default
    - payers: quais colunas gravar (default: as 3)
    - tipos_ids: se informado, só esses tipos de refeição
    - aplicar_default: usa PRECOS_POR_TIPO_DEFAULT quando valor ausente/zerado
    """
    tipos_q = NutTipoRefeicao.query.filter_by(ativo=True)
    if tipos_ids:
        ids = [int(x) for x in tipos_ids]
        tipos_q = tipos_q.filter(NutTipoRefeicao.id.in_(ids))
    tipos = tipos_q.order_by(NutTipoRefeicao.ordem, NutTipoRefeicao.id).all()
    existentes = {
        p.tipo_refeicao_id: p
        for p in NutPrecoDietaTipo.query.filter_by(dieta_id=dieta_id).all()
    }
    mapa = _normalize_precos_map(precos_map)
    cols = _payer_fields(payers)
    for tipo in tipos:
        tnome = (tipo.nome or '').strip().upper()
        if tnome in mapa:
            valor = float(mapa[tnome])
        elif aplicar_default:
            valor = float(PRECOS_POR_TIPO_DEFAULT.get(tnome, 0.0))
        else:
            valor = 0.0
        row = existentes.get(tipo.id)
        if row:
            if forcar:
                if 'empresa' in cols:
                    row.valor_empresa = valor
                if 'paciente' in cols:
                    row.valor_paciente = valor
                if 'acompanhante' in cols:
                    row.valor_acompanhante = valor
            elif aplicar_default:
                emp = float(row.valor_empresa or 0)
                pac = float(row.valor_paciente or 0)
                aco = float(row.valor_acompanhante or 0)
                if emp == 0 and pac == 0 and aco == 0 and valor > 0:
                    if 'empresa' in cols:
                        row.valor_empresa = valor
                    if 'paciente' in cols:
                        row.valor_paciente = valor
                    if 'acompanhante' in cols:
                        row.valor_acompanhante = valor
            continue
        db.session.add(NutPrecoDietaTipo(
            dieta_id=dieta_id,
            tipo_refeicao_id=tipo.id,
            valor_empresa=valor if 'empresa' in cols else 0.0,
            valor_paciente=valor if 'paciente' in cols else 0.0,
            valor_acompanhante=valor if 'acompanhante' in cols else 0.0,
        ))


def _upsert_dieta_catalogo(nome, cat, grupo, ativo, precos, payers=None):
    """Upsert uma dieta do catálogo e força preços nas colunas indicadas."""
    row = NutDieta.query.filter(
        db.func.upper(NutDieta.nome) == nome.upper()
    ).first()
    if not row:
        row = NutDieta(
            nome=nome,
            categoria=cat,
            grupo=grupo,
            ativo=bool(ativo),
        )
        db.session.add(row)
        db.session.flush()
    else:
        row.categoria = cat
        # Não sobrescreve grupo ACOMPANHANTE/FUNCIONARIO (legado EMPRESA) se a dieta já foi criada nesse contexto
        grupo_atual = (getattr(row, 'grupo', None) or '').strip().upper()
        if grupo_atual in ('ACOMPANHANTE', 'EMPRESA', 'FUNCIONARIO', 'FUNCIONÁRIO') and (grupo or '').upper() == 'LACTÁRIO':
            pass
        else:
            row.grupo = grupo
        row.ativo = bool(ativo)
    ensure_precos_para_dieta(
        row.id,
        aplicar_default=False,
        precos_map=precos_dict_da_tupla(precos),
        forcar=True,
        payers=payers,
    )
    return row


def _seed_catalogo_dietas_foto():
    """Upsert dietas + preços do catálogo da foto (idempotente por nome)."""
    # Migra aliases curtos antigos → nomes da foto (só se o destino ainda não existir)
    for antigo, novo in DIETAS_ALIAS_PARA_FOTO.items():
        src = NutDieta.query.filter(
            db.func.upper(NutDieta.nome) == antigo.upper()
        ).first()
        dst = NutDieta.query.filter(
            db.func.upper(NutDieta.nome) == novo.upper()
        ).first()
        if src and not dst:
            src.nome = novo

    for nome, cat, grupo, ativo, precos in DIETAS_CATALOGO_FOTO:
        _upsert_dieta_catalogo(
            nome, cat, grupo, ativo, precos,
            payers=('empresa', 'paciente', 'acompanhante'),
        )


def _seed_catalogo_lactario():
    """
    Upsert catálogo LACTÁRIO (OCR).
    Valores vão para Paciente e Empresa (histórico da grade); Acompanhante fica 0
    para cadastro separado via popup.
    """
    for nome, cat, grupo, ativo, precos in DIETAS_CATALOGO_LACTARIO:
        _upsert_dieta_catalogo(
            nome, cat, grupo, ativo, precos,
            payers=('empresa', 'paciente'),
        )


def _seed_precos_dieta_tipo():
    """Garante matriz dieta × tipo; catálogo da foto + LACTÁRIO com upsert forçado."""
    try:
        NutPrecoDietaTipo.__table__.create(db.engine, checkfirst=True)
    except Exception:
        pass
    _seed_tipos_refeicao()
    _seed_catalogo_dietas_foto()
    _seed_catalogo_lactario()

    # Demais dietas com preço já existente ou do mapa: só preenche células faltantes
    ids_catalogo = {
        d.id for d in NutDieta.query.filter(
            db.func.upper(NutDieta.nome).in_(list(DIETAS_PRECO_MATRIX_NOMES))
        ).all()
    }
    ids_com_preco = {
        r[0] for r in db.session.query(NutPrecoDietaTipo.dieta_id).distinct().all()
    }
    outras = NutDieta.query.filter(
        NutDieta.id.in_(list(ids_com_preco - ids_catalogo) or [-1])
    ).all()
    for dieta in outras:
        # Dietas do mapa operacional usam padrão oral se ainda zeradas
        ensure_precos_para_dieta(dieta.id, aplicar_default=True, forcar=False)


def _seed_precos_refeicoes():
    """Desativa o catálogo plano antigo (enterais/itens) da tela de preços."""
    try:
        NutPrecoRefeicao.__table__.create(db.engine, checkfirst=True)
    except Exception:
        pass
    # Mantém dados no banco, mas oculta da UI antiga
    for row in NutPrecoRefeicao.query.filter_by(ativo=True).all():
        row.ativo = False


def seed_nutricao():
    """Garante cadastros básicos de clínicas e dietas."""
    _ensure_nutricao_columns()
    for nome, ativo in CLINICAS_SEED:
        if not NutClinica.query.filter_by(nome=nome).first():
            db.session.add(NutClinica(nome=nome, ativo=bool(ativo)))

    for nome, cat, ativo in DIETAS_SEED:
        if not NutDieta.query.filter_by(nome=nome).first():
            db.session.add(NutDieta(nome=nome, categoria=cat, grupo='', ativo=bool(ativo)))

    db.session.flush()
    _seed_enfermarias()
    _seed_cardapios()
    _backfill_cardapio_dieta_id()
    _seed_nutricional()
    _seed_pratos_liquidos()
    _seed_produtos()
    _seed_fornecedores()
    _seed_etiquetas()
    _seed_tipos_refeicao()
    _seed_grupos_dieta()
    _seed_precos_dieta_tipo()  # inclui catálogo da foto + preços
    _seed_precos_refeicoes()
    # Após preços/catálogo, reabsorve grupos novos criados nas dietas
    _seed_grupos_dieta()

    if NutPaciente.query.count() == 0:
        exemplos = [
            NutPaciente(
                nome='Maria Silva', sexo='F', nascimento=_parse_date('1985-03-15'),
                prontuario='12345', clinica='CLÍNICA MÉDICA A', leito='101-A',
                dieta='BRANDA COM SAL', diagnostico='HAS', admissao=date.today(),
                altura_cm=165, peso_kg=72, ativo=True,
            ),
            NutPaciente(
                nome='João Santos', sexo='M', nascimento=_parse_date('1972-08-22'),
                prontuario='12346', clinica='CTI - 1', leito='05',
                dieta='PASTOSA COM SAL', diagnostico='Pós-operatório', admissao=date.today(),
                altura_cm=175, peso_kg=80, ativo=True,
            ),
            NutPaciente(
                nome='Ana Oliveira', sexo='F', nascimento=_parse_date('1990-12-01'),
                prontuario='12347', clinica='ONCO', leito='210-B',
                dieta='LIQUIDA SEM SAL', diagnostico='Em tratamento', admissao=date.today(),
                altura_cm=160, peso_kg=58, ativo=True,
            ),
        ]
        for p in exemplos:
            db.session.add(p)

    db.session.commit()


def paciente_from_payload(d, paciente=None):
    paciente = paciente or NutPaciente()
    paciente.nome = (d.get('nome') or '').strip()
    paciente.sexo = (d.get('sexo') or '').strip()[:1] or None
    paciente.nascimento = _parse_date(d.get('nascimento'))
    paciente.prontuario = (d.get('prontuario') or '').strip() or None
    paciente.clinica = (d.get('clinica') or '').strip() or None
    paciente.leito = (d.get('leito') or '').strip() or None
    paciente.dieta = (d.get('dieta') or '').strip() or None
    paciente.diagnostico = (d.get('diagnostico') or '').strip() or None
    paciente.observacoes = (d.get('observacoes') or '').strip() or None
    paciente.admissao = _parse_date(d.get('admissao'))
    paciente.data_saida = _parse_date(d.get('data_saida'))
    try:
        paciente.altura_cm = float(d['altura_cm']) if d.get('altura_cm') not in (None, '') else None
    except (TypeError, ValueError):
        paciente.altura_cm = None
    try:
        paciente.peso_kg = float(d['peso_kg']) if d.get('peso_kg') not in (None, '') else None
    except (TypeError, ValueError):
        paciente.peso_kg = None
    if 'ativo' in d:
        paciente.ativo = bool(d.get('ativo'))
    return paciente


def mapa_from_paciente(paciente, data_ref=None, flags=None, extras=None, usuario=None):
    data_ref = data_ref or date.today()
    flags = flags or {}
    extras = extras or {}
    agora = datetime.utcnow()
    return NutMapaRefeicao(
        data_refeicao=data_ref,
        paciente_id=paciente.id,
        adm=extras.get('adm', paciente.admissao),
        leito=(extras.get('leito') if 'leito' in extras else paciente.leito),
        prontuario=(extras.get('prontuario') if 'prontuario' in extras else paciente.prontuario),
        nome=paciente.nome,
        idade=paciente.idade(data_ref),
        diagnostico=(extras.get('diagnostico') if 'diagnostico' in extras else paciente.diagnostico),
        dieta=(extras.get('dieta') if 'dieta' in extras else paciente.dieta),
        observacoes=(extras.get('observacoes') if 'observacoes' in extras else paciente.observacoes),
        clinica=(extras.get('clinica') if 'clinica' in extras else paciente.clinica),
        enfermaria=(extras.get('enfermaria') or None),
        fl_desjejum=bool(flags.get('fl_desjejum', True)),
        fl_colacao=bool(flags.get('fl_colacao', True)),
        fl_almoco=bool(flags.get('fl_almoco', True)),
        fl_merenda=bool(flags.get('fl_merenda', True)),
        fl_jantar=bool(flags.get('fl_jantar', True)),
        fl_ceia=bool(flags.get('fl_ceia', True)),
        obs_etiqueta=(extras.get('obs_etiqueta') or None),
        extras=(extras.get('extras') or None),
        suplementos=(extras.get('suplementos') or None),
        enteral=(extras.get('enteral') or None),
        formula_infantil=(extras.get('formula_infantil') or None),
        lve=(extras.get('lve') or None),
        data_inclusao=agora,
        usuario_alteracao=(usuario or 'sistema')[:80],
        data_atualizacao=agora,
        # Saída no mapa só via Excluir com motivo — não herdar data_saida do cadastro
        data_saida=None,
        motivo_saida=None,
        ativo=True,
    )


def _chave_linha_mapa(row):
    """Chave de identidade para linhas sem paciente_id."""
    return (
        (row.prontuario or '').strip().upper(),
        (row.nome or '').strip().upper(),
        (row.leito or '').strip().upper(),
    )


def _clonar_linha_mapa(src, data_ref, usuario=None):
    """Copia snapshot operacional de uma linha ativa para outra data."""
    agora = datetime.utcnow()
    idade = src.idade
    if src.paciente_id and src.paciente:
        try:
            idade = src.paciente.idade(data_ref)
        except Exception:
            pass
    return NutMapaRefeicao(
        data_refeicao=data_ref,
        paciente_id=src.paciente_id,
        adm=src.adm,
        leito=src.leito,
        prontuario=src.prontuario,
        nome=src.nome,
        idade=idade,
        diagnostico=src.diagnostico,
        dieta=src.dieta,
        observacoes=src.observacoes,
        clinica=src.clinica,
        enfermaria=src.enfermaria,
        fl_desjejum=bool(src.fl_desjejum),
        fl_colacao=bool(src.fl_colacao),
        fl_almoco=bool(src.fl_almoco),
        fl_merenda=bool(src.fl_merenda),
        fl_jantar=bool(src.fl_jantar),
        fl_ceia=bool(src.fl_ceia),
        obs_etiqueta=src.obs_etiqueta,
        extras=src.extras,
        suplementos=src.suplementos,
        enteral=src.enteral,
        formula_infantil=src.formula_infantil,
        lve=src.lve,
        data_inclusao=src.data_inclusao or agora,
        usuario_alteracao=(usuario or src.usuario_alteracao or 'sistema')[:80],
        data_atualizacao=agora,
        data_saida=None,
        motivo_saida=None,
        hospital_transferencia=None,
        ativo=True,
    )


def _linha_com_baixa(src):
    """Baixa real no mapa: só Excluir com motivo preenchido."""
    return bool(src and (src.motivo_saida or '').strip())


def _linha_mapa_ativa_para_copia(src):
    """Elegível para persistir no dia seguinte (não deu baixa com motivo)."""
    if not src:
        return False
    # ativo=False sem motivo = inconsistência; ainda pode ser fonte de cópia
    if _linha_com_baixa(src):
        return False
    return True


def _sanear_baixas_incompletas(data_ref):
    """Reativa linhas inativas sem motivo (baixa incompleta / bug antigo)."""
    sanadas = 0
    rows = (
        NutMapaRefeicao.query
        .filter_by(data_refeicao=data_ref, ativo=False)
        .all()
    )
    for row in rows:
        if _linha_com_baixa(row):
            continue
        row.ativo = True
        row.data_saida = None
        row.hospital_transferencia = None
        marcar_alteracao_mapa(row, 'sistema')
        sanadas += 1
    return sanadas


def _upsert_linha_no_dia(src, data_ref, by_pid, by_chave):
    """Garante linha de src em data_ref (cria ou reativa). Retorna 1 se alterou."""
    if not _linha_mapa_ativa_para_copia(src):
        return 0

    if src.paciente_id:
        existing = by_pid.get(src.paciente_id)
        if existing:
            if _linha_com_baixa(existing):
                return 0
            if not existing.ativo:
                existing.ativo = True
                existing.data_saida = None
                existing.motivo_saida = None
                existing.hospital_transferencia = None
                marcar_alteracao_mapa(existing, 'sistema')
                return 1
            return 0
        clone = _clonar_linha_mapa(src, data_ref)
        db.session.add(clone)
        by_pid[src.paciente_id] = clone
        return 1

    chave = _chave_linha_mapa(src)
    existing = by_chave.get(chave)
    if existing:
        if _linha_com_baixa(existing):
            return 0
        if not existing.ativo:
            existing.ativo = True
            existing.data_saida = None
            existing.motivo_saida = None
            existing.hospital_transferencia = None
            marcar_alteracao_mapa(existing, 'sistema')
            return 1
        return 0
    clone = _clonar_linha_mapa(src, data_ref)
    db.session.add(clone)
    by_chave[chave] = clone
    return 1


def _copiar_ativos_dia_anterior(data_ref):
    """Merge: cada paciente ativo (sem baixa com motivo) de data_ref-1 passa a existir em data_ref.

    Não pula o dia só porque já há algumas linhas (ex.: Ana em 09/08 não bloqueia os demais).
    """
    data_origem = data_ref - timedelta(days=1)
    alteradas = _sanear_baixas_incompletas(data_ref)
    alteradas += _sanear_baixas_incompletas(data_origem)

    existentes = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref).all()
    by_pid = {r.paciente_id: r for r in existentes if r.paciente_id}
    by_chave = {_chave_linha_mapa(r): r for r in existentes if not r.paciente_id}

    fontes = (
        NutMapaRefeicao.query
        .filter_by(data_refeicao=data_origem)
        .order_by(NutMapaRefeicao.id)
        .all()
    )
    if not fontes:
        return alteradas

    for src in fontes:
        alteradas += _upsert_linha_no_dia(src, data_ref, by_pid, by_chave)
    return alteradas


def _garantir_ausentes_desde_historico(data_ref):
    """Copia do último estado anterior (sem baixa) quem ainda falta no dia alvo.

    Cobre buracos se um dia intermediário nunca recebeu a linha.
    """
    existentes = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref).all()
    by_pid = {r.paciente_id: r for r in existentes if r.paciente_id}
    by_chave = {_chave_linha_mapa(r): r for r in existentes if not r.paciente_id}

    priors = (
        NutMapaRefeicao.query
        .filter(NutMapaRefeicao.data_refeicao < data_ref)
        .order_by(NutMapaRefeicao.data_refeicao.desc(), NutMapaRefeicao.id.desc())
        .all()
    )
    seen_pids = set()
    seen_chaves = set()
    alteradas = 0
    for src in priors:
        if src.paciente_id:
            if src.paciente_id in seen_pids:
                continue
            seen_pids.add(src.paciente_id)
        else:
            chave = _chave_linha_mapa(src)
            if chave in seen_chaves:
                continue
            seen_chaves.add(chave)
        # Último estado anterior: se foi baixa com motivo, não ressuscita
        if _linha_com_baixa(src):
            continue
        alteradas += _upsert_linha_no_dia(src, data_ref, by_pid, by_chave)
    return alteradas


def garantir_mapa_do_dia(data_ref=None):
    """Garante linhas do mapa em data_ref mesclando pacientes ainda sem baixa.

    Novos pacientes entram só via inserção manual. Quem saiu por Excluir
    (motivo_saida preenchido) não é recriado nos dias seguintes.

    - Mescla mesmo se o dia já tiver algumas linhas (não aborta por dia não-vazio).
    - Reativa baixas incompletas (ativo=False sem motivo).
    - Preenche dia a dia e, por fim, cobre ausentes via histórico.
    Cadastro do paciente (data_saida no NutPaciente) NÃO impede a cópia —
    só a baixa no mapa com motivo.
    """
    data_ref = data_ref or date.today()

    oldest = (
        db.session.query(NutMapaRefeicao.data_refeicao)
        .filter(NutMapaRefeicao.data_refeicao < data_ref)
        .order_by(NutMapaRefeicao.data_refeicao.asc())
        .first()
    )
    alteradas = _sanear_baixas_incompletas(data_ref)
    if not oldest:
        if alteradas:
            db.session.commit()
            print(f'[mapa] garantir {data_ref}: sanadas/criadas={alteradas}')
        return alteradas

    cur = oldest[0] + timedelta(days=1)
    while cur <= data_ref:
        alteradas += _copiar_ativos_dia_anterior(cur)
        cur += timedelta(days=1)

    alteradas += _garantir_ausentes_desde_historico(data_ref)

    if alteradas:
        db.session.commit()
    print(f'[mapa] garantir {data_ref}: sanadas/criadas={alteradas}')
    return alteradas


def marcar_alteracao_mapa(row, usuario=None):
    row.usuario_alteracao = (usuario or 'sistema')[:80]
    row.data_atualizacao = datetime.utcnow()
    return row


def _aplicar_baixa_linha(row, motivo, usuario=None, data_saida=None, hospital_transferencia=None):
    """Aplica campos de baixa em uma linha do mapa (mantém registro histórico)."""
    row.data_saida = data_saida
    row.motivo_saida = motivo[:40]
    row.ativo = False
    if hospital_transferencia is not None:
        hosp = (hospital_transferencia or '').strip()
        row.hospital_transferencia = hosp[:200] if hosp else None
    marcar_alteracao_mapa(row, usuario)
    return row


def registrar_saida_mapa(row, motivo, usuario=None, data_saida=None, hospital_transferencia=None):
    """Baixa/soft-exit: mantém histórico na linha (não apaga) e impede persistência futura."""
    if not row:
        return None
    motivo = (motivo or '').strip()
    if not motivo:
        raise ValueError('Motivo da saída é obrigatório')

    data_ref = data_saida or row.data_refeicao or date.today()
    _aplicar_baixa_linha(
        row,
        motivo=motivo,
        usuario=usuario,
        data_saida=data_ref,
        hospital_transferencia=hospital_transferencia,
    )

    # Fecha duplicatas ativas do mesmo paciente no mesmo dia + cópias já criadas à frente
    if row.paciente_id:
        irmas = (
            NutMapaRefeicao.query
            .filter(
                NutMapaRefeicao.paciente_id == row.paciente_id,
                NutMapaRefeicao.ativo.is_(True),
                NutMapaRefeicao.id != row.id,
                NutMapaRefeicao.data_refeicao >= (row.data_refeicao or data_ref),
            )
            .all()
        )
        for irma in irmas:
            _aplicar_baixa_linha(
                irma,
                motivo=motivo,
                usuario=usuario,
                data_saida=data_ref,
                hospital_transferencia=hospital_transferencia,
            )

        pac = NutPaciente.query.get(row.paciente_id)
        if pac:
            pac.ativo = False
            pac.data_saida = data_ref
            pac.hora_saida = datetime.now().strftime('%H:%M:%S')
            pac.motivo_saida = motivo[:40]
    return row


def listar_avisos_alta_mapa(data_ref=None):
    """Pacientes com alta anteriores à data do mapa, ainda presentes nas linhas ativas."""
    data_ref = data_ref or date.today()
    garantir_mapa_do_dia(data_ref)
    rows = (
        NutMapaRefeicao.query
        .filter_by(data_refeicao=data_ref, ativo=True)
        .order_by(NutMapaRefeicao.clinica, NutMapaRefeicao.leito, NutMapaRefeicao.nome)
        .all()
    )
    avisos = []
    for r in rows:
        pac = r.paciente
        saida = None
        hora = '00:00:00'
        motivo = 'Alta médica'
        if pac and pac.data_saida:
            saida = pac.data_saida
            hora = (pac.hora_saida or '14:00:00').strip() or '14:00:00'
            motivo = (pac.motivo_saida or 'Alta médica').strip() or 'Alta médica'
        elif r.data_saida:
            saida = r.data_saida
            motivo = (r.motivo_saida or 'Alta médica').strip() or 'Alta médica'
        if not saida:
            continue
        # alta em data anterior à do mapa → não deveria permanecer
        if saida >= data_ref:
            continue
        avisos.append({
            'mapa_id': r.id,
            'paciente_id': r.paciente_id,
            'clinica': r.clinica or (pac.clinica if pac else '') or '',
            'leito': r.leito or (pac.leito if pac else '') or '',
            'nome': r.nome or (pac.nome if pac else '') or '',
            'data_saida': saida.isoformat(),
            'saida': hora,
            'motivo': motivo,
            'excluir': True,
        })
    return avisos


def aplicar_avisos_alta_mapa(mapa_ids_excluir, usuario=None):
    """Desativa linhas do mapa marcadas para exclusão no aviso de alta (com histórico)."""
    ids = []
    for x in (mapa_ids_excluir or []):
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    if not ids:
        return 0
    qtd = 0
    for mid in ids:
        row = NutMapaRefeicao.query.get(mid)
        if not row or not row.ativo:
            continue
        pac = row.paciente
        motivo = None
        if pac and pac.motivo_saida:
            motivo = pac.motivo_saida
        elif row.motivo_saida:
            motivo = row.motivo_saida
        else:
            motivo = 'Alta médica'
        data_saida = None
        if pac and pac.data_saida:
            data_saida = pac.data_saida
        elif row.data_saida:
            data_saida = row.data_saida
        registrar_saida_mapa(row, motivo=motivo, usuario=usuario, data_saida=data_saida)
        qtd += 1
    if qtd:
        db.session.commit()
    return qtd


CAMPO_UMA = {
    'enteral': 'enteral',
    'suplementos': 'suplementos',
    'formula_infantil': 'formula_infantil',
    'lve': 'lve',
}


def totalizar_mapa_uma(data_ref, categoria='enteral', imprimir_por='clinica', filtro_id=None, filtro_nome=None, horarios=None, amostra=None):
    """Agrega itens do mapa (enteral/suplementos/fórmula/LVE) para impressão U.M.A."""
    from collections import defaultdict

    data_ref = data_ref or date.today()
    garantir_mapa_do_dia(data_ref)
    campo = CAMPO_UMA.get(categoria, 'enteral')

    q = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True)
    linhas = q.order_by(NutMapaRefeicao.clinica, NutMapaRefeicao.leito, NutMapaRefeicao.nome).all()

    # filtro por clínica / grupo (mesmo cadastro NutClinica) ou enfermaria
    filtro_nome = (filtro_nome or '').strip()
    if imprimir_por in ('grupo_clinica', 'clinica') and filtro_nome:
        linhas = [l for l in linhas if (l.clinica or '').strip().upper() == filtro_nome.upper()]
    elif imprimir_por == 'enfermaria' and filtro_id:
        enf = NutEnfermaria.query.get(int(filtro_id))
        if enf:
            leitos = { (lt.numero_leito or '').strip().upper() for lt in (enf.leitos or []) }
            # também aceita match por nome da enfermaria na clínica do mapa
            nome_enf = (enf.nome or '').upper()
            filtradas = []
            for l in linhas:
                leito = (l.leito or '').strip().upper()
                clinica = (l.clinica or '').strip().upper()
                if leito in leitos or nome_enf in clinica or clinica == nome_enf:
                    filtradas.append(l)
            linhas = filtradas

    totais = defaultdict(lambda: {'item': '', 'qtd_pacientes': 0, 'leitos': [], 'pacientes': []})
    detalhe = []
    for l in linhas:
        texto = (getattr(l, campo, None) or '').strip()
        if not texto:
            continue
        # cada linha de texto pode ter múltiplos itens separados por ; ou quebra
        partes = [p.strip() for p in texto.replace('\n', ';').split(';') if p.strip()]
        for item in partes:
            key = item.upper()
            totais[key]['item'] = item
            totais[key]['qtd_pacientes'] += 1
            if l.leito:
                totais[key]['leitos'].append(l.leito)
            if l.nome:
                totais[key]['pacientes'].append(l.nome)
            detalhe.append({
                'item': item,
                'paciente': l.nome or '',
                'leito': l.leito or '',
                'prontuario': l.prontuario or '',
                'clinica': l.clinica or '',
                'dieta': l.dieta or '',
            })

    itens = sorted(totais.values(), key=lambda x: x['item'].upper())
    if amostra is not None:
        try:
            val = float(amostra)
        except (TypeError, ValueError):
            val = 0
        itens.append({
            'item': f'AMOSTRA ({val:g})',
            'qtd_pacientes': 1,
            'leitos': ['—'],
            'pacientes': ['AMOSTRA'],
            'amostra': True,
            'valor_amostra': val,
        })

    labels = {
        'enteral': 'Enteral',
        'suplementos': 'Suplementos',
        'formula_infantil': 'Fórm. Infantis',
        'lve': 'LVE',
    }
    return {
        'data': data_ref.isoformat(),
        'data_label': data_ref.strftime('%d/%m/%Y'),
        'categoria': categoria,
        'categoria_label': labels.get(categoria, categoria),
        'imprimir_por': imprimir_por,
        'filtro_nome': filtro_nome or 'TODOS',
        'horarios': sorted(set(int(h) for h in (horarios or []) if str(h).isdigit())),
        'itens': itens,
        'detalhe': detalhe,
        'total_linhas': len(detalhe),
        'total_itens': len([i for i in itens if not i.get('amostra')]),
    }


REFEICAO_FLAGS = (
    ('desjejum', 'fl_desjejum'),
    ('colacao', 'fl_colacao'),
    ('almoco', 'fl_almoco'),
    ('merenda', 'fl_merenda'),
    ('jantar', 'fl_jantar'),
    ('ceia', 'fl_ceia'),
)

CATEGORIAS_FAT = ('basicas', 'liquidas', 'di', 'acomp')


def _classificar_dieta_faturamento(linha, dieta_cat_map=None):
    """Classifica linha do mapa em BÁSICAS / LÍQUIDAS / D.I. / ACOMP."""
    dieta = (linha.dieta or '').strip().upper()
    cat = (dieta_cat_map or {}).get(dieta, '')
    if 'ACOMP' in dieta or 'ACOMPANHANTE' in dieta:
        return 'acomp'
    if 'LIQUIDA' in dieta:
        return 'liquidas'
    if cat in ('enteral', 'formula', 'lve'):
        return 'di'
    if (linha.enteral or '').strip() or (linha.formula_infantil or '').strip():
        return 'di'
    return 'basicas'


def _zero_matriz():
    return {cat: {ref: 0 for ref, _ in REFEICAO_FLAGS} for cat in CATEGORIAS_FAT}


def relatorio_faturamento(data_de, data_ate, tipo='espelho_1', por_grupo_clinica=False, sintetico=False):
    """Gera espelho/totais de faturamento a partir do mapa de refeições."""
    from collections import defaultdict

    data_de = data_de or date.today()
    data_ate = data_ate or data_de
    if data_ate < data_de:
        data_de, data_ate = data_ate, data_de

    # garante mapa no intervalo (até 31 dias para não pesar)
    cur = data_de
    dias = 0
    while cur <= data_ate and dias < 62:
        garantir_mapa_do_dia(cur)
        cur = date.fromordinal(cur.toordinal() + 1)
        dias += 1

    dieta_cat_map = {
        (d.nome or '').strip().upper(): (d.categoria or 'basica')
        for d in NutDieta.query.all()
    }

    linhas = (
        NutMapaRefeicao.query
        .filter(
            NutMapaRefeicao.data_refeicao >= data_de,
            NutMapaRefeicao.data_refeicao <= data_ate,
            NutMapaRefeicao.ativo.is_(True),
        )
        .order_by(NutMapaRefeicao.data_refeicao, NutMapaRefeicao.clinica, NutMapaRefeicao.leito)
        .all()
    )

    # clinica -> data -> matriz
    blocos = defaultdict(lambda: defaultdict(_zero_matriz))
    totais_gerais = _zero_matriz()
    formulas = defaultdict(lambda: {'item': '', 'qtd': 0})
    complementares = defaultdict(lambda: {'item': '', 'qtd': 0})

    for l in linhas:
        clinica = (l.clinica or 'SEM CLÍNICA').strip() or 'SEM CLÍNICA'
        data_key = l.data_refeicao.isoformat() if l.data_refeicao else data_de.isoformat()
        cat = _classificar_dieta_faturamento(l, dieta_cat_map)

        for ref_key, flag in REFEICAO_FLAGS:
            if getattr(l, flag, False):
                # tipos de relatório de fórmulas/complementares não usam flags da mesma forma
                if tipo in ('total_formulas',):
                    continue
                if tipo == 'total_complementares':
                    continue
                blocos[clinica][data_key][cat][ref_key] += 1
                totais_gerais[cat][ref_key] += 1

        # fórmulas infantis e enterais
        for campo in ('enteral', 'formula_infantil'):
            texto = (getattr(l, campo, None) or '').strip()
            if not texto:
                continue
            for parte in [p.strip() for p in texto.replace('\n', ';').split(';') if p.strip()]:
                k = parte.upper()
                formulas[k]['item'] = parte
                formulas[k]['qtd'] += 1

        # complementares: extras / suplementos / lve
        for campo in ('extras', 'suplementos', 'lve'):
            texto = (getattr(l, campo, None) or '').strip()
            if not texto:
                continue
            for parte in [p.strip() for p in texto.replace('\n', ';').split(';') if p.strip()]:
                k = parte.upper()
                complementares[k]['item'] = parte
                complementares[k]['qtd'] += 1

    # monta tabelas no formato da tela legado
    tabelas = []
    clinicas_ord = sorted(blocos.keys())
    for clinica in clinicas_ord:
        datas = sorted(blocos[clinica].keys())
        for data_key in datas:
            matriz = blocos[clinica][data_key]
            try:
                data_label = date.fromisoformat(data_key).strftime('%d/%m/%y')
            except ValueError:
                data_label = data_key
            linhas_tab = []
            for cat, label in (
                ('basicas', 'BÁSICAS'),
                ('liquidas', 'LÍQUIDAS'),
                ('di', 'D.I.'),
                ('acomp', 'ACOMP.'),
            ):
                row = {'categoria': label, **matriz[cat]}
                row['total'] = sum(matriz[cat][r] for r, _ in REFEICAO_FLAGS)
                linhas_tab.append(row)
            tabelas.append({
                'data': data_key,
                'data_label': data_label,
                'clinica': clinica,
                'linhas': linhas_tab,
            })

    # sintético: agrega por clínica (soma datas)
    if sintetico and tipo.startswith('espelho'):
        agg = defaultdict(_zero_matriz)
        for t in tabelas:
            for row in t['linhas']:
                cat_key = {
                    'BÁSICAS': 'basicas', 'LÍQUIDAS': 'liquidas', 'D.I.': 'di', 'ACOMP.': 'acomp'
                }[row['categoria']]
                for ref, _ in REFEICAO_FLAGS:
                    agg[t['clinica']][cat_key][ref] += row[ref]
        tabelas = []
        for clinica in sorted(agg.keys()):
            linhas_tab = []
            for cat, label in (
                ('basicas', 'BÁSICAS'), ('liquidas', 'LÍQUIDAS'), ('di', 'D.I.'), ('acomp', 'ACOMP.')
            ):
                row = {'categoria': label, **agg[clinica][cat]}
                row['total'] = sum(agg[clinica][cat][r] for r, _ in REFEICAO_FLAGS)
                linhas_tab.append(row)
            tabelas.append({
                'data': f'{data_de.isoformat()}_{data_ate.isoformat()}',
                'data_label': f'{data_de.strftime("%d/%m/%y")}–{data_ate.strftime("%d/%m/%y")}',
                'clinica': clinica,
                'linhas': linhas_tab,
            })

    # página 2 do espelho: só totais por clínica (resumo)
    if tipo == 'espelho_2':
        # mantém mesmas tabelas mas marca como página 2 (pode filtrar só quem tem movimento)
        tabelas = [t for t in tabelas if any(l['total'] > 0 for l in t['linhas'])]

    tipo_labels = {
        'espelho_1': 'Espelho do faturamento — 1ª página',
        'espelho_2': 'Espelho do faturamento — 2ª página',
        'total_sem_correcao': 'Total de refeições (sem correção)',
        'total_refeicoes': 'Total de refeições',
        'total_formulas': 'Total de fórmulas infantis e enterais',
        'total_complementares': 'Total de refeições complementares',
    }

    resumo_totais = []
    for cat, label in (
        ('basicas', 'BÁSICAS'), ('liquidas', 'LÍQUIDAS'), ('di', 'D.I.'), ('acomp', 'ACOMP.')
    ):
        row = {'categoria': label, **totais_gerais[cat]}
        row['total'] = sum(totais_gerais[cat][r] for r, _ in REFEICAO_FLAGS)
        resumo_totais.append(row)

    return {
        'data_de': data_de.isoformat(),
        'data_ate': data_ate.isoformat(),
        'data_de_label': data_de.strftime('%d/%m/%Y'),
        'data_ate_label': data_ate.strftime('%d/%m/%Y'),
        'tipo': tipo,
        'tipo_label': tipo_labels.get(tipo, tipo),
        'por_grupo_clinica': bool(por_grupo_clinica),
        'sintetico': bool(sintetico),
        'tabelas': tabelas,
        'resumo_totais': resumo_totais,
        'formulas': sorted(formulas.values(), key=lambda x: x['item'].upper()),
        'complementares': sorted(complementares.values(), key=lambda x: x['item'].upper()),
        'qtd_tabelas': len(tabelas),
    }


def _grupo_dieta_totalizacao(nome_dieta, dieta_cat_map=None):
    """Agrupa dieta em BÁSICAS / LÍQUIDAS / D.I. / ACOMPANHANTES para subtotais."""
    nome = (nome_dieta or '').strip().upper()
    cat = (dieta_cat_map or {}).get(nome, '')
    if 'ACOMP' in nome or 'ACOMPANHANTE' in nome:
        return 'ACOMPANHANTES'
    if nome.startswith('DI-') or cat in ('enteral', 'formula', 'lve'):
        return 'D.I.'
    if 'LIQUIDA' in nome:
        return 'LÍQUIDAS'
    return 'BÁSICAS'


def totalizacao_dietas(
    data_ref=None,
    totalizacao_para='clinicas',
    imprimir_por='grupo_clinica',
    filtros=None,
    horarios=None,
    metodo='mapa',
    imprimir_total_geral=True,
):
    """Totaliza dietas do mapa por nome × horários (estilo relatório legado)."""
    from collections import defaultdict

    data_ref = data_ref or date.today()
    garantir_mapa_do_dia(data_ref)
    horarios = set(horarios or [])
    flag_map = {
        'desjejum': 'fl_desjejum',
        'colacao': 'fl_colacao',
        'almoco': 'fl_almoco',
        'merenda': 'fl_merenda',
        'jantar': 'fl_jantar',
        'ceia': 'fl_ceia',
    }
    # se nenhum horário marcado, usa todos
    if not horarios:
        horarios = set(flag_map.keys())

    filtros = [str(f).strip() for f in (filtros or []) if str(f).strip()]
    filtros_upper = {f.upper() for f in filtros}
    todos = (not filtros) or ('TODOS' in filtros_upper)

    dieta_cat_map = {
        (d.nome or '').strip().upper(): (d.categoria or 'basica')
        for d in NutDieta.query.all()
    }

    q = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True)
    linhas = q.order_by(NutMapaRefeicao.dieta, NutMapaRefeicao.clinica).all()

    filtro_labels = []
    if imprimir_por == 'enfermaria' and not todos:
        enfs = NutEnfermaria.query.filter(NutEnfermaria.id.in_(
            [int(x) for x in filtros if str(x).isdigit()]
        )).all() if any(str(x).isdigit() for x in filtros) else []
        # também aceita nomes
        if not enfs:
            enfs = NutEnfermaria.query.filter(
                db.func.upper(NutEnfermaria.nome).in_(list(filtros_upper))
            ).all()
        filtro_labels = [e.nome for e in enfs]
        leitos = set()
        nomes_enf = {e.nome.upper() for e in enfs}
        for e in enfs:
            for lt in (e.leitos or []):
                if lt.numero_leito:
                    leitos.add(lt.numero_leito.strip().upper())
        filtradas = []
        for l in linhas:
            leito = (l.leito or '').strip().upper()
            clinica = (l.clinica or '').strip().upper()
            if leito in leitos or clinica in nomes_enf or any(n in clinica for n in nomes_enf):
                filtradas.append(l)
        linhas = filtradas
    elif not todos:
        # clínica / grupo de clínica
        ids = [int(x) for x in filtros if str(x).isdigit()]
        nomes = set()
        if ids:
            for c in NutClinica.query.filter(NutClinica.id.in_(ids)).all():
                nomes.add((c.nome or '').strip().upper())
                filtro_labels.append(c.nome)
        for f in filtros:
            if not str(f).isdigit():
                nomes.add(f.upper())
                if f not in filtro_labels:
                    filtro_labels.append(f)
        linhas = [l for l in linhas if (l.clinica or '').strip().upper() in nomes]
    else:
        filtro_labels = ['TODOS']

    # dieta -> contagens por horário
    totais = defaultdict(lambda: {k: 0 for k in flag_map.keys()})
    for l in linhas:
        dieta = (l.dieta or '').strip() or 'SEM DIETA'
        for hk in horarios:
            flag = flag_map.get(hk)
            if flag and getattr(l, flag, False):
                totais[dieta][hk] += 1

    # monta linhas ordenadas por grupo e nome
    ordem_grupos = ['BÁSICAS', 'LÍQUIDAS', 'D.I.', 'ACOMPANHANTES']
    por_grupo = defaultdict(list)
    for nome, counts in totais.items():
        if sum(counts.values()) <= 0:
            continue
        grp = _grupo_dieta_totalizacao(nome, dieta_cat_map)
        row = {'nome': nome, 'grupo': grp, **counts, 'total': sum(counts.values())}
        por_grupo[grp].append(row)

    linhas_rel = []
    subtotais = []
    gerais = {k: 0 for k in flag_map.keys()}
    for grp in ordem_grupos:
        items = sorted(por_grupo.get(grp, []), key=lambda x: x['nome'].upper())
        if not items:
            continue
        sub = {k: 0 for k in flag_map.keys()}
        for it in items:
            linhas_rel.append(it)
            for k in flag_map.keys():
                sub[k] += it[k]
                gerais[k] += it[k]
        label = {
            'BÁSICAS': 'TOTAL - DIETAS BÁSICAS',
            'LÍQUIDAS': 'TOTAL - DIETAS LÍQUIDAS',
            'D.I.': 'TOTAL - DIETA D.I.',
            'ACOMPANHANTES': 'TOTAL - ACOMPANHANTES DE LEITO',
        }.get(grp, f'TOTAL - {grp}')
        subtotais.append({
            'nome': label,
            'grupo': grp,
            'is_subtotal': True,
            **sub,
            'total': sum(sub.values()),
        })
        linhas_rel.append(subtotais[-1])

    colunas = []
    labels_h = {
        'desjejum': 'D', 'colacao': 'C', 'almoco': 'A',
        'merenda': 'M', 'jantar': 'J', 'ceia': 'Ce',
    }
    for hk in ('desjejum', 'colacao', 'almoco', 'merenda', 'jantar', 'ceia'):
        if hk in horarios:
            colunas.append({'key': hk, 'label': labels_h[hk]})

    return {
        'data': data_ref.isoformat(),
        'data_label': data_ref.strftime('%d/%m/%y'),
        'data_hora_relatorio': datetime.now().strftime('%d/%m/%y %H:%M:%S'),
        'totalizacao_para': totalizacao_para,
        'imprimir_por': imprimir_por,
        'metodo': metodo,
        'filtros_label': ', '.join(filtro_labels) if filtro_labels else 'TODOS',
        'horarios': sorted(horarios),
        'colunas': colunas,
        'linhas': linhas_rel,
        'imprimir_total_geral': bool(imprimir_total_geral),
        'total_geral': {**gerais, 'total': sum(gerais.values())},
        'qtd_dietas': len([x for x in linhas_rel if not x.get('is_subtotal')]),
    }


# ---- Impressão de etiquetas ----

HORARIO_ETIQUETA = {
    'desjejum': {'flag': 'fl_desjejum', 'label': 'Desjejum', 'valido_ate': '08:30'},
    'colacao': {'flag': 'fl_colacao', 'label': 'Colação', 'valido_ate': '10:30'},
    'almoco': {'flag': 'fl_almoco', 'label': 'Almoço', 'valido_ate': '13:30'},
    'merenda': {'flag': 'fl_merenda', 'label': 'Merenda', 'valido_ate': '16:30'},
    'jantar': {'flag': 'fl_jantar', 'label': 'Jantar', 'valido_ate': '19:30'},
    'ceia': {'flag': 'fl_ceia', 'label': 'Ceia', 'valido_ate': '22:30'},
}

MODELOS_ETIQUETA_PRE = [
    {'id': '6080', 'nome': '6080 (30 etiquetas)', 'cols': 3, 'rows': 10, 'fonte': 7},
    {'id': '6082', 'nome': '6082 (14 etiquetas)', 'cols': 2, 'rows': 7, 'fonte': 8},
    {'id': 'A4350', 'nome': 'A4350 (10 etiquetas)', 'cols': 2, 'rows': 5, 'fonte': 8},
    {'id': 'A4356', 'nome': 'A4356 (33 etiquetas)', 'cols': 3, 'rows': 11, 'fonte': 6},
]

MODELOS_ETIQUETA_CUSTOM_FALLBACK = [
    {'id': 'custom_6080_7pt', 'nome': '1 - PIMACO 6080 (7PT) - PADRÃO DIETAS', 'base': '6080', 'fonte': 7},
    {'id': 'custom_6080', 'nome': '2 - PIMACO 6080 - PADRÃO DIETAS', 'base': '6080', 'fonte': 7},
    {'id': 'custom_50x40', 'nome': '3 - ETIQUETADORA COZINHA (50X40) - DIETA', 'base': '6082', 'fonte': 8},
    {'id': 'custom_6080_6pt', 'nome': 'PIMACO 6080 (6PT) - MODELO 6080 (6PT)', 'base': '6080', 'fonte': 6},
]


def list_modelos_etiqueta_impressao():
    """Modelos pré-configurados + personalizados (cadastro NutEtiqueta ou fallback)."""
    customs = []
    nomes_vistos = set()
    for e in list_etiquetas(somente_ativas=True):
        nome = (e.get('nome') or '').strip()
        if not nome:
            continue
        nome_u = nome.upper()
        if '6080' in nome_u:
            base = '6080'
        elif '6082' in nome_u or '50X40' in nome_u.replace(' ', ''):
            base = '6082'
        elif 'A4350' in nome_u:
            base = 'A4350'
        elif 'A4356' in nome_u:
            base = 'A4356'
        else:
            base = '6080'
        display = nome if ('PADRÃO' in nome_u or 'DIETA' in nome_u) else f"{nome} - PADRÃO DIETAS"
        customs.append({
            'id': f"eti_{e['id']}",
            'nome': display,
            'base': base,
            'fonte': int(e.get('tamanho_fonte') or 7),
            'num_colunas': int(e.get('num_colunas') or 0) or None,
            'altura_etiqueta_mm': e.get('altura_etiqueta_mm') or 0,
        })
        nomes_vistos.add(display.upper())
        nomes_vistos.add(nome_u)
    for fb in MODELOS_ETIQUETA_CUSTOM_FALLBACK:
        if fb['nome'].upper() not in nomes_vistos and not any(
            fb['nome'].split(' - ')[0].upper() in n for n in nomes_vistos
        ):
            customs.append(dict(fb))
    if not customs:
        customs = list(MODELOS_ETIQUETA_CUSTOM_FALLBACK)
    return {
        'preconfigurados': MODELOS_ETIQUETA_PRE,
        'personalizados': customs,
    }


def _resolver_modelo_etiqueta(modelo_id):
    modelos = list_modelos_etiqueta_impressao()
    mid = (modelo_id or '6080').strip()
    def _pack(m):
        fonte = int(m.get('fonte') or 7)
        return {
            'id': m['id'],
            'nome': m['nome'],
            'cols': m['cols'],
            'rows': m['rows'],
            'fonte': fonte,
            'fonte_obs': max(fonte - 1, 5),
            'por_pagina': m['cols'] * m['rows'],
        }

    for m in modelos['preconfigurados']:
        if m['id'] == mid:
            return _pack(m)
    for m in modelos['personalizados']:
        if m['id'] == mid:
            base = next((p for p in MODELOS_ETIQUETA_PRE if p['id'] == m.get('base')), MODELOS_ETIQUETA_PRE[0])
            cols = m.get('num_colunas') or base['cols']
            rows = base['rows']
            if cols == 3 and base['id'] == '6080':
                rows = 10
            return _pack({
                'id': m['id'],
                'nome': m['nome'],
                'cols': cols,
                'rows': rows,
                'fonte': int(m.get('fonte') or base['fonte']),
            })
    return _pack(MODELOS_ETIQUETA_PRE[0])


def _obs_linha_etiqueta(row):
    parts = []
    for campo in ('obs_etiqueta', 'extras', 'observacoes', 'suplementos'):
        val = (getattr(row, campo, None) or '').strip()
        if val and val not in parts:
            parts.append(val)
    return ' '.join(parts)


def _fmt_dn(pac, idade=None):
    if pac and pac.nascimento:
        return pac.nascimento.strftime('%d/%m/%y')
    if idade is not None:
        try:
            return f'{int(idade)}a'
        except (TypeError, ValueError):
            pass
    return ''


def _fmt_leito(leito):
    s = (leito or '').strip()
    if not s:
        return ''
    # se já for só número, zera à esquerda (estilo legado L: 05)
    if s.isdigit():
        return s.zfill(2)
    return s


def gerar_impressao_etiquetas(
    data_ref=None,
    horario='desjejum',
    modo='mapa',
    imprimir_por='grupo_clinica',
    filtro_id=None,
    filtro_nome=None,
    ordenar='grupo_dieta_data',
    incluir_enfermaria=False,
    somente_alteradas=False,
    alteradas_desde=None,
    modelo_id='6080',
    seq_inicio=1,
):
    """Gera etiquetas de dieta a partir do mapa de refeições do dia."""
    data_ref = data_ref or date.today()
    garantir_mapa_do_dia(data_ref)
    hinfo = HORARIO_ETIQUETA.get(horario) or HORARIO_ETIQUETA['desjejum']
    flag = hinfo['flag']
    modelo = _resolver_modelo_etiqueta(modelo_id)

    q = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True)
    linhas = q.all()
    linhas = [l for l in linhas if getattr(l, flag, False)]

    filtro_nome = (filtro_nome or '').strip()
    if imprimir_por in ('grupo_clinica', 'clinica'):
        if filtro_nome:
            linhas = [l for l in linhas if (l.clinica or '').strip().upper() == filtro_nome.upper()]
        elif filtro_id:
            cli = NutClinica.query.get(int(filtro_id))
            if cli:
                filtro_nome = cli.nome or ''
                linhas = [l for l in linhas if (l.clinica or '').strip().upper() == filtro_nome.upper()]
    elif imprimir_por == 'enfermaria':
        if filtro_id:
            enf = NutEnfermaria.query.get(int(filtro_id))
            if enf:
                filtro_nome = enf.nome or filtro_nome
                nome_enf = (enf.nome or '').strip().upper()
                leitos = set()
                for lt in (enf.leitos or []):
                    if lt.nome:
                        leitos.add(lt.nome.strip().upper())
                    leitos.add(str(lt.numero).zfill(2))
                    leitos.add(str(lt.numero))
                filtradas = []
                for l in linhas:
                    enf_l = (l.enfermaria or '').strip().upper()
                    leito = (l.leito or '').strip().upper()
                    clinica = (l.clinica or '').strip().upper()
                    if enf_l == nome_enf or leito in leitos or clinica == nome_enf or nome_enf in clinica:
                        filtradas.append(l)
                linhas = filtradas
        elif filtro_nome:
            nome_enf = filtro_nome.upper()
            linhas = [
                l for l in linhas
                if (l.enfermaria or '').strip().upper() == nome_enf
                or (l.clinica or '').strip().upper() == nome_enf
            ]

    if somente_alteradas and alteradas_desde:
        try:
            if isinstance(alteradas_desde, str):
                hh, mm = alteradas_desde.strip().split(':')[:2]
                corte = datetime.combine(data_ref, datetime.min.time()).replace(
                    hour=int(hh), minute=int(mm), second=0, microsecond=0
                )
            else:
                corte = alteradas_desde
            linhas = [
                l for l in linhas
                if (l.data_atualizacao or l.data_inclusao or l.data_criacao) and
                (l.data_atualizacao or l.data_inclusao or l.data_criacao) >= corte
            ]
        except (ValueError, TypeError):
            pass

    dieta_cat_map = {
        (d.nome or '').strip().upper(): (d.categoria or 'basica')
        for d in NutDieta.query.all()
    }

    def sort_key(l):
        grupo = _grupo_dieta_totalizacao(l.dieta, dieta_cat_map)
        dieta = (l.dieta or '').upper()
        clinica = (l.clinica or '').upper()
        enf = (l.enfermaria or '').upper()
        leito = (l.leito or '').upper()
        data_s = data_ref.isoformat()
        if ordenar == 'clinica_enfermaria_dieta':
            return (clinica, enf, dieta, leito, (l.nome or '').upper())
        if ordenar == 'data_clinica_leito_dieta':
            return (data_s, clinica, leito, dieta, (l.nome or '').upper())
        if ordenar == 'clinica_enfermaria_leito':
            return (clinica, enf, leito, dieta, (l.nome or '').upper())
        # grupo; dieta; data; clinica; leito
        return (grupo, dieta, data_s, clinica, leito, (l.nome or '').upper())

    linhas = sorted(linhas, key=sort_key)

    try:
        seq = max(1, int(seq_inicio or 1))
    except (TypeError, ValueError):
        seq = 1

    data_label = data_ref.strftime('%d/%m/%y')
    etiquetas = []
    for l in linhas:
        pac = l.paciente
        setor = (l.clinica or '').strip()
        if incluir_enfermaria and (l.enfermaria or '').strip():
            setor = (l.enfermaria or '').strip()

        linha1_esq = f"{hinfo['label']}-Válido até {hinfo['valido_ate']}"
        linha1_dir = f"{data_label}  n° {seq:04d}-1"
        leito_fmt = _fmt_leito(l.leito)
        dn = _fmt_dn(pac, l.idade)
        etiquetas.append({
            'seq': seq,
            'linha1_esq': linha1_esq,
            'linha1_dir': linha1_dir,
            'setor': (setor or '').upper(),
            'leito': leito_fmt,
            'nome': (l.nome or '').upper(),
            'dn': dn,
            'dieta': (l.dieta or '').upper(),
            'obs': _obs_linha_etiqueta(l),
            'clinica': l.clinica or '',
            'enfermaria': l.enfermaria or '',
        })
        seq += 1

    # páginas com células vazias para completar grade
    por_pagina = modelo['por_pagina']
    paginas = []
    if etiquetas:
        for i in range(0, len(etiquetas), por_pagina):
            chunk = etiquetas[i:i + por_pagina]
            while len(chunk) < por_pagina:
                chunk.append(None)
            paginas.append(chunk)
    else:
        paginas = [[None] * por_pagina]

    return {
        'data': data_ref.isoformat(),
        'data_label': data_label,
        'horario': horario,
        'horario_label': hinfo['label'],
        'valido_ate': hinfo['valido_ate'],
        'modo': modo,
        'imprimir_por': imprimir_por,
        'filtro_nome': filtro_nome or 'TODOS',
        'ordenar': ordenar,
        'incluir_enfermaria': bool(incluir_enfermaria),
        'modelo': modelo,
        'etiquetas': etiquetas,
        'paginas': paginas,
        'total': len(etiquetas),
    }
