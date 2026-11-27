#!/usr/bin/env python3
"""Lança o lactário legado no Hospital Federal de Bonsucesso.

Lê alimentoscomplementares.zip e substitui, só nesse cliente, o cadastro de
fórmula infantil, enteral, suplemento e LVE. Módulos entram como suplemento.
"""
from __future__ import annotations

import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARQUIVO = Path('/home/administrador/Transferências/alimentoscomplementares.zip')
ESTOQUE = Path('/home/administrador/Transferências/estoque.zip')

UNIDADES = {
    1: 'BB',
    2: 'BD',
    3: 'CX',
    4: 'FR',
    6: 'KG',
    7: 'L',
    8: 'LT',
    9: 'ML',
    10: 'PCT',
    12: 'UN',
    13: 'SC',
    16: 'PT',
    24: 'CX',
    26: 'PC',
    27: 'PT',
    28: 'UN',
    1000: 'NC',
}

# Códigos de COLUNAFATURAMENTO / CODCOLUNA do SCN, lidos pelo agrupamento dos nomes.
COLUNAS = {
    35: 'PREMATUROS E RECEM - NATOS DE BAIXO PESO',
    36: 'LACTENTES 0 A 6 MESES',
    37: 'LACTENTES DE 6 A 12 MESES',
    139: 'LACTENTES ANTI-REGURGITAÇÃO',
    140: 'ISENTAS DE LACTOSE',
    141: 'HIPOALERGÊNICAS',
    142: 'ESPECIAIS À BASE DE PROTEÍNA DE SOJA',
    143: 'ESPECIAIS HIDROLISADAS',
    144: 'ELEMENTARES',
    145: 'ERROS INATOS DO METABOLISMO',
    146: 'FÓRMULAS LÁCTEAS',
    183: 'CRIANÇA A PARTIR DE 12 MESES',
    184: 'SUPLEMENTO NUTRICIONAL',
}

GRUPOS_MODULO = {
    1: 'MÓDULO DE CARBOIDRATO',
    2: 'MÓDULO DE FIBRA',
    3: 'MÓDULO DE PROTEÍNA',
    4: 'MÓDULO DE AMINOÁCIDO',
    5: 'MÓDULO DE LIPÍDIO',
    6: 'MÓDULO PROBIÓTICO',
    7: 'MÓDULO SIMBIÓTICO',
    8: 'MODULEN IBD',
}


def norm(valor):
    return ' '.join(str(valor or '').upper().split())


def flag(valor):
    return str(valor or '').strip().upper() == 'T'


def num(valor):
    if valor in (None, ''):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def inteiro(valor):
    if valor in (None, ''):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def ler_planilha(origem, nome):
    if isinstance(origem, zipfile.ZipFile):
        bruto = origem.read(nome)
    else:
        bruto = Path(origem).read_bytes()
    wb = openpyxl.load_workbook(io.BytesIO(bruto), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    linhas = ws.iter_rows(values_only=True)
    header = list(next(linhas))
    saida = []
    for row in linhas:
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue
        saida.append(dict(zip(header, row)))
    wb.close()
    return saida


def unidade_de(codigo):
    if isinstance(codigo, str) and codigo.strip() and not codigo.strip().isdigit():
        return norm(codigo)[:20]
    return UNIDADES.get(inteiro(codigo), '')


def quant_padrao(qtd, un):
    valor = num(qtd)
    if valor is None:
        return ''
    texto = str(int(valor)) if valor == int(valor) else str(valor).replace('.', ',')
    unidade = norm(un)
    return (texto + (' ' + unidade if unidade else '')).strip()[:40]


def composicao_de(valor):
    texto = ' '.join(str(valor or '').split())
    if not texto:
        return ''
    if texto.upper() in (
        'COMP. NUTRICIONAL:',
        'COMP. NUTRICIONAL: VIDE O RÓTULO DO PRODUTO',
    ):
        return ''
    return texto[:4000]


def coluna_de(codigo):
    return COLUNAS.get(inteiro(codigo), '')


def cobranca_de(codigo):
    codigo = inteiro(codigo)
    if codigo == 1:
        return 'espelho_1'
    if codigo == 2:
        return 'espelho_2'
    return 'nao'


def componentes_de(linhas, campo):
    saida = []
    for row in linhas:
        saida.append({
            'componente': norm(row.get(campo)),
            'formula': norm(row.get('FORMULA')).replace(' ', ''),
            'und': flag(row.get('CALCUNID')),
            'vol': flag(row.get('CALCVOLUME')),
            'codigo': norm(row.get('PRODESTOQUE')),
            'un': norm(row.get('UNPRODESTOQUE')),
        })
    return saida


def agrupar(linhas):
    grupos = defaultdict(list)
    for row in linhas:
        grupos[inteiro(row.get('CODIGO'))].append(row)
    return grupos


def catalogo_produtos():
    """NUMERO_PRODUTO do SCN → descrição. Lactário ganha de outro estoque."""
    if not ESTOQUE.exists():
        return {}
    with zipfile.ZipFile(ESTOQUE) as pacote:
        linhas = ler_planilha(pacote, 'ESTOQUE_DESCRI_PROD.xlsx')
    escolhido = {}
    for row in linhas:
        numero = inteiro(row.get('NUMERO_PRODUTO'))
        nome = norm(row.get('DESCRI_PRODUTO'))
        if not numero or not nome:
            continue
        estoque = inteiro(row.get('NUMERO_ESTOQUE')) or 0
        atual = escolhido.get(numero)
        if atual is None or (estoque == 2 and atual[0] != 2):
            escolhido[numero] = (estoque, nome)
    return {numero: nome for numero, (_estoque, nome) in escolhido.items()}


def montar(pacote, produtos):
    leites2 = agrupar(ler_planilha(pacote, 'LACTARIO_LEITES2.xlsx'))
    dietas2 = agrupar(ler_planilha(pacote, 'LACTARIO_DIETAS2.xlsx'))
    lve2 = agrupar(ler_planilha(pacote, 'LACTARIO_LVE2.xlsx'))
    grupos_sup = {
        inteiro(row.get('AUTOMATICO')): norm(row.get('NOMEGRUPO'))
        for row in ler_planilha(pacote, 'LACTARIO_GRUPOS_SUPLEMENTOS.xlsx')
    }
    grupos_lve = {
        inteiro(row.get('AUTOMATICO')): norm(row.get('NOMEGRUPO'))
        for row in ler_planilha(pacote, 'LACTARIO_GRUPOS_LVE.xlsx')
    }

    itens = []

    for row in ler_planilha(pacote, 'LACTARIO_LEITES.xlsx'):
        nome = norm(row.get('NOMELEITE'))
        if nome in ('', '.', '..', '...'):
            continue
        codigo = inteiro(row.get('CODIGO'))
        itens.append({
            'tipo': 'formula',
            'nome': nome,
            'sistema_fechado': flag(row.get('SISTEMAFECHADO')),
            'manipulado': False,
            'unidade': unidade_de(row.get('CODUNIDADE')),
            'produto_principal': produtos.get(inteiro(row.get('CODPRODUTO')), ''),
            'diluicao': norm(row.get('DILUICAO')),
            'coluna_faturamento': coluna_de(row.get('COLUNAFATURAMENTO')),
            'grupo': '',
            'quant_padrao': '',
            'produto_disponivel': flag(row.get('ATIVO')),
            'ativo': True,
            'cobranca': '',
            'calorias': num(row.get('CALORIAS')),
            'ptn': num(row.get('PTN')),
            'hc': num(row.get('HC')),
            'lip': num(row.get('LIP')),
            'fibras': num(row.get('FIBRAS')),
            'composicao': composicao_de(row.get('COMPOSICAONUTRICIONAL')),
            'componentes': componentes_de(leites2.get(codigo, []), 'PARAMETROLEITE'),
            'legado': codigo,
        })

    for row in ler_planilha(pacote, 'LACTARIO_DIETAS.xlsx'):
        nome = norm(row.get('NOMEDIETA'))
        if nome in ('', '.', '..', '...'):
            continue
        codigo = inteiro(row.get('CODIGO'))
        itens.append({
            'tipo': 'enteral',
            'nome': nome,
            'sistema_fechado': flag(row.get('SISTEMAFECHADO')),
            'manipulado': False,
            'unidade': unidade_de(row.get('CODUNIDADE')),
            'produto_principal': produtos.get(inteiro(row.get('CODPRODUTO')), ''),
            'diluicao': '',
            'coluna_faturamento': coluna_de(row.get('COLUNAFATURAMENTO')),
            'grupo': '',
            'quant_padrao': '',
            'produto_disponivel': flag(row.get('ATIVO')),
            'ativo': True,
            'cobranca': '',
            'calorias': num(row.get('CALORIAS')),
            'ptn': num(row.get('PTN')),
            'hc': num(row.get('HC')),
            'lip': num(row.get('LIP')),
            'fibras': num(row.get('FIBRAS')),
            'composicao': composicao_de(row.get('COMPOSICAONUTRICIONAL')),
            'componentes': componentes_de(dietas2.get(codigo, []), 'PARAMETRODIETA'),
            'legado': codigo,
        })

    for row in ler_planilha(pacote, 'LACTARIO_SUPLEMENTOS.xlsx'):
        nome = norm(row.get('NOMESUPLEMENTO'))
        if nome in ('', '.', '..', '...'):
            continue
        itens.append({
            'tipo': 'suplemento',
            'nome': nome,
            'sistema_fechado': False,
            'manipulado': flag(row.get('SUPLEMENTOMANIPULADO')),
            'unidade': unidade_de(row.get('CODUNIDADE')),
            'produto_principal': '',
            'diluicao': '',
            'coluna_faturamento': coluna_de(row.get('COLUNAFATURAMENTO')),
            'grupo': grupos_sup.get(inteiro(row.get('CODGRUPO')), ''),
            'quant_padrao': quant_padrao(row.get('QUANTLIQ'), row.get('UNQUANTLIQ')),
            'produto_disponivel': flag(row.get('ATIVO')),
            'ativo': True,
            'cobranca': '',
            'calorias': num(row.get('CALORIAS')),
            'ptn': num(row.get('PTN')),
            'hc': num(row.get('HC')),
            'lip': num(row.get('LIP')),
            'fibras': num(row.get('FIBRAS')),
            'composicao': composicao_de(row.get('COMPOSICAONUTRICIONAL')),
            'componentes': [],
            'legado': inteiro(row.get('CODIGO')),
        })

    for row in ler_planilha(pacote, 'LACTARIO_MODULOS.xlsx'):
        nome = norm(row.get('NOME'))
        if not nome or nome == 'SIMBIOFLORA':
            continue
        unidade = unidade_de(row.get('UNIDADE'))
        quant = ''
        if unidade.isdigit():
            quant = unidade
            unidade = ''
        itens.append({
            'tipo': 'suplemento',
            'nome': nome,
            'sistema_fechado': False,
            'manipulado': False,
            'unidade': unidade,
            'produto_principal': produtos.get(inteiro(row.get('CODPRODUTO')), ''),
            'diluicao': '',
            'coluna_faturamento': '',
            'grupo': GRUPOS_MODULO.get(inteiro(row.get('CODGRUPO')), ''),
            'quant_padrao': quant,
            'produto_disponivel': True,
            'ativo': True,
            'cobranca': '',
            'calorias': None,
            'ptn': num(row.get('PTN')),
            'hc': num(row.get('HC')),
            'lip': num(row.get('LIP')),
            'fibras': num(row.get('FIBRAS')),
            'composicao': composicao_de(row.get('COMPOSICAONUTRICIONAL')),
            'componentes': [],
            'legado': inteiro(row.get('AUTOMATICO')),
        })

    for row in ler_planilha(pacote, 'LACTARIO_LVE.xlsx'):
        nome = norm(row.get('NOMELVE'))
        if nome in ('', '.', '..', '...'):
            continue
        codigo = inteiro(row.get('CODIGO'))
        itens.append({
            'tipo': 'lve',
            'nome': nome,
            'sistema_fechado': False,
            'manipulado': False,
            'unidade': unidade_de(row.get('CODUNIDADE')),
            'produto_principal': '',
            'diluicao': '',
            'coluna_faturamento': coluna_de(row.get('CODCOLUNA')) or 'FÓRMULAS LÁCTEAS',
            'grupo': grupos_lve.get(inteiro(row.get('CODGRUPO')), ''),
            'quant_padrao': '',
            'produto_disponivel': True,
            'ativo': flag(row.get('ATIVO')),
            'cobranca': cobranca_de(row.get('CODRELATORIO')),
            'calorias': num(row.get('CALORIAS')),
            'ptn': num(row.get('PTN')),
            'hc': num(row.get('HC')),
            'lip': num(row.get('LIP')),
            'fibras': num(row.get('FIBRAS')),
            'composicao': composicao_de(row.get('COMPOSICAONUTRICIONAL')),
            'componentes': componentes_de(lve2.get(codigo, []), 'PARAMETROLVE'),
            'legado': codigo,
        })
    return itens


def chave(item):
    sistema = ''
    if item['tipo'] == 'enteral':
        sistema = 'fechado' if item['sistema_fechado'] else 'aberto'
    elif item['tipo'] == 'formula' and item['sistema_fechado']:
        sistema = 'fechado'
    return (
        item['tipo'],
        sistema,
        'dieta' if item['tipo'] == 'enteral' else '',
        bool(item['manipulado']),
        item['nome'],
        item['produto_principal'] if item['tipo'] in ('formula', 'enteral') else '',
        item['unidade'],
    )


def preferir(atual, novo):
    if atual is None:
        return novo
    if novo['produto_disponivel'] and not atual['produto_disponivel']:
        return novo
    if novo['ativo'] and not atual['ativo']:
        return novo
    return atual


def sem_repetidos(itens):
    escolhidos = {}
    repetidos = 0
    for item in itens:
        chave_item = chave(item)
        if chave_item in escolhidos:
            repetidos += 1
        escolhidos[chave_item] = preferir(escolhidos.get(chave_item), item)
    return list(escolhidos.values()), repetidos


def retirar_catalogo_antigo(cid):
    from models import db
    from models_nutricao import (
        NutCardapio, NutDieta, NutMapaRefeicao, NutPrecoDietaTipo,
        NutRefeicaoAcompanhante, NutRefeicaoFuncionario, NutTotalizacaoDireta,
        NutUmaItem,
    )

    tipos = ('formula', 'enteral', 'suplemento', 'lve', 'modulo')
    dietas = NutDieta.query.filter(
        NutDieta.cliente_id == cid,
        NutDieta.categoria.in_(('formula', 'enteral', 'suplemento', 'lve')),
    ).all()
    ids = [dieta.id for dieta in dietas]
    if ids:
        NutPrecoDietaTipo.query.filter(
            NutPrecoDietaTipo.dieta_id.in_(ids)
        ).delete(synchronize_session=False)
        for model in (
            NutCardapio, NutMapaRefeicao, NutRefeicaoAcompanhante,
            NutRefeicaoFuncionario, NutTotalizacaoDireta,
        ):
            model.query.filter(model.dieta_id.in_(ids)).update(
                {model.dieta_id: None}, synchronize_session=False
            )
        NutDieta.query.filter(NutDieta.id.in_(ids)).delete(synchronize_session=False)
    apagados = NutUmaItem.query.filter(
        NutUmaItem.cliente_id == cid,
        NutUmaItem.tipo.in_(tipos),
    ).delete(synchronize_session=False)
    db.session.flush()
    return apagados, len(ids)


def gravar(cid, itens):
    from nutricao_service import salvar_cadastro_uma, salvar_opcao_uma

    grupos = sorted({
        item['grupo'] for item in itens
        if item['tipo'] == 'suplemento' and item['grupo']
    })
    colunas = sorted({
        item['coluna_faturamento'] for item in itens
        if item['tipo'] in ('enteral', 'suplemento') and item['coluna_faturamento']
    })
    for nome in grupos:
        salvar_opcao_uma(cid, 'suplemento', 'grupo', nome)
    for nome in colunas:
        salvar_opcao_uma(cid, 'enteral', 'coluna', nome)
        salvar_opcao_uma(cid, 'suplemento', 'coluna', nome)

    resumo = defaultdict(int)
    for item in itens:
        payload = dict(item)
        payload.pop('legado', None)
        salvar_cadastro_uma(cid, payload)
        resumo[item['tipo']] += 1
    return dict(resumo)


def main():
    from app import create_app
    from models import db
    from nutricao_service import _garantir_unico_uma_item, seed_nutricao
    from nutricao_tenant import ensure_cliente_hfb

    if not ARQUIVO.exists():
        raise SystemExit(f'Arquivo não encontrado: {ARQUIVO}')

    with zipfile.ZipFile(ARQUIVO) as pacote:
        produtos = catalogo_produtos()
        itens, repetidos = sem_repetidos(montar(pacote, produtos))

    app = create_app()
    with app.app_context():
        seed_nutricao()
        _garantir_unico_uma_item()
        from sqlalchemy import inspect
        insp = inspect(db.engine)
        unicos = list(insp.get_unique_constraints('nut_uma_itens') or [])
        unicos += [
            ix for ix in (insp.get_indexes('nut_uma_itens') or [])
            if ix.get('unique')
        ]
        atual = next((u for u in unicos if u.get('name') == 'uq_nut_uma_item'), None)
        cols = list((atual or {}).get('column_names') or [])
        if 'produto_principal' not in cols:
            raise SystemExit('O cadastro ainda não aceita o mesmo nome com produtos diferentes.')
        cid = ensure_cliente_hfb().id
        apagados, dietas = retirar_catalogo_antigo(cid)
        resumo = gravar(cid, itens)
        db.session.commit()
        print('Cliente', cid, flush=True)
        print('Itens antigos retirados', apagados, 'dietas retiradas', dietas, flush=True)
        print('Repetidos no arquivo (ficou o ativo)', repetidos, flush=True)
        print('Gravados', resumo, 'total', sum(resumo.values()), flush=True)
        print('Produtos do estoque reconhecidos', len(produtos), flush=True)


if __name__ == '__main__':
    main()
