from app_updated import app
from models_updated import db, Usuario, Cliente, Equipamento, Chamado, Permission, SistemaConfig
from datetime import datetime

def init_db():
    with app.app_context():
        # Criar todas as tabelas
        db.create_all()
        
        # Criar permissões padrão
        permissions = [
            Permission(name='view_chamados', description='Visualizar Chamados'),
            Permission(name='create_chamado', description='Criar Chamado'),
            Permission(name='edit_chamado', description='Editar Chamado'),
            Permission(name='view_clientes', description='Visualizar Clientes'),
            Permission(name='create_cliente', description='Criar Cliente'),
            Permission(name='edit_cliente', description='Editar Cliente'),
            Permission(name='view_equipamentos', description='Visualizar Equipamentos'),
            Permission(name='create_equipamento', description='Criar Equipamento'),
            Permission(name='edit_equipamento', description='Editar Equipamento'),
            Permission(name='view_usuarios', description='Visualizar Usuários'),
            Permission(name='create_usuario', description='Criar Usuário'),
            Permission(name='edit_usuario', description='Editar Usuário'),
            Permission(name='admin', description='Administrador Total')
        ]
        
        for perm in permissions:
            existing = Permission.query.filter_by(name=perm.name).first()
            if not existing:
                db.session.add(perm)
        
        # Criar usuário admin padrão
        admin = Usuario.query.filter_by(email='admin@saogeraldo.com').first()
        if not admin:
            admin = Usuario(
                nome='Administrador',
                email='admin@saogeraldo.com',
                tipo='admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            
            # Adicionar todas as permissões ao admin
            all_permissions = Permission.query.all()
            for perm in all_permissions:
                admin.permissions.append(perm)
        
        # Criar cliente de exemplo
        cliente = Cliente.query.filter_by(email_responsavel='cliente@example.com').first()
        if not cliente:
            cliente = Cliente(
                nome='Cliente Exemplo',
                endereco='Rua Exemplo, 123',
                telefone_responsavel='(11) 9999-9999',
                whatsapp_responsavel='(11) 9999-9999',
                email_responsavel='cliente@example.com'
            )
            db.session.add(cliente)
        
        # Criar equipamento de exemplo
        equipamento = Equipamento.query.filter_by(patrimonio='PAT001').first()
        if not equipamento:
            equipamento = Equipamento(
                equipamento='Computador Desktop',
                modelo='Dell OptiPlex 7090',
                data_compra=datetime(2023, 1, 15).date(),
                patrimonio='PAT001',
                observacoes='Equipamento principal do cliente',
                cliente_id=1
            )
            db.session.add(equipamento)
        
        # Criar técnico de exemplo
        tecnico = Usuario.query.filter_by(email='tecnico@saogeraldo.com').first()
        if not tecnico:
            tecnico = Usuario(
                nome='Técnico Exemplo',
                email='tecnico@saogeraldo.com',
                tipo='tecnico'
            )
            tecnico.set_password('tecnico123')
            db.session.add(tecnico)

            # Adicionar permissões básicas ao técnico
            tecnico_perms = ['view_chamados', 'create_chamado', 'edit_chamado', 'view_clientes', 'view_equipamentos']
            for perm_name in tecnico_perms:
                perm = Permission.query.filter_by(name=perm_name).first()
                if perm:
                    tecnico.permissions.append(perm)

        # Criar configuração do sistema padrão
        config = SistemaConfig.query.first()
        if not config:
            config = SistemaConfig(
                smtp_server='smtp.gmail.com',
                smtp_port=587,
                email_from='noreply@saogeraldo.com'
            )
            db.session.add(config)

        db.session.commit()
        print("Banco de dados inicializado com sucesso!")
        print("Usuário admin: admin@saogeraldo.com / admin123")
        print("Usuário técnico: tecnico@saogeraldo.com / tecnico123")

if __name__ == '__main__':
    init_db()

