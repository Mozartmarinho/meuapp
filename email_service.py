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
