from app import create_app, ensure_pesagem_schema, ensure_logistica_schema
from models import db
from whatsapp_pesagem import start_background

app = create_app()
application = app
with app.app_context():
    try:
        db.create_all()
    except Exception as extra:
        print(f"Aviso create_all: {extra}")
    try:
        ensure_pesagem_schema()
    except Exception as extra:
        print(f"Aviso schema pesagem: {extra}")
    try:
        ensure_logistica_schema()
    except Exception as extra:
        print(f"Aviso schema logistica: {extra}")
    try:
        from app import ensure_whatsapp_chamado_schema, ensure_tecnicos_schema
        ensure_whatsapp_chamado_schema()
        ensure_tecnicos_schema()
    except Exception as extra:
        print(f"Aviso schema whatsapp/tecnicos: {extra}")
    try:
        from nutricao_tenant import ensure_nutricao_cliente_schema
        ensure_nutricao_cliente_schema()
    except Exception as extra:
        print(f"Aviso schema nutricao: {extra}")
    try:
        from nutricao_service import seed_nutricao
        seed_nutricao()
    except Exception as extra:
        print(f"Aviso seed nutricao: {extra}")
    try:
        from logistica_service import seed_logistica
        seed_logistica()
    except Exception as extra:
        print(f"Aviso seed logistica: {extra}")
    try:
        from permissions_sistemas import garantir_acesso_master
        garantir_acesso_master()
    except Exception as extra:
        print(f"Aviso acesso master: {extra}")
start_background(app)
try:
    from equipamento_service import start_preventiva_background
    start_preventiva_background(app)
except Exception as extra:
    print(f"Aviso ao iniciar preventiva de equipamentos: {extra}")
