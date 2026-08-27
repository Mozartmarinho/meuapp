"""Garante a coluna legado equipamentos.equipamento (MySQL 1054 na listagem)."""


def run(engine):
    from sqlalchemy import text

    dialect = engine.dialect.name
    conn = engine.connect()
    try:
        def column_names():
            if dialect == 'sqlite':
                rows = conn.execute(text('PRAGMA table_info(equipamentos)'))
                return {str(row[1]) for row in rows}
            rows = conn.execute(text(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND LOWER(TABLE_NAME) = 'equipamentos'"
            ))
            return {str(row[0]) for row in rows}

        try:
            names = {n.lower() for n in column_names()}
        except Exception as exc:
            print('SKIP equipamentos (tabela ausente?):', exc)
            return
        if not names:
            print('SKIP: tabela equipamentos não existe')
            return
        if 'equipamento' not in names:
            trans = conn.begin()
            try:
                if dialect == 'sqlite':
                    conn.execute(text(
                        "ALTER TABLE equipamentos ADD COLUMN equipamento VARCHAR(100) DEFAULT ''"
                    ))
                else:
                    conn.execute(text(
                        "ALTER TABLE equipamentos ADD COLUMN equipamento "
                        "VARCHAR(100) NULL DEFAULT ''"
                    ))
                trans.commit()
                print('OK: ADD equipamentos.equipamento')
            except Exception as exc:
                trans.rollback()
                msg = str(exc)
                if 'Duplicate' in msg or '1060' in msg or 'duplicate column' in msg.lower():
                    print('SKIP (já existe): equipamentos.equipamento')
                else:
                    raise
        trans = conn.begin()
        try:
            conn.execute(text(
                "UPDATE equipamentos SET equipamento = nome_equipamento "
                "WHERE (equipamento IS NULL OR equipamento = '') "
                "AND nome_equipamento IS NOT NULL AND nome_equipamento != ''"
            ))
            trans.commit()
            print('OK: sync equipamentos.equipamento')
        except Exception as exc:
            trans.rollback()
            print('SKIP sync equipamento:', exc)
    finally:
        conn.close()
