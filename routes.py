from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Chamado, Usuario, Cliente, Equipamento
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from datetime import datetime
import random
import string

main = Blueprint('main', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

def gerar_numero_chamado():
    """Gera um número único para o chamado"""
    prefixo = "OS"
    numero = ''.join(random.choices(string.digits, k=6))
    return f"{prefixo}{numero}"

@main.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        user = Usuario.query.filter_by(email=email, ativo=True).first()
        if user and check_password_hash(user.senha, senha):
            session['user_id'] = user.id
            session['user_name'] = user.nome
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('main.inicio'))
        else:
            flash('Email ou senha incorretos.', 'error')
    return render_template('login.html')

@main.route('/logout')
def logout():
    """Logout do usuário"""
    session.clear()
    flash('Você foi deslogado com sucesso.', 'success')
    return redirect(url_for('main.login'))

@main.route('/')
@login_required
def inicio():
    """Tela inicial de escolha entre os sistemas"""
    user = Usuario.query.get(session['user_id'])
    return render_template('inicio.html', user_name=user.nome if user else session.get('user_name', 'Usuário'))

@main.route('/dashboard')
@login_required
def dashboard():
    """Dashboard do sistema de gestão de chamados"""
    user = Usuario.query.get(session['user_id'])
    # Estatísticas básicas
    total_chamados = Chamado.query.count()
    chamados_pendentes = Chamado.query.filter_by(status='Pendente').count()
    chamados_em_andamento = Chamado.query.filter_by(status='Em Andamento').count()
    chamados_concluidos = Chamado.query.filter_by(status='Concluído').count()

    # Chamados recentes
    chamados_recentes = Chamado.query.options(joinedload(Chamado.cliente)).order_by(Chamado.data_criacao.desc()).limit(10).all()

    stats = {
        'total': total_chamados,
        'pendentes': chamados_pendentes,
        'em_andamento': chamados_em_andamento,
        'concluidos': chamados_concluidos
    }

    return render_template('dashboard.html', stats=stats, user_name=user.nome, chamados=chamados_recentes)

@main.route('/chamados')
@login_required
def listar_chamados():
    """Lista todos os chamados"""
    chamados = Chamado.query.order_by(Chamado.data_criacao.desc()).all()
    return render_template('chamados.html', chamados=chamados)

@main.route('/novo_chamado', methods=['GET', 'POST'])
@login_required
def novo_chamado():
    """Criar novo chamado"""
    clientes = Cliente.query.all()
    if request.method == 'POST':
        try:
            numero_chamado = gerar_numero_chamado()
            chamado = Chamado(
                numero_chamado=numero_chamado,
                cliente_id=int(request.form['cliente_id']),
                equipamento=request.form.get('equipamento'),
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

        except Exception as e:
            flash(f'Erro ao criar chamado: {str(e)}', 'error')
            db.session.rollback()

    return render_template('novo_chamado.html', clientes=clientes)

@main.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_chamado(id):
    """Editar chamado existente"""
    chamado = Chamado.query.get_or_404(id)
    clientes = Cliente.query.all()

    if request.method == 'POST':
        try:
            chamado.cliente_id = int(request.form['cliente_id'])
            chamado.equipamento = request.form.get('equipamento')
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

        except Exception as e:
            flash(f'Erro ao atualizar chamado: {str(e)}', 'error')
            db.session.rollback()

    return render_template('editar_chamado.html', chamado=chamado, clientes=clientes)

@main.route('/clientes')
@login_required
def listar_clientes():
    """Lista todos os clientes"""
    clientes = Cliente.query.order_by(Cliente.data_criacao.desc()).all()
    return render_template('clientes.html', clientes=clientes)

@main.route('/novo_cliente', methods=['GET', 'POST'])
@login_required
def novo_cliente():
    """Criar novo cliente"""
    if request.method == 'POST':
        try:
            cliente = Cliente(
                nome=request.form['nome'],
                endereco=request.form['endereco'],
                telefone=request.form['telefone'],
                responsavel=request.form['responsavel'],
                telefone_responsavel=request.form['telefone_responsavel']
            )

            db.session.add(cliente)
            db.session.commit()

            flash('Cliente criado com sucesso!', 'success')
            return redirect(url_for('main.listar_clientes'))

        except Exception as e:
            flash(f'Erro ao criar cliente: {str(e)}', 'error')
            db.session.rollback()

    return render_template('novo_cliente.html')

@main.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_cliente(id):
    """Editar cliente existente"""
    cliente = Cliente.query.get_or_404(id)

    if request.method == 'POST':
        try:
            cliente.nome = request.form['nome']
            cliente.endereco = request.form['endereco']
            cliente.telefone = request.form['telefone']
            cliente.responsavel = request.form['responsavel']
            cliente.telefone_responsavel = request.form['telefone_responsavel']

            db.session.commit()
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_clientes'))

        except Exception as e:
            flash(f'Erro ao atualizar cliente: {str(e)}', 'error')
            db.session.rollback()

    return render_template('editar_cliente.html', cliente=cliente)

@main.route('/api/chamados/<int:id>/status', methods=['POST'])
@login_required
def atualizar_status(id):
    """API para atualizar status do chamado"""
    try:
        chamado = Chamado.query.get_or_404(id)
        novo_status = request.json.get('status')

        chamado.status = novo_status
        if novo_status == 'Concluído' and not chamado.data_conclusao:
            chamado.data_conclusao = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Status atualizado com sucesso'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400


@main.route('/usuarios')
@login_required
def listar_usuarios():
    """Lista todos os usuários"""
    usuarios = Usuario.query.order_by(Usuario.data_criacao.desc()).all()
    return render_template('usuarios.html', usuarios=usuarios)


@main.route('/novo_usuario', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    """Criar novo usuário"""
    if request.method == 'POST':
        try:
            hashed_senha = generate_password_hash(request.form['senha'])
            usuario = Usuario(
                nome=request.form['nome'],
                email=request.form['email'],
                senha=hashed_senha,
                tipo=request.form.get('tipo', 'operador'),
                ativo=True
            )
            db.session.add(usuario)
            db.session.commit()
            flash('Usuário criado com sucesso!', 'success')
            return redirect(url_for('main.listar_usuarios'))
        except Exception as e:
            flash(f'Erro ao criar usuário: {str(e)}', 'error')
            db.session.rollback()
    return render_template('novo_usuario.html')


@main.route('/usuarios/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    """Editar usuário existente"""
    usuario = Usuario.query.get_or_404(id)
    if request.method == 'POST':
        try:
            usuario.nome = request.form['nome']
            usuario.email = request.form['email']
            if request.form['senha']:  # Atualiza senha apenas se fornecida
                usuario.senha = generate_password_hash(request.form['senha'])
            usuario.tipo = request.form.get('tipo', 'operador')
            usuario.ativo = request.form.get('ativo', True) == 'on'
            db.session.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_usuarios'))
        except Exception as e:
            flash(f'Erro ao atualizar usuário: {str(e)}', 'error')
            db.session.rollback()
    return render_template('editar_usuario.html', usuario=usuario)


@main.route('/equipamentos')
@login_required
def listar_equipamentos():
    """Lista todos os equipamentos"""
    equipamentos = Equipamento.query.order_by(Equipamento.data_criacao.desc()).all()
    return render_template('equipamentos.html', equipamentos=equipamentos)


@main.route('/novo_equipamento', methods=['GET', 'POST'])
@login_required
def novo_equipamento():
    """Criar novo equipamento"""
    clientes = Cliente.query.all()
    if request.method == 'POST':
        try:
            data_compra = datetime.strptime(request.form['data_compra'], '%Y-%m-%d').date() if request.form['data_compra'] else None
            data_manutencao = datetime.strptime(request.form['data_manutencao'], '%Y-%m-%d').date() if request.form['data_manutencao'] else None
            cliente_id = request.form.get('cliente_id')
            if not cliente_id and request.form.get('localizacao'):
                cli = Cliente.query.filter_by(nome=request.form['localizacao']).first()
                cliente_id = cli.id if cli else None
            if not cliente_id:
                flash('Selecione um cliente/localização válido.', 'error')
                return render_template('novo_equipamento.html', clientes=clientes)
            equipamento = Equipamento(
                nome_equipamento=request.form['nome_equipamento'],
                modelo=request.form['modelo'],
                numero_serie=request.form['numero_serie'] or None,
                patrimonio=request.form['patrimonio'] or None,
                localizacao=request.form['localizacao'],
                ativo=request.form.get('ativo') == 'on',
                data_compra=data_compra,
                data_manutencao=data_manutencao,
                cliente_id=int(cliente_id)
            )
            db.session.add(equipamento)
            db.session.commit()
            flash('Equipamento criado com sucesso!', 'success')
            return redirect(url_for('main.listar_equipamentos'))
        except Exception as e:
            flash(f'Erro ao criar equipamento: {str(e)}', 'error')
            db.session.rollback()
    return render_template('novo_equipamento.html', clientes=clientes)


@main.route('/equipamentos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_equipamento(id):
    """Editar equipamento existente"""
    equipamento = Equipamento.query.get_or_404(id)
    clientes = Cliente.query.all()
    if request.method == 'POST':
        try:
            equipamento.nome_equipamento = request.form['nome_equipamento']
            equipamento.modelo = request.form['modelo']
            equipamento.numero_serie = request.form['numero_serie']
            equipamento.patrimonio = request.form['patrimonio']
            equipamento.localizacao = request.form['localizacao']
            equipamento.ativo = request.form.get('ativo', True) == 'on'
            if request.form['data_compra']:
                equipamento.data_compra = datetime.strptime(request.form['data_compra'], '%Y-%m-%d')
            else:
                equipamento.data_compra = None
            if request.form['data_manutencao']:
                equipamento.data_manutencao = datetime.strptime(request.form['data_manutencao'], '%Y-%m-%d')
            else:
                equipamento.data_manutencao = None
            db.session.commit()
            flash('Equipamento atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_equipamentos'))
        except Exception as e:
            flash(f'Erro ao atualizar equipamento: {str(e)}', 'error')
            db.session.rollback()
    return render_template('editar_equipamento.html', equipamento=equipamento, clientes=clientes)

@main.route('/relatorios')
#@login_required
def relatorios():
    """Página de relatórios gerenciais"""
    # Top clientes por número de chamados
    top_clientes = db.session.query(
        Cliente.nome,
        func.count(Chamado.id).label('total_chamados')
    ).join(Chamado).group_by(Cliente.id).order_by(func.count(Chamado.id).desc()).limit(10).all()

    # Top equipamentos por número de chamados
    top_equipamentos = db.session.query(
        Chamado.equipamento,
        func.count(Chamado.id).label('total_chamados')
    ).filter(Chamado.equipamento.isnot(None)).group_by(Chamado.equipamento).order_by(func.count(Chamado.id).desc()).limit(10).all()

    # Para equipamentos, obter os problemas (tipo_servico e descricao)
    equipamentos_problemas = {}
    for eq in top_equipamentos:
        problemas = Chamado.query.filter_by(equipamento=eq[0]).with_entities(Chamado.tipo_servico, Chamado.descricao).all()
        equipamentos_problemas[eq[0]] = problemas

    return render_template('relatorios.html', top_clientes=top_clientes, top_equipamentos=top_equipamentos, equipamentos_problemas=equipamentos_problemas)

@main.route('/api/equipamentos_por_cliente/<cliente_nome>', methods=['GET'])
@login_required
def equipamentos_por_cliente(cliente_nome):
    """API para retornar equipamentos filtrados por cliente (localizacao)"""
    equipamentos = Equipamento.query.filter_by(localizacao=cliente_nome).all()
    equipamentos_list = [{'patrimonio': e.patrimonio, 'nome_equipamento': e.nome_equipamento} for e in equipamentos]
    return jsonify(equipamentos_list)
