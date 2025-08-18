import sys
import logging
import site

# Ativar ambiente virtual
site.addsitedir('/home/administrador/meuapp/venv/lib/python3.6/site-packages')

# Inserir o app no path
sys.path.insert(0, '/home/administrador/meuapp')

from app import create_app
application = create_app()

logging.basicConfig(stream=sys.stderr)


