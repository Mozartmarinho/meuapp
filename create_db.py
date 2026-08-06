import pymysql
from db_config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE

conn = pymysql.connect(
    host=MYSQL_HOST,
    port=int(MYSQL_PORT),
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
)

with conn.cursor() as cursor:
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

conn.close()
print(f"Banco de dados '{MYSQL_DATABASE}' criado/verificado com sucesso!")
