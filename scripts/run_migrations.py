#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplica migrações pendentes em migrations/ (ordem alfabética).

Formatos:
  *.sql → executa statements separados por ;
  *.py  → chama run(engine) ou main()

Tabela de controle: schema_migrations (criada automaticamente).
Compatível com SQLAlchemy 1.x (venv do MeuApp / Python 3.6+).
"""
from __future__ import print_function

import hashlib
import os
import sys
from datetime import datetime

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")
sys.path.insert(0, APP_DIR)


def log(msg):
    print("[{}] {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    sys.stdout.flush()


def file_checksum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_sqlite(engine):
    return "sqlite" in str(engine.url)


def ensure_table(engine):
    if is_sqlite(engine):
        ddl = (
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "filename VARCHAR(255) NOT NULL UNIQUE, "
            "checksum VARCHAR(64) NOT NULL, "
            "applied_at DATETIME NOT NULL)"
        )
    else:
        ddl = (
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "id INT AUTO_INCREMENT PRIMARY KEY, "
            "filename VARCHAR(255) NOT NULL UNIQUE, "
            "checksum VARCHAR(64) NOT NULL, "
            "applied_at DATETIME NOT NULL"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
    conn = engine.connect()
    try:
        trans = conn.begin()
        try:
            conn.execute(ddl)
            trans.commit()
        except Exception:
            trans.rollback()
            raise
    finally:
        conn.close()


def applied_filenames(engine):
    conn = engine.connect()
    try:
        rows = conn.execute("SELECT filename, checksum FROM schema_migrations")
        return {row[0]: row[1] for row in rows}
    finally:
        conn.close()


def mark_applied(engine, filename, checksum):
    conn = engine.connect()
    try:
        trans = conn.begin()
        try:
            if is_sqlite(engine):
                conn.execute(
                    "INSERT INTO schema_migrations (filename, checksum, applied_at) "
                    "VALUES (?, ?, ?)",
                    (filename, checksum, datetime.utcnow()),
                )
            else:
                conn.execute(
                    "INSERT INTO schema_migrations (filename, checksum, applied_at) "
                    "VALUES (%s, %s, %s)",
                    (filename, checksum, datetime.utcnow()),
                )
            trans.commit()
        except Exception:
            trans.rollback()
            raise
    finally:
        conn.close()


def split_sql(sql):
    statements = []
    for part in sql.split(";"):
        lines = [
            ln
            for ln in part.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        if lines:
            statements.append("\n".join(lines))
    return statements


def run_sql_file(engine, path):
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    statements = split_sql(sql)
    conn = engine.connect()
    try:
        trans = conn.begin()
        try:
            for stmt in statements:
                log("  SQL: {}...".format(stmt[:80].replace("\n", " ")))
                conn.execute(stmt)
            trans.commit()
        except Exception:
            trans.rollback()
            raise
    finally:
        conn.close()


def run_py_file(engine, path):
    import importlib.util

    name = os.path.splitext(os.path.basename(path))[0]
    mod_name = "migration_{}".format(name)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "run"):
        module.run(engine)
    elif hasattr(module, "main"):
        module.main()
    else:
        raise RuntimeError(
            "Migração Python {} precisa definir run(engine) ou main()".format(path)
        )


def list_migration_files():
    if not os.path.isdir(MIGRATIONS_DIR):
        os.makedirs(MIGRATIONS_DIR)
        return []
    files = []
    for name in sorted(os.listdir(MIGRATIONS_DIR)):
        if name.startswith("."):
            continue
        if name == "__init__.py":
            continue
        if name.endswith(".sql") or name.endswith(".py"):
            files.append(name)
    return files


def main():
    log("Iniciando migrações em {}".format(MIGRATIONS_DIR))

    from app import app
    from models_updated import db

    with app.app_context():
        engine = db.get_engine(app) if hasattr(db, "get_engine") else db.engine
        ensure_table(engine)
        done = applied_filenames(engine)
        pending = list_migration_files()

        if not pending:
            log("Nenhum arquivo em migrations/ — nada a fazer.")
            return 0

        applied_count = 0
        for filename in pending:
            path = os.path.join(MIGRATIONS_DIR, filename)
            checksum = file_checksum(path)

            if filename in done:
                if done[filename] != checksum:
                    log(
                        "AVISO: {} já aplicada, mas checksum mudou "
                        "(não reexecuta — crie um novo arquivo)".format(filename)
                    )
                else:
                    log("Já aplicada: {}".format(filename))
                continue

            log("Aplicando: {}".format(filename))
            try:
                if filename.endswith(".sql"):
                    run_sql_file(engine, path)
                else:
                    run_py_file(engine, path)
                mark_applied(engine, filename, checksum)
                applied_count += 1
                log("OK: {}".format(filename))
            except Exception as e:
                log("FALHA em {}: {}".format(filename, e))
                raise

        log("Migrações concluídas. Novas aplicadas: {}".format(applied_count))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log("Migração abortada: {}".format(exc))
        sys.exit(1)
