import pymysql

# Connect without password (assuming root has no password initially)
conn = pymysql.connect(host='127.0.0.1', user='root')

with conn.cursor() as cursor:
    # Set password for root
    cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY 'saogeraldo2025';")
    # Create database
    cursor.execute("CREATE DATABASE IF NOT EXISTS meuappdb;")

conn.commit()
conn.close()
print("Senha do root definida e banco de dados criado com sucesso!")
