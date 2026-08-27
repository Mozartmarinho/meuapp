"""Cálculo de bruto / tara / líquido do agente de pesagem (sem GUI)."""
from __future__ import annotations

from datetime import datetime


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
    """Produto/roupa já pesado: o operador informa o líquido (tara opcional do recipiente)."""
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


def formatar_peso_ui(peso: float | None) -> str:
    """Somente o visor: 3 dígitos inteiros + 2 decimais (000.00). Não altera o valor gravado."""
    if peso is None:
        return '000.00'
    try:
        p = float(peso)
    except (TypeError, ValueError):
        return '000.00'
    if p < 0:
        return f'-{abs(p):06.2f}'
    return f'{p:06.2f}'


def formatar_data_hora_envio(valor) -> str:
    """Data/hora compacta para a grade de envios do dia (27/08 10:57)."""
    text = str(valor or '').strip()
    if not text:
        return '—'
    trecho = text.replace('T', ' ')[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'):
        try:
            return datetime.strptime(trecho, fmt).strftime('%d/%m %H:%M')
        except ValueError:
            continue
    return text[:16]


def celulas_envio(leitura: dict) -> tuple:
    """Valores da linha: data/hora, cliente, bruto, tara, líquido, ação excluir."""
    bruto = leitura.get('peso_bruto')
    if bruto is None:
        bruto = leitura.get('peso')
    tara = leitura.get('tara')
    liquido = leitura.get('peso_liquido')
    if liquido is None:
        liquido = leitura.get('peso')
    cliente = (leitura.get('cliente_nome') or '').strip() or '—'
    return (
        formatar_data_hora_envio(leitura.get('data_leitura') or leitura.get('data_hora')),
        cliente,
        formatar_peso_ui(bruto),
        formatar_peso_ui(tara),
        formatar_peso_ui(liquido),
        'Excluir',
    )
