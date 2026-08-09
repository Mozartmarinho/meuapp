import pymysql

# Connect to the database
conn = pymysql.connect(host='127.0.0.1', user='root', password='saogeraldo2025', database='meuappdb')

with conn.cursor() as cursor:
    # Add the use_tls column
    cursor.execute("ALTER TABLE sistema_config ADD COLUMN use_tls BOOLEAN DEFAULT TRUE;")

conn.commit()
conn.close()
print("Coluna 'use_tls' adicionada com sucesso à tabela 'sistema_config'!")
