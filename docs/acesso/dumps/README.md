# Dump MySQL — Controle de Acesso

Pasta reservada para dumps **locais** de migração das tabelas `acesso_*`.

## LGPD

Dumps com dados pessoais (nomes, CPF, fotos, eventos) **não devem ser enviados ao GitHub**.

O arquivo `meuappdb_acesso_20260812.sql` foi removido do repositório após a restauração no servidor.

## Uso local (não versionar)

```bash
# gerar (apenas no servidor / máquina segura)
mysqldump -u USER -p --single-transaction meuappdb $(mysql -u USER -p -N -e "SHOW TABLES LIKE 'acesso_%'" meuappdb) \
  > /caminho/seguro/meuappdb_acesso_YYYYMMDD.sql

# restaurar
mysql -u USER -p meuappdb < /caminho/seguro/meuappdb_acesso_YYYYMMDD.sql
```

Arquivos `*.sql` / `*.sql.gz` nesta pasta estão no `.gitignore`.
