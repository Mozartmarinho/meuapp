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
    RecursoGrupo,
    ChamadoSetor,
    ChamadoTecnico,
    ConfiguracaoEmail,
    ChamadoAtendimento,
    ChamadoEncaminhamento,
    ChamadoFoto,
    ChamadoConhecimento,
    MesaServico,
    SlaPrioridade,
    Contrato,
    ChamadoMensagem,
    ChamadoAutomacao,
    ChamadoRamal,
    ChamadoCamera,
    ChamadoPortao,
    ChamadoEstoque,
    ConhecimentoPasta,
    TIPO_FOTO_CONSERTO,
    TIPO_FOTO_ENCAMINHAMENTO,
    TIPO_HOP_ENCAMINHAR,
    TIPO_HOP_DEVOLVER,
    TIPO_HOP_PECA,
    SETOR_COMPRAS,
    STATUS_AGUARDAR_PECA,
    STATUS_ENCAMINHADO,
    STATUS_DEVOLVIDO,
    STATUS_ATENDIDO,
    STATUS_FECHADOS,
    TIPO_SETOR_CHAMADOS,
    TIPO_SETOR_NUTRICAO,
    TIPOS_CONTRATO,
    FUNCOES_TECNICO,
    FUNCOES_TECNICO_KEYS,
    CANAIS_MENSAGEM,
    CANAIS_ENVIO_LIVE,
    PASTA_CONHECIMENTO_PADRAO,
    status_fechado,
    normalizar_setor_chamado,
    normalizar_setor,
    listar_setores,
    adicionar_setor,
    sla_do_chamado,
    _bucket_sla,
    mesas_ativas,
    mesa_padrao,
    resolver_mesa_id,
    aplicar_automacoes,
    parse_valor_faturamento,
    normalizar_prioridade,
    contrato_vigente,
    sla_horas_tipo_contrato,
    TICKET_PARADO_HORAS,
    TIPOS_RECURSO,
    grupo_recurso_padrao,
)
from permissions_sistemas import SISTEMAS, aplicar_permissoes_formulario, conceder_acesso_total
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_, and_
from sqlalchemy.exc import IntegrityError
from datetime import date, datetime, timedelta
from collections import Counter
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
    'main.ver_chamado': 'chamados',
    'main.novo_chamado': 'novo_chamado',
    'main.editar_chamado': 'chamados',
    'main.listar_clientes': 'clientes',
    'main.novo_cliente': 'clientes',
    'main.editar_cliente': 'clientes',
    'main.tecnicos': 'tecnicos',
    'main.adicionar_chamado_setor': 'tecnicos',
    'main.toggle_chamado_setor': 'tecnicos',
    'main.adicionar_chamado_tecnico': 'tecnicos',
    'main.editar_chamado_tecnico': 'tecnicos',
    'main.excluir_chamado_tecnico': 'tecnicos',
    'main.listar_equipamentos': 'equipamentos',
    'main.novo_equipamento': 'equipamentos',
    'main.editar_equipamento': 'equipamentos',
    'main.api_equipamentos': 'equipamentos',
    'main.api_equipamento': 'equipamentos',
    'main.adicionar_setor_equipamento': 'equipamentos',
    'main.toggle_setor_equipamento': 'equipamentos',
    'main.cameras': 'cameras',
    'main.adicionar_camera': 'cameras',
    'main.editar_camera': 'cameras',
    'main.excluir_camera': 'cameras',
    'main.adicionar_setor_camera': 'cameras',
    'main.toggle_setor_camera': 'cameras',
    'main.portoes': 'portoes',
    'main.adicionar_portao': 'portoes',
    'main.editar_portao': 'portoes',
    'main.excluir_portao': 'portoes',
    'main.adicionar_setor_portao': 'portoes',
    'main.toggle_setor_portao': 'portoes',
    'main.estoque': 'estoque',
    'main.adicionar_estoque': 'estoque',
    'main.editar_estoque': 'estoque',
    'main.excluir_estoque': 'estoque',
    'main.recursos': 'recursos',
    'main.ver_recurso': 'recursos',
    'main.salvar_grupo_recurso': 'recursos',
    'main.api_recursos_por_cliente': 'novo_chamado',
    'main.relatorios': 'relatorios',
    'main.relatorio_gestao': 'relatorios',
    'main.relatorio_item': 'relatorios',
    'main.contratos': 'contratos',
    'main.salvar_contrato': 'contratos',
    'main.excluir_contrato': 'contratos',
    'main.agenda': 'agenda',
    'main.conhecimentos': 'conhecimentos',
    'main.novo_conhecimento': 'conhecimentos',
    'main.ver_conhecimento': 'conhecimentos',
    'main.nova_pasta_conhecimento': 'conhecimentos',
    'main.automacoes': 'automacoes',
    'main.auditoria': 'auditoria',
    'main.mensagem_chamado': 'chamados',
    'main.atualizar_mesa_chamado': 'chamados',
}

ESTAGIOS_TICKET = (
    ('pendente', 'Pendente', ('Pendente',)),
    ('aguardando', 'Aguardando Cliente', (STATUS_AGUARDAR_PECA,)),
    ('atendimento', 'Em Atendimento', ('Em Andamento',)),
    ('desenvolvimento', 'Em Desenvolvimento', (STATUS_ENCAMINHADO, STATUS_DEVOLVIDO)),
)


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
    if menu_key in ('recursos', 'equipamentos') and (
        user.tem_menu('chamados', 'recursos') or user.tem_menu('chamados', 'equipamentos')
    ):
        return None
    if request.endpoint == 'main.dashboard' and any(
        user.tem_menu('chamados', k) for k in ('chats', 'recursos')
    ):
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


def _clientes_para_chamados():
    """Clientes habilitados para Gestão de Chamados."""
    return (
        Cliente.query.filter(
            db.or_(Cliente.habilitado_chamados.is_(True), Cliente.habilitado_chamados.is_(None))
        )
        .order_by(Cliente.nome.asc())
        .all()
    )


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


def _primeiro_nome(usuario):
    nome = (getattr(usuario, 'nome', None) or '').strip()
    return nome.split()[0] if nome else 'olá'


def _filtro_chamados_usuario(user):
    conds = [Chamado.tecnico_id == user.id]
    setor = _setor_usuario(user)
    if setor:
        conds.append(and_(Chamado.setor_destino == setor, ~Chamado.status.in_(STATUS_FECHADOS)))
    return or_(*conds)


def _estagio_do_status(status):
    for key, label, statuses in ESTAGIOS_TICKET:
        if status in statuses:
            return key, label
    if status_fechado(status):
        return 'fechado', 'Fechado'
    return 'pendente', 'Pendente'


def _titulo_chamado(chamado):
    desc = (chamado.descricao or '').strip().replace('\n', ' ')
    if desc:
        return desc[:80] + ('…' if len(desc) > 80 else '')
    return chamado.tipo_servico or chamado.numero_chamado


def _url_detalhe_chamado(chamado_id):
    try:
        return url_for('main.ver_chamado', id=chamado_id, _external=True)
    except Exception:
        host = request.host or '127.0.0.1'
        scheme = 'https' if request.is_secure else 'http'
        return f'{scheme}://{host}/chamados/{chamado_id}'


def _fmt_dt(valor):
    if not valor:
        return '—'
    return valor.strftime('%d/%m/%Y %H:%M')


def _contar_sla_widgets(chamados_abertos):
    hoje_d = date.today()
    agora = datetime.utcnow()
    venc_at = {'hoje': 0, 'amanha': 0, 'depois': 0}
    venc_sol = {'hoje': 0, 'amanha': 0, 'depois': 0}
    vencidos = 0
    for c in chamados_abertos:
        info = sla_do_chamado(c)
        if not info:
            continue
        b_at = _bucket_sla(info['venc_atendimento'], hoje_d, agora, False)
        b_sol = _bucket_sla(info['venc_solucao'], hoje_d, agora, False)
        if b_at == 'vencido' or b_sol == 'vencido':
            vencidos += 1
        if b_at in venc_at:
            venc_at[b_at] += 1
        if b_sol in venc_sol:
            venc_sol[b_sol] += 1
    return venc_at, venc_sol, vencidos


def _avisar_abertura_ticket(chamado, opener):
    """E-mail VISUALIZAÇÃO DE TICKET só para quem abriu. Não derruba a criação."""
    dest = (getattr(opener, 'email', None) or '').strip()
    if not dest:
        flash('Ticket criado. Sem e-mail no seu cadastro; visualização não enviada.', 'info')
        return
    try:
        from email_service import smtp_configurado, enviar_visualizacao_ticket
        if not smtp_configurado():
            print('SMTP não configurado; e-mail de visualização de ticket não enviado.')
            return
        enviar_visualizacao_ticket(chamado, opener, _url_detalhe_chamado(chamado.id))
    except Exception as exc:
        print(f'Falha ao enviar visualização de ticket: {exc}')


def _ultima_movimentacao(chamado):
    stamps = [chamado.data_criacao, chamado.encaminhado_em]
    try:
        last_at = (
            db.session.query(func.max(ChamadoAtendimento.data_criacao))
            .filter(ChamadoAtendimento.chamado_id == chamado.id)
            .scalar()
        )
        last_msg = (
            db.session.query(func.max(ChamadoMensagem.data_criacao))
            .filter(ChamadoMensagem.chamado_id == chamado.id)
            .scalar()
        )
        stamps.extend([last_at, last_msg])
    except Exception:
        pass
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else chamado.data_criacao


def _alertas_sla_e_parada(chamados_abertos):
    """Alertas de SLA próximo/vencido e ticket parado — alimentam o sino."""
    agora = datetime.utcnow()
    items = []
    for c in chamados_abertos:
        info = sla_do_chamado(c)
        url = url_for('main.ver_chamado', id=c.id)
        cliente = c.cliente.nome if c.cliente else '—'
        if info:
            if info.get('atendimento_vencido') or info.get('solucao_vencida'):
                qual = 'solução' if info.get('solucao_vencida') else 'atendimento'
                items.append({
                    'id': c.id,
                    'numero_chamado': c.numero_chamado,
                    'cliente': cliente,
                    'tipo': f'SLA {qual} vencido',
                    'setor_destino': c.mesa.nome if c.mesa else (c.setor_destino or ''),
                    'url_atender': url,
                })
            elif info.get('atendimento_proximo') or info.get('solucao_proxima'):
                qual = 'solução' if info.get('solucao_proxima') else 'atendimento'
                items.append({
                    'id': c.id,
                    'numero_chamado': c.numero_chamado,
                    'cliente': cliente,
                    'tipo': f'SLA {qual} vence em breve',
                    'setor_destino': c.mesa.nome if c.mesa else (c.setor_destino or ''),
                    'url_atender': url,
                })
        ult = _ultima_movimentacao(c)
        if ult and (agora - ult) >= timedelta(hours=TICKET_PARADO_HORAS):
            items.append({
                'id': c.id,
                'numero_chamado': c.numero_chamado,
                'cliente': cliente,
                'tipo': f'Sem atualização há {TICKET_PARADO_HORAS}h',
                'setor_destino': c.mesa.nome if c.mesa else (c.setor_destino or ''),
                'url_atender': url,
            })
    return items


def _status_inicial_novo():
    allowed = {'Pendente', 'Em Andamento', STATUS_AGUARDAR_PECA, STATUS_ENCAMINHADO, STATUS_DEVOLVIDO}
    status = (request.args.get('status') or 'Pendente').strip()
    return status if status in allowed else 'Pendente'


RELATORIOS_CATALOGO = (
    {
        'key': 'atendentes',
        'label': 'Atendentes',
        'icon': 'fa-user-clock',
        'items': [
            {'slug': 'atraso-apontamentos', 'label': 'Atraso de apontamentos'},
            {'slug': 'carga-trabalho', 'label': 'Carga de trabalho'},
            {'slug': 'chat-detalhado', 'label': 'Chat detalhado'},
            {'slug': 'deslocamentos', 'label': 'Deslocamentos'},
            {'slug': 'executivo-atendentes', 'label': 'Executivo de atendentes'},
            {'slug': 'extrato-apontamentos', 'label': 'Extrato de apontamentos'},
            {'slug': 'grafico-apontamentos', 'label': 'Gráfico de apontamentos'},
            {'slug': 'picos-atendimento', 'label': 'Picos de atendimento'},
        ],
    },
    {
        'key': 'faturamento',
        'label': 'Faturamento',
        'icon': 'fa-file-invoice-dollar',
        'items': [
            {'slug': 'erros-faturamento', 'label': 'Erros de faturamento'},
            {'slug': 'extrato-consumo-cliente', 'label': 'Extrato de consumo cliente'},
            {'slug': 'faturamentos-pendentes', 'label': 'Faturamentos pendentes'},
            {'slug': 'grafico-consumo-contrato', 'label': 'Gráfico consumo contrato'},
            {'slug': 'historico-faturamentos', 'label': 'Histórico de faturamentos'},
            {'slug': 'reajuste-contratos', 'label': 'Reajuste de contratos'},
            {'slug': 'valores-extras', 'label': 'Valores extras'},
        ],
    },
    {
        'key': 'administrativo',
        'label': 'Administrativo',
        'icon': 'fa-briefcase',
        'items': [
            {'slug': 'avaliacoes-atendimento', 'label': 'Avaliações de atendimento'},
            {'slug': 'avaliacoes-conhecimentos', 'label': 'Avaliações de conhecimentos'},
            {'slug': 'catalogo-servico', 'label': 'Catálogo de serviço'},
            {'slug': 'eficiencia-atendimento', 'label': 'Eficiência de atendimento'},
            {'slug': 'engajamento-clientes', 'label': 'Engajamento clientes'},
            {'slug': 'executivo', 'label': 'Executivo'},
            {'slug': 'exportar', 'label': 'Exportar'},
            {'slug': 'gestao-indicadores', 'label': 'Gestão e indicadores'},
        ],
    },
    {
        'key': 'recurso',
        'label': 'Recurso',
        'icon': 'fa-headset',
        'items': [
            {'slug': 'gatilhos-disparados', 'label': 'Gatilhos disparados'},
            {'slug': 'historico-acoes', 'label': 'Histórico de ações'},
            {'slug': 'historico-gatilhos', 'label': 'Histórico de gatilhos'},
            {'slug': 'informacoes-recursos', 'label': 'Informações dos recursos'},
            {'slug': 'softwares-licencas', 'label': 'Softwares e licenças'},
        ],
    },
    {
        'key': 'excluidos',
        'label': 'Excluídos e bloqueados',
        'icon': 'fa-ban',
        'items': [
            {'slug': 'contatos-bloqueados', 'label': 'Contatos bloqueados'},
            {'slug': 'pre-tickets-excluidos', 'label': 'Pré-tickets excluídos'},
            {'slug': 'recursos-excluidos', 'label': 'Recursos excluídos'},
            {'slug': 'senhas-excluidas', 'label': 'Senhas excluídas'},
        ],
    },
)

RELATORIOS_LIVE = {
    'gestao-indicadores',
    'carga-trabalho',
    'executivo-atendentes',
    'executivo',
}


def _query_chamados_usuario(user):
    return (
        Chamado.query.options(joinedload(Chamado.cliente), joinedload(Chamado.mesa), joinedload(Chamado.contrato))
        .filter(_filtro_chamados_usuario(user))
        .order_by(Chamado.data_criacao.desc())
    )


def _grupos_tickets(chamados):
    grupos = []
    for key, label, statuses in ESTAGIOS_TICKET:
        grupos.append({
            'key': key,
            'label': label,
            'tickets': [c for c in chamados if c.status in statuses],
        })
    fechados = [c for c in chamados if status_fechado(c.status)]
    return grupos, fechados


def _eh_gestor(usuario):
    return bool(usuario and (usuario.is_master or usuario.tipo == 'admin'))


def _ultimo_hop(chamado):
    return (
        ChamadoEncaminhamento.query
        .filter_by(chamado_id=chamado.id)
        .order_by(ChamadoEncaminhamento.id.desc())
        .first()
    )


def _setor_origem_atual(chamado):
    origem = normalizar_setor_chamado(getattr(chamado, 'setor_origem', None))
    if origem:
        return origem
    hop = _ultimo_hop(chamado)
    if hop:
        de = normalizar_setor_chamado(hop.de_setor)
        if de:
            return de
    encaminhado_por = chamado.encaminhado_por
    if encaminhado_por:
        s = _setor_usuario(encaminhado_por)
        if s:
            return s
    if getattr(chamado, 'tecnico_id', None):
        tec = Usuario.query.get(chamado.tecnico_id)
        s = _setor_usuario(tec)
        if s:
            return s
    return ''


def _pode_devolver(chamado, usuario):
    """Técnico do setor destino de um encaminhamento aberto (não de uma devolução)."""
    dest = normalizar_setor_chamado(chamado.setor_destino)
    if not dest or not usuario:
        return False
    user_setor = _setor_usuario(usuario)
    if not (_eh_gestor(usuario) or dest == user_setor):
        return False
    hop = _ultimo_hop(chamado)
    if hop:
        if (hop.tipo or '') == TIPO_HOP_DEVOLVER:
            return False
        para = normalizar_setor_chamado(hop.para_setor)
        return bool(not para or para == dest)
    origem = _setor_origem_atual(chamado)
    if origem and origem != dest:
        return True
    if chamado.encaminhado_por_id and chamado.encaminhado_por_id != usuario.id:
        return True
    return False


def _setor_atuacao(usuario, chamado):
    return _setor_usuario(usuario) or normalizar_setor_chamado(chamado.setor_destino) or ''


def _normalizar_email(email):
    """E-mail normalizado para vínculo técnico ↔ acesso (trim + lower)."""
    return (email or '').strip().lower() or None


def _usuario_por_email(email):
    """Busca Usuario (Acesso) pelo e-mail normalizado."""
    email = _normalizar_email(email)
    if not email:
        return None
    return Usuario.query.filter(func.lower(Usuario.email) == email).first()


def _vincular_tecnicos_ao_usuario(usuario):
    """
    Liga ChamadoTecnico ↔ Usuario pelo e-mail.
    - Todos os técnicos com o mesmo e-mail recebem usuario_id.
    - Técnicos que apontavam para este usuário e mudaram de e-mail são desvinculados.
    """
    if not usuario or not getattr(usuario, 'id', None):
        return
    email = _normalizar_email(usuario.email)
    for t in ChamadoTecnico.query.filter(ChamadoTecnico.usuario_id == usuario.id).all():
        if _normalizar_email(t.email) != email:
            t.usuario_id = None
    if not email:
        return
    for t in ChamadoTecnico.query.filter(func.lower(ChamadoTecnico.email) == email).all():
        t.usuario_id = usuario.id


def _setores_tecnico_usuario(usuario):
    """IDs de chamado_setores onde o usuário está cadastrado como técnico."""
    try:
        email = _normalizar_email(getattr(usuario, 'email', None))
        conds = [ChamadoTecnico.usuario_id == usuario.id]
        if email:
            conds.append(func.lower(ChamadoTecnico.email) == email)
        tec = ChamadoTecnico.query.filter(
            ChamadoTecnico.ativo == True,  # noqa: E712
            or_(*conds),
        ).all()
        return {t.setor_id for t in tec if t.setor_id}
    except Exception:
        return set()


def _pendencias_chamados(usuario):
    """Pendências do login: encaminhamentos ao setor do usuário e chamados aguardando peça."""
    if not usuario:
        return []
    setor = _setor_usuario(usuario)
    gestor = _eh_gestor(usuario)
    meus_setores_tecnicos = _setores_tecnico_usuario(usuario)
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
        ticket_do_meu_setor = bool(
            meus_setores_tecnicos and chamado.setor_tecnico_id in meus_setores_tecnicos
        )
        if not encaminhado_para_mim and not aguardar_peca and not ticket_do_meu_setor:
            continue
        if chamado.id in seen:
            continue
        seen.add(chamado.id)
        origem = _setor_origem_atual(chamado)
        if chamado.status == STATUS_DEVOLVIDO:
            tipo = f'{origem or "Setor"} devolveu {chamado.numero_chamado}'
        elif encaminhado_para_mim and aguardar_peca:
            tipo = 'Aguardar peça / Encaminhado'
        elif encaminhado_para_mim:
            tipo = 'Encaminhado'
        elif ticket_do_meu_setor:
            nome_setor = chamado.setor_tecnico.nome if chamado.setor_tecnico else 'Setor'
            tipo = f'Ticket aberto para {nome_setor}'
        else:
            tipo = STATUS_AGUARDAR_PECA
        encaminhado_por = chamado.encaminhado_por
        fotos_tipo = (
            TIPO_FOTO_CONSERTO if chamado.status == STATUS_DEVOLVIDO else TIPO_FOTO_ENCAMINHAMENTO
        )
        items.append({
            'id': chamado.id,
            'numero_chamado': chamado.numero_chamado,
            'cliente': chamado.cliente.nome if chamado.cliente else 'N/A',
            'status': chamado.status,
            'tipo': tipo,
            'setor_destino': dest or '',
            'setor_origem': origem or '',
            'instrucoes': chamado.encaminhamento_instrucoes or '',
            'notas': chamado.atendimento_notas or '',
            'fotos': _fotos_chamado_payload(chamado, fotos_tipo),
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


def _chamado_atender_payload(chamado, usuario=None):
    todas = _fotos_chamado_payload(chamado)
    origem = _setor_origem_atual(chamado)
    encaminhado_por = chamado.encaminhado_por
    pode_devolver = _pode_devolver(chamado, usuario) if usuario else False
    return {
        'id': chamado.id,
        'numero_chamado': chamado.numero_chamado,
        'cliente': chamado.cliente.nome if chamado.cliente else 'N/A',
        'status': chamado.status,
        'prioridade': chamado.prioridade,
        'descricao': chamado.descricao or '',
        'atendimento_notas': chamado.atendimento_notas or '',
        'setor_destino': chamado.setor_destino or '',
        'setor_origem': origem or '',
        'encaminhamento_instrucoes': chamado.encaminhamento_instrucoes or '',
        'encaminhado_por': encaminhado_por.nome if encaminhado_por else '',
        'encaminhado_por_setor': _setor_usuario(encaminhado_por) if encaminhado_por else '',
        'encaminhado_em': (
            chamado.encaminhado_em.strftime('%d/%m/%Y %H:%M') if chamado.encaminhado_em else ''
        ),
        'pode_devolver': pode_devolver,
        'setor_devolver': origem if pode_devolver else '',
        'usuario_setor': _setor_usuario(usuario) if usuario else '',
        'fotos': [f for f in todas if f['tipo'] != TIPO_FOTO_ENCAMINHAMENTO],
        'fotos_encaminhamento': [f for f in todas if f['tipo'] == TIPO_FOTO_ENCAMINHAMENTO],
        'setores': listar_setores(TIPO_SETOR_CHAMADOS),
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
    cliente_todos = bool(getattr(usuario, 'cliente_todos', False))
    if cliente_todos:
        cliente_nome = 'Todos os clientes'
    elif getattr(usuario, 'cliente', None):
        cliente_nome = usuario.cliente.nome
    else:
        cliente_nome = None
    return {
        'id': usuario.id,
        'nome': usuario.nome,
        'email': usuario.email,
        'ativo': bool(usuario.ativo),
        'is_master': bool(usuario.is_master),
        'setor': _setor_usuario(usuario),
        'setor_nutricao': normalizar_setor(
            TIPO_SETOR_NUTRICAO, getattr(usuario, 'setor_nutricao', None)
        ),
        'cliente_id': getattr(usuario, 'cliente_id', None),
        'cliente_todos': cliente_todos,
        'cliente_nome': cliente_nome,
        'sistemas': {chave: usuario.tem_sistema(chave) for chave in SISTEMAS},
        'permissoes': {sistema: usuario.menus_liberados(sistema) for sistema in SISTEMAS},
    }


def _json_text(value):
    """Coerce optional model fields to a JSON-safe string (never Jinja Undefined)."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    return str(value)


def _cliente_payload(cliente):
    """Payload JSON para modal de clientes no portal (None em chamados = habilitado)."""
    hab_chamados = getattr(cliente, 'habilitado_chamados', None)
    return {
        'id': int(getattr(cliente, 'id', 0) or 0),
        'nome': _json_text(getattr(cliente, 'nome', None)),
        'endereco': _json_text(getattr(cliente, 'endereco', None)),
        'telefone': _json_text(getattr(cliente, 'telefone', None)),
        'email': _json_text(getattr(cliente, 'email', None)),
        'responsavel': _json_text(getattr(cliente, 'responsavel', None)),
        'telefone_responsavel': _json_text(getattr(cliente, 'telefone_responsavel', None)),
        'habilitado_chamados': hab_chamados is None or bool(hab_chamados),
        'habilitado_nutricao': bool(getattr(cliente, 'habilitado_nutricao', False)),
    }


def _pode_gerenciar_clientes(user):
    return bool(
        user
        and (
            user.pode_gerenciar_acessos()
            or user.tem_menu('chamados', 'clientes')
            or user.is_master
            or user.tipo == 'admin'
        )
    )


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
    clientes_portal = []
    clientes_js = []
    smtp_cfg = {'servidor': '', 'porta': 587, 'usar_tls': True, 'usuario': '', 'remetente': ''}
    senha_salva = False
    smtp_ok = False
    if user and user.pode_gerenciar_acessos():
        from email_service import obter_config_smtp, smtp_configurado
        acessos = Usuario.query.order_by(Usuario.data_criacao.desc()).all()
        acessos_js = [_acesso_payload(a) for a in acessos]
        clientes_portal = Cliente.query.order_by(Cliente.data_criacao.desc()).all()
        clientes_js = [_cliente_payload(c) for c in clientes_portal]
        raw_cfg = obter_config_smtp()
        smtp_cfg = {k: v for k, v in raw_cfg.items() if k != 'senha'}
        row = ConfiguracaoEmail.query.get(1)
        senha_salva = bool(row and row.senha) or bool(raw_cfg.get('senha'))
        smtp_ok = smtp_configurado()

    pendencias = _pendencias_chamados(user)
    mostrar_pendencias = bool(session.pop('mostrar_pendencias', False) and pendencias)
    clientes_acesso = Cliente.query.order_by(Cliente.nome.asc()).all()
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
        setores_chamados=listar_setores(TIPO_SETOR_CHAMADOS),
        setores_nutricao=listar_setores(TIPO_SETOR_NUTRICAO),
        clientes_acesso=clientes_acesso,
        clientes_portal=clientes_portal,
        clientes_js=clientes_js,
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
    email = _normalizar_email(form.get('email'))
    nome = (form.get('nome') or '').strip()
    senha = form.get('senha') or ''
    if not nome or not email:
        raise ValueError('Nome e e-mail são obrigatórios.')
    outro = Usuario.query.filter(func.lower(Usuario.email) == email, Usuario.id != usuario.id).first()
    if outro:
        raise ValueError('Já existe um acesso com este e-mail.')
    usuario.nome = nome
    usuario.email = email
    usuario.setor = normalizar_setor_chamado(form.get('setor')) or None
    usuario.setor_nutricao = normalizar_setor(TIPO_SETOR_NUTRICAO, form.get('setor_nutricao')) or None
    usuario.telefone = (form.get('telefone') or '').strip() or None
    raw_cli = (form.get('cliente_id') or '').strip().lower()
    if raw_cli in ('todos', '__all__'):
        usuario.cliente_id = None
        usuario.cliente_todos = True
    elif raw_cli.isdigit():
        cli = Cliente.query.get(int(raw_cli))
        usuario.cliente_id = cli.id if cli else None
        usuario.cliente_todos = False
    else:
        usuario.cliente_id = None
        usuario.cliente_todos = False
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
    _vincular_tecnicos_ao_usuario(usuario)
    db.session.commit()


@main.route('/acessos/setores', methods=['POST'])
@login_required
def criar_setor_funcao():
    """(+) no cadastro de Acessos: inclui função/setor no catálogo do dropdown."""
    user = Usuario.query.get(session['user_id'])
    if not user or not user.pode_gerenciar_acessos():
        if _wants_json():
            return jsonify({'ok': False, 'message': 'Sem permissão para gerenciar acessos.'}), 403
        flash('Você não tem permissão para gerenciar acessos.', 'error')
        return redirect(url_for('main.inicio'))
    data = request.get_json(silent=True) or {}
    tipo = (request.form.get('tipo') or data.get('tipo') or '').strip()
    nome = request.form.get('nome') if request.form.get('nome') is not None else data.get('nome')
    try:
        salvo = adicionar_setor(tipo, nome)
        setores = listar_setores(tipo)
        if _wants_json():
            return jsonify({
                'ok': True,
                'message': 'Função/setor adicionado.',
                'nome': salvo,
                'tipo': tipo,
                'setores': setores,
            })
        flash('Função/setor adicionado.', 'success')
        return redirect(url_for('main.inicio'))
    except ValueError as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({'ok': False, 'message': str(e)}), 400
        flash(str(e), 'error')
        return redirect(url_for('main.inicio'))
    except IntegrityError:
        db.session.rollback()
        if _wants_json():
            return jsonify({'ok': False, 'message': 'Essa função ou setor já existe.'}), 400
        flash('Essa função ou setor já existe.', 'error')
        return redirect(url_for('main.inicio'))
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({'ok': False, 'message': str(e)}), 400
        flash(str(e), 'error')
        return redirect(url_for('main.inicio'))


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
        setores_chamados=listar_setores(TIPO_SETOR_CHAMADOS),
        setores_nutricao=listar_setores(TIPO_SETOR_NUTRICAO),
        clientes=Cliente.query.order_by(Cliente.nome.asc()).all(),
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
        setores_chamados=listar_setores(TIPO_SETOR_CHAMADOS),
        setores_nutricao=listar_setores(TIPO_SETOR_NUTRICAO),
        clientes=Cliente.query.order_by(Cliente.nome.asc()).all(),
    )

@main.route('/dashboard')
@login_required
def dashboard():
    """Dashboard do sistema de gestão de chamados (widgets com dados reais)."""
    user = Usuario.query.get(session['user_id'])
    visiveis = _query_chamados_usuario(user).all()
    mesas = mesas_ativas()
    mesa_filtro = request.args.get('mesa', type=int)
    if mesa_filtro:
        visiveis = [c for c in visiveis if c.mesa_id == mesa_filtro]
    meus = [c for c in visiveis if c.tecnico_id == user.id]
    abertos = [c for c in visiveis if not status_fechado(c.status)]
    st_nao = [c for c in visiveis if c.status == 'Pendente']
    st_and = [c for c in visiveis if c.status in ('Em Andamento', STATUS_ENCAMINHADO, STATUS_DEVOLVIDO, STATUS_AGUARDAR_PECA)]
    st_pause = [c for c in visiveis if c.status == STATUS_AGUARDAR_PECA]
    venc_at, venc_sol, vencidos = _contar_sla_widgets(abertos)
    ids = [c.id for c in visiveis]
    have_at = set()
    if ids:
        have_at = {
            r[0] for r in db.session.query(ChamadoAtendimento.chamado_id)
            .filter(ChamadoAtendimento.chamado_id.in_(ids))
            .distinct()
        }
    sem_resp = [c for c in abertos if c.id not in have_at]
    pie_src = Counter()
    for c in visiveis:
        if c.status in ('Em Andamento', STATUS_ENCAMINHADO, STATUS_DEVOLVIDO, STATUS_AGUARDAR_PECA):
            pie_src[c.setor_destino or user.nome or 'Eu'] += 1
    pie_total = sum(pie_src.values())
    colors = ['#1ABC9C', '#3498db', '#9b59b6', '#e67e22', '#e74c3c', '#95a5a6']
    circ = 339.3
    pie = []
    acc = 0.0
    if pie_total:
        for i, (label, n) in enumerate(pie_src.most_common()):
            frac = n / pie_total
            pie.append({
                'label': label,
                'count': n,
                'pct': round(frac * 100),
                'color': colors[i % len(colors)],
                'dash': round(frac * circ, 2),
                'gap': round(circ - frac * circ, 2),
                'offset': round(-acc * circ, 2),
            })
            acc += frac
    notificacoes = _pendencias_chamados(user)
    alertas = _alertas_sla_e_parada(abertos)
    seen_n = {(n.get('id'), n.get('tipo')) for n in notificacoes}
    for a in alertas:
        key = (a.get('id'), a.get('tipo'))
        if key not in seen_n:
            notificacoes.append(a)
            seen_n.add(key)
    ultimas_respostas = []
    if ids:
        at_rows = (
            ChamadoAtendimento.query.options(joinedload(ChamadoAtendimento.usuario))
            .filter(ChamadoAtendimento.chamado_id.in_(ids))
            .order_by(ChamadoAtendimento.data_criacao.desc())
            .limit(10)
            .all()
        )
        num_by_id = {c.id: c.numero_chamado for c in visiveis}
        for a in at_rows:
            ultimas_respostas.append({
                'chamado_id': a.chamado_id,
                'numero': num_by_id.get(a.chamado_id, ''),
                'texto': (a.o_que_foi_consertado or a.instrucoes or a.status or 'Atualização')[:140],
                'autor': a.usuario.nome if a.usuario else '',
                'quando': a.data_criacao.strftime('%d/%m %H:%M') if a.data_criacao else '',
                'url': url_for('main.listar_chamados', atender=a.chamado_id),
            })
    tickets_index = [{'id': c.id, 'numero': c.numero_chamado} for c in visiveis]
    dash = {
        'todos': len(visiveis),
        'meus': len(meus),
        'nao_atendidos': len(st_nao),
        'em_andamento': len(st_and),
        'pausados': len(st_pause),
        'vencidos': vencidos,
        'venc_at': venc_at,
        'venc_sol': venc_sol,
        'sem_respostas': len(sem_resp),
        'avaliacao': None,
        'pie': pie,
        'pie_total': pie_total,
        'horas': '00:00',
        'setores_chat': listar_setores(TIPO_SETOR_CHAMADOS),
    }
    return render_template(
        'dashboard.html',
        dash=dash,
        user_name=user.nome,
        primeiro_nome=_primeiro_nome(user),
        notificacoes=notificacoes,
        ultimas_respostas=ultimas_respostas,
        tickets_index=tickets_index,
        user_setor=_setor_usuario(user),
        sem_resp=sem_resp[:8],
        mesas=mesas,
        mesa_filtro=mesa_filtro,
    )


@main.route('/chamados')
@login_required
def listar_chamados():
    """Lista chamados abertos pelo usuário e encaminhamentos ao seu setor."""
    user = Usuario.query.get(session['user_id'])
    user_id = session['user_id']
    setor = _setor_usuario(user)
    chamados = _query_chamados_usuario(user).all()
    clientes = _clientes_para_chamados()
    grupos, fechados = _grupos_tickets(chamados)
    if setor:
        subtitulo = f'Chamados que você abriu e encaminhamentos para {setor}'
    else:
        subtitulo = 'Chamados que você abriu — todos os status'
    return render_template(
        'chamados.html',
        chamados=chamados,
        grupos=grupos,
        fechados=fechados,
        clientes=clientes,
        setores=listar_setores(TIPO_SETOR_CHAMADOS),
        subtitulo=subtitulo,
        atender_id=request.args.get('atender', type=int),
        user_setor=setor,
        primeiro_nome=_primeiro_nome(user),
        tickets_index=[{'id': c.id, 'numero': c.numero_chamado} for c in chamados],
        mesas=mesas_ativas(),
    )


@main.route('/chamados/<int:id>')
@login_required
def ver_chamado(id):
    """Ficha do ticket (layout 3 colunas)."""
    user = Usuario.query.get(session['user_id'])
    chamado = Chamado.query.options(
        joinedload(Chamado.cliente),
        joinedload(Chamado.encaminhado_por),
        joinedload(Chamado.mesa),
        joinedload(Chamado.contrato),
    ).get_or_404(id)
    visivel = Chamado.query.filter(_filtro_chamados_usuario(user), Chamado.id == id).first()
    if not visivel and not _eh_gestor(user):
        flash('Você não tem acesso a este ticket.', 'error')
        return redirect(url_for('main.listar_chamados'))
    solicitante = Usuario.query.get(chamado.tecnico_id)
    hops = (
        ChamadoEncaminhamento.query.options(joinedload(ChamadoEncaminhamento.usuario))
        .filter_by(chamado_id=chamado.id)
        .order_by(ChamadoEncaminhamento.id.asc())
        .all()
    )
    atends = (
        ChamadoAtendimento.query.options(joinedload(ChamadoAtendimento.usuario))
        .filter_by(chamado_id=chamado.id)
        .order_by(ChamadoAtendimento.id.asc())
        .all()
    )
    fotos = chamado.fotos.order_by(ChamadoFoto.id.desc()).all()
    ultimos = (
        Chamado.query.filter(Chamado.cliente_id == chamado.cliente_id, Chamado.id != chamado.id)
        .order_by(Chamado.data_criacao.desc())
        .limit(5)
        .all()
    )
    historico = []
    historico.append({
        'quando': chamado.data_criacao,
        'titulo': 'Ticket aberto',
        'texto': f'{solicitante.nome if solicitante else "Usuário"} criou {chamado.numero_chamado}',
    })
    for a in atends:
        historico.append({
            'quando': a.data_criacao,
            'titulo': a.status or 'Atendimento',
            'texto': a.o_que_foi_consertado or a.instrucoes or '',
            'autor': a.usuario.nome if a.usuario else '',
        })
    for h in hops:
        historico.append({
            'quando': h.data_criacao,
            'titulo': (h.tipo or 'encaminhar').title(),
            'texto': f'{(h.de_setor or "—")} → {(h.para_setor or "—")}. {h.instrucoes or h.notas or ""}'.strip(),
            'autor': h.usuario.nome if h.usuario else '',
        })
    historico.sort(key=lambda x: x['quando'] or datetime.min)
    estagio_key, estagio_label = _estagio_do_status(chamado.status)
    mensagens = (
        ChamadoMensagem.query.options(joinedload(ChamadoMensagem.usuario))
        .filter_by(chamado_id=chamado.id)
        .order_by(ChamadoMensagem.data_criacao.asc(), ChamadoMensagem.id.asc())
        .all()
    )
    for m in mensagens:
        historico.append({
            'quando': m.data_criacao,
            'titulo': m.canal or 'Comunicação',
            'texto': m.texto,
            'autor': m.usuario.nome if m.usuario else '',
        })
    historico.sort(key=lambda x: x['quando'] or datetime.min)
    sla = sla_do_chamado(chamado)
    from email_service import smtp_configurado
    return render_template(
        'chamado_detalhe.html',
        chamado=chamado,
        solicitante=solicitante,
        hops=hops,
        atends=atends,
        fotos=fotos,
        ultimos=ultimos,
        historico=historico,
        estagio_label=estagio_label,
        titulo_ticket=_titulo_chamado(chamado),
        aberto=not status_fechado(chamado.status),
        user_setor=_setor_usuario(user),
        setores=listar_setores(TIPO_SETOR_CHAMADOS),
        atender_id=None,
        mensagens=mensagens,
        sla=sla,
        mesas=mesas_ativas(),
        canais=CANAIS_MENSAGEM,
        smtp_ok=smtp_configurado(),
        tab=request.args.get('tab') or '',
    )

@main.route('/novo_chamado', methods=['GET', 'POST'])
@login_required
def novo_chamado():
    """Criar novo chamado"""
    clientes = _clientes_para_chamados()
    mesas = mesas_ativas()
    if request.method == 'POST':
        try:
            user = Usuario.query.get(session['user_id'])
            raw_cliente = (request.form.get('cliente_id') or '').strip()
            if raw_cliente.isdigit():
                cliente_id = int(raw_cliente)
            else:
                cli = Cliente.query.filter_by(nome=raw_cliente).first()
                cliente_id = cli.id if cli else None
            if not cliente_id:
                raise ValueError('Selecione um cliente válido.')

            numero_chamado = gerar_numero_chamado()
            setor_tecnico_id_raw = (request.form.get('setor_tecnico_id') or '').strip()
            setor_tecnico_id = int(setor_tecnico_id_raw) if setor_tecnico_id_raw.isdigit() else None
            chamado = Chamado(
                numero_chamado=numero_chamado,
                cliente_id=cliente_id,
                tipo_servico=request.form['tipo_servico'],
                descricao=request.form['descricao'],
                status=request.form.get('status') or 'Pendente',
                prioridade=normalizar_prioridade(request.form.get('prioridade') or 'Normal'),
                observacoes=request.form.get('observacoes'),
                tecnico_id=session['user_id'],
                mesa_id=resolver_mesa_id(request.form.get('mesa_id')),
                setor_tecnico_id=setor_tecnico_id,
            )
            vig = contrato_vigente(cliente_id)
            if vig:
                chamado.contrato_id = vig.id
            _vincular_equipamento_chamado(chamado, request.form, cliente_id)

            db.session.add(chamado)
            db.session.flush()
            aplicar_automacoes(chamado, 'criar', user)
            db.session.commit()
            _avisar_abertura_ticket(chamado, user)

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

    setores_tecnicos = ChamadoSetor.query.filter_by(ativo=True).order_by(ChamadoSetor.nome).all()
    return render_template(
        'novo_chamado.html',
        clientes=clientes,
        status_inicial=_status_inicial_novo(),
        mesas=mesas,
        mesa_padrao_id=(mesa_padrao().id if mesa_padrao() else None),
        setores_tecnicos=setores_tecnicos,
    )

@main.route('/chamados/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_chamado(id):
    """Editar chamado existente"""
    chamado = Chamado.query.get_or_404(id)
    clientes = _clientes_para_chamados()

    if request.method == 'POST':
        try:
            status_antes = chamado.status
            chamado.cliente_id = int(request.form['cliente_id'])
            _vincular_equipamento_chamado(chamado, request.form, chamado.cliente_id)
            chamado.tipo_servico = request.form['tipo_servico']
            chamado.descricao = request.form['descricao']
            chamado.status = request.form['status']
            chamado.prioridade = normalizar_prioridade(request.form['prioridade'])
            chamado.observacoes = request.form['observacoes']
            mesa_id = resolver_mesa_id(request.form.get('mesa_id'))
            if mesa_id:
                chamado.mesa_id = mesa_id

            if status_fechado(request.form['status']) and not chamado.data_conclusao:
                chamado.data_conclusao = datetime.utcnow()

            user = Usuario.query.get(session['user_id'])
            aplicar_automacoes(chamado, 'status', user, status_anterior=status_antes)

            db.session.commit()
            flash('Chamado atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_chamados'))

        except Exception as e:
            flash(f'Erro ao atualizar chamado: {str(e)}', 'error')
            db.session.rollback()

    return render_template(
        'editar_chamado.html',
        chamado=chamado,
        clientes=clientes,
        mesas=mesas_ativas(),
    )

@main.route('/clientes')
@login_required
def listar_clientes():
    """Lista todos os clientes (cadastro unificado portal/chamados/nutrição)."""
    user = Usuario.query.get(session['user_id'])
    if not _pode_gerenciar_clientes(user):
        flash('Você não tem permissão para gerenciar clientes.', 'error')
        return redirect(url_for('main.inicio'))
    clientes = Cliente.query.order_by(Cliente.data_criacao.desc()).all()
    return render_template('clientes.html', clientes=clientes)


@main.route('/novo_cliente', methods=['GET', 'POST'])
@login_required
def novo_cliente():
    """Criar novo cliente"""
    user = Usuario.query.get(session['user_id'])
    if not _pode_gerenciar_clientes(user):
        if _wants_json():
            return jsonify({'ok': False, 'message': 'Sem permissão para gerenciar clientes.'}), 403
        flash('Você não tem permissão para gerenciar clientes.', 'error')
        return redirect(url_for('main.inicio'))
    if request.method == 'POST':
        try:
            cliente = Cliente(
                nome=request.form['nome'],
                endereco=request.form.get('endereco') or '',
                telefone=request.form.get('telefone') or '',
                email=(request.form.get('email') or '').strip() or None,
                responsavel=request.form.get('responsavel') or '',
                telefone_responsavel=request.form.get('telefone_responsavel') or '',
                habilitado_chamados=request.form.get('habilitado_chamados') == 'on',
                habilitado_nutricao=request.form.get('habilitado_nutricao') == 'on',
            )

            db.session.add(cliente)
            db.session.commit()

            if _wants_json():
                return jsonify({
                    'ok': True,
                    'message': 'Cliente criado com sucesso!',
                    'cliente': _cliente_payload(cliente),
                })
            flash('Cliente criado com sucesso!', 'success')
            return redirect(url_for('main.listar_clientes'))

        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({'ok': False, 'message': str(e)}), 400
            flash(f'Erro ao criar cliente: {str(e)}', 'error')

    return render_template('novo_cliente.html')


@main.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_cliente(id):
    """Editar cliente existente"""
    user = Usuario.query.get(session['user_id'])
    if not _pode_gerenciar_clientes(user):
        if _wants_json():
            return jsonify({'ok': False, 'message': 'Sem permissão para gerenciar clientes.'}), 403
        flash('Você não tem permissão para gerenciar clientes.', 'error')
        return redirect(url_for('main.inicio'))
    cliente = Cliente.query.get_or_404(id)

    if request.method == 'POST':
        try:
            cliente.nome = request.form['nome']
            cliente.endereco = request.form.get('endereco') or ''
            cliente.telefone = request.form.get('telefone') or ''
            cliente.email = (request.form.get('email') or '').strip() or None
            cliente.responsavel = request.form.get('responsavel') or ''
            cliente.telefone_responsavel = request.form.get('telefone_responsavel') or ''
            cliente.habilitado_chamados = request.form.get('habilitado_chamados') == 'on'
            cliente.habilitado_nutricao = request.form.get('habilitado_nutricao') == 'on'

            db.session.commit()
            if _wants_json():
                return jsonify({
                    'ok': True,
                    'message': 'Cliente atualizado com sucesso!',
                    'cliente': _cliente_payload(cliente),
                })
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('main.listar_clientes'))

        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({'ok': False, 'message': str(e)}), 400
            flash(f'Erro ao atualizar cliente: {str(e)}', 'error')

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
    user = Usuario.query.get(session['user_id'])
    if request.method == 'GET':
        return jsonify({'ok': True, 'chamado': _chamado_atender_payload(chamado, user)})

    if not user:
        return jsonify({'ok': False, 'message': 'Sessão inválida.'}), 401

    acao = (request.form.get('acao') or 'salvar').strip().lower()
    status_antes = chamado.status
    notas = (request.form.get('atendimento_notas') or '').strip()
    instrucoes = (request.form.get('instrucoes') or '').strip()
    setor = normalizar_setor_chamado(request.form.get('setor_destino'))
    aguardar_peca = request.form.get('aguardar_peca') in ('1', 'on', 'true', 'sim')
    status_form = (request.form.get('status') or '').strip()
    pode_devolver = _pode_devolver(chamado, user)
    origem = _setor_origem_atual(chamado)
    arquivos_conserto = _arquivos_request('fotos', 'foto')
    arquivos_enc = _arquivos_request('fotos_encaminhar', 'fotos_encaminhamento')
    hop_tipo = None
    hop_de = ''
    hop_para = ''
    atendimento_status = None

    if aguardar_peca:
        setor = SETOR_COMPRAS

    def _exige_servico():
        if not notas:
            return 'Informe o que foi consertado.'
        tem_foto = any(
            arq and getattr(arq, 'filename', None) for arq in arquivos_conserto
        )
        if not tem_foto:
            return 'Anexe a foto do serviço realizado.'
        return None

    if acao == 'encaminhar':
        if aguardar_peca:
            setor = SETOR_COMPRAS
        if not setor:
            return jsonify({'ok': False, 'message': 'Selecione o setor para encaminhar.'}), 400
        if not instrucoes:
            instrucoes = chamado.encaminhamento_instrucoes or ''
        if not instrucoes:
            instrucoes = 'Aguardar peça' if aguardar_peca else ''
        if not instrucoes:
            return jsonify({'ok': False, 'message': 'Informe o que precisa fazer.'}), 400
        if pode_devolver and aguardar_peca:
            erro = _exige_servico()
            if erro:
                return jsonify({'ok': False, 'message': erro}), 400
        de_setor = _setor_atuacao(user, chamado)
        chamado.setor_origem = de_setor or chamado.setor_origem
        chamado.setor_destino = setor
        chamado.encaminhamento_instrucoes = instrucoes
        chamado.encaminhado_por_id = user.id
        chamado.encaminhado_em = datetime.utcnow()
        chamado.status = STATUS_AGUARDAR_PECA if aguardar_peca else STATUS_ENCAMINHADO
        hop_tipo = TIPO_HOP_PECA if aguardar_peca else TIPO_HOP_ENCAMINHAR
        hop_de, hop_para = de_setor, setor
    elif acao == 'finalizar':
        if pode_devolver:
            dest_voltar = origem
            if not dest_voltar:
                return jsonify({
                    'ok': False,
                    'message': (
                        'Não foi possível identificar o setor que encaminhou. '
                        'Cadastre o setor de origem (ex.: Informática) em Acessos.'
                    ),
                }), 400
            erro = _exige_servico()
            if erro:
                return jsonify({'ok': False, 'message': erro}), 400
            de_setor = _setor_atuacao(user, chamado)
            chamado.setor_origem = de_setor
            chamado.setor_destino = dest_voltar
            chamado.encaminhado_por_id = user.id
            chamado.encaminhado_em = datetime.utcnow()
            chamado.status = STATUS_DEVOLVIDO
            chamado.data_conclusao = None
            hop_tipo = TIPO_HOP_DEVOLVER
            hop_de, hop_para = de_setor, dest_voltar
            atendimento_status = STATUS_ATENDIDO
        else:
            chamado.status = STATUS_ATENDIDO
    else:
        if aguardar_peca:
            chamado.status = STATUS_AGUARDAR_PECA
        elif status_form:
            if not (pode_devolver and status_fechado(status_form)):
                chamado.status = status_form
        if setor and not pode_devolver:
            chamado.setor_destino = setor
            chamado.encaminhamento_instrucoes = instrucoes or chamado.encaminhamento_instrucoes
            if not chamado.encaminhado_por_id:
                chamado.encaminhado_por_id = user.id
                chamado.encaminhado_em = datetime.utcnow()

    chamado.atendimento_notas = notas or chamado.atendimento_notas
    if chamado.status == STATUS_DEVOLVIDO:
        chamado.data_conclusao = None
    elif status_fechado(chamado.status) and not chamado.data_conclusao:
        chamado.data_conclusao = datetime.utcnow()

    pendencia_aberta = not status_fechado(chamado.status)
    atendimento = ChamadoAtendimento(
        chamado_id=chamado.id,
        usuario_id=user.id,
        o_que_foi_consertado=notas,
        status=atendimento_status or chamado.status,
        setor_destino=chamado.setor_destino,
        instrucoes=instrucoes,
        pendencia_aberta=pendencia_aberta,
    )
    db.session.add(atendimento)
    db.session.flush()

    if hop_tipo:
        db.session.add(ChamadoEncaminhamento(
            chamado_id=chamado.id,
            usuario_id=user.id,
            atendimento_id=atendimento.id,
            de_setor=hop_de or None,
            para_setor=hop_para,
            notas=notas or None,
            instrucoes=notas if hop_tipo == TIPO_HOP_DEVOLVER else instrucoes,
            tipo=hop_tipo,
            status=chamado.status,
        ))

    try:
        _salvar_fotos_chamado(chamado, atendimento, arquivos_conserto, TIPO_FOTO_CONSERTO)
        _salvar_fotos_chamado(chamado, atendimento, arquivos_enc, TIPO_FOTO_ENCAMINHAMENTO)
        aplicar_automacoes(chamado, 'status', user, status_anterior=status_antes)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'message': f'Erro ao gravar atendimento: {exc}'}), 400

    if acao == 'encaminhar':
        msg = f'Encaminhado para {chamado.setor_destino}.'
    elif acao == 'finalizar' and hop_tipo == TIPO_HOP_DEVOLVER:
        msg = f'Atendido e devolvido para {chamado.setor_destino}.'
    elif acao == 'finalizar':
        msg = 'Chamado finalizado.'
    else:
        msg = 'Atendimento gravado.'
    return jsonify({
        'ok': True,
        'success': True,
        'message': msg,
        'chamado': _chamado_atender_payload(chamado, user),
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


@main.route('/tecnicos', methods=['GET'])
@login_required
def tecnicos():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'tecnicos'):
        flash('Você não tem permissão para acessar Técnicos.', 'error')
        return redirect(url_for('main.inicio'))
    setores = ChamadoSetor.query.order_by(ChamadoSetor.nome).all()
    tecnicos_list = (
        ChamadoTecnico.query
        .options(joinedload(ChamadoTecnico.setor))
        .order_by(ChamadoTecnico.nome)
        .all()
    )
    return render_template(
        'tecnicos.html',
        setores=setores,
        tecnicos=tecnicos_list,
        funcoes=FUNCOES_TECNICO,
    )


@main.route('/tecnicos/setor/adicionar', methods=['POST'])
@login_required
def adicionar_chamado_setor():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'tecnicos'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome do setor.'}), 400
    if ChamadoSetor.query.filter_by(nome=nome).first():
        return jsonify({'ok': False, 'error': 'Setor já cadastrado.'}), 400
    s = ChamadoSetor(nome=nome, ativo=True)
    db.session.add(s)
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'nome': s.nome, 'ativo': s.ativo})


@main.route('/tecnicos/setor/<int:sid>/toggle', methods=['POST'])
@login_required
def toggle_chamado_setor(sid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'tecnicos'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    s = ChamadoSetor.query.get_or_404(sid)
    s.ativo = not s.ativo
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'ativo': s.ativo})


def _tecnico_json(t):
    setor_nome = t.setor.nome if t.setor else ''
    return {
        'ok': True,
        'id': t.id,
        'nome': t.nome,
        'email': t.email or '',
        'funcao': t.funcao or '',
        'funcao_label': t.funcao_label or '',
        'setor': setor_nome,
        'setor_id': t.setor_id or '',
        'ativo': t.ativo,
        'usuario_id': t.usuario_id,
        'vinculado': bool(t.usuario_id),
    }


def _parse_funcao_tecnico(data):
    funcao = (data.get('funcao') or '').strip().lower()
    if not funcao:
        return None, 'Informe a função do técnico.'
    if funcao not in FUNCOES_TECNICO_KEYS:
        return None, 'Função inválida.'
    return funcao, None


@main.route('/tecnicos/tecnico/adicionar', methods=['POST'])
@login_required
def adicionar_chamado_tecnico():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'tecnicos'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    email = _normalizar_email(data.get('email'))
    funcao, err_funcao = _parse_funcao_tecnico(data)
    setor_id_raw = (data.get('setor_id') or '').strip()
    setor_id = int(setor_id_raw) if setor_id_raw.isdigit() else None
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome do técnico.'}), 400
    if err_funcao:
        return jsonify({'ok': False, 'error': err_funcao}), 400
    usuario_vinculado = _usuario_por_email(email)
    t = ChamadoTecnico(
        nome=nome,
        email=email,
        funcao=funcao,
        setor_id=setor_id,
        usuario_id=usuario_vinculado.id if usuario_vinculado else None,
        ativo=True,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(_tecnico_json(t))


@main.route('/tecnicos/tecnico/<int:tid>/editar', methods=['POST'])
@login_required
def editar_chamado_tecnico(tid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'tecnicos'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    t = ChamadoTecnico.query.get_or_404(tid)
    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    email = _normalizar_email(data.get('email'))
    funcao, err_funcao = _parse_funcao_tecnico(data)
    setor_id_raw = (data.get('setor_id') or '').strip()
    setor_id = int(setor_id_raw) if setor_id_raw.isdigit() else None
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome do técnico.'}), 400
    if err_funcao:
        return jsonify({'ok': False, 'error': err_funcao}), 400
    t.nome = nome
    t.email = email
    t.funcao = funcao
    t.setor_id = setor_id
    u = _usuario_por_email(email)
    t.usuario_id = u.id if u else None
    db.session.commit()
    return jsonify(_tecnico_json(t))


@main.route('/tecnicos/tecnico/<int:tid>/excluir', methods=['POST'])
@login_required
def excluir_chamado_tecnico(tid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'tecnicos'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    t = ChamadoTecnico.query.get_or_404(tid)
    db.session.delete(t)
    db.session.commit()
    return jsonify({'ok': True})


@main.route('/telefones-ramais')
@login_required
def telefones_ramais():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'telefones_ramais'):
        flash('Você não tem permissão para acessar Telefones e Ramais.', 'error')
        return redirect(url_for('main.inicio'))
    setores = ChamadoSetor.query.order_by(ChamadoSetor.nome).all()
    ramais = (
        ChamadoRamal.query
        .options(joinedload(ChamadoRamal.setor))
        .order_by(ChamadoRamal.setor_id, ChamadoRamal.nome_pessoa)
        .all()
    )
    return render_template('telefones_ramais.html', setores=setores, ramais=ramais)


@main.route('/ramais/adicionar', methods=['POST'])
@login_required
def adicionar_ramal():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'telefones_ramais'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.get_json(silent=True) or request.form
    setor_id = (data.get('setor_id') or '').strip()
    nome_pessoa = (data.get('nome_pessoa') or '').strip()
    numero_ramal = (data.get('numero_ramal') or '').strip()
    if not setor_id or not nome_pessoa or not numero_ramal:
        return jsonify({'ok': False, 'error': 'Setor, nome e ramal são obrigatórios.'}), 400
    if not setor_id.isdigit():
        return jsonify({'ok': False, 'error': 'Setor inválido.'}), 400
    r = ChamadoRamal(
        setor_id=int(setor_id),
        nome_pessoa=nome_pessoa,
        numero_ramal=numero_ramal,
        nome_equipamento=(data.get('nome_equipamento') or '').strip() or None,
        login=(data.get('login') or '').strip() or None,
        senha=(data.get('senha') or '').strip() or None,
        endereco_configuracao=(data.get('endereco_configuracao') or '').strip() or None,
        ativo=(data.get('ativo') in (True, 'true', '1', 'on', 1)),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify({'ok': True, 'ramal': r.to_dict()})


@main.route('/ramais/<int:rid>/editar', methods=['POST'])
@login_required
def editar_ramal(rid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'telefones_ramais'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    r = ChamadoRamal.query.get_or_404(rid)
    data = request.get_json(silent=True) or request.form
    setor_id = (data.get('setor_id') or '').strip()
    nome_pessoa = (data.get('nome_pessoa') or '').strip()
    numero_ramal = (data.get('numero_ramal') or '').strip()
    if not setor_id or not nome_pessoa or not numero_ramal:
        return jsonify({'ok': False, 'error': 'Setor, nome e ramal são obrigatórios.'}), 400
    if not setor_id.isdigit():
        return jsonify({'ok': False, 'error': 'Setor inválido.'}), 400
    r.setor_id = int(setor_id)
    r.nome_pessoa = nome_pessoa
    r.numero_ramal = numero_ramal
    r.nome_equipamento = (data.get('nome_equipamento') or '').strip() or None
    r.login = (data.get('login') or '').strip() or None
    r.senha = (data.get('senha') or '').strip() or None
    r.endereco_configuracao = (data.get('endereco_configuracao') or '').strip() or None
    r.ativo = (data.get('ativo') in (True, 'true', '1', 'on', 1))
    db.session.commit()
    return jsonify({'ok': True, 'ramal': r.to_dict()})


@main.route('/ramais/<int:rid>/excluir', methods=['POST'])
@login_required
def excluir_ramal(rid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'telefones_ramais'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    r = ChamadoRamal.query.get_or_404(rid)
    db.session.delete(r)
    db.session.commit()
    return jsonify({'ok': True})


@main.route('/ramais/setor/adicionar', methods=['POST'])
@login_required
def adicionar_setor_ramal():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'telefones_ramais'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome do setor.'}), 400
    if ChamadoSetor.query.filter_by(nome=nome).first():
        return jsonify({'ok': False, 'error': 'Setor já cadastrado.'}), 400
    s = ChamadoSetor(nome=nome, ativo=True)
    db.session.add(s)
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'nome': s.nome})


@main.route('/ramais/setor/<int:sid>/toggle', methods=['POST'])
@login_required
def toggle_setor_ramal(sid):
    """Alterna ativo/inativo do setor (mesmo ChamadoSetor de técnicos/câmeras)."""
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'telefones_ramais'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    s = ChamadoSetor.query.get_or_404(sid)
    s.ativo = not s.ativo
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'ativo': s.ativo})


_UPLOAD_CAMERAS = Path(__file__).resolve().parent / 'static' / 'uploads' / 'cameras'


def _salvar_imagem_camera(arquivo, camera_id=None):
    """Salva imagem de câmera em static/uploads/cameras e retorna caminho relativo."""
    if not arquivo or not getattr(arquivo, 'filename', None):
        return None
    original = secure_filename(arquivo.filename)
    if not original:
        return None
    ext = Path(original).suffix.lower()
    if ext not in _FOTO_EXTS:
        return None
    _UPLOAD_CAMERAS.mkdir(parents=True, exist_ok=True)
    prefix = f'cam_{camera_id}_' if camera_id else 'cam_'
    fname = f'{prefix}{uuid.uuid4().hex[:10]}{ext}'
    dest = _UPLOAD_CAMERAS / fname
    arquivo.save(str(dest))
    return f'uploads/cameras/{fname}'


def _remover_imagem_camera(caminho):
    if not caminho:
        return
    try:
        path = Path(__file__).resolve().parent / 'static' / caminho
        if path.is_file():
            path.unlink()
    except OSError:
        pass


@main.route('/cameras')
@login_required
def cameras():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'cameras'):
        flash('Você não tem permissão para acessar Cadastro de Câmeras.', 'error')
        return redirect(url_for('main.inicio'))
    setores = ChamadoSetor.query.order_by(ChamadoSetor.nome).all()
    cameras_list = (
        ChamadoCamera.query
        .options(joinedload(ChamadoCamera.setor))
        .order_by(ChamadoCamera.nome)
        .all()
    )
    dvrs = sorted({
        (c.dvr or '').strip()
        for c in cameras_list
        if (c.dvr or '').strip()
    }, key=lambda s: s.lower())
    return render_template(
        'cameras.html',
        setores=setores,
        cameras=cameras_list,
        dvrs=dvrs,
    )


@main.route('/cameras/setor/adicionar', methods=['POST'])
@login_required
def adicionar_setor_camera():
    """Cadastro de setor (ChamadoSetor) a partir da página de câmeras."""
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'cameras'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome do setor.'}), 400
    if ChamadoSetor.query.filter_by(nome=nome).first():
        return jsonify({'ok': False, 'error': 'Setor já cadastrado.'}), 400
    s = ChamadoSetor(nome=nome, ativo=True)
    db.session.add(s)
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'nome': s.nome, 'ativo': s.ativo})


@main.route('/cameras/setor/<int:sid>/toggle', methods=['POST'])
@login_required
def toggle_setor_camera(sid):
    """Alterna ativo/inativo do setor (mesmo ChamadoSetor dos técnicos)."""
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'cameras'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    s = ChamadoSetor.query.get_or_404(sid)
    s.ativo = not s.ativo
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'ativo': s.ativo})


@main.route('/cameras/adicionar', methods=['POST'])
@login_required
def adicionar_camera():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'cameras'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.form
    nome = (data.get('nome') or '').strip()
    dvr = (data.get('dvr') or '').strip()
    setor_id = (data.get('setor_id') or '').strip()
    if not nome or not dvr or not setor_id:
        return jsonify({'ok': False, 'error': 'Nome, DVR e setor são obrigatórios.'}), 400
    if not setor_id.isdigit():
        return jsonify({'ok': False, 'error': 'Setor inválido.'}), 400
    if not ChamadoSetor.query.get(int(setor_id)):
        return jsonify({'ok': False, 'error': 'Setor não encontrado.'}), 400
    cam = ChamadoCamera(
        nome=nome,
        dvr=dvr,
        setor_id=int(setor_id),
        ativo=True,
    )
    db.session.add(cam)
    db.session.flush()
    imagem = _salvar_imagem_camera(request.files.get('imagem'), cam.id)
    if imagem:
        cam.imagem_path = imagem
    db.session.commit()
    return jsonify({'ok': True, 'camera': cam.to_dict()})


@main.route('/cameras/<int:cid>/editar', methods=['POST'])
@login_required
def editar_camera(cid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'cameras'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    cam = ChamadoCamera.query.get_or_404(cid)
    data = request.form
    nome = (data.get('nome') or '').strip()
    dvr = (data.get('dvr') or '').strip()
    setor_id = (data.get('setor_id') or '').strip()
    if not nome or not dvr or not setor_id:
        return jsonify({'ok': False, 'error': 'Nome, DVR e setor são obrigatórios.'}), 400
    if not setor_id.isdigit():
        return jsonify({'ok': False, 'error': 'Setor inválido.'}), 400
    if not ChamadoSetor.query.get(int(setor_id)):
        return jsonify({'ok': False, 'error': 'Setor não encontrado.'}), 400
    cam.nome = nome
    cam.dvr = dvr
    cam.setor_id = int(setor_id)
    nova = _salvar_imagem_camera(request.files.get('imagem'), cam.id)
    if nova:
        _remover_imagem_camera(cam.imagem_path)
        cam.imagem_path = nova
    db.session.commit()
    return jsonify({'ok': True, 'camera': cam.to_dict()})


@main.route('/cameras/<int:cid>/excluir', methods=['POST'])
@login_required
def excluir_camera(cid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'cameras'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    cam = ChamadoCamera.query.get_or_404(cid)
    _remover_imagem_camera(cam.imagem_path)
    db.session.delete(cam)
    db.session.commit()
    return jsonify({'ok': True})


_UPLOAD_PORTOES = Path(__file__).resolve().parent / 'static' / 'uploads' / 'portoes'


def _salvar_foto_portao(arquivo, portao_id=None):
    """Salva foto de portão em static/uploads/portoes e retorna caminho relativo."""
    if not arquivo or not getattr(arquivo, 'filename', None):
        return None
    original = secure_filename(arquivo.filename)
    if not original:
        return None
    ext = Path(original).suffix.lower()
    if ext not in _FOTO_EXTS:
        return None
    _UPLOAD_PORTOES.mkdir(parents=True, exist_ok=True)
    prefix = f'port_{portao_id}_' if portao_id else 'port_'
    fname = f'{prefix}{uuid.uuid4().hex[:10]}{ext}'
    dest = _UPLOAD_PORTOES / fname
    arquivo.save(str(dest))
    return f'uploads/portoes/{fname}'


def _remover_foto_portao(caminho):
    if not caminho:
        return
    try:
        path = Path(__file__).resolve().parent / 'static' / caminho
        if path.is_file():
            path.unlink()
    except OSError:
        pass


@main.route('/portoes')
@login_required
def portoes():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'portoes'):
        flash('Você não tem permissão para acessar Cadastro de Portões.', 'error')
        return redirect(url_for('main.inicio'))
    setores = ChamadoSetor.query.order_by(ChamadoSetor.nome).all()
    portoes_list = (
        ChamadoPortao.query
        .options(joinedload(ChamadoPortao.setor))
        .order_by(ChamadoPortao.local)
        .all()
    )
    locais = sorted({
        (p.local or '').strip()
        for p in portoes_list
        if (p.local or '').strip()
    }, key=lambda s: s.lower())
    return render_template(
        'portoes.html',
        setores=setores,
        portoes=portoes_list,
        locais=locais,
    )


@main.route('/portoes/adicionar', methods=['POST'])
@login_required
def adicionar_portao():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'portoes'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.form
    local = (data.get('local') or '').strip()
    setor_id = (data.get('setor_id') or '').strip()
    observacoes = (data.get('observacoes') or '').strip()
    if not local or not setor_id:
        return jsonify({'ok': False, 'error': 'Local e setor são obrigatórios.'}), 400
    if not setor_id.isdigit():
        return jsonify({'ok': False, 'error': 'Setor inválido.'}), 400
    if not ChamadoSetor.query.get(int(setor_id)):
        return jsonify({'ok': False, 'error': 'Setor não encontrado.'}), 400
    portao = ChamadoPortao(
        local=local,
        setor_id=int(setor_id),
        observacoes=observacoes or None,
    )
    db.session.add(portao)
    db.session.flush()
    foto = _salvar_foto_portao(request.files.get('foto'), portao.id)
    if foto:
        portao.foto_path = foto
    db.session.commit()
    return jsonify({'ok': True, 'portao': portao.to_dict()})


@main.route('/portoes/<int:pid>/editar', methods=['POST'])
@login_required
def editar_portao(pid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'portoes'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    portao = ChamadoPortao.query.get_or_404(pid)
    data = request.form
    local = (data.get('local') or '').strip()
    setor_id = (data.get('setor_id') or '').strip()
    observacoes = (data.get('observacoes') or '').strip()
    if not local or not setor_id:
        return jsonify({'ok': False, 'error': 'Local e setor são obrigatórios.'}), 400
    if not setor_id.isdigit():
        return jsonify({'ok': False, 'error': 'Setor inválido.'}), 400
    if not ChamadoSetor.query.get(int(setor_id)):
        return jsonify({'ok': False, 'error': 'Setor não encontrado.'}), 400
    portao.local = local
    portao.setor_id = int(setor_id)
    portao.observacoes = observacoes or None
    nova = _salvar_foto_portao(request.files.get('foto'), portao.id)
    if nova:
        _remover_foto_portao(portao.foto_path)
        portao.foto_path = nova
    db.session.commit()
    return jsonify({'ok': True, 'portao': portao.to_dict()})


@main.route('/portoes/<int:pid>/excluir', methods=['POST'])
@login_required
def excluir_portao(pid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'portoes'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    portao = ChamadoPortao.query.get_or_404(pid)
    _remover_foto_portao(portao.foto_path)
    db.session.delete(portao)
    db.session.commit()
    return jsonify({'ok': True})


@main.route('/portoes/setor/adicionar', methods=['POST'])
@login_required
def adicionar_setor_portao():
    """Cadastro de setor (ChamadoSetor) a partir da página de portões."""
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'portoes'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome do setor.'}), 400
    if ChamadoSetor.query.filter_by(nome=nome).first():
        return jsonify({'ok': False, 'error': 'Setor já cadastrado.'}), 400
    s = ChamadoSetor(nome=nome, ativo=True)
    db.session.add(s)
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'nome': s.nome, 'ativo': s.ativo})


@main.route('/portoes/setor/<int:sid>/toggle', methods=['POST'])
@login_required
def toggle_setor_portao(sid):
    """Alterna ativo/inativo do setor (mesmo ChamadoSetor de técnicos/câmeras)."""
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'portoes'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    s = ChamadoSetor.query.get_or_404(sid)
    s.ativo = not s.ativo
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'ativo': s.ativo})


def _parse_data_aquisicao(raw):
    """Parse YYYY-MM-DD date string; empty → None."""
    from datetime import datetime as _dt
    texto = (raw or '').strip()
    if not texto:
        return None
    try:
        return _dt.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        return False


@main.route('/estoque')
@login_required
def estoque():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'estoque'):
        flash('Você não tem permissão para acessar Estoque.', 'error')
        return redirect(url_for('main.inicio'))
    itens = ChamadoEstoque.query.order_by(ChamadoEstoque.produto.asc()).all()
    return render_template('estoque.html', itens=itens)


@main.route('/estoque/adicionar', methods=['POST'])
@login_required
def adicionar_estoque():
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'estoque'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.get_json(silent=True) or request.form
    produto = (data.get('produto') or '').strip()
    marca = (data.get('marca') or '').strip()
    modelo = (data.get('modelo') or '').strip()
    qtd_raw = (data.get('quantidade') or '0').strip()
    if not produto:
        return jsonify({'ok': False, 'error': 'Informe o nome do produto.'}), 400
    try:
        quantidade = int(qtd_raw)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Quantidade inválida.'}), 400
    if quantidade < 0:
        return jsonify({'ok': False, 'error': 'Quantidade não pode ser negativa.'}), 400
    data_aq = _parse_data_aquisicao(data.get('data_aquisicao'))
    if data_aq is False:
        return jsonify({'ok': False, 'error': 'Data de aquisição inválida.'}), 400
    item = ChamadoEstoque(
        produto=produto,
        marca=marca or None,
        modelo=modelo or None,
        quantidade=quantidade,
        data_aquisicao=data_aq,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'item': item.to_dict()})


@main.route('/estoque/<int:eid>/editar', methods=['POST'])
@login_required
def editar_estoque(eid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'estoque'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    item = ChamadoEstoque.query.get_or_404(eid)
    data = request.get_json(silent=True) or request.form
    produto = (data.get('produto') or '').strip()
    marca = (data.get('marca') or '').strip()
    modelo = (data.get('modelo') or '').strip()
    qtd_raw = (data.get('quantidade') or '0').strip()
    if not produto:
        return jsonify({'ok': False, 'error': 'Informe o nome do produto.'}), 400
    try:
        quantidade = int(qtd_raw)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Quantidade inválida.'}), 400
    if quantidade < 0:
        return jsonify({'ok': False, 'error': 'Quantidade não pode ser negativa.'}), 400
    data_aq = _parse_data_aquisicao(data.get('data_aquisicao'))
    if data_aq is False:
        return jsonify({'ok': False, 'error': 'Data de aquisição inválida.'}), 400
    item.produto = produto
    item.marca = marca or None
    item.modelo = modelo or None
    item.quantidade = quantidade
    item.data_aquisicao = data_aq
    db.session.commit()
    return jsonify({'ok': True, 'item': item.to_dict()})


@main.route('/estoque/<int:eid>/excluir', methods=['POST'])
@login_required
def excluir_estoque(eid):
    user = Usuario.query.get(session['user_id'])
    if not user or not user.tem_menu('chamados', 'estoque'):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    item = ChamadoEstoque.query.get_or_404(eid)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'ok': True})


@main.route('/equipamentos')
@login_required
def listar_equipamentos():
    """Cadastro de equipamentos (patrimônios) vinculados ao cliente."""
    equipamentos = (
        Equipamento.query.options(joinedload(Equipamento.cliente))
        .order_by(Equipamento.patrimonio.asc(), Equipamento.nome_equipamento.asc())
        .all()
    )
    clientes = _clientes_para_chamados()
    setores = ChamadoSetor.query.order_by(ChamadoSetor.nome).all()
    return render_template(
        'equipamentos.html',
        equipamentos=equipamentos,
        clientes=clientes,
        setores=setores,
    )


@main.route('/equipamentos/setor/adicionar', methods=['POST'])
@login_required
def adicionar_setor_equipamento():
    """Cadastro de setor (ChamadoSetor) a partir da página de equipamentos."""
    user = Usuario.query.get(session['user_id'])
    if not user or not (
        user.tem_menu('chamados', 'equipamentos') or user.tem_menu('chamados', 'recursos')
    ):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    data = request.get_json(silent=True) or request.form
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'error': 'Informe o nome do setor.'}), 400
    if ChamadoSetor.query.filter_by(nome=nome).first():
        return jsonify({'ok': False, 'error': 'Setor já cadastrado.'}), 400
    s = ChamadoSetor(nome=nome, ativo=True)
    db.session.add(s)
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'nome': s.nome, 'ativo': s.ativo})


@main.route('/equipamentos/setor/<int:sid>/toggle', methods=['POST'])
@login_required
def toggle_setor_equipamento(sid):
    """Alterna ativo/inativo do setor (mesmo ChamadoSetor de técnicos/câmeras/ramais)."""
    user = Usuario.query.get(session['user_id'])
    if not user or not (
        user.tem_menu('chamados', 'equipamentos') or user.tem_menu('chamados', 'recursos')
    ):
        return jsonify({'ok': False, 'error': 'Sem permissão'}), 403
    s = ChamadoSetor.query.get_or_404(sid)
    s.ativo = not s.ativo
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id, 'ativo': s.ativo})


def _dados_equipamento_form(data):
    codigo = (data.get('codigo') or data.get('patrimonio') or '').strip()
    nome = (data.get('nome') or data.get('nome_equipamento') or '').strip()
    setor = (data.get('setor') or data.get('localizacao') or '').strip()
    local = (data.get('local') or '').strip()
    cliente_raw = data.get('cliente_id')
    cliente_id = int(cliente_raw) if str(cliente_raw or '').isdigit() else None
    if not codigo:
        raise ValueError('Informe o código do equipamento.')
    if not nome:
        raise ValueError('Informe o nome do equipamento.')
    if not cliente_id:
        raise ValueError('Selecione o local (cliente).')
    cliente = Cliente.query.get(cliente_id)
    if not cliente:
        raise ValueError('Cliente inválido.')
    # Local = vínculo ao cliente: grava o nome para exibição na listagem
    local = local or (cliente.nome or '').strip() or None
    tipo = (data.get('tipo_recurso') or 'Estação').strip() or 'Estação'
    usuario = (data.get('usuario_equipamento') or data.get('usuario') or '').strip()
    ip = (data.get('ip') or '').strip()
    grupo = grupo_recurso_padrao(cliente_id)
    return {
        'patrimonio': codigo,
        'nome_equipamento': nome,
        'setor': setor or None,
        'localizacao': setor or None,
        'local': local,
        'data_compra': _parse_data_compra(data.get('data_compra')),
        'cliente_id': cliente_id,
        'ativo': True,
        'tipo_recurso': tipo,
        'grupo_id': grupo.id if grupo else None,
        'usuario_equipamento': usuario or None,
        'ip': ip or None,
        'is_agente': data.get('is_agente') in (True, 1, '1', 'on', 'true', 'sim'),
        'atualizado_em': datetime.utcnow(),
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
        equipamento.local = campos['local']
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
    clientes = _clientes_para_chamados()
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
    setores = ChamadoSetor.query.order_by(ChamadoSetor.nome).all()
    return render_template(
        'equipamentos.html',
        equipamentos=Equipamento.query.all(),
        clientes=clientes,
        setores=setores,
    )


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
        equipamento.local = campos['local']
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
@login_required
def relatorios():
    """Catálogo accordion de relatórios (estilo Tiflux)."""
    return render_template('relatorios.html', catalogo=RELATORIOS_CATALOGO)


def _pagina_relatorio_gestao():
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
        'relatorios_gestao.html',
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


@main.route('/relatorios/gestao-indicadores')
@login_required
def relatorio_gestao():
    """Relatório gerencial com dados reais de chamados."""
    return _pagina_relatorio_gestao()


@main.route('/relatorios/<slug>')
@login_required
def relatorio_item(slug):
    if slug == 'gestao-indicadores':
        return _pagina_relatorio_gestao()
    if slug in ('carga-trabalho', 'executivo-atendentes', 'executivo', 'eficiencia-atendimento'):
        return _pagina_relatorio_atendentes(slug)
    titulo = slug.replace('-', ' ').title()
    for cat in RELATORIOS_CATALOGO:
        for item in cat['items']:
            if item['slug'] == slug:
                titulo = item['label']
                break
    return render_template(
        'relatorios_vazio.html',
        titulo=titulo,
        mensagem='Sem dados para este relatório.',
    )


def _pagina_relatorio_atendentes(slug):
    periodo, data_de, data_ate, filtros = _filtro_periodo_chamados()
    chamados = Chamado.query.options(
        joinedload(Chamado.mesa),
        joinedload(Chamado.contrato),
    ).filter(*filtros).all()
    titulos = {
        'carga-trabalho': 'Carga de trabalho',
        'executivo-atendentes': 'Executivo de atendentes',
        'executivo': 'Executivo',
        'eficiencia-atendimento': 'Eficiência de atendimento',
    }
    agrup = 'setor' if slug == 'executivo' else 'usuario'
    buckets = {}
    tempos = []
    sla_ok = sla_nok = 0
    agora = datetime.utcnow()
    for c in chamados:
        user = Usuario.query.get(c.tecnico_id) if c.tecnico_id else None
        if agrup == 'setor':
            key = (c.mesa.nome if c.mesa else None) or (user.setor if user else None) or (c.setor_destino or 'Sem área')
            nome = key
            setor = key
        else:
            key = c.tecnico_id or 0
            nome = user.nome if user else '—'
            setor = (user.setor if user else '') or (c.mesa.nome if c.mesa else '') or '—'
        row = buckets.setdefault(key, {
            'nome': nome, 'setor': setor, 'pendente': 0, 'andamento': 0,
            'concluidos': 0, 'total': 0, 'sla_ok': 0, 'sla_nok': 0, 'tempos': [],
        })
        row['total'] += 1
        st = (c.status or '').strip()
        if st == 'Pendente':
            row['pendente'] += 1
        elif status_fechado(st):
            row['concluidos'] += 1
        else:
            row['andamento'] += 1
        info = sla_do_chamado(c)
        if c.data_conclusao and c.data_criacao:
            horas = (c.data_conclusao - c.data_criacao).total_seconds() / 3600.0
            row['tempos'].append(horas)
            tempos.append(horas)
        if info and c.data_conclusao:
            ok = c.data_conclusao <= info['venc_solucao']
            if ok:
                row['sla_ok'] += 1
                sla_ok += 1
            else:
                row['sla_nok'] += 1
                sla_nok += 1
        elif info and not status_fechado(st) and info.get('solucao_vencida'):
            row['sla_nok'] += 1
            sla_nok += 1
    linhas = []
    for row in buckets.values():
        n_t = len(row['tempos'])
        media = round(sum(row['tempos']) / n_t, 1) if n_t else None
        aval = row['sla_ok'] + row['sla_nok']
        pct = round(row['sla_ok'] * 100.0 / aval, 1) if aval else None
        linhas.append({
            'nome': row['nome'],
            'setor': row['setor'],
            'pendente': row['pendente'],
            'andamento': row['andamento'],
            'concluidos': row['concluidos'],
            'total': row['total'],
            'tempo_medio': media,
            'sla_pct': pct,
        })
    linhas.sort(key=lambda r: r['total'], reverse=True)
    aval_total = sla_ok + sla_nok
    stats = {
        'volume': len(chamados),
        'tempo_medio': round(sum(tempos) / len(tempos), 1) if tempos else None,
        'sla_pct': round(sla_ok * 100.0 / aval_total, 1) if aval_total else None,
        'abertos': sum(1 for c in chamados if not status_fechado(c.status)),
        'concluidos': sum(1 for c in chamados if status_fechado(c.status)),
        'atendentes': len(linhas),
    }
    return render_template(
        'relatorios_atendentes.html',
        titulo=titulos.get(slug, 'Indicadores'),
        slug=slug,
        agrup=agrup,
        stats=stats,
        linhas=linhas,
        filtros={
            'periodo': periodo,
            'data_de': data_de.isoformat() if data_de else '',
            'data_ate': data_ate.isoformat() if data_ate else '',
        },
    )


def _parse_data_iso(valor):
    raw = (valor or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _gravar_contrato(form, row=None):
    cliente_id = form.get('cliente_id')
    if not str(cliente_id or '').isdigit():
        raise ValueError('Selecione um cliente.')
    cliente_id = int(cliente_id)
    if not Cliente.query.get(cliente_id):
        raise ValueError('Cliente inválido.')
    tipo = (form.get('tipo') or 'Suporte').strip()
    if tipo not in TIPOS_CONTRATO:
        tipo = 'Personalizado'
    padrao = sla_horas_tipo_contrato(tipo)
    at_h = form.get('sla_atendimento_horas')
    sol_h = form.get('sla_solucao_horas')
    at_h = int(at_h) if str(at_h or '').strip().isdigit() else padrao[0]
    sol_h = int(sol_h) if str(sol_h or '').strip().isdigit() else padrao[1]
    if row is None:
        row = Contrato(cliente_id=cliente_id)
        db.session.add(row)
    else:
        row.cliente_id = cliente_id
    row.tipo = tipo
    row.inicio = _parse_data_iso(form.get('inicio'))
    row.vencimento = _parse_data_iso(form.get('vencimento'))
    row.dados_faturamento = (form.get('dados_faturamento') or '').strip() or None
    row.valor = parse_valor_faturamento(form.get('valor'))
    row.observacao = (form.get('observacao') or '').strip() or None
    row.sla_atendimento_horas = at_h
    row.sla_solucao_horas = sol_h
    db.session.commit()
    return row


@main.route('/contratos', methods=['GET', 'POST'])
@login_required
def contratos():
    if request.method == 'POST':
        try:
            cid = request.form.get('id')
            row = Contrato.query.get(int(cid)) if str(cid or '').isdigit() else None
            _gravar_contrato(request.form, row)
            flash('Contrato salvo.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(str(e), 'error')
        return redirect(url_for('main.contratos', cliente_id=request.form.get('cliente_id') or None))
    cliente_id = request.args.get('cliente_id', type=int)
    q = Contrato.query.options(joinedload(Contrato.cliente)).order_by(Contrato.id.desc())
    if cliente_id:
        q = q.filter_by(cliente_id=cliente_id)
    return render_template(
        'contratos.html',
        contratos=q.all(),
        clientes=Cliente.query.order_by(Cliente.nome.asc()).all(),
        tipos=TIPOS_CONTRATO,
        cliente_filtro=cliente_id,
        sla_tipos= {t: sla_horas_tipo_contrato(t) for t in TIPOS_CONTRATO},
    )


@main.route('/contratos/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_contrato(id):
    row = Contrato.query.get_or_404(id)
    try:
        Chamado.query.filter_by(contrato_id=row.id).update({Chamado.contrato_id: None})
        db.session.delete(row)
        db.session.commit()
        flash('Contrato excluído.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(str(e), 'error')
    return redirect(url_for('main.contratos'))


@main.route('/agenda')
@login_required
def agenda():
    user = Usuario.query.get(session['user_id'])
    visiveis = _query_chamados_usuario(user).all()
    eventos = []
    for c in visiveis:
        if not c.data_criacao:
            continue
        eventos.append({
            'id': c.id,
            'numero': c.numero_chamado,
            'titulo': _titulo_chamado(c),
            'data': c.data_criacao.strftime('%Y-%m-%d'),
            'hora': c.data_criacao.strftime('%H:%M'),
            'url': url_for('main.ver_chamado', id=c.id),
        })
    return render_template(
        'agenda.html',
        user_name=user.nome,
        eventos=eventos,
    )


_UPLOAD_CONHECIMENTOS = Path(__file__).resolve().parent / 'static' / 'uploads' / 'conhecimentos'
_CONH_MAX_BYTES = 25 * 1024 * 1024
_CONH_EXTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.txt', '.zip'}


def _sanitize_html(raw):
    import re
    text = raw or ''
    text = re.sub(r'(?is)<script[^>]*>.*?</script>', '', text)
    text = re.sub(r'(?is)<iframe[^>]*>.*?</iframe>', '', text)
    text = re.sub(r'(?i)\son\w+\s*=', ' ', text)
    return text.strip()


@main.route('/conhecimentos')
@login_required
def conhecimentos():
    q = (request.args.get('q') or '').strip()
    ordem = (request.args.get('ordem') or 'az').strip()
    query = ChamadoConhecimento.query
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            ChamadoConhecimento.titulo.ilike(like),
            ChamadoConhecimento.tags.ilike(like),
            ChamadoConhecimento.corpo.ilike(like),
        ))
    if ordem == 'za':
        query = query.order_by(ChamadoConhecimento.titulo.desc())
    elif ordem == 'novo':
        query = query.order_by(ChamadoConhecimento.data_criacao.desc())
    else:
        query = query.order_by(ChamadoConhecimento.titulo.asc())
    artigos = query.all()
    nomes_pasta = [p.nome for p in ConhecimentoPasta.query.order_by(ConhecimentoPasta.nome.asc()).all()]
    if PASTA_CONHECIMENTO_PADRAO not in nomes_pasta:
        nomes_pasta.insert(0, PASTA_CONHECIMENTO_PADRAO)
    grupos = []
    seen = set()
    by_pasta = {}
    for a in artigos:
        nome = (a.pasta or PASTA_CONHECIMENTO_PADRAO).strip() or PASTA_CONHECIMENTO_PADRAO
        by_pasta.setdefault(nome, []).append(a)
        seen.add(nome)
    for nome in nomes_pasta:
        grupos.append({'nome': nome, 'artigos': by_pasta.get(nome, [])})
        seen.discard(nome)
    for nome in sorted(seen):
        grupos.append({'nome': nome, 'artigos': by_pasta.get(nome, [])})
    return render_template(
        'conhecimentos.html',
        artigos=artigos,
        grupos=grupos,
        q=q,
        ordem=ordem,
        pasta_filtro=request.args.get('pasta') or '',
    )


@main.route('/conhecimentos/novo', methods=['GET', 'POST'])
@login_required
def novo_conhecimento():
    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        if not titulo:
            flash('Informe um título.', 'error')
            return render_template('conhecimento_form.html', pastas=_nomes_pastas())
        pasta = (request.form.get('pasta') or PASTA_CONHECIMENTO_PADRAO).strip() or PASTA_CONHECIMENTO_PADRAO
        nova = (request.form.get('pasta_nova') or '').strip()
        if nova:
            pasta = nova[:80]
            if not ConhecimentoPasta.query.filter_by(nome=pasta).first():
                db.session.add(ConhecimentoPasta(nome=pasta))
        tags = (request.form.get('tags') or '').strip()
        catalogo = (request.form.get('catalogo') or 'Todos').strip() or 'Todos'
        corpo = _sanitize_html(request.form.get('corpo'))
        arquivo_path = None
        arquivo_nome = None
        arq = request.files.get('arquivo')
        if arq and getattr(arq, 'filename', None):
            original = secure_filename(arq.filename)
            ext = Path(original).suffix.lower()
            if ext not in _CONH_EXTS:
                flash('Tipo de arquivo não permitido.', 'error')
                return render_template('conhecimento_form.html', pastas=_nomes_pastas())
            arq.seek(0, os.SEEK_END)
            size = arq.tell()
            arq.seek(0)
            if size > _CONH_MAX_BYTES:
                flash('Arquivo excede 25 MB.', 'error')
                return render_template('conhecimento_form.html', pastas=_nomes_pastas())
            _UPLOAD_CONHECIMENTOS.mkdir(parents=True, exist_ok=True)
            fname = f'c_{uuid.uuid4().hex[:12]}{ext}'
            dest = _UPLOAD_CONHECIMENTOS / fname
            arq.save(str(dest))
            arquivo_path = f'uploads/conhecimentos/{fname}'
            arquivo_nome = original
        row = ChamadoConhecimento(
            titulo=titulo[:200],
            pasta=pasta[:80],
            tags=tags[:255],
            catalogo=catalogo[:80],
            corpo=corpo,
            arquivo=arquivo_path,
            arquivo_nome=arquivo_nome,
            usuario_id=session['user_id'],
        )
        db.session.add(row)
        db.session.commit()
        flash('Conhecimento criado.', 'success')
        return redirect(url_for('main.conhecimentos'))
    return render_template('conhecimento_form.html', pastas=_nomes_pastas())


@main.route('/conhecimentos/<int:id>')
@login_required
def ver_conhecimento(id):
    artigo = ChamadoConhecimento.query.get_or_404(id)
    return render_template('conhecimento_ver.html', artigo=artigo)


def _nomes_pastas():
    nomes = [p.nome for p in ConhecimentoPasta.query.order_by(ConhecimentoPasta.nome.asc()).all()]
    if PASTA_CONHECIMENTO_PADRAO not in nomes:
        nomes.insert(0, PASTA_CONHECIMENTO_PADRAO)
    return nomes


@main.route('/conhecimentos/pastas', methods=['POST'])
@login_required
def nova_pasta_conhecimento():
    nome = (request.form.get('nome') or '').strip()[:80]
    if not nome:
        flash('Informe o nome da pasta.', 'error')
        return redirect(url_for('main.conhecimentos'))
    if not ConhecimentoPasta.query.filter_by(nome=nome).first():
        db.session.add(ConhecimentoPasta(nome=nome))
        db.session.commit()
        flash('Pasta criada.', 'success')
    else:
        flash('Essa pasta já existe.', 'info')
    return redirect(url_for('main.conhecimentos'))


@main.route('/chamados/<int:id>/mensagem', methods=['POST'])
@login_required
def mensagem_chamado(id):
    user = Usuario.query.get(session['user_id'])
    chamado = Chamado.query.options(joinedload(Chamado.cliente)).get_or_404(id)
    texto = (request.form.get('texto') or '').strip()
    canal = (request.form.get('canal') or 'Chat').strip()
    if canal not in CANAIS_MENSAGEM:
        canal = 'Chat'
    interno = request.form.get('interno') in ('1', 'on', 'true', 'sim')
    if not texto:
        flash('Escreva a mensagem.', 'error')
        return redirect(url_for('main.ver_chamado', id=id, tab='com'))
    enviada = False
    if canal == 'E-mail' and not interno:
        dest = ((chamado.cliente.email if chamado.cliente else '') or '').strip()
        try:
            from email_service import smtp_configurado, enviar_email
            if dest and smtp_configurado():
                enviar_email(
                    dest,
                    f'Ticket {chamado.numero_chamado} — comunicação',
                    texto,
                )
                enviada = True
            elif canal == 'E-mail' and not dest:
                flash('Cliente sem e-mail; mensagem registrada sem envio.', 'info')
            elif not smtp_configurado():
                flash('SMTP não configurado; mensagem registrada sem envio.', 'info')
        except Exception as exc:
            flash(f'E-mail não enviado ({exc}). Mensagem registrada.', 'error')
    db.session.add(ChamadoMensagem(
        chamado_id=chamado.id,
        usuario_id=user.id if user else None,
        texto=texto,
        canal=canal if not interno else 'Interno',
        visivel_cliente=not interno,
        enviada=enviada,
        origem='usuario',
    ))
    db.session.commit()
    flash('Mensagem registrada.' + (' E-mail enviado.' if enviada else ''), 'success')
    return redirect(url_for('main.ver_chamado', id=id, tab='com'))


@main.route('/chamados/<int:id>/mesa', methods=['POST'])
@login_required
def atualizar_mesa_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    mesa_id = resolver_mesa_id(request.form.get('mesa_id'))
    if mesa_id:
        chamado.mesa_id = mesa_id
        db.session.commit()
        flash('Mesa atualizada.', 'success')
    return redirect(url_for('main.ver_chamado', id=id))


@main.route('/automacoes', methods=['GET', 'POST'])
@login_required
def automacoes():
    if request.method == 'POST':
        acao = (request.form.get('acao') or 'regra').strip()
        try:
            if acao == 'mesa':
                nome = (request.form.get('nome') or '').strip()[:80]
                if not nome:
                    raise ValueError('Informe o nome da mesa.')
                if MesaServico.query.filter_by(nome=nome).first():
                    raise ValueError('Essa mesa já existe.')
                db.session.add(MesaServico(nome=nome, ativa=True))
                db.session.commit()
                flash('Mesa cadastrada.', 'success')
            elif acao == 'toggle_mesa':
                mesa = MesaServico.query.get_or_404(int(request.form['id']))
                mesa.ativa = not bool(mesa.ativa)
                db.session.commit()
            elif acao == 'sla':
                pri = normalizar_prioridade(request.form.get('prioridade'))
                at_h = int(request.form.get('prazo_atendimento_horas') or 8)
                sol_h = int(request.form.get('prazo_solucao_horas') or 24)
                row = SlaPrioridade.query.filter_by(prioridade=pri).first()
                if not row:
                    row = SlaPrioridade(prioridade=pri)
                    db.session.add(row)
                row.prazo_atendimento_horas = max(1, at_h)
                row.prazo_solucao_horas = max(1, sol_h)
                db.session.commit()
                flash('SLA atualizado.', 'success')
            elif acao == 'toggle_regra':
                regra = ChamadoAutomacao.query.get_or_404(int(request.form['id']))
                regra.ativa = not bool(regra.ativa)
                db.session.commit()
            elif acao == 'excluir_regra':
                regra = ChamadoAutomacao.query.get_or_404(int(request.form['id']))
                db.session.delete(regra)
                db.session.commit()
                flash('Automação excluída.', 'success')
            elif acao in ('regra', 'editar_regra'):
                nome = (request.form.get('nome') or '').strip()
                if not nome:
                    raise ValueError('Informe o nome da regra.')
                gatilho_val = (request.form.get('gatilho') or 'criar').strip()
                gatilhos_validos = ('criar', 'status', 'sla_proximo', 'sla_vencido', 'sem_resposta')
                dados = dict(
                    nome=nome[:120],
                    gatilho=gatilho_val if gatilho_val in gatilhos_validos else 'criar',
                    prioridade_quando=(request.form.get('prioridade_quando') or '').strip() or None,
                    status_quando=(request.form.get('status_quando') or '').strip() or None,
                    acao=(request.form.get('acao_regra') or 'mensagem').strip() or 'mensagem',
                    mensagem_padrao=(request.form.get('mensagem_padrao') or '').strip() or None,
                    mesa_id=int(request.form['mesa_id']) if str(request.form.get('mesa_id') or '').isdigit() else None,
                    ativa='ativa' in request.form,
                )
                if acao == 'editar_regra':
                    regra = ChamadoAutomacao.query.get_or_404(int(request.form['id']))
                    for k, v in dados.items():
                        setattr(regra, k, v)
                else:
                    dados['ativa'] = True
                    db.session.add(ChamadoAutomacao(**dados))
                db.session.commit()
                flash('Automação salva.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(str(e), 'error')
        return redirect(url_for('main.automacoes'))
    return render_template(
        'automacoes.html',
        regras=ChamadoAutomacao.query.order_by(ChamadoAutomacao.id.asc()).all(),
        mesas=MesaServico.query.order_by(MesaServico.nome.asc()).all(),
        slas=SlaPrioridade.query.order_by(SlaPrioridade.id.asc()).all(),
        setores=listar_setores(TIPO_SETOR_CHAMADOS),
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
