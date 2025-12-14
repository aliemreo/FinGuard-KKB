1 - Bu repo'nun bulunduğu klasörde .env dosyası açın.

Örnek .env dosyası:
<<<<<<<<<<<<<<
# .env dosyası
# API Anahtarların
API_KEY=sk-_qJRJGm4TvoimjrlQzaWHOAZ7KvIwaYDp3kORNWaSt4HMXKP
BASE_URL=https://mia.csp.kloudeks.com/v1

# Veritabanı Ayarları
DB_HOST=db
DB_NAME=ihale_db
DB_USER=myusername
DB_PASSWORD=mypassword
>>>>>>>>>>>>>>>

2- Bu repo'nun bulunduğu klasörde terminali açın, 

docker-compose up -d --build

komutunu yapıştırın.

3- Kurulum bittiğinde bu kodu yapıştırın

docker exec -it ihale_container_final bash
python pipeline.py --mode all --start-date 2024-07-20 --end-date 2024-07-20




