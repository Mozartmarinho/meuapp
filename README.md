# Sistema São Geraldo Service

Sistema web para gestão de pedidos e ordens de serviço desenvolvido em Flask com MySQL.

## Características

- **Design moderno** baseado nas cores da empresa (azul royal e verde limão)
- **Interface responsiva** com sidebar e área principal
- **Gestão completa de pedidos** (criar, editar, listar, filtrar)
- **Dashboard** com estatísticas em tempo real
- **Sistema de status** e prioridades
- **Banco de dados MySQL** para persistência

## Tecnologias Utilizadas

- **Backend**: Python Flask
- **Banco de Dados**: MySQL
- **Frontend**: HTML5, CSS3, JavaScript
- **Frameworks CSS**: Custom CSS com variáveis
- **Ícones**: Font Awesome

## Pré-requisitos

- Python 3.7+
- MySQL Server
- pip (gerenciador de pacotes Python)

## Instalação

### 1. Instalar dependências Python

```bash
cd Sistema_Sao_Geraldo
pip install -r requirements.txt
```

### 2. Configurar MySQL

1. Instale o MySQL Server se não estiver instalado
2. Crie o banco de dados executando o script SQL:

```bash
mysql -u root -p < init_db.sql
```

### 3. Configurar conexão do banco

Edite o arquivo `config.py` e ajuste a string de conexão:

```python
SQLALCHEMY_DATABASE_URI = 'mysql://usuario:senha@localhost/sao_geraldo_db'
```

### 4. Executar a aplicação

```bash
python app.py
```

A aplicação estará disponível em: `http://localhost:5000`

## Estrutura do Projeto

```
Sistema_Sao_Geraldo/
├── app.py                 # Aplicação principal
├── config.py              # Configurações
├── models.py              # Modelos do banco de dados
├── routes.py              # Rotas da aplicação
├── requirements.txt       # Dependências Python
├── init_db.sql           # Script de inicialização do banco
├── templates/            # Templates HTML
│   ├── base.html
│   ├── dashboard.html
│   ├── pedidos.html
│   ├── novo_pedido.html
│   └── editar_pedido.html
└── static/               # Arquivos estáticos
    ├── css/
    │   └── style.css
    ├── js/
    │   └── main.js
    └── img/
        └── logo.jpg
```

## Funcionalidades

### Dashboard
- Estatísticas de pedidos (total, pendentes, em andamento, concluídos)
- Lista dos pedidos mais recentes
- Atualização automática a cada 30 segundos

### Gestão de Pedidos
- **Criar novos pedidos** com informações completas
- **Editar pedidos existentes** incluindo status e prioridade
- **Listar e filtrar** pedidos por status ou busca textual
- **Atualização de status** via AJAX sem recarregar a página

### Interface
- **Design responsivo** que funciona em desktop e mobile
- **Sidebar fixa** com menu de navegação
- **Logo da empresa** no topo da sidebar
- **Cores personalizadas** seguindo a identidade visual

## Uso

### Criando um Novo Pedido

1. Acesse o menu "Novo Pedido"
2. Preencha as informações obrigatórias:
   - Cliente
   - Tipo de Serviço
   - Descrição
3. Defina prioridade e valor (opcionais)
4. Clique em "Salvar Pedido"

### Gerenciando Pedidos

1. Acesse o menu "Pedidos"
2. Use os filtros para encontrar pedidos específicos
3. Altere o status diretamente na tabela
4. Clique no ícone de edição para modificar detalhes

## Personalização

### Cores
As cores podem ser alteradas no arquivo `static/css/style.css`:

```css
:root {
    --primary-color: #1E3A8A;    /* Azul royal */
    --accent-color: #9ACD32;     /* Verde limão */
    --white: #FFFFFF;
    /* ... outras cores */
}
```

### Logo
Substitua o arquivo `static/img/logo.jpg` pela logo desejada.

## Suporte

Para suporte técnico ou dúvidas sobre o sistema, entre em contato com a equipe de desenvolvimento.

## Licença

Este sistema foi desenvolvido especificamente para São Geraldo Service.
