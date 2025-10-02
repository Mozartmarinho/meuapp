import pymysql

# Connect to the database
connection = pymysql.connect(
    host='127.0.0.1',
    user='root',
    password='saogeraldo2025',
    database='meuappdb'
)

try:
    with connection.cursor() as cursor:
        # Check if column exists
        cursor.execute("SHOW COLUMNS FROM chamados LIKE 'data_atendimento'")
        result = cursor.fetchone()
        if not result:
            # Add the column
            cursor.execute("ALTER TABLE chamados ADD COLUMN data_atendimento DATETIME")
            print("Column data_atendimento added successfully.")
        else:
            print("Column data_atendimento already exists.")
    connection.commit()
finally:
    connection.close()
