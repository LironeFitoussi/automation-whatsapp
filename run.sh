#!/bin/bash

# Update package list and install necessary system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip libnss3 xvfb unzip

# Install Python dependencies from requirements.txt
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Ensure WebDriver dependencies are available
echo "Setting up WebDriver Manager and ChromeDriver..."
pip3 install webdriver-manager

# Check if Google Chrome is installed, and install it if not
if ! command -v google-chrome &> /dev/null
then
    echo "Google Chrome not found. Installing..."
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt install ./google-chrome-stable_current_amd64.deb -y
    rm google-chrome-stable_current_amd64.deb
else
    echo "Google Chrome is already installed."
fi

# Export Flask environment variables
export FLASK_APP=app.py
export FLASK_ENV=development

# Run the Flask application
echo "Starting Flask server..."
python3 -m flask run --host=0.0.0.0 --port=5000
