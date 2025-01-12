from flask import Flask
import paypalrestsdk
from .models import db
from .routes import routes_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config.Config')  # Dodano 'app.' przed config

    # Inicjalizacja bazy danych
    db.init_app(app)

    # Konfiguracja PayPal SDK
    paypalrestsdk.configure({
        "mode": app.config['PAYPAL_MODE'],
        "client_id": app.config['PAYPAL_CLIENT_ID'],
        "client_secret": app.config['PAYPAL_CLIENT_SECRET']
    })

    # Rejestracja blueprinta
    app.register_blueprint(routes_bp)

    return app
