#!/bin/bash

# Update package list and install necessary system dependencies
echo "Installing system dependencies..."
sudo yum update -y
sudo yum install -y python3 python3-pip nss xorg-x11-server-Xvfb unzip wget

# Remove any existing pip installations
echo "Removing existing pip installations..."
sudo pip3 uninstall -y pip
sudo rm -rf /usr/local/lib/python3.6/site-packages/pip*

# Install pip
echo "Installing pip..."
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py
rm get-pip.py

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
    rm google-chrome-stable_current_x86_64.rpm
else
    echo "Google Chrome is already installed."
fi

# Export Flask environment variables
export FLASK_APP=app.py
export FLASK_ENV=development

# Run the Flask application
echo "Starting Flask server..."
python3 -m flask run --host=0.0.0.0 --port=5000
