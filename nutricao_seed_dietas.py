"""
Catálogo de dietas + preços por tipo de refeição (foto Cadastro de Preços).

Ordem das tuplas de preço: DESJEJUM, COLAÇÃO, ALMOÇO, MERENDA, JANTAR, CEIA.
Valores da foto (formato BR 4,54 → float 4.54). Empresa/Paciente/Acompanhante
recebem o mesmo valor na carga do seed.
"""

# Padrões de preço da foto
P_ORAL = (4.54, 3.63, 11.82, 3.63, 11.82, 3.63)
P_FORMULA = (6.36, 6.36, 6.36, 6.36, 6.36, 6.36)
P_SUP_200 = (0.0, 8.18, 0.0, 8.18, 0.0, 8.18)
P_MOD_PROT = (5.45, 5.45, 5.45, 5.45, 5.45, 5.45)
P_MOD_CARB = (4.54, 4.54, 4.54, 4.54, 4.54, 4.54)
P_MOD_LIP = (6.82, 6.82, 6.82, 6.82, 6.82, 6.82)
P_ACOMP = (6.36, 5.45, 18.18, 5.45, 18.18, 5.45)
P_KIT_LANCHE = (0.0, 7.27, 0.0, 7.27, 0.0, 0.0)
P_KIT_ALTA = (0.0, 0.0, 0.0, 0.0, 0.0, 13.64)


def _alm(v):
    return (0.0, 0.0, float(v), 0.0, 0.0, 0.0)


# Catálogo da foto — (nome, categoria, grupo, ativo, precos_6)
# categoria: basica | enteral | formula | suplemento | outro
DIETAS_CATALOGO_FOTO = [
    # ---- Dietas orais / clínicas ----
    ('DIETA LIVRE', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA BRANDA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA PASTOSA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA LEVE', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA LIQUIDA COMPLETA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA LIQUIDA SEMIRESTRITA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA LIQUIDA RESTRITA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA HIPOSSODICA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ DIABETICOS', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA HIPOCALORICA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA HIPERPROTEICA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA HIPOLIPIDICA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA HIPERCALORICA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ RENAL (CRONICO)', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ RENAL (AGUDO)', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ HEPATOPATA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ CARDIOPATA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA SEM RESIDUOS', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA LAXANTE', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA CONSTIPANTE', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ GASTROPLASTIA FASE I', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ GASTROPLASTIA FASE II', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ GASTROPLASTIA FASE III', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA PRE-OPERATORIO', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA POS-OPERATORIO', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA SEM GLUTEN', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA SEM LACTOSE', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ PACIENTE COM DISFAGIA', 'basica', 'DIETAS ORAIS', True, P_ORAL),
    ('DIETA P/ NEUTROPENICO', 'basica', 'DIETAS ORAIS', True, P_ORAL),

    # ---- Enterais (preço no Almoço) ----
    ('ENTERAL SISTEMA ABERTO 1000ML', 'enteral', 'NUTRICAO ENTERAL', True, _alm(45.45)),
    ('ENTERAL SISTEMA ABERTO 1500ML', 'enteral', 'NUTRICAO ENTERAL', True, _alm(68.18)),
    ('ENTERAL SISTEMA FECHADO 1000ML', 'enteral', 'NUTRICAO ENTERAL', True, _alm(90.91)),
    ('ENTERAL SISTEMA FECHADO 1500ML', 'enteral', 'NUTRICAO ENTERAL', True, _alm(136.36)),

    # ---- Pediátricas orais ----
    ('DIETA LIVRE PEDIATRICA', 'basica', 'DIETAS PEDIATRICAS', True, P_ORAL),
    ('DIETA BRANDA PEDIATRICA', 'basica', 'DIETAS PEDIATRICAS', True, P_ORAL),
    ('DIETA PASTOSA PEDIATRICA', 'basica', 'DIETAS PEDIATRICAS', True, P_ORAL),
    ('DIETA LEVE PEDIATRICA', 'basica', 'DIETAS PEDIATRICAS', True, P_ORAL),
    ('DIETA LIQUIDA PEDIATRICA', 'basica', 'DIETAS PEDIATRICAS', True, P_ORAL),
    ('DIETA P/ DIABETICOS PEDIATRICA', 'basica', 'DIETAS PEDIATRICAS', True, P_ORAL),

    # ---- Fórmulas infantis ----
    ('FORMULA INFANTIL', 'formula', 'FORMULAS INFANTIS', True, P_FORMULA),
    ('FORMULA INFANTIL HIPOALERGENICA', 'formula', 'FORMULAS INFANTIS', True, P_FORMULA),
    ('FORMULA INFANTIL A BASE DE SOJA', 'formula', 'FORMULAS INFANTIS', True, P_FORMULA),
    ('FORMULA INFANTIL ANTI-REFLUXO', 'formula', 'FORMULAS INFANTIS', True, P_FORMULA),
    ('FORMULA INFANTIL LACTARIO', 'formula', 'FORMULAS INFANTIS', True, P_FORMULA),

    # ---- Suplementos / módulos ----
    ('SUPLEMENTO 200ML', 'suplemento', 'SUPLEMENTOS E MODULOS', True, P_SUP_200),
    ('MODULO PROTEINA', 'suplemento', 'SUPLEMENTOS E MODULOS', True, P_MOD_PROT),
    ('MODULO CARBOIDRATO', 'suplemento', 'SUPLEMENTOS E MODULOS', True, P_MOD_CARB),
    ('MODULO LIPIDEO', 'suplemento', 'SUPLEMENTOS E MODULOS', True, P_MOD_LIP),
    ('ESPESSANTE', 'suplemento', 'SUPLEMENTOS E MODULOS', True, P_SUP_200),

    # ---- Acompanhante / kits ----
    ('ACOMPANHANTE', 'outro', 'ACOMPANHANTE E KITS', True, P_ACOMP),
    ('KIT LANCHE', 'outro', 'ACOMPANHANTE E KITS', True, P_KIT_LANCHE),
    ('KIT ALTA', 'outro', 'ACOMPANHANTE E KITS', True, P_KIT_ALTA),
]

# Aliases curtos do catálogo antigo → nomes da foto (migração idempotente)
DIETAS_ALIAS_PARA_FOTO = {
    'LIVRE': 'DIETA LIVRE',
    'BRANDA': 'DIETA BRANDA',
    'LEVE': 'DIETA LEVE',
    'PASTOSA': 'DIETA PASTOSA',
    'PASTOSA LIQUIDIFICADA': 'DIETA PASTOSA',
    'LIQUIDA COMPLETA': 'DIETA LIQUIDA COMPLETA',
    'SEMI-LIQUIDA': 'DIETA LIQUIDA SEMIRESTRITA',
    'LIQUIDA RESTRITA': 'DIETA LIQUIDA RESTRITA',
    'DIABETICA': 'DIETA P/ DIABETICOS',
    'HIPOSSODICA': 'DIETA HIPOSSODICA',
    'HIPOGORDUROSA': 'DIETA HIPOLIPIDICA',
    'SEM RESIDUOS': 'DIETA SEM RESIDUOS',
    'SEM LACTOSE': 'DIETA SEM LACTOSE',
    'SEM GLUTEN': 'DIETA SEM GLUTEN',
    'NEFROPATA': 'DIETA P/ RENAL (CRONICO)',
    'HEPATOPATA': 'DIETA P/ HEPATOPATA',
}

try:
    from nutricao_seed_lactario import DIETAS_CATALOGO_LACTARIO, DIETAS_LACTARIO_NOMES
except ImportError:  # pragma: no cover
    DIETAS_CATALOGO_LACTARIO = []
    DIETAS_LACTARIO_NOMES = set()

# Matriz principal de preços: foto legada + catálogo LACTÁRIO (OCR)
DIETAS_CATALOGO_PRECOS = list(DIETAS_CATALOGO_FOTO) + list(DIETAS_CATALOGO_LACTARIO)

# Compat: lista (nome, categoria, ativo) usada em imports antigos
DIETAS_PRECOS_SEED = [
    (nome, cat, ativo) for nome, cat, _grp, ativo, _p in DIETAS_CATALOGO_PRECOS
]

# Dietas do mapa operacional (legado) — nome, categoria, ativo
DIETAS_FOTO_SEED = [
    ('BRANDA COM SAL', 'basica', True),
    ('BRANDA CONST COM SAL', 'basica', True),
    ('BRANDA CONST SEM SAL', 'basica', True),
    ('BRANDA DB CONST', 'basica', True),
    ('BRANDA DB CONST SEM SAL', 'basica', True),
    ('BRANDA DB LAX', 'basica', True),
    ('BRANDA DB LAX SEM SAL', 'basica', True),
    ('BRANDA HIOL COM SAL', 'basica', True),
    ('BRANDA HIOL SEM SAL', 'basica', True),
    ('BRANDA LAX COM SAL', 'basica', True),
    ('BRANDA LAX SEM SAL', 'basica', True),
    ('BRANDA SEM SAL', 'basica', True),
    ('LIQUIDA COM SAL', 'basica', True),
    ('LIQUIDA CONST COM SAL', 'basica', True),
    ('LIQUIDA CONST SEM SAL', 'basica', True),
    ('LIQUIDA ESPESSADA', 'basica', True),
    ('LIQUIDA ESPESSADA DB', 'basica', True),
    ('LIQUIDA RESTRITA SEM SAL', 'basica', True),
    ('LIQUIDA SEM SAL', 'basica', True),
    ('PASTOSA COM SAL', 'basica', True),
    ('PASTOSA DB CONST COM SAL', 'basica', True),
    ('PASTOSA DB CONST SEM SAL', 'basica', True),
    ('PASTOSA DB LAX COM SAL', 'basica', True),
    ('PASTOSA DB LAX SEM SAL', 'basica', True),
    ('PASTOSA HIOL COM SAL', 'basica', False),
    ('PASTOSA HIOL SEM SAL', 'basica', False),
    ('PASTOSA SEM SAL', 'basica', True),
    ('SELETIVA', 'basica', True),
]

# Complementares legados (enterais / fórmulas / suplementos nominais)
DIETAS_EXTRA_SEED = [
    ('NORMOCALORICA E NORMOPROTEICA - NUTRI ENTERAL 1L', 'enteral', True),
    ('NORMOCALORICA E HIPERPROTEICA - NUTRI ENTERAL 1L', 'enteral', True),
    ('HIPERCALORICA 1.5 E HIPERPROTEICA - NUTRI ENTERAL 1L', 'enteral', True),
    ('FORMULA INFANTIL HIPOALERGENICA 1:25 - NAN HA', 'formula', True),
    ('FORMULA INFANTIL A BASE DE SOJA 1:30 - NAN SOY', 'formula', True),
    ('FORTIDRINK BAUNILHA 200 ML', 'suplemento', True),
]

# Seed unificado (nome, categoria, ativo) — mapa operacional + extras
# (catálogo da foto é seedado à parte com grupo + preços)
DIETAS_SEED = DIETAS_FOTO_SEED + DIETAS_EXTRA_SEED

TIPOS_PRECO_ORDEM = ('DESJEJUM', 'COLAÇÃO', 'ALMOÇO', 'MERENDA', 'JANTAR', 'CEIA')


def precos_dict_da_tupla(precos_6):
    """Converte tupla de 6 floats em dict nome_tipo → valor."""
    vals = list(precos_6) + [0.0] * 6
    return {t: float(vals[i] or 0) for i, t in enumerate(TIPOS_PRECO_ORDEM)}


# Mapa nome → preços por tipo (para upsert forçado do seed)
DIETAS_PRECOS_POR_NOME = {
    nome.strip().upper(): precos_dict_da_tupla(precos)
    for nome, _cat, _grp, _ativo, precos in DIETAS_CATALOGO_PRECOS
}

# Grupos associados a cada coluna (Funcionário / Paciente / Acompanhante)
# Chave interna permanece 'empresa'; valor gravado como FUNCIONARIO (legado EMPRESA ainda é aceito).
GRUPO_POR_PAYER = {
    'empresa': 'FUNCIONARIO',
    'paciente': 'LACTÁRIO',
    'acompanhante': 'ACOMPANHANTE',
}
