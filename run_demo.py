from flask import Flask
from config_demo import Config
from models import db
from routes import main

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Inicializar extensões
    db.init_app(app)
    
    # Registrar blueprints
    app.register_blueprint(main)
    
    # Criar tabelas do banco de dados
    with app.app_context():
        try:
            db.create_all()
            print("Tabelas criadas com sucesso!")
        except Exception as e:
            print(f"Erro ao criar tabelas: {e}")
    
    return app

if __name__ == '__main__':
    app = create_app()
    print("\n=== Sistema São Geraldo - Versão Demo ===")
    print("Acesse http://localhost no navegador")
    print("Pressione CTRL+C para encerrar\n")
    app.run(debug=True, host='0.0.0.0', port=80)
