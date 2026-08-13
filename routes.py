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
from models import db, Chamado, Usuario, Cliente, Equipamento, ConfiguracaoEmail
from permissions_sistemas import SISTEMAS, aplicar_permissoes_formulario, conceder_acesso_total
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from datetime import datetime, timedelta
import os
import random
import secrets
import string

main = Blueprint('main', __name__)


def _http_cert_download_url() -> str:
    """URL HTTP (sem TLS) para baixar o .cer — evita aviso SSL no instalador."""
    host = (request.host or '127.0.0.1').split(':')[0]
    http_port = '80'
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


RESET_VALIDADE_HORAS = 2
MSG_RESET_ENVIADO = (
    'Se o e-mail estiver cadastrado, enviamos um link para redefinir a senha.'
)


def _gerar_link_redefinicao(usuario):
    token = secrets.token_urlsafe(32)
    usuario.reset_token = token
    usuario.reset_token_expira = datetime.utcnow() + timedelta(hours=RESET_VALIDADE_HORAS)
    db.session.commit()
    return url_for('main.redefinir_senha', token=token, _external=True)


def _enviar_link_redefinicao(usuario):
    from email_service import enviar_redefinicao_senha

    link = _gerar_link_redefinicao(usuario)
    enviar_redefinicao_senha(usuario.email, usuario.nome or 'usuário', link)


def _usuario_por_token_reset(token):
    if not token:
        return None
    usuario = Usuario.query.filter_by(reset_token=token, ativo=True).first()
    if not usuario or not usuario.reset_token_expira:
        return None
    if usuario.reset_token_expira < datetime.utcnow():
        return None
    return usuario


@main.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    if request.method == 'POST':
        from email_service import smtp_configurado

        if not smtp_configurado():
            flash(
                'O envio de e-mail ainda não está configurado no servidor. Fale com a informática.',
                'error',
            )
            return render_template('esqueci_senha.html')
        email = (request.form.get('email') or '').strip().lower()
        usuario = Usuario.query.filter_by(email=email, ativo=True).first() if email else None
        if usuario:
            try:
                _enviar_link_redefinicao(usuario)
            except Exception as exc:
                print(f'Falha ao enviar e-mail de redefinição: {exc}')
                flash(
                    'Não foi possível enviar o e-mail agora. Tente novamente ou fale com a informática.',
                    'error',
                )
                return render_template('esqueci_senha.html')
        flash(MSG_RESET_ENVIADO, 'success')
        return redirect(url_for('main.login'))
    return render_template('esqueci_senha.html')


@main.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    usuario = _usuario_por_token_reset(token)
    if not usuario:
        flash('Este link de redefinição é inválido ou já expirou. Solicite um novo.', 'error')
        return redirect(url_for('main.esqueci_senha'))

    if request.method == 'POST':
        nova = request.form.get('senha') or ''
        confirma = request.form.get('confirma_senha') or ''
        if len(nova) < 6:
            flash('A nova senha deve ter pelo menos 6 caracteres.', 'error')
            return render_template('redefinir_senha.html', token=token)
        if nova != confirma:
            flash('A confirmação não confere com a nova senha.', 'error')
            return render_template('redefinir_senha.html', token=token)
        usuario.senha = generate_password_hash(nova)
        usuario.reset_token = None
        usuario.reset_token_expira = None
        db.session.commit()
        flash('Senha redefinida. Faça login com a nova senha.', 'success')
        return redirect(url_for('main.login'))

    return render_template('redefinir_senha.html', token=token)


@main.route('/alterar-senha', methods=['GET', 'POST'])
@login_required
def alterar_senha():
    usuario = Usuario.query.get(session['user_id'])
    if not usuario:
        flash('Usuário não encontrado.', 'error')
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        acao = request.form.get('acao') or 'alterar'
        if acao == 'enviar_email':
            try:
                _enviar_link_redefinicao(usuario)
                flash(f'Enviamos o link de redefinição para {usuario.email}.', 'success')
            except Exception as exc:
                print(f'Falha ao enviar e-mail de redefinição: {exc}')
                flash(
                    'Não foi possível enviar o e-mail agora. Confira a configuração SMTP ou tente de novo.',
                    'error',
                )
            return redirect(url_for('main.alterar_senha'))

        atual = request.form.get('senha_atual') or ''
        nova = request.form.get('senha') or ''
        confirma = request.form.get('confirma_senha') or ''
        if not check_password_hash(usuario.senha, atual):
            flash('A senha atual está incorreta.', 'error')
            return render_template('alterar_senha.html', usuario=usuario)
        if len(nova) < 6:
            flash('A nova senha deve ter pelo menos 6 caracteres.', 'error')
            return render_template('alterar_senha.html', usuario=usuario)
        if nova != confirma:
            flash('A confirmação não confere com a nova senha.', 'error')
            return render_template('alterar_senha.html', usuario=usuario)
        usuario.senha = generate_password_hash(nova)
        usuario.reset_token = None
        usuario.reset_token_expira = None
        db.session.commit()
        flash('Senha alterada com sucesso.', 'success')
        return redirect(url_for('main.inicio'))

    return render_template('alterar_senha.html', usuario=usuario)


def _wants_json():
    accept = request.headers.get('Accept') or ''
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in accept
    )


def _acesso_payload(usuario):
    return {
        'id': usuario.id,
        'nome': usuario.nome,
        'email': usuario.email,
        'ativo': bool(usuario.ativo),
        'is_master': bool(usuario.is_master),
        'sistemas': {chave: usuario.tem_sistema(chave) for chave in SISTEMAS},
        'permissoes': {sistema: usuario.menus_liberados(sistema) for sistema in SISTEMAS},
    }


@main.route('/')
@login_required
def inicio():
    """Tela inicial de escolha entre os sistemas"""
    user = Usuario.query.get(session['user_id'])
    sistemas_liberados = []
    if user:
        for chave, meta in SISTEMAS.items():
            if user.tem_sistema(chave):
                sistemas_liberados.append(chave)

    acessos = []
    acessos_js = []
    smtp_cfg = {'servidor': '', 'porta': 587, 'usar_tls': True, 'usuario': '', 'remetente': ''}
    senha_salva = False
    smtp_ok = False
    if user and user.pode_gerenciar_acessos():
        from email_service import obter_config_smtp, smtp_configurado
        acessos = Usuario.query.order_by(Usuario.data_criacao.desc()).all()
        acessos_js = [_acesso_payload(a) for a in acessos]
        raw_cfg = obter_config_smtp()
        smtp_cfg = {k: v for k, v in raw_cfg.items() if k != 'senha'}
        row = ConfiguracaoEmail.query.get(1)
        senha_salva = bool(row and row.senha) or bool(raw_cfg.get('senha'))
        smtp_ok = smtp_configurado()

    return render_template(
        'inicio.html',
        user_name=user.nome if user else session.get('user_name', 'Usuário'),
        usuario=user,
        sistemas_liberados=sistemas_liberados,
        acessos=acessos,
        acessos_js=acessos_js,
        sistemas=SISTEMAS,
        smtp_cfg=smtp_cfg,
        senha_salva=senha_salva,
        smtp_ok=smtp_ok,
    )


@main.route('/acessos')
@login_required
def listar_acessos():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.pode_gerenciar_acessos():
        flash('Você não tem permissão para gerenciar acessos.', 'error')
        return redirect(url_for('main.inicio'))
    acessos = Usuario.query.order_by(Usuario.data_criacao.desc()).all()
    return render_template('acessos.html', acessos=acessos, user_name=user.nome)


def _exigir_gestao_acessos():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.pode_gerenciar_acessos():
        flash('Você não tem permissão para acessar as configurações.', 'error')
        return None
    return user


@main.route('/configuracoes', methods=['GET', 'POST'])
@login_required
def configuracoes():
    user = _exigir_gestao_acessos()
    if not user:
        return redirect(url_for('main.inicio'))

    from email_service import obter_config_smtp, smtp_configurado

    if request.method == 'POST':
        servidor = (request.form.get('servidor') or '').strip()
        usuario_smtp = (request.form.get('usuario') or '').strip()
        remetente = (request.form.get('remetente') or '').strip()
        senha_nova = request.form.get('senha') or ''
        try:
            porta = int(request.form.get('porta') or 587)
        except ValueError:
            if _wants_json():
                return jsonify({'ok': False, 'message': 'A porta SMTP precisa ser um número.'}), 400
            flash('A porta SMTP precisa ser um número.', 'error')
            return redirect(url_for('main.configuracoes'))
        if porta < 1 or porta > 65535:
            if _wants_json():
                return jsonify({'ok': False, 'message': 'A porta SMTP é inválida.'}), 400
            flash('A porta SMTP é inválida.', 'error')
            return redirect(url_for('main.configuracoes'))
        if not servidor or not remetente:
            if _wants_json():
                return jsonify({'ok': False, 'message': 'Servidor SMTP e remetente (From) são obrigatórios.'}), 400
            flash('Servidor SMTP e remetente (From) são obrigatórios.', 'error')
            return redirect(url_for('main.configuracoes'))

        row = ConfiguracaoEmail.query.get(1)
        if not row:
            row = ConfiguracaoEmail(id=1)
            db.session.add(row)
        row.servidor = servidor
        row.porta = porta
        row.usar_tls = request.form.get('usar_tls') == 'on'
        row.usuario = usuario_smtp
        row.remetente = remetente
        if senha_nova:
            row.senha = senha_nova
        db.session.commit()
        if _wants_json():
            cfg_atual = obter_config_smtp()
            return jsonify({
                'ok': True,
                'message': 'Configurações de e-mail salvas.',
                'smtp_ok': smtp_configurado(),
                'senha_salva': bool(row.senha) or bool(cfg_atual.get('senha')),
            })
        flash('Configurações de e-mail salvas.', 'success')
        return redirect(url_for('main.configuracoes'))

    cfg = obter_config_smtp()
    row = ConfiguracaoEmail.query.get(1)
    senha_salva = bool(row and row.senha) or bool(cfg.get('senha'))
    return render_template(
        'configuracoes.html',
        user_name=user.nome,
        cfg=cfg,
        senha_salva=senha_salva,
        smtp_ok=smtp_configurado(),
    )


def _salvar_acesso_geral(usuario, form, novo=False):
    email = (form.get('email') or '').strip().lower()
    nome = (form.get('nome') or '').strip()
    senha = form.get('senha') or ''
    if not nome or not email:
        raise ValueError('Nome e e-mail são obrigatórios.')
    outro = Usuario.query.filter(Usuario.email == email, Usuario.id != usuario.id).first()
    if outro:
        raise ValueError('Já existe um acesso com este e-mail.')
    usuario.nome = nome
    usuario.email = email
    if senha:
        usuario.senha = generate_password_hash(senha)
    elif novo:
        raise ValueError('A senha é obrigatória para um novo acesso.')
    if not usuario.is_master:
        usuario.ativo = form.get('ativo') == 'on'
        usuario.tipo = form.get('tipo', 'operador')
    db.session.add(usuario)
    db.session.flush()
    if usuario.is_master:
        conceder_acesso_total(usuario)
    else:
        aplicar_permissoes_formulario(usuario, form)
    db.session.commit()


@main.route('/acessos/novo', methods=['GET', 'POST'])
@login_required
def novo_acesso():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.pode_gerenciar_acessos():
        flash('Você não tem permissão para gerenciar acessos.', 'error')
        return redirect(url_for('main.inicio'))
    if request.method == 'POST':
        try:
            acesso = Usuario(ativo=True, tipo='operador')
            _salvar_acesso_geral(acesso, request.form, novo=True)
            if _wants_json():
                return jsonify({
                    'ok': True,
                    'message': 'Acesso cadastrado com sucesso!',
                    'acesso': _acesso_payload(acesso),
                })
            flash('Acesso cadastrado com sucesso!', 'success')
            return redirect(url_for('main.listar_acessos'))
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({'ok': False, 'message': str(e)}), 400
            flash(str(e), 'error')
    return render_template(
        'acesso_form.html',
        acesso=None,
        sistemas=SISTEMAS,
        permissoes={},
        user_name=user.nome,
    )


@main.route('/acessos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_acesso(id):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.pode_gerenciar_acessos():
        flash('Você não tem permissão para gerenciar acessos.', 'error')
        return redirect(url_for('main.inicio'))
    acesso = Usuario.query.get_or_404(id)
    if request.method == 'POST':
        try:
            _salvar_acesso_geral(acesso, request.form, novo=False)
            if _wants_json():
                return jsonify({
                    'ok': True,
                    'message': 'Acesso atualizado com sucesso!',
                    'acesso': _acesso_payload(acesso),
                })
            flash('Acesso atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_acessos'))
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({'ok': False, 'message': str(e)}), 400
            flash(str(e), 'error')
    permissoes = {sistema: acesso.menus_liberados(sistema) for sistema in SISTEMAS}
    return render_template(
        'acesso_form.html',
        acesso=acesso,
        sistemas=SISTEMAS,
        permissoes=permissoes,
        user_name=user.nome,
    )

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


def _aplicar_menus_chamados(usuario, form):
    from models import PermissaoMenu
    usuario.perm_chamados = True
    for menu_key, _label in SISTEMAS['chamados']['menus']:
        permitido = usuario.is_master or form.get(f'menu_chamados_{menu_key}') == 'on'
        perm = usuario.menus.filter_by(sistema='chamados', menu_key=menu_key).first()
        if not perm:
            db.session.add(PermissaoMenu(
                usuario_id=usuario.id,
                sistema='chamados',
                menu_key=menu_key,
                permitido=permitido,
            ))
        else:
            perm.permitido = permitido


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
            usuario.perm_chamados = True
            db.session.add(usuario)
            db.session.flush()
            _aplicar_menus_chamados(usuario, request.form)
            db.session.commit()
            flash('Usuário criado com sucesso!', 'success')
            return redirect(url_for('main.listar_usuarios'))
        except Exception as e:
            flash(f'Erro ao criar usuário: {str(e)}', 'error')
            db.session.rollback()
    return render_template('novo_usuario.html', menus_chamados=SISTEMAS['chamados']['menus'])


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
            usuario.perm_chamados = True
            _aplicar_menus_chamados(usuario, request.form)
            db.session.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_usuarios'))
        except Exception as e:
            flash(f'Erro ao atualizar usuário: {str(e)}', 'error')
            db.session.rollback()
    return render_template(
        'editar_usuario.html',
        usuario=usuario,
        menus_chamados=SISTEMAS['chamados']['menus'],
        permissoes=usuario.menus_liberados('chamados'),
    )


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


@main.route('/chamados/auditoria')
@login_required
def auditoria():
    """Auditoria dentro do layout de Gestão de Chamados (sidebar preservada)."""
    from datetime import date, timedelta
    from audit_service import listar_logs, ensure_audit_table
    from nutricao_service import _parse_date

    ensure_audit_table()
    hoje = date.today()
    data_de = _parse_date(request.args.get('data_de')) or (hoje - timedelta(days=7))
    data_ate = _parse_date(request.args.get('data_ate')) or hoje
    # Sem parâmetro: filtra chamados; modulo='' (Todos) vem do form como string vazia
    if 'modulo' in request.args:
        modulo = (request.args.get('modulo') or '').strip() or None
    else:
        modulo = 'chamados'
    usuario = (request.args.get('usuario') or '').strip() or None
    acao = (request.args.get('acao') or '').strip() or None
    q = (request.args.get('q') or '').strip() or None
    try:
        limit = min(int(request.args.get('limit') or 200), 500)
    except (TypeError, ValueError):
        limit = 200

    total, logs = listar_logs(
        modulo=modulo,
        usuario=usuario,
        acao=acao,
        q=q,
        data_de=data_de,
        data_ate=data_ate,
        limit=limit,
        offset=0,
    )
    return render_template(
        'auditoria.html',
        logs=logs,
        total=total,
        filtros={
            'data_de': data_de.isoformat(),
            'data_ate': data_ate.isoformat(),
            'modulo': modulo or '',
            'usuario': usuario or '',
            'acao': acao or '',
            'q': q or '',
            'limit': limit,
        },
    )


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
