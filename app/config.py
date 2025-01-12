import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://car_rental_user:password@db:5432/car_rental_db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
    PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')
    PAYPAL_MODE = os.getenv('PAYPAL_MODE', 'sandbox')

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'postgresql://car_rental_user:password@db:5432/car_rental_test_db'
    PAYPAL_CLIENT_ID = 'test_client_id'
    PAYPAL_CLIENT_SECRET = 'test_client_secret'
