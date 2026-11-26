#!/usr/bin/env python3
"""Backup geral: horário configurável, compactação, envio diário e restauração."""
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, date
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['BACKUP_DIR'] = tempfile.mkdtemp(prefix='meuapp-backup-')

from app import create_app  # noqa: E402
from models import ConfiguracaoEmail, Usuario, db  # noqa: E402
from password_utils import generate_password_hash  # noqa: E402
from backup_service import (  # noqa: E402
    HORARIO_PADRAO,
    comprimir_xz,
    descomprimir_backup,
    deve_enviar_backup,
    normalizar_horario,
    validar_arquivo_sql,
)


class HorarioBackupTest(unittest.TestCase):
    def test_padrao_e_validacao(self):
        self.assertEqual(HORARIO_PADRAO, '23:50')
        self.assertEqual(normalizar_horario('23:50'), '23:50')
        self.assertEqual(normalizar_horario('8:05'), '08:05')
        self.assertEqual(normalizar_horario('23:50:00'), '23:50')
        self.assertEqual(normalizar_horario('00:00'), '00:00')
        for invalido in ('24:00', '23:60', '99:99', '2350', '', 'ab:cd'):
            with self.assertRaises(ValueError):
                normalizar_horario(invalido)

    def test_envia_no_horario_configurado_e_nao_repete(self):
        dia = date(2026, 11, 26)
        antes = datetime(2026, 11, 26, 8, 14)
        no_horario = datetime(2026, 11, 26, 8, 15)
        depois = datetime(2026, 11, 26, 8, 37)
        self.assertFalse(deve_enviar_backup(antes, 'a@b.com', '08:15', None, None))
        self.assertTrue(deve_enviar_backup(no_horario, 'a@b.com', '08:15', None, None))
        self.assertTrue(deve_enviar_backup(depois, 'a@b.com', '08:15', None, None))
        self.assertFalse(deve_enviar_backup(depois, 'a@b.com', '08:15', dia, None))
        self.assertFalse(deve_enviar_backup(depois, '', '08:15', None, None))
        self.assertFalse(deve_enviar_backup(datetime(2026, 11, 26, 10, 0), 'a@b.com', '23:50', None, None))
        self.assertTrue(deve_enviar_backup(datetime(2026, 11, 26, 23, 55), 'a@b.com', '23:50', None, None))

    def test_falha_de_envio_espera_antes_de_tentar_de_novo(self):
        agora = datetime(2026, 11, 26, 18, 10)
        tentativa = datetime(2026, 11, 26, 18, 6)
        self.assertFalse(deve_enviar_backup(agora, 'a@b.com', '18:00', None, tentativa, intervalo_retry=300))
        self.assertTrue(deve_enviar_backup(
            datetime(2026, 11, 26, 18, 12),
            'a@b.com',
            '18:00',
            None,
            datetime(2026, 11, 26, 18, 0),
            intervalo_retry=300,
        ))


class CompactacaoBackupTest(unittest.TestCase):
    def test_xz_descompacta_igual_e_fica_menor(self):
        original = b'CREATE TABLE chamados (id INT);\nINSERT INTO chamados VALUES (1);\n' * 4000
        blob = comprimir_xz(original)
        self.assertTrue(blob.startswith(b'\xfd7zXZ\x00'))
        self.assertLess(len(blob), len(original) * 0.2)
        self.assertEqual(descomprimir_backup(blob, 'backup.sql.xz'), original)

    def test_rejeita_comando_perigoso(self):
        fd, nome = tempfile.mkstemp(suffix='.sql')
        os.close(fd)
        try:
            with open(nome, 'wb') as fh:
                fh.write(b'CREATE TABLE t (id INT);\nDROP DATABASE outro;\n')
            with self.assertRaises(ValueError):
                validar_arquivo_sql(__import__('pathlib').Path(nome), 'meuappdb')
        finally:
            os.remove(nome)


class BackupConfigTelaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['TESTING'] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def setUp(self):
        ConfiguracaoEmail.query.delete()
        Usuario.query.delete()
        db.session.commit()
        self.admin = Usuario(
            nome='Mozart Admin',
            email='admin@example.com',
            senha=generate_password_hash('x'),
            is_master=True,
            ativo=True,
        )
        db.session.add(self.admin)
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['user_name'] = self.admin.nome

    def _smtp(self, **extra):
        data = {
            'servidor': 'smtp.exemplo.com',
            'porta': '587',
            'usuario': 'conta@exemplo.com',
            'senha': '',
            'remetente': 'noreply@exemplo.com',
            'usar_tls': 'on',
            'email_backup': 'backup@exemplo.com',
            'backup_horario': '18:30',
        }
        data.update(extra)
        return data

    def test_tela_mostra_horario_padrao_e_restauracao(self):
        pagina = self.client.get('/configuracoes').get_data(as_text=True)
        self.assertIn('name="email_backup"', pagina)
        self.assertIn('name="backup_horario"', pagina)
        self.assertIn('value="23:50"', pagina)
        self.assertIn('Restaurar banco', pagina)
        self.assertIn('RESTAURAR', pagina)
        inicio = self.client.get('/').get_data(as_text=True)
        self.assertIn('name="email_backup"', inicio)
        self.assertIn('name="backup_horario"', inicio)
        self.assertIn('value="23:50"', inicio)
        self.assertIn('Restaurar banco', inicio)
        self.assertIn('todo dia às', inicio)

    def test_salva_email_e_horario_juntos(self):
        resp = self.client.post('/configuracoes', data=self._smtp(), follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('backup@exemplo.com', html)
        self.assertIn('value="18:30"', html)
        self.assertIn('às 18:30', html)
        row = ConfiguracaoEmail.query.get(1)
        self.assertEqual(row.email_backup, 'backup@exemplo.com')
        self.assertEqual(row.backup_horario, '18:30')
        inicio = self.client.get('/').get_data(as_text=True)
        self.assertIn('value="18:30"', inicio)
        self.assertIn('backup@exemplo.com', inicio)

    def test_rejeita_horario_invalido(self):
        resp = self.client.post(
            '/configuracoes',
            data=self._smtp(backup_horario='24:00', email_backup='outro@exemplo.com'),
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 400)
        corpo = resp.get_json()
        self.assertFalse(corpo['ok'])
        self.assertIn('Horário', corpo['message'])
        self.assertIsNone(ConfiguracaoEmail.query.get(1))

    def test_restaurar_exige_confirmacao_e_arquivo_valido(self):
        ruim = self.client.post(
            '/configuracoes/backup/restaurar',
            data={'confirmacao': 'sim', 'arquivo': (io.BytesIO(b'CREATE TABLE t (id INT);\n'), 'a.sql')},
            content_type='multipart/form-data',
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )
        self.assertEqual(ruim.status_code, 400)
        self.assertIn('RESTAURAR', ruim.get_json()['message'])

        perigoso = self.client.post(
            '/configuracoes/backup/restaurar',
            data={
                'confirmacao': 'RESTAURAR',
                'arquivo': (io.BytesIO(b'CREATE TABLE t (id INT);\nDROP DATABASE outro;\n'), 'mau.sql'),
            },
            content_type='multipart/form-data',
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )
        self.assertEqual(perigoso.status_code, 400)
        self.assertIn('apagar', perigoso.get_json()['message'])
        self.assertIsNotNone(Usuario.query.get(self.admin.id))

    def test_agendador_usa_horario_salvo_uma_vez_por_dia(self):
        from backup_service import executar_backup

        row = ConfiguracaoEmail(
            id=1,
            servidor='smtp.exemplo.com',
            porta=587,
            remetente='noreply@exemplo.com',
            email_backup='backup@exemplo.com',
            backup_horario='18:30',
        )
        db.session.add(row)
        db.session.commit()

        def falso_gerar(prefixo='backup_geral'):
            from backup_service import BACKUP_DIR, comprimir_xz
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            path = BACKUP_DIR / f'{prefixo}_teste.sql.xz'
            blob = comprimir_xz(b'CREATE TABLE t (id INT);\nINSERT INTO t VALUES (1);\n')
            path.write_bytes(blob)
            return path, 40, len(blob)

        with patch('backup_service.now_brasilia', return_value=datetime(2026, 11, 26, 18, 29)), \
                patch('backup_service._gerar_arquivo_backup', side_effect=falso_gerar) as gerar, \
                patch('email_service.enviar_email_anexo') as enviar:
            cedo = executar_backup(forcar=False)
            self.assertFalse(cedo['enviado'])
            self.assertEqual(gerar.call_count, 0)

        with patch('backup_service.now_brasilia', return_value=datetime(2026, 11, 26, 18, 41)), \
                patch('backup_service._gerar_arquivo_backup', side_effect=falso_gerar), \
                patch('email_service.enviar_email_anexo') as enviar:
            enviado = executar_backup(forcar=False)
            self.assertTrue(enviado['ok'])
            self.assertTrue(enviado['enviado'])
            self.assertEqual(enviar.call_count, 1)
            self.assertEqual(enviar.call_args[0][0], 'backup@exemplo.com')
            self.assertIn('18:30', enviar.call_args[0][2])
            de_novo = executar_backup(forcar=False)
            self.assertFalse(de_novo['enviado'])
            self.assertEqual(enviar.call_count, 1)

        row = ConfiguracaoEmail.query.get(1)
        self.assertEqual(row.backup_ultimo_dia, date(2026, 11, 26))
        self.assertTrue(row.backup_ultimo_arquivo.endswith('.sql.xz'))


if __name__ == '__main__':
    unittest.main()
