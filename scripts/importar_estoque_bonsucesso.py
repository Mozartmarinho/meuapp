#!/usr/bin/env python3
"""Importa o estoque legado do Hospital Federal de Bonsucesso.

Lê o pacote estoque.zip (exportação SCN) e grava no cliente Bonsucesso:

  ESTOQUE_GRUPO_PROD   → nut_grupos_produto
  ESTOQUE_DESCRI_PROD  → nut_produtos
  ESTOQUE_VALOR        → quantidade, preço médio e último preço

Estoque 1 vira MATRIZ. Estoque 2 vira LACTÁRIO (U.M.A.).
Produtos de cardápio já cadastrados no mesmo código não são reescritos.
"""
from __future__ import annotations

import io
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import openpyxl
import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db_config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER  # noqa: E402

ARQUIVO = Path('/home/administrador/Transferências/estoque.zip')
CLIENTE_NOME = 'Hospital Federal de Bonsucesso'

# NUMERO_ESTOQUE do SCN → nome no sistema
ESTOQUES = {
    1: 'MATRIZ',
    2: 'LACTÁRIO',
}

# NUMERO_UNIDADE do SCN, conferido com a tela de produtos do manual
# (KG no hortifruti, L no vinagre, LT na lata, ML no açafrão, UN no abacaxi, NC na tapioca).
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

UNIDADES_NOVAS = {
    'FR': 'FRASCO',
    'BB': 'BOMBONA',
    'BD': 'BALDE',
    'CX': 'CAIXA',
    'SC': 'SACO',
    'PT': 'POTE',
    'PC': 'PEÇA',
}

GRUPOS_FORMULA = {'ENTERAL', 'DIETAS', 'SUPLEMENTOS', 'LEITES', 'MÓDULOS'}

# Grupos usados pelo cardápio. Não mover um produto que já esteja neles.
GRUPOS_CARDAPIO = {
    'PRATO BASE', 'ACOMPANHAMENTO', 'GUARNIÇÃO', 'FRUTA', 'PRATO',
    'PROTEÍNA OPCIONAL', 'SOBREMESA', 'SALADA', 'SUCO', 'VITAMINA', 'BEBIDAS',
}


def conectar():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=int(MYSQL_PORT),
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4',
        autocommit=False,
    )


def norm(valor):
    return ' '.join(str(valor or '').upper().split())


def flag(valor):
    return str(valor or '').strip().upper() == 'T'


def numero(valor):
    if valor in (None, ''):
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def ler_planilha(z, nome):
    wb = openpyxl.load_workbook(io.BytesIO(z.read(nome)), read_only=True, data_only=True)
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


def escolher(linhas):
    """Uma linha por código: ativa e não excluída, com grupo e unidade reais."""
    def chave(p):
        viva = flag(p.get('ATIVO')) and not flag(p.get('EXCLUIDO'))
        grupo_ok = p.get('NUMERO_GRUPO') not in (None, 1000)
        tem_un = p.get('NUMERO_UNIDADE') not in (None, 1000)
        return (viva, grupo_ok, tem_un, int(p.get('NUMERO_PRODUTO') or 0))

    return max(linhas, key=chave)


def unidade_de(numero_unidade):
    if numero_unidade in (None, ''):
        return 'NC'
    try:
        codigo = int(numero_unidade)
    except (TypeError, ValueError):
        return 'NC'
    return UNIDADES.get(codigo, 'NC')


def cliente_id(cur):
    cur.execute(
        "SELECT id FROM clientes WHERE UPPER(nome) = UPPER(%s) LIMIT 1",
        (CLIENTE_NOME,),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f'Cliente não encontrado: {CLIENTE_NOME}')
    return row[0]


def garantir_estoques(cur, cid):
    ids = {}
    for numero, nome in ESTOQUES.items():
        cur.execute(
            "SELECT id FROM nut_estoques WHERE cliente_id = %s AND UPPER(nome) = UPPER(%s)",
            (cid, nome),
        )
        row = cur.fetchone()
        if row:
            ids[numero] = row[0]
            continue
        cur.execute(
            "INSERT INTO nut_estoques (cliente_id, nome, ativo, data_criacao) VALUES (%s, %s, 1, %s)",
            (cid, nome, datetime.utcnow()),
        )
        ids[numero] = cur.lastrowid
    return ids


def garantir_grupos(cur, cid, grupos):
    ids = {}
    for g in grupos:
        nome = norm(g.get('CODIGO_GRUPO'))
        if not nome:
            nome = norm(g.get('NOME_GRUPO')) or 'NI'
        if len(nome) > 120:
            nome = nome[:120]
        cur.execute(
            "SELECT id FROM nut_grupos_produto WHERE cliente_id = %s AND UPPER(nome) = UPPER(%s)",
            (cid, nome),
        )
        row = cur.fetchone()
        if row:
            ids[g.get('NUMERO_GRUPO')] = row[0]
            continue
        cur.execute(
            """
            INSERT INTO nut_grupos_produto (cliente_id, nome, ativo, data_criacao)
            VALUES (%s, %s, 1, %s)
            """,
            (cid, nome, datetime.utcnow()),
        )
        ids[g.get('NUMERO_GRUPO')] = cur.lastrowid
    if 1000 not in ids:
        cur.execute(
            "SELECT id FROM nut_grupos_produto WHERE cliente_id = %s AND UPPER(nome) = 'NI'",
            (cid,),
        )
        row = cur.fetchone()
        if row:
            ids[1000] = row[0]
    return ids


def garantir_unidades(cur, cid):
    for codigo, descricao in UNIDADES_NOVAS.items():
        cur.execute(
            "SELECT id, descricao FROM nut_unidades WHERE cliente_id = %s AND codigo = %s",
            (cid, codigo),
        )
        row = cur.fetchone()
        if row:
            if not row[1]:
                cur.execute(
                    "UPDATE nut_unidades SET descricao = %s WHERE id = %s",
                    (descricao, row[0]),
                )
            continue
        cur.execute(
            """
            INSERT INTO nut_unidades (
                cliente_id, codigo, descricao, valor_conversao,
                flag_nutrientes, flag_uma, flag_estoque, flag_pratos, ativo, data_criacao
            ) VALUES (%s, %s, %s, 0, 1, 1, 1, 1, 1, %s)
            """,
            (cid, codigo, descricao, datetime.utcnow()),
        )


def codigo_livre(ocupados, codigo):
    if codigo not in ocupados:
        return codigo
    n = 2
    while True:
        alt = f'{codigo}-{n}'
        if len(alt) > 40:
            alt = f'{codigo[:36]}-{n}'
        if alt not in ocupados:
            return alt
        n += 1


def apontar_uma(cur, cid, lactario_id):
    cur.execute("SELECT id FROM nut_config_uma WHERE cliente_id = %s", (cid,))
    if not cur.fetchone():
        return
    cur.execute(
        """
        UPDATE nut_config_uma
           SET estoque_enteral_id = %s,
               estoque_suplemento_id = %s,
               estoque_formula_id = %s,
               estoque_lve_id = %s,
               estoque_modulo_id = %s
         WHERE cliente_id = %s
        """,
        (lactario_id, lactario_id, lactario_id, lactario_id, lactario_id, cid),
    )


def importar(cur, cid):
    with zipfile.ZipFile(ARQUIVO) as z:
        grupos = ler_planilha(z, 'ESTOQUE_GRUPO_PROD.xlsx')
        produtos = ler_planilha(z, 'ESTOQUE_DESCRI_PROD.xlsx')
        valores = ler_planilha(z, 'ESTOQUE_VALOR.xlsx')

    estoques = garantir_estoques(cur, cid)
    grupos_id = garantir_grupos(cur, cid, grupos)
    garantir_unidades(cur, cid)

    cur.execute(
        """
        SELECT p.id, p.estoque_id, p.codigo, p.descricao, g.nome
          FROM nut_produtos p
          JOIN nut_grupos_produto g ON g.id = p.grupo_id
         WHERE p.cliente_id = %s
        """,
        (cid,),
    )
    existentes = {}
    ocupados = {}
    por_desc = {}
    for pid, estoque_id, codigo, descricao, grupo in cur.fetchall():
        codigo_n = norm(codigo)
        desc_n = norm(descricao)
        grupo_n = norm(grupo)
        existentes[(estoque_id, codigo_n)] = (pid, desc_n, grupo_n)
        ocupados.setdefault(estoque_id, set()).add(codigo_n)
        por_desc[(estoque_id, desc_n, grupo_n)] = pid

    precos = {}
    for v in valores:
        precos[(v.get('NUMERO_ESTOQUE'), v.get('NUMERO_PRODUTO'))] = v

    por_codigo = {}
    for p in produtos:
        est = p.get('NUMERO_ESTOQUE')
        if est not in ESTOQUES:
            continue
        codigo = norm(p.get('CODIGO_PRODUTO'))
        if not codigo:
            continue
        por_codigo.setdefault((est, codigo), []).append(p)

    agora = datetime.utcnow()
    inseridos = 0
    atualizados = 0
    sufixados = 0
    pulados_excluidos = 0
    por_estoque = {1: 0, 2: 0}

    for (est, codigo), linhas in por_codigo.items():
        escolhido = escolher(linhas)
        if not (flag(escolhido.get('ATIVO')) and not flag(escolhido.get('EXCLUIDO'))):
            pulados_excluidos += 1
            continue

        descricao = norm(escolhido.get('DESCRI_PRODUTO')) or codigo
        if len(descricao) > 200:
            descricao = descricao[:200]
        if len(codigo) > 40:
            codigo = codigo[:40]

        grupo_num = escolhido.get('NUMERO_GRUPO')
        grupo_id = grupos_id.get(grupo_num) or grupos_id.get(1000)
        if not grupo_id:
            continue
        cur.execute("SELECT nome FROM nut_grupos_produto WHERE id = %s", (grupo_id,))
        grupo_nome = norm(cur.fetchone()[0])

        valor = precos.get((est, escolhido.get('NUMERO_PRODUTO')), {})
        unidade = unidade_de(escolhido.get('NUMERO_UNIDADE'))
        un_liq = unidade_de(escolhido.get('NUMERO_UNID_LIQ'))
        formula = 1 if grupo_nome in GRUPOS_FORMULA else 0
        estoque_id = estoques[est]
        dados = (
            numero(valor.get('QUANTIDADE')),
            unidade,
            numero(valor.get('PRECO_MEDIO')),
            numero(valor.get('PRECO_ULT_NOTA')),
            numero(escolhido.get('QUANTIDADE_MIN')),
            numero(escolhido.get('QUANTIDADE_MAX')),
            numero(escolhido.get('QUANTIDADE_LIQUIDA')),
            un_liq,
            1 if flag(escolhido.get('FATOR_CONV')) else 0,
            formula,
        )

        atual = existentes.get((estoque_id, codigo))
        mesmo = atual[0] if atual and atual[1] == descricao and atual[2] == grupo_nome else None
        if not mesmo:
            mesmo = por_desc.get((estoque_id, descricao, grupo_nome))
        if mesmo:
            cur.execute(
                """
                UPDATE nut_produtos
                   SET quantidade = %s, unidade = %s, preco_medio = %s, ult_preco = %s,
                       quant_min = %s, quant_max = %s, quant_liq = %s, un_liq = %s,
                       fc = %s, formula = %s, ativo = 1, data_alteracao = %s
                 WHERE id = %s
                """,
                (*dados, agora, mesmo),
            )
            atualizados += 1
            por_estoque[est] += 1
            continue

        codigo_final = codigo
        if (estoque_id, codigo) in existentes or codigo in ocupados.get(estoque_id, ()):
            codigo_final = codigo_livre(ocupados.setdefault(estoque_id, set()), codigo)
            sufixados += 1
        ocupados.setdefault(estoque_id, set()).add(codigo_final)
        existentes[(estoque_id, codigo_final)] = (None, descricao, grupo_nome)

        cur.execute(
            """
            INSERT INTO nut_produtos (
                cliente_id, estoque_id, grupo_id, codigo, descricao,
                quantidade, unidade, preco_medio, ult_preco,
                quant_min, quant_max, quant_liq, un_liq,
                fc, formula, ativo, data_criacao, data_alteracao
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, 1, %s, %s
            )
            """,
            (cid, estoque_id, grupo_id, codigo_final, descricao, *dados, agora, agora),
        )
        inseridos += 1
        por_estoque[est] += 1

    apontar_uma(cur, cid, estoques[2])
    return {
        'inseridos': inseridos,
        'atualizados': atualizados,
        'codigo_ajustado': sufixados,
        'fora_do_cadastro_ativo': pulados_excluidos,
        'matriz': por_estoque[1],
        'lactario': por_estoque[2],
    }


def main():
    if not ARQUIVO.exists():
        raise SystemExit(f'Arquivo ausente: {ARQUIVO}')
    conn = conectar()
    try:
        cur = conn.cursor()
        cid = cliente_id(cur)
        resumo = importar(cur, cid)
        conn.commit()
        cur.execute(
            """
            SELECT e.nome, COUNT(*)
              FROM nut_produtos p
              JOIN nut_estoques e ON e.id = p.estoque_id
             WHERE p.cliente_id = %s
             GROUP BY e.nome
             ORDER BY e.nome
            """,
            (cid,),
        )
        print('Importação', resumo, flush=True)
        print('Produtos por estoque:', cur.fetchall(), flush=True)
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
