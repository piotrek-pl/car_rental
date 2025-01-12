import pytest
from app import create_app
from app.models import db as _db
import os

@pytest.fixture(scope='session')
def app():
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'postgresql://car_rental_user:password@db:5432/car_rental_test_db',
        'PAYPAL_MODE': 'sandbox',
        'PAYPAL_CLIENT_ID': 'test_client_id',
        'PAYPAL_CLIENT_SECRET': 'test_client_secret'
    })
    
    # Ustaw kontekst aplikacji
    ctx = app.app_context()
    ctx.push()

    yield app

    ctx.pop()

@pytest.fixture(scope='function')
def db(app):
    _db.drop_all()
    _db.create_all()
    yield _db
    _db.session.close()
    _db.drop_all()

@pytest.fixture(scope='function')
def client(app, db):
    return app.test_client()
