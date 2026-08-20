"""Multi-tenant helpers for Nutrição scoped by Cliente (portal registry)."""
from __future__ import annotations

from flask import g, has_request_context, session

HFB_NOME = 'HOSPITAL FEDERAL DE BONSUCESSO'

# Root nutrição tables that carry cliente_id directly
NUTRICAO_CLIENTE_TABLES = (
    'nut_clinicas',
    'nut_enfermarias',
    'nut_dietas',
    'nut_grupos_dieta',
    'nut_pacientes',
    'nut_mapa_refeicoes',
    'nut_cardapios',
    'nut_tabelas_nutrientes',
    'nut_pratos_liquidos',
    'nut_estoques',
    'nut_unidades',
    'nut_grupos_produto',
    'nut_produtos',
    'nut_fornecedores',
    'nut_etiquetas',
    'nut_precos_refeicoes',
    'nut_tipos_refeicao',
)


def ensure_cliente_hfb():
    """Create/find HOSPITAL FEDERAL DE BONSUCESSO with nutricao enabled."""
    from models import db, Cliente

    cli = Cliente.query.filter(Cliente.nome.ilike(HFB_NOME)).first()
    if not cli:
        cli = Cliente(
            nome=HFB_NOME,
            ativo=True,
            habilitado_chamados=True,
            habilitado_nutricao=True,
        )
        db.session.add(cli)
        db.session.flush()
    else:
        changed = False
        if not getattr(cli, 'habilitado_nutricao', False):
            cli.habilitado_nutricao = True
            changed = True
        if getattr(cli, 'habilitado_chamados', None) is None:
            cli.habilitado_chamados = True
            changed = True
        if changed:
            db.session.flush()
    return cli


def ensure_nutricao_cliente_schema():
    """Add cliente_id to nutrição tables, relax nome uniques, backfill HFB."""
    from sqlalchemy import inspect, text
    from models import db

    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'clientes' not in tables:
            return None

        cli = ensure_cliente_hfb()
        db.session.commit()
        cid = cli.id

        for table in NUTRICAO_CLIENTE_TABLES:
            if table not in tables:
                continue
            cols = {c['name'] for c in insp.get_columns(table)}
            if 'cliente_id' not in cols:
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN cliente_id INT NULL'))
                db.session.commit()
                cols.add('cliente_id')
            db.session.execute(
                text(f'UPDATE {table} SET cliente_id = :cid WHERE cliente_id IS NULL'),
                {'cid': cid},
            )
            db.session.commit()

            # Drop single-column unique indexes that block multi-tenant names
            try:
                insp = inspect(db.engine)
                for idx in insp.get_indexes(table) or []:
                    cols_idx = list(idx.get('column_names') or [])
                    if idx.get('unique') and len(cols_idx) == 1 and cols_idx[0] in (
                        'nome', 'codigo', 'sigla', 'refeicao'
                    ):
                        name = idx.get('name')
                        if not name:
                            continue
                        try:
                            db.session.execute(text(f'ALTER TABLE {table} DROP INDEX `{name}`'))
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
                for uc in insp.get_unique_constraints(table) or []:
                    cols_uc = list(uc.get('column_names') or [])
                    if len(cols_uc) == 1 and cols_uc[0] in ('nome', 'codigo', 'sigla', 'refeicao'):
                        name = uc.get('name')
                        if not name:
                            continue
                        try:
                            db.session.execute(text(f'ALTER TABLE {table} DROP INDEX `{name}`'))
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
            except Exception:
                db.session.rollback()

            # Composite unique (cliente_id, nome/codigo/sigla/refeicao) when applicable
            uniq_specs = []
            if table == 'nut_unidades':
                uniq_specs.append(('codigo', f'uq_{table}_cliente_codigo'))
            elif table == 'nut_tipos_refeicao':
                uniq_specs.append(('nome', f'uq_{table}_cliente_nome'))
                uniq_specs.append(('sigla', f'uq_{table}_cliente_sigla'))
            elif table == 'nut_precos_refeicoes':
                uniq_specs.append(('refeicao', f'uq_{table}_cliente_refeicao'))
            elif table in (
                'nut_clinicas', 'nut_enfermarias', 'nut_dietas', 'nut_grupos_dieta',
                'nut_tabelas_nutrientes', 'nut_pratos_liquidos', 'nut_estoques',
                'nut_grupos_produto', 'nut_fornecedores', 'nut_etiquetas',
            ):
                uniq_specs.append(('nome', f'uq_{table}_cliente_nome'))

            for col, iname in uniq_specs:
                try:
                    db.session.execute(text(
                        f'CREATE UNIQUE INDEX `{iname}` ON {table} (cliente_id, {col})'
                    ))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            # FK (best-effort)
            try:
                insp = inspect(db.engine)
                fks = insp.get_foreign_keys(table) or []
                has_fk = any(
                    'cliente_id' in (fk.get('constrained_columns') or [])
                    and fk.get('referred_table') == 'clientes'
                    for fk in fks
                )
                if not has_fk:
                    db.session.execute(text(
                        f'ALTER TABLE {table} '
                        f'ADD CONSTRAINT fk_{table}_cliente '
                        f'FOREIGN KEY (cliente_id) REFERENCES clientes(id)'
                    ))
                    db.session.commit()
            except Exception:
                db.session.rollback()

            insp = inspect(db.engine)

        # usuarios.cliente_id / cliente_todos
        if 'usuarios' in tables:
            ucols = {c['name'] for c in insp.get_columns('usuarios')}
            if 'cliente_id' not in ucols:
                db.session.execute(text('ALTER TABLE usuarios ADD COLUMN cliente_id INT NULL'))
                db.session.commit()
                ucols.add('cliente_id')
            if 'cliente_todos' not in ucols:
                db.session.execute(text(
                    'ALTER TABLE usuarios ADD COLUMN cliente_todos TINYINT(1) NOT NULL DEFAULT 0'
                ))
                db.session.commit()
                ucols.add('cliente_todos')
            try:
                fks = insp.get_foreign_keys('usuarios') or []
                has_fk = any(
                    'cliente_id' in (fk.get('constrained_columns') or [])
                    and fk.get('referred_table') == 'clientes'
                    for fk in fks
                )
                if not has_fk:
                    db.session.execute(text(
                        'ALTER TABLE usuarios '
                        'ADD CONSTRAINT fk_usuarios_cliente '
                        'FOREIGN KEY (cliente_id) REFERENCES clientes(id)'
                    ))
                    db.session.commit()
            except Exception:
                db.session.rollback()

        return cli
    except Exception:
        db.session.rollback()
        return None


def usuario_sessao_obj():
    from models import Usuario
    uid = session.get('user_id') if has_request_context() else None
    if not uid:
        return None
    return Usuario.query.get(uid)


def usuario_ve_todos_clientes(user):
    """Master/admin or explicit cliente_todos flag → unscoped nutrition view."""
    if not user:
        return False
    if getattr(user, 'cliente_todos', False):
        return True
    return bool(user.is_master or user.tipo == 'admin')


def label_cliente_nutricao(user=None):
    """Sidebar / portal label for nutrition client scope."""
    from models import Cliente

    user = user or usuario_sessao_obj()
    if not user:
        return ''
    if getattr(user, 'cliente_todos', False):
        return 'Todos os clientes'
    cid = getattr(user, 'cliente_id', None)
    if cid:
        cli = getattr(user, 'cliente', None) or Cliente.query.get(cid)
        return (cli.nome if cli else '') or ''
    if user.is_master or user.tipo == 'admin':
        return 'Todos os clientes'
    return ''


def resolve_nutricao_cliente(user=None):
    """Return (user, cliente, cliente_id).

    - cliente_todos → see all (None id)
    - Linked user → that client
    - Master/admin without link → (None id = see all)
    - Other users without link → no cliente (blocked by gate)
    """
    from models import Cliente

    user = user or usuario_sessao_obj()
    if not user:
        return None, None, None
    if getattr(user, 'cliente_todos', False):
        return user, None, None
    cid = getattr(user, 'cliente_id', None)
    if cid:
        cli = Cliente.query.get(cid)
        return user, cli, cid
    if user.is_master or user.tipo == 'admin':
        return user, None, None
    return user, None, None


def current_cliente_id(default=None):
    if has_request_context() and hasattr(g, 'nutricao_cliente_id'):
        return g.nutricao_cliente_id
    _user, _cli, cid = resolve_nutricao_cliente()
    return cid if cid is not None else default


def current_cliente():
    if has_request_context() and hasattr(g, 'nutricao_cliente'):
        return g.nutricao_cliente
    _user, cli, _cid = resolve_nutricao_cliente()
    return cli


def write_cliente_id():
    """Cliente id for inserts. Master/todos without link → HFB."""
    cid = current_cliente_id()
    if cid:
        return cid
    user = usuario_sessao_obj()
    if user and usuario_ve_todos_clientes(user):
        return ensure_cliente_hfb().id
    return None


def apply_cliente_filter(query, model, cliente_id=None):
    """Filter query by cliente_id when set. None = no filter (master/todos all)."""
    if not hasattr(model, 'cliente_id'):
        return query
    cid = cliente_id if cliente_id is not None else current_cliente_id()
    if cid is None:
        return query
    return query.filter(model.cliente_id == cid)


def scoped_query(model, cliente_id=None):
    return apply_cliente_filter(model.query, model, cliente_id=cliente_id)


def row_belongs_to_cliente(row, cliente_id=None):
    if row is None:
        return False
    cid = cliente_id if cliente_id is not None else current_cliente_id()
    if cid is None:
        return True
    return getattr(row, 'cliente_id', None) == cid


def require_cliente_for_write():
    """Return (ok, error_message, cliente_id_for_write)."""
    user = usuario_sessao_obj()
    if not user:
        return False, 'Sessão inválida.', None
    if getattr(user, 'cliente_todos', False):
        return True, None, ensure_cliente_hfb().id
    cid = getattr(user, 'cliente_id', None)
    if cid:
        return True, None, cid
    if user.is_master or user.tipo == 'admin':
        return True, None, ensure_cliente_hfb().id
    return False, 'Seu acesso não está vinculado a um cliente de nutrição. Peça ao administrador.', None
