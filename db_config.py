"""Configuração central do banco MySQL para o meuapp."""
import os

MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'saogeraldo2025')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'meuappdb')

SQLALCHEMY_DATABASE_URI = os.environ.get(
    'DATABASE_URL',
    f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}'
)


def forcar_coluna_equipamento():
    """Cria equipamentos.equipamento no MySQL (autocommit). Idempotente.

    O SELECT antigo do cadastro pede essa coluna. Sem ela o MySQL 1054 quebra
    /equipamentos. Não usa a sessão do SQLAlchemy (DDL fora de transação).
    """
    uri = (SQLALCHEMY_DATABASE_URI or '').lower()
    if 'sqlite' in uri:
        return False
    if os.environ.get('MEUAPP_SKIP_SCHEMA_FIX', '').strip().lower() in ('1', 'true', 'yes'):
        return False
    try:
        import pymysql
    except Exception as exc:
        print('Aviso: pymysql indisponível para forçar equipamentos.equipamento:', exc)
        return False
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=int(MYSQL_PORT),
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            autocommit=True,
            charset='utf8mb4',
        )
    except Exception as exc:
        print('Aviso: não conectou no MySQL para forçar equipamentos.equipamento:', exc)
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND LOWER(TABLE_NAME)='equipamentos' "
            "AND COLUMN_NAME='equipamento'",
            (MYSQL_DATABASE,),
        )
        existe = int(cur.fetchone()[0] or 0)
        if not existe:
            cur.execute(
                "ALTER TABLE equipamentos "
                "ADD COLUMN `equipamento` VARCHAR(100) NULL DEFAULT ''"
            )
            print('FORÇADO: coluna equipamentos.equipamento criada.')
        else:
            try:
                cur.execute(
                    "ALTER TABLE equipamentos MODIFY COLUMN `equipamento` "
                    "VARCHAR(100) NULL DEFAULT ''"
                )
            except Exception:
                pass
        cur.execute(
            "UPDATE equipamentos SET equipamento = nome_equipamento "
            "WHERE (equipamento IS NULL OR equipamento = '') "
            "AND nome_equipamento IS NOT NULL AND nome_equipamento != ''"
        )
        cur.execute(
            "UPDATE equipamentos SET nome_equipamento = equipamento "
            "WHERE (nome_equipamento IS NULL OR nome_equipamento = '') "
            "AND equipamento IS NOT NULL AND equipamento != ''"
        )
        cur.close()
        return True
    except Exception as exc:
        print('Aviso ao forçar equipamentos.equipamento:', exc)
        return False
    finally:
        conn.close()

# SMTP para redefinição de senha (pode sobrescrever por variável de ambiente)
MAIL_SERVER = os.environ.get('MAIL_SERVER', '')
MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', '1') not in ('0', 'false', 'False')
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_FROM = os.environ.get('MAIL_FROM', MAIL_USERNAME or 'nao-responda@saogeraldoservice.com.br')
