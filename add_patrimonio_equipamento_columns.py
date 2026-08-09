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
        # Verificar se a coluna 'patrimonio' existe
        cursor.execute("SHOW COLUMNS FROM chamados LIKE 'patrimonio'")
        result = cursor.fetchone()
        if not result:
            # Adicionar a coluna 'patrimonio'
            cursor.execute("ALTER TABLE chamados ADD COLUMN patrimonio VARCHAR(50)")
            print("Coluna 'patrimonio' adicionada com sucesso.")
        else:
            print("Coluna 'patrimonio' já existe.")

        # Verificar se a coluna 'equipamento' existe
        cursor.execute("SHOW COLUMNS FROM chamados LIKE 'equipamento'")
        result = cursor.fetchone()
        if not result:
            # Adicionar a coluna 'equipamento'
            cursor.execute("ALTER TABLE chamados ADD COLUMN equipamento VARCHAR(100)")
            print("Coluna 'equipamento' adicionada com sucesso.")
        else:
            print("Coluna 'equipamento' já existe.")

    connection.commit()
finally:
    connection.close()
