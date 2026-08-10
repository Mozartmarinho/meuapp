"""
Importa colaboradores e visitantes do dump SQL do Sollus Access (C:\\Sollus)
para as tabelas do módulo Controle de Acesso (meuappdb).

Uso:
  python scripts/importar_sollus_acesso.py
  python scripts/importar_sollus_acesso.py --dump "C:\\Sollus\\13052026.sql"
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

DEFAULT_DUMP = Path(r'C:\Sollus\13052026.sql')
PHOTO_DIRS = [
    Path(r'C:\Sollus'),
    Path(r'C:\Sollus\uploads'),
    Path(r'C:\Sollus\static\uploads'),
    Path(r'C:\Sollus\static\img'),
    ROOT / 'static' / 'acesso_fotos',
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


def _extract_insert(text: str, table: str) -> tuple[list[str] | None, list[tuple]]:
    """Retorna (colunas ou None, rows)."""
    marker = f'INSERT INTO `{table}`'
    start = text.find(marker)
    if start < 0:
        return None, []
    # column list optional
    paren = text.find('(', start)
    values_kw = text.find('VALUES', start)
    if paren < 0 or values_kw < 0:
        return None, []
    cols = None
    if paren < values_kw:
        col_blob = text[paren + 1:text.find(')', paren)]
        cols = [c.strip().strip('`') for c in col_blob.split(',') if c.strip()]
    end = text.find(';', values_kw)
    if end < 0:
        end = len(text)
    values_blob = text[values_kw + 6:end]
    rows = _parse_sql_values(values_blob)
    return cols, rows


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
    for base in PHOTO_DIRS:
        if not base.exists():
            continue
        candidates = [base / name]
        candidates.extend(base.rglob(name))
        for path in candidates:
            if path.is_file():
                mime = mimetypes.guess_type(str(path))[0] or 'image/jpeg'
                data = path.read_bytes()
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


def importar(dump_path: Path) -> dict:
    from app import create_app
    from models import db
    from models_acesso import (
        AcessoPessoa, AcessoVisitante, AcessoEmpresa, AcessoClassificacao,
        AcessoGrupo, AcessoEquipamento,
    )
    from routes_acesso import seed_acesso
    from sqlalchemy import or_ as sa_or_

    # dumps MariaDB/HeidiSQL desta pasta costumam vir em latin-1
    raw = dump_path.read_bytes()
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            text = raw.decode(enc)
            if 'INSERT INTO `users`' in text:
                break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode('latin-1', errors='ignore')
    stats = {
        'dump': str(dump_path),
        'empresas': 0, 'classificacoes': 0, 'grupos': 0, 'equipamentos': 0,
        'pessoas_novas': 0, 'pessoas_atualizadas': 0,
        'visitantes_novos': 0, 'visitantes_atualizados': 0,
        'fotos_encontradas': 0,
    }

    app = create_app()
    with app.app_context():
        seed_acesso()

        # ---- lookups ----
        cols, rows = _extract_insert(text, 'empresas_acesso')
        if not rows:
            cols, rows = _extract_insert(text, 'empresas')
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
        cols_ea, rows_ea = _extract_insert(text, 'empresas_acesso')
        if not rows_ea:
            cols_ea, rows_ea = _extract_insert(text, 'empresas')
        for row in rows_ea:
            d = _row_dict(cols_ea, row, ['id', 'nome', 'cnpj'])
            nome = (d.get('nome') or '').strip()
            emp = AcessoEmpresa.query.filter_by(nome=nome).first()
            if emp and d.get('id') is not None:
                emp_by_src[int(d['id'])] = emp.id

        cols, rows = _extract_insert(text, 'classificacao_users')
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

        cols, rows = _extract_insert(text, 'grupos')
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

        cols, rows = _extract_insert(text, 'equipamentos')
        for row in rows:
            d = _row_dict(cols, row, [
                'id', 'nome', 'marca', 'modelo', 'ip', 'ip_leitor1', 'ip_leitor2',
                'usuario', 'senha', 'device_id', 'controle_giro',
            ])
            nome = (d.get('nome') or '').strip()
            if not nome:
                continue
            device_id = str(d.get('device_id') or '') or None
            eq = None
            if device_id:
                eq = AcessoEquipamento.query.filter_by(device_id=device_id).first()
            if not eq:
                eq = AcessoEquipamento.query.filter_by(nome=nome).first()
            if not eq:
                eq = AcessoEquipamento(
                    nome=nome,
                    marca=(d.get('marca') or d.get('fabricante') or 'Control iD') or 'Control iD',
                    modelo=(d.get('modelo') or '') or None,
                    ip=(d.get('ip') or '') or None,
                    device_id=device_id,
                    controle_giro=(d.get('controle_giro') or '') or None,
                    local=nome,
                    online=bool(d.get('online')),
                    ativo=True,
                )
                db.session.add(eq)
                stats['equipamentos'] += 1
            else:
                eq.ip = d.get('ip') or eq.ip
                eq.modelo = d.get('modelo') or eq.modelo
                eq.controle_giro = d.get('controle_giro') or eq.controle_giro
        db.session.flush()

        # ---- pessoas (users) ----
        user_cols = [
            'id', 'nome', 'user_id', 'foto', 'status', 'deleted_at',
            'data_inicial', 'hora_inicial', 'data_final', 'hora_final',
            'grupo_id', 'token', 'qr_code', 'foto_enviada', 'classificacao',
            'enviado_equipment', 'grupo_ip', 'cards', 'empresa_id',
            'departamento_id', 'setor_id', 'centro_de_custo_id',
        ]
        cols, rows = _extract_insert(text, 'users')
        for row in rows:
            d = _row_dict(cols, row, user_cols)
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
                pessoa.foto = None
                if not pessoa.observacao:
                    pessoa.observacao = f'foto_origem:{foto_file}'
                elif 'foto_origem:' not in (pessoa.observacao or ''):
                    pessoa.observacao = (pessoa.observacao or '') + f' | foto_origem:{foto_file}'

        db.session.flush()

        # ---- visitantes ----
        vis_cols = [
            'id', 'nome', 'visitor_id', 'foto', 'status', 'data_inicial', 'hora_inicial',
            'data_final', 'hora_final', 'grupo_id', 'token', 'foto_enviada', 'classificacao',
            'enviado_equipment', 'grupo_ip', 'cards', 'qr_code', 'visita_unica', 'event',
            'ultima_visita', 'rg', 'cpf', 'empresa_id', 'visita_chave', 'local_id',
        ]
        cols, rows = _extract_insert(text, 'visitantes')
        for row in rows:
            d = _row_dict(cols, row, vis_cols)
            visitor_id = str(d.get('visitor_id') or '').strip()
            nome = (d.get('nome') or '').strip()
            if not visitor_id or not nome:
                continue
            try:
                st = int(d.get('status') if d.get('status') is not None else 1)
            except (TypeError, ValueError):
                st = 1
            ativo = st == 1
            foto_data = _find_photo(d.get('foto'))
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
            # visitantes dump usa empresas (não empresas_acesso) — tenta id 1
            if not vis.empresa_id and emp_by_src:
                vis.empresa_id = next(iter(emp_by_src.values()))
            if src_clas_i and src_clas_i in class_by_src:
                vis.classificacao_id = class_by_src[src_clas_i]
            if foto_data:
                vis.foto = foto_data

        db.session.commit()

        stats['total_pessoas'] = AcessoPessoa.query.count()
        stats['total_visitantes'] = AcessoVisitante.query.count()
    return stats


def main():
    parser = argparse.ArgumentParser(description='Importa dados Sollus Access para o Controle de Acesso')
    parser.add_argument('--dump', type=Path, default=DEFAULT_DUMP, help='Caminho do .sql')
    args = parser.parse_args()
    if not args.dump.exists():
        # fallback para backup
        alt = Path(r'C:\Sollus\backup_SollusAccess.sql')
        if alt.exists():
            args.dump = alt
        else:
            print('Dump não encontrado:', args.dump)
            sys.exit(1)
    print('Importando de', args.dump, '...')
    stats = importar(args.dump)
    print('Concluído:')
    for k, v in stats.items():
        print(f'  {k}: {v}')


if __name__ == '__main__':
    main()
