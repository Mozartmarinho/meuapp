import pymysql

# Connect with password
conn = pymysql.connect(host='127.0.0.1', user='root', password='saogeraldo2025')

with conn.cursor() as cursor:
    # Set password for root (if necessary)
    cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY 'saogeraldo2025';")
    # Create database
    cursor.execute("CREATE DATABASE IF NOT EXISTS meuappdb;")

conn.commit()
conn.close()
print("Senha do root definida e banco de dados criado com sucesso!")
