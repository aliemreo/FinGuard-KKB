# 1. Baz İmaj 
FROM ozcanal22/my-paddleocr-normal:v1
# 2. User
USER root

# 3. Çalışma Dizini
WORKDIR /workspace

# 4. Sistem Kütüphaneleri (Tesseract, Poppler, OpenCV, Postgres Driver, wkhtmltopdf)
# "rm -rf" kısmı imajı temiz tutar.
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-tur \
    wkhtmltopdf \
    libxrender1 \
    libfontconfig1 \
    libxext6 \
    libgl1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Python Kütüphanelerini Kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Container sürekli açık kalsın diye bash başlatıyoruz

CMD ["/bin/bash"]
