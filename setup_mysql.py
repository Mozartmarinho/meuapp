import pymysql

# First, try to connect without password
try:
    conn = pymysql.connect(host='127.0.0.1', user='root')
    print("Connected without password")
except pymysql.err.OperationalError as e:
    print(f"Failed to connect without password: {e}")
    # If that fails, try with the expected password
    try:
        conn = pymysql.connect(host='127.0.0.1', user='root', password='saogeraldo2025')
        print("Connected with password")
    except pymysql.err.OperationalError as e2:
        print(f"Failed to connect with password: {e2}")
        exit(1)

with conn.cursor() as cursor:
    # Set password for root
    cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY 'saogeraldo2025';")
    # Create database
    cursor.execute("CREATE DATABASE IF NOT EXISTS meuappdb;")

conn.commit()
conn.close()
print("Senha do root definida e banco de dados criado com sucesso!")
