"""Configuração central do banco MySQL para o meuapp."""
import os
from urllib.parse import unquote, urlparse

MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'saogeraldo2025')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'meuappdb')

SQLALCHEMY_DATABASE_URI = os.environ.get(
    'DATABASE_URL',
    f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}'
)

# Colunas do model Equipamento. O app cria no MySQL as que a tabela ainda não tiver.
# equipamento espelha nome_equipamento (código antigo SELECT essa coluna).
EQUIPAMENTOS_COLUNAS_DDL = {
    'equipamento': "VARCHAR(100) NULL DEFAULT ''",
    'nome_equipamento': 'VARCHAR(100) NULL',
    'marca': 'VARCHAR(100) NULL',
    'modelo': 'VARCHAR(100) NULL',
    'numero_serie': 'VARCHAR(50) NULL',
    'patrimonio': 'VARCHAR(50) NULL',
    'localizacao': 'VARCHAR(100) NULL',
    'setor': 'VARCHAR(100) NULL',
    'local': 'VARCHAR(200) NULL',
    'ativo': 'TINYINT(1) NOT NULL DEFAULT 1',
    'data_compra': 'DATE NULL',
    'data_manutencao': 'DATE NULL',
    'data_criacao': 'DATETIME NULL',
    'atualizado_em': 'DATETIME NULL',
    'cliente_id': 'INT NULL',
    'tipo_recurso': "VARCHAR(40) NULL DEFAULT 'Estação'",
    'grupo_id': 'INT NULL',
    'usuario_equipamento': 'VARCHAR(120) NULL',
    'ip': 'VARCHAR(45) NULL',
    'is_agente': 'TINYINT(1) NOT NULL DEFAULT 0',
}

# SMTP para redefinição de senha (pode sobrescrever por variável de ambiente)
MAIL_SERVER = os.environ.get('MAIL_SERVER', '')
MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', '1') not in ('0', 'false', 'False')
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_FROM = os.environ.get('MAIL_FROM', MAIL_USERNAME or 'nao-responda@saogeraldoservice.com.br')


def _params_mysql(uri=None):
    raw = uri or SQLALCHEMY_DATABASE_URI or ''
    if 'sqlite' in raw.lower():
        return None
    parsed = urlparse(raw.replace('mysql+pymysql://', 'mysql://', 1).replace('mysql+mysqldb://', 'mysql://', 1))
    if parsed.scheme not in ('mysql', 'mariadb'):
        host = MYSQL_HOST
        if not host:
            return None
        return {
            'host': MYSQL_HOST,
            'port': int(MYSQL_PORT or 3306),
            'user': MYSQL_USER,
            'password': MYSQL_PASSWORD,
            'database': MYSQL_DATABASE,
        }
    dbname = (parsed.path or '/meuappdb').lstrip('/').split('?')[0] or MYSQL_DATABASE
    return {
        'host': parsed.hostname or MYSQL_HOST,
        'port': parsed.port or int(MYSQL_PORT or 3306),
        'user': unquote(parsed.username or MYSQL_USER or 'root'),
        'password': unquote(parsed.password or MYSQL_PASSWORD or ''),
        'database': dbname,
    }


def forcar_colunas_equipamentos(uri=None):
    """Cria no MySQL as colunas do model que a tabela equipamentos ainda não tem.

    Usa PyMySQL em autocommit — não depende da sessão SQLAlchemy. Idempotente.
    """
    params = _params_mysql(uri)
    if not params:
        return False
    try:
        import pymysql
    except ImportError:
        return False
    try:
        conn = pymysql.connect(
            host=params['host'],
            port=int(params['port']),
            user=params['user'],
            password=params['password'],
            database=params['database'],
            autocommit=True,
            charset='utf8mb4',
        )
    except Exception as exc:
        print('Aviso ao conectar MySQL para alinhar equipamentos:', exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE 'equipamentos'")
            if not cur.fetchone():
                return False
            cur.execute('SHOW COLUMNS FROM equipamentos')
            cols = {str(row[0]).lower() for row in cur.fetchall()}
            for name, ddl in EQUIPAMENTOS_COLUNAS_DDL.items():
                if name.lower() in cols:
                    continue
                try:
                    cur.execute(
                        f'ALTER TABLE equipamentos ADD COLUMN `{name}` {ddl}'
                    )
                    cols.add(name.lower())
                    print(f'Schema equipamentos: criada coluna {name}')
                except Exception as exc:
                    print(f'Aviso: não criou equipamentos.{name}: {exc}')
            if 'equipamento' in cols and 'nome_equipamento' in cols:
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
        return True
    except Exception as exc:
        print('Aviso ao alinhar colunas de equipamentos:', exc)
        return False
    finally:
        conn.close()
