from app import create_app, ensure_pesagem_schema, ensure_equipamentos_schema
from db_config import forcar_coluna_equipamento
from whatsapp_pesagem import start_background

app = create_app()
application = app
with app.app_context():
    forcar_coluna_equipamento()
    ensure_pesagem_schema()
    ensure_equipamentos_schema()
start_background(app)
