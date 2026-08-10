"""Import USDA FoodData Central Foundation Foods into nut_* tables."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Tuple, Union

from models import db
from models_nutricao import NutAlimento, NutAlimentoNutriente, NutTabelaNutrientes

DEFAULT_TABELA_NOME = 'FoodData Central Foundation 2026-04-30'

# Nutrient id (FDC) -> (nome PT usado no cadastro, unidade preferida)
FDC_NUTRIENT_LABELS = {
    1008: ('Energia', 'kcal'),
    1003: ('Proteína', 'g'),
    1004: ('Lipídios', 'g'),
    1005: ('Carboidrato', 'g'),
    1079: ('Fibra alimentar', 'g'),
    1087: ('Cálcio', 'mg'),
    1089: ('Ferro', 'mg'),
    1093: ('Sódio', 'mg'),
    1092: ('Potássio', 'mg'),
    1162: ('Vitamina C', 'mg'),
    1051: ('Água', 'g'),
    1007: ('Cinzas', 'g'),
    1258: ('Ácidos graxos saturados', 'g'),
    1292: ('Ácidos graxos monoinsaturados', 'g'),
    1293: ('Ácidos graxos poli-insaturados', 'g'),
    1253: ('Colesterol', 'mg'),
    1095: ('Zinco', 'mg'),
    1090: ('Magnésio', 'mg'),
    1091: ('Fósforo', 'mg'),
    1106: ('Vitamina A (RAE)', 'µg'),
    1114: ('Vitamina D', 'µg'),
    1109: ('Vitamina E', 'mg'),
    1185: ('Vitamina K', 'µg'),
    1165: ('Tiamina', 'mg'),
    1166: ('Riboflavina', 'mg'),
    1167: ('Niacina', 'mg'),
    1175: ('Vitamina B-6', 'mg'),
    1177: ('Folato total', 'µg'),
    1178: ('Vitamina B-12', 'µg'),
}

# Skip kJ energy when kcal is present (avoid duplicate "Energia")
SKIP_NUTRIENT_IDS = {1062}


def _norm_unit(unit: Optional[str]) -> str:
    u = (unit or 'g').strip()
    if not u:
        return 'g'
    # Normalize microgram variants from FDC JSON
    if u in ('Âµg', 'ÂµG', 'ug', 'UG', 'mcg', 'MCG', 'µg', 'μg'):
        return 'µg'
    if u.lower() == 'kcal':
        return 'kcal'
    if u.lower() == 'kj':
        return 'kJ'
    return u[:20]


def _nutrient_label(nutrient: dict) -> Tuple[str, str]:
    nid = nutrient.get('id')
    if nid in FDC_NUTRIENT_LABELS:
        nome, un = FDC_NUTRIENT_LABELS[nid]
        return nome, un
    nome = (nutrient.get('name') or f'Nutriente {nid or "?"}').strip()
    return nome[:120], _norm_unit(nutrient.get('unitName'))


def _ref_consumo(food: dict) -> str:
    portions = food.get('foodPortions') or []
    if not portions:
        return '100 g'
    p = sorted(portions, key=lambda x: (x.get('sequenceNumber') or 999, x.get('id') or 0))[0]
    amount = p.get('amount')
    if amount is None:
        amount = p.get('value')
    mu = p.get('measureUnit') or {}
    unit_name = (mu.get('abbreviation') or mu.get('name') or '').strip()
    gw = p.get('gramWeight')
    parts = []
    if amount not in (None, ''):
        try:
            amount_f = float(amount)
            parts.append(f'{amount_f:g}')
        except (TypeError, ValueError):
            parts.append(str(amount))
    if unit_name:
        parts.append(unit_name)
    label = ' '.join(parts).strip() or 'porção'
    if gw not in (None, ''):
        try:
            return f'{label} ({float(gw):g} g)'[:80]
        except (TypeError, ValueError):
            pass
    return label[:80] or '100 g'


def _macros_from_nutrients(amounts: Dict[int, float]) -> dict:
    protein = float(amounts.get(1003) or 0)
    fat = float(amounts.get(1004) or 0)
    carb = float(amounts.get(1005) or 0)
    energy = amounts.get(1008)
    if energy is None and 1062 in amounts:
        energy = float(amounts[1062]) / 4.184
    energy = float(energy or 0)
    cal_p = round(protein * 4, 2)
    cal_g = round(fat * 9, 2)
    cal_c = round(carb * 4, 2)
    return {
        'qtd_proteina': protein,
        'qtd_gordura': fat,
        'qtd_carboidratos': carb,
        'cal_proteina': cal_p,
        'cal_gordura': cal_g,
        'cal_carboidratos': cal_c,
        'cal_total': round(energy, 2) if energy else round(cal_p + cal_g + cal_c, 2),
    }


def _extract_nutrient_rows(food: dict) -> Tuple[List[dict], Dict[int, float]]:
    rows = []
    amounts: Dict[int, float] = {}
    seen_names = set()
    for item in food.get('foodNutrientes') or food.get('foodNutrients') or []:
        nut = item.get('nutrient') or {}
        nid = nut.get('id')
        if nid in SKIP_NUTRIENT_IDS:
            continue
        amount = item.get('amount')
        if amount is None:
            continue
        try:
            qtd = float(amount)
        except (TypeError, ValueError):
            continue
        if nid is not None:
            amounts[int(nid)] = qtd
        nome, unidade = _nutrient_label(nut)
        # Prefer mapped Portuguese label; keep first occurrence of each name
        key = nome.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        rows.append({
            'nutriente': nome,
            'quantidade': qtd,
            'unidade': unidade,
            'fator': 1.0,
        })
    # Prefer kcal Energy label even if kJ was skipped
    return rows, amounts


def load_foundation_foods(source: Union[str, Path, BinaryIO]) -> List[dict]:
    """Load FoundationFoods array from .json path, .zip path, or file-like object."""
    data = _read_json_payload(source)
    foods = data.get('FoundationFoods') or data.get('foundationFoods')
    if foods is None and isinstance(data, list):
        foods = data
    if not isinstance(foods, list):
        raise ValueError('JSON inválido: esperado array FoundationFoods')
    return [f for f in foods if isinstance(f, dict) and f.get('fdcId')]


def _read_json_payload(source: Union[str, Path, BinaryIO]) -> dict:
    if hasattr(source, 'read'):
        raw = source.read()
        if isinstance(raw, str):
            raw = raw.encode('utf-8')
        return _parse_bytes(raw, getattr(source, 'name', None))
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f'Arquivo não encontrado: {path}')
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path, 'r') as zf:
            names = [n for n in zf.namelist() if n.lower().endswith('.json') and not n.endswith('/')]
            if not names:
                raise ValueError('ZIP sem arquivo JSON')
            # Prefer foundation food json name
            names.sort(key=lambda n: (0 if 'foundation' in n.lower() else 1, len(n)))
            with zf.open(names[0]) as fh:
                return json.load(fh)
    with path.open('rb') as fh:
        return json.load(fh)


def _parse_bytes(raw: bytes, name_hint: Optional[str] = None) -> dict:
    hint = (name_hint or '').lower()
    if hint.endswith('.zip') or raw[:2] == b'PK':
        import io
        with zipfile.ZipFile(io.BytesIO(raw), 'r') as zf:
            names = [n for n in zf.namelist() if n.lower().endswith('.json') and not n.endswith('/')]
            if not names:
                raise ValueError('ZIP sem arquivo JSON')
            names.sort(key=lambda n: (0 if 'foundation' in n.lower() else 1, len(n)))
            with zf.open(names[0]) as fh:
                return json.load(fh)
    return json.loads(raw.decode('utf-8'))


def import_fdc_foundation_foods(
    source: Union[str, Path, BinaryIO],
    *,
    tabela_nome: str = DEFAULT_TABELA_NOME,
    set_official: bool = True,
    batch_size: int = 25,
    deactivate_missing: bool = True,
) -> dict:
    """
    Upsert Foundation Foods into NutTabelaNutrientes / NutAlimento / NutAlimentoNutriente.

    Idempotent by (tabela_id, fdc_id). When set_official=True, activates this table
    and deactivates other nutrient tables so it becomes the primary catalog.
    """
    from nutricao_service import _ensure_nutricao_columns

    _ensure_nutricao_columns()
    foods = load_foundation_foods(source)
    nome_tab = (tabela_nome or DEFAULT_TABELA_NOME).strip()
    if not nome_tab:
        raise ValueError('Nome da tabela é obrigatório')

    tab = NutTabelaNutrientes.query.filter_by(nome=nome_tab).first()
    if not tab:
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
        for a in NutAlimento.query.filter(
            NutAlimento.tabela_id == tab.id,
            NutAlimento.fdc_id.isnot(None),
        ).all()
    }

    created = updated = 0
    nutrient_rows = 0
    seen_fdc = set()
    now = datetime.utcnow()

    for i, food in enumerate(foods, 1):
        fdc_id = int(food['fdcId'])
        seen_fdc.add(fdc_id)
        desc = (food.get('description') or f'FDC {fdc_id}').strip()
        nome = desc.upper()[:200]
        nut_rows, amounts = _extract_nutrient_rows(food)
        macros = _macros_from_nutrients(amounts)
        alim = existing.get(fdc_id)
        if alim is None:
            alim = NutAlimento(tabela_id=tab.id, fdc_id=fdc_id)
            db.session.add(alim)
            existing[fdc_id] = alim
            created += 1
        else:
            updated += 1

        alim.nome = nome
        alim.ativo = True
        alim.ref_consumo = _ref_consumo(food)
        alim.cal_carboidratos = macros['cal_carboidratos']
        alim.cal_gordura = macros['cal_gordura']
        alim.cal_proteina = macros['cal_proteina']
        alim.cal_total = macros['cal_total']
        alim.qtd_carboidratos = macros['qtd_carboidratos']
        alim.qtd_gordura = macros['qtd_gordura']
        alim.qtd_proteina = macros['qtd_proteina']
        alim.ultima_alteracao = now
        db.session.flush()

        NutAlimentoNutriente.query.filter_by(alimento_id=alim.id).delete()
        for n in nut_rows:
            db.session.add(NutAlimentoNutriente(
                alimento_id=alim.id,
                nutriente=n['nutriente'],
                quantidade=n['quantidade'],
                unidade=n['unidade'],
                fator=n['fator'],
            ))
            nutrient_rows += 1

        if i % max(1, batch_size) == 0:
            db.session.commit()

    deactivated = 0
    if deactivate_missing:
        for fdc_id, alim in existing.items():
            if fdc_id not in seen_fdc and alim.ativo:
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
    }
