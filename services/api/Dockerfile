FROM python:3.12-slim
WORKDIR /srv
COPY contracts /contracts
RUN pip install --no-cache-dir /contracts
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api/app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
