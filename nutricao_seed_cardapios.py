"""Seed do cadastro de cardápios (exemplos da tela legado)."""

CARDAPIO_OPCOES = {
    'grupos': ['PRINCIPAL', 'ALTERNATIVO', 'FESTIVO'],
    'dias_semana': ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'],
    'acompanhamentos': [
        'ARROZ S/ SAL', 'ARROZ C/ SAL', 'ARROZ INTEGRAL', 'PURÊ DE BATATA', 'MACARRÃO'
    ],
    'pratos_base': [
        'ISCA DE CARNE AO MOLHO FERRUGEM', 'BIFE ACEBOLADO', 'FRANGO GRELHADO', 'PEIXE ASSADO'
    ],
    'proteicos_opcionais': [
        'ISCA DE FRANGO S/ SAL', 'OVO MEXIDO', 'QUEIJO BRANCO', 'ATUM'
    ],
    'guarnicoes': [
        'BATATA REFOG. S/ SAL', 'LEGUMES REFOGADOS', 'FAROFÁ', 'FEIJÃO'
    ],
    'sobremesas': [
        'MAÇÃ COZ À FRANC.', 'BANANA', 'CREME DE BANANA', 'GELATINA', 'PUDIM'
    ],
    'bebidas': [
        'MATE GELADO', 'CAFÉ C/ LEITE S/ AÇÚC.', 'VIT. MAÇÃ C/ L. INTEG.', 'SUCO DE LARANJA', 'ÁGUA'
    ],
    'entradas_sopas': [
        'CHUCHU REFOG. S/ SAL', 'SOPA DE LEGUMES', 'SALADA CRUA', 'CALDO VERDE'
    ],
    'outros': [
        'ADOÇANTE IND.', 'AÇÚCAR IND.', 'SAL', 'AZEITE'
    ],
    'pratos_pequenos': [
        'PÃO CARECA SAL', 'MANTEIGA IND.', 'QUEIJO MINAS', 'AÇÚCAR IND.',
        'PÃO FRANCÊS', 'BISCOITO ÁGUA E SAL', 'IOGURTE'
    ],
    'principais_liquidos': [
        'GELÉIA DE MOCOTÓ', 'CALDO DE CARNE', 'SOPA CREME', 'MINGAU'
    ],
    'organizar_opcoes': [
        'Dia;Dieta;Horário',
        'Dia;Horário;Dieta',
        'Dieta;Dia;Horário',
        'Dieta;Horário;Dia',
        'Horário;Dia;Dieta',
        'Horário;Dieta;Dia',
    ],
}

# Exemplos da foto
CARDAPIOS_SEED = [
    {
        'tipo': 'grandes',
        'grupo_cardapio': 'PRINCIPAL',
        'dia_mes': 1,
        'dia_semana': 'Domingo',
        'dieta': 'BRANDA CONSTIPANTE HDDS',
        'hr_almoco': True,
        'hr_jantar': True,
        'itens': {
            'entrada_tipo': 'Salada',
            'proteico_tipo': 'Aves',
            'acompanhamento': 'ARROZ S/ SAL',
            'prato_base': 'ISCA DE CARNE AO MOLHO FERRUGEM',
            'proteico_opcional': 'ISCA DE FRANGO S/ SAL',
            'guarnicao': 'BATATA REFOG. S/ SAL',
            'diversos_salada': '',
            'sobremesa': 'MAÇÃ COZ À FRANC.',
            'bebida': 'MATE GELADO',
            'molhos': '',
            'entrada_sopa': 'CHUCHU REFOG. S/ SAL',
            'outros': 'ADOÇANTE IND.',
        },
        'vet': 0,
        'custo': 0,
        'organizar_por': 'Dia;Dieta;Horário',
        'usuario_alteracao': 'silvana',
    },
    {
        'tipo': 'pequenas',
        'grupo_cardapio': 'PRINCIPAL',
        'dia_mes': 1,
        'dia_semana': 'Domingo',
        'dieta': 'BRANDA',
        'hr_desjejum': True,
        'itens': {
            'bebida': 'CAFÉ C/ LEITE S/ AÇÚC.',
            'prato1': 'PÃO CARECA SAL',
            'prato2': 'MANTEIGA IND.',
            'prato3': 'QUEIJO MINAS',
            'prato4': 'AÇÚCAR IND.',
            'prato5': '',
            'prato6': '',
            'prato7': '',
            'sobremesa': 'BANANA',
        },
        'vet': 0,
        'custo': 0,
        'organizar_por': 'Dia;Dieta;Horário',
        'usuario_alteracao': 'silvana',
    },
    {
        'tipo': 'liquidas',
        'grupo_cardapio': 'PRINCIPAL',
        'dia_mes': 1,
        'dia_semana': 'Domingo',
        'dieta': 'DIETA LÍQUIDA COMPLETA',
        'hr_desjejum': True,
        'itens': {
            'principal': 'GELÉIA DE MOCOTÓ',
            'bebida': 'VIT. MAÇÃ C/ L. INTEG.',
            'sobremesa': 'CREME DE BANANA',
            'gelado': 'MATE GELADO',
            'outros': 'AÇÚCAR IND.',
            'conv_bebida_coluna': '',
            'conv_bebida_quant': '',
            'conv_gelado_coluna': '',
            'conv_gelado_quant': '',
        },
        'vet': 0,
        'custo': 0,
        'organizar_por': 'Dia;Dieta;Horário',
        'usuario_alteracao': 'silvana',
    },
]
