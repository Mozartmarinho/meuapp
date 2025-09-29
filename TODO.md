# TODO: Fazer o projeto meuapp funcionar

## Setup Original
1. [x] Criar ambiente virtual (venv)
2. [x] Instalar dependências do requirements.txt
3. [x] Configurar banco de dados SQLite
4. [x] Inicializar tabelas do banco usando init_db.py
5. [x] Executar a aplicação Flask

## Fix Authentication Error and System Issues
6. [x] Update app.py to create default admin user on startup
7. [x] Add authentication routes and decorator to routes.py, protect existing routes
8. [x] Fix variable mismatches in templates/dashboard.html
9. [x] Restart the Flask app and test login/dashboard functionality
10. [x] Verify DB has users and tables, test full flow (login, create/edit chamado)

## Add Equipamento Field to Chamado
11. [x] Update models.py: Add equipamento String(100) nullable to Chamado, update to_dict
12. [] Recreate DB schema (drop_all, create_all) to apply new column (note: chamados data will be lost)
13. [] Update routes.py: Handle 'equipamento' in novo_chamado and editar_chamado POST
14. [] Update templates/novo_chamado.html: Add text input for equipamento below cliente, above tipo_servico
15. [] Update templates/editar_chamado.html: Add text input for equipamento, pre-filled
16. [] Update templates/chamados.html: Add "Equipamento" column, display value or 'N/A'
17. [] Test: Create/edit chamado with equipment text, verify in list
