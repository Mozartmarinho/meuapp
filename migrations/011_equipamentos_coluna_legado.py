"""Cria no MySQL todas as colunas do model Equipamento que a tabela ainda não tem."""

from db_config import EQUIPAMENTOS_COLUNAS_DDL


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
        for col, ddl in EQUIPAMENTOS_COLUNAS_DDL.items():
            if col.lower() in names:
                continue
            trans = conn.begin()
            try:
                conn.execute(text(
                    f'ALTER TABLE equipamentos ADD COLUMN `{col}` {ddl}'
                ))
                trans.commit()
                names.add(col.lower())
                print('OK: ADD equipamentos.' + col)
            except Exception as exc:
                trans.rollback()
                msg = str(exc)
                if 'Duplicate' in msg or '1060' in msg or 'duplicate column' in msg.lower():
                    print('SKIP (já existe): equipamentos.' + col)
                    names.add(col.lower())
                else:
                    raise
        if 'equipamento' in names and 'nome_equipamento' in names:
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
