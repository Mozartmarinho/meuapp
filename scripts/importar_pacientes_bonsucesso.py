#!/usr/bin/env python3
"""Importa o cadastro legado de pacientes do Hospital Federal de Bonsucesso.

Remove do cliente Bonsucesso os pacientes que são cópia do Hospital Federal
de Ipanema (mesmo nome, sem código legado) e carrega:

  PACIENTES.xlsx
  PACIENTES_AVALIACAO_NUTRI.xlsx
  PACIENTES_DADOS_LAB.xlsx
  PACIENTES_AVAL_NUTRI_VO.xlsx
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path

import openpyxl
import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db_config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER  # noqa: E402

PASTA = Path('/home/administrador/Transferências')
ARQ_PAC = PASTA / 'PACIENTES.xlsx'
ARQ_AVAL = PASTA / 'PACIENTES_AVALIACAO_NUTRI.xlsx'
ARQ_LAB = PASTA / 'PACIENTES_DADOS_LAB.xlsx'
ARQ_VO = PASTA / 'PACIENTES_AVAL_NUTRI_VO.xlsx'

REF_LABEL = {
    'D': 'Desjejum',
    'C': 'Colação',
    'A': 'Almoço',
    'M': 'Merenda',
    'J': 'Jantar',
    'CE': 'Ceia',
}
LAB_MAP = {
    'GLICOSE': 'glicose',
    'UREIA': 'ureia',
    'CREATININA': 'creatinina',
    'PTN_TOTAIS': 'ptn_totais',
    'ALBUMINA': 'albumina',
    'ACIDO_URICO': 'acido_urico',
    'COLESTEROL': 'colesterol',
    'TG': 'tg',
    'HTO': 'hto',
    'HB': 'hb',
    'LEUCOCITOS': 'leucocitos',
    'LINFOCITOS': 'linfocitos',
    'NA': 'na',
    'K': 'k',
    'CA': 'ca',
    'P': 'p',
    'MG': 'mg',
    'ACIDO_FOLICO': 'acido_folico',
    'B12': 'b12',
    'AMILASE': 'amilase',
    'LIPASE': 'lipase',
    'BILIRRUBINA_TOTAL': 'bilirrubina',
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


def clip(valor, tamanho):
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    return texto[:tamanho]


def como_data(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None


def como_hora(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, datetime):
        return valor.strftime('%H:%M:%S')
    if isinstance(valor, time):
        return valor.strftime('%H:%M:%S')
    return clip(valor, 20)


def como_int(valor):
    if valor is None or valor == '':
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def como_float(valor):
    if valor is None or valor == '':
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def sexo_de(valor):
    texto = ('' if valor is None else str(valor)).strip().upper()
    if texto in ('M', 'MASC', 'MASCULINO', 'H', 'HOMEM'):
        return 'M'
    if texto in ('F', 'FEM', 'FEMININO', 'MULHER'):
        return 'F'
    if texto in ('O', 'OUTRO', 'OUTROS'):
        return 'O'
    return None


def estatura_cm(valor):
    n = como_float(valor)
    if n is None or n <= 0:
        return None
    if n <= 3:
        n = n * 100.0
    return round(n, 1)


def flag_t(valor):
    return 1 if str(valor or '').strip().upper() == 'T' else 0


def intestino_de(valor):
    texto = ('' if valor is None else str(valor)).strip().lower()
    if texto in ('t', 's', 'sim', '1'):
        return 'sim'
    if texto in ('f', 'n', 'nao', 'não', '0'):
        return 'nao'
    return None


def asg_de(valor):
    texto = ('' if valor is None else str(valor)).strip().upper()[:1]
    return texto if texto in ('A', 'B', 'C') else None


def linhas(caminho, aba=None):
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    ws = wb[aba] if aba else wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    header = next(it)
    idx = {nome: i for i, nome in enumerate(header) if nome}
    for row in it:
        yield idx, row
    wb.close()


def cel(row, idx, nome):
    i = idx.get(nome)
    if i is None or i >= len(row):
        return None
    return row[i]


def cliente_id(cur, nome):
    cur.execute(
        "SELECT id FROM clientes WHERE LOWER(nome) = LOWER(%s) LIMIT 1",
        (nome,),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f'Cliente não encontrado: {nome}')
    return row[0]


def preparar_tabela(cur):
    cur.execute("SHOW COLUMNS FROM nut_pacientes LIKE 'codigo_legado'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE nut_pacientes ADD COLUMN codigo_legado INT NULL")
    cur.execute(
        "SHOW INDEX FROM nut_pacientes WHERE Key_name = 'ix_nut_pacientes_codigo_legado'"
    )
    if not cur.fetchone():
        cur.execute(
            "CREATE INDEX ix_nut_pacientes_codigo_legado "
            "ON nut_pacientes (cliente_id, codigo_legado)"
        )


def mapa_enfermarias(cur, cid):
    cur.execute(
        """
        SELECT e.id, e.nome, c.nome
        FROM nut_enfermarias e
        LEFT JOIN nut_clinica_enfermarias ce ON ce.enfermaria_id = e.id
        LEFT JOIN nut_clinicas c ON c.id = ce.clinica_id AND c.cliente_id = e.cliente_id
        WHERE e.cliente_id = %s
        """,
        (cid,),
    )
    por_id = {}
    for eid, enome, cnome in cur.fetchall():
        item = por_id.setdefault(eid, {'nome': enome or '', 'clinicas': []})
        if cnome and cnome not in item['clinicas']:
            item['clinicas'].append(cnome)
    return por_id


def retirar_copia_ipanema(cur, bonsucesso, ipanema):
    """Pacientes de Bonsucesso sem código legado e com o mesmo nome de Ipanema."""
    cur.execute("DROP TEMPORARY TABLE IF EXISTS tmp_pac_copia_ipanema")
    cur.execute("CREATE TEMPORARY TABLE tmp_pac_copia_ipanema (id INT PRIMARY KEY)")
    cur.execute(
        """
        INSERT INTO tmp_pac_copia_ipanema (id)
        SELECT DISTINCT p.id
        FROM nut_pacientes p
        JOIN nut_pacientes i ON i.nome = p.nome AND i.cliente_id = %s
        WHERE p.cliente_id = %s AND p.codigo_legado IS NULL
        """,
        (ipanema, bonsucesso),
    )
    cur.execute(
        """
        UPDATE nut_mapa_refeicoes m
        JOIN tmp_pac_copia_ipanema t ON t.id = m.paciente_id
        SET m.paciente_id = NULL
        """
    )
    mapas = cur.rowcount
    cur.execute(
        """
        DELETE p FROM nut_pacientes p
        JOIN tmp_pac_copia_ipanema t ON t.id = p.id
        """
    )
    apagados = cur.rowcount
    cur.execute("DROP TEMPORARY TABLE IF EXISTS tmp_pac_copia_ipanema")
    return mapas, apagados


def ja_importados(cur, cid):
    cur.execute(
        "SELECT codigo_legado FROM nut_pacientes "
        "WHERE cliente_id = %s AND codigo_legado IS NOT NULL",
        (cid,),
    )
    return {row[0] for row in cur.fetchall()}


def importar_pacientes(cur, cid, enfermarias, existentes):
    sql = """
        INSERT INTO nut_pacientes (
            cliente_id, nome, sexo, nascimento, prontuario, clinica, enfermaria,
            leito, dieta, diagnostico, observacoes, admissao, data_saida, hora_saida,
            ativo, excluido, data_criacao, codigo_legado
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
    """
    lote = []
    lidos = sem_nome = sem_codigo = dup = sem_enf = 0
    vistos = set(existentes)
    for idx, row in linhas(ARQ_PAC):
        lidos += 1
        nome = clip(cel(row, idx, 'NOME'), 150)
        codigo = como_int(cel(row, idx, 'CODIGOPACIENTE'))
        if not nome:
            sem_nome += 1
            continue
        if codigo is None:
            sem_codigo += 1
            continue
        if codigo in vistos:
            dup += 1
            continue
        vistos.add(codigo)
        enf_id = como_int(cel(row, idx, 'CODENFERMARIA'))
        info = enfermarias.get(enf_id) if enf_id else None
        if enf_id and not info:
            sem_enf += 1
        enfermaria = clip(info['nome'], 120) if info else None
        clinica = None
        if info and len(info['clinicas']) == 1:
            clinica = clip(info['clinicas'][0], 120)
        elif info and info['clinicas']:
            clinica = clip(info['clinicas'][0], 120)
        criado = cel(row, idx, 'ULT_ATUALIZACAO')
        if not isinstance(criado, datetime):
            criado = datetime.utcnow()
        lote.append((
            cid,
            nome,
            sexo_de(cel(row, idx, 'SEXO')),
            como_data(cel(row, idx, 'DATA_NASCIMENTO')),
            clip(cel(row, idx, 'PRONTUARIO'), 40) if not isinstance(cel(row, idx, 'PRONTUARIO'), (int, float))
            else clip(str(int(cel(row, idx, 'PRONTUARIO'))), 40),
            clinica,
            enfermaria,
            clip(cel(row, idx, 'LEITO'), 40),
            None,
            clip(cel(row, idx, 'DIAGNOSTICO'), 65000),
            clip(cel(row, idx, 'OBSERVACOES'), 65000),
            como_data(cel(row, idx, 'DATAENTRADA')),
            como_data(cel(row, idx, 'DATAHORASAIDA')),
            como_hora(cel(row, idx, 'HORASAIDA')),
            flag_t(cel(row, idx, 'ATIVO')),
            flag_t(cel(row, idx, 'EXCLUIDO')),
            criado,
            codigo,
        ))
        if len(lote) >= 2000:
            cur.executemany(sql, lote)
            cur.connection.commit()
            print(f'  pacientes gravados {len(vistos) - len(existentes)}', flush=True)
            lote.clear()
    if lote:
        cur.executemany(sql, lote)
        cur.connection.commit()
    return {
        'lidos': lidos,
        'gravados': len(vistos) - len(existentes),
        'sem_nome': sem_nome,
        'sem_codigo': sem_codigo,
        'duplicados': dup,
        'enfermaria_sem_cadastro': sem_enf,
    }


def ids_por_codigo(cur, cid):
    cur.execute(
        "SELECT codigo_legado, id FROM nut_pacientes "
        "WHERE cliente_id = %s AND codigo_legado IS NOT NULL",
        (cid,),
    )
    return {codigo: pid for codigo, pid in cur.fetchall()}


def importar_avaliacoes(cur, cid, ids):
    cur.execute(
        "SELECT COUNT(*) FROM nut_avaliacoes_nutricionais WHERE cliente_id = %s",
        (cid,),
    )
    if cur.fetchone()[0]:
        return {'avaliacoes': 0, 'pulado': 'já importadas'}
    sql = """
        INSERT INTO nut_avaliacoes_nutricionais (
            cliente_id, paciente_id, data_avaliacao, peso_atual, estatura_cm,
            peso_habitual, peso_calculado, fator_atividade, fator_injuria, fator_termico,
            asg, freq_cardiaca, freq_respiratoria, pressao_arterial, funcao_intestinal,
            prega_biceps, prega_triceps, prega_subescapular, prega_suprailiaca,
            circ_braco, circ_abdomen, circ_panturrilha, hgt, insulina,
            intercorrencias, observacoes, data_criacao
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s
        )
    """
    lote = []
    pulados = 0
    ultimos = {}
    for idx, row in linhas(ARQ_AVAL):
        codigo = como_int(cel(row, idx, 'CODIGOPACIENTE'))
        pid = ids.get(codigo)
        quando = como_data(cel(row, idx, 'DATA_AVALIACAO'))
        if not pid or not quando:
            pulados += 1
            continue
        peso = como_float(cel(row, idx, 'PESO_ATUAL'))
        altura = estatura_cm(cel(row, idx, 'ESTATURA'))
        pmax = cel(row, idx, 'PRESSAO_MAX')
        pmin = cel(row, idx, 'PRESSAO_MIN')
        pressao = None
        if pmax not in (None, '') or pmin not in (None, ''):
            pressao = clip(f'{pmax or ""}/{pmin or ""}'.strip('/'), 20)
        anterior = ultimos.get(pid)
        if anterior is None or quando >= anterior[0]:
            ultimos[pid] = (quando, peso, altura)
        lote.append((
            cid, pid, quando,
            peso if peso and peso > 0 else None,
            altura,
            como_float(cel(row, idx, 'PESO_HABITUAL')),
            como_float(cel(row, idx, 'PESO_CALCULO')),
            como_float(cel(row, idx, 'FTATIVIDADE')) or 1.2,
            como_float(cel(row, idx, 'FTINJURIA')) or 1.0,
            como_float(cel(row, idx, 'FTTERMICO')) or 1.0,
            asg_de(cel(row, idx, 'ASG')),
            clip(cel(row, idx, 'FREQ_CARD'), 20),
            clip(cel(row, idx, 'FREQ_RESP'), 20),
            pressao,
            intestino_de(cel(row, idx, 'FI')),
            como_float(cel(row, idx, 'BICEPS')),
            como_float(cel(row, idx, 'TRICEPS')),
            como_float(cel(row, idx, 'SUB_ESCAPULAR')),
            como_float(cel(row, idx, 'SUPRA_ILIACA')),
            como_float(cel(row, idx, 'CIR_BRACO')),
            como_float(cel(row, idx, 'CIR_ABDOMEM')),
            como_float(cel(row, idx, 'CIR_PANTURRILHA')),
            clip(cel(row, idx, 'HGT'), 20),
            clip(cel(row, idx, 'INSULINA'), 20),
            clip(cel(row, idx, 'INTERCORRENCIAS'), 65000),
            clip(cel(row, idx, 'OBS'), 65000),
            datetime.utcnow(),
        ))
    if lote:
        cur.executemany(sql, lote)
    for pid, (_quando, peso, altura) in ultimos.items():
        if peso or altura:
            cur.execute(
                "UPDATE nut_pacientes SET peso_kg = COALESCE(%s, peso_kg), "
                "altura_cm = COALESCE(%s, altura_cm) WHERE id = %s",
                (peso if peso and peso > 0 else None, altura, pid),
            )
    cur.connection.commit()
    return {'avaliacoes': len(lote), 'sem_paciente': pulados, 'antropometria': len(ultimos)}


def importar_laboratorios(cur, cid, ids):
    cur.execute(
        "SELECT COUNT(*) FROM nut_avaliacoes_nutricionais "
        "WHERE cliente_id = %s AND laboratoriais IS NOT NULL AND laboratoriais <> ''",
        (cid,),
    )
    if cur.fetchone()[0]:
        return {'laboratorios': 0, 'pulado': 'já importados'}
    import json
    grupos = {}
    pulados = 0
    for idx, row in linhas(ARQ_LAB):
        codigo = como_int(cel(row, idx, 'CODIGOPACIENTE'))
        pid = ids.get(codigo)
        quando = como_data(cel(row, idx, 'DATA_EXAME'))
        if not pid or not quando:
            pulados += 1
            continue
        labs = grupos.setdefault((pid, quando), {})
        for origem, destino in LAB_MAP.items():
            valor = cel(row, idx, origem)
            if valor in (None, ''):
                continue
            labs[destino] = str(valor).strip()[:40]
    gravados = 0
    for (pid, quando), labs in grupos.items():
        if not labs:
            continue
        cur.execute(
            "SELECT id, laboratoriais FROM nut_avaliacoes_nutricionais "
            "WHERE cliente_id = %s AND paciente_id = %s AND data_avaliacao = %s "
            "ORDER BY id DESC LIMIT 1",
            (cid, pid, quando),
        )
        achou = cur.fetchone()
        if achou:
            atual = {}
            if achou[1]:
                try:
                    atual = json.loads(achou[1])
                except ValueError:
                    atual = {}
            if not isinstance(atual, dict):
                atual = {}
            atual.update(labs)
            cur.execute(
                "UPDATE nut_avaliacoes_nutricionais SET laboratoriais = %s WHERE id = %s",
                (json.dumps(atual, ensure_ascii=False), achou[0]),
            )
        else:
            cur.execute(
                """
                INSERT INTO nut_avaliacoes_nutricionais (
                    cliente_id, paciente_id, data_avaliacao, laboratoriais, data_criacao
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (cid, pid, quando, json.dumps(labs, ensure_ascii=False), datetime.utcnow()),
            )
        gravados += 1
    cur.connection.commit()
    return {'laboratorios': gravados, 'sem_paciente': pulados}


def importar_via_oral(cur, cid, ids):
    cur.execute(
        "SELECT COUNT(*) FROM nut_evolucoes_paciente WHERE cliente_id = %s",
        (cid,),
    )
    if cur.fetchone()[0]:
        return {'evolucoes': 0, 'pulado': 'já importadas'}
    grupos = defaultdict(list)
    pulados = 0
    for idx, row in linhas(ARQ_VO):
        codigo = como_int(cel(row, idx, 'CODIGOPACIENTE'))
        pid = ids.get(codigo)
        quando = como_data(cel(row, idx, 'DATA'))
        if not pid or not quando:
            pulados += 1
            continue
        ref = str(cel(row, idx, 'REF') or '').strip()
        rotulo = REF_LABEL.get(ref.upper(), ref or 'Refeição')
        volume = cel(row, idx, 'VOLUME')
        partes = [f'{rotulo}: aceitação {volume if volume not in (None, "") else "-"}%']
        for campo, nome in (
            ('VET', 'VET'), ('HC', 'HC'), ('LIP', 'LIP'), ('PTN', 'PTN'), ('FIBRAS', 'fibras'),
        ):
            valor = cel(row, idx, campo)
            if valor not in (None, '', 0, 0.0):
                partes.append(f'{nome} {valor}')
        grupos[(pid, quando)].append(' · '.join(partes))
    sql = """
        INSERT INTO nut_evolucoes_paciente (
            cliente_id, paciente_id, data_registro, tipo, alteracoes, data_criacao
        ) VALUES (%s, %s, %s, 'oral', %s, %s)
    """
    lote = []
    agora = datetime.utcnow()
    for (pid, quando), linhas_ref in grupos.items():
        lote.append((cid, pid, quando, '\n'.join(linhas_ref), agora))
    if lote:
        cur.executemany(sql, lote)
    cur.connection.commit()
    return {'evolucoes': len(lote), 'sem_paciente': pulados}


def main():
    for arq in (ARQ_PAC, ARQ_AVAL, ARQ_LAB, ARQ_VO):
        if not arq.exists():
            raise SystemExit(f'Arquivo ausente: {arq}')
    conn = conectar()
    try:
        cur = conn.cursor()
        preparar_tabela(cur)
        conn.commit()
        bonsucesso = cliente_id(cur, 'Hospital Federal de Bonsucesso')
        ipanema = cliente_id(cur, 'Hospital Federal de Ipanema')
        mapas, apagados = retirar_copia_ipanema(cur, bonsucesso, ipanema)
        conn.commit()
        print(f'Cópias de Ipanema retiradas de Bonsucesso: {apagados} (mapas desvinculados: {mapas})', flush=True)
        enfermarias = mapa_enfermarias(cur, bonsucesso)
        existentes = ja_importados(cur, bonsucesso)
        print(f'Enfermarias do cliente: {len(enfermarias)}. Já importados: {len(existentes)}', flush=True)
        resumo = importar_pacientes(cur, bonsucesso, enfermarias, existentes)
        print('Pacientes', resumo, flush=True)
        ids = ids_por_codigo(cur, bonsucesso)
        print('Avaliações', importar_avaliacoes(cur, bonsucesso, ids), flush=True)
        print('Laboratório', importar_laboratorios(cur, bonsucesso, ids), flush=True)
        print('Via oral', importar_via_oral(cur, bonsucesso, ids), flush=True)
        cur.execute(
            "SELECT COUNT(*) FROM nut_pacientes WHERE cliente_id = %s AND codigo_legado IS NOT NULL",
            (bonsucesso,),
        )
        print('Total Bonsucesso com código legado:', cur.fetchone()[0], flush=True)
        cur.close()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
