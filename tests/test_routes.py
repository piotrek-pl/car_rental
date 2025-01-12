from app.models import Car, Customer, Rental, PaymentStatus
from datetime import datetime, timedelta

def test_create_car(client):
    data = {
        'make': 'Toyota',
        'model': 'Camry',
        'year': 2023
    }
    response = client.post('/cars', json=data)
    print("Response data:", response.json)  # Debug print
    assert response.status_code == 201
    assert response.json['car']['make'] == 'Toyota'

def test_get_cars(client, db):
    # Dodaj testowy samochód
    car = Car(make="Toyota", model="Camry", year=2023)
    db.session.add(car)
    db.session.commit()

    response = client.get('/cars')
    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]['make'] == 'Toyota'

def test_create_rental_with_unavailable_car(client, db):
    # Dodaj samochód oznaczony jako niedostępny
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

    response = client.post('/rentals/create', json={
        'car_id': car.id,
        'customer_id': customer.id,
        'start_date': '2024-01-15T10:00:00',
        'end_date': '2024-01-20T10:00:00',
        'total_amount': 500.00
    })
    assert response.status_code == 400
    assert 'not available' in response.json['error']
