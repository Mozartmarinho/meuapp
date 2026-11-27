"""Análise nutricional, evolução e totalização direta ligadas ao mapa."""
import json
from datetime import date

from models import db
from models_nutricao import (
    NutAlimento, NutAvaliacaoNutricional, NutDieta, NutEvolucaoPaciente,
    NutMapaRefeicao, NutPaciente, NutTotalizacaoDireta,
)
from nutricao_tenant import apply_cliente_filter, write_cliente_id

REFEICOES_DIRETAS = (
    ('desjejum', 'Desjejum'),
    ('colacao', 'Colação'),
    ('almoco', 'Almoço'),
    ('merenda', 'Merenda'),
    ('jantar', 'Jantar'),
    ('ceia', 'Ceia'),
)
TIPOS_DIRETO = ('dieta', 'extra', 'suplemento', 'formula_infantil', 'lve', 'enteral')
TIPOS_EVOLUCAO = ('tne', 'oral')
LABORATORIO = (
    'glicose', 'ureia', 'creatinina', 'ptn_totais', 'albumina', 'acido_urico',
    'colesterol', 'tg', 'hto', 'hb', 'leucocitos', 'linfocitos', 'na', 'k', 'ca',
    'p', 'mg', 'acido_folico', 'b12', 'amilase', 'lipase', 'bilirrubina',
)
HORARIO_ALIASES = {
    'desjejum': 'desjejum', 'd': 'desjejum',
    'colacao': 'colacao', 'colação': 'colacao', 'c': 'colacao',
    'almoco': 'almoco', 'almoço': 'almoco', 'a': 'almoco',
    'merenda': 'merenda', 'm': 'merenda',
    'jantar': 'jantar', 'j': 'jantar',
    'ceia': 'ceia',
}


def _num(valor):
    if valor is None or valor == '':
        return None
    try:
        return float(str(valor).replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _round(valor, casas=1):
    if valor is None:
        return None
    return round(float(valor), casas)


def calcular_avaliacao(dados):
    """IMC, peso teórico, perda de peso, GEB (Harris-Benedict), GET e pregas."""
    peso = _num(dados.get('peso_atual'))
    altura = _num(dados.get('estatura_cm'))
    habitual = _num(dados.get('peso_habitual'))
    sexo = (dados.get('sexo') or '').strip().upper()[:1]
    idade = _num(dados.get('idade'))
    fat_at = _num(dados.get('fator_atividade')) or 1.2
    fat_inj = _num(dados.get('fator_injuria')) or 1.0
    fat_term = _num(dados.get('fator_termico')) or 1.0

    imc = None
    peso_teorico = None
    if altura and altura > 0:
        metros = altura / 100.0
        peso_teorico = _round(22.0 * metros * metros, 1)
        if peso and peso > 0:
            imc = _round(peso / (metros * metros), 2)
    perda = None
    if habitual and habitual > 0 and peso is not None:
        perda = _round((habitual - peso) / habitual * 100.0, 1)

    geb = None
    if peso and altura and idade is not None and sexo in ('M', 'F'):
        if sexo == 'M':
            geb = 66.4730 + (13.7516 * peso) + (5.0033 * altura) - (6.7550 * idade)
        else:
            geb = 655.0955 + (9.5634 * peso) + (1.8496 * altura) - (4.6756 * idade)
        geb = _round(geb, 1)
    get = _round(geb * fat_at * fat_inj * fat_term, 1) if geb is not None else None
    get_kg = _round(get / peso, 1) if get is not None and peso else None

    pregas = [_num(dados.get(k)) for k in (
        'prega_biceps', 'prega_triceps', 'prega_subescapular', 'prega_suprailiaca',
    )]
    gordura = None
    if all(p is not None for p in pregas):
        gordura = _round((sum(pregas) * 0.153) + 5.783, 1)
    cmb = None
    circ = _num(dados.get('circ_braco'))
    triceps = _num(dados.get('prega_triceps'))
    if circ is not None and triceps is not None:
        cmb = _round(circ - (3.1416 * triceps / 10.0), 1)

    return {
        'imc': imc,
        'peso_teorico': peso_teorico,
        'perda_peso': perda,
        'geb': geb,
        'get': get,
        'get_kg': get_kg,
        'gordura': gordura,
        'cmb': cmb,
    }


def macros_da_dieta(nome_dieta, volume_pct=100):
    """Escala a tabela nutricional da dieta pelo volume informado na análise."""
    nome = (nome_dieta or '').strip()
    if not nome:
        return None
    alimento = (
        NutAlimento.query
        .filter(db.func.upper(NutAlimento.nome) == nome.upper(), NutAlimento.ativo.is_(True))
        .first()
    )
    if not alimento:
        return None
    fator = (_num(volume_pct) or 100.0) / 100.0
    return {
        'vet': _round((alimento.cal_total or 0) * fator, 1),
        'hc': _round((alimento.qtd_carboidratos or 0) * fator, 1),
        'lip': _round((alimento.qtd_gordura or 0) * fator, 1),
        'ptn': _round((alimento.qtd_proteina or 0) * fator, 1),
        'fonte': alimento.nome,
    }


def _linha_mapa(mapa_id):
    if not mapa_id:
        return None
    try:
        return NutMapaRefeicao.query.get(int(mapa_id))
    except (TypeError, ValueError):
        return None


def pacientes_do_mapa(data_ref, modo='ambos'):
    """Pacientes ativos do mapa do dia, para os seletores da análise e da evolução."""
    data_ref = data_ref or date.today()
    rows = (
        apply_cliente_filter(
            NutMapaRefeicao.query.filter_by(data_refeicao=data_ref, ativo=True),
            NutMapaRefeicao,
        )
        .order_by(NutMapaRefeicao.clinica, NutMapaRefeicao.leito, NutMapaRefeicao.nome)
        .all()
    )
    saida = []
    vistos = set()
    for row in rows:
        nome = (row.nome or '').strip()
        if not nome:
            continue
        enteral = bool((row.enteral or '').strip() or (row.formula_infantil or '').strip())
        if modo == 'tne' and not enteral:
            continue
        if modo == 'oral' and enteral:
            continue
        chave = (row.paciente_id or 0, nome.upper(), (row.leito or '').upper())
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append({
            'mapa_id': row.id,
            'paciente_id': row.paciente_id,
            'nome': nome,
            'leito': row.leito or '',
            'clinica': row.clinica or '',
            'enfermaria': row.enfermaria or '',
            'dieta': row.dieta or '',
            'enteral': bool(enteral),
            'rotulo': f"{row.leito or 's/ leito'} — {nome}",
        })
    return saida


def _paciente_vigente(paciente):
    """Unificado deixa de existir: evolução e análise seguem o cadastro principal."""
    visto = set()
    atual = paciente
    while atual and getattr(atual, 'excluido', False) and getattr(atual, 'unificado_em_id', None):
        if atual.id in visto:
            break
        visto.add(atual.id)
        seguinte = NutPaciente.query.get(atual.unificado_em_id)
        if not seguinte or seguinte.id == atual.id:
            break
        atual = seguinte
    return atual


def contexto_paciente(mapa_id=None, paciente_id=None):
    linha = _linha_mapa(mapa_id)
    paciente = None
    if linha and linha.paciente_id:
        paciente = linha.paciente or NutPaciente.query.get(linha.paciente_id)
    elif paciente_id:
        try:
            paciente = NutPaciente.query.get(int(paciente_id))
        except (TypeError, ValueError):
            paciente = None
    paciente = _paciente_vigente(paciente)
    if not linha and not paciente:
        return None
    sexo = (paciente.sexo if paciente else '') or ''
    idade = linha.idade if linha and linha.idade is not None else (paciente.idade() if paciente else None)
    return {
        'mapa_id': linha.id if linha else None,
        'paciente_id': (paciente.id if paciente else (linha.paciente_id if linha else None)),
        'nome': (linha.nome if linha else paciente.nome) or '',
        'leito': (linha.leito if linha else paciente.leito) or '',
        'clinica': (linha.clinica if linha else paciente.clinica) or '',
        'enfermaria': (linha.enfermaria if linha else '') or '',
        'dieta': (linha.dieta if linha else paciente.dieta) or '',
        'diagnostico': (linha.diagnostico if linha else paciente.diagnostico) or '',
        'prontuario': (linha.prontuario if linha else paciente.prontuario) or '',
        'sexo': sexo,
        'idade': idade,
        'peso_kg': paciente.peso_kg if paciente else None,
        'altura_cm': paciente.altura_cm if paciente else None,
        'enteral': bool(linha and ((linha.enteral or '').strip() or (linha.formula_infantil or '').strip())),
    }


def _labs_de(texto):
    if not texto:
        return {}
    try:
        data = json.loads(texto)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def avaliacao_dict(row, contexto=None):
    if not row:
        return None
    dados = {
        'id': row.id,
        'paciente_id': row.paciente_id,
        'mapa_id': row.mapa_id,
        'data': row.data_avaliacao.isoformat() if row.data_avaliacao else '',
        'peso_atual': row.peso_atual,
        'estatura_cm': row.estatura_cm,
        'peso_habitual': row.peso_habitual,
        'peso_calculado': row.peso_calculado,
        'fator_atividade': row.fator_atividade if row.fator_atividade is not None else 1.2,
        'fator_injuria': row.fator_injuria if row.fator_injuria is not None else 1.0,
        'fator_termico': row.fator_termico if row.fator_termico is not None else 1.0,
        'asg': row.asg or '',
        'freq_cardiaca': row.freq_cardiaca or '',
        'freq_respiratoria': row.freq_respiratoria or '',
        'pressao_arterial': row.pressao_arterial or '',
        'funcao_intestinal': row.funcao_intestinal or '',
        'prega_biceps': row.prega_biceps,
        'prega_triceps': row.prega_triceps,
        'prega_subescapular': row.prega_subescapular,
        'prega_suprailiaca': row.prega_suprailiaca,
        'circ_braco': row.circ_braco,
        'circ_abdomen': row.circ_abdomen,
        'circ_panturrilha': row.circ_panturrilha,
        'hgt': row.hgt or '',
        'insulina': row.insulina or '',
        'volume_pct': row.volume_pct if row.volume_pct is not None else 100,
        'intercorrencias': row.intercorrencias or '',
        'observacoes': row.observacoes or '',
        'laboratoriais': _labs_de(row.laboratoriais),
    }
    if contexto:
        dados['sexo'] = contexto.get('sexo') or ''
        dados['idade'] = contexto.get('idade')
        dados['dieta'] = contexto.get('dieta') or ''
    dados['calculo'] = calcular_avaliacao(dados)
    dados['macros'] = macros_da_dieta(dados.get('dieta'), dados.get('volume_pct'))
    return dados


def buscar_avaliacao(paciente_id, mapa_id, data_ref):
    q = apply_cliente_filter(NutAvaliacaoNutricional.query, NutAvaliacaoNutricional)
    q = q.filter_by(data_avaliacao=data_ref)
    if paciente_id:
        row = q.filter_by(paciente_id=int(paciente_id)).order_by(NutAvaliacaoNutricional.id.desc()).first()
        if row:
            return row
    if mapa_id:
        return q.filter_by(mapa_id=int(mapa_id)).order_by(NutAvaliacaoNutricional.id.desc()).first()
    return None


def salvar_avaliacao(dados, data_ref, contexto):
    paciente_id = contexto.get('paciente_id') if contexto else dados.get('paciente_id')
    mapa_id = contexto.get('mapa_id') if contexto else dados.get('mapa_id')
    row = buscar_avaliacao(paciente_id, mapa_id, data_ref)
    if not row:
        row = NutAvaliacaoNutricional(
            cliente_id=write_cliente_id(),
            paciente_id=paciente_id,
            mapa_id=mapa_id,
            data_avaliacao=data_ref,
        )
        db.session.add(row)
    row.paciente_id = paciente_id or row.paciente_id
    row.mapa_id = mapa_id or row.mapa_id
    row.peso_atual = _num(dados.get('peso_atual'))
    row.estatura_cm = _num(dados.get('estatura_cm'))
    row.peso_habitual = _num(dados.get('peso_habitual'))
    row.peso_calculado = _num(dados.get('peso_calculado'))
    row.fator_atividade = _num(dados.get('fator_atividade')) or 1.2
    row.fator_injuria = _num(dados.get('fator_injuria')) or 1.0
    row.fator_termico = _num(dados.get('fator_termico')) or 1.0
    asg = (dados.get('asg') or '').strip().upper()[:1]
    row.asg = asg if asg in ('A', 'B', 'C') else None
    row.freq_cardiaca = (dados.get('freq_cardiaca') or '').strip()[:20] or None
    row.freq_respiratoria = (dados.get('freq_respiratoria') or '').strip()[:20] or None
    row.pressao_arterial = (dados.get('pressao_arterial') or '').strip()[:20] or None
    intestino = (dados.get('funcao_intestinal') or '').strip().lower()
    row.funcao_intestinal = intestino if intestino in ('sim', 'nao') else None
    for campo in (
        'prega_biceps', 'prega_triceps', 'prega_subescapular', 'prega_suprailiaca',
        'circ_braco', 'circ_abdomen', 'circ_panturrilha', 'volume_pct',
    ):
        setattr(row, campo, _num(dados.get(campo)))
    row.hgt = (dados.get('hgt') or '').strip()[:20] or None
    row.insulina = (dados.get('insulina') or '').strip()[:20] or None
    row.intercorrencias = (dados.get('intercorrencias') or '').strip() or None
    row.observacoes = (dados.get('observacoes') or '').strip() or None
    labs = dados.get('laboratoriais') or {}
    limpo = {}
    if isinstance(labs, dict):
        for chave in LABORATORIO:
            valor = labs.get(chave)
            if valor not in (None, ''):
                limpo[chave] = str(valor).strip()[:40]
    row.laboratoriais = json.dumps(limpo, ensure_ascii=False)
    if paciente_id and row.data_avaliacao:
        paciente = NutPaciente.query.get(int(paciente_id))
        if paciente:
            if row.peso_atual is not None:
                paciente.peso_kg = row.peso_atual
            if row.estatura_cm is not None:
                paciente.altura_cm = row.estatura_cm
    db.session.commit()
    return row


def listar_evolucoes(paciente_id=None, mapa_id=None):
    q = apply_cliente_filter(NutEvolucaoPaciente.query, NutEvolucaoPaciente)
    if paciente_id:
        q = q.filter_by(paciente_id=int(paciente_id))
    elif mapa_id:
        q = q.filter_by(mapa_id=int(mapa_id))
    else:
        return []
    rows = q.order_by(NutEvolucaoPaciente.data_registro.desc(), NutEvolucaoPaciente.id.desc()).all()
    return [_evolucao_dict(r) for r in rows]


def _evolucao_dict(row):
    return {
        'id': row.id,
        'paciente_id': row.paciente_id,
        'mapa_id': row.mapa_id,
        'data': row.data_registro.isoformat() if row.data_registro else '',
        'data_label': row.data_registro.strftime('%d/%m/%Y') if row.data_registro else '',
        'tipo': row.tipo or 'oral',
        'tipo_label': 'TNE' if row.tipo == 'tne' else 'Via oral',
        'alteracoes': row.alteracoes or '',
        'conduta': row.conduta or '',
        'dieta': row.dieta or '',
        'clinica': row.clinica or '',
        'leito': row.leito or '',
    }


def salvar_evolucao(dados, data_ref, contexto):
    tipo = (dados.get('tipo') or 'oral').strip().lower()
    if tipo not in TIPOS_EVOLUCAO:
        tipo = 'oral'
    row = NutEvolucaoPaciente(
        cliente_id=write_cliente_id(),
        paciente_id=(contexto or {}).get('paciente_id'),
        mapa_id=(contexto or {}).get('mapa_id'),
        data_registro=data_ref,
        tipo=tipo,
        alteracoes=(dados.get('alteracoes') or '').strip() or None,
        conduta=(dados.get('conduta') or '').strip() or None,
        dieta=((contexto or {}).get('dieta') or '')[:200] or None,
        clinica=((contexto or {}).get('clinica') or '')[:120] or None,
        leito=((contexto or {}).get('leito') or '')[:40] or None,
    )
    db.session.add(row)
    db.session.commit()
    return _evolucao_dict(row)


def excluir_evolucao(evo_id):
    row = apply_cliente_filter(NutEvolucaoPaciente.query, NutEvolucaoPaciente).filter_by(id=int(evo_id)).first()
    if not row:
        return False
    db.session.delete(row)
    db.session.commit()
    return True


def _quantidades_de(texto, tipo):
    try:
        data = json.loads(texto or '{}')
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    if tipo == 'dieta':
        return {chave: int(data.get(chave) or 0) for chave, _rotulo in REFEICOES_DIRETAS}
    return {str(h): int(data.get(str(h)) or 0) for h in range(1, 25)}


def _totalizacao_dict(row):
    qtd = _quantidades_de(row.quantidades, row.tipo)
    return {
        'id': row.id,
        'data': row.data_ref.isoformat() if row.data_ref else '',
        'clinica_id': row.clinica_id,
        'clinica': row.clinica or '',
        'tipo': row.tipo or 'dieta',
        'dieta_id': row.dieta_id,
        'item': row.item or '',
        'dieta': row.item or '',
        'quantidades': qtd,
        'total': sum(qtd.values()),
    }


def listar_totalizacao_direta(data_ref, clinica=None):
    q = apply_cliente_filter(
        NutTotalizacaoDireta.query.filter_by(data_ref=data_ref),
        NutTotalizacaoDireta,
    )
    if clinica:
        q = q.filter(db.func.upper(NutTotalizacaoDireta.clinica) == clinica.strip().upper())
    rows = q.order_by(NutTotalizacaoDireta.clinica, NutTotalizacaoDireta.tipo, NutTotalizacaoDireta.item).all()
    return [_totalizacao_dict(r) for r in rows]


def salvar_totalizacao_direta(dados, data_ref):
    tipo = (dados.get('tipo') or 'dieta').strip().lower()
    if tipo not in TIPOS_DIRETO:
        tipo = 'dieta'
    clinica = (dados.get('clinica') or '').strip()
    if not clinica and dados.get('clinica_id'):
        from models_nutricao import NutClinica
        try:
            cad = apply_cliente_filter(NutClinica.query, NutClinica).filter_by(
                id=int(dados.get('clinica_id'))
            ).first()
        except (TypeError, ValueError):
            cad = None
        clinica = (cad.nome if cad else '') or ''
    item = (dados.get('item') or dados.get('dieta') or '').strip()
    dieta_id = dados.get('dieta_id')
    if tipo == 'dieta' and dieta_id and not item:
        try:
            dieta = apply_cliente_filter(NutDieta.query, NutDieta).filter_by(
                id=int(dieta_id)
            ).first()
        except (TypeError, ValueError):
            dieta = None
        item = (dieta.nome if dieta else '') or ''
    if not clinica or not item:
        raise ValueError('Clínica e item são obrigatórios')
    q = apply_cliente_filter(NutTotalizacaoDireta.query, NutTotalizacaoDireta).filter_by(data_ref=data_ref)
    row = q.filter(
        db.func.upper(NutTotalizacaoDireta.clinica) == clinica.upper(),
        NutTotalizacaoDireta.tipo == tipo,
        db.func.upper(NutTotalizacaoDireta.item) == item.upper(),
    ).first()
    if not row:
        row = NutTotalizacaoDireta(
            cliente_id=write_cliente_id(),
            data_ref=data_ref,
            clinica=clinica[:160],
            tipo=tipo,
            item=item[:200],
        )
        db.session.add(row)
    row.clinica = clinica[:160]
    try:
        row.clinica_id = int(dados.get('clinica_id')) if dados.get('clinica_id') else row.clinica_id
    except (TypeError, ValueError):
        pass
    try:
        row.dieta_id = int(dieta_id) if dieta_id else (row.dieta_id if tipo == 'dieta' else None)
    except (TypeError, ValueError):
        row.dieta_id = None
    row.tipo = tipo
    row.item = item[:200]
    atual = _quantidades_de(row.quantidades, tipo)
    novas = dados.get('quantidades') or {}
    if not isinstance(novas, dict):
        novas = {}
    horario = HORARIO_ALIASES.get((dados.get('horario') or '').strip().lower())
    if horario and dados.get('quantidade') is not None and tipo == 'dieta':
        novas = {horario: dados.get('quantidade')}
    for chave, valor in novas.items():
        chave = str(chave)
        if tipo == 'dieta' and chave not in atual:
            continue
        if tipo != 'dieta' and chave not in atual:
            continue
        try:
            n = int(valor or 0)
        except (TypeError, ValueError):
            n = 0
        atual[chave] = max(0, min(n, 9999))
    row.quantidades = json.dumps(atual, ensure_ascii=False)
    db.session.commit()
    return _totalizacao_dict(row)


def excluir_totalizacao_direta(item_id):
    row = apply_cliente_filter(NutTotalizacaoDireta.query, NutTotalizacaoDireta).filter_by(id=int(item_id)).first()
    if not row:
        return False
    db.session.delete(row)
    db.session.commit()
    return True
