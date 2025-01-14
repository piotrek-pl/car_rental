import pika
import json
import logging
import time
from datetime import datetime
from email.mime.text import MIMEText
import smtplib
import os

# Konfiguracja logowania
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Logger do pliku z historią wiadomości
message_history_logger = logging.getLogger('message_history')
message_history_logger.setLevel(logging.INFO)

# Upewnij się, że katalog /app/logs istnieje
os.makedirs('/app/logs', exist_ok=True)

# Handler do pliku z historią wiadomości
file_handler = logging.FileHandler('/app/logs/message_history.log')
file_formatter = logging.Formatter('%(asctime)s - %(message)s')
file_handler.setFormatter(file_formatter)
message_history_logger.addHandler(file_handler)

class RentalNotificationConsumer:
    def __init__(self, 
                 rabbitmq_host='rabbitmq', 
                 rabbitmq_port=5672,
                 rabbitmq_username='guest',
                 rabbitmq_password='guest',
                 rabbitmq_vhost='/',
                 smtp_host='mailhog', 
                 smtp_port=1025,  # Port dla MailHog
                 sender_email='rentals@carrentalsystem.com',
                 max_retries=10):
        self.rabbitmq_host = rabbitmq_host
        self.rabbitmq_port = rabbitmq_port
        self.rabbitmq_username = rabbitmq_username
        self.rabbitmq_password = rabbitmq_password
        self.rabbitmq_vhost = rabbitmq_vhost
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.max_retries = max_retries

    def send_email(self, recipient, subject, body):
        """Wysyłanie wiadomości e-mail"""
        try:
            logger.info(f"Próba wysłania emaila do {recipient}")
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = recipient

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.send_message(msg)
            logger.info(f"Email wysłany do {recipient}")
        except Exception as e:
            logger.error(f"Błąd wysyłania emaila: {e}")

    def process_notification(self, notification):
        """Przetwarzanie różnych typów powiadomień"""
        try:
            logger.info(f"Przetwarzanie powiadomienia: {notification}")
            
            # Logowanie historii wiadomości
            message_history_logger.info(json.dumps({
                'type': notification.get('type', 'unknown'),
                'timestamp': datetime.utcnow().isoformat(),
                'details': notification
            }))

            if notification['type'] == 'new_rental':
                self.send_email(
                    notification['customer_email'], 
                    'Nowa rezerwacja samochodu', 
                    f"""
Witaj {notification['customer_name']}!

Twoja rezerwacja samochodu została utworzona:
Samochód: {notification.get('car_details', 'Brak szczegółów')}
Termin: {notification.get('start_date', 'Brak daty')} - {notification.get('end_date', 'Brak daty')}
Kwota: {notification.get('total_amount', 'Brak kwoty')} USD

Dziękujemy za skorzystanie z naszej wypożyczalni!
"""
                )

            elif notification['type'] == 'payment_completed':
                self.send_email(
                    notification['customer_email'], 
                    'Płatność za rezerwację zakończona', 
                    f"""
Witaj {notification['customer_name']}!

Twoja płatność za rezerwację została potwierdzona.
Rezerwacja: ID {notification.get('rental_id', 'Brak ID')}

Dziękujemy za terminową płatność!
"""
                )

            elif notification['type'] == 'payment_failed':
                self.send_email(
                    notification['customer_email'], 
                    'Problem z płatnością', 
                    f"""
Witaj {notification['customer_name']}!

Niestety, wystąpił problem z Twoją płatnością za rezerwację.
Rezerwacja: ID {notification.get('rental_id', 'Brak ID')}

Prosimy o kontakt z obsługą klienta.
"""
                )

            elif notification['type'] == 'rental_cancelled':
                self.send_email(
                    notification['customer_email'], 
                    'Anulowanie rezerwacji', 
                    f"""
Witaj {notification['customer_name']}!

Twoja rezerwacja została anulowana.
Rezerwacja: ID {notification.get('rental_id', 'Brak ID')}

W razie pytań prosimy o kontakt.
"""
                )

        except Exception as e:
            logger.error(f"Błąd przetwarzania powiadomienia: {e}")

    def connect_to_rabbitmq(self):
        """Próba połączenia z RabbitMQ z obsługą ponownych prób"""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Próba połączenia z RabbitMQ (próba {attempt + 1})")
                
                # Konfiguracja parametrów połączenia
                credentials = pika.PlainCredentials(
                    self.rabbitmq_username, 
                    self.rabbitmq_password
                )
                connection_params = pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    virtual_host=self.rabbitmq_vhost,
                    credentials=credentials,
                    connection_attempts=3,
                    retry_delay=5
                )

                # Próba połączenia
                connection = pika.BlockingConnection(connection_params)
                logger.info("Połączono z RabbitMQ")
                return connection
            except Exception as e:
                logger.error(f"Błąd połączenia z RabbitMQ: {e}")
                time.sleep(10)  # Poczekaj przed kolejną próbą
        
        raise Exception("Nie udało się połączyć z RabbitMQ po wszystkich próbach")

    def callback(self, ch, method, properties, body):
        """Callback dla RabbitMQ - przetwarzanie wiadomości"""
        try:
            # Dekodowanie wiadomości
            notification = json.loads(body)
            logger.info(f"Otrzymano wiadomość: {notification}")
            
            # Przetwarzanie powiadomienia
            self.process_notification(notification)
            
            # Potwierdzenie przetworzenia wiadomości
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except json.JSONDecodeError as je:
            logger.error(f"Błąd dekodowania JSON: {je}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania wiadomości: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start_consuming(self):
        """Rozpoczęcie nasłuchiwania wiadomości"""
        while True:
            try:
                # Połącz się z RabbitMQ
                connection = self.connect_to_rabbitmq()
                channel = connection.channel()
                
                # Deklaracja kolejki (ta sama, co w messaging.py)
                channel.queue_declare(queue='rental_notifications')
                
                # Ustawienie konsumenta
                channel.basic_consume(
                    queue='rental_notifications', 
                    on_message_callback=self.callback
                )
                
                logger.info(" [*] Oczekiwanie na wiadomości. Aby zakończyć naciśnij CTRL+C")
                channel.start_consuming()
                
            except Exception as e:
                logger.error(f"Błąd w start_consuming: {e}")
                time.sleep(15)  # Poczekaj przed ponowną próbą
            finally:
                # Zamknij połączenie, jeśli istnieje
                if 'connection' in locals():
                    try:
                        connection.close()
                    except:
                        pass

def main():
    consumer = RentalNotificationConsumer()
    consumer.start_consuming()

if __name__ == "__main__":
    main()
