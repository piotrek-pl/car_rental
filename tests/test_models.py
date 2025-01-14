
import pytest
from app.models import Car, Customer, Rental, PaymentStatus
from datetime import datetime, timedelta

def test_car_creation(app, db):
    with app.app_context():
        car = Car(make="Toyota", model="Camry", year=2023)
        db.session.add(car)
        db.session.commit()
        assert car.id is not None
        assert car.make == "Toyota"
        assert car.is_available == True

def test_car_availability(app, db):
    with app.app_context():
        car = Car(make="Toyota", model="Camry", year=2023, is_available=True)
        db.session.add(car)
        db.session.commit()
        
        car.is_available = False
        db.session.commit()
        assert not car.is_available

def test_customer_creation(app, db):
    with app.app_context():
        customer = Customer(
            first_name="Jan",
            last_name="Kowalski",
            email="jan@example.com",
            phone="123456789"
        )
        db.session.add(customer)
        db.session.commit()
        assert customer.id is not None
        assert customer.email == "jan@example.com"

def test_rental_creation(app, db):
    with app.app_context():
        car = Car(make="Toyota", model="Camry", year=2023)
        customer = Customer(
            first_name="Jan",
            last_name="Kowalski",
            email="jan@example.com",
            phone="123456789"
        )
        db.session.add(car)
        db.session.add(customer)
        db.session.commit()  # Commit aby uzyskać ID

        rental = Rental(
            car_id=car.id,
            customer_id=customer.id,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=7),
            total_amount=500.00,
            payment_status=PaymentStatus.PENDING
        )
        db.session.add(rental)
        db.session.commit()

        assert rental.id is not None
        assert rental.payment_status == PaymentStatus.PENDING

def test_rental_status_transitions(app, db):
    with app.app_context():
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
        
        rental = Rental(
            car_id=car.id,
            customer_id=customer.id,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=7),
            total_amount=500.00,
            payment_status=PaymentStatus.PENDING,
            payment_id="TEST_PAYMENT_ID"
        )
        
        db.session.add(rental)
        db.session.commit()
        
        rental.payment_status = PaymentStatus.COMPLETED
        db.session.commit()
        assert rental.payment_status == PaymentStatus.COMPLETED
        
        rental.payment_status = PaymentStatus.FAILED
        db.session.commit()
        assert rental.payment_status == PaymentStatus.FAILED
        
        rental.payment_status = PaymentStatus.CANCELLED
        db.session.commit()
        assert rental.payment_status == PaymentStatus.CANCELLED

def test_rental_dates_validation(app, db):
    with app.app_context():
        car = Car(make="Toyota", model="Camry", year=2023)
        customer = Customer(
            first_name="Jan",
            last_name="Kowalski",
            email="jan@example.com",
            phone="123456789"
        )
        db.session.add(car)
        db.session.add(customer)
        db.session.commit()

        start_date = datetime.now()
        end_date = start_date - timedelta(days=1)  # end_date przed start_date

        rental = Rental(
            car_id=car.id,
            customer_id=customer.id,
            start_date=start_date,
            total_amount=500.00,
            payment_status=PaymentStatus.PENDING
        )
        db.session.add(rental)

        with pytest.raises(ValueError):
            rental.end_date = end_date  # To powinno wywołać walidację i błąd
            db.session.commit()

def test_rental_relationships(app, db):
    with app.app_context():
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

        rental1 = Rental(
            car_id=car.id,
            customer_id=customer.id,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=7),
            total_amount=500.00,
            payment_status=PaymentStatus.PENDING
        )
        
        rental2 = Rental(
            car_id=car.id,
            customer_id=customer.id,
            start_date=datetime.now() + timedelta(days=8),
            end_date=datetime.now() + timedelta(days=15),
            total_amount=600.00,
            payment_status=PaymentStatus.PENDING
        )
        
        db.session.add(rental1)
        db.session.add(rental2)
        db.session.commit()

        assert len(car.rentals) == 2
        assert len(customer.rentals) == 2
        assert car.rentals[0].total_amount == 500.00
        assert car.rentals[1].total_amount == 600.00
