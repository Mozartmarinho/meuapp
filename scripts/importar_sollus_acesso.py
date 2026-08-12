"""
Importa colaboradores, visitantes, equipamentos e eventos do dump SQL do Sollus Access
(C:\\Sollus) para as tabelas do módulo Controle de Acesso (meuappdb).

Uso:
  .venv\\Scripts\\python.exe scripts/importar_sollus_acesso.py
  .venv\\Scripts\\python.exe scripts/importar_sollus_acesso.py --dump "C:\\Sollus\\sollusaccess_live_20260811.sql"
  .venv\\Scripts\\python.exe scripts/importar_sollus_acesso.py --from-db
  .venv\\Scripts\\python.exe scripts/importar_sollus_acesso.py --replace-eventos

Observações:
  - Fonte preferida ao vivo: MariaDB portátil em C:\\Sollus\\Sollus Access (DB sollusaccess).
  - Dump recente: C:\\Sollus\\sollusaccess_live_*.sql (ou legado 13052026.sql).
  - Visitantes no Sollus atual ficam em `users` (tipo_pessoa/classificacao), não em tabela `visitantes`.
  - Se já existirem poucos eventos (<1000, tipicamente seed), eles são substituídos.
  - Com volume real já importado, por padrão só acrescenta eventos com data_hora > MAX existente
    (merge). Use --replace-eventos para apagar acesso_eventos e reimportar tudo.
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import re
import sys
from datetime import datetime, date, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DUMP = Path(r'C:\Sollus\sollusaccess_live_20260811.sql')
LEGACY_DUMP = Path(r'C:\Sollus\13052026.sql')
PHOTO_DIRS = [
    ROOT / 'static' / 'acesso_fotos',
    Path(r'C:\Sollus\uploads'),
    Path(r'C:\Sollus\static\uploads'),
]
# Pastas amplas só com match direto (sem rglob) — evita varrer dumps/exes.
PHOTO_DIRS_SHALLOW = [
    Path(r'C:\Sollus'),
    Path(r'C:\Sollus\static\img'),
]

# Ordem de colunas do schema Sollus atual (INSERT sem lista de colunas).
USERS_COLS_LIVE = [
    'id', 'nome', 'user_id', 'foto', 'status', 'deleted_at',
    'data_inicial', 'hora_inicial', 'data_final', 'hora_final',
    'grupo_id', 'token', 'qr_code', 'foto_enviada', 'classificacao',
    'enviado_equipment', 'grupo_ip', 'cards', 'empresa_id',
    'departamento_id', 'setor_id', 'centro_de_custo_id',
    'created_at', 'updated_at', 'created_by', 'updated_by',
    'tipo_pessoa', 'id_nuvem', 'unidade_id', 'apt', 'bloco', 'event',
    'sincronizado', 'turma_id', 'visita_unica', 'ultima_visita',
    'rg', 'cpf', 'tipo_doc_id', 'visita_chave', 'local_id',
    'telefone', 'email', 'login_app', 'senha_hash', 'troca_senha',
    'senha_modificada', 'remover_acesso_app', 'rg_cpf',
    'refeicao_creditos', 'refeicao_valor_pago', 'refeicao', 'refeicao_grupo_id',
    'tipo_perfil',
]


def _parse_sql_values(values_blob: str) -> list[tuple]:
    """Parsea tuplas de um INSERT MySQL (suporta NULL, números, strings com aspas)."""
    rows = []
    i = 0
    n = len(values_blob)
    while i < n:
        while i < n and values_blob[i] in ' \t\r\n,':
            i += 1
        if i >= n:
            break
        if values_blob[i] != '(':
            i += 1
            continue
        i += 1  # skip (
        fields = []
        while i < n:
            while i < n and values_blob[i] in ' \t\r\n':
                i += 1
            if i >= n:
                break
            if values_blob[i] == ')':
                i += 1
                rows.append(tuple(fields))
                break
            if values_blob[i] == ',':
                i += 1
                continue
            # NULL
            if values_blob.startswith('NULL', i) and (i + 4 >= n or values_blob[i + 4] in ',)'):
                fields.append(None)
                i += 4
                continue
            # string
            if values_blob[i] in ("'", '"'):
                quote = values_blob[i]
                i += 1
                buf = []
                while i < n:
                    ch = values_blob[i]
                    if ch == '\\' and i + 1 < n:
                        buf.append(values_blob[i + 1])
                        i += 2
                        continue
                    if ch == quote:
                        # escaped '' 
                        if i + 1 < n and values_blob[i + 1] == quote:
                            buf.append(quote)
                            i += 2
                            continue
                        i += 1
                        break
                    buf.append(ch)
                    i += 1
                fields.append(''.join(buf))
                continue
            # number / bareword
            j = i
            while j < n and values_blob[j] not in ',)':
                j += 1
            token = values_blob[i:j].strip()
            i = j
            if re.fullmatch(r'-?\d+', token):
                fields.append(int(token))
            elif re.fullmatch(r'-?\d+\.\d+', token):
                fields.append(float(token))
            else:
                fields.append(token)
        # continue scanning for next tuple
    return rows


def _find_statement_end(text: str, values_kw: int) -> int:
    """Encontra o ';' que fecha o INSERT, ignorando ponto-e-vírgula dentro de strings."""
    i = values_kw
    n = len(text)
    in_str = False
    quote = None
    while i < n:
        ch = text[i]
        if in_str:
            if ch == '\\' and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                # MySQL escaped '' inside single-quoted string
                if quote == "'" and i + 1 < n and text[i + 1] == "'":
                    i += 2
                    continue
                in_str = False
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = True
            quote = ch
            i += 1
            continue
        if ch == ';':
            return i
        i += 1
    return n


def _iter_inserts(text: str, table: str):
    """Yields (cols|None, rows) for every INSERT INTO `table` in the dump."""
    marker = f'INSERT INTO `{table}`'
    start = 0
    while True:
        start = text.find(marker, start)
        if start < 0:
            break
        paren = text.find('(', start)
        values_kw = text.find('VALUES', start)
        if paren < 0 or values_kw < 0:
            break
        cols = None
        if paren < values_kw:
            col_blob = text[paren + 1:text.find(')', paren)]
            cols = [c.strip().strip('`') for c in col_blob.split(',') if c.strip()]
        end = _find_statement_end(text, values_kw)
        values_blob = text[values_kw + 6:end]
        rows = _parse_sql_values(values_blob)
        yield cols, rows
        start = end + 1


def _extract_insert(text: str, table: str) -> tuple[list[str] | None, list[tuple]]:
    """Retorna (colunas ou None, rows) do primeiro INSERT da tabela."""
    for cols, rows in _iter_inserts(text, table):
        return cols, rows
    return None, []


def _extract_all_insert_rows(text: str, table: str) -> tuple[list[str] | None, list[tuple]]:
    """Concatena todos os INSERT da tabela (necessário para `eventos`)."""
    cols = None
    all_rows: list[tuple] = []
    for c, rows in _iter_inserts(text, table):
        if cols is None and c:
            cols = c
        all_rows.extend(rows)
    return cols, all_rows


def _row_dict(cols: list[str] | None, row: tuple, fallback_cols: list[str]) -> dict:
    names = cols or fallback_cols
    data = {}
    for idx, name in enumerate(names):
        if idx < len(row):
            data[name] = row[idx]
    return data


def _parse_date(val) -> date | None:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_time(val) -> time | None:
    if not val:
        return None
    s = str(val).strip()
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _find_photo(filename: str | None) -> str | None:
    """Retorna data-URL se achar o arquivo; senão None."""
    if not filename:
        return None
    name = Path(str(filename)).name
    if not name or name.lower() in ('null', 'none', 'sem_foto.png', 'exemplo_foto.png'):
        return None
    candidates = []
    for base in PHOTO_DIRS:
        if not base.exists():
            continue
        candidates.append(base / name)
        # rglob só em pastas dedicadas de upload (pequenas)
        try:
            candidates.extend(base.rglob(name))
        except OSError:
            pass
    for base in PHOTO_DIRS_SHALLOW:
        if base.exists():
            candidates.append(base / name)
    seen = set()
    for path in candidates:
        try:
            path = path.resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        mime = mimetypes.guess_type(str(path))[0] or 'image/jpeg'
        try:
            data = path.read_bytes()
        except OSError:
            continue
        # evita estourar banco com fotos gigantes
        if len(data) > 2_500_000:
            continue
        b64 = base64.b64encode(data).decode('ascii')
        return f'data:{mime};base64,{b64}'
    return None


def _status_pessoa(status_val, deleted_at) -> tuple[str, bool]:
    if deleted_at:
        return 'Inativo', False
    try:
        st = int(status_val)
    except (TypeError, ValueError):
        st = 1 if status_val else 0
    if st == 1:
        return 'Ativo', True
    return 'Inativo', False


def _parse_datetime(val) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _tipo_pessoa_from_dump(tipo_usuario, classificacao) -> str:
    tu = (str(tipo_usuario or '')).strip().lower()
    if tu in ('visitor', 'visitante', 'visitantes'):
        return 'VISITANTE'
    if tu in ('user', 'pessoa', 'funcionario', 'funcionarios', 'funcionários'):
        return 'PESSOA'
    try:
        clas = int(classificacao) if classificacao not in (None, '') else None
    except (TypeError, ValueError):
        clas = None
    if clas == 2:
        return 'VISITANTE'
    return 'PESSOA'


def _is_visitante_user(d: dict) -> bool:
    tp = (str(d.get('tipo_pessoa') or '')).strip().upper()
    if tp == 'VISITANTE':
        return True
    try:
        clas = int(d.get('classificacao')) if d.get('classificacao') not in (None, '') else None
    except (TypeError, ValueError):
        clas = None
    return clas == 2


def _load_table_from_db(conn, table: str) -> tuple[list[str], list[tuple]]:
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM `{table}`')
    cols = [d[0] for d in cur.description]
    rows = list(cur.fetchall())
    return cols, rows


def _iter_eventos_from_db(conn, since: datetime | None = None, batch_size: int = 5000):
    cur = conn.cursor()
    if since:
        cur.execute(
            'SELECT * FROM `eventos` WHERE data_hora > %s ORDER BY data_hora ASC',
            (since,),
        )
    else:
        cur.execute('SELECT * FROM `eventos` ORDER BY data_hora ASC')
    cols = [d[0] for d in cur.description]
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        yield cols, rows


def _decode_dump(dump_path: Path) -> str:
    raw = dump_path.read_bytes()
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            text = raw.decode(enc)
            if 'INSERT INTO `users`' in text or 'INSERT INTO `eventos`' in text:
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1', errors='ignore')


def importar(
    dump_path: Path | None = None,
    replace_eventos: bool = False,
    batch_size: int = 2000,
    from_db: dict | None = None,
) -> dict:
    from app import create_app
    from models import db
    from models_acesso import (
        AcessoPessoa, AcessoVisitante, AcessoEmpresa, AcessoClassificacao,
        AcessoGrupo, AcessoEquipamento, AcessoEvento,
    )
    from routes_acesso import seed_acesso
    from sqlalchemy import or_ as sa_or_, func as sa_func

    text = ''
    db_conn = None
    if from_db:
        import pymysql
        db_conn = pymysql.connect(
            host=from_db.get('host', '127.0.0.1'),
            port=int(from_db.get('port', 3307)),
            user=from_db.get('user', 'root'),
            password=from_db.get('password', ''),
            database=from_db.get('database', 'sollusaccess'),
            charset='utf8mb4',
            connect_timeout=15,
        )
        source_label = f"db://{from_db.get('host', '127.0.0.1')}:{from_db.get('port', 3307)}/{from_db.get('database', 'sollusaccess')}"
    else:
        if not dump_path or not dump_path.exists():
            raise FileNotFoundError(f'Dump não encontrado: {dump_path}')
        text = _decode_dump(dump_path)
        source_label = str(dump_path)

    stats = {
        'fonte': source_label,
        'empresas': 0, 'classificacoes': 0, 'grupos': 0, 'equipamentos': 0,
        'pessoas_novas': 0, 'pessoas_atualizadas': 0,
        'visitantes_novos': 0, 'visitantes_atualizados': 0,
        'fotos_encontradas': 0,
        'eventos_importados': 0, 'eventos_apagados': 0, 'eventos_lidos': 0,
        'eventos_pulados_antigos': 0,
    }

    def _get_table(name: str) -> tuple[list[str] | None, list[tuple]]:
        if db_conn is not None:
            try:
                return _load_table_from_db(db_conn, name)
            except Exception:
                return None, []
        cols, rows = _extract_insert(text, name)
        if not rows and name != 'eventos':
            # concatenar múltiplos INSERT se houver
            cols, rows = _extract_all_insert_rows(text, name)
        return cols, rows

    app = create_app()
    with app.app_context():
        seed_acesso()

        # ---- lookups ----
        cols, rows = _get_table('empresas_acesso')
        if not rows:
            cols, rows = _get_table('empresas')
        for row in rows:
            d = _row_dict(cols, row, ['id', 'nome', 'cnpj'])
            nome = (d.get('nome') or '').strip()
            if not nome:
                continue
            emp = AcessoEmpresa.query.filter(
                sa_or_(AcessoEmpresa.nome == nome, AcessoEmpresa.cnpj == (d.get('cnpj') or ''))
            ).first()
            if not emp:
                emp = AcessoEmpresa(nome=nome, cnpj=(d.get('cnpj') or None))
                db.session.add(emp)
                stats['empresas'] += 1
        db.session.flush()

        # map source empresa id -> local
        emp_by_src = {}
        cols_ea, rows_ea = _get_table('empresas_acesso')
        if not rows_ea:
            cols_ea, rows_ea = _get_table('empresas')
        for row in rows_ea:
            d = _row_dict(cols_ea, row, ['id', 'nome', 'cnpj'])
            nome = (d.get('nome') or '').strip()
            emp = AcessoEmpresa.query.filter_by(nome=nome).first()
            if emp and d.get('id') is not None:
                emp_by_src[int(d['id'])] = emp.id

        cols, rows = _get_table('classificacao_users')
        class_by_src = {}
        for row in rows:
            d = _row_dict(cols, row, ['id', 'descricao', 'mostrar_visitante'])
            desc = (d.get('descricao') or '').strip()
            if not desc:
                continue
            # normaliza
            if desc.lower().startswith('funcion'):
                desc_norm = 'Colaborador'
            elif desc.lower().startswith('visit'):
                desc_norm = 'Visitante'
            else:
                desc_norm = desc
            clas = AcessoClassificacao.query.filter(
                sa_or_(
                    AcessoClassificacao.descricao == desc,
                    AcessoClassificacao.descricao == desc_norm,
                )
            ).first()
            if not clas:
                clas = AcessoClassificacao(descricao=desc_norm)
                db.session.add(clas)
                db.session.flush()
                stats['classificacoes'] += 1
            if d.get('id') is not None:
                class_by_src[int(d['id'])] = clas.id
        db.session.flush()

        cols, rows = _get_table('grupos')
        grupo_by_src = {}
        for row in rows:
            d = _row_dict(cols, row, ['id', 'nome', 'descricao', 'mostrar_visitante'])
            nome = (d.get('nome') or '').strip()
            if not nome:
                continue
            g = AcessoGrupo.query.filter_by(nome=nome).first()
            if not g:
                g = AcessoGrupo(nome=nome, descricao=(d.get('descricao') or '') or None, ativo=True)
                db.session.add(g)
                db.session.flush()
                stats['grupos'] += 1
            if d.get('id') is not None:
                grupo_by_src[int(d['id'])] = g.id
        db.session.flush()

        cols, rows = _get_table('equipamentos')
        eq_by_src = {}
        for row in rows:
            d = _row_dict(cols, row, [
                'id', 'nome', 'marca', 'modelo', 'ip', 'ip_leitor1', 'ip_leitor2',
                'usuario', 'senha', 'device_id', 'controle_giro',
            ])
            nome = (d.get('nome') or '').strip()
            if not nome:
                continue
            device_id = str(d.get('device_id') or '') or None
            ip = (str(d.get('ip') or '').strip() or None)
            eq = None
            if device_id:
                eq = AcessoEquipamento.query.filter_by(device_id=device_id).first()
            if not eq and ip:
                eq = AcessoEquipamento.query.filter_by(ip=ip).first()
            if not eq:
                eq = AcessoEquipamento.query.filter_by(nome=nome).first()
            if not eq:
                eq = AcessoEquipamento(
                    nome=nome,
                    marca=(d.get('marca') or d.get('fabricante') or 'Control iD') or 'Control iD',
                    modelo=(d.get('modelo') or '') or None,
                    ip=ip,
                    device_id=device_id,
                    controle_giro=(d.get('controle_giro') or '') or None,
                    local=nome,
                    online=bool(d.get('online')),
                    ativo=True,
                )
                db.session.add(eq)
                db.session.flush()
                stats['equipamentos'] += 1
            else:
                eq.ip = ip or eq.ip
                eq.modelo = d.get('modelo') or eq.modelo
                eq.controle_giro = d.get('controle_giro') or eq.controle_giro
                if device_id and not eq.device_id:
                    eq.device_id = device_id
            if d.get('id') is not None:
                try:
                    eq_by_src[int(d['id'])] = eq.id
                except (TypeError, ValueError):
                    pass
        db.session.flush()
        # também indexa por string de id (eventos.equipamento vem como '1','2',...)
        eq_by_src_str = {str(k): v for k, v in eq_by_src.items()}
        # fallback por nome local
        eq_nome_to_id = {
            (e.nome or '').strip().lower(): e.id
            for e in AcessoEquipamento.query.all()
            if (e.nome or '').strip()
        }

        # ---- pessoas / visitantes (users) ----
        # Schema legado: tabela visitantes separada.
        # Schema atual Sollus: visitantes em users (tipo_pessoa/classificacao).
        user_cols = USERS_COLS_LIVE
        cols, rows = _get_table('users')
        if cols is None and rows:
            cols = user_cols if rows and len(rows[0]) >= len(user_cols) - 5 else [
                'id', 'nome', 'user_id', 'foto', 'status', 'deleted_at',
                'data_inicial', 'hora_inicial', 'data_final', 'hora_final',
                'grupo_id', 'token', 'qr_code', 'foto_enviada', 'classificacao',
                'enviado_equipment', 'grupo_ip', 'cards', 'empresa_id',
                'departamento_id', 'setor_id', 'centro_de_custo_id',
            ]

        def _upsert_visitante_from_user(d: dict):
            visitor_id = str(d.get('user_id') or d.get('visitor_id') or '').strip()
            nome = (d.get('nome') or '').strip()
            if not visitor_id or not nome:
                return
            status_txt, ativo = _status_pessoa(d.get('status'), d.get('deleted_at'))
            if d.get('deleted_at'):
                ativo = False
            foto_data = _find_photo(d.get('foto'))
            if foto_data:
                stats['fotos_encontradas'] += 1
            try:
                src_grupo_i = int(d['grupo_id']) if d.get('grupo_id') not in (None, '') else None
            except (TypeError, ValueError):
                src_grupo_i = None
            try:
                src_emp_i = int(d['empresa_id']) if d.get('empresa_id') not in (None, '') else None
            except (TypeError, ValueError):
                src_emp_i = None
            try:
                src_clas_i = int(d['classificacao']) if d.get('classificacao') not in (None, '') else None
            except (TypeError, ValueError):
                src_clas_i = None

            vis = AcessoVisitante.query.filter_by(visitor_id=visitor_id).first()
            if not vis:
                vis = AcessoVisitante(
                    visitor_id=visitor_id,
                    nome=nome.upper(),
                    data_inicial=_parse_date(d.get('data_inicial')) or date.today(),
                )
                db.session.add(vis)
                stats['visitantes_novos'] += 1
            else:
                stats['visitantes_atualizados'] += 1

            vis.nome = nome.upper()
            vis.cpf = (str(d.get('cpf')).strip() if d.get('cpf') else None) or None
            vis.rg = (str(d.get('rg')).strip() if d.get('rg') else None) or None
            vis.documento = vis.cpf or vis.rg
            vis.tipo_documento = 'CPF' if vis.cpf else ('RG' if vis.rg else 'CPF')
            vis.cartao = (str(d.get('cards')).strip() if d.get('cards') else None) or None
            vis.qr_code = (str(d.get('qr_code')).strip() if d.get('qr_code') else None) or None
            vis.token = (str(d.get('token')).strip() if d.get('token') else None) or None
            vis.anfitriao = (str(d.get('ultima_visita')).strip() if d.get('ultima_visita') else None) or None
            vis.visita_unica = bool(d.get('visita_unica'))
            vis.ativo = ativo
            vis.data_inicial = _parse_date(d.get('data_inicial')) or vis.data_inicial
            vis.hora_inicial = _parse_time(d.get('hora_inicial'))
            vis.data_final = _parse_date(d.get('data_final'))
            vis.hora_final = _parse_time(d.get('hora_final'))
            if src_grupo_i and src_grupo_i in grupo_by_src:
                vis.grupo_id = grupo_by_src[src_grupo_i]
            else:
                g = AcessoGrupo.query.filter_by(nome='Visitantes').first()
                if g and not vis.grupo_id:
                    vis.grupo_id = g.id
            if src_emp_i and src_emp_i in emp_by_src:
                vis.empresa_id = emp_by_src[src_emp_i]
                emp = AcessoEmpresa.query.get(vis.empresa_id)
                if emp:
                    vis.empresa_visitada = emp.nome
            if not vis.empresa_id and emp_by_src:
                vis.empresa_id = next(iter(emp_by_src.values()))
            if src_clas_i and src_clas_i in class_by_src:
                vis.classificacao_id = class_by_src[src_clas_i]
            if foto_data:
                vis.foto = foto_data

        for row in rows:
            d = _row_dict(cols, row, user_cols)
            if _is_visitante_user(d):
                _upsert_visitante_from_user(d)
                continue
            matricula = str(d.get('user_id') or '').strip()
            nome = (d.get('nome') or '').strip()
            if not matricula or not nome:
                continue
            status_txt, ativo = _status_pessoa(d.get('status'), d.get('deleted_at'))
            foto_file = d.get('foto')
            foto_data = _find_photo(foto_file)
            if foto_data:
                stats['fotos_encontradas'] += 1

            src_grupo = d.get('grupo_id')
            try:
                src_grupo_i = int(src_grupo) if src_grupo not in (None, '') else None
            except (TypeError, ValueError):
                src_grupo_i = None
            src_emp = d.get('empresa_id')
            try:
                src_emp_i = int(src_emp) if src_emp not in (None, '') else None
            except (TypeError, ValueError):
                src_emp_i = None
            src_clas = d.get('classificacao')
            try:
                src_clas_i = int(src_clas) if src_clas not in (None, '') else None
            except (TypeError, ValueError):
                src_clas_i = None

            pessoa = AcessoPessoa.query.filter_by(matricula=matricula).first()
            created = pessoa is None
            if created:
                pessoa = AcessoPessoa(matricula=matricula, nome=nome.upper())
                db.session.add(pessoa)
                stats['pessoas_novas'] += 1
            else:
                stats['pessoas_atualizadas'] += 1

            pessoa.nome = nome.upper()
            pessoa.cartao = (str(d.get('cards')).strip() if d.get('cards') else None) or None
            pessoa.qr_code = (str(d.get('qr_code')).strip() if d.get('qr_code') else None) or None
            pessoa.token = (str(d.get('token')).strip() if d.get('token') else None) or None
            pessoa.status = status_txt
            pessoa.ativo = ativo
            pessoa.data_inicial = _parse_date(d.get('data_inicial')) or pessoa.data_inicial
            pessoa.hora_inicial = _parse_time(d.get('hora_inicial'))
            pessoa.data_final = _parse_date(d.get('data_final'))
            pessoa.hora_final = _parse_time(d.get('hora_final'))
            if src_grupo_i and src_grupo_i in grupo_by_src:
                pessoa.grupo_id = grupo_by_src[src_grupo_i]
            if src_emp_i and src_emp_i in emp_by_src:
                pessoa.empresa_id = emp_by_src[src_emp_i]
                emp = AcessoEmpresa.query.get(pessoa.empresa_id)
                if emp:
                    pessoa.empresa = emp.nome
            if src_clas_i and src_clas_i in class_by_src:
                pessoa.classificacao_id = class_by_src[src_clas_i]
            if foto_data:
                pessoa.foto = foto_data
            elif foto_file and not pessoa.foto:
                # guarda referência do arquivo original (sem binário no dump)
                if not pessoa.observacao:
                    pessoa.observacao = f'foto_origem:{foto_file}'
                elif 'foto_origem:' not in (pessoa.observacao or ''):
                    pessoa.observacao = (pessoa.observacao or '') + f' | foto_origem:{foto_file}'

        db.session.flush()

        # ---- visitantes (tabela legada, se existir) ----
        vis_cols = [
            'id', 'nome', 'visitor_id', 'foto', 'status', 'data_inicial', 'hora_inicial',
            'data_final', 'hora_final', 'grupo_id', 'token', 'foto_enviada', 'classificacao',
            'enviado_equipment', 'grupo_ip', 'cards', 'qr_code', 'visita_unica', 'event',
            'ultima_visita', 'rg', 'cpf', 'empresa_id', 'visita_chave', 'local_id',
        ]
        cols, rows = _get_table('visitantes')
        for row in rows:
            d = _row_dict(cols, row, vis_cols)
            # reaproveita upsert unificado
            if not d.get('user_id') and d.get('visitor_id'):
                d['user_id'] = d.get('visitor_id')
            _upsert_visitante_from_user(d)

        db.session.flush()

        # ---- eventos (pode ter dezenas/centenas de milhares; commit em lotes) ----
        ev_cols_fallback = [
            'id', 'user_id', 'nome', 'qr_code', 'data_hora', 'status', 'direction',
            'event_type', 'equipamento', 'card', 'girou', 'classificacao',
            'tipo_usuario', 'event', 'visita_chave', 'uhf_tag', 'local_id',
            'motivo_liberacao', 'placa', 'veiculo_modelo', 'estacionamento_id',
        ]
        # Contagem prévia:
        # - seed/demo (<1000) ou --replace-eventos: limpa e reimporta
        # - volume real: merge — só eventos com data_hora > MAX existente
        eventos_atuais = AcessoEvento.query.count()
        max_evento_existente = None
        deve_importar_eventos = True
        merge_novos_apenas = False
        if replace_eventos or eventos_atuais < 1000:
            if eventos_atuais:
                stats['eventos_apagados'] = eventos_atuais
                print(f'  Removendo {eventos_atuais} eventos existentes (seed/reimport)...', flush=True)
                AcessoEvento.query.delete()
                db.session.commit()
        else:
            max_evento_existente = db.session.query(sa_func.max(AcessoEvento.data_hora)).scalar()
            merge_novos_apenas = True
            print(
                f'  Merge de eventos: já existem {eventos_atuais} registros '
                f'(max={max_evento_existente}). Importando apenas posteriores.',
                flush=True,
            )

        if deve_importar_eventos:
            eq_cache = {e.id: e for e in AcessoEquipamento.query.all()}
            batch: list[dict] = []
            lidos = 0
            importados = 0
            pulados = 0
            print('  Lendo/inserindo eventos...', flush=True)

            if db_conn is not None:
                evento_iter = _iter_eventos_from_db(
                    db_conn,
                    since=max_evento_existente if merge_novos_apenas else None,
                    batch_size=max(batch_size, 2000),
                )
            else:
                evento_iter = _iter_inserts(text, 'eventos')

            for cols_ev, rows_ev in evento_iter:
                for row in rows_ev:
                    d = _row_dict(cols_ev, row, ev_cols_fallback)
                    lidos += 1
                    dh = _parse_datetime(d.get('data_hora'))
                    if not dh:
                        continue
                    if merge_novos_apenas and max_evento_existente and dh <= max_evento_existente:
                        pulados += 1
                        continue
                    nome = (d.get('nome') or '').strip() or '(sem nome)'
                    pessoa_ref = str(d.get('user_id') or '').strip() or None
                    if pessoa_ref in ('0', 'None'):
                        # mantém '0' para negar/desconhecido (como no Sollus)
                        pessoa_ref = pessoa_ref if pessoa_ref == '0' else None

                    eq_local_id = None
                    eq_nome = None
                    eq_raw = d.get('equipamento')
                    if eq_raw not in (None, ''):
                        key = str(eq_raw).strip()
                        if key.isdigit() and int(key) in eq_by_src:
                            eq_local_id = eq_by_src[int(key)]
                        elif key in eq_by_src_str:
                            eq_local_id = eq_by_src_str[key]
                        else:
                            # tenta nome direto
                            eq_local_id = eq_nome_to_id.get(key.lower())
                    if eq_local_id:
                        eq_obj = eq_cache.get(eq_local_id)
                        eq_nome = eq_obj.nome if eq_obj else None

                    status = (str(d.get('status') or 'Liberado').strip() or 'Liberado')
                    girou = (str(d.get('girou')).strip() if d.get('girou') not in (None, '') else None)
                    if girou and girou.upper() == 'GIVE UP':
                        status = 'Desistência'

                    batch.append({
                        'pessoa_ref': pessoa_ref,
                        'nome': nome[:120],
                        'tipo_pessoa': _tipo_pessoa_from_dump(d.get('tipo_usuario'), d.get('classificacao')),
                        'status': status[:20],
                        'direction': (str(d.get('direction')).strip()[:40] if d.get('direction') else None) or None,
                        'event_type': (str(d.get('event_type')).strip()[:80] if d.get('event_type') else None) or None,
                        'equipamento_id': eq_local_id,
                        'equipamento_nome': (eq_nome[:100] if eq_nome else None),
                        'cartao': (str(d.get('card')).strip()[:40] if d.get('card') else None) or None,
                        'girou': (girou[:20] if girou else None),
                        'motivo': (
                            str(d.get('motivo_liberacao')).strip()[:120]
                            if d.get('motivo_liberacao') else None
                        ) or None,
                        'data_hora': dh,
                    })
                    if len(batch) >= batch_size:
                        db.session.bulk_insert_mappings(AcessoEvento, batch)
                        db.session.commit()
                        importados += len(batch)
                        batch.clear()
                        if importados % (batch_size * 5) == 0 or importados <= batch_size:
                            print(f'    eventos: {importados}/{lidos}...', flush=True)

            if batch:
                db.session.bulk_insert_mappings(AcessoEvento, batch)
                db.session.commit()
                importados += len(batch)
                batch.clear()

            stats['eventos_lidos'] = lidos
            stats['eventos_importados'] = importados
            stats['eventos_pulados_antigos'] = pulados
            print(f'  Eventos: lidos={lidos}, importados={importados}, pulados_antigos={pulados}', flush=True)
        else:
            db.session.commit()

        stats['total_pessoas'] = AcessoPessoa.query.count()
        stats['total_visitantes'] = AcessoVisitante.query.count()
        stats['total_equipamentos'] = AcessoEquipamento.query.count()
        stats['total_eventos'] = AcessoEvento.query.count()
        stats['total_empresas'] = AcessoEmpresa.query.count()
        stats['total_grupos'] = AcessoGrupo.query.count()
        if stats['total_eventos']:
            mn, mx = db.session.query(
                sa_func.min(AcessoEvento.data_hora),
                sa_func.max(AcessoEvento.data_hora),
            ).one()
            stats['eventos_min'] = str(mn)
            stats['eventos_max'] = str(mx)

    if db_conn is not None:
        db_conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description='Importa dados Sollus Access para o Controle de Acesso')
    parser.add_argument('--dump', type=Path, default=None, help='Caminho do .sql')
    parser.add_argument(
        '--from-db',
        action='store_true',
        help='Lê direto do MariaDB Sollus (padrão 127.0.0.1:3307/sollusaccess)',
    )
    parser.add_argument('--db-host', default='127.0.0.1')
    parser.add_argument('--db-port', type=int, default=3307)
    parser.add_argument('--db-user', default='root')
    parser.add_argument('--db-password', default='')
    parser.add_argument('--db-name', default='sollusaccess')
    parser.add_argument(
        '--replace-eventos',
        action='store_true',
        help='Apaga acesso_eventos e reimporta (necessário só se quiser substituir o histórico)',
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=2000,
        help='Tamanho do lote de commit para eventos (default 2000)',
    )
    args = parser.parse_args()

    from_db = None
    dump_path = args.dump
    if args.from_db:
        from_db = {
            'host': args.db_host,
            'port': args.db_port,
            'user': args.db_user,
            'password': args.db_password,
            'database': args.db_name,
        }
        print(f"Importando de MariaDB {args.db_host}:{args.db_port}/{args.db_name} ...", flush=True)
    else:
        if dump_path is None:
            for candidate in (DEFAULT_DUMP, LEGACY_DUMP, Path(r'C:\Sollus\backup_SollusAccess.sql')):
                if candidate.exists() and candidate.stat().st_size > 0:
                    dump_path = candidate
                    break
        if dump_path is None or not dump_path.exists():
            print('Dump não encontrado. Use --from-db ou --dump CAMINHO.sql')
            sys.exit(1)
        print('Importando de', dump_path, '...', flush=True)

    stats = importar(
        dump_path,
        replace_eventos=args.replace_eventos,
        batch_size=args.batch_size,
        from_db=from_db,
    )
    print('Concluído:')
    for k, v in stats.items():
        print(f'  {k}: {v}')


if __name__ == '__main__':
    main()
