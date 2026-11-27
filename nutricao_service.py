"""Seed inicial e helpers do módulo de nutrição."""
from datetime import date, datetime, timedelta
import json
import re
import unicodedata
from models import db, now_brasilia, fmt_brasilia
from models_nutricao import (
    NutClinica, NutGrupoClinica, NutEnfermaria, NutLeito,     NutDieta, NutDietaExcluida,
    NutGrupoDieta, NutGrupoDietaExcluido, NutCategoriaDieta, NutPaciente, NutMapaRefeicao, NutCardapio,
    NutItemCardapio, CAMPOS_ITEM_CARDAPIO,
    NutTabelaNutrientes, NutAlimento, NutAlimentoNutriente, NutPratoLiquido,
    NutEstoqueLocal, NutUnidadeMedida, NutGrupoProduto, NutProduto, NutFornecedor,
    NutEtiqueta, NutEtiquetaCampo, NutPrecoRefeicao, NutTipoRefeicao, NutPrecoDietaTipo,
    NutRefeicaoAcompanhante, NutRefeicaoFuncionario,
    NutAvaliacaoNutricional, NutEvolucaoPaciente,
    NutViaAdministracao, NutUmaItem, NutUmaOpcao, NutConfigUma,
    limpar_indice_nome,
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
    CATEGORIAS_DIETA_SEED,
    precos_dict_da_tupla,
)
from nutricao_seed_cardapios import CARDAPIOS_SEED, CARDAPIO_OPCOES
from nutricao_seed_nutricional import ALIMENTOS_SEED, NUTRIENTES_PADRAO
from nutricao_seed_pratos_liquidos import PRATOS_LIQUIDOS_SEED
from nutricao_seed_uma import VIAS_ADMINISTRACAO_SEED, itens_uma_seed
from nutricao_seed_produtos import (
    ESTOQUES_SEED, UNIDADES_SEED, GRUPOS_PRODUTO_SEED, PRODUTOS_SEED,
)
from nutricao_seed_fornecedores import FORNECEDORES_SEED, ESTADOS_BR
from nutricao_seed_etiquetas import ETIQUETAS_SEED
from nutricao_tenant import (
    apply_cliente_filter,
    ensure_cliente_hfb,
    current_cliente_id,
    write_cliente_id,
)

# Seed/migração leve: roda no máximo 1× por processo (todas as abas chamavam a cada request).
_ENSURE_COLUMNS_DONE = False
_SEED_NUTRICAO_DONE = False
# Histórico do mapa: olha no máximo N dias atrás ao preencher buracos (evita carregar anos).
_MAPA_LOOKBACK_DIAS = 60
# data -> carimbo do histórico. Troca de clínica no mesmo dia não relê 60 dias se nada mudou.
_MAPA_GARANTIDO = {}

SEXO_LABELS = {
    'M': 'Masculino',
    'F': 'Feminino',
    'O': 'Outros',
}
SEXO_ALIASES = {
    'm': 'M',
    'masculino': 'M',
    'male': 'M',
    'f': 'F',
    'feminino': 'F',
    'female': 'F',
    'o': 'O',
    'outro': 'O',
    'outros': 'O',
    'other': 'O',
}


def normalizar_sexo(valor):
    """Aceita M/F/O ou os nomes masculino/feminino/outros."""
    raw = (valor or '').strip()
    if not raw:
        return None
    alias = SEXO_ALIASES.get(raw.lower())
    if alias:
        return alias
    up = raw.upper()
    if up in SEXO_LABELS:
        return up
    return None


def sexo_label(valor):
    codigo = normalizar_sexo(valor) or (valor or '').strip().upper()
    return SEXO_LABELS.get(codigo, valor or '')


def _q(model, cliente_id=None):
    """Query scoped to current nutrition client when applicable."""
    return apply_cliente_filter(model.query, model, cliente_id=cliente_id)


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
    q = _q(NutDieta)
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [
        d.to_dict()
        for d in q.order_by(NutDieta.grupo, NutDieta.nome).all()
    ]


def list_grupos_dieta(somente_ativos=False):
    q = _q(NutGrupoDieta)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [
        g.to_dict()
        for g in q.order_by(NutGrupoDieta.ordem, NutGrupoDieta.nome).all()
    ]


def list_categorias_dieta(somente_ativos=False):
    q = _q(NutCategoriaDieta)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [
        c.to_dict()
        for c in q.order_by(NutCategoriaDieta.ordem, NutCategoriaDieta.nome).all()
    ]


def slug_categoria_dieta(nome):
    text = unicodedata.normalize('NFKD', str(nome or '')).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-zA-Z0-9]+', '_', text).strip('_').lower()
    return (text[:40] or 'categoria')


def codigo_categoria_unico(base, exclude_id=None):
    codigo = slug_categoria_dieta(base)
    n = 2
    candidate = codigo
    while True:
        q = _q(NutCategoriaDieta).filter(db.func.lower(NutCategoriaDieta.codigo) == candidate)
        if exclude_id:
            q = q.filter(NutCategoriaDieta.id != exclude_id)
        if not q.first():
            return candidate
        suffix = f'_{n}'
        candidate = codigo[: max(1, 40 - len(suffix))] + suffix
        n += 1


def _seed_categorias_dieta():
    """Garante categorias padrão do Bonsucesso + valores já usados nas dietas dele."""
    try:
        NutCategoriaDieta.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()

    cid = ensure_cliente_hfb().id
    for item in CATEGORIAS_DIETA_SEED:
        if isinstance(item, (list, tuple)):
            codigo = (item[0] or '').strip().lower()
            nome = (item[1] or '').strip() if len(item) > 1 else codigo
            try:
                ordem = int(item[2] if len(item) > 2 else 0)
            except (TypeError, ValueError):
                ordem = 0
        else:
            nome = (item or '').strip()
            codigo = slug_categoria_dieta(nome)
            ordem = 0
        if not codigo or not nome:
            continue
        row = NutCategoriaDieta.query.filter(
            NutCategoriaDieta.cliente_id == cid,
            db.func.lower(NutCategoriaDieta.codigo) == codigo,
        ).first()
        if not row:
            row = NutCategoriaDieta.query.filter(
                NutCategoriaDieta.cliente_id == cid,
                db.func.upper(NutCategoriaDieta.nome) == nome.upper(),
            ).first()
        if not row:
            db.session.add(NutCategoriaDieta(
                cliente_id=cid, codigo=codigo, nome=nome, ordem=ordem or 0, ativo=True,
            ))
        else:
            if not (row.codigo or '').strip():
                row.codigo = codigo
            if ordem and not (row.ordem or 0):
                row.ordem = ordem
            if not (row.nome or '').strip():
                row.nome = nome

    existentes = (
        db.session.query(NutDieta.categoria)
        .filter(
            NutDieta.cliente_id == cid,
            NutDieta.categoria.isnot(None),
            NutDieta.categoria != '',
        )
        .distinct()
        .all()
    )
    last = NutCategoriaDieta.query.filter_by(cliente_id=cid).order_by(NutCategoriaDieta.ordem.desc()).first()
    next_ordem = ((last.ordem or 0) + 10) if last else 60
    for (cat,) in existentes:
        codigo = slug_categoria_dieta(cat)
        if not codigo:
            continue
        if NutCategoriaDieta.query.filter(
            NutCategoriaDieta.cliente_id == cid,
            db.func.lower(NutCategoriaDieta.codigo) == codigo,
        ).first():
            continue
        nome = (cat or '').strip() or codigo
        db.session.add(NutCategoriaDieta(
            cliente_id=cid, codigo=codigo, nome=nome, ordem=next_ordem, ativo=True,
        ))
        next_ordem += 10
    db.session.flush()


def _seed_grupos_dieta():
    """Garante grupos de dieta do Bonsucesso + valores já usados nas dietas dele."""
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

    cid = ensure_cliente_hfb().id
    for nome, ordem in nomes_seed:
        if grupo_foi_excluido(nome, cid):
            continue
        row = NutGrupoDieta.query.filter(
            NutGrupoDieta.cliente_id == cid,
            db.func.upper(NutGrupoDieta.nome) == nome,
        ).first()
        if not row:
            db.session.add(NutGrupoDieta(nome=nome, ordem=ordem or 0, ativo=True, cliente_id=cid))
        elif ordem and not (row.ordem or 0):
            row.ordem = ordem

    existentes = (
        db.session.query(NutDieta.grupo)
        .filter(
            NutDieta.cliente_id == cid,
            NutDieta.grupo.isnot(None),
            NutDieta.grupo != '',
        )
        .distinct()
        .all()
    )
    last = NutGrupoDieta.query.filter_by(cliente_id=cid).order_by(NutGrupoDieta.ordem.desc()).first()
    next_ordem = ((last.ordem or 0) + 10) if last else 110
    for (grupo,) in existentes:
        nome = (grupo or '').strip().upper()
        if not nome or grupo_foi_excluido(nome, cid):
            continue
        if NutGrupoDieta.query.filter(
            NutGrupoDieta.cliente_id == cid,
            db.func.upper(NutGrupoDieta.nome) == nome,
        ).first():
            continue
        db.session.add(NutGrupoDieta(nome=nome, ordem=next_ordem, ativo=True, cliente_id=cid))
        next_ordem += 10
    db.session.flush()


def list_tipos_refeicao(somente_ativos=False):
    q = _q(NutTipoRefeicao)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [t.to_dict() for t in q.order_by(NutTipoRefeicao.ordem, NutTipoRefeicao.id).all()]


def list_clinicas(somente_ativas=False):
    q = _q(NutClinica)
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [c.to_dict() for c in q.order_by(NutClinica.nome).all()]


def list_grupos_clinica(somente_ativos=False, include_clinicas=False):
    q = _q(NutGrupoClinica)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [
        g.to_dict(include_clinicas=include_clinicas)
        for g in q.order_by(NutGrupoClinica.nome).all()
    ]


def nomes_clinicas_do_grupo(grupo_id=None, grupo_nome=None):
    """Nomes (uppercase) das clínicas vinculadas a um grupo."""
    row = None
    if grupo_id:
        try:
            row = _q(NutGrupoClinica).filter_by(id=int(grupo_id)).first()
        except (TypeError, ValueError):
            row = None
    if not row and grupo_nome:
        nome = (grupo_nome or '').strip().upper()
        if nome:
            row = _q(NutGrupoClinica).filter(db.func.upper(NutGrupoClinica.nome) == nome).first()
    if not row:
        return []
    return [(c.nome or '').strip().upper() for c in (row.clinicas or []) if (c.nome or '').strip()]


def expand_filtros_grupo_clinica(filtros):
    """Converte ids/nomes de grupo em rótulos e conjunto de clínicas."""
    filtros = [str(f).strip() for f in (filtros or []) if str(f).strip()]
    ids = []
    nomes_txt = []
    for f in filtros:
        if f.isdigit():
            ids.append(int(f))
        else:
            nomes_txt.append(f)
    labels = []
    nomes = set()
    rows = []
    if ids:
        rows.extend(_q(NutGrupoClinica).filter(NutGrupoClinica.id.in_(ids)).all())
    if nomes_txt:
        rows.extend(
            _q(NutGrupoClinica).filter(
                db.func.upper(NutGrupoClinica.nome).in_([n.upper() for n in nomes_txt])
            ).all()
        )
    seen = set()
    for g in rows:
        if g.id in seen:
            continue
        seen.add(g.id)
        labels.append(g.nome)
        for c in (g.clinicas or []):
            if c.nome:
                nomes.add(c.nome.strip().upper())
    for n in nomes_txt:
        if n.upper() not in { (x or '').upper() for x in labels }:
            # nome digitado que não é grupo: trata como clínica (legado)
            nomes.add(n.upper())
            labels.append(n)
    return labels, nomes


def list_enfermarias(somente_ativas=False):
    from sqlalchemy import func
    q = _q(NutEnfermaria)
    if somente_ativas:
        q = q.filter_by(ativo=True)
    rows = q.order_by(NutEnfermaria.nome).all()
    enf_ids = [e.id for e in rows]
    counts = {}
    if enf_ids:
        counts = dict(
            db.session.query(NutLeito.enfermaria_id, func.count(NutLeito.id))
            .filter(NutLeito.enfermaria_id.in_(enf_ids))
            .group_by(NutLeito.enfermaria_id)
            .all()
        )
    return [e.to_dict(num_leitos=counts.get(e.id, 0)) for e in rows]


def list_leitos(enfermaria_id=None, somente_ativos=False):
    q = NutLeito.query
    cid = current_cliente_id()
    if enfermaria_id:
        if cid is not None and not _q(NutEnfermaria).filter_by(id=enfermaria_id).first():
            return []
        q = q.filter_by(enfermaria_id=enfermaria_id)
    elif cid is not None:
        enf_ids = [e.id for e in _q(NutEnfermaria).with_entities(NutEnfermaria.id).all()]
        if not enf_ids:
            return []
        q = q.filter(NutLeito.enfermaria_id.in_(enf_ids))
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [l.to_dict() for l in q.order_by(NutLeito.numero, NutLeito.nome).all()]


def _limpar_cache_inspetor(insp):
    """SQLAlchemy 1.4 antigo não tem Inspector.clear_cache."""
    limpar = getattr(insp, 'clear_cache', None)
    if callable(limpar):
        limpar()


def _ensure_index(table, name, columns):
    """Cria índice em banco já existente. create_all não altera tabela antiga."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        if table not in set(insp.get_table_names()):
            return
        existentes = {ix['name'] for ix in insp.get_indexes(table)}
        if name in existentes:
            return
        cols = ', '.join(columns)
        sql = f'CREATE INDEX {name} ON {table} ({cols})'
        if db.engine.dialect.name == 'mysql':
            sql += ' ALGORITHM=INPLACE, LOCK=NONE'
        db.session.execute(text(sql))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _garantir_unico_uma_item():
    """O lactário repete o nome da fórmula quando o produto ou a unidade muda."""
    from sqlalchemy import inspect, text
    try:
        if db.engine.dialect.name != 'mysql':
            return
        insp = inspect(db.engine)
        if 'nut_uma_itens' not in set(insp.get_table_names()):
            return
        unicos = insp.get_unique_constraints('nut_uma_itens') or []
        atual = next((u for u in unicos if u.get('name') == 'uq_nut_uma_item'), None)
        cols = list((atual or {}).get('column_names') or [])
        if 'produto_principal' in cols and 'unidade' in cols:
            return
        db.session.execute(text(
            "UPDATE nut_uma_itens SET produto_principal = '' WHERE produto_principal IS NULL"
        ))
        db.session.execute(text(
            "UPDATE nut_uma_itens SET unidade = '' WHERE unidade IS NULL"
        ))
        db.session.execute(text(
            "UPDATE nut_uma_itens SET sistema = '' WHERE sistema IS NULL"
        ))
        db.session.execute(text(
            "UPDATE nut_uma_itens SET papel = '' WHERE papel IS NULL"
        ))
        db.session.execute(text('ALTER TABLE nut_uma_itens DROP INDEX uq_nut_uma_item'))
        db.session.execute(text(
            'ALTER TABLE nut_uma_itens ADD UNIQUE KEY uq_nut_uma_item '
            '(cliente_id, tipo, sistema, papel, manipulado, nome, produto_principal, unidade)'
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _ensure_nutricao_columns(force=False):
    """Adiciona colunas novas em tabelas já existentes (create_all não altera).

    Executa uma vez por processo; reinicie o app após deploy de schema.
    """
    global _ENSURE_COLUMNS_DONE
    if _ENSURE_COLUMNS_DONE and not force:
        return
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
                'dieta_id': 'INTEGER',
                'tipo_lancamento': "VARCHAR(20) DEFAULT 'principal'",
                'lancamento_grupo_id': 'INTEGER',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE nut_mapa_refeicoes ADD COLUMN {col} {tipo}'))
            db.session.commit()
            cols = {c['name'] for c in insp.get_columns('nut_mapa_refeicoes')}
            if 'tipo_lancamento' in cols:
                db.session.execute(text(
                    "UPDATE nut_mapa_refeicoes SET tipo_lancamento = 'principal' "
                    "WHERE tipo_lancamento IS NULL OR tipo_lancamento = ''"
                ))
            if 'lancamento_grupo_id' in cols:
                db.session.execute(text(
                    'UPDATE nut_mapa_refeicoes SET lancamento_grupo_id = id '
                    'WHERE lancamento_grupo_id IS NULL'
                ))
            db.session.commit()
            _ensure_index('nut_mapa_refeicoes', 'ix_nut_mapa_data_ativo', ('data_refeicao', 'ativo'))
        if 'nut_pacientes' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_pacientes')}
            if 'hora_saida' not in cols:
                db.session.execute(text("ALTER TABLE nut_pacientes ADD COLUMN hora_saida VARCHAR(20)"))
            if 'motivo_saida' not in cols:
                db.session.execute(text("ALTER TABLE nut_pacientes ADD COLUMN motivo_saida VARCHAR(40)"))
            if 'enfermaria' not in cols:
                db.session.execute(text("ALTER TABLE nut_pacientes ADD COLUMN enfermaria VARCHAR(120)"))
            if 'excluido' not in cols:
                db.session.execute(text(
                    "ALTER TABLE nut_pacientes ADD COLUMN excluido BOOLEAN DEFAULT 0"
                ))
            if 'codigo_legado' not in cols:
                db.session.execute(text(
                    "ALTER TABLE nut_pacientes ADD COLUMN codigo_legado INT NULL"
                ))
            if 'unificado_em_id' not in cols:
                db.session.execute(text(
                    "ALTER TABLE nut_pacientes ADD COLUMN unificado_em_id INT NULL"
                ))
            db.session.commit()
            _ensure_index('nut_pacientes', 'ix_nut_pacientes_nome', ('nome',))
            _ensure_index('nut_pacientes', 'ix_nut_pacientes_prontuario', ('prontuario',))
            _ensure_index('nut_pacientes', 'ix_nut_pacientes_codigo_legado', ('cliente_id', 'codigo_legado'))
            _ensure_index('nut_pacientes', 'ix_nut_pacientes_unificado_em', ('unificado_em_id',))
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
                'formula': 'BOOLEAN DEFAULT 0',
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
                _limpar_cache_inspetor(insp)
        if 'nut_tipos_refeicao' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_tipos_refeicao')}
            if 'hora_limite' not in cols:
                db.session.execute(text("ALTER TABLE nut_tipos_refeicao ADD COLUMN hora_limite VARCHAR(5) NULL"))
                db.session.commit()
                _limpar_cache_inspetor(insp)
        if 'nut_cardapios' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_cardapios')}
            if 'dieta_id' not in cols:
                db.session.execute(text('ALTER TABLE nut_cardapios ADD COLUMN dieta_id INTEGER NULL'))
                db.session.commit()
                _limpar_cache_inspetor(insp)
        if 'nut_alimentos' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_alimentos')}
            if 'fdc_id' not in cols:
                db.session.execute(text('ALTER TABLE nut_alimentos ADD COLUMN fdc_id INTEGER NULL'))
                db.session.commit()
                _limpar_cache_inspetor(insp)
            try:
                db.session.execute(text(
                    'CREATE UNIQUE INDEX uq_nut_alimento_tabela_fdc '
                    'ON nut_alimentos (tabela_id, fdc_id)'
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
        if 'nut_refeicao_funcionarios' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_refeicao_funcionarios')}
            alteracoes = {
                'quantidade': 'INTEGER DEFAULT 1',
                'data_refeicao': 'DATE NULL',
                'fl_almoco': 'BOOLEAN DEFAULT 1',
                'fl_jantar': 'BOOLEAN DEFAULT 1',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    try:
                        db.session.execute(text(f'ALTER TABLE nut_refeicao_funcionarios ADD COLUMN {col} {tipo}'))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
            _limpar_cache_inspetor(insp)
            try:
                db.session.execute(text(
                    'UPDATE nut_refeicao_funcionarios SET data_refeicao = CURDATE() '
                    'WHERE data_refeicao IS NULL'
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
        if 'nut_refeicao_acompanhantes' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_refeicao_acompanhantes')}
            alteracoes = {
                'quantidade': 'INTEGER DEFAULT 1',
                'data_refeicao': 'DATE NULL',
                'fl_almoco': 'BOOLEAN DEFAULT 1',
                'fl_jantar': 'BOOLEAN DEFAULT 1',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    try:
                        db.session.execute(text(f'ALTER TABLE nut_refeicao_acompanhantes ADD COLUMN {col} {tipo}'))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
            _limpar_cache_inspetor(insp)
            try:
                db.session.execute(text(
                    'UPDATE nut_refeicao_acompanhantes SET data_refeicao = CURDATE() '
                    'WHERE data_refeicao IS NULL'
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
        ('nut_cardapios', 'item_1', 'ALTER TABLE nut_cardapios ADD COLUMN item_1 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_2', 'ALTER TABLE nut_cardapios ADD COLUMN item_2 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_3', 'ALTER TABLE nut_cardapios ADD COLUMN item_3 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_4', 'ALTER TABLE nut_cardapios ADD COLUMN item_4 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_5', 'ALTER TABLE nut_cardapios ADD COLUMN item_5 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_6', 'ALTER TABLE nut_cardapios ADD COLUMN item_6 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_7', 'ALTER TABLE nut_cardapios ADD COLUMN item_7 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_8', 'ALTER TABLE nut_cardapios ADD COLUMN item_8 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_9', 'ALTER TABLE nut_cardapios ADD COLUMN item_9 VARCHAR(255) NULL'),
        ('nut_cardapios', 'item_10', 'ALTER TABLE nut_cardapios ADD COLUMN item_10 VARCHAR(255) NULL'),
        ('nut_alimentos', 'fdc_id', 'ALTER TABLE nut_alimentos ADD COLUMN fdc_id INTEGER NULL'),
        ('nut_refeicao_funcionarios', 'quantidade',
         'ALTER TABLE nut_refeicao_funcionarios ADD COLUMN quantidade INTEGER DEFAULT 1'),
        ('nut_refeicao_funcionarios', 'data_refeicao',
         'ALTER TABLE nut_refeicao_funcionarios ADD COLUMN data_refeicao DATE NULL'),
        ('nut_refeicao_funcionarios', 'fl_almoco',
         'ALTER TABLE nut_refeicao_funcionarios ADD COLUMN fl_almoco BOOLEAN DEFAULT 1'),
        ('nut_refeicao_funcionarios', 'fl_jantar',
         'ALTER TABLE nut_refeicao_funcionarios ADD COLUMN fl_jantar BOOLEAN DEFAULT 1'),
        ('nut_refeicao_acompanhantes', 'quantidade',
         'ALTER TABLE nut_refeicao_acompanhantes ADD COLUMN quantidade INTEGER DEFAULT 1'),
        ('nut_refeicao_acompanhantes', 'data_refeicao',
         'ALTER TABLE nut_refeicao_acompanhantes ADD COLUMN data_refeicao DATE NULL'),
        ('nut_refeicao_acompanhantes', 'fl_almoco',
         'ALTER TABLE nut_refeicao_acompanhantes ADD COLUMN fl_almoco BOOLEAN DEFAULT 1'),
        ('nut_refeicao_acompanhantes', 'fl_jantar',
         'ALTER TABLE nut_refeicao_acompanhantes ADD COLUMN fl_jantar BOOLEAN DEFAULT 1'),
        ('nut_uma_itens', 'diluicao', "ALTER TABLE nut_uma_itens ADD COLUMN diluicao VARCHAR(40) DEFAULT ''"),
        ('nut_uma_itens', 'unidade', "ALTER TABLE nut_uma_itens ADD COLUMN unidade VARCHAR(20) DEFAULT ''"),
        ('nut_uma_itens', 'produto_disponivel',
         'ALTER TABLE nut_uma_itens ADD COLUMN produto_disponivel BOOLEAN DEFAULT 1'),
        ('nut_uma_itens', 'produto_principal',
         "ALTER TABLE nut_uma_itens ADD COLUMN produto_principal VARCHAR(200) DEFAULT ''"),
        ('nut_uma_itens', 'coluna_faturamento',
         "ALTER TABLE nut_uma_itens ADD COLUMN coluna_faturamento VARCHAR(80) DEFAULT ''"),
        ('nut_uma_itens', 'grupo', "ALTER TABLE nut_uma_itens ADD COLUMN grupo VARCHAR(80) DEFAULT ''"),
        ('nut_uma_itens', 'quant_padrao', "ALTER TABLE nut_uma_itens ADD COLUMN quant_padrao VARCHAR(40) DEFAULT ''"),
        ('nut_uma_itens', 'calorias', 'ALTER TABLE nut_uma_itens ADD COLUMN calorias FLOAT NULL'),
        ('nut_uma_itens', 'ptn', 'ALTER TABLE nut_uma_itens ADD COLUMN ptn FLOAT NULL'),
        ('nut_uma_itens', 'hc', 'ALTER TABLE nut_uma_itens ADD COLUMN hc FLOAT NULL'),
        ('nut_uma_itens', 'lip', 'ALTER TABLE nut_uma_itens ADD COLUMN lip FLOAT NULL'),
        ('nut_uma_itens', 'fibras', 'ALTER TABLE nut_uma_itens ADD COLUMN fibras FLOAT NULL'),
        ('nut_uma_itens', 'composicao', 'ALTER TABLE nut_uma_itens ADD COLUMN composicao TEXT'),
        ('nut_uma_itens', 'componentes', "ALTER TABLE nut_uma_itens ADD COLUMN componentes TEXT"),
        ('nut_uma_itens', 'cobranca', "ALTER TABLE nut_uma_itens ADD COLUMN cobranca VARCHAR(20) DEFAULT ''"),
    ):
        try:
            insp = inspect(db.engine)
            _limpar_cache_inspetor(insp)
            if table not in set(insp.get_table_names()):
                continue
            cols = {c['name'] for c in insp.get_columns(table)}
            if col not in cols:
                db.session.execute(text(ddl))
                db.session.commit()
                _limpar_cache_inspetor(insp)
        except Exception:
            db.session.rollback()

    try:
        insp = inspect(db.engine)
        if 'nut_uma_itens' in set(insp.get_table_names()):
            cols = {c['name'] for c in insp.get_columns('nut_uma_itens')}
            if 'produto_disponivel' in cols:
                db.session.execute(text(
                    'UPDATE nut_uma_itens SET produto_disponivel = 1 '
                    'WHERE produto_disponivel IS NULL'
                ))
                db.session.commit()
    except Exception:
        db.session.rollback()

    _garantir_unico_uma_item()

    try:
        NutDietaExcluida.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()

    try:
        NutGrupoDietaExcluido.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()

    try:
        NutCategoriaDieta.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()

    _backfill_cardapio_dieta_id()
    _backfill_cardapio_itens_colunas()
    _ENSURE_COLUMNS_DONE = True


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
        dietas = {}
        for d in NutDieta.query.all():
            if not d.nome:
                continue
            dietas.setdefault(d.cliente_id, {})[_n(d.nome)] = d.id
        if not dietas:
            return
        changed = False
        for row in NutCardapio.query.filter(
            NutCardapio.dieta_id.is_(None),
            NutCardapio.dieta.isnot(None),
        ).all():
            did = (dietas.get(row.cliente_id) or {}).get(_n(row.dieta))
            if did:
                row.dieta_id = did
                changed = True
        if changed:
            db.session.commit()
    except Exception:
        db.session.rollback()


def _backfill_cardapio_itens_colunas():
    """Copia o JSON antigo para item_1..item_10 quando as colunas ainda estão vazias."""
    import json
    try:
        from sqlalchemy import inspect
        insp = inspect(db.engine)
        if 'nut_cardapios' not in set(insp.get_table_names()):
            return
        cols = {c['name'] for c in insp.get_columns('nut_cardapios')}
        if 'item_1' not in cols:
            return
        changed = False
        for row in NutCardapio.query.all():
            if any(getattr(row, f'item_{i}', None) for i in range(1, 11)):
                continue
            try:
                data = json.loads(row.itens or '{}')
            except (TypeError, ValueError):
                data = {}
            if not isinstance(data, dict) or not data:
                continue
            row._gravar_colunas_item(data)
            changed = True
        if changed:
            db.session.commit()
    except Exception:
        db.session.rollback()


def _seed_enfermarias():
    cid = ensure_cliente_hfb().id
    for nome in ENFERMARIAS_SEED:
        nome = (nome or '').strip()
        if not nome:
            continue
        if not NutEnfermaria.query.filter_by(nome=nome, cliente_id=cid).first():
            db.session.add(NutEnfermaria(nome=nome, ativo=True, nutriz=False, cliente_id=cid))
    db.session.flush()

    # vínculos iniciais só na base do Bonsucesso, se a clínica ainda não tiver enfermaria
    for clinica_nome, nomes in VINCULOS_CLINICA_ENFERMARIA_SEED.items():
        clinica = NutClinica.query.filter_by(nome=clinica_nome, cliente_id=cid).first()
        if not clinica:
            continue
        if clinica.enfermarias:
            continue
        for nome_enf in nomes:
            enf = NutEnfermaria.query.filter_by(nome=nome_enf, cliente_id=cid).first()
            if enf and enf not in clinica.enfermarias:
                clinica.enfermarias.append(enf)


def list_cardapios(tipo=None, dieta_id=None):
    q = _q(NutCardapio).filter_by(ativo=True)
    if tipo:
        q = q.filter_by(tipo=tipo)
    dieta = None
    if dieta_id:
        dieta_id = int(dieta_id)
        dieta = _q(NutDieta).filter_by(id=dieta_id).first()
        nome = (dieta.nome or '').strip().upper() if dieta else ''
        cond = NutCardapio.dieta_id == dieta_id
        if nome:
            cond = db.or_(
                cond,
                db.and_(
                    NutCardapio.dieta_id.is_(None),
                    db.func.upper(NutCardapio.dieta) == nome,
                ),
            )
        q = q.filter(cond)
    rows = q.order_by(NutCardapio.dia_mes, NutCardapio.dieta, NutCardapio.id).all()
    if dieta is not None:
        changed = False
        for row in rows:
            if not row.dieta_id:
                row.dieta_id = dieta.id
                if not (row.dieta or '').strip():
                    row.dieta = dieta.nome
                changed = True
        if changed:
            db.session.commit()
    return [c.to_dict() for c in rows]


def _ensure_dietas_excluidas_table():
    try:
        NutDietaExcluida.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()


def _norm_dieta_nome(nome):
    return (nome or '').strip().upper()


def dieta_foi_excluida(nome, cliente_id=None):
    """True se o nome foi removido do cadastro e o seed não deve recriar."""
    nome = _norm_dieta_nome(nome)
    if not nome:
        return False
    _ensure_dietas_excluidas_table()
    q = NutDietaExcluida.query.filter(db.func.upper(NutDietaExcluida.nome) == nome)
    if cliente_id is not None:
        q = q.filter(NutDietaExcluida.cliente_id == cliente_id)
    return q.first() is not None


def marcar_dieta_excluida(nome, cliente_id=None):
    nome = _norm_dieta_nome(nome)
    if not nome:
        return
    _ensure_dietas_excluidas_table()
    q = NutDietaExcluida.query.filter(db.func.upper(NutDietaExcluida.nome) == nome)
    if cliente_id is not None:
        q = q.filter(NutDietaExcluida.cliente_id == cliente_id)
    if q.first():
        return
    db.session.add(NutDietaExcluida(nome=nome, cliente_id=cliente_id))


def _ensure_grupos_excluidos_table():
    try:
        NutGrupoDietaExcluido.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()


def _cliente_grupo_excluido(cliente_id):
    if cliente_id is not None:
        return cliente_id
    try:
        return ensure_cliente_hfb().id
    except Exception:
        return None


def grupo_foi_excluido(nome, cliente_id=None):
    """True se o grupo foi apagado na lixeira e o seed não deve recriar."""
    nome = (nome or '').strip().upper()
    if not nome:
        return False
    _ensure_grupos_excluidos_table()
    q = NutGrupoDietaExcluido.query.filter(db.func.upper(NutGrupoDietaExcluido.nome) == nome)
    cid = _cliente_grupo_excluido(cliente_id)
    if cid is not None:
        q = q.filter(db.or_(
            NutGrupoDietaExcluido.cliente_id == cid,
            NutGrupoDietaExcluido.cliente_id.is_(None),
        ))
    return q.first() is not None


def marcar_grupo_dieta_excluido(nome, cliente_id=None):
    nome = (nome or '').strip().upper()
    if not nome:
        return
    _ensure_grupos_excluidos_table()
    cid = _cliente_grupo_excluido(cliente_id)
    if grupo_foi_excluido(nome, cid):
        return
    db.session.add(NutGrupoDietaExcluido(nome=nome, cliente_id=cid))


def liberar_grupo_dieta_excluido(nome, cliente_id=None):
    """Permite cadastrar de novo um grupo que tinha sido excluído."""
    nome = (nome or '').strip().upper()
    if not nome:
        return
    _ensure_grupos_excluidos_table()
    q = NutGrupoDietaExcluido.query.filter(db.func.upper(NutGrupoDietaExcluido.nome) == nome)
    cid = _cliente_grupo_excluido(cliente_id)
    if cid is not None:
        q = q.filter(db.or_(
            NutGrupoDietaExcluido.cliente_id == cid,
            NutGrupoDietaExcluido.cliente_id.is_(None),
        ))
    q.delete(synchronize_session=False)


def excluir_grupo_dieta(row):
    """Apaga o grupo do cadastro e impede o seed de recriá-lo."""
    nome = (row.nome or '').strip().upper()
    marcar_grupo_dieta_excluido(nome, getattr(row, 'cliente_id', None))
    db.session.delete(row)
    return nome


def liberar_dieta_excluida(nome, cliente_id=None):
    """Permite cadastrar de novo um nome que tinha sido excluído."""
    nome = _norm_dieta_nome(nome)
    if not nome:
        return
    _ensure_dietas_excluidas_table()
    q = NutDietaExcluida.query.filter(db.func.upper(NutDietaExcluida.nome) == nome)
    if cliente_id is not None:
        q = q.filter(NutDietaExcluida.cliente_id == cliente_id)
    q.delete(synchronize_session=False)


def excluir_dieta_e_cardapios(dieta):
    """Remove a dieta do cadastro, cardápios e preços vinculados."""
    dieta_id = dieta.id
    nome = _norm_dieta_nome(dieta.nome)
    cliente_id = getattr(dieta, 'cliente_id', None)

    filtros = []
    if dieta_id:
        filtros.append(NutCardapio.dieta_id == dieta_id)
    if nome:
        filtros.append(db.func.upper(NutCardapio.dieta) == nome)
    cards = _q(NutCardapio).filter(db.or_(*filtros)).all() if filtros else []
    qtd = len(cards)
    for card in cards:
        db.session.delete(card)

    if dieta_id:
        NutPrecoDietaTipo.query.filter_by(dieta_id=dieta_id).delete(synchronize_session=False)
        NutMapaRefeicao.query.filter_by(dieta_id=dieta_id).update(
            {NutMapaRefeicao.dieta_id: None}, synchronize_session=False
        )
        NutRefeicaoAcompanhante.query.filter_by(dieta_id=dieta_id).update(
            {NutRefeicaoAcompanhante.dieta_id: None}, synchronize_session=False
        )
        NutRefeicaoFuncionario.query.filter_by(dieta_id=dieta_id).update(
            {NutRefeicaoFuncionario.dieta_id: None}, synchronize_session=False
        )

    marcar_dieta_excluida(nome, cliente_id)
    db.session.delete(dieta)
    return qtd


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
MEAL_FLAG_FIELD = {
    'desjejum': 'fl_desjejum',
    'colacao': 'fl_colacao',
    'almoco': 'fl_almoco',
    'merenda': 'fl_merenda',
    'jantar': 'fl_jantar',
    'ceia': 'fl_ceia',
}
FLAG_TO_MEAL = {v: k for k, v in MEAL_FLAG_FIELD.items()}
MEAL_LABELS = {
    'desjejum': 'Desjejum',
    'colacao': 'Colação',
    'almoco': 'Almoço',
    'merenda': 'Merenda',
    'jantar': 'Jantar',
    'ceia': 'Ceia',
}
# Siglas do cadastro de tipos → chave interna da refeição
_TIPO_SIGLA_TO_MEAL = {
    'DESJ': 'desjejum', 'D': 'desjejum',
    'COL': 'colacao', 'C': 'colacao',
    'ALM': 'almoco', 'A': 'almoco',
    'MER': 'merenda', 'M': 'merenda',
    'JAN': 'jantar', 'J': 'jantar',
    'CEI': 'ceia', 'CE': 'ceia',
}
_TIPO_NOME_TO_MEAL = {
    'DESJEJUM': 'desjejum',
    'COLACAO': 'colacao', 'COLAÇÃO': 'colacao',
    'ALMOCO': 'almoco', 'ALMOÇO': 'almoco',
    'MERENDA': 'merenda',
    'JANTAR': 'jantar',
    'CEIA': 'ceia',
}


def tipo_refeicao_para_meal(valor):
    """Aceita chave (almoco), sigla (ALM) ou nome (Almoço) e devolve a chave interna."""
    import unicodedata
    if not valor:
        return ''
    s = str(valor).strip()
    low = s.lower()
    if low in MEAL_FLAG_FIELD:
        return low
    up = s.upper()
    meal = _TIPO_SIGLA_TO_MEAL.get(up) or _TIPO_NOME_TO_MEAL.get(up)
    if meal:
        return meal
    nome_n = ''.join(
        c for c in unicodedata.normalize('NFKD', up)
        if not unicodedata.combining(c)
    ).strip()
    return {
        'DESJEJUM': 'desjejum', 'COLACAO': 'colacao', 'ALMOCO': 'almoco',
        'MERENDA': 'merenda', 'JANTAR': 'jantar', 'CEIA': 'ceia',
    }.get(nome_n, '')


def list_tipos_refeicao_impressao():
    """Tipos ativos do cadastro com chave interna para filtros de impressão."""
    tipos = []
    vistos = set()
    for t in list_tipos_refeicao(somente_ativos=True):
        meal = tipo_refeicao_para_meal(t.get('sigla') or t.get('nome'))
        if not meal or meal in vistos:
            continue
        vistos.add(meal)
        tipos.append({
            'chave': meal,
            'nome': t.get('nome') or MEAL_LABELS.get(meal, meal),
            'sigla': t.get('sigla') or '',
        })
    if not tipos:
        tipos = [
            {'chave': chave, 'nome': nome, 'sigla': ''}
            for chave, nome in MEAL_LABELS.items()
        ]
    return tipos


def mapa_horas_limite():
    """Retorna {meal_key: 'HH:MM'} a partir do cadastro de tipos de refeição."""
    out = {}
    for t in NutTipoRefeicao.query.filter_by(ativo=True).all():
        meal = tipo_refeicao_para_meal(t.sigla) or tipo_refeicao_para_meal(t.nome)
        hora = normalizar_hora_limite(getattr(t, 'hora_limite', None))
        if meal and hora:
            out[meal] = hora
    return out


def _agora_brasilia():
    return now_brasilia()


def refeicao_apos_hora_limite(meal, data_mapa, agora=None):
    """True se, no dia do mapa (= hoje), já passou a hora limite da refeição.

    - Dia futuro: ainda aberto (salva no próprio dia).
    - Dia passado: histórico — não adia.
    - Hoje após hora limite: adia para o dia seguinte.
    """
    if meal not in MEALS_SUBST:
        return False
    agora = agora or _agora_brasilia()
    hoje = agora.date() if hasattr(agora, 'date') else date.today()
    data_mapa = data_mapa or hoje
    if data_mapa != hoje:
        return False
    hora = mapa_horas_limite().get(meal)
    if not hora:
        return False
    try:
        parts = hora.split(':')
        hh, mm = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return False
    limite = datetime(hoje.year, hoje.month, hoje.day, hh, mm, 0)
    return agora >= limite


def data_destino_lancamento(meal, data_mapa, agora=None):
    """Data em que a alteração da refeição deve ser lançada/salva."""
    data_mapa = data_mapa or date.today()
    if refeicao_apos_hora_limite(meal, data_mapa, agora=agora):
        return data_mapa + timedelta(days=1)
    return data_mapa


def info_lancamento_refeicoes(data_mapa, agora=None):
    """Metadados de hora limite / destino por refeição (para UI e API)."""
    agora = agora or _agora_brasilia()
    horas = mapa_horas_limite()
    out = {}
    for meal in MEALS_SUBST:
        apos = refeicao_apos_hora_limite(meal, data_mapa, agora=agora)
        dest = data_destino_lancamento(meal, data_mapa, agora=agora)
        hora = horas.get(meal) or ''
        out[meal] = {
            'meal': meal,
            'label': MEAL_LABELS.get(meal, meal),
            'hora_limite': hora,
            'apos_limite': apos,
            'data_mapa': data_mapa.isoformat() if data_mapa else '',
            'data_destino': dest.isoformat() if dest else '',
            'data_destino_label': dest.strftime('%d/%m/%Y') if dest else '',
            'aviso': (
                f'Após {hora}, alterações de {MEAL_LABELS.get(meal, meal)} '
                f'só podem ser aplicadas em {dest.strftime("%d/%m/%Y")}.'
                if apos and hora else ''
            ),
        }
    return out


def _filtro_mesmo_cliente(query, model, cliente_id):
    if cliente_id is None:
        return query.filter(model.cliente_id.is_(None))
    return query.filter(model.cliente_id == cliente_id)


def _candidatos_mapa_sem_paciente(data_alvo, src, somente_ativos=True):
    """Linhas sem paciente_id na data, já filtradas no banco pela chave disponível."""
    if not src or not data_alvo:
        return []
    q = NutMapaRefeicao.query.filter(
        NutMapaRefeicao.data_refeicao == data_alvo,
        NutMapaRefeicao.paciente_id.is_(None),
    )
    q = _filtro_mesmo_cliente(q, NutMapaRefeicao, getattr(src, 'cliente_id', None))
    if somente_ativos:
        q = q.filter(NutMapaRefeicao.ativo.is_(True))
    pront = (getattr(src, 'prontuario', None) or '').strip()
    nome = (getattr(src, 'nome', None) or '').strip()
    leito = (getattr(src, 'leito', None) or '').strip()
    if pront:
        q = q.filter(db.func.upper(NutMapaRefeicao.prontuario) == pront.upper())
    elif nome:
        q = q.filter(db.func.upper(NutMapaRefeicao.nome) == nome.upper())
        if leito:
            q = q.filter(db.func.upper(NutMapaRefeicao.leito) == leito.upper())
    elif leito:
        q = q.filter(db.func.upper(NutMapaRefeicao.leito) == leito.upper())
    else:
        return []
    return q.all()


def buscar_linha_mapa_dia(src, data_alvo):
    """Localiza a linha do mesmo lançamento em data_alvo (não cria)."""
    if not src or not data_alvo:
        return None
    if src.data_refeicao == data_alvo:
        return src
    gid = getattr(src, 'lancamento_grupo_id', None)
    if gid:
        row = (
            _filtro_mesmo_cliente(
                NutMapaRefeicao.query.filter_by(
                    data_refeicao=data_alvo, lancamento_grupo_id=gid, ativo=True,
                ),
                NutMapaRefeicao,
                getattr(src, 'cliente_id', None),
            )
            .order_by(NutMapaRefeicao.id.desc())
            .first()
        )
        if row:
            return row
    if src.paciente_id:
        tipo = normalizar_tipo_lancamento(getattr(src, 'tipo_lancamento', None))
        dieta = (src.dieta or '').strip().upper()
        q = (
            _filtro_mesmo_cliente(
                NutMapaRefeicao.query.filter_by(
                    data_refeicao=data_alvo, paciente_id=src.paciente_id, ativo=True,
                ),
                NutMapaRefeicao,
                getattr(src, 'cliente_id', None),
            )
            .order_by(NutMapaRefeicao.id.desc())
        )
        candidatos = q.all()
        for row in candidatos:
            if normalizar_tipo_lancamento(getattr(row, 'tipo_lancamento', None)) == tipo and (
                (row.dieta or '').strip().upper() == dieta
            ):
                return row
        if len(candidatos) == 1:
            return candidatos[0]
    for r in _candidatos_mapa_sem_paciente(data_alvo, src, somente_ativos=True):
        if _chave_linha_mapa(r) == _chave_linha_mapa(src):
            return r
    return None


def obter_ou_criar_linha_mapa_dia(src, data_alvo, usuario=None):
    """Localiza (ou cria a partir de src) a linha do paciente em data_alvo."""
    if not src or not data_alvo:
        return None
    if src.data_refeicao == data_alvo:
        return src

    existing = buscar_linha_mapa_dia(src, data_alvo)
    if existing:
        return existing

    garantir_mapa_do_dia(data_alvo)
    existing = buscar_linha_mapa_dia(src, data_alvo)
    if existing:
        return existing

    if getattr(src, 'lancamento_grupo_id', None):
        existing = (
            NutMapaRefeicao.query
            .filter_by(data_refeicao=data_alvo, lancamento_grupo_id=src.lancamento_grupo_id)
            .order_by(NutMapaRefeicao.id.desc())
            .first()
        )
    elif src.paciente_id:
        existing = (
            NutMapaRefeicao.query
            .filter_by(data_refeicao=data_alvo, paciente_id=src.paciente_id)
            .order_by(NutMapaRefeicao.id.desc())
            .first()
        )
    if not existing:
        chave = _chave_linha_mapa(src)
        for r in _candidatos_mapa_sem_paciente(data_alvo, src, somente_ativos=False):
            if _chave_linha_mapa(r) == chave:
                existing = r
                break
    if existing:
        if _linha_com_baixa(existing):
            return None
        if not existing.ativo:
            existing.ativo = True
            existing.data_saida = None
            existing.motivo_saida = None
            existing.hospital_transferencia = None
        return existing

    clone = _clonar_linha_mapa(src, data_alvo, usuario=usuario)
    db.session.add(clone)
    db.session.flush()
    garantir_grupo_lancamento(clone)
    return clone


_ITENS_ORDEM = {
    'grandes': [
        'acompanhamento', 'prato_base', 'proteina_opcional', 'proteico_opcional',
        'guarnicao', 'docinho_salada', 'diversos_salada', 'sobremesa', 'fruta',
        'suco', 'vitamina_suco', 'entrada_sopa', 'bebida', 'molhos', 'outros',
    ],
    'pequenas': [
        'bebida', 'prato1', 'prato2', 'prato3', 'prato4', 'prato5', 'prato6', 'prato7', 'sobremesa', 'prato8',
    ],
    'liquidas': [
        'principal', 'bebida', 'sobremesa', 'gelado', 'outros',
    ],
}
_ITENS_SKIP = {
    'entrada_tipo', 'proteico_tipo', 'proteina_tipo',
    'conv_bebida_coluna', 'conv_bebida_quant',
    'conv_gelado_coluna', 'conv_gelado_quant',
    'modo_prato',
}


def _vals_prato(val):
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x).strip() for x in val if str(x).strip()]
    text = str(val).strip()
    return [text] if text else []


def _chave_item_cardapio(key):
    k = str(key or '')
    if k.endswith('_extras'):
        return k[:-7]
    return k


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


def pratos_from_itens(itens, tipo=None, incluir_extras=True):
    """Extrai lista ordenada de pratos a partir do JSON de itens do cardápio.

    incluir_extras=False omite a alimentação complementar (itens extras do cardápio).
    """
    itens = itens or {}
    if not isinstance(itens, dict):
        return []
    ordem = list(_ITENS_ORDEM.get(tipo or '', []))
    for k in itens.keys():
        base = _chave_item_cardapio(k)
        if base not in ordem and base not in _ITENS_SKIP and not str(base).startswith('conv_'):
            ordem.append(base)
    seen_keys = set()
    seen = set()
    out = []
    for key in ordem:
        base = _chave_item_cardapio(key)
        if base in seen_keys:
            continue
        seen_keys.add(base)
        if base in _ITENS_SKIP or str(base).endswith('_tipo'):
            continue
        valores = _vals_prato(itens.get(base))
        if incluir_extras:
            valores = valores + _vals_prato(itens.get(f'{base}_extras'))
        for text in valores:
            up = _norm_txt(text)
            if not up or up in seen:
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


class _CardapioResolvido:
    """Cardápio já escolhido, sem voltar ao banco nem reparsear o JSON."""

    __slots__ = ('id', 'dieta', 'tipo', 'pratos', 'itens')

    def __init__(self, entry):
        self.id = entry[3]
        self.dieta = entry[4]
        self.tipo = entry[5]
        self.pratos = entry[6]
        self.itens = entry[7] if len(entry) > 7 else None


# Índice em memória por cliente: uma leitura de nut_cardapios, não 6 por abertura.
_CARDAPIO_POR_REFEICAO = {}
# Recorte por dieta: abrir o editor não lê a tabela inteira.
_CARDAPIO_POR_DIETA = {}


def invalidar_cache_cardapios():
    global _CARDAPIO_POR_REFEICAO
    _CARDAPIO_POR_REFEICAO = {}
    _CARDAPIO_POR_DIETA.clear()


def _entries_cardapio(rows, guardar_itens=False):
    by_meal = {m: [] for m in MEALS_SUBST}
    for row in rows:
        itens = row.get_itens() if guardar_itens else None
        pratos = pratos_from_itens(itens if guardar_itens else row.get_itens(), row.tipo)
        entry = (
            int(row.dieta_id) if row.dieta_id else None,
            row.dia_mes,
            row.id or 0,
            row.id,
            row.dieta or '',
            row.tipo or '',
            pratos,
        )
        if guardar_itens:
            entry = entry + (itens,)
        for meal in MEALS_SUBST:
            if getattr(row, MEAL_HR_FIELD[meal], False):
                by_meal[meal].append(entry)
    return by_meal


def cardapios_por_refeicao():
    """Lista leve de cardápios ativos do cliente atual, agrupada pelo horário (hr_*)."""
    global _CARDAPIO_POR_REFEICAO
    key = current_cliente_id()
    cached = _CARDAPIO_POR_REFEICAO.get(key)
    if cached is not None:
        return cached
    rows = _q(NutCardapio).filter_by(ativo=True).all()
    built = _entries_cardapio(rows, guardar_itens=False)
    _CARDAPIO_POR_REFEICAO[key] = built
    return built


def _indice_cardapios_dieta(dieta, dieta_id):
    """Só os cardápios desta dieta. Uma consulta, reusada nas 6 refeições."""
    dieta_id_int = None
    if dieta_id:
        try:
            dieta_id_int = int(dieta_id)
        except (TypeError, ValueError):
            dieta_id_int = None
    nome = _norm_txt(dieta)
    key = (current_cliente_id(), dieta_id_int or 0, nome)
    cached = _CARDAPIO_POR_DIETA.get(key)
    if cached is not None:
        return cached
    conds = []
    if dieta_id_int:
        conds.append(NutCardapio.dieta_id == dieta_id_int)
    if nome:
        conds.append(db.func.upper(db.func.trim(NutCardapio.dieta)) == nome)
    if not conds:
        _CARDAPIO_POR_DIETA[key] = {m: [] for m in MEALS_SUBST}
        return _CARDAPIO_POR_DIETA[key]
    rows = (
        _q(NutCardapio)
        .filter(NutCardapio.ativo.is_(True))
        .filter(db.or_(*conds))
        .all()
    )
    _CARDAPIO_POR_DIETA[key] = _entries_cardapio(rows, guardar_itens=True)
    return _CARDAPIO_POR_DIETA[key]


def find_cardapio_for_meal(dieta, meal, data_ref=None, dieta_id=None, exigir_dieta=False):
    """Melhor cardápio para dieta + horário (opcionalmente dia do mês).

    Preferência por dieta_id (FK) quando disponível — alinha com join futuro
    em NutPrecoDietaTipo (dieta × tipo_refeicao / hr_*).
    Com dieta informada, lê só essa dieta. A tabela inteira só entra se
    não houver cardápio dela e a chamada aceitar fallback.
    """
    entries = []
    if (dieta or '').strip() or dieta_id:
        entries = _indice_cardapios_dieta(dieta, dieta_id).get(meal) or []
    if not entries and not exigir_dieta:
        entries = cardapios_por_refeicao().get(meal) or []
    if not entries:
        return None
    dia = data_ref.day if data_ref else None
    dieta_id_int = None
    if dieta_id:
        try:
            dieta_id_int = int(dieta_id)
        except (TypeError, ValueError):
            dieta_id_int = None

    best = None
    best_key = None
    tipo_esperado = _TIPO_CARDAPIO_POR_REFEICAO.get(meal)

    def _considerar(entry, score):
        nonlocal best, best_key
        dia_bonus = 10 if (dia and entry[1] == dia) else 0
        key = (score + dia_bonus, score, -(entry[2] or 0))
        if best_key is None or key > best_key:
            best_key = key
            best = entry

    if tipo_esperado:
        entries = [e for e in entries if (e[5] or '') == tipo_esperado]

    for entry in entries:
        if dieta_id_int and entry[0] and entry[0] == dieta_id_int:
            score = 110
        else:
            score = _dieta_match_score(dieta, entry[4])
        if score <= 0:
            continue
        _considerar(entry, score)
    if best is None and not exigir_dieta:
        for entry in entries:
            _considerar(entry, 0)
    if best is None:
        return None
    return _CardapioResolvido(best)


# Setor (grupo do cadastro) de cada tipo de cardápio. A aba da refeição só enxerga o seu.
_SETORES_POR_TIPO_CARDAPIO = {
    'grandes': (
        ('ACOMPANHAMENTO', 'Acompanhamento', ('acompanhamento',)),
        ('PRATO BASE', 'Prato', ('prato_base',)),
        ('PROTEÍNA OPCIONAL', 'Proteína', ('proteina_opcional', 'proteico_opcional')),
        ('GUARNIÇÃO', 'Guarnição', ('guarnicao',)),
        ('SALADA', 'Salada', ('docinho_salada', 'diversos_salada', 'salada')),
        ('SOBREMESA', 'Sobremesa', ('sobremesa',)),
        ('FRUTA', 'Fruta', ('fruta',)),
        ('SUCO', 'Suco', ('suco',)),
        ('VITAMINA', 'Vitamina', ('vitamina_suco', 'vitamina', 'entrada_sopa')),
        ('OUTROS', 'Outros', ('outros',)),
    ),
    'pequenas': (
        ('BEBIDA', 'Bebida', ('bebida',)),
        ('PRATO', 'Prato', ('prato1', 'prato2', 'prato3', 'prato4', 'prato5', 'prato6', 'prato7', 'prato8')),
        ('SOBREMESA', 'Sobremesa', ('sobremesa',)),
    ),
    'liquidas': (
        ('PRINCIPAL', 'Principal', ('principal',)),
        ('BEBIDA', 'Bebida', ('bebida',)),
        ('SOBREMESA', 'Sobremesa', ('sobremesa',)),
        ('GELADO', 'Gelado', ('gelado',)),
        ('OUTROS', 'Outros', ('outros',)),
    ),
}
_TIPO_CARDAPIO_POR_REFEICAO = {
    'desjejum': 'pequenas',
    'colacao': 'pequenas',
    'almoco': 'grandes',
    'merenda': 'pequenas',
    'jantar': 'grandes',
    'ceia': 'pequenas',
}
_EXTRAS_ALIAS = {
    'docinho_salada': ('salada',),
    'vitamina_suco': ('vitamina',),
}
_TIPOS_ITEM_CARDAPIO = ('pequenas', 'grandes', 'liquidas')


def _grupo_canonico_item(grupo):
    grupo = _norm_txt(grupo)
    if re.match(r'^PRATO\s+\d+$', grupo):
        return 'PRATO'
    return grupo


def campos_grupo_item_cardapio(tipo, grupo):
    """Campos do cardápio que alimentam a busca daquele item. Não cruza refeições."""
    tipo = (tipo or '').strip().lower()
    grupo = _grupo_canonico_item(grupo)
    if tipo not in _TIPOS_ITEM_CARDAPIO or not grupo:
        return []
    for nome, _rotulo, campos in _SETORES_POR_TIPO_CARDAPIO.get(tipo, ()):
        if _norm_txt(nome) == grupo:
            return list(campos)
    return []


def _lembrar_nome_item(destino, nome, item_id=None, grupo=''):
    texto = _norm_txt(nome)
    if not texto or texto in destino:
        return
    destino[texto] = {'id': item_id, 'nome': texto, 'grupo': grupo}


def list_itens_tema_cardapio(tema, tipo):
    """Itens cadastrados no cardápio: inclusão avulsa e histórico já salvo."""
    tipo = (tipo or '').strip().lower()
    grupo = _grupo_canonico_item(tema)
    campos = campos_grupo_item_cardapio(tipo, grupo)
    if not campos:
        return []
    vistos = {}
    for row in _q(NutItemCardapio).filter(
        NutItemCardapio.ativo.is_(True),
        NutItemCardapio.tipo == tipo,
        NutItemCardapio.grupo == grupo,
    ).all():
        _lembrar_nome_item(vistos, row.nome, row.id, grupo)
    chaves = CAMPOS_ITEM_CARDAPIO.get(tipo, ())
    idxs = [i for i, chave in enumerate(chaves, 1) if chave in campos]
    colunas = [NutCardapio.itens] + [getattr(NutCardapio, f'item_{i}') for i in idxs]
    historico = (
        _q(NutCardapio)
        .filter(NutCardapio.ativo.is_(True), NutCardapio.tipo == tipo)
        .with_entities(*colunas)
        .all()
    )
    for rec in historico:
        for valor in rec[1:]:
            _lembrar_nome_item(vistos, valor, None, grupo)
        bruto = rec[0]
        if not bruto:
            continue
        try:
            data = json.loads(bruto) if isinstance(bruto, str) else {}
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            continue
        for campo in campos:
            for nome in _vals_prato(data.get(campo)) + _vals_prato(data.get(f'{campo}_extras')):
                _lembrar_nome_item(vistos, nome, None, grupo)
            for alias in _EXTRAS_ALIAS.get(campo, ()):
                for nome in _vals_prato(data.get(alias)) + _vals_prato(data.get(f'{alias}_extras')):
                    _lembrar_nome_item(vistos, nome, None, grupo)
    out = list(vistos.values())
    out.sort(key=lambda item: (item.get('nome') or '', item.get('id') or 0))
    return out


def list_itens_temas_cardapio(temas, tipo):
    out = {}
    for tema in temas or []:
        t = (tema or '').strip()
        if not t or t in out:
            continue
        out[t] = list_itens_tema_cardapio(t, tipo)
    return out


def criar_item_cardapio(nome, tema, tipo):
    """Grava o item do cardápio sem criar produto."""
    nome = _norm_txt(nome)
    tipo = (tipo or '').strip().lower()
    grupo = _grupo_canonico_item(tema)
    if not nome:
        return None, 'Informe o nome'
    if tipo not in _TIPOS_ITEM_CARDAPIO or not campos_grupo_item_cardapio(tipo, grupo):
        return None, 'Grupo inválido'
    existente = _q(NutItemCardapio).filter(
        NutItemCardapio.tipo == tipo,
        NutItemCardapio.grupo == grupo,
        NutItemCardapio.nome == nome,
    ).first()
    if existente:
        if not existente.ativo:
            existente.ativo = True
            db.session.flush()
        return existente, None
    row = NutItemCardapio(
        cliente_id=write_cliente_id(),
        tipo=tipo,
        grupo=grupo,
        nome=nome,
        ativo=True,
    )
    db.session.add(row)
    db.session.flush()
    return row, None


def _nomes_itens_campo(itens, campo):
    itens = itens or {}
    nomes = _vals_prato(itens.get(campo)) + _vals_prato(itens.get(f'{campo}_extras'))
    for alias in _EXTRAS_ALIAS.get(campo, ()):
        nomes.extend(_vals_prato(itens.get(alias)))
        nomes.extend(_vals_prato(itens.get(f'{alias}_extras')))
    return nomes


def opcoes_itens_refeicao(mapa_row, meal):
    """Itens que a aba pode adicionar: cardápio desta dieta nesta refeição + produtos do setor.

    Desjejum não devolve pratos do almoço, e o almoço não devolve itens do desjejum.
    """
    meal = str(meal or '').strip().lower()
    if meal not in MEALS_SUBST:
        return {'ok': False, 'error': 'Refeição inválida'}
    if eh_lancamento_uma(getattr(mapa_row, 'tipo_lancamento', None)):
        return {
            'ok': False,
            'error': 'LVE, fórmula infantil, enteral e suplemento não usam o cardápio.',
        }
    dieta = (getattr(mapa_row, 'dieta', None) or '').strip()
    data_ref = getattr(mapa_row, 'data_refeicao', None)
    lanc = info_lancamento_refeicoes(data_ref)
    dest_iso = (lanc.get(meal) or {}).get('data_destino') or ''
    data_meal = data_ref
    if dest_iso:
        try:
            data_meal = date.fromisoformat(dest_iso)
        except ValueError:
            data_meal = data_ref
    card = find_cardapio_for_meal(
        dieta,
        meal,
        data_meal,
        dieta_id=getattr(mapa_row, 'dieta_id', None),
        exigir_dieta=True,
    )
    itens = {}
    tipo = _TIPO_CARDAPIO_POR_REFEICAO.get(meal, 'pequenas')
    if card is not None and (card.tipo or '').strip() == tipo:
        if card.itens is not None:
            itens = card.itens or {}
        elif card.id:
            row = NutCardapio.query.get(card.id)
            if row is not None and (row.tipo or '').strip() == tipo:
                itens = row.get_itens() or {}
    if tipo not in _SETORES_POR_TIPO_CARDAPIO:
        tipo = _TIPO_CARDAPIO_POR_REFEICAO.get(meal, 'pequenas')

    setores = []
    for grupo, rotulo, campos in _SETORES_POR_TIPO_CARDAPIO[tipo]:
        da_dieta = []
        vistos = set()
        for campo in campos:
            for nome in _nomes_itens_campo(itens, campo):
                chave = _norm_txt(nome)
                if not chave or chave in vistos:
                    continue
                vistos.add(chave)
                da_dieta.append(nome)
        catalogo = []
        for prod in list_produtos_tema_cardapio(grupo, tipo=tipo):
            nome = (prod.get('nome') or '').strip()
            chave = _norm_txt(nome)
            if not chave or chave in vistos:
                continue
            vistos.add(chave)
            catalogo.append(nome)
        itens_setor = (
            [{'nome': n, 'origem': 'dieta'} for n in da_dieta]
            + [{'nome': n, 'origem': 'setor'} for n in catalogo]
        )
        if not itens_setor:
            continue
        setores.append({
            'setor': grupo,
            'label': rotulo,
            'itens': itens_setor,
        })
    return {
        'ok': True,
        'meal': meal,
        'meal_label': MEAL_LABELS.get(meal, meal),
        'dieta': dieta,
        'tipo': tipo,
        'setores': setores,
    }


def get_mapa_substituicoes(mapa_row):
    """Monta payload completo do diálogo Substituições para uma linha do mapa.

    Refeições já após a hora limite exibem/editam o conteúdo do dia seguinte.
    """
    dieta = (mapa_row.dieta or '').strip()
    data_ref = mapa_row.data_refeicao
    lanc = info_lancamento_refeicoes(data_ref)
    subs_hoje = normalize_substituicoes(mapa_row.get_substituicoes())

    # carrega substituições do dia seguinte (quando houver refeições adiadas)
    destinos = {info['data_destino'] for info in lanc.values() if info.get('apos_limite')}
    subs_por_data = {data_ref.isoformat() if data_ref else '': subs_hoje}
    row_por_data = {data_ref.isoformat() if data_ref else '': mapa_row}
    for dest_iso in destinos:
        try:
            dest_date = date.fromisoformat(dest_iso)
        except ValueError:
            continue
        row_dest = buscar_linha_mapa_dia(mapa_row, dest_date)
        if row_dest:
            row_por_data[dest_iso] = row_dest
            subs_por_data[dest_iso] = normalize_substituicoes(row_dest.get_substituicoes())

    refeicoes = {}
    subs_view = {}
    sem_cardapio = eh_lancamento_uma(getattr(mapa_row, 'tipo_lancamento', None))
    for meal in MEALS_SUBST:
        info = lanc[meal]
        dest_iso = info['data_destino']
        row_src = row_por_data.get(dest_iso) or mapa_row
        data_meal = row_src.data_refeicao or data_ref
        subs_meal = (subs_por_data.get(dest_iso) or subs_hoje).get(meal) or {
            'pares': [], 'justificativa': ''
        }
        card = None if sem_cardapio else find_cardapio_for_meal(
            dieta, meal, data_meal, dieta_id=getattr(mapa_row, 'dieta_id', None),
        )
        pratos = list(card.pratos) if card else []
        pares = subs_meal.get('pares') or []
        refeicoes[meal] = {
            'label': MEAL_LABELS[meal],
            'cardapio_id': card.id if card else None,
            'cardapio_dieta': (card.dieta if card else '') or '',
            'cardapio_tipo': (card.tipo if card else '') or '',
            'pratos': pratos,
            'pares': pares,
            'justificativa': subs_meal.get('justificativa') or '',
            'cardapio_personalizado': cardapio_personalizado(pratos, pares),
            'lancamento': info,
        }
        subs_view[meal] = {
            'pares': list(pares),
            'justificativa': subs_meal.get('justificativa') or '',
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
    adiadas = [m for m, i in lanc.items() if i.get('apos_limite')]
    return {
        'ok': True,
        'mapa_id': mapa_row.id,
        'header': header,
        'dieta': dieta,
        'data_refeicao': data_ref.isoformat() if data_ref else '',
        'paciente_id': mapa_row.paciente_id,
        'refeicoes': refeicoes,
        'substituicoes': subs_view,
        'lancamento': lanc,
        'refeicoes_adiadas': adiadas,
        'sem_cardapio': sem_cardapio,
        'aviso_geral': (
            'Há refeições após a hora limite: as alterações serão salvas no dia seguinte.'
            if adiadas else ''
        ),
    }


def save_mapa_substituicoes(mapa_row, payload, usuario=None):
    """Persiste substituições respeitando hora limite (adia para o dia seguinte)."""
    if eh_lancamento_uma(getattr(mapa_row, 'tipo_lancamento', None)):
        return {
            'erro': 'LVE, fórmula infantil, enteral e suplemento não usam o cardápio.',
            'substituicoes': {},
            'meals_salvos': [],
            'meals_adiados': [],
            'aviso': '',
        }
    data_ref = mapa_row.data_refeicao or date.today()
    lanc = info_lancamento_refeicoes(data_ref)
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

    # agrupa por data destino
    por_destino = {}
    for meal in MEALS_SUBST:
        if meal not in incoming or not isinstance(incoming[meal], dict):
            continue
        dest = date.fromisoformat(lanc[meal]['data_destino'])
        por_destino.setdefault(dest, []).append(meal)

    salvos = []
    adiadas = []
    for dest, meals in por_destino.items():
        row_dest = obter_ou_criar_linha_mapa_dia(mapa_row, dest, usuario=usuario)
        if not row_dest:
            continue
        atual = normalize_substituicoes(row_dest.get_substituicoes())
        merged = {k: dict(v) for k, v in atual.items()}
        for meal in meals:
            bloco = incoming[meal]
            norm = normalize_substituicoes({meal: bloco})[meal]
            if 'pares' in bloco:
                merged[meal]['pares'] = norm['pares']
            if 'justificativa' in bloco:
                merged[meal]['justificativa'] = norm['justificativa']
            salvos.append(meal)
            if lanc[meal].get('apos_limite'):
                adiadas.append({
                    'meal': meal,
                    'label': MEAL_LABELS.get(meal, meal),
                    'data_destino': lanc[meal]['data_destino'],
                    'data_destino_label': lanc[meal]['data_destino_label'],
                    'hora_limite': lanc[meal]['hora_limite'],
                    'aviso': lanc[meal]['aviso'],
                })
        row_dest.set_substituicoes(merged)
        marcar_alteracao_mapa(row_dest, usuario=usuario)

    return {
        'substituicoes': normalize_substituicoes(mapa_row.get_substituicoes()),
        'meals_salvos': salvos,
        'meals_adiados': adiadas,
        'aviso': (
            'Substituições após a hora limite foram salvas no dia seguinte: '
            + ', '.join(f"{a['label']} -> {a['data_destino_label']}" for a in adiadas)
            if adiadas else ''
        ),
    }


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


def listar_justificativas_anteriores(mapa_row, meal=None, limit=40):
    """Lista justificativas já usadas em mapas anteriores do mesmo paciente."""
    if not mapa_row.paciente_id and not (mapa_row.prontuario or '').strip():
        return []
    q = NutMapaRefeicao.query.filter(
        NutMapaRefeicao.id != mapa_row.id,
        NutMapaRefeicao.data_refeicao < (mapa_row.data_refeicao or date.today()),
    )
    if mapa_row.paciente_id:
        q = q.filter(NutMapaRefeicao.paciente_id == mapa_row.paciente_id)
    else:
        q = q.filter(NutMapaRefeicao.prontuario == mapa_row.prontuario)
    rows = q.order_by(NutMapaRefeicao.data_refeicao.desc(), NutMapaRefeicao.id.desc()).limit(80).all()
    meals = [meal] if meal in MEALS_SUBST else list(MEALS_SUBST)
    out = []
    seen = set()
    for row in rows:
        subs = normalize_substituicoes(row.get_substituicoes())
        data_label = row.data_refeicao.strftime('%d/%m/%Y') if row.data_refeicao else ''
        for m in meals:
            just = (subs.get(m) or {}).get('justificativa') or ''
            just = just.strip()
            if not just:
                continue
            key = (just.upper(), m)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                'mapa_id': row.id,
                'data': row.data_refeicao.isoformat() if row.data_refeicao else '',
                'data_label': data_label,
                'meal': m,
                'meal_label': MEAL_LABELS.get(m, m),
                'justificativa': just,
            })
            if len(out) >= limit:
                return out
    return out


def _cardapio_seed_signature(item):
    hrs = tuple(bool(item.get(f'hr_{m}')) for m in MEALS_SUBST)
    return (
        (item.get('tipo') or '').strip().lower(),
        _norm_txt(item.get('dieta')),
        int(item.get('dia_mes') or 1),
        hrs,
    )


def _seed_cardapios():
    cid = ensure_cliente_hfb().id
    dietas_by_nome = {
        _norm_txt(d.nome): d.id
        for d in NutDieta.query.filter_by(cliente_id=cid).all()
        if d.nome
    }
    existentes = {
        (
            (c.tipo or '').strip().lower(),
            _norm_txt(c.dieta),
            int(c.dia_mes or 1),
            tuple(bool(getattr(c, f'hr_{m}')) for m in MEALS_SUBST),
        )
        for c in NutCardapio.query.filter_by(cliente_id=cid).all()
    }
    for item in CARDAPIOS_SEED:
        sig = _cardapio_seed_signature(item)
        if sig in existentes:
            continue
        dieta_nome = item.get('dieta', '') or ''
        row = NutCardapio(
            cliente_id=cid,
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
    invalidar_cache_cardapios()


def list_tabelas_nutrientes(somente_ativas=True):
    q = _q(NutTabelaNutrientes)
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [t.to_dict() for t in q.order_by(NutTabelaNutrientes.nome).all()]


def list_alimentos(tabela_id=None, somente_ativas=True, include_nutrientes=True):
    q = NutAlimento.query.join(NutTabelaNutrientes)
    cid = current_cliente_id()
    if cid is not None:
        q = q.filter(NutTabelaNutrientes.cliente_id == cid)
    if tabela_id:
        q = q.filter(NutAlimento.tabela_id == tabela_id)
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
    cid = ensure_cliente_hfb().id
    if NutTabelaNutrientes.query.filter_by(cliente_id=cid).count() > 0:
        return
    tabelas = {}
    for item in ALIMENTOS_SEED:
        nome_tab = (item.get('tabela') or 'Tabela Padrão').strip()
        if nome_tab not in tabelas:
            tab = NutTabelaNutrientes(nome=nome_tab, ativo=True, cliente_id=cid)
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
    q = _q(NutPratoLiquido)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [p.to_dict() for p in q.order_by(NutPratoLiquido.nome, NutPratoLiquido.id).all()]


def _seed_pratos_liquidos():
    cid = ensure_cliente_hfb().id
    if NutPratoLiquido.query.filter_by(cliente_id=cid).count() > 0:
        return
    for (
        nome, principal, sobremesa, outros, bebida, gelado, extra, fator, ativo
    ) in PRATOS_LIQUIDOS_SEED:
        db.session.add(NutPratoLiquido(
            cliente_id=cid,
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


def _uma_categoria_grupo(tipo, sistema, manipulado):
    sistema = (sistema or '').strip().lower()
    if tipo == 'formula':
        return 'formula', 'FORMULAS INFANTIS'
    if tipo == 'lve':
        return 'lve', 'LVE'
    if tipo == 'modulo':
        return 'suplemento', 'SUPLEMENTOS E MODULOS'
    if tipo == 'enteral':
        if sistema == 'fechado':
            return 'enteral', 'ENTERAL SISTEMA FECHADO'
        return 'enteral', 'ENTERAL SISTEMA ABERTO'
    if manipulado:
        return 'suplemento', 'SUPLEMENTOS MANIPULADOS'
    return 'suplemento', 'SUPLEMENTOS'


def _produto_do_nome_uma(nome, produto=''):
    produto = (produto or '').strip().upper()
    if produto:
        return produto[:200]
    nome = (nome or '').strip().upper()
    if ' - ' in nome:
        return nome.split(' - ', 1)[1].strip()[:200]
    return ''


def desvincular_lve_da_dieta(cid, nome):
    """LVE não é dieta. Remove a dieta espelhada com o mesmo nome."""
    nome = (nome or '').strip().upper()
    if not nome or cid is None:
        return 0
    dietas = NutDieta.query.filter(
        NutDieta.cliente_id == cid,
        db.func.upper(NutDieta.nome) == nome,
        db.func.lower(NutDieta.categoria) == 'lve',
    ).all()
    for dieta in dietas:
        cards = NutCardapio.query.filter(
            db.or_(
                NutCardapio.dieta_id == dieta.id,
                db.and_(
                    NutCardapio.cliente_id == cid,
                    NutCardapio.dieta_id.is_(None),
                    db.func.upper(NutCardapio.dieta) == nome,
                ),
            )
        ).all()
        for card in cards:
            db.session.delete(card)
        NutMapaRefeicao.query.filter_by(dieta_id=dieta.id).update(
            {NutMapaRefeicao.dieta_id: None}, synchronize_session=False
        )
        db.session.delete(dieta)
    return len(dietas)


def desvincular_lves_das_dietas(cid):
    """Tira do cadastro de dietas todo LVE já gravado deste cliente."""
    if cid is None:
        return 0
    itens = NutUmaItem.query.filter(_chave_uma(cid), NutUmaItem.tipo == 'lve').all()
    total = 0
    for item in itens:
        total += desvincular_lve_da_dieta(cid, item.nome)
    return total


def apagar_cadastro_lve(row):
    """Apaga o LVE. Não desativa e não deixa dieta com o mesmo nome."""
    if row is None:
        return None
    if (row.tipo or '').strip().lower() != 'lve':
        raise ValueError('Só o cadastro de LVE é apagado por aqui')
    desvincular_lve_da_dieta(row.cliente_id, row.nome)
    db.session.delete(row)
    return row


def _espelhar_uma_item(cid, tipo, nome, sistema, manipulado, grupo='', atualizar=False):
    """Leva fórmula, enteral e suplemento para o cadastro de dieta. LVE fica de fora."""
    if (tipo or '').strip().lower() == 'lve':
        desvincular_lve_da_dieta(cid, nome)
        return
    nome = (nome or '').strip().upper()
    if not nome or tipo == 'prato':
        if nome and not NutPratoLiquido.query.filter_by(cliente_id=cid, nome=nome).first():
            db.session.add(NutPratoLiquido(
                cliente_id=cid,
                nome=nome,
                grupo_extra=True,
                fator_conv_tot=1,
                ativo=True,
            ))
        return
    if dieta_foi_excluida(nome, cid):
        return
    categoria, grupo_padrao = _uma_categoria_grupo(tipo, sistema, manipulado)
    grupo = (grupo or '').strip().upper() or grupo_padrao
    dieta = NutDieta.query.filter_by(cliente_id=cid, nome=nome).first()
    if dieta:
        if atualizar and grupo:
            dieta.grupo = grupo[:80]
            dieta.categoria = categoria
        return
    db.session.add(NutDieta(
        cliente_id=cid,
        nome=nome[:200],
        categoria=categoria,
        grupo=grupo[:80],
        ativo=True,
    ))


def gravar_uma_item(cid, tipo, nome, sistema='', papel='', manipulado=False, produto='', quantidade=0):
    tipo = (tipo or '').strip().lower()
    if tipo not in ('prato', 'suplemento', 'enteral', 'formula', 'lve', 'modulo'):
        raise ValueError('Tipo de item inválido')
    nome = (nome or '').strip().upper()
    if not nome:
        raise ValueError('Informe o nome')
    sistema = (sistema or '').strip().lower()
    if sistema not in ('', 'aberto', 'fechado'):
        sistema = ''
    papel = (papel or '').strip().lower()
    if papel not in ('', 'dieta', 'suplemento'):
        papel = ''
    manipulado = bool(manipulado)
    row = NutUmaItem.query.filter_by(
        cliente_id=cid,
        tipo=tipo,
        sistema=sistema,
        papel=papel,
        manipulado=manipulado,
        nome=nome[:200],
    ).first()
    if row:
        if produto:
            row.produto = _produto_do_nome_uma(nome, produto)
        row.ativo = True
    else:
        row = NutUmaItem(
            cliente_id=cid,
            tipo=tipo,
            sistema=sistema,
            papel=papel,
            manipulado=manipulado,
            nome=nome[:200],
            produto=_produto_do_nome_uma(nome, produto),
            quantidade=float(quantidade or 0),
            ativo=True,
        )
        db.session.add(row)
    _espelhar_uma_item(cid, tipo, row.nome, sistema, manipulado)
    return row


def list_uma_itens(tipo=None, sistema=None, papel=None, manipulado=None, somente_ativos=True,
                   somente_disponiveis=False):
    q = _q(NutUmaItem)
    if tipo:
        q = q.filter(db.func.lower(NutUmaItem.tipo) == (tipo or '').strip().lower())
    if sistema:
        q = q.filter(db.func.lower(NutUmaItem.sistema) == (sistema or '').strip().lower())
    if papel:
        q = q.filter(db.func.lower(NutUmaItem.papel) == (papel or '').strip().lower())
    if manipulado is not None:
        q = q.filter(NutUmaItem.manipulado.is_(bool(manipulado)))
    if somente_ativos:
        q = q.filter(NutUmaItem.ativo.is_(True))
    if somente_disponiveis:
        q = q.filter(NutUmaItem.produto_disponivel.is_(True))
    return [i.to_dict() for i in q.order_by(NutUmaItem.nome, NutUmaItem.id).all()]


TIPOS_CADASTRO_UMA = ('formula', 'enteral', 'suplemento', 'lve')

COLUNAS_FATURAMENTO_UMA = (
    'BÁSICAS',
    'LÍQUIDAS',
    'D.I.',
    'ACOMP.',
    'FORMULAS INFANTIS',
    'ENTERAL SISTEMA ABERTO',
    'ENTERAL SISTEMA FECHADO',
    'SUPLEMENTOS',
    'SUPLEMENTOS MANIPULADOS',
    'LVE',
)

# Cadastro de LVE do sistema legado. Não usa grupo de dieta nem coluna de faturamento.
GRUPOS_LVE = (
    'MISTURA NUTRITIVA S/LACTOSE',
    'SEM LACTOSE',
)

COLUNAS_TOTALIZACAO_LVE = (
    'PREMATUROS E RECEM - NATOS DE BAIXO PESO',
    'LACTENTES 0 A 6 MESES',
    'LACTENTES DE 6 A 12 MESES',
    'ERROS INATOS DO METABOLISMO',
    'FÓRMULAS LÁCTEAS',
    'LACTENTES ANTI-REGURGITAÇÃO',
    'ISENTAS DE LACTOSE',
)

# Coluna do cadastro de fórmula infantil no lactário (faixa e tipo da fórmula).
COLUNAS_TOTALIZACAO_FORMULA = COLUNAS_TOTALIZACAO_LVE + (
    'HIPOALERGÊNICAS',
    'ESPECIAIS À BASE DE PROTEÍNA DE SOJA',
    'ESPECIAIS HIDROLISADAS',
    'ELEMENTARES',
    'CRIANÇA A PARTIR DE 12 MESES',
    'SUPLEMENTO NUTRICIONAL',
)


def colunas_faturamento_uma(grupos=None):
    return unir_nomes_uma(list(COLUNAS_FATURAMENTO_UMA) + list(grupos or []))


def unir_nomes_uma(*listas):
    vistos = []
    for lista in listas:
        for nome in lista or []:
            nome = (nome or '').strip().upper()
            if nome and nome not in vistos:
                vistos.append(nome)
    return vistos


def _lista_opcao_uma(tipo, campo):
    tipo = (tipo or '').strip().lower()
    campo = (campo or '').strip().lower()
    if tipo not in TIPOS_CADASTRO_UMA:
        raise ValueError('Tipo de cadastro inválido')
    if campo not in ('grupo', 'coluna'):
        raise ValueError('Campo inválido')
    if tipo == 'lve':
        return 'grupo_lve' if campo == 'grupo' else 'coluna_lve'
    if tipo == 'formula' and campo == 'coluna':
        return 'coluna_formula'
    if campo == 'grupo':
        return 'grupo'
    return 'coluna'


def list_opcoes_uma(lista):
    q = _q(NutUmaOpcao).filter(
        NutUmaOpcao.lista == lista,
        NutUmaOpcao.ativo.is_(True),
    )
    return [row.nome for row in q.order_by(NutUmaOpcao.nome, NutUmaOpcao.id).all()]


def _ordem_nome_uma(nome):
    base = unicodedata.normalize('NFD', nome or '')
    sem_acento = ''.join(ch for ch in base if unicodedata.category(ch) != 'Mn')
    return sem_acento.casefold()


def _ordenar_nomes_uma(nomes):
    return sorted(nomes, key=_ordem_nome_uma)


def _nomes_seed_grupo_dieta():
    nomes = set()
    for item in GRUPOS_DIETA_SEED:
        if isinstance(item, (list, tuple)):
            nome = (item[0] or '').strip().upper()
        else:
            nome = (item or '').strip().upper()
        if nome:
            nomes.add(nome)
    return nomes


def _tipos_campo_uma(tipo, campo='grupo'):
    tipo = (tipo or '').strip().lower()
    if tipo == 'lve' or (tipo == 'formula' and campo == 'coluna'):
        return (tipo,)
    return ('formula', 'enteral', 'suplemento')


def _opcoes_da_lista(lista):
    rows = _q(NutUmaOpcao).filter(NutUmaOpcao.lista == lista).all()
    ativos = [row.nome for row in rows if row.ativo and row.nome]
    ocultos = {(row.nome or '').strip().upper() for row in rows if not row.ativo}
    return ativos, ocultos


def listar_campo_uma(tipo, campo):
    """Nomes visíveis do grupo ou da coluna, em ordem alfabética."""
    lista = _lista_opcao_uma(tipo, campo)
    if lista == 'grupo':
        base = [g['nome'] for g in list_grupos_dieta(somente_ativos=True)]
        return _ordenar_nomes_uma(unir_nomes_uma(base))
    if lista == 'grupo_lve':
        base = GRUPOS_LVE
    elif lista == 'coluna_lve':
        base = COLUNAS_TOTALIZACAO_LVE
    elif lista == 'coluna_formula':
        base = COLUNAS_TOTALIZACAO_FORMULA
    else:
        grupos = [g['nome'] for g in list_grupos_dieta(somente_ativos=True)]
        base = colunas_faturamento_uma(grupos)
    ativos, ocultos = _opcoes_da_lista(lista)
    nomes = [nome for nome in unir_nomes_uma(base, ativos) if nome not in ocultos]
    return _ordenar_nomes_uma(nomes)


def _grupo_dieta_por_nome(cid, nome, somente_ativo=False):
    q = NutGrupoDieta.query.filter(
        _chave_uma_cliente(NutGrupoDieta, cid),
        db.func.upper(NutGrupoDieta.nome) == nome,
    )
    if somente_ativo:
        q = q.filter(NutGrupoDieta.ativo.is_(True))
    return q.first()


def _opcao_por_nome(cid, lista, nome):
    return NutUmaOpcao.query.filter(
        _chave_uma_cliente(NutUmaOpcao, cid),
        NutUmaOpcao.lista == lista,
        db.func.upper(NutUmaOpcao.nome) == nome,
    ).first()


def _marcar_opcao_uma(cid, lista, nome, ativo):
    row = _opcao_por_nome(cid, lista, nome)
    if row:
        row.ativo = ativo
        row.nome = nome
        return row
    row = NutUmaOpcao(cliente_id=cid, lista=lista, nome=nome, ativo=ativo)
    db.session.add(row)
    return row


def _aplicar_renome_uma(cid, tipo, campo, atual, novo):
    tipos = _tipos_campo_uma(tipo, campo)
    coluna = NutUmaItem.grupo if campo == 'grupo' else NutUmaItem.coluna_faturamento
    itens = NutUmaItem.query.filter(
        _chave_uma(cid),
        NutUmaItem.tipo.in_(tipos),
        db.func.upper(coluna) == atual,
    ).all()
    for item in itens:
        if campo == 'grupo':
            item.grupo = novo
        else:
            item.coluna_faturamento = novo
    if campo != 'grupo' or 'lve' in tipos:
        return
    dietas = NutDieta.query.filter(
        _chave_uma_cliente(NutDieta, cid),
        db.func.upper(NutDieta.grupo) == atual,
    ).all()
    for dieta in dietas:
        dieta.grupo = novo


def _guardar_grupo_seed_inativo(cid, nome):
    if nome not in _nomes_seed_grupo_dieta():
        return
    row = _grupo_dieta_por_nome(cid, nome)
    if row:
        row.ativo = False
        return
    db.session.add(NutGrupoDieta(cliente_id=cid, nome=nome, ordem=0, ativo=False))


def salvar_opcao_uma(cid, tipo, campo, nome):
    """Grava um grupo ou uma coluna criado pelo botão + do cadastro."""
    nome = _txt_uma(nome, 80)
    if not nome:
        raise ValueError('Informe o nome')
    lista = _lista_opcao_uma(tipo, campo)
    if lista == 'grupo':
        liberar_grupo_dieta_excluido(nome, cid)
        row = _grupo_dieta_por_nome(cid, nome)
        if row:
            row.ativo = True
            return row.nome
        last = NutGrupoDieta.query.filter(
            _chave_uma_cliente(NutGrupoDieta, cid),
        ).order_by(NutGrupoDieta.ordem.desc()).first()
        ordem = (int(last.ordem or 0) + 10) if last else 10
        row = NutGrupoDieta(cliente_id=cid, nome=nome, ordem=ordem, ativo=True)
        db.session.add(row)
        return row.nome
    row = _opcao_por_nome(cid, lista, nome)
    if row:
        row.ativo = True
        return row.nome
    row = NutUmaOpcao(cliente_id=cid, lista=lista, nome=nome, ativo=True)
    db.session.add(row)
    return row.nome


def renomear_opcao_uma(cid, tipo, campo, nome_atual, nome_novo):
    """Troca o nome de um grupo ou coluna e atualiza os cadastros que o usam."""
    atual = _txt_uma(nome_atual, 80)
    novo = _txt_uma(nome_novo, 80)
    if not atual or not novo:
        raise ValueError('Informe o nome')
    if atual == novo:
        return novo
    if atual not in listar_campo_uma(tipo, campo):
        raise ValueError('Item não encontrado')
    if novo in listar_campo_uma(tipo, campo):
        raise ValueError('Já existe um item com este nome')
    lista = _lista_opcao_uma(tipo, campo)
    if lista == 'grupo':
        row = _grupo_dieta_por_nome(cid, atual, somente_ativo=True)
        if not row:
            raise ValueError('Item não encontrado')
        outro = _grupo_dieta_por_nome(cid, novo)
        if outro and outro.id != row.id:
            outro.ativo = True
            row.ativo = False
        else:
            row.nome = novo
            _guardar_grupo_seed_inativo(cid, atual)
    else:
        _marcar_opcao_uma(cid, lista, atual, False)
        _marcar_opcao_uma(cid, lista, novo, True)
    _aplicar_renome_uma(cid, tipo, campo, atual, novo)
    return novo


def remover_opcao_uma(cid, tipo, campo, nome):
    """Tira o grupo ou a coluna da lista, sem apagar os cadastros já gravados."""
    atual = _txt_uma(nome, 80)
    if not atual:
        raise ValueError('Informe o nome')
    if atual not in listar_campo_uma(tipo, campo):
        raise ValueError('Item não encontrado')
    lista = _lista_opcao_uma(tipo, campo)
    if lista == 'grupo':
        row = _grupo_dieta_por_nome(cid, atual, somente_ativo=True)
        if not row:
            raise ValueError('Item não encontrado')
        row.ativo = False
        return atual
    _marcar_opcao_uma(cid, lista, atual, False)
    return atual


def _chave_uma_cliente(model, cid):
    if cid is None:
        return model.cliente_id.is_(None)
    return model.cliente_id == cid


def _txt_uma(v, limite):
    return (v or '').strip().upper()[:limite]


def _num_uma_opt(v):
    if v in (None, ''):
        return None
    try:
        return float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _componentes_uma(valor):
    if isinstance(valor, str):
        try:
            valor = json.loads(valor) if valor.strip() else []
        except (TypeError, ValueError):
            return []
    if not isinstance(valor, list):
        return []
    limpos = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        componente = _txt_uma(item.get('componente'), 120)
        formula = _txt_uma(item.get('formula'), 200)
        codigo = _txt_uma(item.get('codigo') or item.get('cod_produto'), 40)
        un = _txt_uma(item.get('un'), 20)
        if not any((componente, formula, codigo, un)):
            continue
        limpos.append({
            'componente': componente,
            'formula': formula,
            'und': bool(item.get('und')),
            'vol': bool(item.get('vol')),
            'codigo': codigo,
            'un': un,
        })
    return limpos


def _chave_uma(cid):
    if cid is None:
        return NutUmaItem.cliente_id.is_(None)
    return NutUmaItem.cliente_id == cid


def _sistema_cadastro_uma(tipo, d, row=None):
    if tipo in ('formula', 'enteral'):
        fechado = d.get('sistema_fechado')
        if fechado is None and 'sistema' in d:
            fechado = (d.get('sistema') or '').strip().lower() == 'fechado'
        if fechado is None and row is not None:
            return row.sistema or ''
        if fechado:
            return 'fechado'
        return 'aberto' if tipo == 'enteral' else ''
    return ''


def salvar_cadastro_uma(cid, d, row=None):
    """Grava o cadastro da foto (fórmula, enteral, suplemento ou LVE)."""
    tipo = (d.get('tipo') or (row.tipo if row else '') or '').strip().lower()
    if tipo not in TIPOS_CADASTRO_UMA:
        raise ValueError('Tipo de cadastro inválido')
    nome = _txt_uma(d.get('nome') if 'nome' in d else (row.nome if row else ''), 200)
    if not nome:
        raise ValueError('Informe o nome')
    sistema = _sistema_cadastro_uma(tipo, d, row)
    papel = 'dieta' if tipo == 'enteral' else ''
    manipulado = bool(d.get('manipulado')) if tipo == 'suplemento' else False
    if tipo in ('formula', 'enteral'):
        produto_principal = _txt_uma(
            d.get('produto_principal') if 'produto_principal' in d else (row.produto_principal if row else ''),
            200,
        )
    else:
        produto_principal = ''
    if 'unidade' in d:
        unidade = _txt_uma(d.get('unidade'), 20)
    elif row is not None:
        unidade = row.unidade or ''
    else:
        unidade = ''
    conflito = NutUmaItem.query.filter(
        _chave_uma(cid),
        NutUmaItem.tipo == tipo,
        NutUmaItem.sistema == sistema,
        NutUmaItem.papel == papel,
        NutUmaItem.manipulado == manipulado,
        NutUmaItem.nome == nome,
        NutUmaItem.produto_principal == produto_principal,
        NutUmaItem.unidade == unidade,
    )
    if row is not None:
        conflito = conflito.filter(NutUmaItem.id != row.id)
    if conflito.first():
        raise ValueError('Já existe um item com este nome')
    if row is None:
        row = NutUmaItem(
            cliente_id=cid,
            tipo=tipo,
            ativo=True,
            produto_disponivel=True,
            cobranca='espelho_1' if tipo == 'lve' else '',
        )
        db.session.add(row)
    row.tipo = tipo
    row.nome = nome
    row.sistema = sistema
    row.papel = papel
    row.manipulado = manipulado
    row.unidade = unidade
    if tipo == 'formula':
        row.diluicao = _txt_uma(d.get('diluicao'), 40)
    if tipo == 'lve':
        row.ativo = bool(d.get('ativo', True))
        cobranca = (d.get('cobranca') or 'espelho_1').strip().lower()
        if cobranca not in ('nao', 'espelho_1', 'espelho_2'):
            cobranca = 'espelho_1'
        row.cobranca = cobranca
        row.produto_disponivel = True
    else:
        row.produto_disponivel = bool(d.get('produto_disponivel', True))
        row.ativo = True
    if tipo in ('formula', 'enteral'):
        row.produto_principal = produto_principal
        if row.produto_principal:
            row.produto = row.produto_principal[:200]
    if tipo in TIPOS_CADASTRO_UMA:
        row.grupo = _txt_uma(d.get('grupo'), 80)
    if tipo == 'suplemento':
        row.quant_padrao = _txt_uma(d.get('quant_padrao'), 40)
    if 'coluna_faturamento' in d:
        row.coluna_faturamento = _txt_uma(d.get('coluna_faturamento'), 80)
    for campo in ('calorias', 'ptn', 'hc', 'lip', 'fibras'):
        if campo in d:
            setattr(row, campo, _num_uma_opt(d.get(campo)))
    if tipo != 'lve' and 'composicao' in d:
        row.composicao = (d.get('composicao') or '').strip()[:4000]
    if 'componentes' in d:
        row.componentes = json.dumps(_componentes_uma(d.get('componentes')), ensure_ascii=False)
    _espelhar_uma_item(
        cid, tipo, row.nome, row.sistema, row.manipulado,
        grupo=row.grupo or '',
        atualizar=bool((row.grupo or '').strip()),
    )
    return row


def list_vias(somente_ativas=True):
    q = _q(NutViaAdministracao)
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [v.to_dict() for v in q.order_by(NutViaAdministracao.nome, NutViaAdministracao.id).all()]


VALIDADES_UMA_PADRAO = (
    {'horario': '06:00', 'valido_ate': '10:00'},
    {'horario': '10:00', 'valido_ate': '14:00'},
    {'horario': '14:00', 'valido_ate': '18:00'},
    {'horario': '18:00', 'valido_ate': '22:00'},
    {'horario': '22:00', 'valido_ate': '02:00'},
)

_ESTOQUES_UMA = (
    'estoque_enteral_id',
    'estoque_suplemento_id',
    'estoque_formula_id',
    'estoque_lve_id',
    'estoque_modulo_id',
)


def _fmt_br_uma(valor, casas=1):
    try:
        num = float(valor or 0)
    except (TypeError, ValueError):
        num = 0.0
    texto = f'{num:.{casas}f}'
    return texto.replace('.', ',')


def _parse_br_uma(valor, default=0.0):
    if valor is None or valor == '':
        return default
    if isinstance(valor, bool):
        return default
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(' ', '')
    if not texto:
        return default
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return default


def _hora_uma(valor):
    texto = str(valor or '').strip()
    m = re.fullmatch(r'(\d{1,2}):(\d{2})', texto)
    if not m:
        return ''
    hora, minuto = int(m.group(1)), int(m.group(2))
    if hora > 23 or minuto > 59:
        return ''
    return f'{hora:02d}:{minuto:02d}'


def _garantir_tabela_config_uma():
    try:
        NutConfigUma.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()


def _config_uma_do_cliente(cliente_id=None):
    _garantir_tabela_config_uma()
    if cliente_id is None:
        cliente_id = write_cliente_id()
    q = NutConfigUma.query
    if cliente_id:
        return q.filter_by(cliente_id=cliente_id).first()
    return q.filter(NutConfigUma.cliente_id.is_(None)).first()


def _validades_uma(bruto):
    if isinstance(bruto, (list, tuple)):
        data = list(bruto)
    else:
        try:
            data = json.loads(bruto or '[]')
        except (TypeError, ValueError):
            data = []
    if not isinstance(data, list):
        return [dict(item) for item in VALIDADES_UMA_PADRAO]
    saida = []
    for item in data:
        if not isinstance(item, dict):
            continue
        horario = _hora_uma(item.get('horario'))
        valido = _hora_uma(item.get('valido_ate'))
        if horario and valido:
            saida.append({'horario': horario, 'valido_ate': valido})
    return saida


def config_uma_dict(cliente_id=None):
    """Configuração da U.M.A. do cliente. Sem registro, devolve o padrão do manual."""
    row = _config_uma_do_cliente(cliente_id)
    produto = None
    if row and row.agua_produto_id:
        produto = NutProduto.query.get(row.agua_produto_id)
    bruto_validades = row.validades if row and (row.validades or '').strip() else VALIDADES_UMA_PADRAO
    validades = _validades_uma(bruto_validades)
    if not validades:
        validades = [dict(item) for item in VALIDADES_UMA_PADRAO]
    metodo = (row.gotejamento_metodo if row else '') or 'continuo'
    if metodo not in ('continuo', 'calculado'):
        metodo = 'continuo'
    horas = row.gotejamento_horas if row and row.gotejamento_horas else 3.5
    volume = row.volume_agua if row else 0
    return {
        'via_enteral': (row.via_enteral if row else '') or '',
        'via_suplemento': (row.via_suplemento if row else '') or '',
        'via_formula': (row.via_formula if row else '') or '',
        'via_agua': (row.via_agua if row else '') or '',
        'volume_agua': volume or 0,
        'volume_agua_txt': _fmt_br_uma(volume, 1),
        'agua_produto_id': row.agua_produto_id if row else None,
        'agua_produto': (produto.descricao if produto else '') or '',
        'agua_coluna': (row.agua_coluna if row else '') or '',
        'gotejamento_metodo': metodo,
        'gotejamento_horas': horas or 3.5,
        'gotejamento_horas_txt': _fmt_br_uma(horas or 3.5, 1),
        'horas_divisao': horas if metodo == 'calculado' and horas else 15,
        'estoque_enteral_id': row.estoque_enteral_id if row else None,
        'estoque_suplemento_id': row.estoque_suplemento_id if row else None,
        'estoque_formula_id': row.estoque_formula_id if row else None,
        'estoque_lve_id': row.estoque_lve_id if row else None,
        'estoque_modulo_id': row.estoque_modulo_id if row else None,
        'validades': validades,
    }


def salvar_config_uma(payload, cliente_id=None):
    """Grava a configuração da U.M.A. Levanta ValueError se o payload for inválido."""
    d = payload or {}
    if cliente_id is None:
        cliente_id = write_cliente_id()

    def _via(chave):
        return str(d.get(chave) or '').strip().upper()[:80]

    metodo = str(d.get('gotejamento_metodo') or 'continuo').strip().lower()
    if metodo not in ('continuo', 'calculado'):
        raise ValueError('Método de gotejamento inválido')
    horas = _parse_br_uma(d.get('gotejamento_horas'), 3.5)
    if metodo == 'calculado' and horas <= 0:
        raise ValueError('Informe as horas do gotejamento calculado')

    produto_id = d.get('agua_produto_id')
    produto = None
    if produto_id not in (None, '', 0, '0'):
        try:
            produto_id = int(produto_id)
        except (TypeError, ValueError):
            raise ValueError('Produto da água inválido')
        produto = _q(NutProduto).filter(NutProduto.id == produto_id).first()
        if not produto:
            raise ValueError('Produto da água não encontrado neste cliente')
    else:
        produto_id = None

    estoques = {}
    for chave in _ESTOQUES_UMA:
        bruto = d.get(chave)
        if bruto in (None, '', 0, '0'):
            estoques[chave] = None
            continue
        try:
            eid = int(bruto)
        except (TypeError, ValueError):
            raise ValueError('Estoque inválido')
        estoque = _q(NutEstoqueLocal).filter(NutEstoqueLocal.id == eid).first()
        if not estoque:
            raise ValueError('Estoque não encontrado neste cliente')
        estoques[chave] = estoque.id

    row = _config_uma_do_cliente(cliente_id)
    if not row:
        row = NutConfigUma(cliente_id=cliente_id)
        db.session.add(row)

    row.via_enteral = _via('via_enteral')
    row.via_suplemento = _via('via_suplemento')
    row.via_formula = _via('via_formula')
    row.via_agua = _via('via_agua')
    row.volume_agua = max(0.0, _parse_br_uma(d.get('volume_agua'), 0))
    row.agua_produto_id = produto.id if produto else None
    row.agua_coluna = str(d.get('agua_coluna') or '').strip().upper()[:80]
    row.gotejamento_metodo = metodo
    row.gotejamento_horas = horas if horas > 0 else 3.5
    for chave, eid in estoques.items():
        setattr(row, chave, eid)

    validades = _validades_uma(d.get('validades'))
    if not validades:
        validades = [dict(item) for item in VALIDADES_UMA_PADRAO]
    row.validades = json.dumps(validades, ensure_ascii=False)
    db.session.commit()
    return config_uma_dict(cliente_id)


def calcular_gotejamento_uma(volume, cfg=None):
    """mL/h da etapa. Contínuo divide por 15; calculado divide pelas horas configuradas."""
    cfg = cfg or config_uma_dict()
    metodo = cfg.get('gotejamento_metodo') or 'continuo'
    if metodo == 'calculado':
        horas = _parse_br_uma(cfg.get('gotejamento_horas'), 0)
    else:
        horas = 15.0
    vol = _parse_br_uma(volume, 0)
    if horas <= 0 or vol <= 0:
        return None
    return round(vol / horas, 2)


def _seed_uma(cid):
    try:
        NutViaAdministracao.__table__.create(db.engine, checkfirst=True)
        NutUmaItem.__table__.create(db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()
    for nome, via_oral in VIAS_ADMINISTRACAO_SEED:
        nome = (nome or '').strip().upper()
        if not nome:
            continue
        row = NutViaAdministracao.query.filter_by(cliente_id=cid, nome=nome).first()
        if row:
            continue
        db.session.add(NutViaAdministracao(
            cliente_id=cid,
            nome=nome,
            produto='',
            via_oral=bool(via_oral),
            ativo=True,
        ))
    if NutUmaItem.query.filter_by(cliente_id=cid).first():
        return
    for item in itens_uma_seed():
        gravar_uma_item(
            cid,
            item['tipo'],
            item['nome'],
            sistema=item.get('sistema') or '',
            papel=item.get('papel') or '',
            manipulado=bool(item.get('manipulado')),
        )


def list_estoques(somente_ativos=True):
    q = _q(NutEstoqueLocal)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [e.to_dict() for e in q.order_by(NutEstoqueLocal.nome).all()]


def list_unidades(somente_ativas=True):
    q = _q(NutUnidadeMedida)
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [u.to_dict() for u in q.order_by(NutUnidadeMedida.codigo).all()]


def list_grupos_produto(somente_ativos=True):
    q = _q(NutGrupoProduto)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [g.to_dict() for g in q.order_by(NutGrupoProduto.nome).all()]


def list_produtos(estoque_id=None, grupo_id=None, somente_ativos=True):
    q = _q(NutProduto).outerjoin(NutGrupoProduto)
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


def nomes_grupo_tema_cardapio(tema, variantes_prato=False):
    """Nomes de grupo equivalentes ao tema do campo (BEBIDA ≈ BEBIDAS, PRATO 1–7 ≈ PRATO)."""
    tema = _norm_txt(tema)
    if not tema:
        return set()
    nomes = {tema}
    if re.match(r'^PRATO\s+\d+$', tema):
        nomes.add('PRATO')
        nomes.add('PRATOS')
    elif tema.endswith('S') and len(tema) > 3:
        nomes.add(tema[:-1])
    else:
        nomes.add(tema + 'S')
    if variantes_prato and (tema == 'PRATO' or tema == 'PRATOS' or re.match(r'^PRATO\s+\d+$', tema)):
        nomes.add('PRATO')
        nomes.add('PRATOS')
        for i in range(1, 8):
            nomes.add(f'PRATO {i}')
    return nomes


def estoque_padrao_produto():
    q = _q(NutEstoqueLocal)
    matriz = q.filter(db.func.upper(NutEstoqueLocal.nome) == 'MATRIZ').first()
    if matriz:
        return matriz
    ativo = q.filter_by(ativo=True).order_by(NutEstoqueLocal.id).first()
    return ativo or q.order_by(NutEstoqueLocal.id).first()


def garantir_grupo_produto_tema(tema):
    tema = _norm_txt(tema)
    if not tema:
        return None
    nomes = nomes_grupo_tema_cardapio(tema)
    grupos = _q(NutGrupoProduto).filter(db.func.upper(NutGrupoProduto.nome).in_(nomes)).all()
    exact = next((g for g in grupos if _norm_txt(g.nome) == tema), None)
    row = exact or (grupos[0] if grupos else None)
    if row:
        if not row.ativo:
            row.ativo = True
        return row
    row = NutGrupoProduto(nome=tema, ativo=True, cliente_id=write_cliente_id())
    db.session.add(row)
    db.session.flush()
    return row


def _codigo_produto_unico(estoque_id, nome):
    base = re.sub(r'[^A-Z0-9]', '', _norm_txt(nome))[:10] or 'ITEM'
    codigo = base
    n = 1
    while _q(NutProduto).filter_by(estoque_id=estoque_id, codigo=codigo).first():
        n += 1
        suf = str(n)
        codigo = (base[: max(1, 12 - len(suf))] + suf)[:12]
    return codigo


# Catálogo de itens do cardápio por cliente.
_CATALOGO_PRODUTOS_CARDAPIO = {}


def invalidar_cache_produtos_cardapio():
    global _CATALOGO_PRODUTOS_CARDAPIO
    _CATALOGO_PRODUTOS_CARDAPIO = {}


def _catalogo_produtos_cardapio():
    """Produtos ativos do cliente atual, agrupados pelo nome do grupo."""
    global _CATALOGO_PRODUTOS_CARDAPIO
    key = current_cliente_id()
    cached = _CATALOGO_PRODUTOS_CARDAPIO.get(key)
    if cached is not None:
        return cached
    grupos = _q(NutGrupoProduto).all()
    id_nome = {g.id: _norm_txt(g.nome) for g in grupos}
    por_nome = {}
    if id_nome:
        rows = (
            _q(NutProduto)
            .filter(NutProduto.ativo.is_(True), NutProduto.grupo_id.in_(list(id_nome)))
            .with_entities(NutProduto.id, NutProduto.descricao, NutProduto.grupo_id)
            .order_by(NutProduto.descricao, NutProduto.id)
            .all()
        )
        vistos = {}
        for pid, descricao, gid in rows:
            nome_grupo = id_nome.get(gid) or ''
            nome = (descricao or '').strip()
            key = _norm_txt(nome)
            if not nome_grupo or not key:
                continue
            seen = vistos.setdefault(nome_grupo, set())
            if key in seen:
                continue
            seen.add(key)
            por_nome.setdefault(nome_grupo, []).append({
                'id': pid,
                'nome': nome,
                'grupo': nome_grupo,
            })
    _CATALOGO_PRODUTOS_CARDAPIO[key] = por_nome
    return por_nome


# Sobremesa existe nas refeições pequenas e nas grandes. O grupo guarda o tipo.
_GRUPOS_CARDAPIO_POR_TIPO = {'SOBREMESA'}


def grupo_produto_cardapio(tema, tipo=None):
    """Nome do grupo de estoque. Sobremesa de desjejum não entra no almoço."""
    tema = _norm_txt(tema)
    tipo = (tipo or '').strip().lower()
    if tema in _GRUPOS_CARDAPIO_POR_TIPO and tipo in ('pequenas', 'grandes', 'liquidas'):
        return f'{tema} · {tipo.upper()}'
    return tema


def list_produtos_tema_cardapio(tema, tipo=None):
    tema = _norm_txt(tema)
    if not tema:
        return []
    catalogo = _catalogo_produtos_cardapio()
    grupo = grupo_produto_cardapio(tema, tipo)
    nomes = nomes_grupo_tema_cardapio(grupo, variantes_prato=(grupo == tema))
    if grupo != tema:
        nomes = {_norm_txt(grupo)}
    seen = set()
    out = []
    for nome_grupo in nomes:
        for item in catalogo.get(nome_grupo) or []:
            key = _norm_txt(item.get('nome'))
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
    out.sort(key=lambda item: (_norm_txt(item.get('nome')), item.get('id') or 0))
    return out


def list_produtos_temas_cardapio(temas, tipo=None):
    _catalogo_produtos_cardapio()
    out = {}
    for tema in temas or []:
        t = _norm_txt(tema)
        if not t or t in out:
            continue
        out[t] = list_produtos_tema_cardapio(t, tipo=tipo)
    return out


def criar_produto_tema_cardapio(nome, tema, tipo=None):
    nome = _norm_txt(nome)
    tema_livre = _norm_txt(tema)
    tema = grupo_produto_cardapio(tema_livre, tipo)
    if not nome:
        return None, 'Informe o nome'
    if not tema:
        return None, 'Informe o grupo'
    grupo = garantir_grupo_produto_tema(tema)
    if grupo is None:
        return None, 'Grupo inválido'
    estoque = estoque_padrao_produto()
    if estoque is None:
        return None, 'Cadastre um estoque em Produtos'
    nomes = nomes_grupo_tema_cardapio(tema)
    grupos = _q(NutGrupoProduto).filter(db.func.upper(NutGrupoProduto.nome).in_(nomes)).all()
    gids = [g.id for g in grupos] or [grupo.id]
    existente = _q(NutProduto).filter(
        NutProduto.grupo_id.in_(gids),
        db.func.upper(NutProduto.descricao) == nome,
    ).first()
    if existente:
        if not existente.ativo:
            existente.ativo = True
            db.session.flush()
            invalidar_cache_produtos_cardapio()
        return existente, None
    row = NutProduto(
        estoque_id=estoque.id,
        grupo_id=grupo.id,
        codigo=_codigo_produto_unico(estoque.id, nome),
        descricao=nome,
        quantidade=0,
        unidade='UN',
        ativo=True,
        cliente_id=write_cliente_id(),
    )
    db.session.add(row)
    db.session.flush()
    invalidar_cache_produtos_cardapio()
    return row, None


def _seed_produtos():
    cid = ensure_cliente_hfb().id
    for nome in ESTOQUES_SEED:
        if not NutEstoqueLocal.query.filter_by(nome=nome, cliente_id=cid).first():
            db.session.add(NutEstoqueLocal(nome=nome, ativo=True, cliente_id=cid))
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
        row = NutUnidadeMedida.query.filter_by(codigo=codigo, cliente_id=cid).first()
        if not row:
            db.session.add(NutUnidadeMedida(
                cliente_id=cid,
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
        if not NutGrupoProduto.query.filter_by(nome=nome, cliente_id=cid).first():
            db.session.add(NutGrupoProduto(nome=nome, ativo=True, cliente_id=cid))
    db.session.flush()

    if NutProduto.query.filter_by(cliente_id=cid).count() > 0:
        return
    for (
        estoque_nome, grupo_nome, codigo, descricao, qtd, un,
        preco_med, ult_preco, qmin, qmax, qliq, un_liq, fc
    ) in PRODUTOS_SEED:
        est = NutEstoqueLocal.query.filter_by(nome=estoque_nome, cliente_id=cid).first()
        grp = NutGrupoProduto.query.filter_by(nome=grupo_nome, cliente_id=cid).first()
        if not est or not grp:
            continue
        db.session.add(NutProduto(
            cliente_id=cid,
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
    q = _q(NutFornecedor)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [f.to_dict() for f in q.order_by(NutFornecedor.nome, NutFornecedor.id).all()]


def _seed_fornecedores():
    cid = ensure_cliente_hfb().id
    if NutFornecedor.query.filter_by(cliente_id=cid).count() > 0:
        return
    for item in FORNECEDORES_SEED:
        db.session.add(NutFornecedor(
            cliente_id=cid,
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
    q = _q(NutEtiqueta)
    if somente_ativas:
        q = q.filter_by(ativa=True)
    return [e.to_dict() for e in q.order_by(NutEtiqueta.nome, NutEtiqueta.id).all()]


def _seed_etiquetas():
    cid = ensure_cliente_hfb().id
    if NutEtiqueta.query.filter_by(cliente_id=cid).count() > 0:
        return
    for item in ETIQUETAS_SEED:
        row = NutEtiqueta(
            cliente_id=cid,
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
    q = _q(NutPrecoRefeicao)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [
        r.to_dict()
        for r in q.order_by(NutPrecoRefeicao.ordem, NutPrecoRefeicao.id).all()
    ]


def list_precos_dieta_tipo(somente_ativas=True, somente_tipos_ativos=True):
    """Lista preços dieta × tipo (linhas planas)."""
    q = NutPrecoDietaTipo.query.join(NutDieta).join(NutTipoRefeicao)
    cid = current_cliente_id()
    if cid is not None:
        q = q.filter(NutDieta.cliente_id == cid)
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
    dietas_q = _q(NutDieta)
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
    cid = ensure_cliente_hfb().id
    existentes = {
        (t.nome or '').strip().upper(): t
        for t in NutTipoRefeicao.query.filter_by(cliente_id=cid).all()
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
        by_sigla = NutTipoRefeicao.query.filter(
            NutTipoRefeicao.cliente_id == cid,
            db.func.upper(NutTipoRefeicao.sigla) == sigla.upper(),
        ).first()
        if by_sigla:
            by_sigla.nome = nome
            by_sigla.ordem = ordem
            by_sigla.ativo = True
            if not (by_sigla.hora_limite or '').strip():
                by_sigla.hora_limite = hora_limite
            continue
        db.session.add(NutTipoRefeicao(
            cliente_id=cid,
            nome=nome, sigla=sigla, ordem=ordem, hora_limite=hora_limite, ativo=True,
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
    dieta = NutDieta.query.get(dieta_id) if dieta_id else None
    cid_dieta = getattr(dieta, 'cliente_id', None) if dieta else None
    tipos_q = NutTipoRefeicao.query.filter_by(ativo=True)
    if cid_dieta is not None:
        tipos_q = tipos_q.filter(NutTipoRefeicao.cliente_id == cid_dieta)
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
    """Upsert uma dieta do catálogo do Bonsucesso e força preços nas colunas indicadas."""
    cid = ensure_cliente_hfb().id
    row = NutDieta.query.filter(
        NutDieta.cliente_id == cid,
        db.func.upper(NutDieta.nome) == nome.upper(),
    ).first()
    if not row:
        if dieta_foi_excluida(nome, cid):
            return None
        row = NutDieta(
            cliente_id=cid,
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
        # Não reativa dieta que o usuário desmarcou no cadastro
        if row.ativo is None:
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
    cid = ensure_cliente_hfb().id
    for antigo, novo in DIETAS_ALIAS_PARA_FOTO.items():
        src = NutDieta.query.filter(
            NutDieta.cliente_id == cid,
            db.func.upper(NutDieta.nome) == antigo.upper(),
        ).first()
        dst = NutDieta.query.filter(
            NutDieta.cliente_id == cid,
            db.func.upper(NutDieta.nome) == novo.upper(),
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
    cid = ensure_cliente_hfb().id
    ids_catalogo = {
        d.id for d in NutDieta.query.filter(
            NutDieta.cliente_id == cid,
            db.func.upper(NutDieta.nome).in_(list(DIETAS_PRECO_MATRIX_NOMES)),
        ).all()
    }
    ids_com_preco = {
        r[0] for r in db.session.query(NutPrecoDietaTipo.dieta_id).distinct().all()
    }
    outras = NutDieta.query.filter(
        NutDieta.cliente_id == cid,
        NutDieta.id.in_(list(ids_com_preco - ids_catalogo) or [-1]),
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
    # Mantém dados no banco, mas oculta da UI antiga (update em lote)
    cid = ensure_cliente_hfb().id
    NutPrecoRefeicao.query.filter_by(ativo=True, cliente_id=cid).update(
        {NutPrecoRefeicao.ativo: False}, synchronize_session=False
    )


def seed_nutricao(force=False):
    """Garante cadastros básicos de clínicas e dietas.

    Idempotente e cacheado por processo: a 1ª chamada (~2s) faz o trabalho;
    as demais retornam na hora (antes cada aba do menu pagava o seed inteiro).
    """
    global _SEED_NUTRICAO_DONE
    if _SEED_NUTRICAO_DONE and not force:
        return
    _ensure_nutricao_columns(force=force)
    cid = ensure_cliente_hfb().id
    for nome, ativo in CLINICAS_SEED:
        if not NutClinica.query.filter_by(nome=nome, cliente_id=cid).first():
            db.session.add(NutClinica(nome=nome, ativo=bool(ativo), cliente_id=cid))

    for nome, cat, ativo in DIETAS_SEED:
        if dieta_foi_excluida(nome, cid):
            continue
        if not NutDieta.query.filter_by(nome=nome, cliente_id=cid).first():
            db.session.add(NutDieta(nome=nome, categoria=cat, grupo='', ativo=bool(ativo), cliente_id=cid))

    db.session.flush()
    _seed_enfermarias()
    _seed_cardapios()
    _backfill_cardapio_dieta_id()
    _seed_nutricional()
    _seed_pratos_liquidos()
    _seed_uma(cid)
    _seed_produtos()
    _seed_fornecedores()
    _seed_etiquetas()
    _seed_tipos_refeicao()
    _seed_grupos_dieta()
    _seed_categorias_dieta()
    _seed_precos_dieta_tipo()  # inclui catálogo da foto + preços
    _seed_precos_refeicoes()
    # Após preços/catálogo, reabsorve grupos/categorias novos criados nas dietas
    _seed_grupos_dieta()
    _seed_categorias_dieta()

    # Backfill cliente_id on any seed rows still NULL
    for model in (
        NutClinica, NutGrupoClinica, NutEnfermaria, NutDieta, NutDietaExcluida, NutGrupoDieta, NutGrupoDietaExcluido, NutCategoriaDieta, NutPaciente, NutMapaRefeicao,
        NutCardapio, NutTabelaNutrientes, NutPratoLiquido, NutEstoqueLocal, NutUnidadeMedida,
        NutGrupoProduto, NutProduto, NutFornecedor, NutEtiqueta, NutPrecoRefeicao, NutTipoRefeicao,
        NutViaAdministracao, NutUmaItem,
    ):
        try:
            model.query.filter(model.cliente_id.is_(None)).update(
                {model.cliente_id: cid}, synchronize_session=False
            )
        except Exception:
            pass

    if NutPaciente.query.filter_by(cliente_id=cid).count() == 0:
        exemplos = [
            NutPaciente(
                nome='Maria Silva', sexo='F', nascimento=_parse_date('1985-03-15'),
                prontuario='12345', clinica='CLÍNICA MÉDICA A', leito='101-A',
                dieta='BRANDA COM SAL', diagnostico='HAS', admissao=date.today(),
                altura_cm=165, peso_kg=72, ativo=True, cliente_id=cid,
            ),
            NutPaciente(
                nome='João Santos', sexo='M', nascimento=_parse_date('1972-08-22'),
                prontuario='12346', clinica='CTI - 1', leito='05',
                dieta='PASTOSA COM SAL', diagnostico='Pós-operatório', admissao=date.today(),
                altura_cm=175, peso_kg=80, ativo=True, cliente_id=cid,
            ),
            NutPaciente(
                nome='Ana Oliveira', sexo='F', nascimento=_parse_date('1990-12-01'),
                prontuario='12347', clinica='ONCO', leito='210-B',
                dieta='LIQUIDA SEM SAL', diagnostico='Em tratamento', admissao=date.today(),
                altura_cm=160, peso_kg=58, ativo=True, cliente_id=cid,
            ),
        ]
        for p in exemplos:
            db.session.add(p)

    db.session.commit()
    try:
        cardapios_por_refeicao()
    except Exception:
        invalidar_cache_cardapios()
    _SEED_NUTRICAO_DONE = True


def paciente_from_payload(d, paciente=None):
    is_new = paciente is None
    paciente = paciente or NutPaciente()
    paciente.nome = limpar_indice_nome((d.get('nome') or '').strip())
    paciente.sexo = normalizar_sexo(d.get('sexo'))
    paciente.nascimento = _parse_date(d.get('nascimento'))
    paciente.prontuario = (d.get('prontuario') or '').strip() or None
    paciente.clinica = (d.get('clinica') or '').strip() or None
    paciente.enfermaria = (d.get('enfermaria') or '').strip() or None
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
    if is_new or not paciente.cliente_id:
        paciente.cliente_id = write_cliente_id()
    return paciente


TIPOS_LANCAMENTO_MAPA = (
    'principal', 'adicional', 'substituicao',
    'lve', 'formula', 'enteral', 'suplemento',
)
TIPOS_LANCAMENTO_DIETA = ('principal', 'adicional', 'substituicao')
TIPOS_LANCAMENTO_UMA = ('lve', 'formula', 'enteral', 'suplemento')
CAMPOS_UMA_POR_TIPO = {
    'lve': 'lve',
    'formula': 'formula_infantil',
    'enteral': 'enteral',
    'suplemento': 'suplementos',
}
ROTULOS_TIPO_LANCAMENTO = {
    'principal': 'Principal',
    'adicional': 'Adicional',
    'substituicao': 'Substituição',
    'lve': 'LVE',
    'formula': 'Fórm. infantil',
    'enteral': 'Enteral',
    'suplemento': 'Suplemento',
}


def normalizar_tipo_lancamento(valor, default='principal'):
    raw = (valor or '').strip().lower()
    aliases = {
        'principal': 'principal',
        'dieta_principal': 'principal',
        'adicional': 'adicional',
        'extra': 'adicional',
        'nova': 'adicional',
        'nova_dieta': 'adicional',
        'substituicao': 'substituicao',
        'substituição': 'substituicao',
        'subst': 'substituicao',
        'lve': 'lve',
        'formula': 'formula',
        'formula_infantil': 'formula',
        'fórmula': 'formula',
        'enteral': 'enteral',
        'interal': 'enteral',
        'suplemento': 'suplemento',
        'suplementos': 'suplemento',
    }
    return aliases.get(raw, default if default in TIPOS_LANCAMENTO_MAPA else 'principal')


def rotulo_tipo_lancamento(tipo):
    return ROTULOS_TIPO_LANCAMENTO.get(normalizar_tipo_lancamento(tipo), 'Principal')


def ordem_tipo_lancamento(tipo):
    return {
        'principal': 0,
        'substituicao': 1,
        'adicional': 2,
        'suplemento': 3,
        'enteral': 4,
        'formula': 5,
        'lve': 6,
    }.get(normalizar_tipo_lancamento(tipo), 9)


def eh_lancamento_uma(tipo):
    return normalizar_tipo_lancamento(tipo) in TIPOS_LANCAMENTO_UMA


def resolver_dieta_mapa(dieta_id=None, dieta_nome=None):
    """Resolve NutDieta ativa por id ou nome (sem criar cadastro)."""
    dieta = None
    if dieta_id not in (None, ''):
        try:
            dieta = _q(NutDieta).filter_by(id=int(dieta_id)).first()
        except (TypeError, ValueError):
            dieta = None
    nome = (dieta_nome or '').strip()
    if not dieta and nome:
        dieta = _q(NutDieta).filter(
            db.func.upper(NutDieta.nome) == nome.upper(),
            NutDieta.ativo.is_(True),
        ).first()
        if not dieta:
            dieta = _q(NutDieta).filter(db.func.upper(NutDieta.nome) == nome.upper()).first()
    return dieta


def garantir_grupo_lancamento(row):
    """Garante lancamento_grupo_id = id na primeira persistência do lançamento."""
    if row is None:
        return row
    if row.id and not row.lancamento_grupo_id:
        row.lancamento_grupo_id = row.id
    return row


def _mesmo_paciente_mapa(a, b):
    if not a or not b:
        return False
    if a.paciente_id and b.paciente_id and int(a.paciente_id) == int(b.paciente_id):
        return True
    return _chave_linha_mapa(a) == _chave_linha_mapa(b) and bool(
        (a.prontuario or a.nome or a.leito)
    )


def _buscar_irmao_uma(row, tipo_uma, candidatos):
    for outro in candidatos:
        if outro is row or not getattr(outro, 'ativo', True):
            continue
        if outro.data_refeicao != row.data_refeicao:
            continue
        if normalizar_tipo_lancamento(getattr(outro, 'tipo_lancamento', None)) != tipo_uma:
            continue
        if _mesmo_paciente_mapa(row, outro):
            return outro
    return None


def _novo_lancamento_uma(src, tipo_uma, texto):
    """Lançamento só de LVE, fórmula, enteral ou suplemento, sem cardápio."""
    campo = CAMPOS_UMA_POR_TIPO[tipo_uma]
    agora = now_brasilia()
    linha = NutMapaRefeicao(
        cliente_id=getattr(src, 'cliente_id', None) or write_cliente_id(),
        data_refeicao=src.data_refeicao,
        paciente_id=src.paciente_id,
        adm=src.adm,
        leito=src.leito,
        prontuario=src.prontuario,
        nome=src.nome,
        idade=src.idade,
        diagnostico=src.diagnostico,
        dieta=src.dieta,
        dieta_id=getattr(src, 'dieta_id', None),
        tipo_lancamento=tipo_uma,
        observacoes=None,
        clinica=src.clinica,
        enfermaria=src.enfermaria,
        fl_desjejum=False,
        fl_colacao=False,
        fl_almoco=False,
        fl_merenda=False,
        fl_jantar=False,
        fl_ceia=False,
        obs_etiqueta=None,
        extras=None,
        suplementos=None,
        enteral=None,
        formula_infantil=None,
        lve=None,
        substituicoes=None,
        data_inclusao=agora,
        usuario_alteracao=(getattr(src, 'usuario_alteracao', None) or 'sistema')[:80],
        data_atualizacao=agora,
        data_saida=None,
        motivo_saida=None,
        hospital_transferencia=None,
        ativo=True,
    )
    setattr(linha, campo, texto)
    return linha


def _desligar_cardapio_uma(row):
    """Lançamento de LVE/fórmula/enteral/suplemento não carrega refeição nem cardápio."""
    mudou = False
    for flag in MEAL_FLAG_FIELD.values():
        if getattr(row, flag, False):
            setattr(row, flag, False)
            mudou = True
    if (getattr(row, 'substituicoes', None) or '').strip():
        row.substituicoes = None
        mudou = True
    return mudou


def separar_lancamentos_uma(data_ref):
    """Tira LVE, fórmula infantil, enteral e suplemento da linha do cardápio.

    Cada um vira um lançamento próprio, que pode ser apagado sem dar alta
    e sem alterar o cardápio da dieta.
    """
    if not data_ref:
        return 0
    rows = list(
        apply_cliente_filter(
            NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True),
            NutMapaRefeicao,
        ).all()
    )
    mudou = 0
    for row in list(rows):
        tipo = normalizar_tipo_lancamento(getattr(row, 'tipo_lancamento', None))
        if tipo in TIPOS_LANCAMENTO_UMA:
            if _desligar_cardapio_uma(row):
                mudou += 1
            continue
        if tipo not in TIPOS_LANCAMENTO_DIETA:
            continue
        for tipo_uma, campo in CAMPOS_UMA_POR_TIPO.items():
            texto = (getattr(row, campo, None) or '').strip()
            if not texto:
                continue
            irmao = _buscar_irmao_uma(row, tipo_uma, rows)
            if irmao is None:
                irmao = _novo_lancamento_uma(row, tipo_uma, texto)
                db.session.add(irmao)
                db.session.flush()
                garantir_grupo_lancamento(irmao)
                rows.append(irmao)
            elif not (getattr(irmao, campo, None) or '').strip():
                setattr(irmao, campo, texto)
            setattr(row, campo, None)
            mudou += 1
    if mudou:
        db.session.commit()
    return mudou


def aplicar_campos_uma_independentes(row, dados, usuario=None, apagar_vazio=False):
    """Grava LVE, fórmula, enteral e suplemento fora da linha do cardápio.

    Campo vazio na própria linha U.M.A. apaga esse lançamento.
    Na linha da dieta, o vazio só apaga se apagar_vazio=True (tela da U.M.A.).
    """
    if not row or not isinstance(dados, dict):
        return row
    tipo_row = normalizar_tipo_lancamento(getattr(row, 'tipo_lancamento', None))
    candidatos = list(
        apply_cliente_filter(
            NutMapaRefeicao.query.filter_by(data_refeicao=row.data_refeicao, ativo=True),
            NutMapaRefeicao,
        ).all()
    )
    if row not in candidatos:
        candidatos.append(row)
    for tipo_uma, campo in CAMPOS_UMA_POR_TIPO.items():
        if campo not in dados:
            continue
        bruto = dados.get(campo)
        valor = (str(bruto).strip() if bruto is not None else '') or None
        if tipo_row == tipo_uma:
            setattr(row, campo, valor)
            if not valor:
                _aplicar_baixa_linha(
                    row,
                    motivo='Lançamento apagado',
                    usuario=usuario,
                    data_saida=row.data_refeicao,
                )
            else:
                _desligar_cardapio_uma(row)
            continue
        if tipo_row in TIPOS_LANCAMENTO_DIETA:
            setattr(row, campo, None)
        if not valor:
            if apagar_vazio:
                irmao = _buscar_irmao_uma(row, tipo_uma, candidatos)
                if irmao is not None:
                    apagar_lancamento_uma(irmao, usuario=usuario)
            continue
        irmao = _buscar_irmao_uma(row, tipo_uma, candidatos)
        if irmao is None:
            irmao = _novo_lancamento_uma(row, tipo_uma, valor)
            irmao.usuario_alteracao = (usuario or 'sistema')[:80]
            db.session.add(irmao)
            db.session.flush()
            garantir_grupo_lancamento(irmao)
            candidatos.append(irmao)
        else:
            setattr(irmao, campo, valor)
            _desligar_cardapio_uma(irmao)
            if usuario:
                irmao.usuario_alteracao = usuario[:80]
    return row


def apagar_lancamento_uma(row, usuario=None):
    """Apaga só este lançamento de LVE, fórmula, enteral ou suplemento."""
    if not row or not eh_lancamento_uma(getattr(row, 'tipo_lancamento', None)):
        raise ValueError('Este lançamento não é de LVE, fórmula, enteral ou suplemento')
    _aplicar_baixa_linha(
        row,
        motivo='Lançamento apagado',
        usuario=usuario,
        data_saida=row.data_refeicao or date.today(),
    )
    gid = getattr(row, 'lancamento_grupo_id', None)
    if gid and row.data_refeicao:
        futuros = (
            NutMapaRefeicao.query.filter(
                NutMapaRefeicao.lancamento_grupo_id == gid,
                NutMapaRefeicao.ativo.is_(True),
                NutMapaRefeicao.id != row.id,
                NutMapaRefeicao.data_refeicao > row.data_refeicao,
            )
            .all()
        )
        for futuro in futuros:
            _aplicar_baixa_linha(
                futuro,
                motivo='Lançamento apagado',
                usuario=usuario,
                data_saida=futuro.data_refeicao,
            )
    return row


def _chave_grupo_lancamento(row):
    gid = getattr(row, 'lancamento_grupo_id', None)
    if gid:
        return ('grupo', int(gid))
    tipo = normalizar_tipo_lancamento(getattr(row, 'tipo_lancamento', None))
    dieta = (getattr(row, 'dieta', None) or '').strip().upper()
    pid = getattr(row, 'paciente_id', None)
    rid = int(getattr(row, 'id', 0) or 0)
    if pid:
        return ('pid', int(pid), tipo, dieta, rid)
    return ('chave',) + _chave_linha_mapa(row) + (tipo, dieta, rid)


def mapa_from_paciente(paciente, data_ref=None, flags=None, extras=None, usuario=None):
    data_ref = data_ref or date.today()
    flags = flags or {}
    extras = extras or {}
    agora = now_brasilia()
    dieta_nome = extras.get('dieta') if 'dieta' in extras else paciente.dieta
    dieta_obj = resolver_dieta_mapa(extras.get('dieta_id'), dieta_nome)
    tipo = normalizar_tipo_lancamento(extras.get('tipo_lancamento'), 'principal')
    return NutMapaRefeicao(
        cliente_id=getattr(paciente, 'cliente_id', None) or write_cliente_id(),
        data_refeicao=data_ref,
        paciente_id=paciente.id,
        adm=extras.get('adm', paciente.admissao),
        leito=(extras.get('leito') if 'leito' in extras else paciente.leito),
        prontuario=(extras.get('prontuario') if 'prontuario' in extras else paciente.prontuario),
        nome=paciente.nome,
        idade=paciente.idade(data_ref),
        diagnostico=(extras.get('diagnostico') if 'diagnostico' in extras else paciente.diagnostico),
        dieta=(dieta_obj.nome if dieta_obj else (dieta_nome or None)),
        dieta_id=dieta_obj.id if dieta_obj else extras.get('dieta_id'),
        tipo_lancamento=tipo,
        observacoes=(extras.get('observacoes') if 'observacoes' in extras else paciente.observacoes),
        clinica=(extras.get('clinica') if 'clinica' in extras else paciente.clinica),
        enfermaria=(
            extras.get('enfermaria') if 'enfermaria' in extras else getattr(paciente, 'enfermaria', None)
        ),
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


def criar_lancamento_dieta_desde_linha(src, flags=None, extras=None, usuario=None, tipo_lancamento='adicional'):
    """Novo lançamento de dieta no mesmo paciente/leito, sem duplicar o cadastro."""
    if not src:
        return None
    flags = flags or {}
    extras = extras or {}
    tipo = normalizar_tipo_lancamento(tipo_lancamento, 'adicional')
    if tipo == 'principal':
        tipo = 'adicional'
    dieta_nome = extras.get('dieta') if extras.get('dieta') not in (None, '') else src.dieta
    dieta_obj = resolver_dieta_mapa(extras.get('dieta_id'), dieta_nome)
    agora = now_brasilia()
    linha = NutMapaRefeicao(
        cliente_id=getattr(src, 'cliente_id', None) or write_cliente_id(),
        data_refeicao=src.data_refeicao,
        paciente_id=src.paciente_id,
        adm=src.adm,
        leito=src.leito,
        prontuario=src.prontuario,
        nome=src.nome,
        idade=src.idade,
        diagnostico=src.diagnostico,
        dieta=(dieta_obj.nome if dieta_obj else (dieta_nome or src.dieta)),
        dieta_id=dieta_obj.id if dieta_obj else None,
        tipo_lancamento=tipo,
        observacoes=(extras.get('observacoes') if 'observacoes' in extras else src.observacoes),
        clinica=src.clinica,
        enfermaria=src.enfermaria,
        fl_desjejum=bool(flags.get('fl_desjejum', False)),
        fl_colacao=bool(flags.get('fl_colacao', False)),
        fl_almoco=bool(flags.get('fl_almoco', False)),
        fl_merenda=bool(flags.get('fl_merenda', False)),
        fl_jantar=bool(flags.get('fl_jantar', False)),
        fl_ceia=bool(flags.get('fl_ceia', False)),
        obs_etiqueta=(extras.get('obs_etiqueta') if 'obs_etiqueta' in extras else None),
        extras=(extras.get('extras') if 'extras' in extras else None),
        suplementos=(extras.get('suplementos') if 'suplementos' in extras else None),
        enteral=(extras.get('enteral') if 'enteral' in extras else None),
        formula_infantil=(extras.get('formula_infantil') if 'formula_infantil' in extras else None),
        lve=(extras.get('lve') if 'lve' in extras else None),
        substituicoes=None,
        data_inclusao=agora,
        usuario_alteracao=(usuario or 'sistema')[:80],
        data_atualizacao=agora,
        data_saida=None,
        motivo_saida=None,
        hospital_transferencia=None,
        ativo=True,
    )
    return linha


def _chave_linha_mapa(row):
    """Chave de identidade para linhas sem paciente_id."""
    return (
        (row.prontuario or '').strip().upper(),
        (row.nome or '').strip().upper(),
        (row.leito or '').strip().upper(),
    )


def _clonar_linha_mapa(src, data_ref, usuario=None):
    """Copia snapshot operacional de uma linha ativa para outra data."""
    agora = now_brasilia()
    idade = src.idade
    if src.paciente_id and src.paciente:
        try:
            idade = src.paciente.idade(data_ref)
        except Exception:
            pass
    return NutMapaRefeicao(
        cliente_id=getattr(src, 'cliente_id', None),
        data_refeicao=data_ref,
        paciente_id=src.paciente_id,
        adm=src.adm,
        leito=src.leito,
        prontuario=src.prontuario,
        nome=src.nome,
        idade=idade,
        diagnostico=src.diagnostico,
        dieta=src.dieta,
        dieta_id=getattr(src, 'dieta_id', None),
        tipo_lancamento=normalizar_tipo_lancamento(getattr(src, 'tipo_lancamento', None)),
        lancamento_grupo_id=getattr(src, 'lancamento_grupo_id', None),
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
        substituicoes=src.substituicoes,
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
    agora = now_brasilia()
    q = NutMapaRefeicao.query.filter(
        NutMapaRefeicao.data_refeicao == data_ref,
        NutMapaRefeicao.ativo.is_(False),
        db.or_(
            NutMapaRefeicao.motivo_saida.is_(None),
            db.func.trim(NutMapaRefeicao.motivo_saida) == '',
        ),
    )
    return q.update({
        NutMapaRefeicao.ativo: True,
        NutMapaRefeicao.data_saida: None,
        NutMapaRefeicao.hospital_transferencia: None,
        NutMapaRefeicao.usuario_alteracao: 'sistema',
        NutMapaRefeicao.data_atualizacao: agora,
    }, synchronize_session=False) or 0


def _upsert_linha_no_dia(src, data_ref, by_grupo, by_chave):
    """Garante o lançamento de src em data_ref (cria ou reativa). Retorna 1 se alterou."""
    if not _linha_mapa_ativa_para_copia(src):
        return 0

    grupo = getattr(src, 'lancamento_grupo_id', None)
    if grupo:
        existing = by_grupo.get(int(grupo))
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
        db.session.flush()
        garantir_grupo_lancamento(clone)
        by_grupo[int(grupo)] = clone
        return 1

    chave = _chave_grupo_lancamento(src)
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
    db.session.flush()
    garantir_grupo_lancamento(clone)
    by_chave[chave] = clone
    if clone.lancamento_grupo_id:
        by_grupo[int(clone.lancamento_grupo_id)] = clone
    return 1


def _indices_linhas_mapa(existentes):
    by_grupo = {}
    by_chave = {}
    for r in existentes:
        gid = getattr(r, 'lancamento_grupo_id', None)
        if gid:
            by_grupo[int(gid)] = r
        else:
            by_chave[_chave_grupo_lancamento(r)] = r
    return by_grupo, by_chave


_MAPA_COLS_LEVES = (
    'id', 'cliente_id', 'data_refeicao', 'lancamento_grupo_id', 'paciente_id', 'tipo_lancamento',
    'dieta', 'prontuario', 'nome', 'leito', 'motivo_saida', 'ativo',
)


def _query_linhas_mapa_leves():
    """Identidade da linha, sem os TEXT (dieta livre, cardápio, UMA)."""
    from sqlalchemy.orm import load_only
    return NutMapaRefeicao.query.options(load_only(*_MAPA_COLS_LEVES))


def _hidratar_linhas_mapa(rows):
    """Carrega colunas completas só das linhas que vão ser clonadas."""
    from sqlalchemy.orm import joinedload
    ids = [r.id for r in rows if getattr(r, 'id', None)]
    if not ids:
        return {}
    for r in rows:
        if getattr(r, 'id', None):
            db.session.expire(r)
    loaded = (
        NutMapaRefeicao.query
        .options(joinedload(NutMapaRefeicao.paciente))
        .filter(NutMapaRefeicao.id.in_(ids))
        .all()
    )
    return {r.id: r for r in loaded}


def _copiar_fontes_para_o_dia(fontes, data_ref, by_grupo, by_chave):
    """Cria ou reativa no dia alvo. Só hidrata a fonte quando falta clonar."""
    alteradas = 0
    clonar = []
    for src in fontes:
        if not _linha_mapa_ativa_para_copia(src):
            continue
        grupo = getattr(src, 'lancamento_grupo_id', None)
        if grupo:
            existing = by_grupo.get(int(grupo))
        else:
            existing = by_chave.get(_chave_grupo_lancamento(src))
        if existing:
            if _linha_com_baixa(existing):
                continue
            if not existing.ativo:
                existing.ativo = True
                existing.data_saida = None
                existing.motivo_saida = None
                existing.hospital_transferencia = None
                marcar_alteracao_mapa(existing, 'sistema')
                alteradas += 1
            continue
        clonar.append(src)
    if not clonar:
        return alteradas
    full = _hidratar_linhas_mapa(clonar)
    for src in clonar:
        row = full.get(src.id)
        if row is None:
            continue
        alteradas += _upsert_linha_no_dia(row, data_ref, by_grupo, by_chave)
    return alteradas


def _linhas_mapa_por_cliente(rows):
    grupos = {}
    for row in rows:
        grupos.setdefault(getattr(row, 'cliente_id', None), []).append(row)
    return grupos


def _copiar_ativos_dia_anterior(data_ref):
    """Merge: cada lançamento ativo (sem baixa com motivo) de data_ref-1 passa a existir em data_ref.

    Não pula o dia só porque já há algumas linhas (ex.: Ana em 09/08 não bloqueia os demais).
    A cópia não cruza clientes: o mapa de um hospital não entra no do outro.
    """
    data_origem = data_ref - timedelta(days=1)
    alteradas = _sanear_baixas_incompletas(data_ref)
    alteradas += _sanear_baixas_incompletas(data_origem)

    existentes = _linhas_mapa_por_cliente(
        _query_linhas_mapa_leves().filter_by(data_refeicao=data_ref).all()
    )
    fontes = _linhas_mapa_por_cliente(
        _query_linhas_mapa_leves()
        .filter_by(data_refeicao=data_origem)
        .order_by(NutMapaRefeicao.id)
        .all()
    )
    if not fontes:
        return alteradas

    for _cid, fontes_cli in fontes.items():
        by_grupo, by_chave = _indices_linhas_mapa(existentes.get(_cid) or [])
        alteradas += _copiar_fontes_para_o_dia(fontes_cli, data_ref, by_grupo, by_chave)
    return alteradas


def _garantir_ausentes_desde_historico(data_ref):
    """Copia do último estado anterior (sem baixa) quem ainda falta no dia alvo.

    Cobre buracos se um dia intermediário nunca recebeu a linha.
    Limita o lookback para não carregar o histórico inteiro do banco.
    A cópia permanece dentro do mesmo cliente.
    """
    existentes = _linhas_mapa_por_cliente(
        _query_linhas_mapa_leves().filter_by(data_refeicao=data_ref).all()
    )

    since = data_ref - timedelta(days=_MAPA_LOOKBACK_DIAS)
    priors = (
        _query_linhas_mapa_leves()
        .filter(
            NutMapaRefeicao.data_refeicao < data_ref,
            NutMapaRefeicao.data_refeicao >= since,
        )
        .order_by(NutMapaRefeicao.data_refeicao.desc(), NutMapaRefeicao.id.desc())
        .all()
    )
    alteradas = 0
    for cid, rows in _linhas_mapa_por_cliente(priors).items():
        by_grupo, by_chave = _indices_linhas_mapa(existentes.get(cid) or [])
        seen_grupos = set()
        seen_chaves = set()
        fontes = []
        for src in rows:
            gid = getattr(src, 'lancamento_grupo_id', None)
            if gid:
                if int(gid) in seen_grupos:
                    continue
                seen_grupos.add(int(gid))
            else:
                chave = _chave_grupo_lancamento(src)
                if chave in seen_chaves:
                    continue
                seen_chaves.add(chave)
            if _linha_com_baixa(src):
                continue
            fontes.append(src)
        alteradas += _copiar_fontes_para_o_dia(fontes, data_ref, by_grupo, by_chave)
    return alteradas


def _stamp_parte(valor):
    if valor is None:
        return ''
    if hasattr(valor, 'isoformat'):
        return valor.isoformat()
    return str(valor)


def _stamp_historico_mapa(data_ref):
    """Carimbo barato do que a cópia do dia precisa enxergar. Muda se entrar ou sair linha."""
    since = data_ref - timedelta(days=_MAPA_LOOKBACK_DIAS)
    mapa = db.session.query(
        db.func.count(NutMapaRefeicao.id),
        db.func.max(NutMapaRefeicao.id),
        db.func.max(NutMapaRefeicao.data_atualizacao),
    ).filter(
        NutMapaRefeicao.data_refeicao < data_ref,
        NutMapaRefeicao.data_refeicao >= since,
    ).one()
    ac = db.session.query(
        db.func.count(NutRefeicaoAcompanhante.id),
        db.func.max(NutRefeicaoAcompanhante.id),
        db.func.max(NutRefeicaoAcompanhante.data_atualizacao),
    ).filter(
        db.or_(
            NutRefeicaoAcompanhante.data_refeicao.is_(None),
            db.and_(
                NutRefeicaoAcompanhante.data_refeicao < data_ref,
                NutRefeicaoAcompanhante.data_refeicao >= since,
            ),
        )
    ).one()
    return tuple(_stamp_parte(v) for v in (tuple(mapa) + tuple(ac)))



def garantir_mapa_do_dia(data_ref=None):
    """Garante linhas do mapa em data_ref mesclando pacientes ainda sem baixa.

    Novos pacientes entram só via inserção manual. Quem saiu por Excluir
    (motivo_saida preenchido) não é recriado nos dias seguintes.

    - Mescla mesmo se o dia já tiver algumas linhas (não aborta por dia não-vazio).
    - Reativa baixas incompletas (ativo=False sem motivo).
    - Copia só do dia anterior + preenche ausentes no lookback recente
      (não varre mais o histórico dia a dia desde a primeira linha).
    Cadastro do paciente (data_saida no NutPaciente) NÃO impede a cópia —
    só a baixa no mapa com motivo.

    Se o histórico do lookback não mudou desde a última garantia deste processo,
    a troca de clínica não relê os TEXT dos 60 dias.
    """
    data_ref = data_ref or date.today()
    chave = data_ref.isoformat()

    alteradas = _sanear_baixas_incompletas(data_ref)
    stamp = _stamp_historico_mapa(data_ref)
    if _MAPA_GARANTIDO.get(chave) == stamp:
        if alteradas:
            db.session.commit()
            print(f'[mapa] garantir {data_ref}: sanadas/criadas={alteradas}')
        return alteradas

    since = data_ref - timedelta(days=_MAPA_LOOKBACK_DIAS)
    tem_anterior = (
        db.session.query(NutMapaRefeicao.id)
        .filter(
            NutMapaRefeicao.data_refeicao < data_ref,
            NutMapaRefeicao.data_refeicao >= since,
        )
        .limit(1)
        .first()
    )
    if tem_anterior:
        alteradas += _copiar_ativos_dia_anterior(data_ref)
        alteradas += _garantir_ausentes_desde_historico(data_ref)
        # Acompanhantes acompanham o paciente enquanto ele permanece no mapa
        alteradas += garantir_acompanhantes_do_dia(data_ref, commit=False)

    if alteradas:
        db.session.commit()
        print(f'[mapa] garantir {data_ref}: sanadas/criadas={alteradas}')
    _MAPA_GARANTIDO[chave] = _stamp_historico_mapa(data_ref)
    return alteradas


def marcar_alteracao_mapa(row, usuario=None):
    row.usuario_alteracao = (usuario or 'sistema')[:80]
    row.data_atualizacao = now_brasilia()
    return row


MSG_LEITO_OCUPADO = 'Leito ocupado. Escolha outro leito.'


def leito_ocupado_no_mapa(data_ref, clinica, enfermaria, leito, exclude_id=None, paciente_id=None):
    """True se o leito já tem outro paciente ativo (mesmo paciente pode ter várias dietas)."""
    clinica_n = (clinica or '').strip().upper()
    enfermaria_n = (enfermaria or '').strip().upper()
    leito_n = (leito or '').strip().upper()
    if not data_ref or not clinica_n or not enfermaria_n or not leito_n:
        return False
    q = (
        _q(NutMapaRefeicao)
        .filter(
            NutMapaRefeicao.data_refeicao == data_ref,
            NutMapaRefeicao.ativo.is_(True),
            db.func.upper(NutMapaRefeicao.clinica) == clinica_n,
            db.func.upper(NutMapaRefeicao.enfermaria) == enfermaria_n,
        )
    )
    if exclude_id is not None:
        q = q.filter(NutMapaRefeicao.id != int(exclude_id))
    rows = q.all()
    chaves_alvo = _chaves_ocupacao_leito(leito)
    if not chaves_alvo:
        return False
    for row in rows:
        if not (_chaves_ocupacao_leito(row.leito) & chaves_alvo):
            continue
        if paciente_id and row.paciente_id and int(row.paciente_id) == int(paciente_id):
            continue
        return True
    return False


def _chaves_ocupacao_leito(valor):
    """Normaliza rótulos de leito para comparação (nº, nome, '1 — Janela')."""
    if valor is None:
        return set()
    s = str(valor).strip().upper()
    if not s:
        return set()
    keys = {s}
    for sep in ('—', ' - ', '–'):
        if sep in s:
            keys.add(s.split(sep, 1)[0].strip())
            break
    # remove zeros à esquerda em chaves numéricas
    for k in list(keys):
        if k.isdigit():
            keys.add(str(int(k)))
            keys.add(str(int(k)).zfill(2))
    return {k for k in keys if k}


def list_leitos_vagos(
    data_ref,
    clinica=None,
    enfermaria=None,
    enfermaria_id=None,
    exclude_mapa_id=None,
):
    """Leitos cadastrados ativos da enfermaria que não estão ocupados no mapa do dia."""
    data_ref = data_ref or date.today()
    enf = None
    if enfermaria_id:
        enf = _q(NutEnfermaria).filter_by(id=int(enfermaria_id)).first()
    elif (enfermaria or '').strip():
        nome = (enfermaria or '').strip()
        enf = (
            _q(NutEnfermaria)
            .filter(db.func.upper(NutEnfermaria.nome) == nome.upper())
            .first()
        )
    if not enf:
        return {'enfermaria': None, 'leitos': [], 'ocupados': 0}

    clinica_n = (clinica or '').strip()
    enf_nome = (enf.nome or '').strip()

    ocupados_q = (
        _q(NutMapaRefeicao)
        .filter(
            NutMapaRefeicao.data_refeicao == data_ref,
            NutMapaRefeicao.ativo.is_(True),
            db.func.upper(NutMapaRefeicao.enfermaria) == enf_nome.upper(),
        )
    )
    if clinica_n:
        ocupados_q = ocupados_q.filter(
            db.func.upper(NutMapaRefeicao.clinica) == clinica_n.upper()
        )
    if exclude_mapa_id is not None:
        ocupados_q = ocupados_q.filter(NutMapaRefeicao.id != int(exclude_mapa_id))

    ocupados = set()
    for row in ocupados_q.all():
        ocupados |= _chaves_ocupacao_leito(row.leito)

    leitos = []
    for l in (
        NutLeito.query
        .filter_by(enfermaria_id=enf.id, ativo=True)
        .order_by(NutLeito.numero, NutLeito.nome)
        .all()
    ):
        keys = _chaves_ocupacao_leito(l.numero)
        keys |= _chaves_ocupacao_leito(l.nome)
        if keys & ocupados:
            continue
        numero = l.numero
        nome = (l.nome or '').strip()
        if numero is not None and nome and nome != str(numero) and nome != str(numero).zfill(2):
            rotulo = f'{numero} — {nome}'
            valor = str(numero)
        else:
            rotulo = nome or (str(numero) if numero is not None else f'Leito {l.id}')
            valor = str(numero) if numero is not None else rotulo
        leitos.append({
            'id': l.id,
            'enfermaria_id': enf.id,
            'numero': numero,
            'nome': nome,
            'valor': valor,
            'rotulo': rotulo,
            'ativo': True,
        })

    return {
        'enfermaria': {'id': enf.id, 'nome': enf.nome or ''},
        'leitos': leitos,
        'ocupados': len(ocupados),
        'data': data_ref.isoformat(),
        'clinica': clinica_n,
    }


def _rotulo_valor_leito(leito):
    """Rótulo de exibição e valor canônico de um leito cadastrado."""
    numero = leito.numero
    nome = (leito.nome or '').strip()
    if numero is not None and nome and nome != str(numero) and nome != str(numero).zfill(2):
        return str(numero), f'{numero} — {nome}'
    rotulo = nome or (str(numero) if numero is not None else f'Leito {leito.id}')
    valor = str(numero) if numero is not None else rotulo
    return valor, rotulo


def montar_grade_leitos_mapa(data_ref, clinica_nome=None, clinica_nomes=None):
    """Uma linha por leito cadastrado da clínica, com paciente do mapa se ocupado.

    A grade segue as enfermarias vinculadas à clínica e os leitos ativos de cada
    uma. Pacientes no mapa cujo leito não está no cadastro entram no fim do grupo.
    clinica_nomes filtra um conjunto (ex.: clínicas de um grupo). Lista vazia
    devolve grade vazia — não é o mesmo que "todas".
    """
    from collections import defaultdict

    data_ref = data_ref or date.today()
    nome_filtro = (clinica_nome or '').strip()
    nomes_set = None
    if clinica_nomes is not None:
        nomes_set = {(n or '').strip().upper() for n in clinica_nomes if (n or '').strip()}
        if not nomes_set:
            return []
    todas = nomes_set is None and ((not nome_filtro) or nome_filtro == '__todas__')

    from sqlalchemy.orm import selectinload
    q_cli = _q(NutClinica).filter_by(ativo=True).options(
        selectinload(NutClinica.enfermarias)
    )
    if nomes_set is not None:
        q_cli = q_cli.filter(db.func.upper(NutClinica.nome).in_(list(nomes_set)))
    elif not todas:
        q_cli = q_cli.filter(db.func.upper(NutClinica.nome) == nome_filtro.upper())
    clinicas = q_cli.order_by(NutClinica.nome).all()

    linhas_q = apply_cliente_filter(
        NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True),
        NutMapaRefeicao,
    )
    if nomes_set is not None:
        linhas_q = linhas_q.filter(
            db.func.upper(NutMapaRefeicao.clinica).in_(list(nomes_set))
        )
    elif not todas:
        linhas_q = linhas_q.filter(
            db.func.upper(NutMapaRefeicao.clinica) == nome_filtro.upper()
        )
    linhas_mapa = linhas_q.all()

    idx = defaultdict(list)
    for row in linhas_mapa:
        cli_u = (row.clinica or '').strip().upper()
        enf_u = (row.enfermaria or '').strip().upper()
        idx[(cli_u, enf_u)].append({
            'keys': _chaves_ocupacao_leito(row.leito),
            'linha': row,
            'usado': False,
        })

    def _slot(clinica_nome_s, clinica_id, enf_nome, enf_id, leito_rotulo, leito_valor,
              leito_id=None, leito_numero=None, linha=None, fora_cadastro=False):
        return {
            'clinica': clinica_nome_s or '',
            'clinica_id': clinica_id,
            'enfermaria': enf_nome or '',
            'enfermaria_id': enf_id,
            'leito': leito_rotulo or '',
            'leito_valor': leito_valor or leito_rotulo or '',
            'leito_id': leito_id,
            'leito_numero': leito_numero,
            'vago': linha is None,
            'fora_cadastro': bool(fora_cadastro),
            'linha': linha.to_dict(incluir_substituicoes=False) if linha is not None else None,
        }

    enf_ids = []
    for clinica in clinicas:
        for enf in (clinica.enfermarias or []):
            if getattr(enf, 'ativo', True) and enf.id not in enf_ids:
                enf_ids.append(enf.id)
    leitos_por_enf = defaultdict(list)
    if enf_ids:
        for leito in (
            NutLeito.query
            .filter(NutLeito.enfermaria_id.in_(enf_ids), NutLeito.ativo.is_(True))
            .order_by(NutLeito.numero, NutLeito.nome)
            .all()
        ):
            leitos_por_enf[leito.enfermaria_id].append(leito)

    grade = []
    for clinica in clinicas:
        cli_nome = clinica.nome or ''
        cli_u = cli_nome.strip().upper()
        enfermarias = [e for e in (clinica.enfermarias or []) if getattr(e, 'ativo', True)]
        enfermarias.sort(key=lambda e: (e.nome or '').upper())
        for enf in enfermarias:
            enf_nome = enf.nome or ''
            enf_u = enf_nome.strip().upper()
            leitos = leitos_por_enf.get(enf.id, [])
            bucket = idx.get((cli_u, enf_u), [])
            for leito in leitos:
                valor, rotulo = _rotulo_valor_leito(leito)
                keys = (
                    _chaves_ocupacao_leito(leito.numero)
                    | _chaves_ocupacao_leito(leito.nome)
                    | _chaves_ocupacao_leito(valor)
                )
                matches = []
                for item in bucket:
                    if item['usado'] or not item['keys']:
                        continue
                    if item['keys'] & keys:
                        matches.append(item)
                if not matches:
                    grade.append(_slot(
                        cli_nome, clinica.id, enf_nome, enf.id,
                        rotulo, valor, leito.id, leito.numero, None, False,
                    ))
                    continue
                matches.sort(key=lambda it: (
                    ordem_tipo_lancamento(getattr(it['linha'], 'tipo_lancamento', None)),
                    it['linha'].id or 0,
                ))
                for item in matches:
                    item['usado'] = True
                    grade.append(_slot(
                        cli_nome, clinica.id, enf_nome, enf.id,
                        rotulo, valor, leito.id, leito.numero, item['linha'], False,
                    ))

    for (_cli_u, _enf_u), bucket in idx.items():
        for item in bucket:
            if item['usado']:
                continue
            row = item['linha']
            grade.append(_slot(
                row.clinica, None, row.enfermaria, None,
                row.leito or '', row.leito or '', None, None, row, True,
            ))

    grade.sort(key=lambda item: (
        (item.get('clinica') or '').upper(),
        (item.get('enfermaria') or '').upper(),
        1 if item.get('fora_cadastro') else 0,
        item.get('leito_numero') if item.get('leito_numero') is not None else 10 ** 9,
        (item.get('leito') or '').upper(),
        (item.get('linha') or {}).get('nome') or '',
    ))
    return grade


CAMPOS_MAPA_UMA = ('extras', 'suplementos', 'enteral', 'formula_infantil', 'lve')


def linha_tem_conteudo_uma(row):
    """True se algum campo U.M.A. do paciente tem texto."""
    for campo in CAMPOS_MAPA_UMA:
        if (getattr(row, campo, None) or '').strip():
            return True
    return False


def listar_linhas_mapa_uma(data_ref):
    """Pacientes do dia com U.M.A. preenchida, de qualquer clínica, enfermaria ou leito."""
    data_ref = data_ref or date.today()
    uma_cols = [getattr(NutMapaRefeicao, campo) for campo in CAMPOS_MAPA_UMA]
    rows = apply_cliente_filter(
        NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True),
        NutMapaRefeicao,
    ).filter(db.or_(*[
        db.and_(col.isnot(None), db.func.trim(col) != '') for col in uma_cols
    ])).all()
    linhas = [r for r in rows if linha_tem_conteudo_uma(r)]
    linhas.sort(key=lambda r: (
        (r.clinica or '').upper(),
        (r.enfermaria or '').upper(),
        (r.leito or '').upper(),
        (r.nome or '').upper(),
        r.id or 0,
    ))
    return [r.to_dict() for r in linhas]


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


def resolver_partes_acompanhante(data_ref, fl_almoco=True, fl_jantar=True, agora=None):
    """Divide lançamento A/J entre o dia pedido e o dia seguinte (hora limite).

    Retorna lista de partes:
      {data_refeicao, fl_almoco, fl_jantar, adiadas: [meals], aviso}
    """
    data_ref = data_ref or date.today()
    fl_almoco = bool(fl_almoco)
    fl_jantar = bool(fl_jantar)
    partes_map = {}

    def _add(meal, flag_name, marcado):
        if not marcado:
            return
        dest = data_destino_lancamento(meal, data_ref, agora=agora)
        key = dest.isoformat()
        if key not in partes_map:
            partes_map[key] = {
                'data_refeicao': dest,
                'fl_almoco': False,
                'fl_jantar': False,
                'adiadas': [],
                'aviso': '',
            }
        partes_map[key][flag_name] = True
        if dest != data_ref:
            partes_map[key]['adiadas'].append(meal)

    _add('almoco', 'fl_almoco', fl_almoco)
    _add('jantar', 'fl_jantar', fl_jantar)

    partes = []
    for p in sorted(partes_map.values(), key=lambda x: x['data_refeicao']):
        if p['adiadas']:
            labels = ', '.join(MEAL_LABELS.get(m, m) for m in p['adiadas'])
            p['aviso'] = (
                f'A refeição será lançada para o dia seguinte '
                f'({p["data_refeicao"].strftime("%d/%m/%Y")})'
                + (f': {labels}.' if labels else '.')
            )
        partes.append(p)
    return partes


def paciente_ativo_no_mapa(paciente_id):
    """True se o paciente ainda tem linha ativa no mapa de refeições (qualquer dia)."""
    if not paciente_id:
        return False
    return (
        NutMapaRefeicao.query
        .filter_by(paciente_id=paciente_id, ativo=True)
        .first()
        is not None
    )


MSG_ACOMP_SO_SAIDA_MAPA = (
    'A refeição do acompanhante só é removida quando o paciente sair do mapa '
    '(alta médica, óbito ou transferência).'
)


def _chave_acompanhante(row):
    """Identidade estável do lançamento (paciente + nome) para copiar entre dias."""
    nome = (getattr(row, 'nome_acompanhante', None) or '').strip().lower()
    return (getattr(row, 'paciente_id', None), nome)


def _clonar_acompanhante_no_dia(src, data_ref):
    """Cria cópia ativa do acompanhante em data_ref (sem commit)."""
    return NutRefeicaoAcompanhante(
        cliente_id=src.cliente_id,
        nome_acompanhante=src.nome_acompanhante,
        paciente_id=src.paciente_id,
        dieta_id=src.dieta_id,
        refeicao=src.refeicao,
        quantidade=int(src.quantidade or 1),
        data_refeicao=data_ref,
        fl_almoco=True if src.fl_almoco is None else bool(src.fl_almoco),
        fl_jantar=True if src.fl_jantar is None else bool(src.fl_jantar),
        ativo=True,
    )


def garantir_acompanhantes_do_dia(data_ref=None, commit=True):
    """Copia refeições de acompanhante para o dia (e preenche dias intermediários).

    Enquanto o paciente permanecer no mapa, o acompanhante aparece em cada dia
    desde o lançamento até a saída com motivo — inclusive dias que foram pulados.
    """
    data_ref = data_ref or date.today()
    since = data_ref - timedelta(days=_MAPA_LOOKBACK_DIAS)

    # Pacientes ativos no mapa em qualquer dia do período (até data_ref)
    mapa_rows = (
        db.session.query(NutMapaRefeicao.paciente_id, NutMapaRefeicao.data_refeicao)
        .filter(
            NutMapaRefeicao.ativo.is_(True),
            NutMapaRefeicao.paciente_id.isnot(None),
            NutMapaRefeicao.data_refeicao >= since,
            NutMapaRefeicao.data_refeicao <= data_ref,
        )
        .distinct()
        .all()
    )
    dias_por_paciente = {}
    for pid, dmapa in mapa_rows:
        if not pid or not dmapa:
            continue
        dias_por_paciente.setdefault(pid, set()).add(dmapa)
    if not dias_por_paciente:
        return 0

    pids = list(dias_por_paciente.keys())

    # Todas as linhas de acompanhante do período (ativas e inativas no dia)
    ac_rows = (
        NutRefeicaoAcompanhante.query
        .filter(
            NutRefeicaoAcompanhante.paciente_id.in_(pids),
            db.or_(
                NutRefeicaoAcompanhante.data_refeicao.is_(None),
                db.and_(
                    NutRefeicaoAcompanhante.data_refeicao >= since,
                    NutRefeicaoAcompanhante.data_refeicao <= data_ref,
                ),
            ),
        )
        .all()
    )

    # chave -> {data: row} e fontes ativas mais recentes por chave
    por_chave_dias = {}
    fontes = {}  # chave -> melhor fonte ativa (data mais recente <= data_ref)
    for r in ac_rows:
        key = _chave_acompanhante(r)
        if not key[0] or not key[1]:
            continue
        d = r.data_refeicao
        por_chave_dias.setdefault(key, {})
        if d is not None:
            por_chave_dias[key][d] = r
        if not r.ativo:
            continue
        # fonte: preferir a mais recente com data, senão NULL conta como origem antiga
        cur = fontes.get(key)
        if cur is None:
            fontes[key] = r
            continue
        cd = cur.data_refeicao
        if d is None:
            continue
        if cd is None or d >= cd:
            fontes[key] = r

    criadas = 0
    for key, src in fontes.items():
        pid = key[0]
        dias_mapa = dias_por_paciente.get(pid) or set()
        if not dias_mapa:
            continue
        # A partir do primeiro lançamento (ou do 1º dia do paciente no mapa no lookback)
        inicio = src.data_refeicao
        if inicio is None:
            inicio = min(dias_mapa)
        for dia in sorted(dias_mapa):
            if dia < inicio or dia > data_ref:
                continue
            existentes_dia = por_chave_dias.get(key) or {}
            if dia in existentes_dia:
                # já tem linha (ativa ou baixa do dia) — não recria
                continue
            clone = _clonar_acompanhante_no_dia(src, dia)
            db.session.add(clone)
            por_chave_dias.setdefault(key, {})[dia] = clone
            criadas += 1

    if criadas and commit:
        db.session.commit()
    return criadas


def baixar_acompanhantes_do_paciente(paciente_id, motivo=None, data_saida=None):
    """Baixa (soft) todos os acompanhantes ativos do paciente (saída do mapa)."""
    if not paciente_id:
        return 0
    motivo = ((motivo or 'Baixa paciente').strip() or 'Baixa paciente')[:40]
    data_ref = data_saida or date.today()
    rows = (
        NutRefeicaoAcompanhante.query
        .filter_by(paciente_id=paciente_id, ativo=True)
        .all()
    )
    for row in rows:
        row.ativo = False
        row.data_saida = data_ref
        row.motivo_saida = motivo
        row.data_atualizacao = now_brasilia()
    return len(rows)


def _fechar_mapa_do_paciente(paciente_id, usuario=None, motivo='Exclusão cadastro'):
    """Tira o paciente do mapa de hoje em diante, sem reescrever os dias anteriores.

    Se ele ainda estiver só no histórico, grava uma baixa hoje no mesmo lançamento
    para o mapa não copiá-lo de novo nos dias seguintes.
    """
    if not paciente_id:
        return
    hoje = date.today()
    motivo = ((motivo or 'Exclusão cadastro').strip() or 'Exclusão cadastro')[:40]
    linhas = NutMapaRefeicao.query.filter_by(paciente_id=paciente_id).all()
    if not linhas:
        return

    def _grupo(row):
        if row.id and not row.lancamento_grupo_id:
            garantir_grupo_lancamento(row)
        if row.lancamento_grupo_id:
            return ('g', int(row.lancamento_grupo_id))
        return ('id', row.id)

    grupos = {}
    for row in linhas:
        grupos.setdefault(_grupo(row), []).append(row)

    for rows in grupos.values():
        for row in rows:
            no_prazo = row.data_refeicao is None or row.data_refeicao >= hoje
            if row.ativo and no_prazo and not _linha_com_baixa(row):
                _aplicar_baixa_linha(row, motivo=motivo, usuario=usuario, data_saida=hoje)
        fechado = any(
            r.data_refeicao and r.data_refeicao >= hoje and _linha_com_baixa(r)
            for r in rows
        )
        if fechado:
            continue
        fontes = [
            r for r in rows
            if r.data_refeicao and r.data_refeicao < hoje and _linha_mapa_ativa_para_copia(r)
        ]
        if not fontes:
            continue
        src = max(fontes, key=lambda r: (r.data_refeicao, r.id or 0))
        garantir_grupo_lancamento(src)
        clone = _clonar_linha_mapa(src, hoje, usuario=usuario)
        db.session.add(clone)
        db.session.flush()
        garantir_grupo_lancamento(clone)
        _aplicar_baixa_linha(clone, motivo=motivo, usuario=usuario, data_saida=hoje)


def _texto_cadastro(valor):
    if valor is None:
        return ''
    return str(valor).strip()


def _campo_vazio(valor):
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    return False


def _completar_cadastro_principal(principal, duplicados):
    """O principal guarda o que já tem e recebe o que só existia nos outros."""
    campos = (
        'sexo', 'nascimento', 'prontuario', 'clinica', 'enfermaria', 'leito',
        'dieta', 'altura_cm', 'peso_kg', 'codigo_legado',
    )
    for campo in campos:
        if not _campo_vazio(getattr(principal, campo)):
            continue
        for dup in duplicados:
            valor = getattr(dup, campo)
            if not _campo_vazio(valor):
                setattr(principal, campo, valor)
                break
    for campo in ('diagnostico', 'observacoes'):
        base = _texto_cadastro(getattr(principal, campo))
        extras = []
        for dup in duplicados:
            extra = _texto_cadastro(getattr(dup, campo))
            if extra and extra != base and extra not in extras:
                extras.append(extra)
        if extras:
            setattr(principal, campo, '\n'.join([base] + extras).strip() if base else '\n'.join(extras))
    admissoes = [principal.admissao] + [dup.admissao for dup in duplicados]
    admissoes = [dia for dia in admissoes if dia]
    if admissoes:
        principal.admissao = min(admissoes)


def _assumir_internacao_se_preciso(principal, duplicados):
    """Se algum cadastro ainda está internado, o principal continua no sistema."""
    def internado(pac):
        return bool(pac.ativo) and not bool(pac.excluido)

    if internado(principal):
        principal.excluido = False
        principal.data_saida = None
        principal.hora_saida = None
        principal.motivo_saida = None
        return
    ativos = [dup for dup in duplicados if internado(dup)]
    if not ativos:
        principal.ativo = False
        if not principal.data_saida:
            saidas = [dup.data_saida for dup in duplicados if dup.data_saida]
            if saidas:
                principal.data_saida = max(saidas)
        return
    atual = max(ativos, key=lambda pac: ((pac.admissao or date.min), pac.id or 0))
    for campo in ('clinica', 'enfermaria', 'leito', 'dieta'):
        valor = getattr(atual, campo)
        if not _campo_vazio(valor):
            setattr(principal, campo, valor)
    principal.ativo = True
    principal.excluido = False
    principal.data_saida = None
    principal.hora_saida = None
    principal.motivo_saida = None


def unificar_pacientes(principal, duplicados, usuario=None):
    """Leva mapa, acompanhante, avaliação e evolução para o principal e some com o resto.

    Os outros cadastros ficam excluídos: não entram em lista, relatório nem marcação.
    """
    if not principal:
        raise ValueError('Escolha o paciente principal.')
    outros = []
    vistos = set()
    for dup in duplicados or []:
        if not dup or dup.id == principal.id or dup.id in vistos:
            continue
        if bool(dup.excluido) or bool(principal.excluido):
            raise ValueError('Paciente já unificado não entra de novo.')
        if (
            dup.cliente_id and principal.cliente_id
            and int(dup.cliente_id) != int(principal.cliente_id)
        ):
            raise ValueError('Os pacientes precisam ser do mesmo hospital.')
        vistos.add(dup.id)
        outros.append(dup)
    if not outros:
        raise ValueError('Leve ao menos dois pacientes para unificar.')

    _completar_cadastro_principal(principal, outros)
    _assumir_internacao_se_preciso(principal, outros)
    principal.excluido = False

    hoje = date.today()
    hora = datetime.now().strftime('%H:%M:%S')
    for dup in outros:
        NutMapaRefeicao.query.filter_by(paciente_id=dup.id).update({
            NutMapaRefeicao.paciente_id: principal.id,
            NutMapaRefeicao.nome: principal.nome,
            NutMapaRefeicao.prontuario: principal.prontuario,
        }, synchronize_session=False)
        NutRefeicaoAcompanhante.query.filter_by(paciente_id=dup.id).update({
            NutRefeicaoAcompanhante.paciente_id: principal.id,
        }, synchronize_session=False)
        NutAvaliacaoNutricional.query.filter_by(paciente_id=dup.id).update({
            NutAvaliacaoNutricional.paciente_id: principal.id,
        }, synchronize_session=False)
        NutEvolucaoPaciente.query.filter_by(paciente_id=dup.id).update({
            NutEvolucaoPaciente.paciente_id: principal.id,
        }, synchronize_session=False)
        dup.excluido = True
        dup.ativo = False
        dup.unificado_em_id = principal.id
        dup.data_saida = dup.data_saida or hoje
        dup.motivo_saida = 'Unificação'
        if not dup.hora_saida:
            dup.hora_saida = hora
    return principal


def chave_nome_unificacao(nome):
    """Nome comparável: sem acento, sem caixa e com um espaço só entre as palavras."""
    texto = unicodedata.normalize('NFD', str(nome or ''))
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    texto = texto.casefold()
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def escolher_principal_unificacao(membros, contagem_mapa=None):
    """Internado, prontuário, mais linhas de mapa e, por fim, o menor id."""
    contagem_mapa = contagem_mapa or {}

    def ordem(pac):
        internado = bool(pac.ativo) and not bool(getattr(pac, 'excluido', False))
        tem_prontuario = bool(_texto_cadastro(getattr(pac, 'prontuario', None)))
        mapas = int(contagem_mapa.get(pac.id, 0) or 0)
        return (0 if internado else 1, 0 if tem_prontuario else 1, -mapas, pac.id or 0)

    return min(membros, key=ordem)


def listar_grupos_duplicados_nascimento():
    """Grupos com o mesmo hospital, o mesmo nome e a mesma data de nascimento.

    Sem nascimento não entra. Quem já foi excluído também não.
    """
    from sqlalchemy import func
    pacientes = (
        NutPaciente.query
        .filter(NutPaciente.nascimento.isnot(None))
        .filter(db.or_(NutPaciente.excluido.is_(None), NutPaciente.excluido.is_(False)))
        .all()
    )
    contagem = dict(
        db.session.query(NutMapaRefeicao.paciente_id, func.count(NutMapaRefeicao.id))
        .filter(NutMapaRefeicao.paciente_id.isnot(None))
        .group_by(NutMapaRefeicao.paciente_id)
        .all()
    )
    agrupados = {}
    for pac in pacientes:
        nome = chave_nome_unificacao(pac.nome)
        if not nome or not pac.nascimento:
            continue
        chave = (pac.cliente_id, nome, pac.nascimento)
        agrupados.setdefault(chave, []).append(pac)
    grupos = []
    for (cliente_id, nome, nascimento), membros in agrupados.items():
        if len(membros) < 2:
            continue
        principal = escolher_principal_unificacao(membros, contagem)
        outros = [pac for pac in membros if pac.id != principal.id]
        grupos.append({
            'cliente_id': cliente_id,
            'nome': nome,
            'nascimento': nascimento,
            'principal': principal,
            'outros': outros,
            'contagem_mapa': contagem,
        })
    grupos.sort(key=lambda g: (g['cliente_id'] or 0, g['nome'], g['nascimento'], g['principal'].id or 0))
    return grupos


def aplicar_unificacao_duplicados(usuario='unificacao'):
    """Unifica cada grupo duplicado. Não grava sozinho: quem chama dá o commit."""
    grupos = listar_grupos_duplicados_nascimento()
    desativados = 0
    for grupo in grupos:
        unificar_pacientes(grupo['principal'], grupo['outros'], usuario=usuario)
        desativados += len(grupo['outros'])
    return {'grupos': len(grupos), 'desativados': desativados}


def excluir_paciente_cadastro(paciente, usuario=None):
    """Apaga o paciente do cadastro. Alta (ativo=False) continua visível; este some da lista."""
    if not paciente:
        return None
    hoje = date.today()
    paciente.excluido = True
    paciente.ativo = False
    paciente.data_saida = paciente.data_saida or hoje
    if not (paciente.motivo_saida or '').strip():
        paciente.motivo_saida = 'Exclusão cadastro'
    if not paciente.hora_saida:
        paciente.hora_saida = datetime.now().strftime('%H:%M:%S')
    _fechar_mapa_do_paciente(paciente.id, usuario=usuario, motivo='Exclusão cadastro')
    baixar_acompanhantes_do_paciente(
        paciente.id,
        motivo='Exclusão cadastro',
        data_saida=paciente.data_saida,
    )
    return paciente


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
        baixar_acompanhantes_do_paciente(
            row.paciente_id,
            motivo=motivo,
            data_saida=data_ref,
        )
    return row


def listar_avisos_alta_mapa(data_ref=None, garantir=True):
    """Pacientes com alta anteriores à data do mapa, ainda presentes nas linhas ativas."""
    from sqlalchemy.orm import joinedload
    data_ref = data_ref or date.today()
    if garantir:
        garantir_mapa_do_dia(data_ref)
    alta_pac = NutMapaRefeicao.paciente.has(db.and_(
        NutPaciente.data_saida.isnot(None),
        NutPaciente.data_saida < data_ref,
    ))
    alta_linha = db.and_(
        NutMapaRefeicao.data_saida.isnot(None),
        NutMapaRefeicao.data_saida < data_ref,
    )
    rows = (
        NutMapaRefeicao.query
        .options(joinedload(NutMapaRefeicao.paciente))
        .filter(
            NutMapaRefeicao.data_refeicao == data_ref,
            NutMapaRefeicao.ativo.is_(True),
            db.or_(alta_pac, alta_linha),
        )
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


_VOL_UMA_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(ML|MG|G|L)\b', re.IGNORECASE)
_MLH_UMA_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*ML\s*/\s*H\b', re.IGNORECASE)
_AGUA_UMA_RE = re.compile(
    r'(?:TOT(?:AL)?\.?\s*)?(?:ÁGUA|AGUA)\s*[:\-]\s*(\d+(?:[.,]\d+)?)',
    re.IGNORECASE,
)
_VIA_UMA_RE = re.compile(
    r'(MAMADEIRA\s+DR\s+BROWN|MAMADEIRA\s+KUKA|'
    r'MAMADEIRA\s+C\s*/\s*BICO(?:\s*-\s*V\.?\s*O\.?)?|'
    r'FRASCO\s*-\s*V\.?\s*O\.?|COPO\s*-\s*V\.?\s*O\.?|'
    r'CHUCA|SNE|SNG|SOG|GTT|GASTROSTOMIA|JEJUNOSTOMIA|'
    r'MAM\s*[0-2]|V\.?\s*O\.?)',
    re.IGNORECASE,
)
_HORAS_PREFIX_UMA_RE = re.compile(
    r'\b(?:HOR[AÁ]RIOS?|DIETAS?|[DH])\s*[:\-]\s*((?:\d{1,2}(?!\d)\s*[,/;]\s*)+\d{1,2}(?!\d))',
    re.IGNORECASE,
)
_HORAS_SLASH_UMA_RE = re.compile(r'(?:\d{1,2}(?!\d)\s+/\s+)+\d{1,2}(?!\d)')
_HORA_SOLTA_UMA_RE = re.compile(r'(?:^|\s)(\d{1,2})(?!\d)\s*/(?=\s|$)')


def _num_uma(txt):
    s = (txt or '').strip()
    if not s:
        return 0.0
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _fmt_num_uma(valor, casas=0):
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        valor = 0.0
    txt = f'{valor:.{casas}f}'
    inteiro, _, frac = txt.partition('.')
    if casas:
        return f'{inteiro},{frac}'
    return inteiro


def _horas_texto_uma(texto):
    found = []

    def _add(nums):
        for n in nums:
            try:
                h = int(n)
            except (TypeError, ValueError):
                continue
            if 1 <= h <= 24 and h not in found:
                found.append(h)

    bruto = texto or ''
    for m in _HORAS_PREFIX_UMA_RE.finditer(bruto):
        _add(re.findall(r'\d{1,2}', m.group(1)))
    if not found:
        for m in _HORAS_SLASH_UMA_RE.finditer(bruto):
            _add(re.findall(r'\d{1,2}', m.group(0)))
    if not found:
        _add(_HORA_SOLTA_UMA_RE.findall(bruto))
    return found


def _volume_texto_uma(texto):
    achados = list(_VOL_UMA_RE.finditer(texto or ''))
    if not achados:
        return 0.0, ''
    m = achados[-1]
    num = _num_uma(m.group(1))
    un = m.group(2).upper()
    if un == 'L':
        num *= 1000.0
        un = 'ML'
    return num, un


def _sistema_texto_uma(texto, categoria):
    t = (texto or '').upper()
    if re.search(r'\bFECHAD', t) or re.search(r'\bSIS(?:TEMA)?\s*[:=]?\s*F\b', t):
        return 'F'
    if re.search(r'\bABERT', t) or re.search(r'\bSIS(?:TEMA)?\s*[:=]?\s*A\b', t):
        return 'A'
    if categoria in ('enteral', 'formula_infantil'):
        return 'A'
    return ''


def _aceita_sistema_uma(codigo, sistema, categoria):
    if categoria not in ('enteral', 'formula_infantil'):
        return True
    sistema = (sistema or 'aberto').strip().lower()
    if sistema == 'ambos':
        return True
    if sistema == 'fechado':
        return codigo == 'F'
    return codigo != 'F'


def _produto_exibicao_uma(texto):
    """Nome do produto sem horários, via ou marca de sistema."""
    t = texto or ''
    t = _HORAS_PREFIX_UMA_RE.sub(' ', t)
    t = _HORAS_SLASH_UMA_RE.sub(' ', t)
    t = _HORA_SOLTA_UMA_RE.sub(' ', t)
    t = _VIA_UMA_RE.sub(' ', t)
    t = _MLH_UMA_RE.sub(' ', t)
    t = _AGUA_UMA_RE.sub(' ', t)
    t = re.sub(r'\b(FECHADO|ABERTO)\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bSIS(?:TEMA)?\s*[:=]?\s*[AF]\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+/\s+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip(' -/')
    return t or (texto or '').strip()


def _via_texto_uma(texto):
    m = _VIA_UMA_RE.search(texto or '')
    if not m:
        return ''
    via = re.sub(r'\s+', ' ', m.group(1).upper()).strip()
    via = via.replace('V. O.', 'V. O.').replace('V.O.', 'V. O.')
    if via.startswith('FRASCO'):
        return 'FRASCO - V. O.'
    if via in ('V. O.', 'V.O.', 'VO'):
        return 'V. O.'
    return via


def _agua_texto_uma(texto):
    m = _AGUA_UMA_RE.search(texto or '')
    if not m:
        return 0.0
    return _num_uma(m.group(1))


def _mlh_texto_uma(texto):
    m = _MLH_UMA_RE.search(texto or '')
    if not m:
        return 0.0
    return _num_uma(m.group(1))


def _compact_vol_uma(num, un):
    if not num or not un:
        return ''
    if abs(num - round(num)) < 0.001:
        n = str(int(round(num)))
    else:
        n = _fmt_num_uma(num, 1)
    return f'{n}{un}'


def _marcado_uma(valor):
    if valor is True or valor == 1:
        return True
    if isinstance(valor, str) and valor.strip().lower() in ('1', 'true', 'on', 'sim', 's', 'x'):
        return True
    return False


def _linha_legivel_uma(item):
    """Converte um item da grade em texto que o mapa da U.M.A. já sabe ler."""
    nome = ''
    for chave in ('extra', 'suplemento', 'dieta', 'formula', 'lve', 'nome'):
        val = item.get(chave)
        if isinstance(val, str) and val.strip():
            nome = val.strip()
            break
    partes = [nome]
    diluicao = str(item.get('diluicao') or '').strip()
    if diluicao:
        partes.append(f'DIL {diluicao}')
    volume = str(item.get('volume') or '').strip()
    unid = str(item.get('unid') or '').strip()
    if volume:
        partes.append(volume)
        if unid:
            partes.append(unid)
    horas = [h for h in range(1, 25) if _marcado_uma(item.get(f'h{h}'))]
    if horas:
        partes.append('D: ' + ' / '.join(str(h) for h in horas) + ' /')
    vol_dieta = str(item.get('vol_dieta') or '').strip()
    unidade = str(item.get('unidade') or '').strip()
    if (vol_dieta or unidade) and vol_dieta != volume:
        partes.append(f'{vol_dieta} {unidade}'.strip())
    vol_agua = str(item.get('vol_agua') or '').strip()
    if vol_agua:
        partes.append(f'AGUA: {vol_agua}')
    via = str(item.get('via') or item.get('via_dieta') or '').strip()
    if via:
        partes.append(via)
    sistema = str(item.get('sistema') or '').strip().lower()
    if sistema in ('fechado', 'f'):
        partes.append('FECHADO')
    elif sistema in ('aberto', 'a'):
        partes.append('ABERTO')
    gotejamento = str(item.get('gotejamento') or '').strip()
    if gotejamento and gotejamento not in ('0', '0,0', '0,00', '0.0', '0.00'):
        partes.append(f'{gotejamento} ML/H')
    return ' '.join(p for p in partes if p).strip()


def itens_campo_uma(texto):
    """Itens estruturados gravados na grade ({uma_itens: [...]})."""
    bruto = (texto or '').strip()
    if not bruto.startswith('{'):
        return []
    try:
        data = json.loads(bruto)
    except (TypeError, ValueError):
        return []
    itens = data.get('uma_itens') if isinstance(data, dict) else None
    if not isinstance(itens, list):
        return []
    return [item for item in itens if isinstance(item, dict)]


def descricoes_campo_uma(texto):
    """Lista de itens de extras/suplementos/enteral/fórmula/LVE.

    Aceita o JSON da grade ({uma_itens: [...]}) e o texto livre antigo.
    """
    bruto = (texto or '').strip()
    if not bruto:
        return []
    if bruto.startswith('{'):
        try:
            data = json.loads(bruto)
        except (TypeError, ValueError):
            data = None
        itens = data.get('uma_itens') if isinstance(data, dict) else None
        if isinstance(itens, list):
            saida = []
            for item in itens:
                if not isinstance(item, dict):
                    continue
                linha = _linha_legivel_uma(item)
                if linha:
                    saida.append(linha)
            return saida
    return [p.strip() for p in re.split(r'[\n;]+', bruto) if p.strip()]


def _chave_leito_uma(leito):
    s = (leito or '').strip()
    m = re.search(r'\d+', s)
    return (int(m.group()) if m else 10 ** 9, s.upper())


def _mapa_grupo_dieta_uma():
    mapa = {}
    for row in NutDieta.query.all():
        nome = (row.nome or '').strip().upper()
        if nome:
            mapa[nome] = (row.grupo or '').strip()
    return mapa


def _mapa_grupos_por_clinica_uma():
    out = {}
    grupos = (
        NutGrupoClinica.query
        .filter_by(ativo=True)
        .order_by(NutGrupoClinica.nome)
        .all()
    )
    for g in grupos:
        for c in (g.clinicas or []):
            key = (c.nome or '').strip().upper()
            if key:
                out.setdefault(key, []).append(g.nome)
    return out


def _filtrar_linhas_mapa_uma(linhas, imprimir_por, filtro_id, filtro_nome, grupo_id, grupo_nome):
    filtro_nome = (filtro_nome or '').strip()
    if grupo_id or grupo_nome:
        nomes = set(nomes_clinicas_do_grupo(grupo_id, grupo_nome))
        if nomes:
            linhas = [l for l in linhas if (l.clinica or '').strip().upper() in nomes]
        else:
            linhas = []
    if imprimir_por == 'grupo_clinica' and (filtro_id or filtro_nome):
        nomes = set(nomes_clinicas_do_grupo(filtro_id, filtro_nome))
        if nomes:
            linhas = [l for l in linhas if (l.clinica or '').strip().upper() in nomes]
        elif filtro_nome:
            linhas = [l for l in linhas if (l.clinica or '').strip().upper() == filtro_nome.upper()]
    elif imprimir_por == 'clinica' and filtro_nome:
        linhas = [l for l in linhas if (l.clinica or '').strip().upper() == filtro_nome.upper()]
    elif imprimir_por == 'enfermaria' and filtro_id:
        try:
            enf = NutEnfermaria.query.get(int(filtro_id))
        except (TypeError, ValueError):
            enf = None
        if enf:
            leitos = {(lt.nome or '').strip().upper() for lt in (enf.leitos or [])}
            leitos |= {str(lt.numero) for lt in (enf.leitos or []) if lt.numero is not None}
            nome_enf = (enf.nome or '').strip().upper()
            filtradas = []
            for l in linhas:
                leito = (l.leito or '').strip().upper()
                clinica = (l.clinica or '').strip().upper()
                enf_linha = (l.enfermaria or '').strip().upper()
                if leito in leitos or enf_linha == nome_enf or nome_enf in clinica or clinica == nome_enf:
                    filtradas.append(l)
            linhas = filtradas
    return linhas, filtro_nome


def totalizar_mapa_uma(
    data_ref,
    categoria='enteral',
    imprimir_por='clinica',
    filtro_id=None,
    filtro_nome=None,
    horarios=None,
    amostra=None,
    grupo_clinica_id=None,
    grupo_clinica_nome=None,
    selecionar_horarios=None,
    coluna_extra='diagnostico',
    sistema='aberto',
    tipo_mapa='trabalho',
    linhas_em_branco=0,
    separar_grupo=False,
    nao_imprimir_produto=False,
):
    """Monta o mapa da U.M.A. (enteral, fórmula infantil, suplementos ou LVE)."""
    from collections import defaultdict

    data_ref = data_ref or date.today()
    garantir_mapa_do_dia(data_ref)
    categoria = CAMPO_UMA.get(categoria, 'enteral') and categoria
    if categoria not in CAMPO_UMA:
        categoria = 'enteral'
    campo = CAMPO_UMA[categoria]
    coluna_extra = 'grupo_dieta' if coluna_extra == 'grupo_dieta' else 'diagnostico'
    sistema = (sistema or 'aberto').strip().lower()
    if sistema not in ('aberto', 'fechado', 'ambos'):
        sistema = 'aberto'
    tipo_mapa = 'cobranca' if tipo_mapa == 'cobranca' else 'trabalho'
    try:
        linhas_em_branco = int(linhas_em_branco or 0)
    except (TypeError, ValueError):
        linhas_em_branco = 0
    linhas_em_branco = max(0, min(linhas_em_branco, 40))

    horas_pedidas = []
    for h in (horarios or []):
        try:
            n = int(h)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 24 and n not in horas_pedidas:
            horas_pedidas.append(n)
    if selecionar_horarios is None:
        selecionar = bool(horas_pedidas)
    else:
        selecionar = bool(selecionar_horarios)
    colunas_horas = sorted(horas_pedidas) if selecionar and horas_pedidas else list(range(1, 25))
    horas_set = set(colunas_horas)

    q = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True)
    linhas = q.order_by(NutMapaRefeicao.clinica, NutMapaRefeicao.leito, NutMapaRefeicao.nome).all()
    linhas, filtro_nome = _filtrar_linhas_mapa_uma(
        linhas, imprimir_por, filtro_id, filtro_nome, grupo_clinica_id, grupo_clinica_nome,
    )

    grupo_rotulo = (grupo_clinica_nome or '').strip()
    if grupo_clinica_id and not grupo_rotulo:
        try:
            grp = NutGrupoClinica.query.get(int(grupo_clinica_id))
        except (TypeError, ValueError):
            grp = None
        if grp:
            grupo_rotulo = grp.nome or ''

    grupos_dieta = _mapa_grupo_dieta_uma()
    grupos_clinica = _mapa_grupos_por_clinica_uma()
    mostrar_produto = not bool(nao_imprimir_produto)

    totais = defaultdict(lambda: {'item': '', 'qtd_pacientes': 0, 'leitos': [], 'pacientes': []})
    detalhe = []
    montadas = []

    for l in linhas:
        partes = descricoes_campo_uma(getattr(l, campo, None))
        if not partes:
            continue
        for item in partes:
            codigo_sis = _sistema_texto_uma(item, categoria)
            if not _aceita_sistema_uma(codigo_sis, sistema, categoria):
                continue
            horas_item = _horas_texto_uma(item)
            if selecionar and horas_item:
                visiveis = [h for h in horas_item if h in horas_set]
                if not visiveis:
                    continue
            else:
                visiveis = [h for h in horas_item if h in horas_set] if horas_item else []
            vol_num, un = _volume_texto_uma(item)
            etapas = len(visiveis) if horas_item else 0
            total_num = (vol_num * etapas) if etapas and vol_num else 0.0
            agua = _agua_texto_uma(item)
            mlh = _mlh_texto_uma(item)
            dieta_nome = (l.dieta or '').strip()
            grupo_dieta = grupos_dieta.get(dieta_nome.upper(), '')
            extra = grupo_dieta if coluna_extra == 'grupo_dieta' else (l.diagnostico or '')
            idade = ''
            if l.idade is not None:
                idade = f'{int(l.idade)}A'
            clinica = (l.clinica or '').strip()
            enfermaria = (l.enfermaria or '').strip()
            leito = (l.leito or '').strip()
            if enfermaria and leito:
                enf_leito = f'{enfermaria}/{leito}'
            else:
                enf_leito = leito or enfermaria
            titulo_sec = clinica or 'Sem clínica'
            if enfermaria and enfermaria.upper() != clinica.upper():
                titulo_sec = f'{titulo_sec} / {enfermaria}' if clinica else enfermaria
            produto = _produto_exibicao_uma(item) if mostrar_produto else ''
            horas_txt = (' / '.join(str(h) for h in visiveis) + ' /') if visiveis else ''
            linha = {
                'item': item,
                'produto': produto,
                'paciente': l.nome or '',
                'nome': l.nome or '',
                'leito': leito,
                'enf_leito': enf_leito,
                'prontuario': l.prontuario or '',
                'clinica': clinica,
                'enfermaria': enfermaria,
                'clinica_key': clinica.upper(),
                'titulo_secao': titulo_sec,
                'dieta': dieta_nome,
                'diagnostico': l.diagnostico or '',
                'grupo_dieta': grupo_dieta,
                'extra': extra,
                'idade': idade,
                'volume': _compact_vol_uma(vol_num, un),
                'volume_lve': _fmt_num_uma(vol_num, 3) if vol_num else '',
                'volume_num': vol_num,
                'unidade': un or ('ML' if categoria == 'lve' else ''),
                'etapas': etapas if horas_item else '',
                'total': (f'{_fmt_num_uma(total_num, 1)} {un}' if total_num and un else ''),
                'total_lve': _fmt_num_uma(total_num, 3) if total_num else '',
                'total_infantil': (_fmt_num_uma(total_num, 0) if total_num and abs(total_num - round(total_num)) < 0.001 else (_fmt_num_uma(total_num, 1) if total_num else '')),
                'vol_infantil': (_fmt_num_uma(vol_num, 0) if vol_num and abs(vol_num - round(vol_num)) < 0.001 else (_fmt_num_uma(vol_num, 1) if vol_num else '')),
                'agua': f'{_fmt_num_uma(agua, 1)} ML',
                'mlh': _fmt_num_uma(mlh, 0),
                'horas': visiveis,
                'horas_txt': horas_txt,
                'horas_enteral': (f'D: {horas_txt}' if horas_txt else ''),
                'via': _via_texto_uma(item),
                'sis': codigo_sis,
                'amostra': False,
            }
            montadas.append(linha)
            key = item.upper()
            totais[key]['item'] = item if mostrar_produto else ''
            totais[key]['qtd_pacientes'] += 1
            if leito:
                totais[key]['leitos'].append(leito)
            if l.nome:
                totais[key]['pacientes'].append(l.nome)
            detalhe.append({
                'item': item if mostrar_produto else '',
                'paciente': l.nome or '',
                'leito': leito,
                'prontuario': l.prontuario or '',
                'clinica': clinica,
                'dieta': dieta_nome,
                'horas': visiveis,
                'sis': codigo_sis,
            })

    montadas.sort(key=lambda r: (
        r['clinica_key'],
        (r['enfermaria'] or '').upper(),
        _chave_leito_uma(r['leito']),
        (r['nome'] or '').upper(),
        (r['produto'] or r['item'] or '').upper(),
    ))

    secoes_map = {}
    ordem_sec = []
    for row in montadas:
        sk = (row['clinica_key'], (row['enfermaria'] or '').upper(), row['titulo_secao'])
        if sk not in secoes_map:
            secoes_map[sk] = {
                'titulo': row['titulo_secao'],
                'clinica': row['clinica'],
                'enfermaria': row['enfermaria'],
                'clinica_key': row['clinica_key'],
                'linhas': [],
                'blocos': [],
            }
            ordem_sec.append(sk)
        secoes_map[sk]['linhas'].append(row)

    for sk in ordem_sec:
        sec = secoes_map[sk]
        blocos = {}
        ordem_b = []
        for row in sec['linhas']:
            prod = (row['produto'] or row['item'] or '').strip()
            bk = prod.upper() if mostrar_produto else ''
            if bk not in blocos:
                blocos[bk] = {'produto': prod if mostrar_produto else '', 'linhas': []}
                ordem_b.append(bk)
            blocos[bk]['linhas'].append(row)
        sec['blocos'] = [blocos[k] for k in ordem_b]

    secoes = [secoes_map[k] for k in ordem_sec]
    if separar_grupo:
        buckets = {}
        ordem_g = []
        for sec in secoes:
            nomes = grupos_clinica.get(sec['clinica_key']) or ['Sem grupo']
            nome_g = nomes[0]
            if nome_g not in buckets:
                buckets[nome_g] = []
                ordem_g.append(nome_g)
            buckets[nome_g].append(sec)
        if 'Sem grupo' in ordem_g:
            ordem_g = [n for n in ordem_g if n != 'Sem grupo'] + ['Sem grupo']
        grupos = []
        for nome_g in ordem_g:
            secs = buckets[nome_g]
            grupos.append({
                'nome': nome_g,
                'secoes': secs,
                'linhas': [ln for sec in secs for ln in sec['linhas']],
            })
    else:
        grupos = [{
            'nome': '',
            'secoes': secoes,
            'linhas': montadas,
        }]

    itens = sorted(totais.values(), key=lambda x: (x['item'] or '').upper())
    amostra_valor = None
    if amostra is not None:
        try:
            amostra_valor = float(amostra)
        except (TypeError, ValueError):
            amostra_valor = 0.0
        itens.append({
            'item': f'AMOSTRA ({amostra_valor:g})',
            'qtd_pacientes': 1,
            'leitos': ['—'],
            'pacientes': ['AMOSTRA'],
            'amostra': True,
            'valor_amostra': amostra_valor,
        })

    labels = {
        'enteral': 'Enteral',
        'suplementos': 'Suplementos',
        'formula_infantil': 'Fórm. Infantis',
        'lve': 'LVE',
    }
    titulos = {
        'enteral': 'MAPA DE ENTERAL',
        'suplementos': 'MAPA DE SUPLEMENTOS',
        'formula_infantil': 'MAPA DE FÓRMULAS INFANTIS',
        'lve': 'MAPA DE LVE',
    }
    sistema_labels = {'aberto': 'ABERTO', 'fechado': 'FECHADO', 'ambos': 'AMBOS'}
    sis_label = sistema_labels.get(sistema, 'ABERTO')
    if categoria == 'enteral':
        if tipo_mapa == 'cobranca':
            subtitulo = f'PEDIDO / COBRANÇA DE DIETAS ENTERAIS - SISTEMA {sis_label}'
        else:
            subtitulo = f'MAPA DE TRABALHO - SISTEMA {sis_label}'
    elif categoria == 'suplementos':
        faixa = 'TODOS OS HORÁRIOS' if not selecionar else ' / '.join(str(h) for h in colunas_horas)
        prefixo = 'COBRANÇA - ' if tipo_mapa == 'cobranca' else ''
        subtitulo = f'{prefixo}{faixa}'
    elif tipo_mapa == 'cobranca':
        subtitulo = 'PEDIDO / COBRANÇA'
    else:
        subtitulo = ''
    layout = 'lista'
    if tipo_mapa == 'trabalho' and categoria in ('enteral', 'formula_infantil', 'lve'):
        layout = 'grade'

    return {
        'data': data_ref.isoformat(),
        'data_label': data_ref.strftime('%d/%m/%Y'),
        'emitido_em': fmt_brasilia(now_brasilia(), '%d/%m/%Y %H:%M:%S'),
        'empresa': 'São Geraldo Refeições e Alimentos',
        'categoria': categoria,
        'categoria_label': labels.get(categoria, categoria),
        'titulo': titulos.get(categoria, 'MAPA DA U.M.A.'),
        'subtitulo': subtitulo,
        'layout': layout,
        'tipo_mapa': tipo_mapa,
        'tipo_mapa_label': 'Cobrança' if tipo_mapa == 'cobranca' else 'Trabalho',
        'sistema': sistema,
        'sistema_label': {'aberto': 'Aberto', 'fechado': 'Fechado', 'ambos': 'Ambos'}.get(sistema, 'Aberto'),
        'coluna_extra': coluna_extra,
        'coluna_extra_label': 'Grupo da dieta' if coluna_extra == 'grupo_dieta' else 'Diagnóstico',
        'nao_imprimir_produto': not mostrar_produto,
        'linhas_em_branco': linhas_em_branco,
        'separar_grupo': bool(separar_grupo),
        'imprimir_por': imprimir_por,
        'filtro_nome': filtro_nome or 'TODOS',
        'grupo_nome': grupo_rotulo or 'TODOS',
        'horarios': colunas_horas,
        'selecionar_horarios': selecionar,
        'todos_horarios': not selecionar,
        'itens': itens,
        'detalhe': detalhe,
        'grupos': grupos,
        'amostra_valor': amostra_valor,
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


def _clinica_para_acompanhante(a, data_ref, clinica_por_paciente_dia=None):
    """Resolve clínica do lançamento de acompanhante (mapa do dia ou cadastro do paciente)."""
    pid = a.paciente_id
    if pid and clinica_por_paciente_dia:
        cli = clinica_por_paciente_dia.get((int(pid), data_ref))
        if cli:
            return cli
    pac = a.paciente
    if pac and (pac.clinica or '').strip():
        return (pac.clinica or '').strip()
    return 'SEM CLÍNICA'


def _somar_acompanhantes_faturamento(blocos, totais_gerais, data_de, data_ate, clinica_por_paciente_dia):
    """Inclui lançamentos de nut_refeicao_acompanhantes na categoria ACOMP."""
    from sqlalchemy import or_

    rows = (
        _q(NutRefeicaoAcompanhante)
        .filter(NutRefeicaoAcompanhante.ativo.is_(True))
        .filter(or_(
            NutRefeicaoAcompanhante.data_saida.is_(None),
            NutRefeicaoAcompanhante.data_saida > data_de,
        ))
        .filter(or_(
            NutRefeicaoAcompanhante.data_refeicao.is_(None),
            (
                (NutRefeicaoAcompanhante.data_refeicao >= data_de)
                & (NutRefeicaoAcompanhante.data_refeicao <= data_ate)
            ),
        ))
        .all()
    )
    flag_map = {
        'almoco': 'fl_almoco',
        'jantar': 'fl_jantar',
    }
    for a in rows:
        data_ref = a.data_refeicao or data_de
        if data_ref < data_de or data_ref > data_ate:
            continue
        if a.data_saida and a.data_saida <= data_ref:
            continue
        clinica = _clinica_para_acompanhante(a, data_ref, clinica_por_paciente_dia)
        data_key = data_ref.isoformat()
        qtd = max(int(a.quantidade or 1), 1)
        for ref_key, attr in flag_map.items():
            marcado = getattr(a, attr, None)
            # legado sem coluna: conta almoco e jantar
            if marcado is None:
                ativo_flag = True
            else:
                ativo_flag = bool(marcado)
            if not ativo_flag:
                continue
            blocos[clinica][data_key]['acomp'][ref_key] += qtd
            totais_gerais['acomp'][ref_key] += qtd


def relatorio_faturamento(data_de, data_ate, tipo='espelho_1', por_grupo_clinica=False, sintetico=False):
    """Gera espelho/totais de faturamento a partir do mapa + refeições acompanhante."""
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
        _q(NutMapaRefeicao)
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
    clinica_por_paciente_dia = {}
    cfg_uma = config_uma_dict()
    rotulo_agua = (cfg_uma.get('agua_produto') or cfg_uma.get('agua_coluna') or '').strip()

    for l in linhas:
        clinica = (l.clinica or 'SEM CLÍNICA').strip() or 'SEM CLÍNICA'
        data_key = l.data_refeicao.isoformat() if l.data_refeicao else data_de.isoformat()
        if l.paciente_id and l.data_refeicao:
            clinica_por_paciente_dia[(int(l.paciente_id), l.data_refeicao)] = clinica
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
            bruto_uma = getattr(l, campo, None)
            for parte in descricoes_campo_uma(bruto_uma):
                k = parte.upper()
                formulas[k]['item'] = parte
                formulas[k]['qtd'] += 1
            if rotulo_agua:
                for item in itens_campo_uma(bruto_uma):
                    if _parse_br_uma(item.get('vol_agua'), 0) > 0:
                        k = rotulo_agua.upper()
                        formulas[k]['item'] = rotulo_agua
                        formulas[k]['qtd'] += 1

        # complementares: extras / suplementos / lve
        for campo in ('extras', 'suplementos', 'lve'):
            for parte in descricoes_campo_uma(getattr(l, campo, None)):
                k = parte.upper()
                complementares[k]['item'] = parte
                complementares[k]['qtd'] += 1

    # Lançamentos de refeição acompanhante → linha ACOMP. (por clínica do paciente no dia)
    if tipo not in ('total_formulas', 'total_complementares'):
        _somar_acompanhantes_faturamento(
            blocos, totais_gerais, data_de, data_ate, clinica_por_paciente_dia
        )
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


# Mapeamento refeição do mapa → siglas do cadastro de preços (NutTipoRefeicao)
_REF_KEY_SIGLAS = {
    'desjejum': ('DESJ', 'D', 'DESJEJUM'),
    'colacao': ('COL', 'C', 'COLAÇÃO', 'COLACAO'),
    'almoco': ('ALM', 'A', 'ALMOÇO', 'ALMOCO'),
    'merenda': ('MER', 'M', 'MERENDA'),
    'jantar': ('JAN', 'J', 'JANTAR'),
    'ceia': ('CEI', 'CE', 'CEIA'),
}
_REF_KEY_LABELS = {
    'desjejum': 'Desjejum',
    'colacao': 'Colação',
    'almoco': 'Almoço',
    'merenda': 'Merenda',
    'jantar': 'Jantar',
    'ceia': 'Ceia',
}


def _norm_nome_preco(s):
    import unicodedata
    t = ' '.join((s or '').strip().upper().split())
    t = unicodedata.normalize('NFKD', t)
    return ''.join(c for c in t if not unicodedata.combining(c))


def _indexes_precos_faturamento():
    """Índices para resolver preço de dieta×tipo, catálogo plano e produtos."""
    dietas_por_nome = {}
    for d in NutDieta.query.all():
        nome = _norm_nome_preco(d.nome)
        if not nome:
            continue
        # se já existe, mantém; depois preferimos as com preço no resolver
        dietas_por_nome.setdefault(nome, d.id)

    tipos_por_sigla = {}
    tipos_por_nome = {}
    for t in NutTipoRefeicao.query.all():
        sid = t.id
        for s in (t.sigla or '',):
            k = _norm_nome_preco(s)
            if k:
                tipos_por_sigla[k] = sid
        nk = _norm_nome_preco(t.nome)
        if nk:
            tipos_por_nome[nk] = sid

    precos_dieta_tipo = {}
    dietas_com_preco = set()
    for p in NutPrecoDietaTipo.query.all():
        cell = {
            'empresa': float(p.valor_empresa or 0),
            'paciente': float(p.valor_paciente or 0),
            'acompanhante': float(p.valor_acompanhante or 0),
        }
        precos_dieta_tipo[(p.dieta_id, p.tipo_refeicao_id)] = cell
        if cell['empresa'] > 0 or cell['paciente'] > 0 or cell['acompanhante'] > 0:
            dietas_com_preco.add(p.dieta_id)

    precos_plano = {}
    for r in NutPrecoRefeicao.query.filter_by(ativo=True).all():
        nome = _norm_nome_preco(r.refeicao)
        if not nome:
            continue
        emp = float(r.valor_empresa if r.valor_empresa is not None else (r.valor or 0))
        pac = float(r.valor_paciente or 0)
        aco = float(r.valor_acompanhante or 0)
        precos_plano[nome] = {'empresa': emp, 'paciente': pac, 'acompanhante': aco}

    produtos_por_nome = {}
    for p in NutProduto.query.filter_by(ativo=True).all():
        desc = _norm_nome_preco(p.descricao)
        if not desc:
            continue
        pm = float(p.preco_medio or 0) or float(p.ult_preco or 0)
        if pm <= 0:
            continue
        if desc not in produtos_por_nome or pm > produtos_por_nome[desc]:
            produtos_por_nome[desc] = pm

    return {
        'dietas_por_nome': dietas_por_nome,
        'dietas_com_preco': dietas_com_preco,
        'tipos_por_sigla': tipos_por_sigla,
        'tipos_por_nome': tipos_por_nome,
        'precos_dieta_tipo': precos_dieta_tipo,
        'precos_plano': precos_plano,
        'produtos_por_nome': produtos_por_nome,
    }


def _resolver_dieta_id(nome_item, idx):
    """Resolve dieta com preço: match exato, senão nome-base mais adequado com preço."""
    nome = _norm_nome_preco(nome_item)
    if not nome:
        return None
    com_preco = idx.get('dietas_com_preco') or set()
    dietas = idx['dietas_por_nome']

    def pick_com_preco(chave):
        did = dietas.get(chave)
        if did and did in com_preco:
            return did
        return None

    direct = pick_com_preco(nome)
    if direct:
        return direct

    bases = [nome]
    for suf in (' COM SAL', ' SEM SAL', ' C/ SAL', ' S/ SAL'):
        if nome.endswith(suf):
            bases.append(nome[: -len(suf)].strip())
            break
    for base in bases:
        hit = pick_com_preco(base)
        if hit:
            return hit

    # (prioridade, peso, dieta_id)
    # 2 = dieta é prefixo do nome (BRANDA ⊂ BRANDA COM SAL) → maior len melhor
    # 1 = nome é prefixo da dieta (LIQUIDA ⊂ LIQUIDA COMPLETA) → menor len melhor
    candidatos = []
    for base in bases:
        if not base:
            continue
        for dnome, did in dietas.items():
            if did not in com_preco or dnome == base:
                continue
            if base.startswith(dnome + ' ') or (base.startswith(dnome) and len(base) > len(dnome)):
                candidatos.append((2, len(dnome), did))
            elif dnome.startswith(base + ' ') or (dnome.startswith(base) and len(dnome) > len(base)):
                candidatos.append((1, -len(dnome), did))
    if candidatos:
        candidatos.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidatos[0][2]

    return dietas.get(nome)


def _tipo_id_para_ref(ref_key, idx):
    for sig in _REF_KEY_SIGLAS.get(ref_key, ()):
        tid = idx['tipos_por_sigla'].get(_norm_nome_preco(sig))
        if tid:
            return tid
        tid = idx['tipos_por_nome'].get(_norm_nome_preco(sig))
        if tid:
            return tid
    return None


def _preco_unitario_item(nome_item, ref_key, payer, idx):
    """Resolve preço unitário: cadastro dieta×tipo → catálogo plano → preço médio produto."""
    payer = payer if payer in ('empresa', 'paciente', 'acompanhante') else 'empresa'
    nome = _norm_nome_preco(nome_item)

    dieta_id = _resolver_dieta_id(nome_item, idx)
    tipo_id = _tipo_id_para_ref(ref_key, idx) if ref_key else None
    if dieta_id and tipo_id:
        cell = idx['precos_dieta_tipo'].get((dieta_id, tipo_id))
        if cell:
            val = float(cell.get(payer) or 0)
            if val <= 0:
                val = float(cell.get('empresa') or 0)
            if val > 0:
                return val, 'preços refeições (dieta × tipo)'

    if nome:
        plano = idx['precos_plano'].get(nome)
        if not plano:
            for pnome, pvals in idx['precos_plano'].items():
                if nome.startswith(pnome) or pnome.startswith(nome):
                    plano = pvals
                    break
        if plano:
            val = float(plano.get(payer) or 0) or float(plano.get('empresa') or 0)
            if val > 0:
                return val, 'preços refeições (catálogo)'

        prod = idx['produtos_por_nome'].get(nome)
        if prod is None:
            for pnome, pval in idx['produtos_por_nome'].items():
                if nome.startswith(pnome) or pnome.startswith(nome) or nome in pnome or pnome in nome:
                    prod = pval
                    break
        if prod and float(prod) > 0:
            return float(prod), 'produto (preço médio)'

    return 0.0, 'sem preço'


def _add_linha_fat_valor(linhas, *, data_ref, fonte, pessoa, clinica, item, ref_key, qtd, payer, idx):
    qtd = max(int(qtd or 1), 1)
    unit, origem = _preco_unitario_item(item, ref_key, payer, idx)
    total = round(unit * qtd, 2)
    linhas.append({
        'data': data_ref.isoformat() if data_ref else '',
        'data_label': data_ref.strftime('%d/%m/%Y') if data_ref else '',
        'fonte': fonte,
        'pessoa': pessoa or '',
        'clinica': (clinica or '').strip() or 'SEM CLÍNICA',
        'item': (item or '').strip() or 'SEM ITEM',
        'refeicao': _REF_KEY_LABELS.get(ref_key, ref_key or ''),
        'refeicao_key': ref_key or '',
        'quantidade': qtd,
        'preco_unitario': round(unit, 2),
        'total': total,
        'origem_preco': origem,
        'payer': payer,
    })


def relatorio_faturamento_valores(data_de, data_ate):
    """Faturamento com valores: mapa + acompanhante + funcionários × preços."""
    from collections import defaultdict
    from sqlalchemy import or_

    data_de = data_de or date.today()
    data_ate = data_ate or data_de
    if data_ate < data_de:
        data_de, data_ate = data_ate, data_de

    cur = data_de
    dias = 0
    while cur <= data_ate and dias < 62:
        garantir_mapa_do_dia(cur)
        cur = date.fromordinal(cur.toordinal() + 1)
        dias += 1

    idx = _indexes_precos_faturamento()
    linhas = []

    mapa_rows = (
        _q(NutMapaRefeicao)
        .filter(
            NutMapaRefeicao.data_refeicao >= data_de,
            NutMapaRefeicao.data_refeicao <= data_ate,
            NutMapaRefeicao.ativo.is_(True),
        )
        .order_by(NutMapaRefeicao.data_refeicao, NutMapaRefeicao.clinica, NutMapaRefeicao.nome)
        .all()
    )

    clinica_por_paciente_dia = {}
    for l in mapa_rows:
        if l.paciente_id and l.data_refeicao:
            clinica_por_paciente_dia[(int(l.paciente_id), l.data_refeicao)] = (
                (l.clinica or '').strip() or 'SEM CLÍNICA'
            )
        dieta = (l.dieta or '').strip() or 'SEM DIETA'
        clinica = (l.clinica or '').strip() or 'SEM CLÍNICA'
        for ref_key, flag in REFEICAO_FLAGS:
            if getattr(l, flag, False):
                _add_linha_fat_valor(
                    linhas,
                    data_ref=l.data_refeicao,
                    fonte='Paciente',
                    pessoa=l.nome,
                    clinica=clinica,
                    item=dieta,
                    ref_key=ref_key,
                    qtd=1,
                    payer='empresa',
                    idx=idx,
                )
        # Itens livres (extras / enterais / etc.) → preço médio do produto ou catálogo
        for campo, label in (
            ('extras', 'Extra'),
            ('suplementos', 'Suplemento'),
            ('enteral', 'Enteral'),
            ('formula_infantil', 'Fórmula infantil'),
            ('lve', 'LVE'),
        ):
            for parte in descricoes_campo_uma(getattr(l, campo, None)):
                _add_linha_fat_valor(
                    linhas,
                    data_ref=l.data_refeicao,
                    fonte='Paciente',
                    pessoa=l.nome,
                    clinica=clinica,
                    item=parte,
                    ref_key=None,
                    qtd=1,
                    payer='empresa',
                    idx=idx,
                )

    ac_rows = (
        _q(NutRefeicaoAcompanhante)
        .filter(NutRefeicaoAcompanhante.ativo.is_(True))
        .filter(or_(
            NutRefeicaoAcompanhante.data_saida.is_(None),
            NutRefeicaoAcompanhante.data_saida > data_de,
        ))
        .filter(or_(
            NutRefeicaoAcompanhante.data_refeicao.is_(None),
            (
                (NutRefeicaoAcompanhante.data_refeicao >= data_de)
                & (NutRefeicaoAcompanhante.data_refeicao <= data_ate)
            ),
        ))
        .all()
    )
    for a in ac_rows:
        data_ref = a.data_refeicao or data_de
        if data_ref < data_de or data_ref > data_ate:
            continue
        if a.data_saida and a.data_saida <= data_ref:
            continue
        clinica = _clinica_para_acompanhante(a, data_ref, clinica_por_paciente_dia)
        dieta = (
            (a.refeicao or '').strip()
            or ((a.dieta_rel.nome if a.dieta_rel else '') or '').strip()
            or 'SEM DIETA'
        )
        qtd = max(int(a.quantidade or 1), 1)
        flags = {
            'almoco': bool(a.fl_almoco) if a.fl_almoco is not None else True,
            'jantar': bool(a.fl_jantar) if a.fl_jantar is not None else True,
        }
        for ref_key, ativo_flag in flags.items():
            if not ativo_flag:
                continue
            _add_linha_fat_valor(
                linhas,
                data_ref=data_ref,
                fonte='Acompanhante',
                pessoa=a.nome_acompanhante,
                clinica=clinica,
                item=dieta,
                ref_key=ref_key,
                qtd=qtd,
                payer='acompanhante',
                idx=idx,
            )

    func_rows = (
        _q(NutRefeicaoFuncionario)
        .filter(NutRefeicaoFuncionario.ativo.is_(True))
        .filter(or_(
            NutRefeicaoFuncionario.data_refeicao.is_(None),
            (
                (NutRefeicaoFuncionario.data_refeicao >= data_de)
                & (NutRefeicaoFuncionario.data_refeicao <= data_ate)
            ),
        ))
        .all()
    )
    for f in func_rows:
        data_ref = f.data_refeicao or data_de
        if data_ref < data_de or data_ref > data_ate:
            continue
        dieta = (
            (f.refeicao or '').strip()
            or ((f.dieta_rel.nome if f.dieta_rel else '') or '').strip()
            or 'SEM DIETA'
        )
        qtd = max(int(f.quantidade or 1), 1)
        flags = {
            'almoco': bool(f.fl_almoco) if f.fl_almoco is not None else True,
            'jantar': bool(f.fl_jantar) if f.fl_jantar is not None else True,
        }
        for ref_key, ativo_flag in flags.items():
            if not ativo_flag:
                continue
            _add_linha_fat_valor(
                linhas,
                data_ref=data_ref,
                fonte='Funcionário',
                pessoa=f.nome,
                clinica='FUNCIONÁRIOS',
                item=dieta,
                ref_key=ref_key,
                qtd=qtd,
                payer='empresa',
                idx=idx,
            )

    linhas.sort(key=lambda x: (x['data'], x['fonte'], x['clinica'], x['pessoa'], x['item'], x['refeicao']))

    resumo_fonte = defaultdict(lambda: {'quantidade': 0, 'total': 0.0})
    resumo_item = defaultdict(lambda: {'item': '', 'quantidade': 0, 'total': 0.0})
    sem_preco = 0
    for row in linhas:
        resumo_fonte[row['fonte']]['quantidade'] += row['quantidade']
        resumo_fonte[row['fonte']]['total'] += row['total']
        k = _norm_nome_preco(row['item'])
        resumo_item[k]['item'] = row['item']
        resumo_item[k]['quantidade'] += row['quantidade']
        resumo_item[k]['total'] += row['total']
        if row['preco_unitario'] <= 0:
            sem_preco += 1

    total_qtd = sum(r['quantidade'] for r in linhas)
    total_valor = round(sum(r['total'] for r in linhas), 2)

    return {
        'data_de': data_de.isoformat(),
        'data_ate': data_ate.isoformat(),
        'data_de_label': data_de.strftime('%d/%m/%Y'),
        'data_ate_label': data_ate.strftime('%d/%m/%Y'),
        'titulo': 'Faturamento com valores',
        'linhas': linhas,
        'resumo_fontes': [
            {'fonte': f, 'quantidade': v['quantidade'], 'total': round(v['total'], 2)}
            for f, v in sorted(resumo_fonte.items())
        ],
        'resumo_itens': sorted(
            [
                {'item': v['item'], 'quantidade': v['quantidade'], 'total': round(v['total'], 2)}
                for v in resumo_item.values()
            ],
            key=lambda x: x['item'].upper(),
        ),
        'total_quantidade': total_qtd,
        'total_valor': total_valor,
        'qtd_linhas': len(linhas),
        'qtd_sem_preco': sem_preco,
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
    imprimir_por='clinica',
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
        if imprimir_por == 'grupo_clinica':
            filtro_labels, nomes = expand_filtros_grupo_clinica(filtros)
            linhas = [l for l in linhas if (l.clinica or '').strip().upper() in nomes]
        else:
            # clínica
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


def totalizacao_dietas_refeicoes(
    data_ref=None,
    totalizacao_para='clinicas',
    imprimir_por='clinica',
    filtros=None,
    horarios=None,
    metodo='todas',
    imprimir_total_geral=True,
):
    """Totaliza dietas do mapa + refeições de acompanhantes + funcionários.

    Acompanhantes e funcionários não têm flags por horário: a quantidade
    cadastrada é aplicada a cada horário selecionado no relatório.
    """
    from collections import defaultdict
    from sqlalchemy import or_

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
    if not horarios:
        horarios = set(flag_map.keys())

    filtros = [str(f).strip() for f in (filtros or []) if str(f).strip()]
    filtros_upper = {f.upper() for f in filtros}
    todos = (not filtros) or ('TODOS' in filtros_upper)

    dieta_cat_map = {
        (d.nome or '').strip().upper(): (d.categoria or 'basica')
        for d in _q(NutDieta).all()
    }

    # ---- Mapa de refeições (mesmos filtros da totalização de dietas) ----
    q = _q(NutMapaRefeicao).filter_by(data_refeicao=data_ref, ativo=True)
    linhas = q.order_by(NutMapaRefeicao.dieta, NutMapaRefeicao.clinica).all()

    filtro_labels = []
    nomes_clinica = set()
    nomes_enf = set()
    leitos_filtro = set()

    if imprimir_por == 'enfermaria' and not todos:
        enfs = NutEnfermaria.query.filter(NutEnfermaria.id.in_(
            [int(x) for x in filtros if str(x).isdigit()]
        )).all() if any(str(x).isdigit() for x in filtros) else []
        if not enfs:
            enfs = NutEnfermaria.query.filter(
                db.func.upper(NutEnfermaria.nome).in_(list(filtros_upper))
            ).all()
        filtro_labels = [e.nome for e in enfs]
        nomes_enf = {e.nome.upper() for e in enfs}
        for e in enfs:
            for lt in (e.leitos or []):
                if lt.numero_leito:
                    leitos_filtro.add(lt.numero_leito.strip().upper())
        filtradas = []
        for l in linhas:
            leito = (l.leito or '').strip().upper()
            clinica = (l.clinica or '').strip().upper()
            if leito in leitos_filtro or clinica in nomes_enf or any(n in clinica for n in nomes_enf):
                filtradas.append(l)
        linhas = filtradas
    elif not todos:
        if imprimir_por == 'grupo_clinica':
            filtro_labels, nomes_clinica = expand_filtros_grupo_clinica(filtros)
        else:
            ids = [int(x) for x in filtros if str(x).isdigit()]
            if ids:
                for c in NutClinica.query.filter(NutClinica.id.in_(ids)).all():
                    nomes_clinica.add((c.nome or '').strip().upper())
                    filtro_labels.append(c.nome)
            for f in filtros:
                if not str(f).isdigit():
                    nomes_clinica.add(f.upper())
                    if f not in filtro_labels:
                        filtro_labels.append(f)
        linhas = [l for l in linhas if (l.clinica or '').strip().upper() in nomes_clinica]
    else:
        filtro_labels = ['TODOS']

    totais = defaultdict(lambda: {k: 0 for k in flag_map.keys()})
    contagem_fontes = {'mapa': 0, 'acompanhantes': 0, 'funcionarios': 0}

    for l in linhas:
        dieta = (l.dieta or '').strip() or 'SEM DIETA'
        for hk in horarios:
            flag = flag_map.get(hk)
            if flag and getattr(l, flag, False):
                totais[dieta][hk] += 1
                contagem_fontes['mapa'] += 1

    # Pacientes do mapa (para filtrar acompanhantes pela clínica do dia)
    pacientes_mapa_ok = set()
    clinica_por_paciente = {}
    for l in linhas:
        if l.paciente_id:
            pacientes_mapa_ok.add(l.paciente_id)
            clinica_por_paciente[l.paciente_id] = (l.clinica or '').strip().upper()

    # ---- Refeições acompanhante ----
    ac_q = (
        _q(NutRefeicaoAcompanhante)
        .filter(NutRefeicaoAcompanhante.ativo.is_(True))
        .filter(or_(
            NutRefeicaoAcompanhante.data_saida.is_(None),
            NutRefeicaoAcompanhante.data_saida > data_ref,
        ))
        .filter(or_(
            NutRefeicaoAcompanhante.data_refeicao == data_ref,
            NutRefeicaoAcompanhante.data_refeicao.is_(None),
        ))
    )
    acompanhantes = ac_q.all()
    for a in acompanhantes:
        if not todos:
            pid = a.paciente_id
            if imprimir_por == 'enfermaria':
                if pid not in pacientes_mapa_ok:
                    continue
            else:
                cli = clinica_por_paciente.get(pid)
                if not cli:
                    pac = a.paciente
                    cli = ((pac.clinica if pac else '') or '').strip().upper()
                if cli not in nomes_clinica:
                    continue
        dieta = (
            (a.refeicao or '').strip()
            or ((a.dieta_rel.nome if a.dieta_rel else '') or '').strip()
            or 'SEM DIETA'
        )
        qtd = max(int(a.quantidade or 1), 1)
        flags = {
            'almoco': bool(a.fl_almoco) if a.fl_almoco is not None else True,
            'jantar': bool(a.fl_jantar) if a.fl_jantar is not None else True,
        }
        for hk in horarios:
            if hk in flags:
                if flags[hk]:
                    totais[dieta][hk] += qtd
                    contagem_fontes['acompanhantes'] += qtd
            # outros horários não entram para acompanhante (só A/J)

    # ---- Refeições funcionários ----
    funcionarios = (
        _q(NutRefeicaoFuncionario)
        .filter(NutRefeicaoFuncionario.ativo.is_(True))
        .filter(or_(
            NutRefeicaoFuncionario.data_refeicao == data_ref,
            NutRefeicaoFuncionario.data_refeicao.is_(None),
        ))
        .all()
    )
    for f in funcionarios:
        dieta = (
            (f.refeicao or '').strip()
            or ((f.dieta_rel.nome if f.dieta_rel else '') or '').strip()
            or 'SEM DIETA'
        )
        qtd = max(int(f.quantidade or 1), 1)
        flags = {
            'almoco': bool(f.fl_almoco) if f.fl_almoco is not None else True,
            'jantar': bool(f.fl_jantar) if f.fl_jantar is not None else True,
        }
        for hk in horarios:
            if hk in flags and flags[hk]:
                totais[dieta][hk] += qtd
                contagem_fontes['funcionarios'] += qtd

    ordem_grupos = ['BÁSICAS', 'LÍQUIDAS', 'D.I.', 'ACOMPANHANTES']
    por_grupo = defaultdict(list)
    for nome, counts in totais.items():
        if sum(counts.values()) <= 0:
            continue
        grp = _grupo_dieta_totalizacao(nome, dieta_cat_map)
        row = {'nome': nome, 'grupo': grp, **counts, 'total': sum(counts.values())}
        por_grupo[grp].append(row)

    linhas_rel = []
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
        linhas_rel.append({
            'nome': label,
            'grupo': grp,
            'is_subtotal': True,
            **sub,
            'total': sum(sub.values()),
        })

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
        'fontes': contagem_fontes,
        'titulo': 'TOTALIZAÇÃO DE DIETAS E REFEIÇÕES',
    }


# ---- Totalização de alimentos (substituição e consumo) e cardápio servido ----

_MEAL_ORDEM_REL = ('desjejum', 'colacao', 'almoco', 'merenda', 'jantar', 'ceia')


def _meals_escolhidos(horarios):
    """Mantém a ordem Desjejum → Ceia. Vazio significa todas as refeições."""
    vistos = []
    for h in horarios or []:
        meal = tipo_refeicao_para_meal(h)
        if meal and meal not in vistos:
            vistos.append(meal)
    if not vistos:
        vistos = list(_MEAL_ORDEM_REL)
    escolhidos = set(vistos)
    return [m for m in _MEAL_ORDEM_REL if m in escolhidos]


def _resolver_filtro_local(imprimir_por, filtros):
    """Traduz o multi-select da tela em clínicas ou enfermarias do mapa."""
    filtros = [str(f).strip() for f in (filtros or []) if str(f).strip()]
    filtros_upper = {f.upper() for f in filtros}
    todos = (not filtros) or ('TODOS' in filtros_upper)
    ctx = {
        'todos': todos,
        'imprimir_por': imprimir_por if imprimir_por in ('clinica', 'enfermaria') else 'clinica',
        'labels': ['TODOS'] if todos else [],
        'nomes_clinica': set(),
        'nomes_enf': set(),
        'leitos': set(),
    }
    if todos:
        return ctx

    if ctx['imprimir_por'] == 'enfermaria':
        ids = [int(x) for x in filtros if str(x).isdigit()]
        enfs = []
        if ids:
            enfs.extend(_q(NutEnfermaria).filter(NutEnfermaria.id.in_(ids)).all())
        nomes_txt = [f for f in filtros if not str(f).isdigit()]
        if nomes_txt:
            enfs.extend(
                _q(NutEnfermaria).filter(
                    db.func.upper(NutEnfermaria.nome).in_([n.upper() for n in nomes_txt])
                ).all()
            )
        vistos = set()
        for e in enfs:
            if e.id in vistos:
                continue
            vistos.add(e.id)
            ctx['labels'].append(e.nome)
            if e.nome:
                ctx['nomes_enf'].add(e.nome.strip().upper())
            for lt in (e.leitos or []):
                if lt.nome:
                    ctx['leitos'].add(lt.nome.strip().upper())
                if lt.numero is not None:
                    ctx['leitos'].add(str(lt.numero).strip().upper())
        for n in nomes_txt:
            if n.upper() not in ctx['nomes_enf']:
                ctx['nomes_enf'].add(n.upper())
                ctx['labels'].append(n)
        return ctx

    ids = [int(x) for x in filtros if str(x).isdigit()]
    if ids:
        for c in _q(NutClinica).filter(NutClinica.id.in_(ids)).all():
            if c.nome:
                ctx['nomes_clinica'].add(c.nome.strip().upper())
                ctx['labels'].append(c.nome)
    for f in filtros:
        if not str(f).isdigit():
            ctx['nomes_clinica'].add(f.upper())
            if f not in ctx['labels']:
                ctx['labels'].append(f)
    return ctx


def _linha_no_filtro(linha, ctx):
    if ctx['todos']:
        return True
    clinica = (linha.clinica or '').strip().upper()
    enfermaria = (getattr(linha, 'enfermaria', None) or '').strip().upper()
    leito = (linha.leito or '').strip().upper()
    if ctx['imprimir_por'] == 'enfermaria':
        if enfermaria in ctx['nomes_enf'] or leito in ctx['leitos'] or clinica in ctx['nomes_enf']:
            return True
        return any(n and (n in clinica or n in enfermaria) for n in ctx['nomes_enf'])
    return clinica in ctx['nomes_clinica']


def _coluna_local(clinica, enfermaria, imprimir_por, fallback='SEM LOCAL'):
    if imprimir_por == 'enfermaria':
        nome = (enfermaria or '').strip() or (clinica or '').strip()
    else:
        nome = (clinica or '').strip()
    return nome or fallback


def _nova_contagem():
    return {'itens': {}, 'colunas': {}}


def _acumular_item(bucket, nome, coluna, qtd=1):
    nome_txt = ' '.join(str(nome or '').split())
    col_txt = ' '.join(str(coluna or '').split()) or 'SEM LOCAL'
    try:
        qtd = int(qtd)
    except (TypeError, ValueError):
        return
    if not nome_txt or qtd <= 0:
        return
    chave = _norm_txt(nome_txt)
    col_chave = _norm_txt(col_txt)
    bucket['colunas'].setdefault(col_chave, col_txt)
    item = bucket['itens'].setdefault(chave, {'nome': nome_txt.upper(), 'cols': {}})
    item['cols'][col_chave] = item['cols'].get(col_chave, 0) + qtd


def _matriz_de(bucket):
    col_chaves = sorted(bucket['colunas'], key=lambda k: bucket['colunas'][k].upper())
    colunas = [
        {'key': f'c{i}', 'label': bucket['colunas'][chave]}
        for i, chave in enumerate(col_chaves)
    ]
    idx = {chave: col['key'] for chave, col in zip(col_chaves, colunas)}
    linhas = []
    totais = {c['key']: 0 for c in colunas}
    totais['total'] = 0
    for chave in sorted(bucket['itens'], key=lambda k: bucket['itens'][k]['nome']):
        item = bucket['itens'][chave]
        row = {'nome': item['nome'], 'total': 0}
        for c in colunas:
            row[c['key']] = 0
        for col_chave, qtd in item['cols'].items():
            key = idx.get(col_chave)
            if not key:
                continue
            row[key] += qtd
            row['total'] += qtd
            totais[key] += qtd
            totais['total'] += qtd
        if row['total']:
            linhas.append(row)
    return {'colunas': colunas, 'linhas': linhas, 'totais': totais}


def _pares_da_refeicao(linha, meal):
    bruto = linha.get_substituicoes() if hasattr(linha, 'get_substituicoes') else {}
    bloco = normalize_substituicoes(bruto).get(meal) or {}
    return [
        p for p in (bloco.get('pares') or [])
        if (p.get('remover') or '').strip() or (p.get('adicionar') or '').strip()
    ]


def _pratos_padrao(dieta, dieta_id, meal, data_ref, incluir_extras=True):
    card = find_cardapio_for_meal(
        dieta, meal, data_ref, dieta_id=dieta_id, exigir_dieta=True,
    )
    if not card:
        return []
    if incluir_extras:
        return list(card.pratos)
    itens = card.itens if isinstance(card.itens, dict) else None
    if itens is None and card.id:
        row = NutCardapio.query.get(card.id)
        itens = row.get_itens() if row is not None else None
    if isinstance(itens, dict):
        return pratos_from_itens(itens, card.tipo, incluir_extras=False)
    return list(card.pratos)


def _linhas_mapa_dia(data_ref):
    garantir_mapa_do_dia(data_ref)
    return (
        _q(NutMapaRefeicao)
        .filter_by(data_refeicao=data_ref, ativo=True)
        .order_by(
            NutMapaRefeicao.clinica,
            NutMapaRefeicao.enfermaria,
            NutMapaRefeicao.leito,
            NutMapaRefeicao.nome,
        )
        .all()
    )


def _acompanhantes_do_dia(data_ref):
    from sqlalchemy import or_
    return (
        _q(NutRefeicaoAcompanhante)
        .filter(NutRefeicaoAcompanhante.ativo.is_(True))
        .filter(or_(
            NutRefeicaoAcompanhante.data_saida.is_(None),
            NutRefeicaoAcompanhante.data_saida > data_ref,
        ))
        .filter(or_(
            NutRefeicaoAcompanhante.data_refeicao == data_ref,
            NutRefeicaoAcompanhante.data_refeicao.is_(None),
        ))
        .all()
    )


def _funcionarios_do_dia(data_ref):
    from sqlalchemy import or_
    return (
        _q(NutRefeicaoFuncionario)
        .filter(NutRefeicaoFuncionario.ativo.is_(True))
        .filter(or_(
            NutRefeicaoFuncionario.data_refeicao == data_ref,
            NutRefeicaoFuncionario.data_refeicao.is_(None),
        ))
        .all()
    )


def _refeicao_extra_vale(row, meal):
    """Acompanhante e funcionário só têm almoço e jantar."""
    if meal not in ('almoco', 'jantar'):
        return False
    flag = getattr(row, MEAL_FLAG_FIELD[meal], None)
    return True if flag is None else bool(flag)


def _dieta_extra(row):
    dieta = (getattr(row, 'refeicao', None) or '').strip()
    if not dieta and getattr(row, 'dieta_rel', None) is not None:
        dieta = (row.dieta_rel.nome or '').strip()
    return dieta, getattr(row, 'dieta_id', None)


def _locais_por_paciente(linhas):
    locais = {}
    for linha in linhas:
        if not linha.paciente_id:
            continue
        atual = locais.get(linha.paciente_id)
        if atual is None or (linha.tipo_lancamento or 'principal') == 'principal':
            locais[linha.paciente_id] = (
                (linha.clinica or '').strip(),
                (linha.enfermaria or '').strip(),
            )
    return locais


def _cabecalho_relatorio(data_ref, ctx, meals, titulo):
    return {
        'titulo': titulo,
        'data': data_ref.isoformat(),
        'data_label': data_ref.strftime('%d/%m/%y'),
        'data_hora_relatorio': fmt_brasilia(now_brasilia(), '%d/%m/%y %H:%M:%S'),
        'imprimir_por': ctx['imprimir_por'],
        'filtros_label': ', '.join(ctx['labels']) if ctx['labels'] else 'TODOS',
        'horarios': meals,
        'horarios_label': ', '.join(MEAL_LABELS.get(m, m) for m in meals),
    }


def totalizacao_substituicao_alimentos(
    data_ref=None,
    imprimir_por='clinica',
    filtros=None,
    horarios=None,
):
    """Conta, por clínica ou enfermaria, só o que entrou e o que saiu na substituição."""
    data_ref = data_ref or date.today()
    meals = _meals_escolhidos(horarios)
    ctx = _resolver_filtro_local(imprimir_por, filtros)
    linhas = [l for l in _linhas_mapa_dia(data_ref) if _linha_no_filtro(l, ctx)]

    blocos = []
    for meal in meals:
        incluidos = _nova_contagem()
        retirados = _nova_contagem()
        trocas = 0
        for linha in linhas:
            if not getattr(linha, MEAL_FLAG_FIELD[meal], False):
                continue
            pares = _pares_da_refeicao(linha, meal)
            if not pares:
                continue
            coluna = _coluna_local(linha.clinica, linha.enfermaria, ctx['imprimir_por'])
            teve = False
            for par in pares:
                add = (par.get('adicionar') or '').strip()
                rem = (par.get('remover') or '').strip()
                if add:
                    _acumular_item(incluidos, add, coluna, 1)
                    teve = True
                if rem:
                    _acumular_item(retirados, rem, coluna, 1)
                    teve = True
            if teve:
                trocas += 1
        blocos.append({
            'meal': meal,
            'meal_label': MEAL_LABELS.get(meal, meal).upper(),
            'trocas': trocas,
            'tabelas': [
                {
                    'titulo': 'Itens incluídos na substituição',
                    **_matriz_de(incluidos),
                },
                {
                    'titulo': 'Itens retirados do cardápio',
                    **_matriz_de(retirados),
                },
            ],
        })

    rel = _cabecalho_relatorio(
        data_ref, ctx, meals, 'TOTALIZAÇÃO DE SUBSTITUIÇÃO DE ALIMENTOS',
    )
    rel['modo'] = 'substituicao'
    rel['blocos'] = blocos
    rel['qtd_trocas'] = sum(b['trocas'] for b in blocos)
    return rel


def totalizacao_consumo_alimentos(
    data_ref=None,
    imprimir_por='clinica',
    filtros=None,
    horarios=None,
):
    """Conta cada alimento que sai para o paciente, já com a substituição aplicada."""
    data_ref = data_ref or date.today()
    meals = _meals_escolhidos(horarios)
    ctx = _resolver_filtro_local(imprimir_por, filtros)
    linhas = [l for l in _linhas_mapa_dia(data_ref) if _linha_no_filtro(l, ctx)]
    locais = _locais_por_paciente(linhas)
    acompanhantes = _acompanhantes_do_dia(data_ref)
    funcionarios = _funcionarios_do_dia(data_ref)

    blocos = []
    for meal in meals:
        bucket = _nova_contagem()
        porcoes = 0
        for linha in linhas:
            if not getattr(linha, MEAL_FLAG_FIELD[meal], False):
                continue
            dieta = (linha.dieta or '').strip()
            pares = _pares_da_refeicao(linha, meal)
            padrao = _pratos_padrao(dieta, linha.dieta_id, meal, data_ref)
            servidos = cardapio_personalizado(padrao, pares)
            if not servidos:
                continue
            coluna = _coluna_local(linha.clinica, linha.enfermaria, ctx['imprimir_por'])
            for prato in servidos:
                _acumular_item(bucket, prato, coluna, 1)
                porcoes += 1

        for a in acompanhantes:
            if not _refeicao_extra_vale(a, meal):
                continue
            no_mapa = a.paciente_id in locais
            clinica, enfermaria = locais.get(a.paciente_id, ('', ''))
            if not clinica and a.paciente is not None:
                clinica = (a.paciente.clinica or '').strip()
            if not no_mapa and not ctx['todos']:
                if ctx['imprimir_por'] == 'enfermaria':
                    continue
                if (clinica or '').strip().upper() not in ctx['nomes_clinica']:
                    continue
            dieta, dieta_id = _dieta_extra(a)
            qtd = max(int(a.quantidade or 1), 1)
            pratos = _pratos_padrao(dieta, dieta_id, meal, data_ref)
            coluna = _coluna_local(
                clinica, enfermaria, ctx['imprimir_por'], fallback='ACOMPANHANTES',
            )
            for prato in pratos:
                _acumular_item(bucket, prato, coluna, qtd)
                porcoes += qtd

        if ctx['todos']:
            for f in funcionarios:
                if not _refeicao_extra_vale(f, meal):
                    continue
                dieta, dieta_id = _dieta_extra(f)
                qtd = max(int(f.quantidade or 1), 1)
                pratos = _pratos_padrao(dieta, dieta_id, meal, data_ref)
                for prato in pratos:
                    _acumular_item(bucket, prato, 'FUNCIONÁRIOS', qtd)
                    porcoes += qtd

        blocos.append({
            'meal': meal,
            'meal_label': MEAL_LABELS.get(meal, meal).upper(),
            'porcoes': porcoes,
            'tabelas': [{
                'titulo': 'Alimentos servidos',
                **_matriz_de(bucket),
            }],
        })

    rel = _cabecalho_relatorio(
        data_ref, ctx, meals, 'TOTALIZAÇÃO DO CONSUMO (COM SUBSTITUIÇÃO)',
    )
    rel['modo'] = 'consumo'
    rel['blocos'] = blocos
    rel['qtd_porcoes'] = sum(b['porcoes'] for b in blocos)
    return rel


def _nomes_filtro_cadastro(modelo, filtros):
    filtros = [str(f).strip() for f in (filtros or []) if str(f).strip()]
    upper = {f.upper() for f in filtros}
    if (not filtros) or ('TODOS' in upper):
        return True, ['TODOS'], set()
    ids = [int(x) for x in filtros if str(x).isdigit()]
    nomes = set()
    labels = []
    if ids:
        for row in _q(modelo).filter(modelo.id.in_(ids)).all():
            if row.nome:
                nomes.add(row.nome.strip().upper())
                labels.append(row.nome)
    for f in filtros:
        if not str(f).isdigit():
            nomes.add(f.upper())
            if f not in labels:
                labels.append(f)
    return False, labels, nomes


def _passa_clinica_enfermaria(clinica, enfermaria, todos_cli, nomes_cli, todos_enf, nomes_enf):
    if not todos_cli and (clinica or '').strip().upper() not in nomes_cli:
        return False
    if not todos_enf and (enfermaria or '').strip().upper() not in nomes_enf:
        return False
    return True


def _itens_servidos(padrao, pares):
    adds = {
        _norm_txt(p.get('adicionar'))
        for p in (pares or [])
        if (p.get('adicionar') or '').strip()
    }
    servidos = cardapio_personalizado(padrao, pares)
    retirados = []
    vistos = set()
    for p in pares or []:
        rem = (p.get('remover') or '').strip()
        chave = _norm_txt(rem)
        if rem and chave not in vistos:
            vistos.add(chave)
            retirados.append(rem.upper())
    return [
        {'nome': prato, 'substituido': _norm_txt(prato) in adds}
        for prato in servidos
    ], retirados


def impressao_cardapio_servido(
    data_ref=None,
    clinicas=None,
    enfermarias=None,
    horarios=None,
):
    """Cardápio que cada paciente recebe, depois da substituição."""
    data_ref = data_ref or date.today()
    meals = _meals_escolhidos(horarios)
    todos_cli, labels_cli, nomes_cli = _nomes_filtro_cadastro(NutClinica, clinicas)
    todos_enf, labels_enf, nomes_enf = _nomes_filtro_cadastro(NutEnfermaria, enfermarias)
    linhas = _linhas_mapa_dia(data_ref)
    locais = _locais_por_paciente(linhas)

    def _entra(clinica, enfermaria):
        return _passa_clinica_enfermaria(
            clinica, enfermaria, todos_cli, nomes_cli, todos_enf, nomes_enf,
        )

    blocos = []
    for meal in meals:
        grupos = {}
        total = 0

        def _grupo(clinica, enfermaria):
            cli = (clinica or '').strip() or 'SEM CLÍNICA'
            enf = (enfermaria or '').strip() or 'SEM ENFERMARIA'
            g = grupos.setdefault(cli.upper(), {'clinica': cli, 'enfermarias': {}})
            return g['enfermarias'].setdefault(enf.upper(), {'enfermaria': enf, 'linhas': []})

        for linha in linhas:
            if not getattr(linha, MEAL_FLAG_FIELD[meal], False):
                continue
            if not _entra(linha.clinica, linha.enfermaria):
                continue
            pares = _pares_da_refeicao(linha, meal)
            padrao = _pratos_padrao(
                (linha.dieta or '').strip(), linha.dieta_id, meal, data_ref,
                incluir_extras=False,
            )
            pratos, retirados = _itens_servidos(padrao, pares)
            _grupo(linha.clinica, linha.enfermaria)['linhas'].append({
                'leito': linha.leito or '',
                'nome': linha.nome or '',
                'dieta': (linha.dieta or '').strip(),
                'tipo': 'Paciente',
                'pratos': pratos,
                'retirados': retirados,
            })
            total += 1

        for a in _acompanhantes_do_dia(data_ref):
            if not _refeicao_extra_vale(a, meal):
                continue
            clinica, enfermaria = locais.get(a.paciente_id, ('', ''))
            if not clinica and a.paciente is not None:
                clinica = (a.paciente.clinica or '').strip()
            if not _entra(clinica, enfermaria):
                continue
            dieta, dieta_id = _dieta_extra(a)
            qtd = max(int(a.quantidade or 1), 1)
            pratos, _retirados = _itens_servidos(
                _pratos_padrao(dieta, dieta_id, meal, data_ref, incluir_extras=False), [],
            )
            nome = (a.nome_acompanhante or '').strip() or 'Acompanhante'
            if qtd > 1:
                nome = f'{nome} (x{qtd})'
            _grupo(clinica or 'ACOMPANHANTES', enfermaria)['linhas'].append({
                'leito': '',
                'nome': nome,
                'dieta': dieta,
                'tipo': 'Acompanhante',
                'pratos': pratos,
                'retirados': [],
            })
            total += 1

        if todos_cli and todos_enf:
            for f in _funcionarios_do_dia(data_ref):
                if not _refeicao_extra_vale(f, meal):
                    continue
                dieta, dieta_id = _dieta_extra(f)
                qtd = max(int(f.quantidade or 1), 1)
                pratos, _retirados = _itens_servidos(
                    _pratos_padrao(dieta, dieta_id, meal, data_ref, incluir_extras=False), [],
                )
                nome = (f.nome or '').strip() or 'Funcionário'
                if qtd > 1:
                    nome = f'{nome} (x{qtd})'
                _grupo('FUNCIONÁRIOS', '')['linhas'].append({
                    'leito': '',
                    'nome': nome,
                    'dieta': dieta,
                    'tipo': 'Funcionário',
                    'pratos': pratos,
                    'retirados': [],
                })
                total += 1

        grupos_out = []
        for g in sorted(grupos.values(), key=lambda x: x['clinica'].upper()):
            enfs = []
            for enf in sorted(g['enfermarias'].values(), key=lambda x: x['enfermaria'].upper()):
                enf['linhas'].sort(key=lambda r: (
                    r['leito'].upper(), r['nome'].upper(),
                ))
                enfs.append(enf)
            grupos_out.append({'clinica': g['clinica'], 'enfermarias': enfs})
        blocos.append({
            'meal': meal,
            'meal_label': MEAL_LABELS.get(meal, meal).upper(),
            'grupos': grupos_out,
            'total': total,
        })

    return {
        'titulo': 'CARDÁPIO SERVIDO',
        'data': data_ref.isoformat(),
        'data_label': data_ref.strftime('%d/%m/%y'),
        'data_hora_relatorio': fmt_brasilia(now_brasilia(), '%d/%m/%y %H:%M:%S'),
        'clinicas_label': ', '.join(labels_cli) if labels_cli else 'TODOS',
        'enfermarias_label': ', '.join(labels_enf) if labels_enf else 'TODOS',
        'horarios': meals,
        'horarios_label': ', '.join(MEAL_LABELS.get(m, m) for m in meals),
        'blocos': blocos,
        'total': sum(b['total'] for b in blocos),
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

# Gabarito oficial Pimaco (cm → mm). 6080/6180: Carta 3×10, 66,7×25,4 mm.
GEOMETRIA_ETIQUETA = {
    '6080': {
        'page': 'letter', 'page_w': 215.9, 'page_h': 279.4,
        'm_top': 12.7, 'm_left': 4.8, 'm_right': 4.8, 'm_bottom': 12.7,
        'label_w': 66.7, 'label_h': 25.4, 'gap_x': 3.1, 'gap_y': 0,
        'pad_t': 3.4, 'pad_x': 3.6, 'pad_b': 1.6,
    },
    '6082': {
        'page': 'letter', 'page_w': 215.9, 'page_h': 279.4,
        'm_top': 21.2, 'm_left': 4.0, 'm_right': 4.0, 'm_bottom': 21.2,
        'label_w': 101.6, 'label_h': 33.9, 'gap_x': 5.2, 'gap_y': 0,
        'pad_t': 3.2, 'pad_x': 3.5, 'pad_b': 1.6,
    },
    'A4350': {
        'page': 'A4', 'page_w': 210.0, 'page_h': 297.0,
        'm_top': 9.0, 'm_left': 4.7, 'm_right': 4.7, 'm_bottom': 9.0,
        'label_w': 99.0, 'label_h': 55.8, 'gap_x': 2.6, 'gap_y': 0,
        'pad_t': 4.0, 'pad_x': 4.0, 'pad_b': 2.0,
    },
    'A4356': {
        'page': 'A4', 'page_w': 210.0, 'page_h': 297.0,
        'm_top': 8.8, 'm_left': 7.2, 'm_right': 7.2, 'm_bottom': 8.8,
        'label_w': 63.5, 'label_h': 25.4, 'gap_x': 2.6, 'gap_y': 0,
        'pad_t': 3.2, 'pad_x': 3.2, 'pad_b': 1.5,
    },
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
            'margem_superior': e.get('margem_superior') or 0,
            'margem_esquerda': e.get('margem_esquerda') or 0,
            'margem_direita': e.get('margem_direita') or 0,
            'margem_inferior': e.get('margem_inferior') or 0,
            'dist_colunas_mm': e.get('dist_colunas_mm') or 0,
            'folha_largura_mm': e.get('folha_largura_mm') or 0,
            'folha_altura_mm': e.get('folha_altura_mm') or 0,
            'tamanho_folha': e.get('tamanho_folha') or '',
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


def _geometria_etiqueta(base_id, extra=None):
    """Medidas oficiais do modelo + overrides do cadastro (mm)."""
    geom = dict(GEOMETRIA_ETIQUETA.get(base_id) or GEOMETRIA_ETIQUETA['6080'])
    extra = extra or {}
    mapa = {
        'm_top': extra.get('margem_superior') or extra.get('m_top'),
        'm_left': extra.get('margem_esquerda') or extra.get('m_left'),
        'm_right': extra.get('margem_direita') or extra.get('m_right'),
        'm_bottom': extra.get('margem_inferior') or extra.get('m_bottom'),
        'label_h': extra.get('altura_etiqueta_mm') or extra.get('label_h'),
        'gap_x': extra.get('dist_colunas_mm') or extra.get('gap_x'),
        'page_w': extra.get('folha_largura_mm') or extra.get('page_w'),
        'page_h': extra.get('folha_altura_mm') or extra.get('page_h'),
    }
    for chave, valor in mapa.items():
        try:
            num = float(valor or 0)
        except (TypeError, ValueError):
            num = 0
        if num > 0:
            geom[chave] = num
    folha = (extra.get('tamanho_folha') or extra.get('page') or geom.get('page') or 'letter').strip().lower()
    if folha in ('a4', 'letter', 'carta'):
        geom['page'] = 'A4' if folha == 'a4' else 'letter'
        if folha == 'a4' and not extra.get('folha_largura_mm'):
            geom['page_w'] = 210.0
            geom['page_h'] = 297.0
    cols = int(extra.get('cols') or extra.get('num_colunas') or 0)
    cadastro_alterou = any(
        extra.get(k)
        for k in ('margem_esquerda', 'folha_largura_mm', 'dist_colunas_mm', 'margem_direita')
    )
    if cadastro_alterou and cols >= 2 and geom.get('page_w'):
        resto = geom['page_w'] - geom['m_left'] - geom['m_right'] - geom['gap_x'] * (cols - 1)
        largura = resto / cols
        if 20 <= largura <= 120:
            geom['label_w'] = round(largura, 2)
    return geom


def _posicoes_etiquetas(geom, cols, rows):
    pitch_x = geom['label_w'] + geom['gap_x']
    pitch_y = geom['label_h'] + geom['gap_y']
    posicoes = []
    for i in range(cols * rows):
        col = i % cols
        row = i // cols
        posicoes.append({
            'top': round(geom['m_top'] + row * pitch_y, 2),
            'left': round(geom['m_left'] + col * pitch_x, 2),
        })
    return posicoes


def _resolver_modelo_etiqueta(modelo_id):
    modelos = list_modelos_etiqueta_impressao()
    mid = (modelo_id or '6080').strip()

    def _pack(m, extra=None):
        fonte = int(m.get('fonte') or 7)
        cols = int(m.get('cols') or 3)
        rows = int(m.get('rows') or 10)
        extra = dict(extra or {})
        extra['cols'] = cols
        geom = _geometria_etiqueta(m.get('base') or m.get('id') or '6080', extra)
        packed = {
            'id': m['id'],
            'nome': m['nome'],
            'cols': cols,
            'rows': rows,
            'fonte': fonte,
            'fonte_obs': max(fonte - 1, 5),
            'por_pagina': cols * rows,
        }
        packed.update(geom)
        packed['posicoes'] = _posicoes_etiquetas(geom, cols, rows)
        return packed

    for m in modelos['preconfigurados']:
        if m['id'] == mid:
            return _pack(m, m)
    for m in modelos['personalizados']:
        if m['id'] == mid:
            base = next((p for p in MODELOS_ETIQUETA_PRE if p['id'] == m.get('base')), MODELOS_ETIQUETA_PRE[0])
            cols = m.get('num_colunas') or base['cols']
            rows = base['rows']
            if cols == 3 and base['id'] == '6080':
                rows = 10
            extra = dict(m)
            extra['id'] = base['id']
            extra['base'] = base['id']
            extra['cols'] = cols
            return _pack({
                'id': m['id'],
                'nome': m['nome'],
                'cols': cols,
                'rows': rows,
                'fonte': int(m.get('fonte') or base['fonte']),
                'base': base['id'],
            }, extra)
    return _pack(MODELOS_ETIQUETA_PRE[0], MODELOS_ETIQUETA_PRE[0])


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


def _fmt_data_hora_etiqueta(row):
    """Última alteração do mapa; se ausente, data de inclusão (dd/mm/yyyy HH:mm).

    Timestamps do mapa são gravados em Brasília (naive), como estoque saídas.
    fmt_brasilia só desloca se o datetime for aware; naive não é reinterpretado
    como UTC (evita double-shift).
    """
    dt = row.data_atualizacao or row.data_inclusao or row.data_criacao
    return fmt_brasilia(dt, '%d/%m/%Y %H:%M')


def gerar_impressao_etiquetas(
    data_ref=None,
    horario='desjejum',
    modo='mapa',
    imprimir_por='clinica',
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
    if imprimir_por == 'grupo_clinica' and (filtro_id or filtro_nome):
        nomes = set(nomes_clinicas_do_grupo(filtro_id, filtro_nome))
        if nomes:
            linhas = [l for l in linhas if (l.clinica or '').strip().upper() in nomes]
        elif filtro_nome:
            linhas = [l for l in linhas if (l.clinica or '').strip().upper() == filtro_nome.upper()]
        elif filtro_id:
            cli = NutClinica.query.get(int(filtro_id))
            if cli:
                filtro_nome = cli.nome or ''
                linhas = [l for l in linhas if (l.clinica or '').strip().upper() == filtro_nome.upper()]
    elif imprimir_por == 'clinica':
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
            'data_hora': _fmt_data_hora_etiqueta(l),
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


def _fmt_data_br(valor):
    if not valor:
        return ''
    if isinstance(valor, datetime):
        valor = valor.date() if hasattr(valor, 'date') else valor
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    s = str(valor).strip()
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return f'{s[8:10]}/{s[5:7]}/{s[0:4]}'
    return s


def _marca_x(valor):
    return 'X' if valor else ''


def _marca_isolamento(row):
    """Coluna I do mapa impresso: isolamento indicado em diagnóstico/obs."""
    texto = ' '.join([
        row.diagnostico or '',
        row.observacoes or '',
        row.obs_etiqueta or '',
    ]).upper()
    return any(chave in texto for chave in ('ISOLAMENTO', 'ISOLADO', 'ISOL.'))


def gerar_impressao_mapa(data_de=None, data_ate=None, clinica_nome=None):
    """Relatório do mapa de produção: linhas do período com totais de dietas e refeições."""
    data_de = data_de or date.today()
    data_ate = data_ate or data_de
    if data_ate < data_de:
        data_de, data_ate = data_ate, data_de

    q = apply_cliente_filter(
        NutMapaRefeicao.query.filter(
            NutMapaRefeicao.data_refeicao >= data_de,
            NutMapaRefeicao.data_refeicao <= data_ate,
        ),
        NutMapaRefeicao,
    )
    nome_cli = (clinica_nome or '').strip()
    if nome_cli and nome_cli != '__todas__':
        q = q.filter(db.func.upper(NutMapaRefeicao.clinica) == nome_cli.upper())
    rows = q.order_by(
        NutMapaRefeicao.data_refeicao,
        NutMapaRefeicao.clinica,
        NutMapaRefeicao.enfermaria,
        NutMapaRefeicao.leito,
        NutMapaRefeicao.nome,
    ).all()

    linhas = []
    totais_refeicao = {
        'desjejum': 0, 'colacao': 0, 'almoco': 0,
        'merenda': 0, 'jantar': 0, 'ceia': 0,
    }
    dietas = {}
    for row in rows:
        if not (row.nome or '').strip() and not (row.leito or '').strip():
            continue
        fl = {
            'desjejum': bool(row.fl_desjejum),
            'colacao': bool(row.fl_colacao),
            'almoco': bool(row.fl_almoco),
            'merenda': bool(row.fl_merenda),
            'jantar': bool(row.fl_jantar),
            'ceia': bool(row.fl_ceia),
        }
        for chave, on in fl.items():
            if on:
                totais_refeicao[chave] += 1
        dieta = (row.dieta or '').strip() or '(sem dieta)'
        dietas[dieta] = dietas.get(dieta, 0) + 1
        linhas.append({
            'data': row.data_refeicao.isoformat() if row.data_refeicao else '',
            'data_label': _fmt_data_br(row.data_refeicao),
            'clinica': row.clinica or '',
            'enfermaria': row.enfermaria or '',
            'admissao': _fmt_data_br(row.adm),
            'leito': row.leito or '',
            'prontuario': row.prontuario or '',
            'nome': row.nome or '',
            'idade': row.idade if row.idade is not None else '',
            'diagnostico': row.diagnostico or '',
            'dieta': dieta if dieta != '(sem dieta)' else '',
            'isolamento': _marca_x(_marca_isolamento(row)),
            'obs': row.observacoes or '',
            'd': _marca_x(fl['desjejum']),
            'c': _marca_x(fl['colacao']),
            'a': _marca_x(fl['almoco']),
            'm': _marca_x(fl['merenda']),
            'j': _marca_x(fl['jantar']),
            'ceia': _marca_x(fl['ceia']),
            'saida': _fmt_data_br(row.data_saida),
        })

    soma_dietas = [
        {'nome': nome, 'qtd': qtd}
        for nome, qtd in sorted(dietas.items(), key=lambda item: item[0].upper())
    ]
    return {
        'data_de': data_de.isoformat(),
        'data_ate': data_ate.isoformat(),
        'data_de_label': _fmt_data_br(data_de),
        'data_ate_label': _fmt_data_br(data_ate),
        'periodo_unico': data_de == data_ate,
        'clinica': nome_cli if nome_cli and nome_cli != '__todas__' else '',
        'clinica_label': nome_cli if nome_cli and nome_cli != '__todas__' else 'Todas',
        'data_hora_relatorio': fmt_brasilia(now_brasilia(), '%d/%m/%Y %H:%M'),
        'linhas': linhas,
        'total_dietas': len(linhas),
        'soma_dietas': soma_dietas,
        'totais_refeicao': totais_refeicao,
    }


def gerar_impressao_mapa_distribuicao(
    data_de=None,
    data_ate=None,
    clinica_nomes=None,
    tipo_refeicao='almoco',
):
    """Lista de distribuição: pacientes da refeição, agrupados por clínica."""
    data_de = data_de or date.today()
    data_ate = data_ate or data_de
    if data_ate < data_de:
        data_de, data_ate = data_ate, data_de

    meal = tipo_refeicao_para_meal(tipo_refeicao) or 'almoco'
    flag = MEAL_FLAG_FIELD.get(meal) or 'fl_almoco'
    meal_label = MEAL_LABELS.get(meal, meal).upper()

    nomes_cli = []
    if isinstance(clinica_nomes, str):
        clinica_nomes = [clinica_nomes]
    for nome in clinica_nomes or []:
        n = (nome or '').strip()
        if n and n != '__todas__':
            nomes_cli.append(n)

    q = apply_cliente_filter(
        NutMapaRefeicao.query.filter(
            NutMapaRefeicao.data_refeicao >= data_de,
            NutMapaRefeicao.data_refeicao <= data_ate,
            getattr(NutMapaRefeicao, flag).is_(True),
        ),
        NutMapaRefeicao,
    )
    if nomes_cli:
        nomes_up = [n.upper() for n in nomes_cli]
        q = q.filter(db.func.upper(NutMapaRefeicao.clinica).in_(nomes_up))
    rows = q.order_by(
        NutMapaRefeicao.data_refeicao,
        NutMapaRefeicao.clinica,
        NutMapaRefeicao.leito,
        NutMapaRefeicao.nome,
    ).all()

    grupos = []
    atual = None
    for row in rows:
        nome = (row.nome or '').strip()
        if not nome and not (row.leito or '').strip():
            continue
        data_iso = row.data_refeicao.isoformat() if row.data_refeicao else ''
        clinica = (row.clinica or '').strip() or 'Sem clínica'
        chave = data_iso + '|' + clinica
        if atual is None or atual['chave'] != chave:
            atual = {
                'chave': chave,
                'data': data_iso,
                'data_label': _fmt_data_br(row.data_refeicao),
                'clinica': clinica,
                'linhas': [],
            }
            grupos.append(atual)
        atual['linhas'].append({
            'nome': nome,
            'prontuario': row.prontuario or '',
            'leito': row.leito or '',
            'dieta': (row.dieta or '').strip(),
            'obs': row.observacoes or '',
        })

    for g in grupos:
        g['total'] = len(g['linhas'])

    return {
        'titulo': 'MAPA DISTRIBUIÇÃO',
        'data_de': data_de.isoformat(),
        'data_ate': data_ate.isoformat(),
        'data_de_label': _fmt_data_br(data_de),
        'data_ate_label': _fmt_data_br(data_ate),
        'periodo_unico': data_de == data_ate,
        'clinicas': nomes_cli,
        'clinica_label': ', '.join(nomes_cli) if nomes_cli else 'Todas',
        'tipo': meal,
        'tipo_label': meal_label,
        'data_hora_relatorio': fmt_brasilia(now_brasilia(), '%d/%m/%Y %H:%M'),
        'grupos': grupos,
        'total': sum(g['total'] for g in grupos),
    }
