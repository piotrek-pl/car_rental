import pytest
from app.models import Car, Customer, Rental, PaymentStatus
from datetime import datetime, timedelta

def test_car_creation(app, db):
    car = Car(make="Toyota", model="Camry", year=2023)
    db.session.add(car)
    db.session.commit()
    assert car.id is not None
    assert car.make == "Toyota"
    assert car.is_available == True

def test_customer_creation(app, db):
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
