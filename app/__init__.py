from flask import Flask
import paypalrestsdk
import logging
from .models import db
from .routes import routes_bp

# Konfiguracja globalnego loggera
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config.Config')
    app.config['DEBUG'] = True  # Włącz tryb debug
    app.config['JSON_AS_ASCII'] = False

    db.init_app(app)
    
    logger.info("Inicjalizacja aplikacji...")  # Log
    logger.info(f"URI bazy danych: {app.config['SQLALCHEMY_DATABASE_URI']}")  # Log

    with app.app_context():
        try:
            logger.info("Tworzenie tabel bazy danych...")  # Log
            db.create_all()
            logger.info("Tabele utworzone pomyślnie!")  # Log
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia tabel: {str(e)}")  # Log

    app.register_blueprint(routes_bp)

    return app
