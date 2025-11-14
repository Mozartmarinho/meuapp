# -*- coding: utf-8 -*-
from flask import Flask, session, request, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from models_updated import db
from routes_updated import main
from logger import setup_logger
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# Fix for Python 2.7 Unicode issues
if sys.version_info[0] == 2:
    reload(sys)
    sys.setdefaultencoding('utf-8')

def create_app():
    app = Flask(__name__)

    # Configurações
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua-chave-secreta-aqui')
    # Atualizar para usar MySQL com senha fornecida
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'mysql+pymysql://root:saogeraldo2025@127.0.0.1:3306/meuappdb')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Inicializar extensões
    db.init_app(app)

    # Configurar SQLite para Unicode se necessário
    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
        @app.before_first_request
        def setup_sqlite():
            db.engine.raw_connection().text_factory = str

    # Configurar logging
    if not app.debug:
        # Criar diretório de logs se não existir
        if not os.path.exists('logs'):
            os.mkdir('logs')

        # Configurar handler para arquivo com rotação
        file_handler = RotatingFileHandler('logs/meuapp.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        # Configurar handler para console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        console_handler.setLevel(logging.INFO)
        app.logger.addHandler(console_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('MeuApp startup')

    # Captura global de exceções
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Log da exceção
        app.logger.error('Exception occurred: %s', str(e), exc_info=True)

        # Tentar salvar no banco se possível
        try:
            from models_updated import ErrorLog
            with app.app_context():
                error_log = ErrorLog(
                    error_type=type(e).__name__,
                    error_message=str(e),
                    traceback=str(e.__traceback__) if hasattr(e, '__traceback__') else '',
                    url=request.url if 'request' in globals() else '',
                    method=request.method if 'request' in globals() else '',
                    user_agent=request.headers.get('User-Agent', '') if 'request' in globals() else '',
                    ip_address=request.remote_addr if 'request' in globals() else ''
                )
                db.session.add(error_log)
                db.session.commit()
        except Exception as log_error:
            app.logger.error('Failed to log error to database: %s', str(log_error))

        # Retornar página de erro genérica
        return render_template('error.html', error=str(e)), 500

    # Registrar blueprints
    app.register_blueprint(main)

    # Set up logger for the app
    logger = setup_logger()

    # Add welcome endpoint with logging
    @app.route('/welcome_app', methods=['GET'])
    def welcome_app():
        logger.info("Request received: {} {}".format(request.method, request.path))
        return jsonify({'message': 'Welcome to the Flask API Service!'})

    # New welcome endpoint with full logging
    @app.route('/welcome', methods=['GET'])
    def welcome():
        logger.info("Request received: {} {} from IP: {} User-Agent: {}".format(request.method, request.path, request.remote_addr, request.headers.get('User-Agent', 'Unknown')))
        return jsonify({'message': 'Welcome to the Flask API Service!'})

    # Adicionar contexto global para templates
    @app.context_processor
    def inject_user():
        # expose current_user and the registered view functions to templates
        try:
            vf = app.view_functions
        except Exception:
            vf = {}
        # helper to safely build urls in templates without raising BuildError
        from flask import url_for
        def safe_url(endpoint, **values):
            try:
                return url_for(endpoint, **values)
            except Exception:
                return '#'
        # also expose a safe 'url_for' to templates so existing templates that call
        # url_for(...) won't raise BuildError; safe_url returns '#' on failure
        try:
            current_user_name = session.get('user_name')
        except RuntimeError:
            # working outside request context
            current_user_name = None

        return dict(current_user=current_user_name, view_functions=vf, safe_url=safe_url, url_for=safe_url)

    return app

# Criar aplicação
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)

