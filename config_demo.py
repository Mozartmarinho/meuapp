from db_config import SQLALCHEMY_DATABASE_URI as MYSQL_URI


class Config:
    SECRET_KEY = 'sua_chave_secreta_aqui'

    # MySQL local (mesmo banco do restante do projeto)
    SQLALCHEMY_DATABASE_URI = MYSQL_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEBUG = True
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
