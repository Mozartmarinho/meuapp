"""Backup geral do banco: compactação máxima, e-mail diário e restauração."""
from __future__ import annotations

import fcntl
import gzip
import io
import logging
import lzma
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from db_config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER
from models import ConfiguracaoEmail, db, fmt_brasilia, now_brasilia

LOG = logging.getLogger('backup_email')

HORARIO_PADRAO = '23:50'
RETRY_SEGUNDOS = 300
LIMITE_UPLOAD = 400 * 1024 * 1024
LIMITE_DESCOMPACTADO = 2 * 1024 * 1024 * 1024
RETENCAO_SEGUNDOS = 30 * 86400
_PRESET_XZ = 9 | lzma.PRESET_EXTREME
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_HORA_RE = re.compile(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?$')

BACKUP_DIR = Path(os.environ.get('BACKUP_DIR') or (Path(__file__).resolve().parent / 'backups' / 'geral'))

_thread_lock = threading.Lock()
_start_lock = threading.Lock()
_scheduler_started = False
_scheduler_fh = None
_dump_help = None


def email_backup_valido(valor: str) -> bool:
    texto = (valor or '').strip().lower()
    return bool(texto) and len(texto) <= 200 and _EMAIL_RE.match(texto) is not None


def normalizar_horario(valor: str) -> str:
    texto = (valor or '').strip()
    encontrado = _HORA_RE.match(texto)
    if not encontrado:
        raise ValueError('Horário inválido. Use HH:MM, entre 00:00 e 23:59.')
    hora = int(encontrado.group(1))
    minuto = int(encontrado.group(2))
    segundo = int(encontrado.group(3) or 0)
    if hora > 23 or minuto > 59 or segundo > 59:
        raise ValueError('Horário inválido. Use HH:MM, entre 00:00 e 23:59.')
    return f'{hora:02d}:{minuto:02d}'


def horario_configurado(valor: str | None) -> str:
    bruto = (valor or '').strip()
    if not bruto:
        return HORARIO_PADRAO
    try:
        return normalizar_horario(bruto)
    except ValueError:
        return HORARIO_PADRAO


def deve_enviar_backup(agora, email, horario, ultimo_dia_ok, ultima_tentativa, intervalo_retry=RETRY_SEGUNDOS) -> bool:
    """True depois do horário configurado, uma vez por dia, com nova tentativa se o envio falhou."""
    if not (email or '').strip():
        return False
    if agora.strftime('%H:%M') < horario_configurado(horario):
        return False
    if ultimo_dia_ok == agora.date():
        return False
    if ultima_tentativa is not None:
        delta = (agora - ultima_tentativa).total_seconds()
        if 0 <= delta < intervalo_retry:
            return False
    return True


def formatar_tamanho(valor) -> str:
    if valor is None:
        return ''
    tamanho = float(valor)
    for unidade in ('B', 'KB', 'MB', 'GB'):
        if tamanho < 1024 or unidade == 'GB':
            if unidade == 'B':
                return f'{int(tamanho)} B'
            return f'{tamanho:.1f} {unidade}'.replace('.', ',')
        tamanho /= 1024.0
    return ''


def comprimir_xz(data: bytes) -> bytes:
    return lzma.compress(data, format=lzma.FORMAT_XZ, preset=_PRESET_XZ)


def ensure_backup_schema() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    if 'configuracao_email' not in set(insp.get_table_names()):
        ConfiguracaoEmail.__table__.create(db.engine, checkfirst=True)
        return
    cols = {c['name'] for c in insp.get_columns('configuracao_email')}
    specs = (
        ('email_backup', 'VARCHAR(200)'),
        ('backup_horario', 'VARCHAR(5)'),
        ('backup_ultimo_dia', 'DATE'),
        ('backup_ultimo_em', 'DATETIME'),
        ('backup_ultima_tentativa_em', 'DATETIME'),
        ('backup_ultimo_arquivo', 'VARCHAR(255)'),
        ('backup_ultimo_bytes', 'BIGINT'),
        ('backup_ultimo_erro', 'TEXT'),
    )
    for nome, tipo in specs:
        if nome in cols:
            continue
        db.session.execute(text(f'ALTER TABLE configuracao_email ADD COLUMN {nome} {tipo}'))
        db.session.commit()
        cols.add(nome)
    if 'backup_horario' in cols:
        db.session.execute(text(
            "UPDATE configuracao_email SET backup_horario = :hora "
            "WHERE backup_horario IS NULL OR backup_horario = ''"
        ), {'hora': HORARIO_PADRAO})
        db.session.commit()


def info_backup() -> dict:
    try:
        ensure_backup_schema()
    except Exception:
        LOG.exception('Falha ao preparar colunas do backup')
        db.session.rollback()
    row = None
    try:
        row = ConfiguracaoEmail.query.get(1)
    except Exception:
        db.session.rollback()
    email = (getattr(row, 'email_backup', None) or '').strip() if row else ''
    horario = horario_configurado(getattr(row, 'backup_horario', None) if row else None)
    ultimo_em = getattr(row, 'backup_ultimo_em', None) if row else None
    erro = (getattr(row, 'backup_ultimo_erro', None) or '').strip() if row else ''
    arquivo = (getattr(row, 'backup_ultimo_arquivo', None) or '').strip() if row else ''
    tamanho = getattr(row, 'backup_ultimo_bytes', None) if row else None
    ultimo_fmt = fmt_brasilia(ultimo_em) if ultimo_em else ''
    bytes_fmt = formatar_tamanho(tamanho) if tamanho else ''
    return {
        'email': email,
        'horario': horario,
        'ultimo_em_fmt': ultimo_fmt,
        'ultimo_bytes_fmt': bytes_fmt,
        'ultimo_erro': erro,
        'tem_arquivo': caminho_backup_atual() is not None,
        'mensagem': _mensagem_status(email, horario, ultimo_fmt, bytes_fmt, erro),
    }


def executar_backup(forcar: bool = False) -> dict:
    try:
        with _operacao():
            return _executar_backup(forcar)
    except Exception as exc:
        LOG.exception('Falha no backup geral')
        db.session.rollback()
        return {'ok': False, 'enviado': False, 'message': _mensagem_erro(exc), 'backup': _info_segura()}


def restaurar_upload(arquivo, confirmacao: str) -> dict:
    if (confirmacao or '').strip() != 'RESTAURAR':
        raise ValueError('Digite RESTAURAR para confirmar a restauração do banco.')
    if arquivo is None or not getattr(arquivo, 'filename', None):
        raise ValueError('Selecione o arquivo de backup.')
    data = arquivo.read(LIMITE_UPLOAD + 1)
    if not data:
        raise ValueError('Arquivo de backup vazio.')
    if len(data) > LIMITE_UPLOAD:
        raise ValueError('Arquivo maior que 400 MB. Envie o backup compactado (.xz).')

    fd, tmp_name = tempfile.mkstemp(prefix='meuapp-restore-', suffix='.sql')
    os.close(fd)
    os.chmod(tmp_name, 0o600)
    tmp = Path(tmp_name)
    try:
        try:
            _descomprimir_para_arquivo(data, arquivo.filename, tmp, LIMITE_DESCOMPACTADO)
            validar_arquivo_sql(tmp, _nome_banco())
        except ValueError:
            raise
        except Exception as exc:
            LOG.exception('Backup inválido na restauração')
            raise ValueError(_mensagem_erro(exc)) from exc

        with _operacao():
            try:
                pre_path, _original, _compactado = _gerar_arquivo_backup(prefixo='pre_restore')
                _aplicar_sql(tmp)
                _apontar_arquivo(pre_path)
                db.session.remove()
                db.engine.dispose()
            except ValueError:
                raise
            except Exception as exc:
                LOG.exception('Falha ao restaurar backup')
                db.session.rollback()
                raise ValueError(_mensagem_erro(exc)) from exc
        nome = _nome_exibicao(arquivo.filename)
        return {
            'ok': True,
            'message': (
                f'Banco restaurado a partir de {nome}. '
                'A cópia de antes da restauração ficou salva no servidor e pode ser baixada '
                'em Configurações para voltar atrás, se precisar.'
            ),
            'backup': _info_segura(),
        }
    finally:
        tmp.unlink(missing_ok=True)


def caminho_backup_atual():
    try:
        row = ConfiguracaoEmail.query.get(1)
    except Exception:
        db.session.rollback()
        return None
    nome = (getattr(row, 'backup_ultimo_arquivo', None) or '').strip() if row else ''
    return _caminho_seguro(nome)


def start_backup_background(app) -> None:
    """Uma thread por processo. Só quem pega o lock roda o horário; os outros tentam de novo se o processo dono cair."""
    global _scheduler_started
    if app.config.get('TESTING'):
        return
    if os.environ.get('BACKUP_EMAIL_DISABLE', '').strip().lower() in ('1', 'true', 'yes'):
        return
    with _start_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    thread = threading.Thread(target=_scheduler_supervise, args=(app,), name='backup-email', daemon=True)
    thread.start()


def _scheduler_supervise(app) -> None:
    global _scheduler_fh
    while True:
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            fh = open(BACKUP_DIR / 'scheduler.lock', 'a+')
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fh.close()
                time.sleep(30)
                continue
            _scheduler_fh = fh
            _scheduler_loop(app)
        except Exception:
            LOG.exception('Agendador do backup diário encerrou')
            time.sleep(30)


def validar_arquivo_sql(path: Path, dbname: str) -> None:
    tamanho = path.stat().st_size
    if tamanho < 20:
        raise ValueError('Backup vazio ou incompleto.')
    with path.open('rb') as fh:
        cabeca = fh.read(300000).upper()
    if not any(marca in cabeca for marca in (b'CREATE TABLE', b'INSERT INTO', b'DROP TABLE')):
        raise ValueError('O arquivo não parece um backup de banco de dados.')
    db_up = (dbname or '').upper().encode()
    proibidos = (b'INTO OUTFILE', b'INTO DUMPFILE', b'LOAD_FILE', b'LOAD DATA')
    with path.open('rb') as fh:
        for linha in fh:
            trecho = linha[:8192].strip().upper()
            if not trecho or trecho.startswith((b'--', b'/*', b'#')):
                continue
            if trecho.startswith(b'DROP DATABASE'):
                raise ValueError('O backup não pode apagar outro banco.')
            if trecho.startswith(b'CREATE DATABASE') or trecho.startswith(b'USE '):
                if not db_up or db_up not in trecho:
                    raise ValueError('O backup aponta para outro banco de dados.')
            for token in proibidos:
                if token in trecho:
                    raise ValueError('O arquivo contém comandos que não fazem parte de um backup.')


def _executar_backup(forcar: bool) -> dict:
    from email_service import enviar_email_anexo, smtp_configurado

    ensure_backup_schema()
    row = _obter_row()
    email = (row.email_backup or '').strip()
    horario = horario_configurado(row.backup_horario)
    agora = now_brasilia()
    if not forcar and not deve_enviar_backup(
        agora,
        email,
        horario,
        row.backup_ultimo_dia,
        row.backup_ultima_tentativa_em,
    ):
        return {'ok': True, 'enviado': False, 'message': '', 'backup': info_backup()}
    if not email:
        return {
            'ok': False,
            'enviado': False,
            'message': 'Cadastre o e-mail que recebe o backup.',
            'backup': info_backup(),
        }
    if not smtp_configurado():
        return {
            'ok': False,
            'enviado': False,
            'message': 'Configure o servidor SMTP e o remetente antes de enviar o backup.',
            'backup': info_backup(),
        }

    row.backup_ultima_tentativa_em = agora
    db.session.commit()
    gerou = False
    try:
        caminho, original, compactado = _gerar_arquivo_backup()
        row.backup_ultimo_arquivo = caminho.name
        row.backup_ultimo_bytes = compactado
        db.session.commit()
        gerou = True
        _enviar_anexo(enviar_email_anexo, email, caminho, original, compactado, agora, horario)
        row.backup_ultimo_dia = agora.date()
        row.backup_ultimo_em = agora
        row.backup_ultimo_erro = None
        db.session.commit()
        return {
            'ok': True,
            'enviado': True,
            'message': (
                f'Backup enviado para {email} às {horario}. '
                f'Compactado: {formatar_tamanho(compactado)} '
                f'(original {formatar_tamanho(original)}).'
            ),
            'backup': info_backup(),
        }
    except Exception as exc:
        LOG.exception('Envio do backup geral falhou')
        db.session.rollback()
        row = _obter_row()
        mensagem = _mensagem_erro(exc)
        row.backup_ultimo_erro = mensagem[:2000]
        db.session.commit()
        if gerou:
            mensagem = (
                f'O backup foi gerado, mas o e-mail não saiu: {mensagem} '
                'O arquivo ficou salvo no servidor e pode ser baixado em Configurações.'
            )
        return {'ok': False, 'enviado': False, 'message': mensagem, 'backup': info_backup()}


def _enviar_anexo(enviar, email, caminho: Path, original: int, compactado: int, agora: datetime, horario: str) -> None:
    assunto = f"Backup geral — {agora.strftime('%d/%m/%Y')}"
    texto = (
        'Backup geral do sistema São Geraldo.\n\n'
        f"Gerado em: {agora.strftime('%d/%m/%Y %H:%M')} (horário de Brasília)\n"
        f'Horário configurado: {horario}\n'
        f'Banco: {_nome_banco()}\n'
        f'Tamanho original: {formatar_tamanho(original)}\n'
        f'Tamanho compactado: {formatar_tamanho(compactado)}\n\n'
        'O anexo está no formato XZ, com compressão máxima.\n'
        'Para restaurar: Opções → Configurações → Restaurar banco.\n'
        'Envie este arquivo e confirme digitando RESTAURAR.\n'
    )
    enviar(email, assunto, texto, caminho.name, caminho.read_bytes())


def _gerar_arquivo_backup(prefixo: str = 'backup_geral'):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    agora = now_brasilia()
    nome = f"{prefixo}_{agora.strftime('%Y%m%d_%H%M%S')}.sql.xz"
    destino = BACKUP_DIR / nome
    parcial = Path(str(destino) + '.part')
    try:
        original = _escrever_dump_xz(parcial)
        if original < 20:
            raise RuntimeError('O backup gerado está vazio.')
        parcial.replace(destino)
    except Exception:
        parcial.unlink(missing_ok=True)
        raise
    _limpar_antigos(preservar=nome)
    return destino, original, destino.stat().st_size


def _escrever_dump_xz(destino: Path) -> int:
    compressor = lzma.LZMACompressor(format=lzma.FORMAT_XZ, preset=_PRESET_XZ)
    original = 0
    with destino.open('wb') as saida:
        def escrever(bloco: bytes) -> None:
            nonlocal original
            if not bloco:
                return
            original += len(bloco)
            compactado = compressor.compress(bloco)
            if compactado:
                saida.write(compactado)

        dialeto = db.engine.dialect.name
        if dialeto == 'mysql':
            _stream_mysqldump(escrever)
        elif dialeto == 'sqlite':
            escrever(_dump_sqlite_bytes())
        else:
            raise RuntimeError('O backup geral está disponível para o banco MySQL.')
        resto = compressor.flush()
        if resto:
            saida.write(resto)
    return original


def _stream_mysqldump(escrever) -> None:
    cnf = _cnf_temporario()
    proc = None
    try:
        proc = subprocess.Popen(
            _mysqldump_cmd(cnf),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        erros = []

        def ler_erro():
            if proc.stderr:
                erros.append(proc.stderr.read())

        leitor = threading.Thread(target=ler_erro, daemon=True)
        leitor.start()
        assert proc.stdout is not None
        while True:
            bloco = proc.stdout.read(256 * 1024)
            if not bloco:
                break
            escrever(bloco)
        try:
            rc = proc.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=15)
            raise RuntimeError('A geração do backup excedeu o tempo limite.')
        leitor.join(timeout=30)
        if rc != 0:
            texto = b''.join(erros).decode('utf-8', errors='replace')
            raise RuntimeError(_mensagem_erro(texto) or f'mysqldump falhou ({rc}).')
    finally:
        if proc and proc.poll() is None:
            proc.kill()
        try:
            os.remove(cnf)
        except OSError:
            pass


def _mysqldump_cmd(cnf: str) -> list:
    cmd = [
        _binario('mysqldump'),
        f'--defaults-extra-file={cnf}',
        '--single-transaction',
        '--quick',
        '--hex-blob',
        '--add-drop-table',
        '--default-character-set=utf8mb4',
        '--no-tablespaces',
        '--routines',
        '--triggers',
        '--events',
    ]
    if _mysqldump_tem_opcao('column-statistics'):
        cmd.append('--column-statistics=0')
    cmd.append(MYSQL_DATABASE)
    return cmd


def _mysqldump_tem_opcao(nome: str) -> bool:
    global _dump_help
    if _dump_help is None:
        try:
            proc = subprocess.run(
                [_binario('mysqldump'), '--help'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=20,
                check=False,
            )
            _dump_help = proc.stdout.decode('utf-8', errors='replace').lower()
        except Exception:
            _dump_help = ''
    return nome.lower() in _dump_help


def _dump_sqlite_bytes() -> bytes:
    raw = db.engine.raw_connection()
    try:
        dbapi = raw
        for attr in ('driver_connection', 'connection'):
            if hasattr(dbapi, 'iterdump'):
                break
            dbapi = getattr(dbapi, attr, dbapi)
        if not hasattr(dbapi, 'iterdump'):
            raise RuntimeError('Não foi possível ler o banco para o backup.')
        return ('\n'.join(dbapi.iterdump()) + '\n').encode('utf-8')
    finally:
        raw.close()


def _aplicar_sql(path: Path) -> None:
    if db.engine.dialect.name == 'mysql':
        _aplicar_mysql(path)
        return
    if db.engine.dialect.name == 'sqlite':
        sql = path.read_text(encoding='utf-8', errors='replace')
        raw = db.engine.raw_connection()
        try:
            dbapi = raw
            for attr in ('driver_connection', 'connection'):
                if hasattr(dbapi, 'executescript'):
                    break
                dbapi = getattr(dbapi, attr, dbapi)
            dbapi.executescript(sql)
            if hasattr(dbapi, 'commit'):
                dbapi.commit()
        finally:
            raw.close()
        return
    raise RuntimeError('A restauração está disponível para o banco MySQL.')


def _aplicar_mysql(path: Path) -> None:
    cnf = _cnf_temporario()
    try:
        cmd = [
            _binario('mysql'),
            f'--defaults-extra-file={cnf}',
            '--default-character-set=utf8mb4',
            '--binary-mode',
            MYSQL_DATABASE,
        ]
        with path.open('rb') as fh:
            proc = subprocess.run(
                cmd,
                stdin=fh,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3600,
                check=False,
            )
        if proc.returncode != 0:
            texto = proc.stderr.decode('utf-8', errors='replace')
            raise RuntimeError(_mensagem_erro(texto) or 'Falha ao restaurar o banco.')
    finally:
        try:
            os.remove(cnf)
        except OSError:
            pass


def _descomprimir_para_arquivo(data: bytes, filename: str, destino: Path, limite: int) -> int:
    tipo = _tipo_compactacao(data, filename)
    total = 0
    with destino.open('wb') as saida:
        if tipo == 'sql':
            if len(data) > limite:
                raise ValueError('Backup grande demais.')
            saida.write(data)
            return len(data)
        if tipo == 'gz':
            try:
                fonte = gzip.GzipFile(fileobj=io.BytesIO(data))
            except Exception as exc:
                raise ValueError('Não foi possível descompactar o arquivo GZ.') from exc
            while True:
                pedaco = fonte.read(1024 * 1024)
                if not pedaco:
                    break
                total += len(pedaco)
                if total > limite:
                    raise ValueError('Backup descompactado grande demais.')
                saida.write(pedaco)
            return total
        dec = lzma.LZMADecompressor()
        idx = 0
        try:
            while not dec.eof:
                if idx < len(data):
                    fim = min(len(data), idx + 1024 * 1024)
                    pedaco = dec.decompress(data[idx:fim])
                    idx = fim
                else:
                    pedaco = dec.decompress(b'')
                if pedaco:
                    total += len(pedaco)
                    if total > limite:
                        raise ValueError('Backup descompactado grande demais.')
                    saida.write(pedaco)
                elif idx >= len(data):
                    break
        except lzma.LZMAError as exc:
            raise ValueError('Não foi possível descompactar o arquivo XZ.') from exc
        if not dec.eof:
            raise ValueError('Arquivo XZ incompleto ou inválido.')
    return total


def descomprimir_backup(data: bytes, filename: str) -> bytes:
    fd, nome = tempfile.mkstemp(prefix='meuapp-backup-', suffix='.sql')
    os.close(fd)
    path = Path(nome)
    try:
        _descomprimir_para_arquivo(data, filename, path, LIMITE_DESCOMPACTADO)
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def _tipo_compactacao(data: bytes, filename: str) -> str:
    nome = (filename or '').lower()
    if data.startswith(b'\xfd7zXZ\x00') or nome.endswith('.xz'):
        return 'xz'
    if data.startswith(b'\x1f\x8b') or nome.endswith('.gz'):
        return 'gz'
    return 'sql'


def _cnf_temporario() -> str:
    fd, path = tempfile.mkstemp(prefix='meuapp-mysql-', suffix='.cnf')
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write('[client]\n')
        fh.write(f'host={_cnf_valor(MYSQL_HOST)}\n')
        fh.write(f'port={int(MYSQL_PORT)}\n')
        fh.write(f'user={_cnf_valor(MYSQL_USER)}\n')
        fh.write(f'password={_cnf_valor(MYSQL_PASSWORD)}\n')
    return path


def _cnf_valor(valor) -> str:
    texto = '' if valor is None else str(valor).replace('\n', '').replace('\r', '')
    return '"' + texto.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _binario(nome: str) -> str:
    path = shutil.which(nome)
    if not path:
        raise RuntimeError(f'O programa {nome} não está instalado no servidor.')
    return path


def _nome_banco() -> str:
    if db.engine.dialect.name == 'mysql':
        return MYSQL_DATABASE
    return 'main'


def _obter_row():
    row = ConfiguracaoEmail.query.get(1)
    if row:
        return row
    row = ConfiguracaoEmail(id=1, backup_horario=HORARIO_PADRAO)
    db.session.add(row)
    db.session.flush()
    return row


def _apontar_arquivo(path: Path) -> None:
    row = _obter_row()
    row.backup_ultimo_arquivo = path.name
    row.backup_ultimo_bytes = path.stat().st_size
    row.backup_ultimo_erro = None
    db.session.commit()


def _caminho_seguro(nome: str):
    if not nome or '/' in nome or '\\' in nome or nome.startswith('.'):
        return None
    base = BACKUP_DIR.resolve()
    path = (base / nome).resolve()
    if path.parent != base or not path.is_file():
        return None
    return path


def _limpar_antigos(preservar: str = '') -> None:
    if not BACKUP_DIR.exists():
        return
    manter = {preservar}
    try:
        row = ConfiguracaoEmail.query.get(1)
        if row and row.backup_ultimo_arquivo:
            manter.add(row.backup_ultimo_arquivo)
    except Exception:
        db.session.rollback()
    limite = time.time() - RETENCAO_SEGUNDOS
    for path in BACKUP_DIR.iterdir():
        if not path.is_file() or path.name in manter:
            continue
        if path.name.endswith('.part'):
            path.unlink(missing_ok=True)
            continue
        if not (path.name.startswith('backup_geral_') or path.name.startswith('pre_restore_')):
            continue
        try:
            if path.stat().st_mtime < limite:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _mensagem_status(email, horario, ultimo_fmt, bytes_fmt, erro) -> str:
    partes = [f'Envio automático às {horario} (horário de Brasília).']
    if not email:
        partes.append('Cadastre o e-mail para ligar o envio.')
    elif ultimo_fmt:
        extra = f'Último envio: {ultimo_fmt}'
        if bytes_fmt:
            extra += f' · {bytes_fmt} compactado'
        partes.append(extra + '.')
    else:
        partes.append('Nenhum backup enviado ainda.')
    if erro:
        partes.append(f'Falha na última tentativa: {erro}')
    return ' '.join(partes)


def _mensagem_erro(exc) -> str:
    texto = exc if isinstance(exc, str) else str(exc or '')
    texto = texto.strip() or 'Falha ao gerar o backup.'
    senha = MYSQL_PASSWORD or ''
    if senha:
        texto = texto.replace(senha, '***')
    texto = ' '.join(texto.split())
    if len(texto) > 500:
        texto = texto[:500] + '…'
    return texto


def _nome_exibicao(filename: str) -> str:
    nome = Path(filename or 'backup').name
    limpo = ''.join(ch for ch in nome if ch.isalnum() or ch in '._- ')
    return (limpo or 'backup')[:80]


def _info_segura() -> dict:
    try:
        return info_backup()
    except Exception:
        db.session.rollback()
        return {
            'email': '',
            'horario': HORARIO_PADRAO,
            'mensagem': '',
            'tem_arquivo': False,
            'ultimo_em_fmt': '',
            'ultimo_bytes_fmt': '',
            'ultimo_erro': '',
        }


@contextmanager
def _operacao():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(BACKUP_DIR / 'operacao.lock', 'a+')
    with _thread_lock:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


def _scheduler_loop(app) -> None:
    time.sleep(20)
    while True:
        try:
            with app.app_context():
                resultado = executar_backup(forcar=False)
            if resultado.get('enviado'):
                LOG.info(resultado.get('message'))
            elif resultado.get('ok') is False and resultado.get('message'):
                LOG.error(resultado.get('message'))
        except Exception:
            LOG.exception('Erro no agendador do backup diário')
        time.sleep(60)
