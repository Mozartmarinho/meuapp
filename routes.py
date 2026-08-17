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
from models import (
    db,
    Chamado,
    Usuario,
    Cliente,
    Equipamento,
    ConfiguracaoEmail,
    ChamadoAtendimento,
    ChamadoFoto,
    TIPO_FOTO_CONSERTO,
    TIPO_FOTO_ENCAMINHAMENTO,
    SETORES_CHAMADO,
    STATUS_AGUARDAR_PECA,
    STATUS_ENCAMINHADO,
    STATUS_ATENDIDO,
    STATUS_FECHADOS,
    status_fechado,
    normalizar_setor_chamado,
)
from permissions_sistemas import SISTEMAS, aplicar_permissoes_formulario, conceder_acesso_total
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_, and_
from sqlalchemy.exc import IntegrityError
from datetime import date, datetime, timedelta
from pathlib import Path
from werkzeug.utils import secure_filename
import os
import random
import secrets
import string
import uuid

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


_CHAMADOS_ENDPOINT_MENUS = {
    'main.dashboard': 'dashboard',
    'main.listar_chamados': 'chamados',
    'main.novo_chamado': 'novo_chamado',
    'main.editar_chamado': 'chamados',
    'main.listar_clientes': 'clientes',
    'main.novo_cliente': 'clientes',
    'main.editar_cliente': 'clientes',
    'main.listar_equipamentos': 'equipamentos',
    'main.novo_equipamento': 'equipamentos',
    'main.editar_equipamento': 'equipamentos',
    'main.api_equipamentos': 'equipamentos',
    'main.api_equipamento': 'equipamentos',
    'main.relatorios': 'relatorios',
    'main.auditoria': 'auditoria',
}


@main.before_request
def _checar_permissao_menu_chamados():
    menu_key = _CHAMADOS_ENDPOINT_MENUS.get(request.endpoint)
    if not menu_key:
        return None
    if 'user_id' not in session:
        return None
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_sistema('chamados'):
        flash('Você não tem permissão para o Sistema de Gestão de Chamados.', 'error')
        return redirect(url_for('main.inicio'))
    if user.tem_menu('chamados', menu_key):
        return None
    if (request.path or '').startswith('/api/'):
        return jsonify({'ok': False, 'error': 'Você não tem permissão para acessar esta aba.'}), 403
    flash('Você não tem permissão para acessar esta aba.', 'error')
    return redirect(url_for('main.inicio'))


def _parse_data_compra(valor):
    raw = (valor or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _vincular_equipamento_chamado(chamado, form, cliente_id):
    """Grava patrimônio, nome e FK a partir do cadastro de equipamentos."""
    eq_id_raw = (form.get('equipamento_id') or '').strip()
    codigo = (form.get('patrimonio') or '').strip()
    nome_form = (form.get('equipamento') or '').strip()
    eq = None
    if eq_id_raw.isdigit():
        eq = Equipamento.query.filter_by(id=int(eq_id_raw), cliente_id=cliente_id).first()
    if not eq and codigo:
        eq = Equipamento.query.filter_by(patrimonio=codigo, cliente_id=cliente_id).first()
        if not eq:
            eq = Equipamento.query.filter_by(patrimonio=codigo).first()
    if eq:
        chamado.equipamento_id = eq.id
        chamado.patrimonio = eq.patrimonio
        chamado.equipamento = eq.nome_equipamento
        return
    chamado.equipamento_id = None
    chamado.patrimonio = codigo or None
    chamado.equipamento = nome_form or None

def gerar_numero_chamado():
    """Gera um número único para o chamado"""
    prefixo = "OS"
    numero = ''.join(random.choices(string.digits, k=6))
    return f"{prefixo}{numero}"


_FOTO_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
_UPLOAD_CHAMADOS = Path(__file__).resolve().parent / 'static' / 'uploads' / 'chamados'


def _setor_usuario(usuario):
    return normalizar_setor_chamado(getattr(usuario, 'setor', None) if usuario else '')


def _eh_gestor(usuario):
    return bool(usuario and (usuario.is_master or usuario.tipo == 'admin'))


def _pendencias_chamados(usuario):
    """Pendências do login: encaminhamentos ao setor do usuário e chamados aguardando peça."""
    if not usuario:
        return []
    setor = _setor_usuario(usuario)
    gestor = _eh_gestor(usuario)
    seen = set()
    items = []
    rows = (
        Chamado.query.options(joinedload(Chamado.cliente), joinedload(Chamado.encaminhado_por))
        .filter(~Chamado.status.in_(STATUS_FECHADOS))
        .order_by(Chamado.data_criacao.desc())
        .all()
    )
    for chamado in rows:
        dest = normalizar_setor_chamado(chamado.setor_destino)
        encaminhado_para_mim = bool(dest) and (gestor or dest == setor)
        aguardar_peca = chamado.status == STATUS_AGUARDAR_PECA and (
            gestor or chamado.tecnico_id == usuario.id or dest == setor
        )
        if not encaminhado_para_mim and not aguardar_peca:
            continue
        if chamado.id in seen:
            continue
        seen.add(chamado.id)
        if encaminhado_para_mim and aguardar_peca:
            tipo = 'Aguardar peça / Encaminhado'
        elif encaminhado_para_mim:
            tipo = 'Encaminhado'
        else:
            tipo = STATUS_AGUARDAR_PECA
        encaminhado_por = chamado.encaminhado_por
        items.append({
            'id': chamado.id,
            'numero_chamado': chamado.numero_chamado,
            'cliente': chamado.cliente.nome if chamado.cliente else 'N/A',
            'status': chamado.status,
            'tipo': tipo,
            'setor_destino': dest or '',
            'instrucoes': chamado.encaminhamento_instrucoes or '',
            'fotos': _fotos_chamado_payload(chamado, TIPO_FOTO_ENCAMINHAMENTO),
            'encaminhado_por': encaminhado_por.nome if encaminhado_por else '',
            'encaminhado_em': (
                chamado.encaminhado_em.strftime('%d/%m/%Y %H:%M') if chamado.encaminhado_em else ''
            ),
            'url_atender': url_for('main.listar_chamados', atender=chamado.id),
        })
    return items


def _tipo_foto_chamado(foto):
    tipo = (getattr(foto, 'tipo', None) or '').strip().lower()
    if tipo == TIPO_FOTO_ENCAMINHAMENTO:
        return TIPO_FOTO_ENCAMINHAMENTO
    return TIPO_FOTO_CONSERTO


def _fotos_chamado_payload(chamado, tipo=None):
    itens = []
    for foto in chamado.fotos.order_by(ChamadoFoto.id.desc()).all():
        foto_tipo = _tipo_foto_chamado(foto)
        if tipo and foto_tipo != tipo:
            continue
        itens.append({
            'id': foto.id,
            'url': url_for('static', filename=foto.caminho),
            'nome': foto.nome_original or Path(foto.caminho).name,
            'tipo': foto_tipo,
        })
    return itens


def _arquivos_request(*nomes):
    arquivos = []
    for nome in nomes:
        arquivos.extend(request.files.getlist(nome))
    return arquivos


def _salvar_fotos_chamado(chamado, atendimento, arquivos, tipo=TIPO_FOTO_CONSERTO):
    _UPLOAD_CHAMADOS.mkdir(parents=True, exist_ok=True)
    tipo = TIPO_FOTO_ENCAMINHAMENTO if tipo == TIPO_FOTO_ENCAMINHAMENTO else TIPO_FOTO_CONSERTO
    for arquivo in arquivos:
        if not arquivo or not getattr(arquivo, 'filename', None):
            continue
        original = secure_filename(arquivo.filename)
        if not original:
            continue
        ext = Path(original).suffix.lower()
        if ext not in _FOTO_EXTS:
            continue
        fname = f'ch_{chamado.id}_{uuid.uuid4().hex[:10]}{ext}'
        dest = _UPLOAD_CHAMADOS / fname
        arquivo.save(str(dest))
        db.session.add(ChamadoFoto(
            chamado_id=chamado.id,
            atendimento_id=atendimento.id if atendimento else None,
            caminho=f'uploads/chamados/{fname}',
            nome_original=original,
            tipo=tipo,
        ))


def _chamado_atender_payload(chamado):
    todas = _fotos_chamado_payload(chamado)
    return {
        'id': chamado.id,
        'numero_chamado': chamado.numero_chamado,
        'cliente': chamado.cliente.nome if chamado.cliente else 'N/A',
        'status': chamado.status,
        'prioridade': chamado.prioridade,
        'descricao': chamado.descricao or '',
        'atendimento_notas': chamado.atendimento_notas or '',
        'setor_destino': chamado.setor_destino or '',
        'encaminhamento_instrucoes': chamado.encaminhamento_instrucoes or '',
        'fotos': [f for f in todas if f['tipo'] != TIPO_FOTO_ENCAMINHAMENTO],
        'fotos_encaminhamento': [f for f in todas if f['tipo'] == TIPO_FOTO_ENCAMINHAMENTO],
        'setores': list(SETORES_CHAMADO),
    }

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
            session['mostrar_pendencias'] = True
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
                msg = f'Enviamos o link de redefinição para {usuario.email}.'
                if _wants_json():
                    return jsonify({'ok': True, 'message': msg})
                flash(msg, 'success')
            except Exception as exc:
                print(f'Falha ao enviar e-mail de redefinição: {exc}')
                msg = (
                    'Não foi possível enviar o e-mail agora. Confira a configuração SMTP ou tente de novo.'
                )
                if _wants_json():
                    return jsonify({'ok': False, 'message': msg}), 400
                flash(msg, 'error')
            return redirect(url_for('main.alterar_senha'))

        atual = request.form.get('senha_atual') or ''
        nova = request.form.get('senha') or ''
        confirma = request.form.get('confirma_senha') or ''
        erro = None
        if not check_password_hash(usuario.senha, atual):
            erro = 'A senha atual está incorreta.'
        elif len(nova) < 6:
            erro = 'A nova senha deve ter pelo menos 6 caracteres.'
        elif nova != confirma:
            erro = 'A confirmação não confere com a nova senha.'
        if erro:
            if _wants_json():
                return jsonify({'ok': False, 'message': erro}), 400
            flash(erro, 'error')
            return render_template('alterar_senha.html', usuario=usuario)
        usuario.senha = generate_password_hash(nova)
        usuario.reset_token = None
        usuario.reset_token_expira = None
        db.session.commit()
        if _wants_json():
            return jsonify({'ok': True, 'message': 'Senha alterada com sucesso.'})
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
        'setor': _setor_usuario(usuario),
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

    pendencias = _pendencias_chamados(user)
    mostrar_pendencias = bool(session.pop('mostrar_pendencias', False) and pendencias)
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
        pendencias=pendencias,
        pendencias_js=pendencias,
        mostrar_pendencias=mostrar_pendencias,
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
    usuario.setor = normalizar_setor_chamado(form.get('setor')) or None
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
    chamados_concluidos = Chamado.query.filter(Chamado.status.in_(STATUS_FECHADOS)).count()

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
    """Lista chamados abertos pelo usuário e encaminhamentos ao seu setor."""
    user = Usuario.query.get(session['user_id'])
    user_id = session['user_id']
    setor = _setor_usuario(user)
    conds = [Chamado.tecnico_id == user_id]
    if setor:
        conds.append(and_(Chamado.setor_destino == setor, ~Chamado.status.in_(STATUS_FECHADOS)))
    chamados = (
        Chamado.query.options(joinedload(Chamado.cliente))
        .filter(or_(*conds))
        .order_by(Chamado.data_criacao.desc())
        .all()
    )
    clientes = Cliente.query.order_by(Cliente.nome.asc()).all()
    if setor:
        subtitulo = f'Chamados que você abriu e encaminhamentos para {setor}'
    else:
        subtitulo = 'Chamados que você abriu — todos os status'
    return render_template(
        'chamados.html',
        chamados=chamados,
        clientes=clientes,
        setores=SETORES_CHAMADO,
        subtitulo=subtitulo,
        atender_id=request.args.get('atender', type=int),
    )

@main.route('/novo_chamado', methods=['GET', 'POST'])
@login_required
def novo_chamado():
    """Criar novo chamado"""
    clientes = Cliente.query.order_by(Cliente.nome.asc()).all()
    if request.method == 'POST':
        try:
            raw_cliente = (request.form.get('cliente_id') or '').strip()
            if raw_cliente.isdigit():
                cliente_id = int(raw_cliente)
            else:
                cli = Cliente.query.filter_by(nome=raw_cliente).first()
                cliente_id = cli.id if cli else None
            if not cliente_id:
                raise ValueError('Selecione um cliente válido.')

            numero_chamado = gerar_numero_chamado()
            chamado = Chamado(
                numero_chamado=numero_chamado,
                cliente_id=cliente_id,
                tipo_servico=request.form['tipo_servico'],
                descricao=request.form['descricao'],
                status=request.form.get('status') or 'Pendente',
                prioridade=request.form.get('prioridade') or 'Normal',
                observacoes=request.form.get('observacoes'),
                tecnico_id=session['user_id']
            )
            _vincular_equipamento_chamado(chamado, request.form, cliente_id)

            db.session.add(chamado)
            db.session.commit()

            if _wants_json():
                return jsonify({
                    'ok': True,
                    'success': True,
                    'message': 'Chamado criado com sucesso!',
                    'chamado': chamado.to_dict(),
                })

            flash('Chamado criado com sucesso!', 'success')
            return redirect(url_for('main.listar_chamados'))

        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({
                    'ok': False,
                    'success': False,
                    'message': f'Erro ao criar chamado: {str(e)}',
                }), 400
            flash(f'Erro ao criar chamado: {str(e)}', 'error')

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
            _vincular_equipamento_chamado(chamado, request.form, chamado.cliente_id)
            chamado.tipo_servico = request.form['tipo_servico']
            chamado.descricao = request.form['descricao']
            chamado.status = request.form['status']
            chamado.prioridade = request.form['prioridade']
            chamado.observacoes = request.form['observacoes']

            if status_fechado(request.form['status']) and not chamado.data_conclusao:
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
        if status_fechado(novo_status) and not chamado.data_conclusao:
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


@main.route('/api/chamados/<int:id>/atender', methods=['GET', 'POST'])
@login_required
def atender_chamado(id):
    """Consulta e grava atendimento do técnico (notas, foto, status, encaminhamento)."""
    chamado = Chamado.query.options(
        joinedload(Chamado.cliente),
        joinedload(Chamado.encaminhado_por),
    ).get_or_404(id)
    if request.method == 'GET':
        return jsonify({'ok': True, 'chamado': _chamado_atender_payload(chamado)})

    user = Usuario.query.get(session['user_id'])
    if not user:
        return jsonify({'ok': False, 'message': 'Sessão inválida.'}), 401

    acao = (request.form.get('acao') or 'salvar').strip().lower()
    notas = (request.form.get('atendimento_notas') or '').strip()
    instrucoes = (request.form.get('instrucoes') or '').strip()
    setor = normalizar_setor_chamado(request.form.get('setor_destino'))
    aguardar_peca = request.form.get('aguardar_peca') in ('1', 'on', 'true', 'sim')
    status_form = (request.form.get('status') or '').strip()

    if acao == 'encaminhar':
        if not setor:
            return jsonify({'ok': False, 'message': 'Selecione o setor para encaminhar.'}), 400
        if not instrucoes:
            return jsonify({'ok': False, 'message': 'Informe o que precisa fazer.'}), 400
        chamado.setor_destino = setor
        chamado.encaminhamento_instrucoes = instrucoes
        chamado.encaminhado_por_id = user.id
        chamado.encaminhado_em = datetime.utcnow()
        chamado.status = STATUS_AGUARDAR_PECA if aguardar_peca else STATUS_ENCAMINHADO
    elif acao == 'finalizar':
        if setor:
            chamado.setor_destino = setor
            chamado.encaminhamento_instrucoes = instrucoes or chamado.encaminhamento_instrucoes
            if not chamado.encaminhado_por_id:
                chamado.encaminhado_por_id = user.id
                chamado.encaminhado_em = datetime.utcnow()
        chamado.status = STATUS_ATENDIDO
    else:
        if aguardar_peca:
            chamado.status = STATUS_AGUARDAR_PECA
        elif status_form:
            chamado.status = status_form
        if setor:
            chamado.setor_destino = setor
            chamado.encaminhamento_instrucoes = instrucoes or chamado.encaminhamento_instrucoes
            if not chamado.encaminhado_por_id:
                chamado.encaminhado_por_id = user.id
                chamado.encaminhado_em = datetime.utcnow()

    chamado.atendimento_notas = notas or chamado.atendimento_notas
    if status_fechado(chamado.status) and not chamado.data_conclusao:
        chamado.data_conclusao = datetime.utcnow()

    pendencia_aberta = not status_fechado(chamado.status)
    atendimento = ChamadoAtendimento(
        chamado_id=chamado.id,
        usuario_id=user.id,
        o_que_foi_consertado=notas,
        status=chamado.status,
        setor_destino=chamado.setor_destino,
        instrucoes=instrucoes if acao == 'encaminhar' else instrucoes,
        pendencia_aberta=pendencia_aberta,
    )
    db.session.add(atendimento)
    db.session.flush()

    arquivos_conserto = _arquivos_request('fotos', 'foto')
    arquivos_enc = _arquivos_request('fotos_encaminhar', 'fotos_encaminhamento')
    try:
        _salvar_fotos_chamado(chamado, atendimento, arquivos_conserto, TIPO_FOTO_CONSERTO)
        _salvar_fotos_chamado(chamado, atendimento, arquivos_enc, TIPO_FOTO_ENCAMINHAMENTO)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'message': f'Erro ao gravar atendimento: {exc}'}), 400

    if acao == 'encaminhar':
        msg = 'Encaminhamento registrado.'
    elif acao == 'finalizar':
        msg = 'Chamado finalizado.'
    else:
        msg = 'Atendimento gravado.'
    return jsonify({
        'ok': True,
        'success': True,
        'message': msg,
        'chamado': _chamado_atender_payload(chamado),
    })


def _redir_usuarios_portal():
    flash('Cadastro de usuários e permissões fica em Acessos, na tela principal do portal.', 'info')
    return redirect(url_for('main.inicio'))


@main.route('/usuarios')
@login_required
def listar_usuarios():
    """Usuários do módulo Chamados: centralizado em Acessos na home."""
    return _redir_usuarios_portal()


@main.route('/novo_usuario', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    """Usuários do módulo Chamados: centralizado em Acessos na home."""
    return _redir_usuarios_portal()


@main.route('/usuarios/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    """Usuários do módulo Chamados: centralizado em Acessos na home."""
    return _redir_usuarios_portal()


@main.route('/equipamentos')
@login_required
def listar_equipamentos():
    """Cadastro de equipamentos (patrimônios) vinculados ao cliente."""
    equipamentos = (
        Equipamento.query.options(joinedload(Equipamento.cliente))
        .order_by(Equipamento.patrimonio.asc(), Equipamento.nome_equipamento.asc())
        .all()
    )
    clientes = Cliente.query.order_by(Cliente.nome.asc()).all()
    return render_template(
        'equipamentos.html',
        equipamentos=equipamentos,
        clientes=clientes,
    )


def _dados_equipamento_form(data):
    codigo = (data.get('codigo') or data.get('patrimonio') or '').strip()
    nome = (data.get('nome') or data.get('nome_equipamento') or '').strip()
    setor = (data.get('setor') or data.get('localizacao') or '').strip()
    cliente_raw = data.get('cliente_id')
    cliente_id = int(cliente_raw) if str(cliente_raw or '').isdigit() else None
    if not codigo:
        raise ValueError('Informe o código do equipamento.')
    if not nome:
        raise ValueError('Informe o nome do equipamento.')
    if not cliente_id:
        raise ValueError('Selecione o cliente.')
    if not Cliente.query.get(cliente_id):
        raise ValueError('Cliente inválido.')
    return {
        'patrimonio': codigo,
        'nome_equipamento': nome,
        'setor': setor or None,
        'localizacao': setor or None,
        'data_compra': _parse_data_compra(data.get('data_compra')),
        'cliente_id': cliente_id,
        'ativo': True,
    }


@main.route('/api/equipamentos', methods=['GET', 'POST'])
@login_required
def api_equipamentos():
    if request.method == 'GET':
        cliente_id = request.args.get('cliente_id', type=int)
        q = Equipamento.query.options(joinedload(Equipamento.cliente))
        if cliente_id:
            q = q.filter_by(cliente_id=cliente_id)
        itens = q.order_by(Equipamento.patrimonio.asc()).all()
        return jsonify({'ok': True, 'equipamentos': [e.to_dict() for e in itens]})
    data = request.get_json(silent=True) or request.form
    try:
        campos = _dados_equipamento_form(data)
        equipamento = Equipamento(**campos)
        db.session.add(equipamento)
        db.session.commit()
        return jsonify({
            'ok': True,
            'success': True,
            'message': 'Equipamento cadastrado com sucesso!',
            'equipamento': equipamento.to_dict(),
        })
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc), 'message': str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'ok': False,
            'error': 'Já existe um equipamento com este código.',
            'message': 'Já existe um equipamento com este código.',
        }), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc), 'message': str(exc)}), 400


@main.route('/api/equipamentos/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_equipamento(id):
    equipamento = Equipamento.query.get_or_404(id)
    if request.method == 'GET':
        return jsonify({'ok': True, 'equipamento': equipamento.to_dict()})
    if request.method == 'DELETE':
        try:
            Chamado.query.filter_by(equipamento_id=equipamento.id).update(
                {Chamado.equipamento_id: None}, synchronize_session=False
            )
            db.session.delete(equipamento)
            db.session.commit()
            return jsonify({'ok': True, 'success': True, 'message': 'Equipamento excluído.'})
        except Exception as exc:
            db.session.rollback()
            return jsonify({'ok': False, 'error': str(exc), 'message': str(exc)}), 400
    data = request.get_json(silent=True) or request.form
    try:
        campos = _dados_equipamento_form(data)
        equipamento.patrimonio = campos['patrimonio']
        equipamento.nome_equipamento = campos['nome_equipamento']
        equipamento.setor = campos['setor']
        equipamento.localizacao = campos['localizacao']
        equipamento.data_compra = campos['data_compra']
        equipamento.cliente_id = campos['cliente_id']
        db.session.commit()
        return jsonify({
            'ok': True,
            'success': True,
            'message': 'Equipamento atualizado com sucesso!',
            'equipamento': equipamento.to_dict(),
        })
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc), 'message': str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'ok': False,
            'error': 'Já existe um equipamento com este código.',
            'message': 'Já existe um equipamento com este código.',
        }), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc), 'message': str(exc)}), 400


@main.route('/novo_equipamento', methods=['GET', 'POST'])
@login_required
def novo_equipamento():
    """Criar novo equipamento (popup na listagem; POST legado ainda aceito)."""
    if request.method == 'GET':
        return redirect(url_for('main.listar_equipamentos'))
    clientes = Cliente.query.order_by(Cliente.nome.asc()).all()
    try:
        campos = _dados_equipamento_form(request.form)
        equipamento = Equipamento(**campos)
        db.session.add(equipamento)
        db.session.commit()
        flash('Equipamento criado com sucesso!', 'success')
        return redirect(url_for('main.listar_equipamentos'))
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao criar equipamento: {str(e)}', 'error')
    return render_template('equipamentos.html', equipamentos=Equipamento.query.all(), clientes=clientes)


@main.route('/equipamentos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_equipamento(id):
    """Editar equipamento existente (popup na listagem)."""
    if request.method == 'GET':
        return redirect(url_for('main.listar_equipamentos'))
    equipamento = Equipamento.query.get_or_404(id)
    try:
        campos = _dados_equipamento_form(request.form)
        equipamento.patrimonio = campos['patrimonio']
        equipamento.nome_equipamento = campos['nome_equipamento']
        equipamento.setor = campos['setor']
        equipamento.localizacao = campos['localizacao']
        equipamento.data_compra = campos['data_compra']
        equipamento.cliente_id = campos['cliente_id']
        db.session.commit()
        flash('Equipamento atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_equipamentos'))
    except Exception as e:
        flash(f'Erro ao atualizar equipamento: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('main.listar_equipamentos'))


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


def _filtro_periodo_chamados():
    """Filtro de data_criacao: presets 30/90/ano ou intervalo custom. Default: todos."""
    periodo = (request.args.get('periodo') or 'todos').strip().lower()
    if periodo not in ('todos', '30', '90', 'ano', 'custom'):
        periodo = 'todos'
    hoje = date.today()
    data_de = _parse_data_compra(request.args.get('data_de'))
    data_ate = _parse_data_compra(request.args.get('data_ate'))
    if periodo == '30':
        data_de, data_ate = hoje - timedelta(days=29), hoje
    elif periodo == '90':
        data_de, data_ate = hoje - timedelta(days=89), hoje
    elif periodo == 'ano':
        data_de, data_ate = date(hoje.year, 1, 1), hoje
    elif periodo == 'todos':
        data_de, data_ate = None, None
    else:
        periodo = 'custom'
        if data_de and data_ate and data_de > data_ate:
            data_de, data_ate = data_ate, data_de
    filtros = []
    if data_de:
        filtros.append(Chamado.data_criacao >= datetime.combine(data_de, datetime.min.time()))
    if data_ate:
        filtros.append(
            Chamado.data_criacao < datetime.combine(data_ate + timedelta(days=1), datetime.min.time())
        )
    return periodo, data_de, data_ate, filtros


@main.route('/relatorios')
#@login_required
def relatorios():
    """Página de relatórios gerenciais"""
    periodo, data_de, data_ate, filtros = _filtro_periodo_chamados()

    total_chamados = Chamado.query.filter(*filtros).count()
    clientes_distintos = (
        db.session.query(func.count(func.distinct(Chamado.cliente_id))).filter(*filtros).scalar() or 0
    )

    status_rows = (
        db.session.query(Chamado.status, func.count(Chamado.id))
        .filter(*filtros)
        .group_by(Chamado.status)
        .all()
    )
    status_map = {(s or '').strip(): n for s, n in status_rows}

    top_clientes_rows = (
        db.session.query(Cliente.nome, func.count(Chamado.id).label('total'))
        .join(Chamado)
        .filter(*filtros)
        .group_by(Cliente.id, Cliente.nome)
        .order_by(func.count(Chamado.id).desc())
        .limit(10)
        .all()
    )
    top_clientes = []
    for nome, total in top_clientes_rows:
        pct = round((total * 100.0 / total_chamados), 1) if total_chamados else 0
        top_clientes.append({'nome': nome or '—', 'total': int(total), 'pct': pct})

    top = top_clientes[0] if top_clientes else None
    stats = {
        'total': total_chamados,
        'clientes': int(clientes_distintos),
        'top_cliente': top['nome'] if top else '—',
        'top_cliente_qtd': top['total'] if top else 0,
        'pendentes': int(status_map.get('Pendente', 0)),
        'em_andamento': int(status_map.get('Em Andamento', 0)),
        'concluidos': int(sum(status_map.get(s, 0) for s in STATUS_FECHADOS)),
    }

    top_eq_rows = (
        db.session.query(Chamado.equipamento, func.count(Chamado.id).label('total'))
        .filter(Chamado.equipamento.isnot(None), Chamado.equipamento != '', *filtros)
        .group_by(Chamado.equipamento)
        .order_by(func.count(Chamado.id).desc())
        .limit(10)
        .all()
    )
    top_equipamentos = []
    for nome, total in top_eq_rows:
        pct = round((total * 100.0 / total_chamados), 1) if total_chamados else 0
        top_equipamentos.append({'nome': nome, 'total': int(total), 'pct': pct})

    equipamentos_problemas = {}
    for eq in top_equipamentos:
        tipos = (
            db.session.query(Chamado.tipo_servico, func.count(Chamado.id))
            .filter(Chamado.equipamento == eq['nome'], *filtros)
            .group_by(Chamado.tipo_servico)
            .order_by(func.count(Chamado.id).desc())
            .all()
        )
        equipamentos_problemas[eq['nome']] = [
            {'tipo': t or '—', 'total': int(n)} for t, n in tipos
        ]

    return render_template(
        'relatorios.html',
        stats=stats,
        top_clientes=top_clientes,
        top_equipamentos=top_equipamentos,
        equipamentos_problemas=equipamentos_problemas,
        filtros={
            'periodo': periodo,
            'data_de': data_de.isoformat() if data_de else '',
            'data_ate': data_ate.isoformat() if data_ate else '',
        },
    )

@main.route('/api/equipamentos_por_cliente/<cliente_ref>', methods=['GET'])
@login_required
def equipamentos_por_cliente(cliente_ref):
    """Patrimônios vinculados ao cliente selecionado no chamado."""
    q = Equipamento.query
    if str(cliente_ref).isdigit():
        q = q.filter_by(cliente_id=int(cliente_ref))
    else:
        cli = Cliente.query.filter_by(nome=cliente_ref).first()
        if cli:
            q = q.filter_by(cliente_id=cli.id)
        else:
            q = q.filter(or_(Equipamento.localizacao == cliente_ref, Equipamento.setor == cliente_ref))
    equipamentos = q.order_by(Equipamento.patrimonio.asc(), Equipamento.nome_equipamento.asc()).all()
    return jsonify([
        {
            'id': e.id,
            'patrimonio': e.patrimonio or '',
            'nome_equipamento': e.nome_equipamento,
            'setor': e.setor or e.localizacao or '',
        }
        for e in equipamentos
    ])
