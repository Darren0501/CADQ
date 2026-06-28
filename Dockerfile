# Use a lightweight official Python runtime as a parent image
FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    iptables tcpdump \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# Copy your actual CADQ script into the container
COPY cadq_controller.py .

# Run the controller when the container launches
CMD ["python", "-u", "cadq_controller.py"]