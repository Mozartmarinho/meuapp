import pymysql

# Conexão com o banco de dados
connection = pymysql.connect(
    host='127.0.0.1',
    user='root',
    password='saogeraldo2025',
    database='meuappdb'
)

try:
    with connection.cursor() as cursor:
        # Verificar colunas da tabela chamados
        cursor.execute("SHOW COLUMNS FROM chamados")
        columns = cursor.fetchall()
        print("Colunas da tabela 'chamados':")
        for column in columns:
            print(f"- {column[0]}: {column[1]}")
finally:
    connection.close()
