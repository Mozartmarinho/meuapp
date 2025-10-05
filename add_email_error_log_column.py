import mysql.connector
from config import DB_CONFIG

def add_email_error_log_column():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Verificar se a coluna já existe
        cursor.execute("SHOW COLUMNS FROM sistema_config LIKE 'email_error_log'")
        if cursor.fetchone():
            print("A coluna 'email_error_log' já existe.")
            return

        # Adicionar a coluna
        cursor.execute("ALTER TABLE sistema_config ADD COLUMN email_error_log TEXT")
        conn.commit()
        print("Coluna 'email_error_log' adicionada com sucesso à tabela 'sistema_config'.")

    except mysql.connector.Error as err:
        print(f"Erro ao adicionar coluna: {err}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_email_error_log_column()
