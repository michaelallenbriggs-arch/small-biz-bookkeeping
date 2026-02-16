FROM python:3.11-slim

# Install system dependencies for BOTH Tesseract + OpenCV
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Auto-detect tessdata location and create symlink
RUN if [ -d /usr/share/tesseract-ocr/4.00/tessdata ]; then \
        ln -sf /usr/share/tesseract-ocr/4.00/tessdata /usr/share/tessdata; \
    elif [ -d /usr/share/tesseract-ocr/tessdata ]; then \
        ln -sf /usr/share/tesseract-ocr/tessdata /usr/share/tessdata; \
    fi

ENV TESSDATA_PREFIX=/usr/share/tessdata

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]