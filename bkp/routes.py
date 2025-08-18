from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from models import db, Pedido, Usuario
from datetime import datetime
import random
import string

main = Blueprint('main', __name__)

def gerar_numero_pedido():
    """Gera um número único para o pedido"""
    prefixo = "OS"
    numero = ''.join(random.choices(string.digits, k=6))
    return f"{prefixo}{numero}"

@main.route('/')
def dashboard():
    """Página principal do dashboard"""
    # Estatísticas básicas
    total_pedidos = Pedido.query.count()
    pedidos_pendentes = Pedido.query.filter_by(status='Pendente').count()
    pedidos_em_andamento = Pedido.query.filter_by(status='Em Andamento').count()
    pedidos_concluidos = Pedido.query.filter_by(status='Concluído').count()
    
    # Pedidos recentes
    pedidos_recentes = Pedido.query.order_by(Pedido.data_criacao.desc()).limit(10).all()
    
    stats = {
        'total': total_pedidos,
        'pendentes': pedidos_pendentes,
        'em_andamento': pedidos_em_andamento,
        'concluidos': pedidos_concluidos
    }
    
    return render_template('dashboard.html', stats=stats, pedidos=pedidos_recentes)

@main.route('/pedidos')
def listar_pedidos():
    """Lista todos os pedidos"""
    status_filtro = request.args.get('status', '')
    busca = request.args.get('busca', '')
    
    query = Pedido.query
    
    if status_filtro:
        query = query.filter_by(status=status_filtro)
    
    if busca:
        query = query.filter(
            (Pedido.numero_pedido.contains(busca)) |
            (Pedido.cliente.contains(busca)) |
            (Pedido.tipo_servico.contains(busca))
        )
    
    pedidos = query.order_by(Pedido.data_criacao.desc()).all()
    
    return render_template('pedidos.html', pedidos=pedidos, status_filtro=status_filtro, busca=busca)

@main.route('/pedidos/novo', methods=['GET', 'POST'])
def novo_pedido():
    """Criar novo pedido"""
    if request.method == 'POST':
        try:
            pedido = Pedido(
                numero_pedido=gerar_numero_pedido(),
                cliente=request.form['cliente'],
                tipo_servico=request.form['tipo_servico'],
                descricao=request.form['descricao'],
                prioridade=request.form['prioridade'],
                valor=float(request.form['valor']) if request.form['valor'] else None,
                observacoes=request.form['observacoes']
            )
            
            db.session.add(pedido)
            db.session.commit()
            
            flash('Pedido criado com sucesso!', 'success')
            return redirect(url_for('main.listar_pedidos'))
            
        except Exception as e:
            flash(f'Erro ao criar pedido: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('novo_pedido.html')

@main.route('/pedidos/<int:id>/editar', methods=['GET', 'POST'])
def editar_pedido(id):
    """Editar pedido existente"""
    pedido = Pedido.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            pedido.cliente = request.form['cliente']
            pedido.tipo_servico = request.form['tipo_servico']
            pedido.descricao = request.form['descricao']
            pedido.status = request.form['status']
            pedido.prioridade = request.form['prioridade']
            pedido.valor = float(request.form['valor']) if request.form['valor'] else None
            pedido.observacoes = request.form['observacoes']
            
            if request.form['status'] == 'Concluído' and not pedido.data_conclusao:
                pedido.data_conclusao = datetime.utcnow()
            
            db.session.commit()
            flash('Pedido atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_pedidos'))
            
        except Exception as e:
            flash(f'Erro ao atualizar pedido: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('editar_pedido.html', pedido=pedido)

@main.route('/api/pedidos/<int:id>/status', methods=['POST'])
def atualizar_status(id):
    """API para atualizar status do pedido"""
    try:
        pedido = Pedido.query.get_or_404(id)
        novo_status = request.json.get('status')
        
        pedido.status = novo_status
        if novo_status == 'Concluído' and not pedido.data_conclusao:
            pedido.data_conclusao = datetime.utcnow()
        
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
