# Use an official Python runtime as the base image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the Python script and requirements file to the container
COPY main.py requirements.txt /app/

# Install the required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the HTML file to the container
COPY index.html /app/templates/index.html

# Expose the port for the Flask app
EXPOSE 8080

# Set the entrypoint command to run the Python script
CMD python main.py


