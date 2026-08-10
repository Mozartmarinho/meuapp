from flask import (
    Blueprint,
    Response,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    session,
)
from functools import wraps
from password_utils import generate_password_hash, check_password_hash
from models import db, Chamado, Usuario, Cliente, Equipamento
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from datetime import datetime
import os
import random
import string

main = Blueprint('main', __name__)


def _http_cert_download_url() -> str:
    """URL HTTP (sem TLS) para baixar o .cer — evita aviso SSL no instalador."""
    host = (request.host or '127.0.0.1').split(':')[0]
    http_port = str(os.environ.get('PORT', '80')).strip() or '80'
    if http_port == '80':
        return f'http://{host}/certificado.cer'
    return f'http://{host}:{http_port}/certificado.cer'


def _build_trust_installer_bat(cert_url: str) -> str:
    """Gera .bat que baixa o .cer público e importa no Current User\\Root."""
    safe_url = cert_url.replace('"', '').replace("'", '')
    # Passa pasta do .bat e URL como argumentos (-Args) para evitar expansão frágil.
    return rf'''@echo off
setlocal EnableExtensions
title Instalar certificado local - Sao Geraldo
echo.
echo ========================================
echo  Instalar certificado HTTPS (local)
echo ========================================
echo.
echo Este script importa APENAS o certificado PUBLICO no
echo store do usuario atual (Autoridades Raiz Confiaveis).
echo O navegador NAO instala isso sozinho — voce precisa
echo executar este arquivo (pode aparecer aviso do SmartScreen).
echo.
echo URL do certificado: {safe_url}
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "& {{ param([string]$Dir,[string]$CertUrl); $ErrorActionPreference='Stop'; $beside=Join-Path $Dir 'sao-geraldo-local.cer'; if (Test-Path -LiteralPath $beside) {{ $p=$beside; Write-Host ('Usando: '+$p) }} else {{ $p=Join-Path $env:TEMP 'sao-geraldo-local.cer'; Write-Host ('Baixando de '+$CertUrl+' ...'); Invoke-WebRequest -Uri $CertUrl -OutFile $p -UseBasicParsing }}; $cert=New-Object System.Security.Cryptography.X509Certificates.X509Certificate2((Resolve-Path -LiteralPath $p)); $store=New-Object System.Security.Cryptography.X509Certificates.X509Store('Root','CurrentUser'); $store.Open('ReadWrite'); try {{ if ($store.Certificates | Where-Object {{ $_.Thumbprint -eq $cert.Thumbprint }}) {{ Write-Host ('Ja confiavel: '+$cert.Thumbprint) }} else {{ $store.Add($cert); Write-Host ('Importado em CurrentUser\\Root: '+$cert.Thumbprint) }} }} finally {{ $store.Close() }}; Write-Host ('Subject: '+$cert.Subject); Write-Host 'Feche e reabra o Chrome/Edge, depois abra o site em HTTPS.' }}" ^
  "%~dp0" "{safe_url}"

if errorlevel 1 (
  echo.
  echo FALHA. Baixe sao-geraldo-local.cer em /instalar-certificado,
  echo coloque na mesma pasta deste .bat e execute de novo.
  echo Ou use o metodo manual: clique duplo no .cer -^> Usuario atual
  echo -^> Autoridades de Certificacao Raiz Confiaveis.
  pause
  exit /b 1
)

echo.
echo Pronto. Reinicie o navegador para o aviso sumir.
pause
endlocal
'''

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

@main.route('/instalar-certificado')
@main.route('/https-ajuda')
def instalar_certificado():
    """Ajuda pública para confiar no certificado autoassinado (Windows)."""
    return render_template(
        'instalar_certificado.html',
        is_https=request.is_secure,
        cert_http_url=_http_cert_download_url(),
    )


@main.route('/certificado.cer')
def download_certificado_cer():
    """Serve só o certificado público em DER (.cer). Nunca a chave privada."""
    from generate_certs import load_public_cert_der

    try:
        der = load_public_cert_der()
    except Exception as exc:
        return (
            f'Certificado indisponível. Gere com generate_certs.py ({exc})',
            503,
            {'Content-Type': 'text/plain; charset=utf-8'},
        )
    return Response(
        der,
        mimetype='application/x-x509-ca-cert',
        headers={
            'Content-Disposition': 'attachment; filename="sao-geraldo-local.cer"',
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
        },
    )


@main.route('/downloads/instalar-certificado.bat')
def download_instalar_certificado_bat():
    """Instalador Windows: baixa o .cer público e importa no Trusted Root do usuário."""
    body = _build_trust_installer_bat(_http_cert_download_url())
    return Response(
        body,
        mimetype='application/x-bat',
        headers={
            'Content-Disposition': 'attachment; filename="instalar-certificado.bat"',
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
        },
    )


@main.route('/downloads/trust_local_cert.ps1')
def download_trust_local_cert_ps1():
    """PowerShell one-liner-friendly: importa .cer ao lado ou baixa via HTTP."""
    cert_url = _http_cert_download_url().replace("'", "''")
    body = f"""# Instala o certificado PUBLICO no Current User \\ Trusted Root.
# Uso: clique direito -> Executar com PowerShell
#  ou: powershell -ExecutionPolicy Bypass -File .\\trust_local_cert.ps1
#
# O navegador NAO instala CA sozinho — este script precisa da sua acao.

$ErrorActionPreference = 'Stop'
$CertUrl = '{cert_url}'
$CertPath = Join-Path $PSScriptRoot 'sao-geraldo-local.cer'
if (-not (Test-Path -LiteralPath $CertPath)) {{
    $CertPath = Join-Path $env:TEMP 'sao-geraldo-local.cer'
    Write-Host "Baixando certificado de $CertUrl ..."
    Invoke-WebRequest -Uri $CertUrl -OutFile $CertPath -UseBasicParsing
}}

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2((Resolve-Path -LiteralPath $CertPath))
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
    [System.Security.Cryptography.X509Certificates.StoreName]::Root,
    [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
$store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
try {{
    $existing = $store.Certificates | Where-Object {{ $_.Thumbprint -eq $cert.Thumbprint }}
    if ($existing) {{
        Write-Host "Ja confiavel: $($cert.Thumbprint)"
    }} else {{
        $store.Add($cert)
        Write-Host "Importado em CurrentUser\\Root: $($cert.Thumbprint)"
    }}
}} finally {{
    $store.Close()
}}

Write-Host "Subject: $($cert.Subject)"
Write-Host "Feche e reabra Chrome/Edge, depois abra o site em HTTPS."
"""
    return Response(
        body,
        mimetype='application/octet-stream',
        headers={
            'Content-Disposition': 'attachment; filename="trust_local_cert.ps1"',
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
        },
    )


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
            try:
                from audit_service import registrar_auditoria
                registrar_auditoria(
                    'login',
                    modulo='sistema',
                    entidade='usuario',
                    entidade_id=str(user.id),
                    detalhe={'email': email},
                    usuario_id=user.id,
                    usuario_nome=user.nome,
                    status_http=200,
                    sucesso=True,
                )
            except Exception:
                pass
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('main.inicio'))
        else:
            try:
                from audit_service import registrar_auditoria
                registrar_auditoria(
                    'login',
                    modulo='sistema',
                    entidade='usuario',
                    detalhe={'email': email, 'resultado': 'falha'},
                    usuario_nome=email,
                    status_http=401,
                    sucesso=False,
                )
            except Exception:
                pass
            flash('Email ou senha incorretos.', 'error')
    return render_template('login.html', show_https_cert_help=request.is_secure)

@main.route('/logout')
def logout():
    """Logout do usuário"""
    try:
        from audit_service import registrar_auditoria
        registrar_auditoria(
            'logout',
            modulo='sistema',
            entidade='usuario',
            entidade_id=str(session.get('user_id') or ''),
            detalhe='Logout',
            sucesso=True,
            status_http=200,
        )
    except Exception:
        pass
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

@main.route('/configuracoes')
@login_required
def configuracoes():
    """Página placeholder de configurações do módulo de chamados"""
    return render_template('configuracoes.html')


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
