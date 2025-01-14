from flask import Blueprint, request, jsonify, url_for, redirect, abort
import paypalrestsdk
from datetime import datetime
import logging
from functools import wraps
from .models import Car, Customer, Rental, PaymentStatus, db
from sqlalchemy.exc import SQLAlchemyError
from .messaging import send_to_queue
import json 

# Konfiguracja loggera
logger = logging.getLogger(__name__)

routes_bp = Blueprint('routes', __name__)

def handle_transaction(f):
    """Decorator do obsługi transakcji bazy danych"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            db.session.commit()
            return result
        except SQLAlchemyError as e:
            db.session.rollback()
            response = jsonify({
                "error": "Blad bazy danych",
                "details": str(e)
            })
            response.headers["Content-Type"] = "application/json; charset=utf-8"
            return response, 500
        except Exception as e:
            db.session.rollback()
            response = jsonify({
                "error": "Nieoczekiwany blad",
                "details": str(e)
            })
            response.headers["Content-Type"] = "application/json; charset=utf-8"
            return response, 500
    return decorated_function

@routes_bp.route('/test', methods=['GET'])
def test():
    """Endpoint testowy"""
    return jsonify({"message": "Blueprint dziala poprawnie!"})

@routes_bp.route('/rentals/create', methods=['POST'])
@handle_transaction
def create_rental_with_payment():
    """Tworzenie rezerwacji z płatnością PayPal"""
    try:
        data = request.json
        logger.info(f"Otrzymano dane rezerwacji: {data}")  # Dodatkowe logowanie
        
        # Sprawdzenie samochodu
        car = db.session.get(Car, data['car_id'])
        if not car:
            return jsonify({"error": "Samochod nie znaleziony"}), 404
        logger.info(f"Znaleziono samochod: {car}")

        # Sprawdzenie dostępności samochodu
        if not car.is_available:
            logger.warning(f"Samochod {car.id} jest niedostepny")
            return jsonify({"error": "Samochod nie jest dostepny"}), 400

        # Tworzenie płatności PayPal
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "transactions": [{
                "amount": {
                    "total": str(data['total_amount']),
                    "currency": "USD"
                },
                "description": f"Wynajem samochodu: {car.make} {car.model}"
            }],
            "redirect_urls": {
                "return_url": url_for('routes.complete_rental', _external=True),
                "cancel_url": url_for('routes.cancel_rental', _external=True)
            }
        })

        # Próba utworzenia płatności
        if not payment.create():
            logger.error(f"Nie udalo sie utworzyc patnosci: {payment.error}")
            return jsonify({"error": payment.error}), 400

        logger.info(f"Utworzono płatnosc: {payment.id}")

        # Oznaczenie samochodu jako niedostępnego
        car.is_available = False
        db.session.add(car)

        # Tworzenie rekordu rezerwacji
        customer = db.session.get(Customer, data['customer_id'])
        if not customer:
            return jsonify({"error": "Klient nie znaleziony"}), 404

        rental = Rental(
            car_id=data['car_id'],
            customer_id=data['customer_id'],
            start_date=datetime.fromisoformat(data['start_date']),
            end_date=datetime.fromisoformat(data['end_date']),
            total_amount=float(data['total_amount']),
            payment_id=payment.id,
            payment_status=PaymentStatus.PENDING
        )
        
        db.session.add(rental)
        db.session.flush()
        logger.info(f"Utworzono rezerwacje: {rental.id}")

        # Przygotowanie powiadomienia
        notification = {
            "type": "new_rental",
            "customer_email": customer.email,
            "customer_name": f"{customer.first_name} {customer.last_name}",
            "customer_phone": customer.phone,
            "car_id": car.id,
            "car_details": f"{car.make} {car.model}",
            "car_year": car.year,
            "start_date": data['start_date'],
            "end_date": data['end_date'],
            "total_amount": str(data['total_amount']),
            "created_at": datetime.utcnow().isoformat(),
            "rental_id": rental.id
        }
        
        # Wysłanie powiadomienia do kolejki
        logger.info(f"Proba wysłania powiadomienia: {notification}")
        try:
            send_result = send_to_queue(notification)
            logger.info(f"Wyslanie powiadomienia zakonczone: {send_result}")
        except Exception as e:
            logger.error(f"Blad podczas wysyłania powiadomienia: {e}")
        
        # Pobranie adresu przekierowania
        redirect_url = next(link.href for link in payment.links if link.method == "REDIRECT")
        
        return jsonify({
            "message": "Rezerwacja utworzona pomyslnie",
            "rental_id": rental.id,
            "redirect_url": redirect_url,
            "payment_id": payment.id
        }), 201

    except Exception as e:
        logger.error(f"Blad podczas tworzenia rezerwacji: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@routes_bp.route('/rentals/complete', methods=['GET'])
@handle_transaction
def complete_rental():
    """Zakończenie rezerwacji po udanej płatności"""
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')
    
    try:
        # Znajdź rezerwację po ID płatności
        rental = Rental.query.filter_by(payment_id=payment_id).first()
        if not rental:
            abort(404) 
        
        # Wykonaj płatność PayPal
        payment = paypalrestsdk.Payment.find(payment_id)
        if not payment.execute({"payer_id": payer_id}):
            # Jeśli płatność się nie powiodła
            rental.payment_status = PaymentStatus.FAILED
            car = db.session.get(Car, rental.car_id)
            car.is_available = True

            # Powiadomienie o nieudanej płatności
            customer = db.session.get(Customer, rental.customer_id)
            notification = {
                "type": "payment_failed",
                "rental_id": rental.id,
                "customer_email": customer.email,
                "customer_name": f"{customer.first_name} {customer.last_name}"
            }
            send_to_queue(notification)
            
            return jsonify({"error": "Wykonanie platnosci nie powiodlo sie"}), 400

        # Oznacz rezerwację jako opłaconą
        rental.payment_status = PaymentStatus.COMPLETED
        
        # Powiadomienie o udanej płatności
        customer = db.session.get(Customer, rental.customer_id)
        notification = {
            "type": "payment_completed",
            "rental_id": rental.id,
            "customer_email": customer.email,
            "customer_name": f"{customer.first_name} {customer.last_name}"
        }
        send_to_queue(notification)
        
        return jsonify({
            "message": "Platnosc zakonczona sukcesem",
            "rental_id": rental.id,
            "status": "COMPLETED"
        })

    except Exception as e:
        logger.error(f"Blad w complete_rental: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@routes_bp.route('/rentals/<int:rental_id>/cancel', methods=['POST'])
@handle_transaction
def cancel_rental_by_id(rental_id):
    """Anulowanie rezerwacji o konkretnym ID"""
    try:
        rental = db.session.get(Rental, rental_id)
        if not rental:
            abort(404)
        
        # Sprawdź status rezerwacji
        if rental.payment_status == PaymentStatus.CANCELLED:
            return jsonify({
                "message": "Rezerwacja jest juz anulowana",
                "rental_id": rental.id,
                "status": rental.payment_status.value
            }), 400
        
        # Sprawdź czy rezerwacja nie jest już zakończona
        if rental.payment_status == PaymentStatus.COMPLETED:
            return jsonify({
                "message": "Nie mozna anulowac zakonczonej rezerwacji",
                "rental_id": rental.id,
                "status": rental.payment_status.value
            }), 400
            
        # Zmień status rezerwacji
        rental.payment_status = PaymentStatus.CANCELLED
        
        # Przywróć dostępność samochodu
        car = db.session.get(Car, rental.car_id)
        if car:
            car.is_available = True

        # Powiadomienie o anulowaniu rezerwacji
        customer = db.session.get(Customer, rental.customer_id)
        notification = {
            "type": "rental_cancelled",
            "rental_id": rental.id,
            "customer_email": customer.email,
            "customer_name": f"{customer.first_name} {customer.last_name}"
        }
        send_to_queue(notification)
            
        return jsonify({
            "message": "Rezerwacja anulowana pomyslnie",
            "rental_id": rental.id,
            "status": "CANCELLED"
        })
    except Exception as e:
        logger.error(f"Blad podczas anulowania rezerwacji: {str(e)}")
        return jsonify({"error": str(e)}), 500

@routes_bp.route('/rentals/cancel', methods=['GET'])
@handle_transaction
def cancel_rental():
    """Anulowanie rezerwacji z poziomu płatności"""
    token = request.args.get('token')  # Token from PayPal
    payment_id = request.args.get('paymentId')  # PayPal Payment ID
    
    logger.info(f"Zadanie anulowania - token: {token}, payment_id: {payment_id}")
    
    try:
        # Spróbuj znaleźć rezerwację po payment_id
        rental = None
        if token:
            rental = Rental.query.filter_by(payment_id=token).first()
        if not rental and payment_id:
            rental = Rental.query.filter_by(payment_id=payment_id).first()
            
        if not rental:
            abort(404) 
        # Sprawdź status rezerwacji
        if rental.payment_status == PaymentStatus.CANCELLED:
            return jsonify({
                "message": "Rezerwacja jest juz anulowana",
                "rental_id": rental.id,
                "status": rental.payment_status.value
            }), 400
        
        # Sprawdź czy rezerwacja nie jest już zakończona
        if rental.payment_status == PaymentStatus.COMPLETED:
            return jsonify({
                "message": "Nie można anulowac zakonczonej rezerwacji",
                "rental_id": rental.id,
                "status": rental.payment_status.value
            }), 400
            
        # Zmień status rezerwacji
        rental.payment_status = PaymentStatus.CANCELLED
        
        # Przywróć dostępność samochodu
        car = db.session.get(Car, rental.car_id)
        if car:
            car.is_available = True
            logger.info(f"Samochod {car.id} oznaczony jako dostepny")

        # Powiadomienie o anulowaniu rezerwacji
        customer = db.session.get(Customer, rental.customer_id)
        notification = {
            "type": "rental_cancelled",
            "rental_id": rental.id,
            "customer_email": customer.email,
            "customer_name": f"{customer.first_name} {customer.last_name}"
        }
        send_to_queue(notification)
        
        return jsonify({
            "message": "Rezerwacja anulowana pomyslnie",
            "rental_id": rental.id,
            "status": "CANCELLED"
        })

    except Exception as e:
        logger.error(f"Blad w cancel_rental: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@routes_bp.route('/cars', methods=['GET'])
def get_cars():
    """Pobieranie listy wszystkich samochodów"""
    cars = Car.query.all()
    return jsonify([{
        "id": car.id, 
        "make": car.make, 
        "model": car.model, 
        "year": car.year,
        "is_available": car.is_available
    } for car in cars])

@routes_bp.route('/cars', methods=['POST'])
@handle_transaction
def add_car():
    """Dodawanie nowego samochodu"""
    data = request.json
    car = Car(
        make=data['make'], 
        model=data['model'], 
        year=data['year'],
        is_available=data.get('is_available', True)
    )
    db.session.add(car)
    return jsonify({
        "message": "Samochod dodany pomyslnie!",
        "car": {
            "id": car.id,
            "make": car.make,
            "model": car.model,
            "year": car.year,
            "is_available": car.is_available
        }
    }), 201

@routes_bp.route('/cars/<int:car_id>', methods=['DELETE'])
@handle_transaction
def delete_car(car_id):
    """Usuwanie samochodu"""
    car = Car.query.get_or_404(car_id)
    db.session.delete(car)
    return jsonify({"message": "Samochod usuniety pomyslnie!"})

@routes_bp.route('/customers', methods=['GET'])
def get_customers():
    """Pobieranie listy wszystkich klientów"""
    customers = Customer.query.all()
    return jsonify([{
        "id": customer.id,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone
    } for customer in customers])

@routes_bp.route('/customers', methods=['POST'])
@handle_transaction
def add_customer():
    """Dodawanie nowego klienta"""
    data = request.json
    customer = Customer(
        first_name=data['first_name'],
        last_name=data['last_name'],
        email=data['email'],
        phone=data['phone']
    )
    db.session.add(customer)
    return jsonify({
        "message": "Klient dodany pomyslnie!",
        "customer": {
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone
        }
    }), 201

@routes_bp.route('/rentals/<int:rental_id>/status', methods=['GET'])
def get_rental_status(rental_id):
    """Sprawdzenie statusu rezerwacji"""
    try:
        rental = db.session.get(Rental, rental_id)
        if not rental:
            abort(404) 
        return jsonify({
            "rental_id": rental.id,
            "payment_id": rental.payment_id,
            "status": rental.payment_status.value,
            "car_id": rental.car_id
        })
    except Exception as e:
        logger.error(f"Blad podczas pobierania statusu rezerwacji: {str(e)}")
        return jsonify({"error": str(e)}), 500

@routes_bp.route('/rentals', methods=['GET'])
def get_rentals():
    """Pobieranie listy wszystkich rezerwacji"""
    rentals = Rental.query.all()
    return jsonify([{
        "id": rental.id,
        "car_id": rental.car_id,
        "customer_id": rental.customer_id,
        "start_date": rental.start_date.isoformat(),
        "end_date": rental.end_date.isoformat(),
        "total_amount": rental.total_amount,
        "payment_status": rental.payment_status.value,
        "payment_id": rental.payment_id
    } for rental in rentals])
