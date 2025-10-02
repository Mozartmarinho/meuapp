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
        # Verifica se a coluna 'feito' já existe
        cursor.execute("SHOW COLUMNS FROM chamados LIKE 'feito'")
        result = cursor.fetchone()
        if not result:
            # Adiciona a coluna 'feito'
            cursor.execute("ALTER TABLE chamados ADD COLUMN feito TEXT")
            print("Coluna 'feito' adicionada com sucesso.")
        else:
            print("Coluna 'feito' já existe.")
    connection.commit()
finally:
    connection.close()
