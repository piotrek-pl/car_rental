import pytest
from app import create_app
from app.models import db as _db
from unittest.mock import patch

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
    
    return app

@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()

@pytest.fixture(scope='function')
def client(app):
    return app.test_client()

@pytest.fixture(scope='function')
def mock_rabbitmq():
    with patch('app.messaging.send_to_queue') as mock:
        mock.return_value = True
        yield mock

@pytest.fixture
def mock_paypal_payment():
    with patch('paypalrestsdk.Payment') as mock:
        payment = mock.return_value
        payment.id = "TEST_PAYMENT_ID"
        payment.create.return_value = True
        payment.links = [
            type('Link', (), {'method': 'REDIRECT', 'href': 'http://test-redirect.com'})()
        ]
        yield mock
