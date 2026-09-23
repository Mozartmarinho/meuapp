"""Importa a Tabela Brasileira de Composição de Alimentos (TACO, 4ª edição / NEPA-UNICAMP)."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path

from models import db
from models_nutricao import NutAlimento, NutAlimentoNutriente, NutTabelaNutrientes

DEFAULT_TABELA_NOME = 'TACO'
DEFAULT_CSV_URL = (
    'https://raw.githubusercontent.com/brolesi/taco/master/'
    'data/processed/taco/taco_composicao.csv'
)
BUNDLED_CSV = Path(__file__).resolve().parent / 'data' / 'taco' / 'taco_composicao.csv'

# coluna CSV -> (rótulo na UI, unidade)
TACO_NUTRIENTES = (
    ('energia_kcal', 'Energia', 'kcal'),
    ('energia_kj', 'Energia', 'kJ'),
    ('proteina_g', 'Proteína', 'g'),
    ('lipideos_g', 'Lipídios', 'g'),
    ('carboidrato_g', 'Carboidrato', 'g'),
    ('fibra_g', 'Fibra alimentar', 'g'),
    ('umidade_pct', 'Água', 'g'),
    ('cinzas_g', 'Cinzas', 'g'),
    ('colesterol_mg', 'Colesterol', 'mg'),
    ('calcio_mg', 'Cálcio', 'mg'),
    ('magnesio_mg', 'Magnésio', 'mg'),
    ('manganes_mg', 'Manganês', 'mg'),
    ('fosforo_mg', 'Fósforo', 'mg'),
    ('ferro_mg', 'Ferro', 'mg'),
    ('sodio_mg', 'Sódio', 'mg'),
    ('potassio_mg', 'Potássio', 'mg'),
    ('cobre_mg', 'Cobre', 'mg'),
    ('zinco_mg', 'Zinco', 'mg'),
    ('retinol_mcg', 'Retinol', 'µg'),
    ('RE_mcg', 'Equivalente de retinol (RE)', 'µg'),
    ('RAE_mcg', 'Vitamina A (RAE)', 'µg'),
    ('tiamina_mg', 'Tiamina', 'mg'),
    ('riboflavina_mg', 'Riboflavina', 'mg'),
    ('piridoxina_mg', 'Vitamina B-6', 'mg'),
    ('niacina_mg', 'Niacina', 'mg'),
    ('vitamina_c_mg', 'Vitamina C', 'mg'),
)


def _num(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ('na', 'nd', 'n/a', 'tr', 'trace', '-', 'none'):
        return None
    s = s.replace(',', '.')
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _rnd(val, nd=2):
    if val is None:
        return 0.0
    return round(float(val), nd)


def _load_rows(source=None):
    raw = None
    if source:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError('CSV TACO não encontrado: {}'.format(path))
        raw = path.read_bytes()
    elif BUNDLED_CSV.is_file():
        raw = BUNDLED_CSV.read_bytes()
    else:
        try:
            from urllib.request import urlopen, Request
            req = Request(DEFAULT_CSV_URL, headers={'User-Agent': 'meuapp-taco-import'})
            with urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except Exception as exc:
            raise FileNotFoundError(
                'Não foi possível baixar a TACO. Coloque o CSV em {} ({})'.format(
                    BUNDLED_CSV, exc
                )
            )
        BUNDLED_CSV.parent.mkdir(parents=True, exist_ok=True)
        BUNDLED_CSV.write_bytes(raw)

    text = raw.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError('CSV TACO vazio')
    if 'descricao' not in (reader.fieldnames or []):
        raise ValueError('CSV TACO inválido (falta coluna descricao)')
    return rows


def import_taco_table(
    source=None,
    tabela_nome=DEFAULT_TABELA_NOME,
    set_official=False,
    batch_size=50,
    deactivate_missing=True,
):
    """Upsert TACO em nut_tabelas_nutrientes / nut_alimentos (idempotente por número TACO)."""
    from nutricao_service import _ensure_nutricao_columns

    _ensure_nutricao_columns()
    foods = _load_rows(source)
    nome_tab = (tabela_nome or DEFAULT_TABELA_NOME).strip() or DEFAULT_TABELA_NOME

    tab = NutTabelaNutrientes.query.filter_by(nome=nome_tab).first()
    if tab is None:
        tab = NutTabelaNutrientes(nome=nome_tab, ativo=True)
        db.session.add(tab)
        db.session.flush()
    else:
        tab.ativo = True

    if set_official:
        for other in NutTabelaNutrientes.query.filter(NutTabelaNutrientes.id != tab.id).all():
            other.ativo = False

    existing = {
        a.fdc_id: a
        for a in NutAlimento.query.filter_by(tabela_id=tab.id).all()
        if a.fdc_id is not None
    }

    created = 0
    updated = 0
    nutrient_rows = 0
    seen = set()
    now = datetime.utcnow()

    for i, food in enumerate(foods, 1):
        taco_id = _num(food.get('numero_alimento'))
        if taco_id is None:
            continue
        taco_id = int(taco_id)
        seen.add(taco_id)
        nome = (food.get('descricao') or 'TACO {}'.format(taco_id)).strip().upper()[:200]
        categoria = (food.get('categoria') or '').strip()
        prot = _num(food.get('proteina_g')) or 0.0
        fat = _num(food.get('lipideos_g')) or 0.0
        carb = _num(food.get('carboidrato_g')) or 0.0
        energy = _num(food.get('energia_kcal'))
        if energy is None:
            energy = prot * 4 + fat * 9 + carb * 4

        alim = existing.get(taco_id)
        if alim is None:
            alim = NutAlimento(tabela_id=tab.id, fdc_id=taco_id)
            db.session.add(alim)
            existing[taco_id] = alim
            created += 1
        else:
            updated += 1

        alim.nome = nome
        alim.ativo = True
        alim.ref_consumo = ('100 g' + (' · ' + categoria if categoria else ''))[:80]
        alim.qtd_proteina = _rnd(prot)
        alim.qtd_gordura = _rnd(fat)
        alim.qtd_carboidratos = _rnd(carb)
        alim.cal_proteina = _rnd(prot * 4)
        alim.cal_gordura = _rnd(fat * 9)
        alim.cal_carboidratos = _rnd(carb * 4)
        alim.cal_total = _rnd(energy)
        alim.ultima_alteracao = now
        db.session.flush()

        NutAlimentoNutriente.query.filter_by(alimento_id=alim.id).delete()
        for col, label, un in TACO_NUTRIENTES:
            qtd = _num(food.get(col))
            if qtd is None:
                continue
            db.session.add(NutAlimentoNutriente(
                alimento_id=alim.id,
                nutriente=label,
                quantidade=_rnd(qtd, 4 if un in ('mg', 'µg') else 2),
                unidade=un,
                fator=1,
            ))
            nutrient_rows += 1

        if i % max(1, batch_size) == 0:
            db.session.commit()

    deactivated = 0
    if deactivate_missing:
        for taco_id, alim in existing.items():
            if taco_id not in seen and alim.ativo:
                alim.ativo = False
                alim.ultima_alteracao = now
                deactivated += 1

    db.session.commit()
    return {
        'ok': True,
        'tabela_id': tab.id,
        'tabela_nome': tab.nome,
        'foods_source': len(foods),
        'created': created,
        'updated': updated,
        'deactivated': deactivated,
        'nutrient_rows': nutrient_rows,
        'ativos': NutAlimento.query.filter_by(tabela_id=tab.id, ativo=True).count(),
        'fonte': 'TACO 4ª edição (NEPA/UNICAMP, 2011) — valores por 100 g parte comestível',
    }
