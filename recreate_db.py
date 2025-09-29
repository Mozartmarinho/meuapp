from app import create_app
from models import db

app = create_app()
with app.app_context():
    db.drop_all()
    db.create_all()
    print("Database schema recreated successfully. Note: All data has been lost.")
