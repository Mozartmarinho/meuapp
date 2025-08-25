from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from models_updated import db
from routes_updated import main
import os

def create_app():
    app = Flask(__name__)
    
    # Configurações
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua-chave-secreta-aqui')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///saogeraldo.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Inicializar extensões
    db.init_app(app)
    
    # Registrar blueprints
    app.register_blueprint(main)
    
    # Adicionar contexto global para templates
    @app.context_processor
    def inject_user():
        return dict(current_user=session.get('user_name'))
    
    return app

# Criar aplicação
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
