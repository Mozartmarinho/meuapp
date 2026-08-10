"""Rotas do Sistema de Controle de Acesso — São Geraldo Service."""
from functools import wraps
from datetime import datetime, date, time, timedelta
import csv
import io

from flask import (
    Blueprint, render_template, request, jsonify, redirect,
    url_for, flash, session, Response,
)
from sqlalchemy import func, or_, inspect, text

from models import db
from models_acesso import (
    AcessoGrupo, AcessoHorario, AcessoEquipamento,
    AcessoPessoa, AcessoVisitante, AcessoEvento, AcessoAmbiente,
    AcessoEmpresa, AcessoClassificacao, AcessoDepartamento,
    AcessoSetor, AcessoCentroCusto, AcessoTipoDocumento,
)

acesso = Blueprint('acesso', __name__, template_folder='templates_acesso')

# Limite visual de licença (como na tela de referência)
LICENCA_LIMITE_USUARIOS = 600


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _parse_time(value):
    if not value:
        return None
    text_v = str(value).strip()
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(text_v, fmt).time()
        except ValueError:
            continue
    return None


def _parse_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'on', 'yes', 'sim')


def ensure_acesso_schema():
    """Cria tabelas novas e colunas extras em acesso_pessoas (MySQL)."""
    try:
        db.create_all()
        insp = inspect(db.engine)
        if 'acesso_pessoas' not in set(insp.get_table_names()):
            return
        cols = {c['name'] for c in insp.get_columns('acesso_pessoas')}
        alters = []
        specs = {
            'empresa_id': 'INT NULL',
            'classificacao_id': 'INT NULL',
            'departamento_id': 'INT NULL',
            'setor_id': 'INT NULL',
            'centro_custo_id': 'INT NULL',
            'status': "VARCHAR(20) NULL DEFAULT 'Ativo'",
            'foto': 'VARCHAR(255) NULL',
            'hora_inicial': 'TIME NULL',
            'hora_final': 'TIME NULL',
            'tipo_cartao': "VARCHAR(20) NULL DEFAULT 'wiegand'",
            'token': 'VARCHAR(100) NULL',
            'equipamentos_ids': 'VARCHAR(255) NULL',
        }
        for name, ddl in specs.items():
            if name not in cols:
                alters.append(f'ADD COLUMN `{name}` {ddl}')
        if alters:
            db.session.execute(text(f"ALTER TABLE acesso_pessoas {', '.join(alters)}"))
            db.session.commit()
        # sincroniza status a partir de ativo legado
        db.session.execute(text(
            "UPDATE acesso_pessoas SET status='Ativo' "
            "WHERE (status IS NULL OR status='') AND (ativo=1 OR ativo IS NULL)"
        ))
        db.session.execute(text(
            "UPDATE acesso_pessoas SET status='Inativo' "
            "WHERE (status IS NULL OR status='') AND ativo=0"
        ))
        db.session.commit()

        if 'acesso_visitantes' in set(insp.get_table_names()):
            vcols = {c['name'] for c in insp.get_columns('acesso_visitantes')}
            vspecs = {
                'tipo_documento': "VARCHAR(40) NULL DEFAULT 'CPF'",
                'rg': 'VARCHAR(20) NULL',
                'empresa_id': 'INT NULL',
                'classificacao_id': 'INT NULL',
                'anfitriao': 'VARCHAR(120) NULL',
                'tipo_cartao': "VARCHAR(20) NULL DEFAULT 'wiegand'",
                'token': 'VARCHAR(100) NULL',
                'foto': 'LONGTEXT NULL',
                'equipamento_id': 'INT NULL',
                'local_acesso': 'VARCHAR(120) NULL',
                'ident_modo': "VARCHAR(20) NULL DEFAULT 'foto'",
                'refeicao': 'TINYINT(1) NULL DEFAULT 0',
                'refeicao_creditos': 'INT NULL DEFAULT 0',
                'imprimir_ao_salvar': 'TINYINT(1) NULL DEFAULT 0',
                'baixar_qr_ao_salvar': 'TINYINT(1) NULL DEFAULT 0',
                'impressora': 'VARCHAR(80) NULL',
                'modelo_impressao': 'VARCHAR(80) NULL',
            }
            valters = []
            for name, ddl in vspecs.items():
                if name not in vcols:
                    valters.append(f'ADD COLUMN `{name}` {ddl}')
            if valters:
                db.session.execute(text(f"ALTER TABLE acesso_visitantes {', '.join(valters)}"))
                db.session.commit()
    except Exception:
        db.session.rollback()


def _seed_lookup(model, field, values):
    for value in values:
        exists = model.query.filter(getattr(model, field) == value).first()
        if not exists:
            db.session.add(model(**{field: value}))


def seed_acesso():
    """Dados iniciais do módulo de Controle de Acesso."""
    ensure_acesso_schema()

    if AcessoEmpresa.query.count() == 0:
        db.session.add(AcessoEmpresa(nome='São Geraldo Service', cnpj=''))

    _seed_lookup(AcessoClassificacao, 'descricao', [
        'Colaborador', 'Terceirizado', 'Estagiário', 'Livre',
    ])
    _seed_lookup(AcessoDepartamento, 'descricao', [
        'Operações', 'Administrativo', 'Manutenção', 'Nutrição',
    ])
    _seed_lookup(AcessoSetor, 'descricao', [
        'Acesso', 'Recepção', 'TI', 'Cozinha',
    ])
    _seed_lookup(AcessoCentroCusto, 'descricao', [
        'Geral', 'Hospital', 'Administração',
    ])

    if AcessoTipoDocumento.query.count() == 0:
        db.session.add_all([
            AcessoTipoDocumento(descricao='CPF', digitos=11),
            AcessoTipoDocumento(descricao='RG', digitos=0),
            AcessoTipoDocumento(descricao='Passaporte', digitos=0),
            AcessoTipoDocumento(descricao='CNH', digitos=11),
        ])

    if AcessoGrupo.query.count() == 0:
        padrao = AcessoGrupo(
            nome='Acesso Geral',
            descricao='Grupo padrão com liberação em todos os equipamentos.',
            ativo=True,
        )
        visitantes = AcessoGrupo(
            nome='Visitantes',
            descricao='Acesso temporário para visitantes.',
            ativo=True,
        )
        db.session.add_all([padrao, visitantes])
        db.session.flush()
        db.session.add(AcessoHorario(
            grupo_id=padrao.id,
            dia_semana='TODOS',
            hora_inicial=time(0, 0),
            hora_final=time(23, 59),
        ))
        db.session.add(AcessoHorario(
            grupo_id=visitantes.id,
            dia_semana='TODOS',
            hora_inicial=time(7, 0),
            hora_final=time(19, 0),
        ))

    agora = datetime.utcnow()
    equipamentos_seed = [
        ('Recepção', '192.168.0.237', 'DEV-REC', True, 'Ambos os lados', 'iDFace'),
        ('Fabrica', '192.168.0.234', 'DEV-FAB', True, 'Ambos os lados', 'iDFace'),
        ('Escritorio', '192.168.0.247', 'DEV-ESC', False, 'Somente Entrada', 'iDFlex'),
        ('Portão Principal', '192.168.0.246', 'DEV-POR', False, 'Ambos os lados', 'iDBlock'),
        ('Portaria', '192.168.0.239', 'DEV-PTA', False, 'Ambos os lados', 'iDFace'),
        ('Refeitorio', '192.168.0.233', 'DEV-REF', False, 'Entrada/Saida', 'iDFace'),
    ]
    for nome, ip, device_id, online, giro, modelo in equipamentos_seed:
        eq = AcessoEquipamento.query.filter(
            or_(AcessoEquipamento.device_id == device_id, AcessoEquipamento.nome == nome)
        ).first()
        if not eq:
            db.session.add(AcessoEquipamento(
                nome=nome, marca='Control iD', modelo=modelo, ip=ip, device_id=device_id,
                controle_giro=giro, local=nome, online=online,
                last_alive=agora if online else None, ativo=True,
            ))
        else:
            eq.ip = eq.ip or ip
            eq.online = online if eq.last_alive is None else eq.online
            if online and not eq.last_alive:
                eq.last_alive = agora

    if AcessoAmbiente.query.count() == 0:
        db.session.add_all([
            AcessoAmbiente(nome='Refeitório', descricao='Área de refeições', capacidade_maxima=120, ocupacao_atual=34, ativo=True),
            AcessoAmbiente(nome='Auditorio', descricao='Eventos e treinamentos', capacidade_maxima=80, ocupacao_atual=12, ativo=True),
            AcessoAmbiente(nome='Área VIP', descricao='Acesso restrito', capacidade_maxima=20, ocupacao_atual=5, ativo=True),
        ])

    if AcessoPessoa.query.count() == 0:
        grupo = AcessoGrupo.query.filter_by(nome='Acesso Geral').first()
        emp = AcessoEmpresa.query.first()
        clas = AcessoClassificacao.query.filter_by(descricao='Colaborador').first()
        dep = AcessoDepartamento.query.filter_by(descricao='Operações').first()
        setr = AcessoSetor.query.filter_by(descricao='Acesso').first()
        cc = AcessoCentroCusto.query.filter_by(descricao='Geral').first()
        pessoa = AcessoPessoa(
            matricula='1001',
            nome='COLABORADOR DEMO',
            cartao='123456',
            empresa_id=emp.id if emp else None,
            classificacao_id=clas.id if clas else None,
            departamento_id=dep.id if dep else None,
            setor_id=setr.id if setr else None,
            centro_custo_id=cc.id if cc else None,
            departamento=dep.descricao if dep else 'Operações',
            setor=setr.descricao if setr else 'Acesso',
            empresa=emp.nome if emp else 'São Geraldo Service',
            grupo_id=grupo.id if grupo else None,
            status='Ativo',
            ativo=True,
        )
        db.session.add(pessoa)

    if AcessoEvento.query.count() == 0:
        eq_rec = AcessoEquipamento.query.filter_by(nome='Recepção').first()
        eq_fab = AcessoEquipamento.query.filter_by(nome='Fabrica').first()
        agora = datetime.utcnow()
        amostras = [
            ('12977641700', 'MARIA SILVA SANTOS', 'Liberado', 'Entrada', 'Face', 'TURN LEFT', eq_rec, 2),
            ('12977827714', 'ADALBERTO GOMES DA CRUZ', 'Liberado', 'Saída', 'Face', 'TURN RIGHT', eq_fab, 5),
            ('1001', 'COLABORADOR DEMO', 'Negado', 'Entrada', 'Cartao', '', eq_rec, 8),
            ('12977001122', 'ANA PAULA FERREIRA', 'Desistência', 'Entrada', 'Face', 'GIVE UP', eq_fab, 12),
            ('12977641700', 'MARIA SILVA SANTOS', 'Liberado', 'Saída', 'Face', 'TURN RIGHT', eq_rec, 20),
            ('12977999888', 'JOAO PEDRO ALMEIDA', 'Liberado', 'Entrada', 'QR', 'TURN LEFT', eq_fab, 35),
            ('1001', 'COLABORADOR DEMO', 'Liberado', 'Entrada', 'Face', 'TURN LEFT', eq_rec, 50),
            ('12977001122', 'ANA PAULA FERREIRA', 'Negado', 'Entrada', 'Face', '', eq_fab, 65),
        ]
        for mat, nome, st, direcao, metodo, girou, eq, mins in amostras:
            db.session.add(AcessoEvento(
                pessoa_ref=mat,
                nome=nome,
                tipo_pessoa='PESSOA',
                status=st,
                direction=direcao,
                event_type=metodo,
                equipamento_id=eq.id if eq else None,
                equipamento_nome=eq.nome if eq else None,
                girou=girou or None,
                data_hora=agora - timedelta(minutes=mins),
            ))

    db.session.commit()


def _catalogos():
    return {
        'empresas': [e.to_dict() for e in AcessoEmpresa.query.order_by(AcessoEmpresa.nome).all()],
        'classificacoes': [c.to_dict() for c in AcessoClassificacao.query.order_by(AcessoClassificacao.descricao).all()],
        'departamentos': [d.to_dict() for d in AcessoDepartamento.query.order_by(AcessoDepartamento.descricao).all()],
        'setores': [s.to_dict() for s in AcessoSetor.query.order_by(AcessoSetor.descricao).all()],
        'centros': [c.to_dict() for c in AcessoCentroCusto.query.order_by(AcessoCentroCusto.descricao).all()],
        'grupos': [g.to_dict() for g in AcessoGrupo.query.order_by(AcessoGrupo.nome).all()],
    }


def _apply_pessoa_fields(pessoa, data):
    if 'nome' in data and data.get('nome') is not None:
        pessoa.nome = (data.get('nome') or pessoa.nome).strip().upper()
    if 'matricula' in data and data.get('matricula') is not None:
        nova = (data.get('matricula') or '').strip()
        if nova and nova != pessoa.matricula:
            if AcessoPessoa.query.filter(
                AcessoPessoa.matricula == nova,
                AcessoPessoa.id != (pessoa.id or 0),
            ).first():
                raise ValueError('Matrícula já cadastrada')
            pessoa.matricula = nova
    for field in ('cartao', 'qr_code', 'documento', 'observacao', 'foto', 'token', 'tipo_cartao', 'equipamentos_ids'):
        if field in data:
            setattr(pessoa, field, (data.get(field) or '').strip() or None)

    for field in ('empresa_id', 'classificacao_id', 'departamento_id', 'setor_id', 'centro_custo_id', 'grupo_id'):
        if field in data:
            setattr(pessoa, field, _parse_int(data.get(field)))

    # espelha nomes em campos texto legados
    if pessoa.empresa_id:
        emp = AcessoEmpresa.query.get(pessoa.empresa_id)
        pessoa.empresa = emp.nome if emp else pessoa.empresa
    elif 'empresa' in data:
        pessoa.empresa = (data.get('empresa') or '').strip() or None

    if pessoa.departamento_id:
        dep = AcessoDepartamento.query.get(pessoa.departamento_id)
        pessoa.departamento = dep.descricao if dep else pessoa.departamento
    if pessoa.setor_id:
        setr = AcessoSetor.query.get(pessoa.setor_id)
        pessoa.setor = setr.descricao if setr else pessoa.setor

    if 'data_inicial' in data:
        pessoa.data_inicial = _parse_date(data.get('data_inicial')) or pessoa.data_inicial or date.today()
    if 'hora_inicial' in data:
        pessoa.hora_inicial = _parse_time(data.get('hora_inicial')) or pessoa.hora_inicial or time(0, 0)
    if 'data_final' in data:
        pessoa.data_final = _parse_date(data.get('data_final'))
    if 'hora_final' in data:
        pessoa.hora_final = _parse_time(data.get('hora_final'))

    if 'status' in data and data.get('status') is not None and data.get('status') != '':
        raw = str(data.get('status')).strip()
        # compatível com 1/0/2 da UI de referência
        mapa = {'1': 'Ativo', '0': 'Inativo', '2': 'Livre', 'ativo': 'Ativo', 'inativo': 'Inativo', 'livre': 'Livre'}
        pessoa.status = mapa.get(raw.lower(), raw)
    elif 'ativo' in data:
        pessoa.status = 'Ativo' if str(data.get('ativo')).lower() not in ('0', 'false', 'off') else 'Inativo'
    pessoa.sync_ativo_status()


def _date_range(range_key, custom_date=None):
    """Retorna (inicio, fim, label_comparacao, inicio_cmp, fim_cmp)."""
    hoje = date.today()
    if custom_date:
        d = _parse_date(custom_date)
        if d:
            ini = datetime.combine(d, time.min)
            fim = datetime.combine(d, time.max)
            cmp_ini = ini - timedelta(days=30)
            cmp_fim = fim - timedelta(days=30)
            return ini, fim, 'vs. 30 dias anteriores', cmp_ini, cmp_fim

    key = (range_key or 'today').lower()
    if key == 'all':
        return None, None, 'vs. período anterior', None, None
    if key == 'yesterday':
        d = hoje - timedelta(days=1)
        ini = datetime.combine(d, time.min)
        fim = datetime.combine(d, time.max)
        cmp_ini = ini - timedelta(days=1)
        cmp_fim = fim - timedelta(days=1)
        return ini, fim, 'vs. dia anterior', cmp_ini, cmp_fim
    if key == '7days':
        ini = datetime.combine(hoje - timedelta(days=6), time.min)
        fim = datetime.combine(hoje, time.max)
        cmp_ini = ini - timedelta(days=7)
        cmp_fim = ini - timedelta(seconds=1)
        return ini, fim, 'vs. 7 dias anteriores', cmp_ini, cmp_fim

    # today (default)
    ini = datetime.combine(hoje, time.min)
    fim = datetime.combine(hoje, time.max)
    cmp_ini = ini - timedelta(days=30)
    cmp_fim = ini - timedelta(seconds=1)
    return ini, fim, 'vs. 30 dias anteriores', cmp_ini, cmp_fim


def _count_status(query):
    liberados = negados = desistencias = 0
    for st, girou in query.with_entities(AcessoEvento.status, AcessoEvento.girou).all():
        if (girou or '').upper() == 'GIVE UP' or st == 'Desistência':
            desistencias += 1
        elif st == 'Negado':
            negados += 1
        else:
            liberados += 1
    return liberados, negados, desistencias


def _eventos_filtrados(range_key='today', custom_date=None, status_filter='', search=''):
    ini, fim, cmp_label, cmp_ini, cmp_fim = _date_range(range_key, custom_date)
    q = AcessoEvento.query
    if ini and fim:
        q = q.filter(AcessoEvento.data_hora >= ini, AcessoEvento.data_hora <= fim)
    if search:
        like = f'%{search}%'
        q = q.filter(or_(
            AcessoEvento.nome.ilike(like),
            AcessoEvento.pessoa_ref.ilike(like),
            AcessoEvento.equipamento_nome.ilike(like),
        ))
    if status_filter:
        sf = status_filter.lower()
        if sf == 'liberado':
            q = q.filter(AcessoEvento.status == 'Liberado').filter(
                or_(AcessoEvento.girou.is_(None), AcessoEvento.girou != 'GIVE UP')
            )
        elif sf == 'negado':
            q = q.filter(AcessoEvento.status == 'Negado')
        elif sf == 'desistencia':
            q = q.filter(or_(
                AcessoEvento.status == 'Desistência',
                AcessoEvento.girou == 'GIVE UP',
            ))
    return q, ini, fim, cmp_label, cmp_ini, cmp_fim


def _stats_periodo(ini, fim):
    q = AcessoEvento.query
    if ini and fim:
        q = q.filter(AcessoEvento.data_hora >= ini, AcessoEvento.data_hora <= fim)
    liberados, negados, desistencias = _count_status(q)
    total = liberados + negados  # total acessos (sem desistências no total principal, como referência)
    # na UI de referência: Total = liberados + negados
    return {
        'total': total,
        'liberados': liberados,
        'negados': negados,
        'desistencias': desistencias,
    }


# ---- PÁGINAS ----
@acesso.route('/acesso')
@login_required
def dashboard():
    seed_acesso()
    range_key = (request.args.get('range') or 'today').strip()
    custom_date = request.args.get('date') or ''
    status_filter = (request.args.get('status') or '').strip()
    search = (request.args.get('q') or '').strip()

    q, ini, fim, cmp_label, cmp_ini, cmp_fim = _eventos_filtrados(
        range_key, custom_date, status_filter, search
    )
    stats = _stats_periodo(ini, fim)
    stats_cmp = _stats_periodo(cmp_ini, cmp_fim) if cmp_ini and cmp_fim else {'liberados': 0}
    base_lib = stats_cmp.get('liberados') or 0
    if base_lib:
        pct_lib = ((stats['liberados'] - base_lib) / base_lib) * 100
    else:
        pct_lib = 100.0 if stats['liberados'] else 0.0

    eventos = q.order_by(AcessoEvento.data_hora.desc()).limit(50).all()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    online_list = [e for e in equipamentos if e.online]
    ambientes = AcessoAmbiente.query.filter_by(ativo=True).order_by(AcessoAmbiente.nome).all()

    return render_template(
        'acesso_dashboard.html',
        stats=stats,
        pct_liberados=pct_lib,
        comparison_label=cmp_label,
        eventos=[e.to_dict() for e in eventos],
        equipamentos=[e.to_dict() for e in equipamentos],
        online_count=len(online_list),
        offline_count=len(equipamentos) - len(online_list),
        ambientes=[a.to_dict() for a in ambientes],
        range_key=range_key if not custom_date else 'custom',
        custom_date=custom_date,
        status_filter=status_filter,
        search=search,
        active_page='dashboard',
        active_sub='dashboard',
    )


@acesso.route('/acesso/api/dashboard')
@login_required
def api_dashboard():
    """JSON para atualização periódica do monitoramento."""
    seed_acesso()
    range_key = (request.args.get('range') or 'today').strip()
    custom_date = request.args.get('date') or ''
    status_filter = (request.args.get('status') or '').strip()
    search = (request.args.get('q') or '').strip()
    q, ini, fim, cmp_label, cmp_ini, cmp_fim = _eventos_filtrados(
        range_key, custom_date, status_filter, search
    )
    stats = _stats_periodo(ini, fim)
    stats_cmp = _stats_periodo(cmp_ini, cmp_fim) if cmp_ini and cmp_fim else {'liberados': 0}
    base_lib = stats_cmp.get('liberados') or 0
    pct_lib = ((stats['liberados'] - base_lib) / base_lib) * 100 if base_lib else (100.0 if stats['liberados'] else 0.0)
    eventos = q.order_by(AcessoEvento.data_hora.desc()).limit(50).all()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    online = sum(1 for e in equipamentos if e.online)
    return jsonify({
        'ok': True,
        'stats': stats,
        'pct_liberados': pct_lib,
        'comparison_label': cmp_label,
        'eventos': [e.to_dict() for e in eventos],
        'equipamentos': [e.to_dict() for e in equipamentos],
        'online_count': online,
        'offline_count': len(equipamentos) - online,
        'ambientes': [a.to_dict() for a in AcessoAmbiente.query.filter_by(ativo=True).all()],
    })


@acesso.route('/acesso/pessoas')
@login_required
def pessoas_page():
    seed_acesso()
    filtros = {
        'q': (request.args.get('q') or request.args.get('search_term') or '').strip(),
        'empresa_id': request.args.get('f_empresa_id') or request.args.get('empresa_id') or '',
        'classificacao_id': request.args.get('f_classificacao') or request.args.get('classificacao_id') or '',
        'departamento_id': request.args.get('f_departamento_id') or request.args.get('departamento_id') or '',
        'setor_id': request.args.get('f_setor_id') or request.args.get('setor_id') or '',
        'centro_custo_id': request.args.get('f_centro_de_custo_id') or request.args.get('centro_custo_id') or '',
        'mostrar_inativos': request.args.get('mostrar_inativos') in ('1', 'true', 'on'),
        'apenas_sem_foto': request.args.get('apenas_sem_foto') in ('1', 'true', 'on'),
    }

    query = AcessoPessoa.query
    if filtros['q']:
        like = f"%{filtros['q']}%"
        query = query.filter(or_(
            AcessoPessoa.nome.ilike(like),
            AcessoPessoa.matricula.ilike(like),
            AcessoPessoa.cartao.ilike(like),
            AcessoPessoa.documento.ilike(like),
        ))
    if filtros['empresa_id']:
        query = query.filter(AcessoPessoa.empresa_id == int(filtros['empresa_id']))
    if filtros['classificacao_id']:
        query = query.filter(AcessoPessoa.classificacao_id == int(filtros['classificacao_id']))
    if filtros['departamento_id']:
        query = query.filter(AcessoPessoa.departamento_id == int(filtros['departamento_id']))
    if filtros['setor_id']:
        query = query.filter(AcessoPessoa.setor_id == int(filtros['setor_id']))
    if filtros['centro_custo_id']:
        query = query.filter(AcessoPessoa.centro_custo_id == int(filtros['centro_custo_id']))
    if not filtros['mostrar_inativos']:
        query = query.filter(or_(
            AcessoPessoa.status.in_(['Ativo', 'Livre']),
            AcessoPessoa.status.is_(None),
        ))
        query = query.filter(or_(AcessoPessoa.ativo.is_(True), AcessoPessoa.ativo.is_(None)))
    if filtros['apenas_sem_foto']:
        query = query.filter(or_(AcessoPessoa.foto.is_(None), AcessoPessoa.foto == ''))

    pessoas = query.order_by(AcessoPessoa.nome).all()
    total_ativos_licenca = AcessoPessoa.query.filter(
        or_(AcessoPessoa.status.in_(['Ativo', 'Livre']), AcessoPessoa.status.is_(None))
    ).count()
    cats = _catalogos()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    return render_template(
        'acesso_pessoas.html',
        pessoas=[p.to_dict() for p in pessoas],
        total_encontrados=len(pessoas),
        total_ativos_licenca=total_ativos_licenca,
        limite_usuarios=LICENCA_LIMITE_USUARIOS,
        filtros=filtros,
        equipamentos=[e.to_dict() for e in equipamentos],
        active_page='pessoas',
        active_sub='cadastros',
        **cats,
    )


@acesso.route('/acesso/pessoas/export.csv')
@login_required
def pessoas_export_csv():
    seed_acesso()
    pessoas = AcessoPessoa.query.order_by(AcessoPessoa.nome).all()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow([
        'matricula', 'nome', 'status', 'cartao', 'empresa', 'classificacao',
        'departamento', 'setor', 'centro_custo', 'grupo', 'documento',
    ])
    for p in pessoas:
        d = p.to_dict()
        writer.writerow([
            d['matricula'], d['nome'], d['status'], d['cartao'], d['empresa_nome'],
            d['classificacao'], d['departamento'], d['setor'], d['centro_custo'],
            d['grupo_nome'], d['documento'],
        ])
    data = '\ufeff' + buf.getvalue()
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=colaboradores.csv'},
    )


@acesso.route('/acesso/equipamentos')
@login_required
def equipamentos_page():
    seed_acesso()
    equipamentos = AcessoEquipamento.query.order_by(AcessoEquipamento.nome).all()
    return render_template(
        'acesso_equipamentos.html',
        equipamentos=[e.to_dict() for e in equipamentos],
        active_page='equipamentos',
    )


@acesso.route('/acesso/grupos')
@login_required
def grupos_page():
    seed_acesso()
    grupos = AcessoGrupo.query.order_by(AcessoGrupo.nome).all()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    grupos_data = []
    for g in grupos:
        d = g.to_dict()
        d['equipamento_ids'] = [e.id for e in g.equipamentos]
        d['horarios'] = [h.to_dict() for h in g.horarios]
        grupos_data.append(d)
    return render_template(
        'acesso_grupos.html',
        grupos=grupos_data,
        equipamentos=[e.to_dict() for e in equipamentos],
        active_page='grupos',
    )


@acesso.route('/acesso/visitantes')
@login_required
def visitantes_page():
    seed_acesso()
    view = (request.args.get('view') or 'cadastro').strip().lower()
    if view not in ('cadastro', 'lista', 'relatorios'):
        view = 'cadastro'
    q = (request.args.get('q') or '').strip()
    query = AcessoVisitante.query
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoVisitante.nome.ilike(like),
            AcessoVisitante.visitor_id.ilike(like),
            AcessoVisitante.cpf.ilike(like),
            AcessoVisitante.documento.ilike(like),
            AcessoVisitante.anfitriao.ilike(like),
        ))
    visitantes = query.order_by(AcessoVisitante.data_criacao.desc()).limit(200).all()
    cats = _catalogos()
    tipos_doc = [t.to_dict() for t in AcessoTipoDocumento.query.order_by(AcessoTipoDocumento.descricao).all()]
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    hoje = date.today()
    ativos_hoje = AcessoVisitante.query.filter(
        AcessoVisitante.ativo.is_(True),
        AcessoVisitante.data_inicial <= hoje,
        or_(AcessoVisitante.data_final.is_(None), AcessoVisitante.data_final >= hoje),
    ).count()
    return render_template(
        'acesso_visitantes.html',
        view=view,
        visitantes=[v.to_dict() for v in visitantes],
        tipos_doc=tipos_doc,
        equipamentos=[e.to_dict() for e in equipamentos],
        q=q,
        total_visitantes=AcessoVisitante.query.count(),
        ativos_hoje=ativos_hoje,
        active_page='visitantes',
        active_sub='visitantes',
        **cats,
    )


@acesso.route('/acesso/eventos')
@login_required
def eventos_page():
    seed_acesso()
    status = (request.args.get('status') or '').strip()
    q = (request.args.get('q') or '').strip()
    query = AcessoEvento.query
    if status:
        query = query.filter(AcessoEvento.status == status)
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            AcessoEvento.nome.ilike(like),
            AcessoEvento.pessoa_ref.ilike(like),
            AcessoEvento.equipamento_nome.ilike(like),
        ))
    eventos = query.order_by(AcessoEvento.data_hora.desc()).limit(200).all()
    equipamentos = AcessoEquipamento.query.filter_by(ativo=True).order_by(AcessoEquipamento.nome).all()
    return render_template(
        'acesso_eventos.html',
        eventos=[e.to_dict() for e in eventos],
        equipamentos=[eq.to_dict() for eq in equipamentos],
        status=status,
        q=q,
        active_page='eventos',
    )


@acesso.route('/acesso/ambientes')
@login_required
def ambientes_page():
    seed_acesso()
    ambientes = AcessoAmbiente.query.order_by(AcessoAmbiente.nome).all()
    items = [
        [a.nome, a.descricao or '—', f'{a.ocupacao_atual}/{a.capacidade_maxima}', 'Ativo' if a.ativo else 'Inativo']
        for a in ambientes
    ]
    return render_template(
        'acesso_placeholder.html',
        page_title='Gestão de Ambientes',
        page_desc='Controle de lotação e capacidade dos ambientes (refeitório, auditório, áreas restritas).',
        columns=['Ambiente', 'Descrição', 'Ocupação', 'Status'],
        items=items,
        active_page='ambientes',
    )


@acesso.route('/acesso/estacionamentos')
@login_required
def estacionamentos_page():
    return render_template(
        'acesso_placeholder.html',
        page_title='Estacionamentos',
        page_desc='Gestão de vagas, permissões e ocupação de veículos — em expansão.',
        active_page='estacionamentos',
    )


@acesso.route('/acesso/impressoras')
@login_required
def impressoras_page():
    return render_template(
        'acesso_placeholder.html',
        page_title='Impressoras',
        page_desc='Configuração de impressoras de crachá, etiquetas e comprovantes — em expansão.',
        active_page='impressoras',
    )


@acesso.route('/acesso/veiculos')
@login_required
def veiculos_page():
    return render_template(
        'acesso_placeholder.html',
        page_title='Veículos',
        page_desc='Relatório de acessos veiculares (placa, tag UHF e liberação) — em expansão.',
        active_page='veiculos',
    )


@acesso.route('/acesso/permanencia')
@login_required
def permanencia_page():
    return render_template(
        'acesso_placeholder.html',
        page_title='Permanência',
        page_desc='Tempo de permanência por pessoa/ambiente (primeira entrada e última saída) — em expansão.',
        active_page='permanencia',
    )


@acesso.route('/acesso/sobre')
@login_required
def sobre_page():
    return render_template(
        'acesso_placeholder.html',
        page_title='Sobre o Sistema',
        page_desc='Sistema de Controle de Acesso — São Geraldo Service. Gestão de colaboradores, equipamentos, regras e monitoramento em tempo real.',
        active_page='sobre',
    )


# ---- APIs Pessoas ----
@acesso.route('/acesso/api/pessoas', methods=['GET', 'POST'])
@login_required
def api_pessoas():
    seed_acesso()
    if request.method == 'GET':
        return jsonify([p.to_dict() for p in AcessoPessoa.query.order_by(AcessoPessoa.nome).all()])

    data = request.get_json(silent=True) or request.form.to_dict()
    matricula = (data.get('matricula') or '').strip()
    nome = (data.get('nome') or '').strip()
    if not matricula or not nome:
        return jsonify({'ok': False, 'error': 'Matrícula e nome são obrigatórios'}), 400
    if AcessoPessoa.query.filter_by(matricula=matricula).first():
        return jsonify({'ok': False, 'error': 'Matrícula já cadastrada'}), 400

    pessoa = AcessoPessoa(
        matricula=matricula,
        nome=nome.upper(),
        status=(data.get('status') or 'Ativo').strip(),
        data_inicial=_parse_date(data.get('data_inicial')) or date.today(),
    )
    try:
        _apply_pessoa_fields(pessoa, data)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    db.session.add(pessoa)
    db.session.commit()
    return jsonify({'ok': True, 'pessoa': pessoa.to_dict()}), 201


@acesso.route('/acesso/api/pessoas/<int:pid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_pessoa_item(pid):
    pessoa = AcessoPessoa.query.get_or_404(pid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'pessoa': pessoa.to_dict()})
    if request.method == 'DELETE':
        db.session.delete(pessoa)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    try:
        _apply_pessoa_fields(pessoa, data)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    db.session.commit()
    return jsonify({'ok': True, 'pessoa': pessoa.to_dict()})


# ---- APIs Equipamentos ----
@acesso.route('/acesso/api/equipamentos', methods=['GET', 'POST'])
@login_required
def api_equipamentos():
    seed_acesso()
    if request.method == 'GET':
        return jsonify([e.to_dict() for e in AcessoEquipamento.query.order_by(AcessoEquipamento.nome).all()])

    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome é obrigatório'}), 400

    device_id = (data.get('device_id') or '').strip() or None
    if device_id and AcessoEquipamento.query.filter_by(device_id=device_id).first():
        return jsonify({'ok': False, 'error': 'device_id já cadastrado'}), 400

    eq = AcessoEquipamento(
        nome=nome,
        marca=(data.get('marca') or 'Control iD').strip(),
        modelo=(data.get('modelo') or '').strip() or None,
        ip=(data.get('ip') or '').strip() or None,
        device_id=device_id,
        usuario_disp=(data.get('usuario_disp') or 'admin').strip(),
        senha_disp=(data.get('senha_disp') or '').strip() or None,
        controle_giro=(data.get('controle_giro') or 'Ambos os lados').strip(),
        local=(data.get('local') or '').strip() or None,
        ativo=str(data.get('ativo', '1')).lower() not in ('0', 'false', 'off'),
    )
    db.session.add(eq)
    db.session.commit()
    return jsonify({'ok': True, 'equipamento': eq.to_dict()}), 201


@acesso.route('/acesso/api/equipamentos/<int:eid>', methods=['PUT', 'DELETE'])
@login_required
def api_equipamento_item(eid):
    eq = AcessoEquipamento.query.get_or_404(eid)
    if request.method == 'DELETE':
        db.session.delete(eq)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    for field in ('nome', 'marca', 'modelo', 'ip', 'usuario_disp', 'senha_disp', 'controle_giro', 'local'):
        if field in data:
            setattr(eq, field, (data.get(field) or '').strip() or None)
    if 'device_id' in data:
        nova = (data.get('device_id') or '').strip() or None
        if nova and nova != eq.device_id:
            if AcessoEquipamento.query.filter_by(device_id=nova).first():
                return jsonify({'ok': False, 'error': 'device_id já cadastrado'}), 400
        eq.device_id = nova
    if 'online' in data:
        eq.online = bool(data.get('online'))
        if eq.online:
            eq.last_alive = datetime.utcnow()
    if 'ativo' in data:
        eq.ativo = str(data.get('ativo')).lower() not in ('0', 'false', 'off')
    db.session.commit()
    return jsonify({'ok': True, 'equipamento': eq.to_dict()})


# ---- APIs Grupos ----
@acesso.route('/acesso/api/grupos', methods=['GET', 'POST'])
@login_required
def api_grupos():
    seed_acesso()
    if request.method == 'GET':
        out = []
        for g in AcessoGrupo.query.order_by(AcessoGrupo.nome).all():
            d = g.to_dict()
            d['equipamento_ids'] = [e.id for e in g.equipamentos]
            d['horarios'] = [h.to_dict() for h in g.horarios]
            out.append(d)
        return jsonify(out)

    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome é obrigatório'}), 400
    if AcessoGrupo.query.filter_by(nome=nome).first():
        return jsonify({'ok': False, 'error': 'Grupo já existe'}), 400

    grupo = AcessoGrupo(
        nome=nome,
        descricao=(data.get('descricao') or '').strip() or None,
        ativo=True,
    )
    db.session.add(grupo)
    db.session.flush()

    eq_ids = data.get('equipamento_ids') or []
    if isinstance(eq_ids, str):
        eq_ids = [x for x in eq_ids.split(',') if x.strip()]
    for eid in eq_ids:
        eq = AcessoEquipamento.query.get(int(eid))
        if eq:
            grupo.equipamentos.append(eq)

    hi = _parse_time(data.get('hora_inicial')) or time(0, 0)
    hf = _parse_time(data.get('hora_final')) or time(23, 59)
    db.session.add(AcessoHorario(
        grupo_id=grupo.id,
        dia_semana=(data.get('dia_semana') or 'TODOS').strip().upper(),
        hora_inicial=hi,
        hora_final=hf,
    ))
    db.session.commit()
    d = grupo.to_dict()
    d['equipamento_ids'] = [e.id for e in grupo.equipamentos]
    d['horarios'] = [h.to_dict() for h in grupo.horarios]
    return jsonify({'ok': True, 'grupo': d}), 201


@acesso.route('/acesso/api/grupos/<int:gid>', methods=['PUT', 'DELETE'])
@login_required
def api_grupo_item(gid):
    grupo = AcessoGrupo.query.get_or_404(gid)
    if request.method == 'DELETE':
        db.session.delete(grupo)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    if 'nome' in data:
        nome = (data.get('nome') or '').strip()
        if nome:
            grupo.nome = nome
    if 'descricao' in data:
        grupo.descricao = (data.get('descricao') or '').strip() or None
    if 'ativo' in data:
        grupo.ativo = str(data.get('ativo')).lower() not in ('0', 'false', 'off')
    if 'equipamento_ids' in data:
        eq_ids = data.get('equipamento_ids') or []
        grupo.equipamentos = []
        for eid in eq_ids:
            eq = AcessoEquipamento.query.get(int(eid))
            if eq:
                grupo.equipamentos.append(eq)
    db.session.commit()
    d = grupo.to_dict()
    d['equipamento_ids'] = [e.id for e in grupo.equipamentos]
    d['horarios'] = [h.to_dict() for h in grupo.horarios]
    return jsonify({'ok': True, 'grupo': d})


# ---- APIs Visitantes ----
def _apply_visitante_fields(visitante, data, creating=False):
    if 'nome' in data or creating:
        nome = (data.get('nome') or '').strip()
        if not nome:
            raise ValueError('Nome é obrigatório')
        visitante.nome = nome.upper()

    tipo_doc = (data.get('tipo_documento') or data.get('documento_tipo') or '').strip()
    if tipo_doc or creating:
        visitante.tipo_documento = tipo_doc or visitante.tipo_documento or 'CPF'

    doc = (data.get('documento') or '').strip()
    if 'documento' in data or creating:
        visitante.documento = doc or None
        if (visitante.tipo_documento or '').upper() == 'CPF':
            visitante.cpf = doc or None
        elif (visitante.tipo_documento or '').upper() == 'RG':
            visitante.rg = doc or None

    for field in (
        'cpf', 'rg', 'empresa_visitada', 'motivo', 'cartao', 'tipo_cartao',
        'qr_code', 'token', 'foto', 'local_acesso', 'ident_modo',
        'impressora', 'modelo_impressao', 'anfitriao',
    ):
        if field in data:
            val = data.get(field)
            if field == 'foto':
                setattr(visitante, field, val or None)
            else:
                setattr(visitante, field, (str(val).strip() if val is not None else '') or None)

    for field in ('grupo_id', 'empresa_id', 'classificacao_id', 'equipamento_id', 'refeicao_creditos'):
        if field in data:
            setattr(visitante, field, _parse_int(data.get(field)))

    if visitante.empresa_id:
        emp = AcessoEmpresa.query.get(visitante.empresa_id)
        if emp:
            visitante.empresa_visitada = emp.nome

    if 'data_inicial' in data or creating:
        visitante.data_inicial = _parse_date(data.get('data_inicial')) or visitante.data_inicial or date.today()
    if 'hora_inicial' in data or creating:
        visitante.hora_inicial = _parse_time(data.get('hora_inicial')) or visitante.hora_inicial or time(7, 0)
    if 'data_final' in data:
        visitante.data_final = _parse_date(data.get('data_final'))
    elif creating and not visitante.data_final:
        visitante.data_final = visitante.data_inicial
    if 'hora_final' in data or creating:
        visitante.hora_final = _parse_time(data.get('hora_final')) or visitante.hora_final or time(19, 0)

    for flag in (
        'visita_unica', 'refeicao', 'imprimir_ao_salvar', 'baixar_qr_ao_salvar', 'ativo',
    ):
        if flag in data or (creating and flag != 'ativo'):
            if flag == 'ativo' and flag not in data:
                visitante.ativo = True
            else:
                setattr(visitante, flag, _parse_bool(data.get(flag), default=False if flag != 'ativo' else True))


@acesso.route('/acesso/api/visitantes', methods=['GET', 'POST'])
@login_required
def api_visitantes():
    seed_acesso()
    if request.method == 'GET':
        q = (request.args.get('q') or '').strip()
        query = AcessoVisitante.query
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                AcessoVisitante.nome.ilike(like),
                AcessoVisitante.visitor_id.ilike(like),
                AcessoVisitante.cpf.ilike(like),
                AcessoVisitante.documento.ilike(like),
                AcessoVisitante.anfitriao.ilike(like),
            ))
        limit = min(int(request.args.get('limit', 200)), 500)
        rows = query.order_by(AcessoVisitante.id.desc()).limit(limit).all()
        return jsonify({'ok': True, 'visitantes': [v.to_dict() for v in rows]})

    data = request.get_json(silent=True) or request.form.to_dict()
    visitor_id = (data.get('visitor_id') or '').strip()
    if not visitor_id:
        last = db.session.query(func.count(AcessoVisitante.id)).scalar() or 0
        visitor_id = f'V{last + 1:05d}'
    if AcessoVisitante.query.filter_by(visitor_id=visitor_id).first():
        return jsonify({'ok': False, 'error': 'visitor_id já cadastrado'}), 400

    grupo = AcessoGrupo.query.filter_by(nome='Visitantes').first()
    visitante = AcessoVisitante(visitor_id=visitor_id, ativo=True)
    try:
        _apply_visitante_fields(visitante, data, creating=True)
        if not visitante.grupo_id and grupo:
            visitante.grupo_id = grupo.id
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    db.session.add(visitante)
    db.session.commit()
    return jsonify({'ok': True, 'visitante': visitante.to_dict()}), 201


@acesso.route('/acesso/api/visitantes/<int:vid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_visitante_item(vid):
    visitante = AcessoVisitante.query.get_or_404(vid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'visitante': visitante.to_dict()})
    if request.method == 'DELETE':
        db.session.delete(visitante)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    try:
        _apply_visitante_fields(visitante, data, creating=False)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    db.session.commit()
    return jsonify({'ok': True, 'visitante': visitante.to_dict()})


@acesso.route('/acesso/api/visitantes/buscar', methods=['GET'])
@login_required
def api_visitantes_buscar():
    """Busca por documento ou nome (reutiliza cadastro existente)."""
    seed_acesso()
    doc = (request.args.get('documento') or request.args.get('doc') or '').strip()
    nome = (request.args.get('nome') or request.args.get('q') or '').strip()
    query = AcessoVisitante.query
    if doc:
        digits = ''.join(ch for ch in doc if ch.isalnum())
        query = query.filter(or_(
            AcessoVisitante.documento == doc,
            AcessoVisitante.cpf == doc,
            AcessoVisitante.rg == doc,
            AcessoVisitante.documento.ilike(f'%{digits}%'),
            AcessoVisitante.cpf.ilike(f'%{digits}%'),
        ))
    elif nome:
        query = query.filter(AcessoVisitante.nome.ilike(f'%{nome}%'))
    else:
        return jsonify({'ok': False, 'error': 'Informe documento ou nome'}), 400
    rows = query.order_by(AcessoVisitante.data_criacao.desc()).limit(30).all()
    return jsonify({'ok': True, 'visitantes': [v.to_dict() for v in rows]})


@acesso.route('/acesso/api/visitantes/anfitrioes', methods=['GET'])
@login_required
def api_visitantes_anfitrioes():
    """Autocomplete de anfitrião a partir de colaboradores."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'ok': True, 'itens': []})
    like = f'%{q}%'
    pessoas = AcessoPessoa.query.filter(
        or_(AcessoPessoa.nome.ilike(like), AcessoPessoa.matricula.ilike(like))
    ).order_by(AcessoPessoa.nome).limit(15).all()
    return jsonify({
        'ok': True,
        'itens': [{
            'id': p.id,
            'nome': p.nome,
            'matricula': p.matricula,
            'documento': p.documento or '',
        } for p in pessoas],
    })


@acesso.route('/acesso/api/tipos-documento', methods=['GET', 'POST'])
@login_required
def api_tipos_documento():
    seed_acesso()
    if request.method == 'GET':
        rows = AcessoTipoDocumento.query.order_by(AcessoTipoDocumento.descricao).all()
        return jsonify({'ok': True, 'tipos': [t.to_dict() for t in rows]})

    data = request.get_json(silent=True) or {}
    desc = (data.get('descricao') or '').strip().upper()
    if not desc:
        return jsonify({'ok': False, 'error': 'Descrição obrigatória'}), 400
    if AcessoTipoDocumento.query.filter_by(descricao=desc).first():
        return jsonify({'ok': False, 'error': 'Tipo já existe'}), 400
    tipo = AcessoTipoDocumento(descricao=desc, digitos=_parse_int(data.get('digitos')) or 0)
    db.session.add(tipo)
    db.session.commit()
    return jsonify({'ok': True, 'tipo': tipo.to_dict()}), 201


@acesso.route('/acesso/api/tipos-documento/<int:tid>', methods=['PUT', 'DELETE'])
@login_required
def api_tipos_documento_item(tid):
    tipo = AcessoTipoDocumento.query.get_or_404(tid)
    if request.method == 'DELETE':
        db.session.delete(tipo)
        db.session.commit()
        return jsonify({'ok': True})
    data = request.get_json(silent=True) or {}
    if 'descricao' in data:
        desc = (data.get('descricao') or '').strip().upper()
        if not desc:
            return jsonify({'ok': False, 'error': 'Descrição obrigatória'}), 400
        tipo.descricao = desc
    if 'digitos' in data:
        tipo.digitos = _parse_int(data.get('digitos')) or 0
    db.session.commit()
    return jsonify({'ok': True, 'tipo': tipo.to_dict()})


# ---- APIs Eventos ----
@acesso.route('/acesso/api/eventos', methods=['GET', 'POST'])
@login_required
def api_eventos():
    seed_acesso()
    if request.method == 'GET':
        limit = min(int(request.args.get('limit', 100)), 500)
        eventos = AcessoEvento.query.order_by(AcessoEvento.data_hora.desc()).limit(limit).all()
        return jsonify([e.to_dict() for e in eventos])

    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Nome é obrigatório'}), 400

    eq = None
    if data.get('equipamento_id'):
        eq = AcessoEquipamento.query.get(int(data['equipamento_id']))

    evento = AcessoEvento(
        pessoa_ref=(data.get('pessoa_ref') or '').strip() or None,
        nome=nome,
        tipo_pessoa=(data.get('tipo_pessoa') or 'PESSOA').strip().upper(),
        status=(data.get('status') or 'Liberado').strip(),
        direction=(data.get('direction') or '').strip() or None,
        event_type=(data.get('event_type') or 'manual').strip(),
        equipamento_id=eq.id if eq else None,
        equipamento_nome=eq.nome if eq else (data.get('equipamento_nome') or '').strip() or None,
        cartao=(data.get('cartao') or '').strip() or None,
        girou=(data.get('girou') or '').strip() or None,
        motivo=(data.get('motivo') or '').strip() or None,
        data_hora=datetime.utcnow(),
    )
    db.session.add(evento)
    db.session.commit()
    return jsonify({'ok': True, 'evento': evento.to_dict()}), 201
