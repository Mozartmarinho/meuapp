# Copilot Instructions for São Geraldo Service

## Visão Geral
Este é um sistema web de gestão de pedidos e ordens de serviço, desenvolvido em Flask (Python) com MySQL. O projeto segue uma arquitetura MVC simplificada:
- **app.py**: único ponto de entrada. Não recriar `app_updated.py` nem `config.py` como segundo Flask app.
- **db_config.py**: string de conexão MySQL (`SQLALCHEMY_DATABASE_URI`).
- **models.py** / **routes.py**: modelos e rotas do núcleo (chamados).
- **routes_nutricao.py**, **routes_pesagem.py**, **routes_acesso.py**: módulos extras.
- **static/**: arquivos estáticos (CSS, JS, imagens).
- **templates/** e **templates_nutricao/**: templates HTML Jinja2.

## Fluxos de Trabalho
- **Execução local (Windows)**: atalho **São Geraldo Service** (`iniciar_meuapp.bat`) ou `python app.py`. Início automático: `instalar_inicio_automatico.bat`.
- **Servidor Linux**: Nginx porta 80 → Gunicorn (`meuapp.service`). Deploy: `scripts/deploy.sh`. Início automático: `scripts/instalar_inicio_automatico.sh`.
- **Inicialização do banco**: execute `python init_db.py` / `scripts/run_migrations.py`.
- **Configuração do banco**: ajuste `SQLALCHEMY_DATABASE_URI` em `db_config.py`.
- **Dependências**: instale com `pip install -r requirements.txt`.

## Convenções e Padrões
- **Rotas**: definidas em `routes.py`, usam decorators Flask (@app.route).
- **Modelos**: herdam de `db.Model` (SQLAlchemy), definidos em `models.py`.
- **Templates**: herdam de `base.html` e usam blocos Jinja2 para conteúdo dinâmico.
- **Estilo**: cores principais em `static/css/style.css` via variáveis CSS.
- **Atualização de status**: feita via AJAX (JS em `static/js/main.js`).
- **Dashboard**: atualiza automaticamente a cada 30s (JS).

## Integrações e Pontos Críticos
- **Banco de dados**: MySQL, conexão via SQLAlchemy.
- **Login/autenticação**: (verifique se implementado, pode estar em `routes.py` ou `models.py`).
- **Scripts auxiliares**: `init_db.py` para inicialização, `scripts/run_migrations.py` para migrações.
- **Um único projeto**: este repositório `meuapp`. Não criar `*_updated.py` nem um segundo app Flask.
- **Backup**: diretório `bkp/` contém versões antigas de arquivos críticos.

## Exemplos de Padrão
- Nova rota:
  ```python
  @app.route('/novo_recurso')
  def novo_recurso():
      # lógica aqui
      return render_template('novo_recurso.html')
  ```
- Novo modelo:
  ```python
  class Cliente(db.Model):
      id = db.Column(db.Integer, primary_key=True)
      nome = db.Column(db.String(100), nullable=False)
  ```

## Recomendações para agentes AI
- Sempre confira se há arquivos *_updated.py ou em `bkp/` antes de sobrescrever.
- Siga a estrutura de templates e herança de `base.html`.
- Use variáveis CSS para manter o padrão visual.
- Consulte `README.md` para instruções detalhadas de setup e uso.

---
Seções incompletas ou dúvidas? Peça feedback ao usuário para refinar as instruções.
