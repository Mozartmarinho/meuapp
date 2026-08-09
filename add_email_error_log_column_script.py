import pymysql

# Connect to the database
conn = pymysql.connect(host='127.0.0.1', user='root', password='saogeraldo2025', database='meuappdb')

with conn.cursor() as cursor:
    # Add the email_error_log column
    cursor.execute("ALTER TABLE sistema_config ADD COLUMN email_error_log TEXT;")

conn.commit()
conn.close()
print("Coluna 'email_error_log' adicionada com sucesso à tabela 'sistema_config'!")
