# CI/CD — Deploy automático do MeuApp

Sempre que houver `git push` para a branch **main** no GitHub, o servidor Ubuntu
atualiza o código, instala dependências, roda migrações, reinicia a aplicação
e recarrega o Nginx — com log completo em `logs/deploy/`.

**Produção neste servidor:** acesso em **HTTP porta 80**
(`http://192.168.0.253` → Nginx → Gunicorn via `meuapp.sock`).
Não usa a porta 5000 do `python app.py` (isso é só desenvolvimento).

## Por que self-hosted runner?

O servidor está na LAN (`192.168.0.253`). O GitHub Actions na nuvem **não
alcança** esse IP sem abrir SSH na internet. O runner instalado **no próprio
servidor** recebe o job sem expor porta.

> Alternativa SSH (nuvem): veja `.github/workflows/deploy-ssh.yml.example`.

---

## Arquivos criados

| Arquivo | Função |
|---------|--------|
| `.github/workflows/deploy.yml` | Dispara o deploy no push para `main` |
| `scripts/deploy.sh` | Pull → deps → migrações → restart → logs |
| `scripts/run_migrations.py` | Aplica `migrations/*` pendentes |
| `migrations/` | Pasta das migrações versionadas |
| `deploy/sudoers.meuapp-deploy` | Sudo sem senha só para systemctl/nginx |

---

## Passo a passo (uma vez no servidor)

### 1. Commit e push destes arquivos para `main`

No seu ambiente de desenvolvimento (ou neste servidor):

```bash
cd /home/administrador/meuapp
chmod +x scripts/deploy.sh scripts/run_migrations.py
git checkout main
git pull origin main
# adicione os arquivos novos, commit e:
git push origin main
```

> O primeiro push ainda **não** faz deploy automático (runner ainda não existe).
> Depois do passo 3, os próximos pushes já disparam.

### 2. Permitir restart sem senha (sudoers)

```bash
sudo cp /home/administrador/meuapp/deploy/sudoers.meuapp-deploy /etc/sudoers.d/meuapp-deploy
sudo chmod 440 /etc/sudoers.d/meuapp-deploy
sudo visudo -cf /etc/sudoers.d/meuapp-deploy
```

Teste:

```bash
sudo systemctl status meuapp --no-pager | head -5
sudo nginx -t
```

### 3. Instalar o GitHub Actions self-hosted runner

1. Abra: https://github.com/Mozartmarinho/meuapp/settings/actions/runners/new  
2. Escolha **Linux x64** e copie o token da tela.  
3. No servidor:

Na página do runner, o GitHub mostra os 3 comandos exatos (`mkdir`, `curl`, `tar`).
Execute-os e depois:

```bash
cd /home/administrador/actions-runner

./config.sh --url https://github.com/Mozartmarinho/meuapp \
  --token SEU_TOKEN_AQUI \
  --name meuapp-production \
  --labels self-hosted,linux,production \
  --work _work

sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

> Use o **token e a URL do pacote** gerados na página do GitHub (a versão do runner muda).

Confirme em: https://github.com/Mozartmarinho/meuapp/settings/actions/runners  
O runner deve aparecer **Idle** (verde).

### 4. Habilitar deploy neste servidor

O script só executa o `git reset` se existir o arquivo de trava:

```bash
touch /home/administrador/meuapp/.ci_deploy_enabled
```

(Isso evita um deploy acidental antes do runner/sudoers estarem prontos.)

### 5. Testar o pipeline

```bash
# Disparo manual (sem mudar código):
# GitHub → Actions → Deploy Production → Run workflow

# Ou faça um commit vazio na main:
git checkout main
git commit --allow-empty -m "ci: test deploy pipeline"
git push origin main
```

Acompanhe em **Actions**. No servidor:

```bash
tail -f /home/administrador/meuapp/logs/deploy/latest.log
```

### 5. Fluxo do dia a dia

```bash
git checkout -b feature/minha-mudanca
# ... edite ...
git add -A && git commit -m "feat: ..."
git push -u origin HEAD
# abra PR → merge em main
# (ou push direto em main)
# → deploy automático
```

---

## O que o deploy faz

1. `git fetch` + `reset --hard origin/main`  
2. `pip install -r requirements.txt` (venv)  
3. `python scripts/run_migrations.py`  
4. `systemctl restart meuapp`  
5. `nginx -t` + `systemctl reload nginx` (continua na **porta 80**)  
6. Health-check em `http://127.0.0.1/login`  
7. Log em `logs/deploy/deploy_YYYYMMDD_HHMMSS.log` (+ symlink `latest.log`)

## Migrações de banco

Não há Alembic neste projeto. Use arquivos em `migrations/`:

```text
migrations/
  001_create_schema_migrations_note.sql   # já incluso (no-op)
  002_add_coluna_exemplo.sql              # próximo change
```

Exemplo `002_add_coluna_exemplo.sql`:

```sql
ALTER TABLE chamados ADD COLUMN exemplo VARCHAR(100) NULL;
```

Ou Python `003_backfill.py`:

```python
def run(engine):
    with engine.begin() as conn:
        conn.execute("UPDATE ...")
```

Regras:
- Nome em ordem alfabética / numérica (`001_`, `002_`, …)
- Nunca edite uma migração já aplicada em produção — crie outra
- O controle fica na tabela `schema_migrations`

## Logs e troubleshooting

```bash
# Último deploy
less /home/administrador/meuapp/logs/deploy/latest.log

# Histórico
ls -lt /home/administrador/meuapp/logs/deploy/

# Serviços
sudo systemctl status meuapp
sudo systemctl status nginx
sudo journalctl -u meuapp -n 50 --no-pager

# Runner
cd /home/administrador/actions-runner && sudo ./svc.sh status
```

## Segurança

- **Não** coloque senhas no `deploy.sh` (o antigo `deploy.sh` na raiz tinha senha em texto — não use mais).
- Sudoers libera **apenas** comandos de systemctl/nginx listados.
- Secrets de banco continuam no servidor (`app.py` / env); não vão para o GitHub.
- Proteja a branch `main`: Settings → Branches → Require PR / reviews (opcional).

## Alternativa SSH (se o servidor for público)

1. Renomeie `deploy-ssh.yml.example` → `deploy-ssh.yml`  
2. Remova ou desabilite `deploy.yml`  
3. Secrets: `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, `SSH_PORT`  
4. Mesmo `scripts/deploy.sh` no servidor  

Self-hosted continua sendo a opção recomendada para este ambiente.
