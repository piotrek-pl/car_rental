# Użyj oficjalnego obrazu Pythona jako bazowego
FROM python:3.11-slim

# Ustaw zmienną środowiskową, aby uniknąć buforowania wyjścia
ENV PYTHONUNBUFFERED=1

# Dodaj serwery DNS Google
#RUN echo "nameserver 8.8.8.8" > /etc/resolv.conf && \
#    echo "nameserver 8.8.4.4" >> /etc/resolv.conf

# Ustaw katalog roboczy
WORKDIR /app

# Skopiuj plik requirements.txt
COPY requirements.txt .

# Instalacja pip i zależności z określonym źródłem
RUN pip install --upgrade pip -i https://pypi.org/simple && \
    pip install -r requirements.txt -i https://pypi.org/simple && \
    pip install email-validator -i https://pypi.org/simple

# Skopiuj resztę kodu aplikacji
COPY . .

# Expose port 5000
EXPOSE 5000

# Komenda uruchamiająca aplikację
CMD ["flask", "run", "--host=0.0.0.0"]
