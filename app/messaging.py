import pika
import json

def send_to_queue(message):
    try:
        # Połączenie z RabbitMQ
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host='rabbitmq')  # nazwa serwisu z docker-compose
        )
        channel = connection.channel()
        
        # Deklaracja kolejki
        channel.queue_declare(queue='rental_notifications')
        
        # Wysłanie wiadomości
        channel.basic_publish(
            exchange='',
            routing_key='rental_notifications',
            body=json.dumps(message)
        )
        
        connection.close()
        print("Wiadomość wysłana do kolejki")
        return True
        
    except Exception as e:
        print(f"Błąd podczas wysyłania wiadomości: {str(e)}")
        return False
