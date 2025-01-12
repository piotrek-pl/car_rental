from flask import Blueprint, request, jsonify, url_for, redirect
import paypalrestsdk
from datetime import datetime
from functools import wraps
from .models import Car, Customer, Rental, PaymentStatus, db
from sqlalchemy.exc import SQLAlchemyError

routes_bp = Blueprint('routes', __name__)

def handle_transaction(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            db.session.commit()
            return result
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({"error": "Database error", "details": str(e)}), 500
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "Unexpected error", "details": str(e)}), 500
    return decorated_function

@routes_bp.route('/test', methods=['GET'])
def test():
    return jsonify({"message": "Blueprint działa poprawnie!"})

@routes_bp.route('/rentals/create', methods=['POST'])
@handle_transaction
def create_rental_with_payment():
    try:
        data = request.json
        print("Received data:", data)  # Debug log
        
        car = Car.query.get_or_404(data['car_id'])
        print("Found car:", car)  # Debug log
        
        if not car.is_available:
            return jsonify({"error": "Car is not available"}), 400

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
                "description": f"Car Rental: {car.make} {car.model}"
            }],
            "redirect_urls": {
                "return_url": url_for('routes.complete_rental', _external=True),
                "cancel_url": url_for('routes.cancel_rental', _external=True)
            }
        })

        if not payment.create():
            print("Payment creation failed:", payment.error)  # Debug log
            return jsonify({"error": payment.error}), 400

        print("Payment created:", payment.id)  # Debug log

        car.is_available = False
        db.session.add(car)

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
        print("Created rental:", rental.id)  # Debug log
        
        redirect_url = next(link.href for link in payment.links if link.method == "REDIRECT")
        
        return jsonify({
            "message": "Rental created successfully",
            "rental_id": rental.id,
            "redirect_url": redirect_url,
            "payment_id": payment.id  # Dodane dla debugowania
        }), 201

    except Exception as e:
        print("Error occurred:", str(e))  # Debug log
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@routes_bp.route('/rentals/complete', methods=['GET'])
@handle_transaction
def complete_rental():
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')
    
    try:
        rental = Rental.query.filter_by(payment_id=payment_id).first_or_404()
        
        payment = paypalrestsdk.Payment.find(payment_id)
        if not payment.execute({"payer_id": payer_id}):
            rental.payment_status = PaymentStatus.FAILED
            car = Car.query.get(rental.car_id)
            car.is_available = True
            return jsonify({"error": "Payment execution failed"}), 400

        rental.payment_status = PaymentStatus.COMPLETED
        
        return jsonify({
            "message": "Payment completed successfully",
            "rental_id": rental.id,
            "status": "COMPLETED"
        })

    except Exception as e:
        print("Error in complete_rental:", str(e))  # Debug log
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@routes_bp.route('/rentals/<int:rental_id>/cancel', methods=['POST'])
@handle_transaction
def cancel_rental_by_id(rental_id):
    try:
        rental = Rental.query.get_or_404(rental_id)
        
        # Sprawdź czy rezerwacja nie jest już anulowana
        if rental.payment_status == PaymentStatus.CANCELLED:
            return jsonify({
                "message": "Rental is already cancelled",
                "rental_id": rental.id,
                "status": rental.payment_status.value
            }), 400
        
        # Sprawdź czy rezerwacja nie jest już zakończona
        if rental.payment_status == PaymentStatus.COMPLETED:
            return jsonify({
                "message": "Cannot cancel completed rental",
                "rental_id": rental.id,
                "status": rental.payment_status.value
            }), 400
            
        rental.payment_status = PaymentStatus.CANCELLED
        
        car = Car.query.get(rental.car_id)
        if car:
            car.is_available = True
            
        return jsonify({
            "message": "Rental cancelled successfully",
            "rental_id": rental.id,
            "status": "CANCELLED"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@routes_bp.route('/rentals/cancel', methods=['GET'])
@handle_transaction
def cancel_rental():
    token = request.args.get('token')  # Token from PayPal
    payment_id = request.args.get('paymentId')  # PayPal Payment ID
    
    print("Cancellation request - token:", token, "payment_id:", payment_id)  # Debug log
    
    try:
        # Spróbuj znaleźć rezerwację po payment_id
        rental = None
        if token:
            rental = Rental.query.filter_by(payment_id=token).first()
        if not rental and payment_id:
            rental = Rental.query.filter_by(payment_id=payment_id).first()
            
        if not rental:
            return jsonify({"error": "Rental not found"}), 404
            
        # Sprawdź czy rezerwacja nie jest już anulowana
        if rental.payment_status == PaymentStatus.CANCELLED:
            return jsonify({
                "message": "Rental is already cancelled",
                "rental_id": rental.id,
                "status": rental.payment_status.value
            }), 400
        
        # Sprawdź czy rezerwacja nie jest już zakończona
        if rental.payment_status == PaymentStatus.COMPLETED:
            return jsonify({
                "message": "Cannot cancel completed rental",
                "rental_id": rental.id,
                "status": rental.payment_status.value
            }), 400
            
        print("Found rental:", rental.id)  # Debug log
        
        rental.payment_status = PaymentStatus.CANCELLED
        
        car = Car.query.get(rental.car_id)
        if car:
            car.is_available = True
            print(f"Car {car.id} marked as available")  # Debug log
        
        return jsonify({
            "message": "Rental cancelled successfully",
            "rental_id": rental.id,
            "status": "CANCELLED"
        })

    except Exception as e:
        print("Error in cancel_rental:", str(e))  # Debug log
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# Standardowe endpointy dla samochodów
@routes_bp.route('/cars', methods=['GET'])
def get_cars():
    """
    Pobieranie listy wszystkich samochodów.
    """
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
    """
    Dodawanie nowego samochodu.
    """
    data = request.json
    car = Car(
        make=data['make'], 
        model=data['model'], 
        year=data['year'],
        is_available=data.get('is_available', True)
    )
    db.session.add(car)
    return jsonify({
        "message": "Car added successfully!",
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
    """
    Usuwanie samochodu.
    """
    car = Car.query.get_or_404(car_id)
    db.session.delete(car)
    return jsonify({"message": "Car deleted successfully!"})

# Standardowe endpointy dla klientów
@routes_bp.route('/customers', methods=['GET'])
def get_customers():
    """
    Pobieranie listy wszystkich klientów.
    """
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
    """
    Dodawanie nowego klienta.
    """
    data = request.json
    customer = Customer(
        first_name=data['first_name'],
        last_name=data['last_name'],
        email=data['email'],
        phone=data['phone']
    )
    db.session.add(customer)
    return jsonify({
        "message": "Customer added successfully!",
        "customer": {
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone
        }
    }), 201

# Endpoint do sprawdzania statusu
@routes_bp.route('/rentals/<int:rental_id>/status', methods=['GET'])
def get_rental_status(rental_id):
    try:
        rental = Rental.query.get_or_404(rental_id)
        return jsonify({
            "rental_id": rental.id,
            "payment_id": rental.payment_id,
            "status": rental.payment_status.value,
            "car_id": rental.car_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Endpoint do pobierania wszystkich rezerwacji
@routes_bp.route('/rentals', methods=['GET'])
def get_rentals():
    """
    Pobieranie listy wszystkich rezerwacji.
    """
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
