#!/usr/bin/env python3
"""Layout Pimaco 6080: medidas oficiais e posicionamento em mm."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from nutricao_service import (  # noqa: E402
    _posicoes_etiquetas,
    _resolver_modelo_etiqueta,
    GEOMETRIA_ETIQUETA,
)


class Etiqueta6080LayoutTest(unittest.TestCase):
    def test_medidas_oficiais_6080(self):
        g = GEOMETRIA_ETIQUETA['6080']
        self.assertEqual(g['page'], 'letter')
        self.assertEqual(g['page_w'], 215.9)
        self.assertEqual(g['page_h'], 279.4)
        self.assertEqual(g['m_top'], 12.7)
        self.assertEqual(g['m_left'], 4.8)
        self.assertEqual(g['label_w'], 66.7)
        self.assertEqual(g['label_h'], 25.4)
        self.assertEqual(g['gap_x'], 3.1)
        # 3 colunas + 2 gutters + margens laterais = largura da folha
        total = g['m_left'] + 3 * g['label_w'] + 2 * g['gap_x'] + g['m_right']
        self.assertAlmostEqual(total, 215.9, places=1)

    def test_resolver_inclui_posicoes(self):
        from app import create_app
        from models import db
        app = create_app()
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        with app.app_context():
            db.create_all()
            m = _resolver_modelo_etiqueta('6080')
            self.assertEqual(m['cols'], 3)
            self.assertEqual(m['rows'], 10)
            self.assertEqual(len(m['posicoes']), 30)
            self.assertEqual(m['posicoes'][0]['top'], 12.7)
            self.assertEqual(m['posicoes'][0]['left'], 4.8)
            # 2ª coluna
            self.assertAlmostEqual(m['posicoes'][1]['left'], 4.8 + 66.7 + 3.1, places=1)
            # 2ª linha
            self.assertAlmostEqual(m['posicoes'][3]['top'], 12.7 + 25.4, places=1)
            # 3ª coluna não ultrapassa a folha
            self.assertLess(
                m['posicoes'][2]['left'] + m['label_w'],
                m['page_w'] + 0.05,
            )

    def test_posicoes_3x10(self):
        g = GEOMETRIA_ETIQUETA['6080']
        pos = _posicoes_etiquetas(g, 3, 10)
        self.assertEqual(len(pos), 30)
        self.assertEqual(pos[-1]['top'], round(12.7 + 9 * 25.4, 2))
        self.assertEqual(pos[-1]['left'], round(4.8 + 2 * 69.8, 2))


if __name__ == '__main__':
    unittest.main()
