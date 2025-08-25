#!/usr/bin/env python3
"""
Script de migração do sistema antigo para o novo sistema completo
Este script copia os dados do sistema antigo para o novo sistema
"""

import os
import shutil
from datetime import datetime

def backup_sistema_antigo():
    """Cria backup do sistema antigo"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"bkp_sistema_antigo_{timestamp}"
    
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    # Arquivos a serem copiados
    arquivos_antigos = [
        'app.py', 'models.py', 'routes.py', 'init_db.py',
        'templates/', 'static/', 'requirements.txt'
    ]
    
    for arquivo in arquivos_antigos:
        if os.path.exists(arquivo):
            if os.path.isdir(arquivo):
                shutil.copytree(arquivo, os.path.join(backup_dir, arquivo))
            else:
                shutil.copy2(arquivo, backup_dir)
    
    print(f"Backup criado em: {backup_dir}")
    return backup_dir

def instalar_novo_sistema():
    """Instala o novo sistema"""
    print("Instalando novo sistema...")
    
    # Copiar arquivos novos
    arquivos_novos = [
        'models_updated.py', 'routes_updated.py', 'app_updated.py',
        'init_db_updated.py', 'README_UPDATED.md'
    ]
    
    for arquivo in arquivos_novos:
        if os.path.exists(arquivo):
            novo_nome = arquivo.replace('_updated', '')
            shutil.copy2(arquivo, novo_nome)
    
    # Copiar templates novos
    templates_novos = [
        'templates/login.html', 'templates/dashboard.html',
        'templates/clientes.html', 'templates/novo_cliente.html'
    ]
    
    for template in templates_novos:
        if os.path.exists(template):
            shutil.copy2(template, template)
    
    print("Novo sistema instalado com sucesso!")

def atualizar_requirements():
    """Atualiza requirements.txt com novas dependências
