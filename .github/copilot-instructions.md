# Copilot Instructions for São Geraldo Service

## Visão Geral
Este é um sistema web de gestão de pedidos e ordens de serviço, desenvolvido em Flask (Python) com MySQL. O projeto segue uma arquitetura MVC simplificada:
- **app.py**: ponto de entrada, inicializa o app Flask, registra rotas e configurações.
- **models.py**: define os modelos de dados (ORM SQLAlchemy).
- **routes.py**: implementa as rotas e lógica de negócio.
- **config.py**: centraliza configurações, incluindo a string de conexão do banco.
- **static/**: arquivos estáticos (CSS, JS, imagens).
- **templates/**: templates HTML Jinja2.

## Fluxos de Trabalho
- **Execução local**: `python app.py` (aplicação roda em http://localhost:5000)
- **Inicialização do banco**: execute `mysql -u root -p < init_db.sql` para criar as tabelas.
- **Configuração do banco**: ajuste a string `SQLALCHEMY_DATABASE_URI` em `config.py`.
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
- **Scripts auxiliares**: `init_db.py` para inicialização, `migrar_sistema.py` para migrações.
- **Arquivos *_updated.py**: versões alternativas/experimentais, não sobrescrever sem análise.
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
