# In Dockerfile

# Start with an official, lightweight Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the file with all your Python dependencies
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your entire application code into the container
COPY . .

# Tell Docker that the app will listen on port 5000
EXPOSE 5000

# The command to run your app using the Gunicorn server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]