# Use Ubuntu 22.04 as the base image. It is a stable choice that has
# all the necessary dependencies in its default repositories.
FROM ubuntu:22.04

# Avoid prompts during apt-get install.
ENV DEBIAN_FRONTEND=noninteractive

# Install all necessary system-level dependencies in a single step.
# This includes Python3, pip, and other libraries required for your application.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    wkhtmltopdf \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libqpdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the environment variable for the wkhtmltopdf executable path.
# On Ubuntu, the path is typically /usr/bin/wkhtmltopdf.
ENV WKHTMLTOPDF_PATH=/usr/bin/wkhtmltopdf

# Set the working directory for your application.
WORKDIR /app

# Copy the requirements file and install Python dependencies.
# This part remains the same to use Docker's layer caching effectively.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# Copy the rest of your application's source code.
COPY . .

# Expose the port your app will listen on.
EXPOSE 8000

# Define the command to run your application.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]


