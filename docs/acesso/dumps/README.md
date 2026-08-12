# Dump MySQL — Controle de Acesso

Snapshot das tabelas `acesso_*` do banco `meuappdb` para restaurar em outro servidor.

## Arquivo

- `dumps/meuappdb_acesso_20260812.sql` (~82 MB)

## Tabelas incluidas

Todas as tabelas com prefixo `acesso_` (pessoas, visitantes, eventos, equipamentos, empresas, ambientes, refeicoes, estacionamentos, veiculos, permissoes, etc.), incluindo `acesso_pessoas.foto` e `acesso_visitantes.foto` (LONGTEXT).

Nao inclui tabelas de outros modulos (chamados, nutricao, etc.).

## Restore

Crie o banco (se necessario) e importe:

```bash
mysql -u USER -p -e "CREATE DATABASE IF NOT EXISTS meuappdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u USER -p meuappdb < meuappdb_acesso_20260812.sql
```

Se o dump estiver compactado (`.sql.gz`):

```bash
gunzip -c meuappdb_acesso_YYYYMMDD.sql.gz | mysql -u USER -p meuappdb
```

## Aviso LGPD / PII

Este dump contem dados pessoais (nomes, CPF, fotos e eventos de acesso). O repositorio **meuapp** esta **publico** no GitHub — trate o arquivo como sensivel, restrinja quem baixa e considere tornar o repositorio privado ou remover o dump apos a migracao.

## Geracao

Gerado com `mysqldump --single-transaction` a partir de `meuappdb` filtrando `acesso_%`.
