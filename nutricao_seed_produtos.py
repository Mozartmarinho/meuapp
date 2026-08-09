"""Seed do cadastro de produtos (estoque / grupos / unidades)."""

ESTOQUES_SEED = [
    'MATRIZ',
]

UNIDADES_SEED = [
    ('UN', 'Unidade'),
    ('L', 'Litro'),
    ('LT', 'Litro'),
    ('ML', 'Mililitro'),
    ('KG', 'Quilograma'),
    ('BD', 'Balde'),
    ('NC', 'Não classificado'),
]

GRUPOS_PRODUTO_SEED = [
    'BEBIDAS',
    'CEREAIS',
    'CARNES',
    'LATICÍNIOS',
    'HORTIFRUTI',
    'DESCARTÁVEIS',
]

# estoque, grupo, codigo, descricao, qtd, un, preco_med, ult_preco, min, max, qtd_liq, un_liq, fc
PRODUTOS_SEED = [
    ('MATRIZ', 'BEBIDAS', 'ACHOC0', 'ACHOCOLATADO 200 ML', 0, 'UN', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'AGU1500', 'AGUA 1500', 0, 'L', 0.01, 0.01, 0, 0, 0, 'NC', True),
    ('MATRIZ', 'BEBIDAS', 'AGU200', 'AGUA MINERAL 200 ML', 0, 'UN', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'AGU510', 'AGUA MINERAL 510 ML', 0, 'L', 0.01, 0.01, 0, 0, 0, 'NC', True),
    ('MATRIZ', 'BEBIDAS', 'COCA2L', 'COCA COLA 2L', 0, 'L', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'COLORA', 'CLOROFILA', 0, 'KG', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'GATORA', 'GATORADE', 0, 'UN', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'GUAR2L', 'GUARANA DIET 2L', 0, 'L', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'LEIUAT', 'LEITE UAT ITAMBYN', 0, 'L', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'MANGO', 'SUCO DE MORANGO 200 ML TP', 0, 'UN', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'MATCHA', 'MATE 200', 0, 'ML', 0.01, 0.01, 0, 0, 0, 'NC', False),
    ('MATRIZ', 'BEBIDAS', 'SUCLAR', 'SUCO DE LARANJA 200 ML', 0, 'UN', 0.01, 0.01, 0, 0, 0, 'NC', False),
]
