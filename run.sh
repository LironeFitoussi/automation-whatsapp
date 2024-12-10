#!/bin/bash

# Update package list and install necessary system dependencies
echo "Installing system dependencies..."
sudo yum update -y
sudo yum install -y python3 python3-pip nss xorg-x11-server-Xvfb unzip wget

# Remove all existing pip packages
echo "Removing all existing pip packages..."
pip3 freeze > installed_packages.txt
pip3 uninstall -y -r installed_packages.txt
rm -f installed_packages.txt

# Upgrade pip to the latest version
echo "Upgrading pip..."
pip3 install --upgrade pip

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
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
    sudo yum install -y ./google-chrome-stable_current_x86_64.rpm
    rm -f google-chrome-stable_current_x86_64.rpm
else
    echo "Google Chrome is already installed."
fi

# Export Flask environment variables
export FLASK_APP=app.py
export FLASK_ENV=development

# Run the Flask application
echo "Starting Flask server..."
python3 -m flask run --host=0.0.0.0 --port=5000
