# São Geraldo Service - Sistema de Gestão Completo

Sistema completo de gestão de chamados, clientes, equipamentos e usuários com controle de permissões.

## Funcionalidades

- **Autenticação**: Sistema de login/logout com sessões
- **Gestão de Clientes**: Cadastro completo com informações de contato
- **Gestão de Equipamentos**: Controle de equipamentos por cliente
- **Gestão de Usuários**: Controle de acesso com diferentes níveis de permissão
- **Chamados**: Sistema completo de chamados de serviço
- **Permissões Granulares**: Controle detalhado de acesso por funcionalidade

## Instalação

### 1. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar o Banco de Dados

```bash
python init_db_updated.py
```

### 3. Executar a Aplicação

```bash
python app_updated.py
```

## Usuários Padrão

- **Administrador**: admin@saogeraldo.com / senha: admin123
- **Técnico**: tecnico@saogeraldo.com / senha: tecnico123

## Estrutura de Permissões

### Permissões Disponíveis:
- `view_chamados` - Visualizar Chamados
- `create_chamado` - Criar Chamado
- `edit_chamado` - Editar Chamado
- `view_clientes` - Visualizar Clientes
- `create_cliente` - Criar Cliente
- `edit_cliente` - Editar Cliente
- `view_equipamentos` - Visualizar Equipamentos
- `create_equipamento` - Criar Equipamento
- `edit_equipamento` - Editar Equipamento
- `view_usuarios` - Visualizar Usuários
- `create_usuario` - Criar Usuário
- `edit_usuario` - Editar Usuário
- `admin` - Administrador Total

## Estrutura do Banco de Dados

### Tabelas Principais:

1. **usuarios** - Usuários do sistema
2. **clientes** - Cadastro de clientes
3. **equipamentos** - Equipamentos dos clientes
4. **chamados** - Chamados de serviço
5. **permissions** - Permissões do sistema
6. **user_permissions** - Relação usuário-permissão

## Fluxo de Trabalho

1. **Login**: Acessar o sistema com credenciais válidas
2. **Dashboard**: Visualizar estatísticas e chamados pessoais
3. **Clientes**: Gerenciar cadastro de clientes
4. **Equipamentos**: Cadastrar equipamentos por cliente
5. **Chamados**: Criar e gerenciar chamados de serviço

## Vínculo Automático

- Técnicos logados automaticamente vinculados aos seus clientes
- Chamados criados automaticamente associados ao técnico logado
- Clientes vinculados por email do responsável técnico

## Segurança

- Senhas criptografadas com hash
- Sessões seguras
- Controle de permissões granular
- Validação de entrada de dados

## Desenvolvimento

### Adicionar Novas Permissões:

```python
# Em init_db_updated.py
new_permission = Permission(name='nova_permissao', description='Descrição')
db.session.add(new_permission)
```

### Verificar Permissão no Código:

```python
if user.has_permission('nome_da_permissao'):
    # Permitir acesso
```

## Suporte

Para suporte ou dúvidas, entre em contato com a equipe de desenvolvimento.
