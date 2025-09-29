import pymysql

conn = pymysql.connect(host='127.0.0.1', user='root', password='saogeraldo2025')

with conn.cursor() as cursor:
    cursor.execute("CREATE DATABASE IF NOT EXISTS meuappdb")

conn.close()
print("Banco de dados criado com sucesso!")
