FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Verify tessdata exists and set path
RUN ls -la /usr/share/tesseract-ocr/ && \
    if [ -d /usr/share/tesseract-ocr/4.00/tessdata ]; then \
        echo "Found tessdata at 4.00"; \
        export TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata; \
    elif [ -d /usr/share/tesseract-ocr/5/tessdata ]; then \
        echo "Found tessdata at 5"; \
        export TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata; \
    fi

# Try both common paths
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Verify Tesseract works at build time
RUN tesseract --version && \
    tesseract --list-langs

EXPOSE 10000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]