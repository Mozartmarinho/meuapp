class Config:
    # Configurações básicas
    SECRET_KEY = 'sua_chave_secreta_aqui'
    
    # Configurações do SQLite para demo
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:Br@sil2016@127.0.0.1:3306/meuappdb'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configurações adicionais
    DEBUG = True
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
