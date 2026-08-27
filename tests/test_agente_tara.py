#!/usr/bin/env python3
"""Tara digitável, líquido = bruto − tara, e envio de roupa já pesada (sem GUI)."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AGENTE_DIR = os.path.join(ROOT, 'agente_pesagem')
AGENTE_PY = os.path.join(AGENTE_DIR, 'agente_pesagem.py')
sys.path.insert(0, AGENTE_DIR)

from pesagem_calc import (  # noqa: E402
    bruto_da_leitura,
    calcular_pesos,
    parse_peso_digitado,
    pesos_ja_pesado,
)


class TaraFixaTest(unittest.TestCase):
    def test_parse_peso_digitado(self):
        self.assertEqual(parse_peso_digitado('12,50'), 12.5)
        self.assertEqual(parse_peso_digitado('12.5'), 12.5)
        self.assertEqual(parse_peso_digitado(' 5 kg '), 5.0)
        self.assertEqual(parse_peso_digitado('0'), 0.0)
        self.assertIsNone(parse_peso_digitado(''))
        self.assertIsNone(parse_peso_digitado('abc'))
        self.assertIsNone(parse_peso_digitado(None))

    def test_liquido_e_bruto_menos_tara(self):
        pesos = calcular_pesos(10.0, 1.25)
        self.assertEqual(pesos['peso_bruto'], 10.0)
        self.assertEqual(pesos['tara'], 1.25)
        self.assertEqual(pesos['peso_liquido'], 8.75)
        self.assertEqual(pesos['peso'], 8.75)

    def test_tara_zero_liquido_igual_bruto(self):
        pesos = calcular_pesos(7.2, 0)
        self.assertEqual(pesos['peso_liquido'], 7.2)
        self.assertEqual(pesos['peso_bruto'], 7.2)

    def test_tara_fixa_ignora_tara_da_balanca(self):
        bruto = bruto_da_leitura({
            'peso': 8.0,
            'peso_bruto': 10.0,
            'tara': 2.0,
            'peso_liquido': 8.0,
        })
        self.assertEqual(bruto, 10.0)
        pesos = calcular_pesos(bruto, tara=0.5)
        self.assertEqual(pesos['peso_liquido'], 9.5)
        self.assertNotEqual(pesos['tara'], 2.0)

    def test_ja_pesado_envia_liquido(self):
        pesos = pesos_ja_pesado(12.34)
        self.assertEqual(pesos['peso_liquido'], 12.34)
        self.assertEqual(pesos['peso'], 12.34)
        self.assertEqual(pesos['peso_bruto'], 12.34)
        self.assertEqual(pesos['tara'], 0.0)

    def test_ja_pesado_com_tara_opcional(self):
        pesos = pesos_ja_pesado(10.0, tara=1.5)
        self.assertEqual(pesos['peso_liquido'], 10.0)
        self.assertEqual(pesos['peso_bruto'], 11.5)
        self.assertEqual(pesos['tara'], 1.5)

    def test_visor_e_botao_no_codigo(self):
        with open(AGENTE_PY, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn("text='Líquido'", src)
        self.assertIn("text='Enviar roupa já pesada'", src)
        self.assertIn("text='Aplicar tara'", src)
        self.assertIn("self.ent_tara = tk.Entry(", src)
        self.assertIn('_preview_tara_digitada', src)
        self.assertIn("origem='ja_pesado'", src)
        self.assertIn("APP_VERSION = '1.5.0'", src)
        self.assertIn("self.title('Roupa já pesada')", src)
        self.assertIn("self.var_tara = tk.StringVar", src)
        led = src.split('class LedPesoDisplay', 1)[1][:900]
        self.assertIn("text='Líquido'", led)
        self.assertNotIn("text='Peso'", led)

    def test_default_config_tem_tara_fixa(self):
        with open(AGENTE_PY, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn("'tara_fixa': 0.0", src)

    def test_dashboard_mostra_origem_roupa_ja_pesada(self):
        path = os.path.join(ROOT, 'templates_pesagem', 'pesagem_dashboard.html')
        with open(path, encoding='utf-8') as fh:
            html = fh.read()
        self.assertIn('Roupa já pesada', html)


if __name__ == '__main__':
    unittest.main()
