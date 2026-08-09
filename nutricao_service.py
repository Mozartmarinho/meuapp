"""Seed inicial e helpers do módulo de nutrição."""
from datetime import date, datetime
from models import db
from models_nutricao import (
    NutClinica, NutEnfermaria, NutLeito, NutDieta, NutPaciente, NutMapaRefeicao, NutCardapio,
    NutTabelaNutrientes, NutAlimento, NutAlimentoNutriente, NutPratoLiquido,
    NutEstoqueLocal, NutUnidadeMedida, NutGrupoProduto, NutProduto, NutFornecedor,
    NutEtiqueta, NutEtiquetaCampo,
)
from nutricao_seed_enfermarias import ENFERMARIAS_SEED, VINCULOS_CLINICA_ENFERMARIA_SEED
from nutricao_seed_dietas import DIETAS_SEED
from nutricao_seed_cardapios import CARDAPIOS_SEED, CARDAPIO_OPCOES
from nutricao_seed_nutricional import ALIMENTOS_SEED, NUTRIENTES_PADRAO
from nutricao_seed_pratos_liquidos import PRATOS_LIQUIDOS_SEED
from nutricao_seed_produtos import (
    ESTOQUES_SEED, UNIDADES_SEED, GRUPOS_PRODUTO_SEED, PRODUTOS_SEED,
)
from nutricao_seed_fornecedores import FORNECEDORES_SEED, ESTADOS_BR
from nutricao_seed_etiquetas import ETIQUETAS_SEED


# Cadastro de Clínicas (legado "Grupo") — nome, ativo
CLINICAS_SEED = [
    ('3º CM + VASCULAR', True),
    ('4º/5º MATERNIDADE', False),
    ('BRONCO OFTALMO', False),
    ('CABEÇA E PESCOÇO', True),
    ('CARDIO', False),
    ('CARDIO + UC', True),
    ('CARDIOLOGIA', True),
    ('CETIP + CIPE + PEDIATRIA', True),
    ('CIR. A1', False),
    ('CIR. A2', False),
    ('CIRURGIA A1', False),
    ('CIRURGIA A2', False),
    ('CIRURGIA B + NEURO', False),
    ('CIRURGIA G. A', False),
    ('CIRURGIA GERAL A', True),
    ('CIRURGIA GERAL B', True),
    ('CIRURGIA PEDIATRICA', False),
    ('CLÍNICA MÉDICA A', True),
    ('CLÍNICA MÉDICA B', True),
    ('CLÍNICA MÉDICA C', True),
    ('CRECHE', False),
    ('CTI - 1', True),
    ('CTI - 2', True),
    ('CTI + ORTO + VASC', False),
    ('CTI 1 + CTI 2 (FATURAMENTO)', True),
    ('CTI PED (PRÉDIO 1)', False),
    ('CTI PEDIÁTRICO', False),
    ('CTI TOTALIZAÇÃO', False),
    ('CTI2', False),
    ('DP + UTR', True),
    ('EMERG. (FATURAMENTO)', True),
    ('EMERGÊNCIA (MASC. E FEM.)', True),
    ('EMERGÊNCIA 1', False),
    ('EMERGÊNCIA 2', True),
    ('EMERGÊNCIA CORREDOR', True),
    ('EMERGÊNCIA CURTA PERMANÊNCIA', True),
    ('EMERGÊNCIA MASCULINA', False),
    ('ENTERAL', False),
    ('ENTERAL A', False),
    ('ENTERAL B', False),
    ('GINECO', True),
    ('HEMODIÁLISE', False),
    ('HOSPITAL DIA', True),
    ('MATERNIDADE', False),
    ('MATERNIDADE A', False),
    ('MATERNIDADE ALA A', True),
    ('MATERNIDADE ALA A + B', True),
    ('MATERNIDADE ALA B', False),
    ('MATERNIDADE B', True),
    ('MATERNIDADE LACTÁRIO', False),
    ('MATERNIDADE/SALA DE PARTO', False),
    ('NEFRO', True),
    ('NEFRO + UTR + DP', True),
    ('NEFRO+DP+UTR+CTI (FATURAMENTO)', False),
    ('NEURO', True),
    ('OFTALMO + OTORRINO + PLÁSTICA', True),
    ('OFTALMO+OTORRINO+PLÁSTICA', True),
    ('ONCO', True),
    ('ORTOPEDIA', True),
    ('OTORRINO', False),
    ('PED + CTI PED', True),
    ('PEDIATRIA + CIR. INFANTIL', False),
    ('PEDIATRIA ALA B', False),
    ('PEDIATRIA C/ CIRURGIA', False),
    ('PEDIATRIA S/ CIRURGIA', False),
    ('PÓS OP.', False),
    ('PU', False),
    ('PU (T.C.)', False),
    ('PU PED (T.C.)', False),
    ('PU PED-UPG', False),
    ('SALA DE ESTABILIZAÇÃO', True),
    ('SALA DE RECUPERAÇÃO ANESTÉSICA', True),
    ('TESTE', False),
    ('TODOS', True),
    ('UCO', True),
    ('UI NEO', True),
    ('UROLOGIA', True),
    ('USE', True),
    ('USE (FEM E MASC)', False),
    ('USE (TOT)', False),
    ('UTI NEO NATAL', True),
    ('UTO + UC', False),
    ('VASCULAR', True),
    ('VASCULAR + ONCO', False),
]


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return None


def list_dietas(somente_ativas=False):
    q = NutDieta.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [d.to_dict() for d in q.order_by(NutDieta.nome).all()]


def list_clinicas(somente_ativas=False):
    q = NutClinica.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [c.to_dict() for c in q.order_by(NutClinica.nome).all()]


def list_enfermarias(somente_ativas=False):
    from sqlalchemy import func
    q = NutEnfermaria.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    rows = q.order_by(NutEnfermaria.nome).all()
    counts = dict(
        db.session.query(NutLeito.enfermaria_id, func.count(NutLeito.id))
        .group_by(NutLeito.enfermaria_id)
        .all()
    )
    return [e.to_dict(num_leitos=counts.get(e.id, 0)) for e in rows]


def list_leitos(enfermaria_id=None, somente_ativos=False):
    q = NutLeito.query
    if enfermaria_id:
        q = q.filter_by(enfermaria_id=enfermaria_id)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [l.to_dict() for l in q.order_by(NutLeito.numero, NutLeito.nome).all()]


def _ensure_nutricao_columns():
    """Adiciona colunas novas em tabelas já existentes (create_all não altera)."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'nut_enfermarias' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_enfermarias')}
            if 'nutriz' not in cols:
                db.session.execute(text('ALTER TABLE nut_enfermarias ADD COLUMN nutriz BOOLEAN DEFAULT 0'))
                db.session.commit()
        if 'nut_mapa_refeicoes' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_mapa_refeicoes')}
            alteracoes = {
                'obs_etiqueta': 'TEXT',
                'extras': 'TEXT',
                'suplementos': 'TEXT',
                'enteral': 'TEXT',
                'formula_infantil': 'TEXT',
                'lve': 'TEXT',
                'data_inclusao': 'DATETIME',
                'enfermaria': 'VARCHAR(120)',
                'usuario_alteracao': 'VARCHAR(80)',
                'motivo_saida': 'VARCHAR(40)',
            }
            for col, tipo in alteracoes.items():
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE nut_mapa_refeicoes ADD COLUMN {col} {tipo}'))
            db.session.commit()
        if 'nut_pacientes' in tables:
            cols = {c['name'] for c in insp.get_columns('nut_pacientes')}
            if 'hora_saida' not in cols:
                db.session.execute(text("ALTER TABLE nut_pacientes ADD COLUMN hora_saida VARCHAR(20)"))
            if 'motivo_saida' not in cols:
                db.session.execute(text("ALTER TABLE nut_pacientes ADD COLUMN motivo_saida VARCHAR(40)"))
            db.session.commit()
    except Exception:
        db.session.rollback()


def _seed_enfermarias():
    for nome in ENFERMARIAS_SEED:
        nome = (nome or '').strip()
        if not nome:
            continue
        if not NutEnfermaria.query.filter_by(nome=nome).first():
            db.session.add(NutEnfermaria(nome=nome, ativo=True, nutriz=False))
    db.session.flush()

    # vínculos iniciais só se a clínica ainda não tiver nenhuma enfermaria
    for clinica_nome, nomes in VINCULOS_CLINICA_ENFERMARIA_SEED.items():
        clinica = NutClinica.query.filter_by(nome=clinica_nome).first()
        if not clinica:
            continue
        if clinica.enfermarias:
            continue
        for nome_enf in nomes:
            enf = NutEnfermaria.query.filter_by(nome=nome_enf).first()
            if enf and enf not in clinica.enfermarias:
                clinica.enfermarias.append(enf)


def list_cardapios(tipo=None):
    q = NutCardapio.query.filter_by(ativo=True)
    if tipo:
        q = q.filter_by(tipo=tipo)
    return [
        c.to_dict()
        for c in q.order_by(NutCardapio.dia_mes, NutCardapio.dieta, NutCardapio.id).all()
    ]


def _seed_cardapios():
    if NutCardapio.query.count() > 0:
        return
    for item in CARDAPIOS_SEED:
        row = NutCardapio(
            tipo=item['tipo'],
            grupo_cardapio=item.get('grupo_cardapio', 'PRINCIPAL'),
            dia_mes=item.get('dia_mes', 1),
            dia_semana=item.get('dia_semana', ''),
            dieta=item.get('dieta', ''),
            hr_desjejum=bool(item.get('hr_desjejum')),
            hr_colacao=bool(item.get('hr_colacao')),
            hr_almoco=bool(item.get('hr_almoco')),
            hr_merenda=bool(item.get('hr_merenda')),
            hr_jantar=bool(item.get('hr_jantar')),
            hr_ceia=bool(item.get('hr_ceia')),
            vet=float(item.get('vet') or 0),
            custo=float(item.get('custo') or 0),
            organizar_por=item.get('organizar_por', 'Dia;Dieta;Horário'),
            usuario_alteracao=item.get('usuario_alteracao', 'sistema'),
            data_alteracao=datetime(2026, 1, 5, 11, 43, 16),
            ativo=True,
        )
        row.set_itens(item.get('itens') or {})
        db.session.add(row)


def list_tabelas_nutrientes(somente_ativas=True):
    q = NutTabelaNutrientes.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [t.to_dict() for t in q.order_by(NutTabelaNutrientes.nome).all()]


def list_alimentos(tabela_id=None, somente_ativas=True):
    q = NutAlimento.query
    if tabela_id:
        q = q.filter_by(tabela_id=tabela_id)
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [
        a.to_dict()
        for a in q.order_by(NutAlimento.nome, NutAlimento.id).all()
    ]


def _seed_nutricional():
    if NutTabelaNutrientes.query.count() > 0:
        return
    tabelas = {}
    for item in ALIMENTOS_SEED:
        nome_tab = (item.get('tabela') or 'Tabela Padrão').strip()
        if nome_tab not in tabelas:
            tab = NutTabelaNutrientes(nome=nome_tab, ativo=True)
            db.session.add(tab)
            db.session.flush()
            tabelas[nome_tab] = tab
        tab = tabelas[nome_tab]
        alim = NutAlimento(
            tabela_id=tab.id,
            nome=(item.get('nome') or '').strip().upper(),
            cal_carboidratos=float(item.get('cal_carboidratos') or 0),
            cal_gordura=float(item.get('cal_gordura') or 0),
            cal_proteina=float(item.get('cal_proteina') or 0),
            cal_total=float(item.get('cal_total') or 0),
            qtd_carboidratos=float(item.get('qtd_carboidratos') or 0),
            qtd_gordura=float(item.get('qtd_gordura') or 0),
            qtd_proteina=float(item.get('qtd_proteina') or 0),
            ref_consumo=item.get('ref_consumo') or '',
            coeficiente_npu=float(item.get('coeficiente_npu') or 0),
            gluten=bool(item.get('gluten')),
            fenilalanina=bool(item.get('fenilalanina')),
            ativo=True,
        )
        db.session.add(alim)
        db.session.flush()
        nuts = item.get('nutrientes') or []
        if not nuts:
            nuts = [(n, 0, u, f) for n, u, f in NUTRIENTES_PADRAO]
        for nome_n, qtd, un, fator in nuts:
            db.session.add(NutAlimentoNutriente(
                alimento_id=alim.id,
                nutriente=nome_n,
                quantidade=float(qtd or 0),
                unidade=un or 'g',
                fator=float(fator or 1),
            ))


def list_pratos_liquidos(somente_ativos=True):
    q = NutPratoLiquido.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [p.to_dict() for p in q.order_by(NutPratoLiquido.nome, NutPratoLiquido.id).all()]


def _seed_pratos_liquidos():
    if NutPratoLiquido.query.count() > 0:
        return
    for (
        nome, principal, sobremesa, outros, bebida, gelado, extra, fator, ativo
    ) in PRATOS_LIQUIDOS_SEED:
        db.session.add(NutPratoLiquido(
            nome=(nome or '').strip().upper(),
            grupo_principal=bool(principal),
            grupo_sobremesa=bool(sobremesa),
            grupo_outros=bool(outros),
            grupo_bebida=bool(bebida),
            grupo_gelado=bool(gelado),
            grupo_extra=bool(extra),
            fator_conv_tot=float(fator or 1),
            ativo=bool(ativo),
        ))


def list_estoques(somente_ativos=True):
    q = NutEstoqueLocal.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [e.to_dict() for e in q.order_by(NutEstoqueLocal.nome).all()]


def list_unidades(somente_ativas=True):
    q = NutUnidadeMedida.query
    if somente_ativas:
        q = q.filter_by(ativo=True)
    return [u.to_dict() for u in q.order_by(NutUnidadeMedida.codigo).all()]


def list_grupos_produto(somente_ativos=True):
    q = NutGrupoProduto.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [g.to_dict() for g in q.order_by(NutGrupoProduto.nome).all()]


def list_produtos(estoque_id=None, grupo_id=None, somente_ativos=True):
    q = NutProduto.query
    if estoque_id:
        q = q.filter_by(estoque_id=estoque_id)
    if grupo_id:
        q = q.filter_by(grupo_id=grupo_id)
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [
        p.to_dict()
        for p in q.order_by(NutProduto.codigo, NutProduto.id).all()
    ]


def _seed_produtos():
    for nome in ESTOQUES_SEED:
        if not NutEstoqueLocal.query.filter_by(nome=nome).first():
            db.session.add(NutEstoqueLocal(nome=nome, ativo=True))
    for codigo, desc in UNIDADES_SEED:
        if not NutUnidadeMedida.query.filter_by(codigo=codigo).first():
            db.session.add(NutUnidadeMedida(codigo=codigo, descricao=desc, ativo=True))
    for nome in GRUPOS_PRODUTO_SEED:
        if not NutGrupoProduto.query.filter_by(nome=nome).first():
            db.session.add(NutGrupoProduto(nome=nome, ativo=True))
    db.session.flush()

    if NutProduto.query.count() > 0:
        return
    for (
        estoque_nome, grupo_nome, codigo, descricao, qtd, un,
        preco_med, ult_preco, qmin, qmax, qliq, un_liq, fc
    ) in PRODUTOS_SEED:
        est = NutEstoqueLocal.query.filter_by(nome=estoque_nome).first()
        grp = NutGrupoProduto.query.filter_by(nome=grupo_nome).first()
        if not est or not grp:
            continue
        db.session.add(NutProduto(
            estoque_id=est.id,
            grupo_id=grp.id,
            codigo=(codigo or '').strip().upper(),
            descricao=(descricao or '').strip().upper(),
            quantidade=float(qtd or 0),
            unidade=(un or 'UN').strip().upper(),
            preco_medio=float(preco_med or 0),
            ult_preco=float(ult_preco or 0),
            quant_min=float(qmin or 0),
            quant_max=float(qmax or 0),
            quant_liq=float(qliq or 0),
            un_liq=(un_liq or 'NC').strip().upper(),
            fc=bool(fc),
            ativo=True,
        ))


def list_fornecedores(somente_ativos=True):
    q = NutFornecedor.query
    if somente_ativos:
        q = q.filter_by(ativo=True)
    return [f.to_dict() for f in q.order_by(NutFornecedor.nome, NutFornecedor.id).all()]


def _seed_fornecedores():
    if NutFornecedor.query.count() > 0:
        return
    for item in FORNECEDORES_SEED:
        db.session.add(NutFornecedor(
            nome=(item.get('nome') or '').strip().upper(),
            endereco=(item.get('endereco') or '').strip().upper() or None,
            bairro=(item.get('bairro') or '').strip().upper() or None,
            municipio=(item.get('municipio') or '').strip().upper() or None,
            cep=(item.get('cep') or '').strip() or None,
            estado=(item.get('estado') or '').strip().upper() or None,
            cnpj=(item.get('cnpj') or '').strip() or None,
            inscricao_estadual=(item.get('inscricao_estadual') or '').strip() or None,
            telefone=(item.get('telefone') or '').strip() or None,
            email=(item.get('email') or '').strip() or None,
            faturamento_dias=int(item.get('faturamento_dias') or 0),
            site=(item.get('site') or '').strip() or None,
            observacao=(item.get('observacao') or '').strip() or None,
            ativo=True,
        ))


def list_etiquetas(somente_ativas=False):
    q = NutEtiqueta.query
    if somente_ativas:
        q = q.filter_by(ativa=True)
    return [e.to_dict() for e in q.order_by(NutEtiqueta.nome, NutEtiqueta.id).all()]


def _seed_etiquetas():
    if NutEtiqueta.query.count() > 0:
        return
    for item in ETIQUETAS_SEED:
        row = NutEtiqueta(
            nome=(item.get('nome') or '').strip(),
            ativa=bool(item.get('ativa', True)),
            tamanho_folha=(item.get('tamanho_folha') or 'carta').strip().lower(),
            folha_altura_mm=float(item.get('folha_altura_mm') or 0),
            folha_largura_mm=float(item.get('folha_largura_mm') or 0),
            orientacao=(item.get('orientacao') or 'retrato').strip().lower(),
            margem_esquerda=float(item.get('margem_esquerda') or 0),
            margem_direita=float(item.get('margem_direita') or 0),
            margem_superior=float(item.get('margem_superior') or 0),
            margem_inferior=float(item.get('margem_inferior') or 0),
            num_colunas=int(item.get('num_colunas') or 1),
            dist_colunas_mm=float(item.get('dist_colunas_mm') or 0),
            altura_etiqueta_mm=float(item.get('altura_etiqueta_mm') or 0),
            tamanho_fonte=int(item.get('tamanho_fonte') or 7),
        )
        db.session.add(row)
        db.session.flush()
        for c in (item.get('campos') or []):
            db.session.add(NutEtiquetaCampo(
                etiqueta_id=row.id,
                tipo=((c.get('tipo') or 'D').strip().upper()[:1] or 'D'),
                nome=(c.get('nome') or '').strip().upper(),
                texto=(c.get('texto') or '').strip() or None,
            ))


def seed_nutricao():
    """Garante cadastros básicos de clínicas e dietas."""
    _ensure_nutricao_columns()
    for nome, ativo in CLINICAS_SEED:
        if not NutClinica.query.filter_by(nome=nome).first():
            db.session.add(NutClinica(nome=nome, ativo=bool(ativo)))

    for nome, cat, ativo in DIETAS_SEED:
        if not NutDieta.query.filter_by(nome=nome).first():
            db.session.add(NutDieta(nome=nome, categoria=cat, ativo=bool(ativo)))

    db.session.flush()
    _seed_enfermarias()
    _seed_cardapios()
    _seed_nutricional()
    _seed_pratos_liquidos()
    _seed_produtos()
    _seed_fornecedores()
    _seed_etiquetas()

    if NutPaciente.query.count() == 0:
        exemplos = [
            NutPaciente(
                nome='Maria Silva', sexo='F', nascimento=_parse_date('1985-03-15'),
                prontuario='12345', clinica='CLÍNICA MÉDICA A', leito='101-A',
                dieta='BRANDA COM SAL', diagnostico='HAS', admissao=date.today(),
                altura_cm=165, peso_kg=72, ativo=True,
            ),
            NutPaciente(
                nome='João Santos', sexo='M', nascimento=_parse_date('1972-08-22'),
                prontuario='12346', clinica='CTI - 1', leito='05',
                dieta='PASTOSA COM SAL', diagnostico='Pós-operatório', admissao=date.today(),
                altura_cm=175, peso_kg=80, ativo=True,
            ),
            NutPaciente(
                nome='Ana Oliveira', sexo='F', nascimento=_parse_date('1990-12-01'),
                prontuario='12347', clinica='ONCO', leito='210-B',
                dieta='LIQUIDA SEM SAL', diagnostico='Em tratamento', admissao=date.today(),
                altura_cm=160, peso_kg=58, ativo=True,
            ),
        ]
        for p in exemplos:
            db.session.add(p)

    db.session.commit()


def paciente_from_payload(d, paciente=None):
    paciente = paciente or NutPaciente()
    paciente.nome = (d.get('nome') or '').strip()
    paciente.sexo = (d.get('sexo') or '').strip()[:1] or None
    paciente.nascimento = _parse_date(d.get('nascimento'))
    paciente.prontuario = (d.get('prontuario') or '').strip() or None
    paciente.clinica = (d.get('clinica') or '').strip() or None
    paciente.leito = (d.get('leito') or '').strip() or None
    paciente.dieta = (d.get('dieta') or '').strip() or None
    paciente.diagnostico = (d.get('diagnostico') or '').strip() or None
    paciente.observacoes = (d.get('observacoes') or '').strip() or None
    paciente.admissao = _parse_date(d.get('admissao'))
    paciente.data_saida = _parse_date(d.get('data_saida'))
    try:
        paciente.altura_cm = float(d['altura_cm']) if d.get('altura_cm') not in (None, '') else None
    except (TypeError, ValueError):
        paciente.altura_cm = None
    try:
        paciente.peso_kg = float(d['peso_kg']) if d.get('peso_kg') not in (None, '') else None
    except (TypeError, ValueError):
        paciente.peso_kg = None
    if 'ativo' in d:
        paciente.ativo = bool(d.get('ativo'))
    return paciente


def mapa_from_paciente(paciente, data_ref=None, flags=None, extras=None, usuario=None):
    data_ref = data_ref or date.today()
    flags = flags or {}
    extras = extras or {}
    agora = datetime.utcnow()
    return NutMapaRefeicao(
        data_refeicao=data_ref,
        paciente_id=paciente.id,
        adm=extras.get('adm', paciente.admissao),
        leito=(extras.get('leito') if 'leito' in extras else paciente.leito),
        prontuario=(extras.get('prontuario') if 'prontuario' in extras else paciente.prontuario),
        nome=paciente.nome,
        idade=paciente.idade(data_ref),
        diagnostico=(extras.get('diagnostico') if 'diagnostico' in extras else paciente.diagnostico),
        dieta=(extras.get('dieta') if 'dieta' in extras else paciente.dieta),
        observacoes=(extras.get('observacoes') if 'observacoes' in extras else paciente.observacoes),
        clinica=(extras.get('clinica') if 'clinica' in extras else paciente.clinica),
        enfermaria=(extras.get('enfermaria') or None),
        fl_desjejum=bool(flags.get('fl_desjejum', True)),
        fl_colacao=bool(flags.get('fl_colacao', True)),
        fl_almoco=bool(flags.get('fl_almoco', True)),
        fl_merenda=bool(flags.get('fl_merenda', True)),
        fl_jantar=bool(flags.get('fl_jantar', True)),
        fl_ceia=bool(flags.get('fl_ceia', True)),
        obs_etiqueta=(extras.get('obs_etiqueta') or None),
        extras=(extras.get('extras') or None),
        suplementos=(extras.get('suplementos') or None),
        enteral=(extras.get('enteral') or None),
        formula_infantil=(extras.get('formula_infantil') or None),
        lve=(extras.get('lve') or None),
        data_inclusao=agora,
        usuario_alteracao=(usuario or 'sistema')[:80],
        data_atualizacao=agora,
        data_saida=paciente.data_saida,
        ativo=True,
    )


def garantir_mapa_do_dia(data_ref=None):
    """Compatibilidade: inclusão no mapa é manual via Inserir paciente."""
    return 0


def marcar_alteracao_mapa(row, usuario=None):
    row.usuario_alteracao = (usuario or 'sistema')[:80]
    row.data_atualizacao = datetime.utcnow()
    return row


def listar_avisos_alta_mapa(data_ref=None):
    """Pacientes com alta anteriores à data do mapa, ainda presentes nas linhas ativas."""
    data_ref = data_ref or date.today()
    garantir_mapa_do_dia(data_ref)
    rows = (
        NutMapaRefeicao.query
        .filter_by(data_refeicao=data_ref, ativo=True)
        .order_by(NutMapaRefeicao.clinica, NutMapaRefeicao.leito, NutMapaRefeicao.nome)
        .all()
    )
    avisos = []
    for r in rows:
        pac = r.paciente
        saida = None
        hora = '00:00:00'
        motivo = 'A'
        if pac and pac.data_saida:
            saida = pac.data_saida
            hora = (pac.hora_saida or '14:00:00').strip() or '14:00:00'
            motivo = (pac.motivo_saida or 'A').strip() or 'A'
        elif r.data_saida:
            saida = r.data_saida
        if not saida:
            continue
        # alta em data anterior à do mapa → não deveria permanecer
        if saida >= data_ref:
            continue
        avisos.append({
            'mapa_id': r.id,
            'paciente_id': r.paciente_id,
            'clinica': r.clinica or (pac.clinica if pac else '') or '',
            'leito': r.leito or (pac.leito if pac else '') or '',
            'nome': r.nome or (pac.nome if pac else '') or '',
            'data_saida': saida.isoformat(),
            'saida': hora,
            'motivo': motivo,
            'excluir': True,
        })
    return avisos


def aplicar_avisos_alta_mapa(mapa_ids_excluir):
    """Desativa linhas do mapa marcadas para exclusão no aviso de alta."""
    ids = []
    for x in (mapa_ids_excluir or []):
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    if not ids:
        return 0
    qtd = 0
    for mid in ids:
        row = NutMapaRefeicao.query.get(mid)
        if not row or not row.ativo:
            continue
        row.ativo = False
        qtd += 1
    if qtd:
        db.session.commit()
    return qtd


CAMPO_UMA = {
    'enteral': 'enteral',
    'suplementos': 'suplementos',
    'formula_infantil': 'formula_infantil',
    'lve': 'lve',
}


def totalizar_mapa_uma(data_ref, categoria='enteral', imprimir_por='clinica', filtro_id=None, filtro_nome=None, horarios=None, amostra=None):
    """Agrega itens do mapa (enteral/suplementos/fórmula/LVE) para impressão U.M.A."""
    from collections import defaultdict

    data_ref = data_ref or date.today()
    garantir_mapa_do_dia(data_ref)
    campo = CAMPO_UMA.get(categoria, 'enteral')

    q = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True)
    linhas = q.order_by(NutMapaRefeicao.clinica, NutMapaRefeicao.leito, NutMapaRefeicao.nome).all()

    # filtro por clínica / grupo (mesmo cadastro NutClinica) ou enfermaria
    filtro_nome = (filtro_nome or '').strip()
    if imprimir_por in ('grupo_clinica', 'clinica') and filtro_nome:
        linhas = [l for l in linhas if (l.clinica or '').strip().upper() == filtro_nome.upper()]
    elif imprimir_por == 'enfermaria' and filtro_id:
        enf = NutEnfermaria.query.get(int(filtro_id))
        if enf:
            leitos = { (lt.numero_leito or '').strip().upper() for lt in (enf.leitos or []) }
            # também aceita match por nome da enfermaria na clínica do mapa
            nome_enf = (enf.nome or '').upper()
            filtradas = []
            for l in linhas:
                leito = (l.leito or '').strip().upper()
                clinica = (l.clinica or '').strip().upper()
                if leito in leitos or nome_enf in clinica or clinica == nome_enf:
                    filtradas.append(l)
            linhas = filtradas

    totais = defaultdict(lambda: {'item': '', 'qtd_pacientes': 0, 'leitos': [], 'pacientes': []})
    detalhe = []
    for l in linhas:
        texto = (getattr(l, campo, None) or '').strip()
        if not texto:
            continue
        # cada linha de texto pode ter múltiplos itens separados por ; ou quebra
        partes = [p.strip() for p in texto.replace('\n', ';').split(';') if p.strip()]
        for item in partes:
            key = item.upper()
            totais[key]['item'] = item
            totais[key]['qtd_pacientes'] += 1
            if l.leito:
                totais[key]['leitos'].append(l.leito)
            if l.nome:
                totais[key]['pacientes'].append(l.nome)
            detalhe.append({
                'item': item,
                'paciente': l.nome or '',
                'leito': l.leito or '',
                'prontuario': l.prontuario or '',
                'clinica': l.clinica or '',
                'dieta': l.dieta or '',
            })

    itens = sorted(totais.values(), key=lambda x: x['item'].upper())
    if amostra is not None:
        try:
            val = float(amostra)
        except (TypeError, ValueError):
            val = 0
        itens.append({
            'item': f'AMOSTRA ({val:g})',
            'qtd_pacientes': 1,
            'leitos': ['—'],
            'pacientes': ['AMOSTRA'],
            'amostra': True,
            'valor_amostra': val,
        })

    labels = {
        'enteral': 'Enteral',
        'suplementos': 'Suplementos',
        'formula_infantil': 'Fórm. Infantis',
        'lve': 'LVE',
    }
    return {
        'data': data_ref.isoformat(),
        'data_label': data_ref.strftime('%d/%m/%Y'),
        'categoria': categoria,
        'categoria_label': labels.get(categoria, categoria),
        'imprimir_por': imprimir_por,
        'filtro_nome': filtro_nome or 'TODOS',
        'horarios': sorted(set(int(h) for h in (horarios or []) if str(h).isdigit())),
        'itens': itens,
        'detalhe': detalhe,
        'total_linhas': len(detalhe),
        'total_itens': len([i for i in itens if not i.get('amostra')]),
    }


REFEICAO_FLAGS = (
    ('desjejum', 'fl_desjejum'),
    ('colacao', 'fl_colacao'),
    ('almoco', 'fl_almoco'),
    ('merenda', 'fl_merenda'),
    ('jantar', 'fl_jantar'),
    ('ceia', 'fl_ceia'),
)

CATEGORIAS_FAT = ('basicas', 'liquidas', 'di', 'acomp')


def _classificar_dieta_faturamento(linha, dieta_cat_map=None):
    """Classifica linha do mapa em BÁSICAS / LÍQUIDAS / D.I. / ACOMP."""
    dieta = (linha.dieta or '').strip().upper()
    cat = (dieta_cat_map or {}).get(dieta, '')
    if 'ACOMP' in dieta or 'ACOMPANHANTE' in dieta:
        return 'acomp'
    if 'LIQUIDA' in dieta:
        return 'liquidas'
    if cat in ('enteral', 'formula', 'lve'):
        return 'di'
    if (linha.enteral or '').strip() or (linha.formula_infantil or '').strip():
        return 'di'
    return 'basicas'


def _zero_matriz():
    return {cat: {ref: 0 for ref, _ in REFEICAO_FLAGS} for cat in CATEGORIAS_FAT}


def relatorio_faturamento(data_de, data_ate, tipo='espelho_1', por_grupo_clinica=False, sintetico=False):
    """Gera espelho/totais de faturamento a partir do mapa de refeições."""
    from collections import defaultdict

    data_de = data_de or date.today()
    data_ate = data_ate or data_de
    if data_ate < data_de:
        data_de, data_ate = data_ate, data_de

    # garante mapa no intervalo (até 31 dias para não pesar)
    cur = data_de
    dias = 0
    while cur <= data_ate and dias < 62:
        garantir_mapa_do_dia(cur)
        cur = date.fromordinal(cur.toordinal() + 1)
        dias += 1

    dieta_cat_map = {
        (d.nome or '').strip().upper(): (d.categoria or 'basica')
        for d in NutDieta.query.all()
    }

    linhas = (
        NutMapaRefeicao.query
        .filter(
            NutMapaRefeicao.data_refeicao >= data_de,
            NutMapaRefeicao.data_refeicao <= data_ate,
            NutMapaRefeicao.ativo.is_(True),
        )
        .order_by(NutMapaRefeicao.data_refeicao, NutMapaRefeicao.clinica, NutMapaRefeicao.leito)
        .all()
    )

    # clinica -> data -> matriz
    blocos = defaultdict(lambda: defaultdict(_zero_matriz))
    totais_gerais = _zero_matriz()
    formulas = defaultdict(lambda: {'item': '', 'qtd': 0})
    complementares = defaultdict(lambda: {'item': '', 'qtd': 0})

    for l in linhas:
        clinica = (l.clinica or 'SEM CLÍNICA').strip() or 'SEM CLÍNICA'
        data_key = l.data_refeicao.isoformat() if l.data_refeicao else data_de.isoformat()
        cat = _classificar_dieta_faturamento(l, dieta_cat_map)

        for ref_key, flag in REFEICAO_FLAGS:
            if getattr(l, flag, False):
                # tipos de relatório de fórmulas/complementares não usam flags da mesma forma
                if tipo in ('total_formulas',):
                    continue
                if tipo == 'total_complementares':
                    continue
                blocos[clinica][data_key][cat][ref_key] += 1
                totais_gerais[cat][ref_key] += 1

        # fórmulas infantis e enterais
        for campo in ('enteral', 'formula_infantil'):
            texto = (getattr(l, campo, None) or '').strip()
            if not texto:
                continue
            for parte in [p.strip() for p in texto.replace('\n', ';').split(';') if p.strip()]:
                k = parte.upper()
                formulas[k]['item'] = parte
                formulas[k]['qtd'] += 1

        # complementares: extras / suplementos / lve
        for campo in ('extras', 'suplementos', 'lve'):
            texto = (getattr(l, campo, None) or '').strip()
            if not texto:
                continue
            for parte in [p.strip() for p in texto.replace('\n', ';').split(';') if p.strip()]:
                k = parte.upper()
                complementares[k]['item'] = parte
                complementares[k]['qtd'] += 1

    # monta tabelas no formato da tela legado
    tabelas = []
    clinicas_ord = sorted(blocos.keys())
    for clinica in clinicas_ord:
        datas = sorted(blocos[clinica].keys())
        for data_key in datas:
            matriz = blocos[clinica][data_key]
            try:
                data_label = date.fromisoformat(data_key).strftime('%d/%m/%y')
            except ValueError:
                data_label = data_key
            linhas_tab = []
            for cat, label in (
                ('basicas', 'BÁSICAS'),
                ('liquidas', 'LÍQUIDAS'),
                ('di', 'D.I.'),
                ('acomp', 'ACOMP.'),
            ):
                row = {'categoria': label, **matriz[cat]}
                row['total'] = sum(matriz[cat][r] for r, _ in REFEICAO_FLAGS)
                linhas_tab.append(row)
            tabelas.append({
                'data': data_key,
                'data_label': data_label,
                'clinica': clinica,
                'linhas': linhas_tab,
            })

    # sintético: agrega por clínica (soma datas)
    if sintetico and tipo.startswith('espelho'):
        agg = defaultdict(_zero_matriz)
        for t in tabelas:
            for row in t['linhas']:
                cat_key = {
                    'BÁSICAS': 'basicas', 'LÍQUIDAS': 'liquidas', 'D.I.': 'di', 'ACOMP.': 'acomp'
                }[row['categoria']]
                for ref, _ in REFEICAO_FLAGS:
                    agg[t['clinica']][cat_key][ref] += row[ref]
        tabelas = []
        for clinica in sorted(agg.keys()):
            linhas_tab = []
            for cat, label in (
                ('basicas', 'BÁSICAS'), ('liquidas', 'LÍQUIDAS'), ('di', 'D.I.'), ('acomp', 'ACOMP.')
            ):
                row = {'categoria': label, **agg[clinica][cat]}
                row['total'] = sum(agg[clinica][cat][r] for r, _ in REFEICAO_FLAGS)
                linhas_tab.append(row)
            tabelas.append({
                'data': f'{data_de.isoformat()}_{data_ate.isoformat()}',
                'data_label': f'{data_de.strftime("%d/%m/%y")}–{data_ate.strftime("%d/%m/%y")}',
                'clinica': clinica,
                'linhas': linhas_tab,
            })

    # página 2 do espelho: só totais por clínica (resumo)
    if tipo == 'espelho_2':
        # mantém mesmas tabelas mas marca como página 2 (pode filtrar só quem tem movimento)
        tabelas = [t for t in tabelas if any(l['total'] > 0 for l in t['linhas'])]

    tipo_labels = {
        'espelho_1': 'Espelho do faturamento — 1ª página',
        'espelho_2': 'Espelho do faturamento — 2ª página',
        'total_sem_correcao': 'Total de refeições (sem correção)',
        'total_refeicoes': 'Total de refeições',
        'total_formulas': 'Total de fórmulas infantis e enterais',
        'total_complementares': 'Total de refeições complementares',
    }

    resumo_totais = []
    for cat, label in (
        ('basicas', 'BÁSICAS'), ('liquidas', 'LÍQUIDAS'), ('di', 'D.I.'), ('acomp', 'ACOMP.')
    ):
        row = {'categoria': label, **totais_gerais[cat]}
        row['total'] = sum(totais_gerais[cat][r] for r, _ in REFEICAO_FLAGS)
        resumo_totais.append(row)

    return {
        'data_de': data_de.isoformat(),
        'data_ate': data_ate.isoformat(),
        'data_de_label': data_de.strftime('%d/%m/%Y'),
        'data_ate_label': data_ate.strftime('%d/%m/%Y'),
        'tipo': tipo,
        'tipo_label': tipo_labels.get(tipo, tipo),
        'por_grupo_clinica': bool(por_grupo_clinica),
        'sintetico': bool(sintetico),
        'tabelas': tabelas,
        'resumo_totais': resumo_totais,
        'formulas': sorted(formulas.values(), key=lambda x: x['item'].upper()),
        'complementares': sorted(complementares.values(), key=lambda x: x['item'].upper()),
        'qtd_tabelas': len(tabelas),
    }


def _grupo_dieta_totalizacao(nome_dieta, dieta_cat_map=None):
    """Agrupa dieta em BÁSICAS / LÍQUIDAS / D.I. / ACOMPANHANTES para subtotais."""
    nome = (nome_dieta or '').strip().upper()
    cat = (dieta_cat_map or {}).get(nome, '')
    if 'ACOMP' in nome or 'ACOMPANHANTE' in nome:
        return 'ACOMPANHANTES'
    if nome.startswith('DI-') or cat in ('enteral', 'formula', 'lve'):
        return 'D.I.'
    if 'LIQUIDA' in nome:
        return 'LÍQUIDAS'
    return 'BÁSICAS'


def totalizacao_dietas(
    data_ref=None,
    totalizacao_para='clinicas',
    imprimir_por='grupo_clinica',
    filtros=None,
    horarios=None,
    metodo='mapa',
    imprimir_total_geral=True,
):
    """Totaliza dietas do mapa por nome × horários (estilo relatório legado)."""
    from collections import defaultdict

    data_ref = data_ref or date.today()
    garantir_mapa_do_dia(data_ref)
    horarios = set(horarios or [])
    flag_map = {
        'desjejum': 'fl_desjejum',
        'colacao': 'fl_colacao',
        'almoco': 'fl_almoco',
        'merenda': 'fl_merenda',
        'jantar': 'fl_jantar',
        'ceia': 'fl_ceia',
    }
    # se nenhum horário marcado, usa todos
    if not horarios:
        horarios = set(flag_map.keys())

    filtros = [str(f).strip() for f in (filtros or []) if str(f).strip()]
    filtros_upper = {f.upper() for f in filtros}
    todos = (not filtros) or ('TODOS' in filtros_upper)

    dieta_cat_map = {
        (d.nome or '').strip().upper(): (d.categoria or 'basica')
        for d in NutDieta.query.all()
    }

    q = NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True)
    linhas = q.order_by(NutMapaRefeicao.dieta, NutMapaRefeicao.clinica).all()

    filtro_labels = []
    if imprimir_por == 'enfermaria' and not todos:
        enfs = NutEnfermaria.query.filter(NutEnfermaria.id.in_(
            [int(x) for x in filtros if str(x).isdigit()]
        )).all() if any(str(x).isdigit() for x in filtros) else []
        # também aceita nomes
        if not enfs:
            enfs = NutEnfermaria.query.filter(
                db.func.upper(NutEnfermaria.nome).in_(list(filtros_upper))
            ).all()
        filtro_labels = [e.nome for e in enfs]
        leitos = set()
        nomes_enf = {e.nome.upper() for e in enfs}
        for e in enfs:
            for lt in (e.leitos or []):
                if lt.numero_leito:
                    leitos.add(lt.numero_leito.strip().upper())
        filtradas = []
        for l in linhas:
            leito = (l.leito or '').strip().upper()
            clinica = (l.clinica or '').strip().upper()
            if leito in leitos or clinica in nomes_enf or any(n in clinica for n in nomes_enf):
                filtradas.append(l)
        linhas = filtradas
    elif not todos:
        # clínica / grupo de clínica
        ids = [int(x) for x in filtros if str(x).isdigit()]
        nomes = set()
        if ids:
            for c in NutClinica.query.filter(NutClinica.id.in_(ids)).all():
                nomes.add((c.nome or '').strip().upper())
                filtro_labels.append(c.nome)
        for f in filtros:
            if not str(f).isdigit():
                nomes.add(f.upper())
                if f not in filtro_labels:
                    filtro_labels.append(f)
        linhas = [l for l in linhas if (l.clinica or '').strip().upper() in nomes]
    else:
        filtro_labels = ['TODOS']

    # dieta -> contagens por horário
    totais = defaultdict(lambda: {k: 0 for k in flag_map.keys()})
    for l in linhas:
        dieta = (l.dieta or '').strip() or 'SEM DIETA'
        for hk in horarios:
            flag = flag_map.get(hk)
            if flag and getattr(l, flag, False):
                totais[dieta][hk] += 1

    # monta linhas ordenadas por grupo e nome
    ordem_grupos = ['BÁSICAS', 'LÍQUIDAS', 'D.I.', 'ACOMPANHANTES']
    por_grupo = defaultdict(list)
    for nome, counts in totais.items():
        if sum(counts.values()) <= 0:
            continue
        grp = _grupo_dieta_totalizacao(nome, dieta_cat_map)
        row = {'nome': nome, 'grupo': grp, **counts, 'total': sum(counts.values())}
        por_grupo[grp].append(row)

    linhas_rel = []
    subtotais = []
    gerais = {k: 0 for k in flag_map.keys()}
    for grp in ordem_grupos:
        items = sorted(por_grupo.get(grp, []), key=lambda x: x['nome'].upper())
        if not items:
            continue
        sub = {k: 0 for k in flag_map.keys()}
        for it in items:
            linhas_rel.append(it)
            for k in flag_map.keys():
                sub[k] += it[k]
                gerais[k] += it[k]
        label = {
            'BÁSICAS': 'TOTAL - DIETAS BÁSICAS',
            'LÍQUIDAS': 'TOTAL - DIETAS LÍQUIDAS',
            'D.I.': 'TOTAL - DIETA D.I.',
            'ACOMPANHANTES': 'TOTAL - ACOMPANHANTES DE LEITO',
        }.get(grp, f'TOTAL - {grp}')
        subtotais.append({
            'nome': label,
            'grupo': grp,
            'is_subtotal': True,
            **sub,
            'total': sum(sub.values()),
        })
        linhas_rel.append(subtotais[-1])

    colunas = []
    labels_h = {
        'desjejum': 'D', 'colacao': 'C', 'almoco': 'A',
        'merenda': 'M', 'jantar': 'J', 'ceia': 'Ce',
    }
    for hk in ('desjejum', 'colacao', 'almoco', 'merenda', 'jantar', 'ceia'):
        if hk in horarios:
            colunas.append({'key': hk, 'label': labels_h[hk]})

    return {
        'data': data_ref.isoformat(),
        'data_label': data_ref.strftime('%d/%m/%y'),
        'data_hora_relatorio': datetime.now().strftime('%d/%m/%y %H:%M:%S'),
        'totalizacao_para': totalizacao_para,
        'imprimir_por': imprimir_por,
        'metodo': metodo,
        'filtros_label': ', '.join(filtro_labels) if filtro_labels else 'TODOS',
        'horarios': sorted(horarios),
        'colunas': colunas,
        'linhas': linhas_rel,
        'imprimir_total_geral': bool(imprimir_total_geral),
        'total_geral': {**gerais, 'total': sum(gerais.values())},
        'qtd_dietas': len([x for x in linhas_rel if not x.get('is_subtotal')]),
    }
