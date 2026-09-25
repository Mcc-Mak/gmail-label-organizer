FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY organizer.py .
RUN useradd -m appuser
USER appuser
ENTRYPOINT ["python", "organizer.py"]
