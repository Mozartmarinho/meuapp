"""Adiciona colunas faltantes para compatibilidade Linux com o app GitHub."""


def run(engine):
    statements = [
        "ALTER TABLE clientes ADD COLUMN telefone VARCHAR(20) NULL",
        "ALTER TABLE clientes ADD COLUMN responsavel VARCHAR(100) NULL",
        "ALTER TABLE equipamentos ADD COLUMN numero_serie VARCHAR(50) NULL",
        "ALTER TABLE equipamentos ADD COLUMN data_manutencao DATE NULL",
    ]
    conn = engine.connect()
    try:
        for stmt in statements:
            trans = conn.begin()
            try:
                conn.execute(stmt)
                trans.commit()
                print("OK:", stmt)
            except Exception as e:
                trans.rollback()
                # Já existe
                if "Duplicate column" in str(e) or "1060" in str(e):
                    print("SKIP (já existe):", stmt)
                else:
                    raise
    finally:
        conn.close()
