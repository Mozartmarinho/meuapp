# Instruções para Configurar MySQL no Windows 10

## 1. Instalar o Serviço MySQL

Execute o arquivo `install_mysql_service.bat` como **Administrador**:
- Clique com o botão direito no arquivo `install_mysql_service.bat`
- Selecione "Executar como administrador"

Isso instalará o serviço MySQL com o diretório de dados em `C:\Users\mz\mysql-data`.

## 2. Iniciar o Serviço MySQL

Execute o arquivo `start_mysql_service.bat` como **Administrador**:
- Clique com o botão direito no arquivo `start_mysql_service.bat`
- Selecione "Executar como administrador"

Isso iniciará o serviço MySQL.

## 3. Configurar MySQL para Iniciar Automaticamente com o Windows

Após instalar o serviço, configure-o para iniciar automaticamente:
- Abra o **Gerenciador de Serviços** (services.msc)
- Procure pelo serviço "MySQL"
- Clique com o botão direito no serviço MySQL
- Selecione "Propriedades"
- Na aba "Geral", altere o "Tipo de inicialização" para "Automática"
- Clique em "Aplicar" e "OK"

## 4. Configurar a Senha do Root e Criar o Banco

Execute o script Python para configurar a senha:
```bash
python setup_mysql_fixed.py
```

Isso definirá a senha do root como "saogeeraldo2025" e criará o banco "meuappdb".

## 5. Testar a Conexão

Teste a conexão com o banco:
```bash
"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -u root -psaogeeraldo2025 -e "USE meuappdb; SELECT 1;"
```

## 6. Inicializar o Banco de Dados do Sistema

Execute o script para inicializar as tabelas e dados padrão:
```bash
python init_db.py
```

Isso criará as tabelas, permissões e usuários padrão.

## 7. Configurar o App para Iniciar Automaticamente

Para que o sistema inicie automaticamente sem interação humana:

1. Execute `install_meuapp_service.bat` como **Administrador** para instalar o serviço do app.
2. O serviço será configurado para iniciar automaticamente com o Windows.

Se precisar remover o serviço, execute `uninstall_meuapp_service.bat` como Administrador.

## 8. Testar o Sistema

Após todas as configurações, reinicie o computador. O MySQL e o app devem iniciar automaticamente.

Acesse o sistema em: http://localhost:5000 (ou a porta configurada no app.py)

## Observações

- Certifique-se de executar os comandos como Administrador quando necessário.
- O diretório de dados do MySQL está em `C:\Users\mz\mysql-data` para evitar problemas de permissão.
- A senha do banco é "saogeeraldo2025" conforme solicitado.
- O banco de dados "meuappdb" será criado automaticamente.
