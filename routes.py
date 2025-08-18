from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from models import db, Chamado, Usuario
from datetime import datetime
import random
import string

main = Blueprint('main', __name__)

def gerar_numero_chamado():
    """Gera um número único para o chamado"""
    prefixo = "OS"
    numero = ''.join(random.choices(string.digits, k=6))
    return f"{prefixo}{numero}"

@main.route('/')
def dashboard():
    """Página principal do dashboard"""
    # Estatísticas básicas
    total_chamados = Chamado.query.count()
    chamados_pendentes = Chamado.query.filter_by(status='Pendente').count()
    chamados_em_andamento = Chamado.query.filter_by(status='Em Andamento').count()
    chamados_concluidos = Chamado.query.filter_by(status='Concluído').count()

    # Chamados recentes
    chamados_recentes = Chamado.query.order_by(Chamado.data_criacao.desc()).limit(10).all()

    stats = {
        'total': total_chamados,
        'pendentes': chamados_pendentes,
        'em_andamento': chamados_em_andamento,
        'concluidos': chamados_concluidos
    }

    return render_template('dashboard.html', stats=stats, chamados=chamados_recentes)

@main.route('/chamados')
def listar_chamados():
    """Lista todos os chamados"""
    status_filtro = request.args.get('status', '')
    busca = request.args.get('busca', '')

    query = Chamado.query

    if status_filtro:
        query = query.filter_by(status=status_filtro)

    if busca:
        query = query.filter(
            (Chamado.numero_chamado.contains(busca)) |
            (Chamado.cliente.contains(busca)) |
            (Chamado.tipo_servico.contains(busca))
        )

    chamados = query.order_by(Chamado.data_criacao.desc()).all()

    return render_template('chamados.html', chamados=chamados, status_filtro=status_filtro, busca=busca)

@main.route('/chamados/novo', methods=['GET', 'POST'])
def novo_chamado():
    """Criar novo chamado"""
    if request.method == 'POST':
        try:
            chamado = Chamado(
                numero_chamado=gerar_numero_chamado(),
                cliente=request.form['cliente'],
                tipo_servico=request.form['tipo_servico'],
                descricao=request.form['descricao'],
                prioridade=request.form['prioridade'],
                valor=float(request.form['valor']) if request.form['valor'] else None,
                observacoes=request.form['observacoes']
            )

            db.session.add(chamado)
            db.session.commit()

            flash('Chamado criado com sucesso!', 'success')
            return redirect(url_for('main.listar_chamados'))

        except Exception as e:
            flash(f'Erro ao criar chamado: {str(e)}', 'error')
            db.session.rollback()

    return render_template('novo_chamado.html')

@main.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
def editar_chamado(id):
    """Editar chamado existente"""
    chamado = Chamado.query.get_or_404(id)

    if request.method == 'POST':
        try:
            chamado.cliente = request.form['cliente']
            chamado.tipo_servico = request.form['tipo_servico']
            chamado.descricao = request.form['descricao']
            chamado.status = request.form['status']
            chamado.prioridade = request.form['prioridade']
            chamado.valor = float(request.form['valor']) if request.form['valor'] else None
            chamado.observacoes = request.form['observacoes']

            if request.form['status'] == 'Concluído' and not chamado.data_conclusao:
                chamado.data_conclusao = datetime.utcnow()

            db.session.commit()
            flash('Chamado atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_chamados'))

        except Exception as e:
            flash(f'Erro ao atualizar chamado: {str(e)}', 'error')
            db.session.rollback()

    return render_template('editar_chamado.html', chamado=chamado)

@main.route('/api/chamados/<int:id>/status', methods=['POST'])
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

