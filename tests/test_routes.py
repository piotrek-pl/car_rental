import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.models import Car, Customer, Rental, PaymentStatus

def test_create_rental_with_payment(client, db):
    with patch('app.routes.send_to_queue') as mock_send_queue:
        with client.application.app_context():
            car = Car(make="Toyota", model="Camry", year=2023, is_available=True)
            customer = Customer(
                first_name="Jan",
                last_name="Kowalski",
                email="jan@example.com",
                phone="123456789"
            )
            db.session.add(car)
            db.session.add(customer)
            db.session.commit()

            data = {
                'car_id': car.id,
                'customer_id': customer.id,
                'start_date': '2024-01-15T10:00:00',
                'end_date': '2024-01-20T10:00:00',
                'total_amount': 500.00
            }

            with patch('paypalrestsdk.Payment') as mock_paypal_payment:
                payment = mock_paypal_payment.return_value
                payment.id = "TEST_PAYMENT_ID"
                payment.create.return_value = True
                payment.links = [
                    type('Link', (), {'method': 'REDIRECT', 'href': 'http://test-redirect.com'})()
                ]

                response = client.post('/rentals/create', 
                                     json=data,
                                     content_type='application/json')

                assert response.status_code == 201
                assert 'rental_id' in response.json
                assert 'redirect_url' in response.json
                assert response.json['redirect_url'] == "http://test-redirect.com"

                car = db.session.get(Car, car.id)
                assert not car.is_available

                mock_send_queue.assert_called_once()
                notification_data = mock_send_queue.call_args[0][0]
                assert notification_data['type'] == 'new_rental'
                assert notification_data['customer_email'] == 'jan@example.com'

def test_cancel_rental(client, db):
    with patch('app.routes.send_to_queue') as mock_send_queue:
        with client.application.app_context():
            car = Car(make="Toyota", model="Camry", year=2023, is_available=False)
            customer = Customer(
                first_name="Jan",
                last_name="Kowalski",
                email="jan@example.com",
                phone="123456789"
            )
            db.session.add(car)
            db.session.add(customer)
            db.session.commit()

            rental = Rental(
                car_id=car.id,
                customer_id=customer.id,
                start_date=datetime.now(),
                end_date=datetime.now() + timedelta(days=7),
                total_amount=500.00,
                payment_id="TEST_PAYMENT_ID",
                payment_status=PaymentStatus.PENDING
            )
            db.session.add(rental)
            db.session.commit()

            response = client.post(f'/rentals/{rental.id}/cancel')
            assert response.status_code == 200
            assert response.json['status'] == 'CANCELLED'

            car = db.session.get(Car, car.id)
            assert car.is_available

            mock_send_queue.assert_called_once()
            notification_data = mock_send_queue.call_args[0][0]
            assert notification_data['type'] == 'rental_cancelled'

def test_complete_rental_payment(client, db):
    with patch('app.routes.send_to_queue') as mock_send_queue:
        with client.application.app_context():
            car = Car(make="Toyota", model="Camry", year=2023, is_available=False)
            customer = Customer(
                first_name="Jan",
                last_name="Kowalski",
                email="jan@example.com",
                phone="123456789"
            )
            db.session.add(car)
            db.session.add(customer)
            db.session.commit()

            rental = Rental(
                car_id=car.id,
                customer_id=customer.id,
                start_date=datetime.now(),
                end_date=datetime.now() + timedelta(days=7),
                total_amount=500.00,
                payment_id="TEST_PAYMENT_ID",
                payment_status=PaymentStatus.PENDING
            )
            db.session.add(rental)
            db.session.commit()

            with patch('paypalrestsdk.Payment.find') as mock_find:
                payment = MagicMock()
                payment.execute.return_value = True
                mock_find.return_value = payment

                response = client.get('/rentals/complete?paymentId=TEST_PAYMENT_ID&PayerID=TEST_PAYER_ID')

                assert response.status_code == 200
                assert response.json['status'] == 'COMPLETED'

                rental = db.session.get(Rental, rental.id)
                assert rental.payment_status == PaymentStatus.COMPLETED

                mock_send_queue.assert_called_once()
                notification_data = mock_send_queue.call_args[0][0]
                assert notification_data['type'] == 'payment_completed'

def test_payment_failure(client, db):
    with patch('app.routes.send_to_queue') as mock_send_queue:
        with client.application.app_context():
            car = Car(make="Toyota", model="Camry", year=2023, is_available=False)
            customer = Customer(
                first_name="Jan",
                last_name="Kowalski",
                email="jan@example.com",
                phone="123456789"
            )
            db.session.add(car)
            db.session.add(customer)
            db.session.commit()

            rental = Rental(
                car_id=car.id,
                customer_id=customer.id,
                start_date=datetime.now(),
                end_date=datetime.now() + timedelta(days=7),
                total_amount=500.00,
                payment_id="TEST_PAYMENT_ID",
                payment_status=PaymentStatus.PENDING
            )
            db.session.add(rental)
            db.session.commit()

            with patch('paypalrestsdk.Payment.find') as mock_find:
                payment = MagicMock()
                payment.execute.return_value = False
                mock_find.return_value = payment

                response = client.get('/rentals/complete?paymentId=TEST_PAYMENT_ID&PayerID=TEST_PAYER_ID')

                assert response.status_code == 400

                rental = db.session.get(Rental, rental.id)
                assert rental.payment_status == PaymentStatus.FAILED

                car = db.session.get(Car, car.id)
                assert car.is_available

                mock_send_queue.assert_called_once()
                notification_data = mock_send_queue.call_args[0][0]
                assert notification_data['type'] == 'payment_failed'
