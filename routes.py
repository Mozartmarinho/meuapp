from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models_updated import db, Cliente, Equipamento, Usuario, Chamado, Permission
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

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
        print(f"Login attempt: email={email}, senha={senha}")
        
        user = Usuario.query.filter_by(email=email).first()
        print(f"User found: {user}")
        
        if user and user.check_password(senha) and user.ativo:
            print("Password correct and user active")
            session['user_id'] = user.id
            session['user_name'] = user.nome
            session['user_type'] = user.tipo
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            print("Login failed: invalid email or password or inactive user")
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
    
    # Chamados do técnico logado
    query = Chamado.query.filter_by(tecnico_id=session['user_id'])
    
    # Busca por número do chamado
    numero_chamado = request.args.get('numero_chamado')
    if numero_chamado:
        query = query.filter(Chamado.numero_chamado.like(f'%{numero_chamado}%'))
    
    meus_chamados = query.all()
    
    stats = {
        'total': total_chamados,
        'pendentes': chamados_pendentes,
        'em_andamento': chamados_em_andamento,
        'concluidos': chamados_concluidos
    }
    
    return render_template('dashboard.html', 
                         stats=stats,
                         meus_chamados=meus_chamados,
                         numero_chamado=numero_chamado)

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
            telefone_responsavel=request.form['telefone_responsavel'],
            whatsapp_responsavel=request.form['whatsapp_responsavel'],
            email_responsavel=request.form['email_responsavel']
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
        cliente.telefone_responsavel = request.form['telefone_responsavel']
        cliente.whatsapp_responsavel = request.form['whatsapp_responsavel']
        cliente.email_responsavel = request.form['email_responsavel']
        
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
            equipamento=request.form['equipamento'],
            modelo=request.form['modelo'],
            data_compra=datetime.strptime(request.form['data_compra'], '%Y-%m-%d') if request.form['data_compra'] else None,
            patrimonio=request.form['patrimonio'],
            observacoes=request.form['observacoes'],
            cliente_id=request.form['cliente_id']
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
        equipamento.equipamento = request.form['equipamento']
        equipamento.modelo = request.form['modelo']
        equipamento.data_compra = datetime.strptime(request.form['data_compra'], '%Y-%m-%d') if request.form['data_compra'] else None
        equipamento.patrimonio = request.form['patrimonio']
        equipamento.observacoes = request.form['observacoes']
        equipamento.cliente_id = request.form['cliente_id']
        
        db.session.commit()
        flash('Equipamento atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_equipamentos'))
    
    return render_template('editar_equipamento.html', equipamento=equipamento, clientes=clientes)

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
            telefone=request.form['telefone'],
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
    
    if request.method == 'POST':
        usuario.nome = request.form['nome']
        usuario.telefone = request.form['telefone']
        usuario.email = request.form['email']
        usuario.tipo = request.form['tipo']
        
        if request.form.get('senha'):
            usuario.set_password(request.form['senha'])
        
        db.session.commit()
        flash('Usuário atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_usuarios'))
    
    return render_template('editar_usuario.html', usuario=usuario)

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
        chamados = Chamado.query.filter_by(cliente_id=cliente.id).all()
    else:
        # Admin vê todos os chamados
        chamados = Chamado.query.all()
    
    return render_template('chamado.html', chamados=chamados)

@main.route('/chamados/novo', methods=['GET', 'POST'])
@login_required
@permission_required('create_chamado')
def novo_chamado():
    user = Usuario.query.get(session['user_id'])
    
    # Buscar cliente associado ao técnico logado
    cliente = Cliente.query.filter_by(email_responsavel=user.email).first()
    
    if request.method == 'POST':
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
            tecnico_id=session['user_id']
        )
        db.session.add(chamado)
        db.session.commit()
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
    data = request.get_json()
    
    chamado.status = data['status']
    if data['status'] == 'Em Andamento':
        chamado.data_atendimento = datetime.utcnow()
    elif data['status'] == 'Concluído':
        chamado.data_conclusao = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True})
