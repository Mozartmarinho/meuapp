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

Por padrão sobe **HTTP (porta 80)** e **HTTPS (porta 443)** em `0.0.0.0`:

- `http://127.0.0.1/`
- `https://127.0.0.1/` (certificado autoassinado em `certs/`)

Se a porta 443 exigir admin ou estiver ocupada, o app tenta **8443** e imprime o aviso.

Variáveis úteis: `HOST`, `PORT`, `HTTPS_PORT`, `ENABLE_HTTPS=0` (só HTTP).

#### Certificado local (HTTPS)

Certs em `certs/cert.pem` + `certs/key.pem` são gerados automaticamente na 1ª subida (ou manualmente):

```bash
.\.venv\Scripts\python.exe generate_certs.py
# regenerar:
.\.venv\Scripts\python.exe generate_certs.py --force
```

Sem confiança no sistema, Chrome/Edge mostram `net::ERR_CERT_AUTHORITY_INVALID` (cert autoassinado).

**Como remover o aviso neste PC (dev local):**

```powershell
# Opção A — script
powershell -ExecutionPolicy Bypass -File .\trust_local_cert.ps1

# Opção B — via generate_certs
.\.venv\Scripts\python.exe generate_certs.py --trust
```

Isso importa `certs/cert.pem` no store **Current User → Trusted Root Certification Authorities**. Depois **reinicie o Chrome/Edge** e abra `https://127.0.0.1/`.

- Só vale para **este usuário nesta máquina**. Outros PCs precisam repetir o trust (ou usar mkcert).
- Em **produção** use um domínio real + CA pública (ex.: Let's Encrypt) — não dá para sumir o aviso para usuários aleatórios com cert local.
- Se regenerar com `--force`, rode o trust de novo (thumbprint muda).
- `certs/` está no `.gitignore` (não commitar chave privada).

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
