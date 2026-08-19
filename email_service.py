"""Envio de e-mail do sistema (redefinição de senha)."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from db_config import (
    MAIL_FROM,
    MAIL_PASSWORD,
    MAIL_PORT,
    MAIL_SERVER,
    MAIL_USERNAME,
    MAIL_USE_TLS,
)

ASSUNTO_REDEFINICAO = 'redefinição senha sistema são geraldo'


def _config_env():
    return {
        'servidor': (MAIL_SERVER or '').strip(),
        'porta': int(MAIL_PORT or 587),
        'usar_tls': bool(MAIL_USE_TLS),
        'usuario': (MAIL_USERNAME or '').strip(),
        'senha': MAIL_PASSWORD or '',
        'remetente': (MAIL_FROM or '').strip(),
    }


def obter_config_smtp():
    """Usa a configuração salva no banco; se faltar, cai no ambiente / db_config."""
    cfg = _config_env()
    try:
        from flask import has_app_context
        from models import ConfiguracaoEmail

        if not has_app_context():
            return cfg
        row = ConfiguracaoEmail.query.get(1)
        if not row:
            return cfg
        cfg = {
            'servidor': (row.servidor or '').strip() or cfg['servidor'],
            'porta': int(row.porta or cfg['porta'] or 587),
            'usar_tls': bool(row.usar_tls) if row.usar_tls is not None else cfg['usar_tls'],
            'usuario': (row.usuario or '').strip() or cfg['usuario'],
            'senha': row.senha if row.senha else cfg['senha'],
            'remetente': (row.remetente or '').strip() or cfg['remetente'],
        }
    except Exception:
        pass
    if not cfg['remetente']:
        cfg['remetente'] = cfg['usuario']
    return cfg


def smtp_configurado() -> bool:
    cfg = obter_config_smtp()
    return bool(cfg.get('servidor') and cfg.get('remetente'))


def enviar_email(destinatario: str, assunto: str, texto: str, html: str | None = None) -> None:
    cfg = obter_config_smtp()
    if not cfg.get('servidor') or not cfg.get('remetente'):
        raise RuntimeError(
            'E-mail de saída não está configurado. '
            'Preencha Servidor SMTP e Remetente em Opções → Configurações.'
        )

    msg = EmailMessage()
    msg['Subject'] = assunto
    msg['From'] = cfg['remetente']
    msg['To'] = destinatario
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype='html')

    with smtplib.SMTP(cfg['servidor'], int(cfg['porta'] or 587), timeout=20) as smtp:
        if cfg.get('usar_tls'):
            smtp.starttls()
        if cfg.get('usuario'):
            smtp.login(cfg['usuario'], cfg.get('senha') or '')
        smtp.send_message(msg)


def _esc(valor) -> str:
    text = '' if valor is None else str(valor)
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def montar_email_visualizacao_ticket(chamado, opener, url_detalhe: str):
    """HTML estilo Tiflux: VISUALIZAÇÃO DE TICKET, para o usuário que abriu."""
    from models import status_fechado

    numero = _esc(getattr(chamado, 'numero_chamado', '') or '')
    titulo_raw = (getattr(chamado, 'descricao', None) or getattr(chamado, 'tipo_servico', None) or numero or '').strip()
    titulo = titulo_raw.replace('\n', ' ')
    if len(titulo) > 140:
        titulo = titulo[:137] + '…'
    assunto_linha = f'[{numero}] {titulo}' if numero else titulo
    aberto = not status_fechado(getattr(chamado, 'status', None))
    badge = 'Aberto' if aberto else _esc(chamado.status or 'Fechado')
    badge_bg = '#1ABC9C' if aberto else '#8a97a6'
    cliente = _esc(chamado.cliente.nome if getattr(chamado, 'cliente', None) else '—')
    tipo = _esc(getattr(chamado, 'tipo_servico', None) or '—')
    mesa = _esc(chamado.mesa.nome if getattr(chamado, 'mesa', None) else '—')
    setor = _esc(getattr(chamado, 'setor_destino', None) or '—')
    prioridade = _esc(getattr(chamado, 'prioridade', None) or '—')
    recurso = '—'
    sol_nome = _esc(opener.nome if opener else '—')
    sol_email = _esc(opener.email if opener else '')
    solicitante = f'{sol_nome} ({sol_email})' if sol_email else sol_nome
    responsavel = solicitante
    desc = _esc(getattr(chamado, 'descricao', None) or '—').replace('\n', '<br>')
    arquivos = '—'
    link = _esc(url_detalhe)
    html = f'''
<div style="font-family:Arial,Helvetica,sans-serif;background:#f4f6f8;padding:24px 12px;">
  <div style="max-width:640px;margin:0 auto;background:#fff;border:1px solid #e4e8ec;border-radius:8px;overflow:hidden;">
    <div style="padding:20px 24px 8px;border-bottom:1px solid #eef1f4;">
      <div style="font-size:13px;letter-spacing:.08em;color:#5b6b7c;font-weight:700;">VISUALIZAÇÃO DE TICKET</div>
      <div style="margin-top:10px;">
        <span style="display:inline-block;background:{badge_bg};color:#fff;font-size:12px;font-weight:700;padding:4px 10px;border-radius:999px;">{badge}</span>
      </div>
      <h1 style="font-size:18px;line-height:1.35;color:#2c3e50;margin:14px 0 0;font-weight:700;">{_esc(assunto_linha)}</h1>
    </div>
    <div style="padding:8px 24px 20px;font-size:14px;color:#3d4c5c;">
      <p style="margin:12px 0;"><strong>Cliente</strong><br>{cliente}</p>
      <p style="margin:12px 0;"><strong>Tipo</strong><br>{tipo}</p>
      <p style="margin:12px 0;"><strong>Mesa</strong><br>{mesa}</p>
      <p style="margin:12px 0;"><strong>Área responsável</strong><br>{setor}</p>
      <p style="margin:12px 0;"><strong>Prioridade</strong><br>{prioridade}</p>
      <p style="margin:12px 0;"><strong>Recurso</strong><br>{recurso}</p>
      <p style="margin:12px 0;"><strong>Solicitante</strong><br>{solicitante}</p>
      <p style="margin:12px 0;"><strong>Responsável</strong><br>{responsavel}</p>
      <p style="margin:12px 0;"><strong>Descrição</strong><br>{desc}</p>
      <p style="margin:12px 0;"><strong>Arquivos</strong><br>{arquivos}</p>
      <p style="margin:20px 0 8px;">
        <a href="{link}" style="color:#1ABC9C;font-weight:700;text-decoration:none;">+ Detalhes</a>
      </p>
    </div>
  </div>
</div>
'''
    texto = (
        f'VISUALIZAÇÃO DE TICKET\n'
        f'{badge} — {assunto_linha}\n\n'
        f'Cliente: {chamado.cliente.nome if getattr(chamado, "cliente", None) else "—"}\n'
        f'Tipo: {getattr(chamado, "tipo_servico", None) or "—"}\n'
        f'Mesa: {chamado.mesa.nome if getattr(chamado, "mesa", None) else "—"}\n'
        f'Área responsável: {getattr(chamado, "setor_destino", None) or "—"}\n'
        f'Prioridade: {getattr(chamado, "prioridade", None) or "—"}\n'
        f'Recurso: —\n'
        f'Solicitante: {sol_nome} ({sol_email})\n'
        f'Responsável: {sol_nome}\n\n'
        f'Descrição:\n{getattr(chamado, "descricao", None) or "—"}\n\n'
        f'Arquivos: —\n'
        f'Detalhes: {url_detalhe}\n'
    )
    assunto = f'Ticket {numero} aberto — VISUALIZAÇÃO DE TICKET'
    return assunto, texto, html


def enviar_visualizacao_ticket(chamado, opener, url_detalhe: str) -> None:
    dest = (getattr(opener, 'email', None) or '').strip()
    if not dest:
        raise ValueError('Usuário sem e-mail.')
    assunto, texto, html = montar_email_visualizacao_ticket(chamado, opener, url_detalhe)
    enviar_email(dest, assunto, texto, html)


def enviar_redefinicao_senha(destinatario: str, nome: str, link: str) -> None:
    texto = (
        f'Olá, {nome}.\n\n'
        'Recebemos um pedido para redefinir a senha da sua conta no sistema São Geraldo Service.\n\n'
        'Abra o link abaixo (válido por 2 horas):\n'
        f'{link}\n\n'
        'Se você não pediu essa alteração, ignore este e-mail.\n\n'
        'São Geraldo Service\n'
    )
    html = f'''
    <p>Olá, {nome}.</p>
    <p>Recebemos um pedido para redefinir a senha da sua conta no sistema São Geraldo Service.</p>
    <p><a href="{link}">Clique aqui para redefinir sua senha</a></p>
    <p>O link é válido por 2 horas.</p>
    <p>Se você não pediu essa alteração, ignore este e-mail.</p>
    <p>São Geraldo Service</p>
    '''
    enviar_email(destinatario, ASSUNTO_REDEFINICAO, texto, html)
