"""Seed inicial e helpers do módulo de nutrição."""
from datetime import date, datetime
from models import db
from models_nutricao import NutClinica, NutDieta, NutPaciente, NutMapaRefeicao


DIETAS_SEED = [
    ('BRANDA', 'basica'),
    ('BRANDA CONSTIPANTE', 'basica'),
    ('BRANDA HIOS', 'basica'),
    ('BRANDA DB', 'basica'),
    ('BRANDA HIOL/HEPATO', 'basica'),
    ('BRANDA HIOP/RENAL', 'basica'),
    ('PASTOSA', 'basica'),
    ('PASTOSA DB', 'basica'),
    ('PASTOSA HIOS', 'basica'),
    ('LÍQUIDA', 'basica'),
    ('HIPERPROTEICA', 'basica'),
    ('HIPOSSÓDICA', 'basica'),
    ('DIABÉTICA', 'basica'),
    ('JEJUM', 'basica'),
    ('NORMAL', 'basica'),
    ('NORMOCALORICA E NORMOPROTEICA - NUTRI ENTERAL 1L', 'enteral'),
    ('NORMOCALORICA E HIPERPROTEICA - NUTRI ENTERAL 1L', 'enteral'),
    ('HIPERCALORICA 1.5 E HIPERPROTEICA - NUTRI ENTERAL 1L', 'enteral'),
    ('FORMULA INFANTIL HIPOALERGENICA 1:25 - NAN HA', 'formula'),
    ('FORMULA INFANTIL A BASE DE SOJA 1:30 - NAN SOY', 'formula'),
    ('FORTIDRINK BAUNILHA 200 ML', 'suplemento'),
]

CLINICAS_SEED = [
    ('Clínica Médica', 'CC-1001'),
    ('CTI', 'CC-1002'),
    ('Oncologia', 'CC-1003'),
    ('Maternidade', 'CC-1004'),
    ('Pediatria', 'CC-1005'),
    ('Cardiologia', 'CC-1006'),
    ('Centro Cirúrgico', 'CC-1007'),
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


def seed_nutricao():
    """Garante cadastros básicos de clínicas e dietas."""
    for nome, cc in CLINICAS_SEED:
        if not NutClinica.query.filter_by(nome=nome).first():
            db.session.add(NutClinica(nome=nome, centro_custo=cc))

    for nome, cat in DIETAS_SEED:
        if not NutDieta.query.filter_by(nome=nome).first():
            db.session.add(NutDieta(nome=nome, categoria=cat))

    if NutPaciente.query.count() == 0:
        exemplos = [
            NutPaciente(
                nome='Maria Silva', sexo='F', nascimento=_parse_date('1985-03-15'),
                prontuario='12345', clinica='Clínica Médica', leito='101-A',
                dieta='BRANDA', diagnostico='HAS', admissao=date.today(),
                altura_cm=165, peso_kg=72, ativo=True,
            ),
            NutPaciente(
                nome='João Santos', sexo='M', nascimento=_parse_date('1972-08-22'),
                prontuario='12346', clinica='CTI', leito='05',
                dieta='HIPERPROTEICA', diagnostico='Pós-operatório', admissao=date.today(),
                altura_cm=175, peso_kg=80, ativo=True,
            ),
            NutPaciente(
                nome='Ana Oliveira', sexo='F', nascimento=_parse_date('1990-12-01'),
                prontuario='12347', clinica='Oncologia', leito='210-B',
                dieta='LÍQUIDA', diagnostico='Em tratamento', admissao=date.today(),
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


def mapa_from_paciente(paciente, data_ref=None, flags=None):
    data_ref = data_ref or date.today()
    flags = flags or {}
    return NutMapaRefeicao(
        data_refeicao=data_ref,
        paciente_id=paciente.id,
        adm=paciente.admissao,
        leito=paciente.leito,
        prontuario=paciente.prontuario,
        nome=paciente.nome,
        idade=paciente.idade(data_ref),
        diagnostico=paciente.diagnostico,
        dieta=paciente.dieta,
        observacoes=paciente.observacoes,
        clinica=paciente.clinica,
        fl_desjejum=bool(flags.get('fl_desjejum', True)),
        fl_colacao=bool(flags.get('fl_colacao', True)),
        fl_almoco=bool(flags.get('fl_almoco', True)),
        fl_merenda=bool(flags.get('fl_merenda', True)),
        fl_jantar=bool(flags.get('fl_jantar', True)),
        fl_ceia=bool(flags.get('fl_ceia', True)),
        data_saida=paciente.data_saida,
        ativo=True,
    )


def garantir_mapa_do_dia(data_ref=None):
    """Garante linhas do mapa para pacientes ativos na data."""
    data_ref = data_ref or date.today()
    pacientes = NutPaciente.query.filter_by(ativo=True).all()
    criados = 0
    for p in pacientes:
        exists = NutMapaRefeicao.query.filter_by(
            data_refeicao=data_ref, paciente_id=p.id, ativo=True
        ).first()
        if exists:
            continue
        # não inclui quem já teve saída antes da data
        if p.data_saida and p.data_saida < data_ref:
            continue
        db.session.add(mapa_from_paciente(p, data_ref))
        criados += 1
    if criados:
        db.session.commit()
    return criados
