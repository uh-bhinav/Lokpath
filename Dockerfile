# In Dockerfile

# --- Stage 1: The Builder ---
# This stage installs all dependencies
FROM python:3.10-slim AS builder

WORKDIR /app

COPY requirements.txt .

# Install dependencies into a temporary directory
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt


# --- Stage 2: The Final Image ---
# This is the lean, final image for production
FROM python:3.10-slim

WORKDIR /app

# Copy only the installed dependencies from the builder stage
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy your application code
COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]