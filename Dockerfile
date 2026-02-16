FROM python:3.11-slim

# Install tesseract from a dedicated repo with proper tessdata
RUN apt-get update && apt-get install -y \
    wget \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Tesseract 5 from Debian testing (has better tessdata packaging)
RUN echo "deb http://deb.debian.org/debian testing main" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y -t testing tesseract-ocr tesseract-ocr-eng libtesseract-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Debug: Show exactly where tessdata is
RUN echo "=== Tesseract Version ===" && \
    tesseract --version && \
    echo "=== Available Languages ===" && \
    tesseract --list-langs && \
    echo "=== Tessdata Location ===" && \
    find /usr -name "tessdata" -type d 2>/dev/null

EXPOSE 10000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]