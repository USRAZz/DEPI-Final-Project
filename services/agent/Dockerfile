FROM python:3.12-slim
WORKDIR /srv
COPY contracts /contracts
RUN pip install --no-cache-dir /contracts
COPY services/agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Shared AI code, prompts and policies live at the repo root; copy them next to the app.
COPY ai_core ./ai_core
COPY prompts ./prompts
COPY policies ./policies
COPY services/agent/app ./app
ENV PROMPTS_DIR=/srv/prompts POLICIES_FILE=/srv/policies/payments.yaml
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
