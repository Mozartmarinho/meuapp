from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from models_updated import db, Cliente, Equipamento, Usuario, Chamado, Permission, ChamadoFoto, SistemaConfig
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from sqlalchemy import func, case
import json
import os
import base64
from email.mime.base import MIMEBase
from email import encoders

main = Blueprint('main', __name__)

# Decorador para verificar login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para verificar permissões
def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('main.login'))
            
            user = Usuario.query.get(session['user_id'])
            if not user or not user.has_permission(permission):
                flash('Você não tem permissão para acessar esta funcionalidade.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Rotas de Autenticação
@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        
        user = Usuario.query.filter_by(email=email).first()
        
        if user and user.check_password(senha) and user.ativo:
            session['user_id'] = user.id
            session['user_name'] = user.nome
            session['user_type'] = user.tipo
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Email ou senha inválidos!', 'error')
    
    return render_template('login.html')

@main.route('/logout')
def logout():
    session.clear()
    flash('Logout realizado com sucesso!', 'success')
    return redirect(url_for('main.login'))

# Dashboard
@main.route('/')
@login_required
def dashboard():
    user = Usuario.query.get(session['user_id'])
    
    # Contadores
    total_chamados = Chamado.query.count()
    chamados_pendentes = Chamado.query.filter_by(status='Pendente').count()
    chamados_em_andamento = Chamado.query.filter_by(status='Em Andamento').count()
    chamados_concluidos = Chamado.query.filter_by(status='Concluído').count()
    
    # Buscar cliente associado ao técnico logado
    cliente = Cliente.query.filter_by(email_responsavel=user.email).first()
    
    if user.tipo == 'tecnico' and cliente:
        query = Chamado.query.filter_by(cliente_id=cliente.id)
    else:
        query = Chamado.query.filter_by(tecnico_id=session['user_id'])
    
    # Busca
    numero_chamado = request.args.get('numero_chamado')
    cliente_nome = request.args.get('cliente_nome')
    
    if numero_chamado:
        query = query.filter(Chamado.numero_chamado.like(f'%{numero_chamado}%'))
    if cliente_nome:
        query = query.join(Cliente).filter(Cliente.nome.like(f'%{cliente_nome}%'))
    
    meus_chamados = query.order_by(Chamado.data_criacao.desc()).limit(10).all()
    
    return render_template('dashboard.html', 
                           user_name=user.nome,
                           stats={
                               'total': total_chamados,
                               'pendentes': chamados_pendentes,
                               'em_andamento': chamados_em_andamento,
                               'concluidos': chamados_concluidos
                           },
                           meus_chamados=meus_chamados,
                           numero_chamado=numero_chamado,
                           cliente_nome=cliente_nome)

# Rotas de Clientes
@main.route('/clientes')
@login_required
@permission_required('view_clientes')
def listar_clientes():
    clientes = Cliente.query.filter_by(ativo=True).all()
    return render_template('clientes.html', clientes=clientes)

@main.route('/clientes/novo', methods=['GET', 'POST'])
@login_required
@permission_required('create_cliente')
def novo_cliente():
    if request.method == 'POST':
        cliente = Cliente(
            nome=request.form['nome'],
            endereco=request.form['endereco'],
            telefone_responsavel=request.form.get('telefone_responsavel', ''),
            whatsapp_responsavel=request.form.get('whatsapp_responsavel', ''),
            email_responsavel=request.form.get('email_responsavel', '')
        )
        db.session.add(cliente)
        db.session.commit()
        flash('Cliente criado com sucesso!', 'success')
        return redirect(url_for('main.listar_clientes'))
    
    return render_template('novo_cliente.html')

@main.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('edit_cliente')
def editar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    
    if request.method == 'POST':
        cliente.nome = request.form['nome']
        cliente.endereco = request.form['endereco']
        cliente.telefone_responsavel = request.form.get('telefone_responsavel', '')
        cliente.whatsapp_responsavel = request.form.get('whatsapp_responsavel', '')
        cliente.email_responsavel = request.form.get('email_responsavel', '')
        
        db.session.commit()
        flash('Cliente atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_clientes'))
    
    return render_template('editar_cliente.html', cliente=cliente)

# Rotas de Equipamentos
@main.route('/equipamentos')
@login_required
@permission_required('view_equipamentos')
def listar_equipamentos():
    equipamentos = Equipamento.query.filter_by(ativo=True).all()
    return render_template('equipamentos.html', equipamentos=equipamentos)

@main.route('/equipamentos/novo', methods=['GET', 'POST'])
@login_required
@permission_required('create_equipamento')
def novo_equipamento():
    clientes = Cliente.query.filter_by(ativo=True).all()
    
    if request.method == 'POST':
        equipamento = Equipamento(
            equipamento=request.form.get('equipamento', ''),
            modelo=request.form.get('modelo', ''),
            data_compra=datetime.strptime(request.form['data_compra'], '%Y-%m-%d') if request.form.get('data_compra') else None,
            patrimonio=request.form.get('patrimonio', ''),
            observacoes=request.form.get('observacoes', ''),
            cliente_id=request.form.get('cliente_id', None),
            ativo='ativo' in request.form
        )
        db.session.add(equipamento)
        db.session.commit()
        flash('Equipamento criado com sucesso!', 'success')
        return redirect(url_for('main.listar_equipamentos'))
    
    return render_template('novo_equipamento.html', clientes=clientes)

@main.route('/equipamentos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('edit_equipamento')
def editar_equipamento(id):
    equipamento = Equipamento.query.get_or_404(id)
    clientes = Cliente.query.filter_by(ativo=True).all()
    
    if request.method == 'POST':
        equipamento.equipamento = request.form.get('equipamento') or equipamento.equipamento
        equipamento.modelo = request.form.get('modelo') or equipamento.modelo
        if request.form.get('data_compra'):
            equipamento.data_compra = datetime.strptime(request.form['data_compra'], '%Y-%m-%d')
        equipamento.patrimonio = request.form.get('patrimonio') or equipamento.patrimonio
        equipamento.observacoes = request.form.get('observacoes') or equipamento.observacoes
        if request.form.get('cliente_id'):
            equipamento.cliente_id = int(request.form['cliente_id'])
        equipamento.ativo = 'ativo' in request.form
        
        db.session.commit()
        flash('Equipamento atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_equipamentos'))
    
    return render_template('editar_equipamento.html', equipamento= equipamento, clientes=clientes)

# Rota de Relatórios
@main.route('/relatorios')
@login_required
@permission_required('view_equipamentos')  # Assuming reports require equipment view permission
def relatorios():
    cliente_nome = request.args.get('cliente_nome', None)

    # Dados para gráfico de pizza: clientes por quantidade de atendimentos (chamados)
    clientes_equip = db.session.query(
        Cliente.nome,
        func.count(Chamado.id).label('chamado_count')
    ).outerjoin(Chamado, Cliente.id == Chamado.cliente_id).group_by(Cliente.id).all()

    # Equipamentos filtrados por cliente, se cliente_nome for fornecido
    query = db.session.query(
        Equipamento,
        Cliente,
        func.count(Chamado.id).label('chamado_count')
    ).select_from(Equipamento).join(Cliente).outerjoin(Chamado, Chamado.cliente_id == Cliente.id).group_by(
        Equipamento.id, Cliente.id
    )

    if cliente_nome:
        query = query.filter(Cliente.nome.ilike(f'%{cliente_nome}%'))

    equipamentos = query.order_by(func.count(Chamado.id).desc()).all()

    clientes_equip_list = [(row[0], row[1]) for row in clientes_equip]
    clientes_equip_json = json.dumps(clientes_equip_list)
    return render_template('relatorios.html', clientes_equip=clientes_equip, equipamentos=equipamentos, clientes_equip_json=clientes_equip_json, cliente_nome=cliente_nome)

# Rotas de Usuários
@main.route('/usuarios')
@login_required
@permission_required('view_usuarios')
def listar_usuarios():
    usuarios = Usuario.query.filter_by(ativo=True).all()
    return render_template('usuarios.html', usuarios=usuarios)

@main.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@permission_required('create_usuario')
def novo_usuario():
    if request.method == 'POST':
        usuario = Usuario(
            nome=request.form['nome'],
            telefone=request.form.get('telefone', ''),  # Use get with default empty string
            email=request.form['email'],
            tipo=request.form['tipo']
        )
        usuario.set_password(request.form['senha'])
        db.session.add(usuario)
        db.session.commit()
        flash('Usuário criado com sucesso!', 'success')
        return redirect(url_for('main.listar_usuarios'))
    
    return render_template('novo_usuario.html')

@main.route('/usuarios/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('edit_usuario')
def editar_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    permissions = Permission.query.all()
    
    if request.method == 'POST':
        usuario.nome = request.form['nome']
        usuario.telefone = request.form.get('telefone', '')
        usuario.email = request.form['email']
        usuario.tipo = request.form['tipo']
        usuario.ativo = 'ativo' in request.form
        
        if request.form.get('senha'):
            usuario.set_password(request.form['senha'])
        
        # Atualizar permissões
        selected_permission_ids = request.form.getlist('permissions')
        usuario.permissions = []
        for perm_id in selected_permission_ids:
            perm = Permission.query.get(int(perm_id))
            if perm:
                usuario.permissions.append(perm)
        
        db.session.commit()
        flash('Usuário atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_usuarios'))
    
    return render_template('editar_usuario.html', usuario=usuario, permissions=permissions)

# Rotas de Chamados (atualizadas)
@main.route('/chamados')
@login_required
@permission_required('view_chamados')
def listar_chamados():
    user = Usuario.query.get(session['user_id'])
    
    # Buscar cliente associado ao técnico logado
    cliente = Cliente.query.filter_by(email_responsavel=user.email).first()
    
    if user.tipo == 'tecnico' and cliente:
        # Técnico vê apenas chamados do seu cliente
        chamados = Chamado.query.filter_by(cliente_id=cliente.id).order_by(
            case(
                (Chamado.status == 'Pendente', 1),
                (Chamado.status == 'Em Andamento', 2),
                (Chamado.status == 'Concluído', 3),
                else_=4
            )
        ).all()
    else:
        # Admin vê todos os chamados
        chamados = Chamado.query.order_by(
            case(
                (Chamado.status == 'Pendente', 1),
                (Chamado.status == 'Em Andamento', 2),
                (Chamado.status == 'Concluído', 3),
                else_=4
            )
        ).all()
    
    total_chamados = len(chamados)
    pendentes = sum(1 for c in chamados if c.status == 'Pendente')
    em_andamento = sum(1 for c in chamados if c.status == 'Em Andamento')
    concluidos = sum(1 for c in chamados if c.status == 'Concluído')
    
    return render_template('chamados.html', chamados=chamados, total_chamados=total_chamados,
                           pendentes=pendentes, em_andamento=em_andamento, concluidos=concluidos)

@main.route('/chamados/novo', methods=['GET', 'POST'])
@login_required
@permission_required('create_chamado')
def novo_chamado():
    user = Usuario.query.get(session['user_id'])
    
    # Buscar cliente associado ao técnico logado
    cliente = Cliente.query.filter_by(email_responsavel=user.email).first()
    
    if request.method == 'POST':
        # Validação dos campos obrigatórios
        required_fields = ['cliente_id', 'tipo_servico', 'status', 'prioridade', 'patrimonio']
        for field in required_fields:
            if not request.form.get(field):
                flash(f'O campo {field.replace("_", " ").capitalize()} é obrigatório.', 'error')
                clientes = Cliente.query.filter_by(ativo=True).all()
                return render_template('novo_chamado.html', clientes=clientes, cliente_selecionado=cliente)
        
        # Gerar número do chamado
        ultimo_chamado = Chamado.query.order_by(Chamado.id.desc()).first()
        numero = f"CHM{ultimo_chamado.id + 1:04d}" if ultimo_chamado else "CHM0001"
        
        chamado = Chamado(
            numero_chamado=numero,
            cliente_id=cliente.id if cliente else request.form['cliente_id'],
            tipo_servico=request.form['tipo_servico'],
            descricao=request.form['descricao'],
            status=request.form['status'],
            prioridade=request.form['prioridade'],
            observacoes=request.form['observacoes'],
            patrimonio=request.form['patrimonio'],
            equipamento=request.form['equipamento'],
            tecnico_id=session['user_id']
        )
        db.session.add(chamado)
        db.session.commit()

        # Enviar email para o responsável do cliente
        cliente_obj = Cliente.query.get(chamado.cliente_id)
        if cliente_obj and cliente_obj.email_responsavel:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                config = SistemaConfig.query.first()
                if config and config.smtp_server and config.email_from:
                    msg = MIMEMultipart()
                    msg['From'] = config.email_from
                    msg['To'] = cliente_obj.email_responsavel
                    msg['Subject'] = f"{config.email_subject_prefix} Novo Chamado Criado"

                    corpo = f"""
Olá,

Um novo chamado foi aberto no sistema São Geraldo Service.

Cliente: {cliente_obj.nome}
Número do Chamado: {chamado.numero_chamado}
Data e Hora: {chamado.data_criacao.strftime('%d/%m/%Y %H:%M:%S')}
Status: {chamado.status.upper()}

Atenciosamente,
Sistema São Geraldo Service
"""

                    msg.attach(MIMEText(corpo, 'plain'))

                    server = smtplib.SMTP(config.smtp_server, config.smtp_port)
                    if config.use_tls:
                        server.starttls()
                    server.login(config.smtp_username, config.smtp_password)
                    text = msg.as_string()
                    server.sendmail(config.email_from, cliente_obj.email_responsavel, text)
                    server.quit()
            except Exception as e:
                # Log error in SistemaConfig.email_error_log
                config = SistemaConfig.query.first()
                if config:
                    if config.email_error_log:
                        config.email_error_log += f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Erro ao enviar email: {str(e)}"
                    else:
                        config.email_error_log = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Erro ao enviar email: {str(e)}"
                    db.session.commit()
                print(f"Erro ao enviar email: {e}")
        flash('Chamado criado com sucesso!', 'success')
        return redirect(url_for('main.listar_chamados'))
    
    clientes = Cliente.query.filter_by(ativo=True).all()
    return render_template('novo_chamado.html', clientes=clientes, cliente_selecionado=cliente)

@main.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('edit_chamado')
def editar_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    clientes = Cliente.query.filter_by(ativo=True).all()
    
    if request.method == 'POST':
        chamado.cliente_id = request.form['cliente_id']
        chamado.tipo_servico = request.form['tipo_servico']
        chamado.descricao = request.form['descricao']
        chamado.status = request.form['status']
        chamado.prioridade = request.form['prioridade']
        chamado.observacoes = request.form['observacoes']
        
        if request.form['status'] == 'Concluído' and not chamado.data_conclusao:
            chamado.data_conclusao = datetime.utcnow()
        
        db.session.commit()
        flash('Chamado atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_chamados'))
    
    return render_template('editar_chamado.html', chamado=chamado, clientes=clientes)

# API para atualização de status
@main.route('/api/chamados/<int:id>/status', methods=['POST'])
@login_required
def atualizar_status_chamado(id):
    chamado = Chamado.query.get_or_404(id)

    def enviar_email_status(chamado, status, user_email, user_name):
        cliente_obj = Cliente.query.get(chamado.cliente_id)
        if not cliente_obj or not cliente_obj.email_responsavel:
            return
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            config = SistemaConfig.query.first()
            if not (config and config.smtp_server and config.email_from):
                return

            # Prepare photos for embedding if Concluído
            fotos_embed = []
            if status == 'Concluído':
                fotos = ChamadoFoto.query.filter_by(chamado_id=chamado.id).all()
                for foto in fotos:
                    file_path = os.path.join(current_app.root_path, 'static', 'uploads', foto.filename)
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            img_data = f.read()
                            img_base64 = base64.b64encode(img_data).decode('utf-8')
                            # Assume JPEG, but could detect
                            img_src = f"data:image/jpeg;base64,{img_base64}"
                            fotos_embed.append(img_src)

            # Function to create message
            def create_message(to_email, subject_suffix):
                msg = MIMEMultipart()
                msg['From'] = config.email_from
                msg['To'] = to_email
                msg['Subject'] = f"{config.email_subject_prefix} {subject_suffix}"

                if status == 'Concluído':
                    corpo = f"""
<html>
<body>
<p>Olá,</p>
<p>O chamado foi concluído no sistema São Geraldo Service.</p>
<p><strong>Cliente:</strong> {cliente_obj.nome} | <strong>Número do Chamado:</strong> {chamado.numero_chamado} | <strong>Data e Hora da Criação:</strong> {chamado.data_criacao.strftime('%d/%m/%Y %H:%M:%S')}</p>
<p><strong>Tipo de Serviço:</strong> {chamado.tipo_servico} | <strong>Descrição:</strong> {chamado.descricao} | <strong>Patrimônio:</strong> {chamado.patrimonio}</p>
<p><strong>Equipamento:</strong> {chamado.equipamento} | <strong>Prioridade:</strong> {chamado.prioridade} | <strong>Observações:</strong> {chamado.observacoes}</p>
<p><strong>Status:</strong> <b>{status.upper()}</b> | <strong>Ação realizada por:</strong> {user_name} | <strong>Data e Hora da Conclusão:</strong> {chamado.data_conclusao.strftime('%d/%m/%Y %H:%M:%S')}</p>
<p><strong>Serviço Executado:</strong> {chamado.feito}</p>
"""
                    for img_src in fotos_embed:
                        corpo += f'<p><img src="{img_src}" style="max-width: 100%; height: auto;"></p>'
                    corpo += """
<p>Atenciosamente,<br>Sistema São Geraldo Service</p>
</body>
</html>
"""
                    msg.attach(MIMEText(corpo, 'html'))
                else:
                    corpo = f"""
Olá,

O chamado número {chamado.numero_chamado} foi atualizado no sistema São Geraldo Service.

Cliente: {cliente_obj.nome}
Número do Chamado: {chamado.numero_chamado}
Data e Hora: {datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S')}
Status: {status.upper()}
Ação realizada por: {user_name}

Atenciosamente,
Sistema São Geraldo Service
"""
                    msg.attach(MIMEText(corpo, 'plain'))
                return msg

            server = smtplib.SMTP(config.smtp_server, config.smtp_port)
            if config.use_tls:
                server.starttls()
            server.login(config.smtp_username, config.smtp_password)

            # Send to client responsible
            msg_cliente = create_message(cliente_obj.email_responsavel, "Atualização de Chamado")
            text_cliente = msg_cliente.as_string()
            server.sendmail(config.email_from, cliente_obj.email_responsavel, text_cliente)

            # Send to user if different
            if user_email and user_email != cliente_obj.email_responsavel:
                msg_user = create_message(user_email, "Atualização de Chamado")
                text_user = msg_user.as_string()
                server.sendmail(config.email_from, user_email, text_user)

            server.quit()
        except Exception as e:
            # Log error in SistemaConfig.email_error_log
            config = SistemaConfig.query.first()
            if config:
                if config.email_error_log:
                    config.email_error_log += f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Erro ao enviar email: {str(e)}"
                else:
                    config.email_error_log = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Erro ao enviar email: {str(e)}"
                db.session.commit()
            print(f"Erro ao enviar email: {e}")

    user = Usuario.query.get(session['user_id'])
    user_email = user.email if user else None

    if request.content_type.startswith('multipart/form-data'):
        # Handle form data for Concluído
        status = request.form['status']
        feito = request.form['feito']
        files = request.files.getlist('fotos')

        chamado.status = status
        chamado.feito = feito
        if not chamado.data_conclusao:
            chamado.data_conclusao = datetime.utcnow()

        # Save photos
        import os
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        for file in files[:4]:  # Up to 4
            if file and file.filename:
                filename = f"{chamado.id}_{file.filename}"
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)
                foto = ChamadoFoto(chamado_id=chamado.id, filename=filename)
                db.session.add(foto)

        db.session.commit()
        enviar_email_status(chamado, status, user_email, user.nome)
        return jsonify({'success': True})
    else:
        # JSON for other statuses
        data = request.get_json()
        status = data['status']

        if status == 'Em Andamento':
            if not chamado.data_atendimento:
                chamado.data_atendimento = datetime.utcnow()

        chamado.status = status
        db.session.commit()
        enviar_email_status(chamado, status, user_email, user.nome)
        return jsonify({'success': True})

# Rota de Sistema
@main.route('/sistema', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def sistema():
    config = SistemaConfig.query.first()
    if not config:
        config = SistemaConfig()
        db.session.add(config)
        db.session.commit()
    
    if request.method == 'POST':
        config.smtp_server = request.form.get('smtp_server', '')
        config.smtp_port = int(request.form.get('smtp_port', 587))
        config.smtp_username = request.form.get('smtp_username', '')
        config.smtp_password = request.form.get('smtp_password', '')
        config.email_from = request.form.get('email_from', '')
        config.email_subject_prefix = request.form.get('email_subject_prefix', '[São Geraldo Service]')
        config.use_tls = 'use_tls' in request.form

        db.session.commit()
        flash('Configurações do sistema atualizadas com sucesso!', 'success')
        return redirect(url_for('main.sistema'))
    
    return render_template('sistema.html', config=config)

@main.route('/api/equipamentos_por_cliente/<cliente_nome>')
@login_required
def equipamentos_por_cliente(cliente_nome):
    cliente = Cliente.query.filter_by(nome=cliente_nome, ativo=True).first()
    if not cliente:
        return jsonify([])  # Retorna lista vazia se cliente não encontrado

    equipamentos = Equipamento.query.filter_by(cliente_id=cliente.id, ativo=True).all()
    equipamentos_list = []
    for equip in equipamentos:
        equipamentos_list.append({
            'id': equip.id,
            'patrimonio': equip.patrimonio,
            'nome_equipamento': equip.equipamento
        })
    return jsonify(equipamentos_list)
