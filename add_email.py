import re

# Read the file
with open('routes_updated.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the novo_chamado function and add email sending
pattern = r'(        db\.session\.commit\(\)\s*flash\('Chamado criado com sucesso!', 'success'\))'
replacement = '''        db.session.commit()

        # Enviar email para o responsável do cliente
        cliente_obj = Cliente.query.get(chamado.cliente_id)
        if cliente_obj and cliente_obj.email_responsavel:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                config = SistemaConfig.query.first()
                if config and config.smtp_server and config.email_from:
                    msg = MIMEMultipart()
                    msg['From'] = config.email_from
                    msg['To'] = cliente_obj.email_responsavel
                    msg['Subject'] = f"{config.email_subject_prefix} Novo Chamado Criado"

                    corpo = f"""
Olá,

Um novo chamado foi aberto no sistema São Geraldo Service.

Cliente: {cliente_obj.nome}
Número do Chamado: {chamado.numero_chamado}
Data e Hora: {chamado.data_criacao.strftime('%d/%m/%Y %H:%M:%S')}
Status: {chamado.status}

Atenciosamente,
Sistema São Geraldo Service
"""

                    msg.attach(MIMEText(corpo, 'plain'))

                    server = smtplib.SMTP(config.smtp_server, config.smtp_port)
                    server.starttls()
                    server.login(config.smtp_username, config.smtp_password)
                    text = msg.as_string()
                    server.sendmail(config.email_from, cliente_obj.email_responsavel, text)
                    server.quit()
            except Exception as e:
                print(f"Erro ao enviar email: {e}")

        flash('Chamado criado com sucesso!', 'success')'''

# Replace
new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Write back
with open('routes_updated.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Email functionality added successfully')
