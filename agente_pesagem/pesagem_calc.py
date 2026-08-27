"""Cálculo de bruto / tara / líquido do agente de pesagem (sem GUI)."""
from __future__ import annotations


def parse_peso_digitado(texto) -> float | None:
    """Converte texto do operador (12,5 / 12.5 / 5 kg) em kg."""
    if texto is None:
        return None
    raw = str(texto).strip().lower().replace('kg', '').replace(' ', '')
    raw = raw.replace(',', '.')
    if not raw:
        return None
    try:
        valor = float(raw)
    except (TypeError, ValueError):
        return None
    if valor != valor or abs(valor) > 99999:  # NaN ou absurdo
        return None
    return round(valor, 4)


def calcular_pesos(bruto, tara=0.0) -> dict:
    """Líquido = bruto − tara. Tara fixa do operador; bruto vem da balança."""
    try:
        b = float(bruto if bruto is not None else 0.0)
    except (TypeError, ValueError):
        b = 0.0
    try:
        t = float(tara if tara is not None else 0.0)
    except (TypeError, ValueError):
        t = 0.0
    liq = round(b - t, 4)
    return {
        'peso_bruto': round(b, 4),
        'tara': round(t, 4),
        'peso_liquido': liq,
        'peso': liq,
    }


def pesos_ja_pesado(liquido, tara=0.0) -> dict:
    """Produto já pesado: o operador informa o líquido (tara opcional do recipiente)."""
    try:
        liq = float(liquido)
    except (TypeError, ValueError):
        liq = 0.0
    try:
        t = float(tara if tara is not None else 0.0)
    except (TypeError, ValueError):
        t = 0.0
    bruto = round(liq + t, 4)
    liq = round(liq, 4)
    return {
        'peso_bruto': bruto,
        'tara': round(t, 4),
        'peso_liquido': liq,
        'peso': liq,
    }


def bruto_da_leitura(data: dict) -> float | None:
    """Peso na plataforma (bruto). Prefere peso_bruto; senão o peso ao vivo."""
    if not isinstance(data, dict):
        return None
    for chave in ('peso_bruto', 'peso'):
        if data.get(chave) is None:
            continue
        try:
            return float(data[chave])
        except (TypeError, ValueError):
            continue
    return None
