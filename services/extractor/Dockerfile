FROM python:3.12-slim
WORKDIR /srv
# Tesseract (fallback engine) with Arabic; libgomp/libgl for PaddleOCR and OpenCV.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-ara libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY contracts /contracts
RUN pip install --no-cache-dir /contracts
COPY services/extractor/requirements.txt services/extractor/requirements-ocr.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ocr.txt
COPY ai_core ./ai_core
COPY prompts ./prompts
COPY services/extractor/app ./app
ENV PROMPTS_DIR=/srv/prompts OCR_ENGINE=paddleocr
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
