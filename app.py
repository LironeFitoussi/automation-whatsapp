from flask import Flask, request, jsonify
from pymongo import MongoClient
import pandas as pd
import os
import phonenumbers
from phonenumbers import geocoder
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from typing import Optional
from pymongo.errors import DuplicateKeyError
import threading

# Flask App Initialization
app = Flask(__name__)

# MongoDB Connection
client = MongoClient("mongodb+srv://lironefit:FiXSGqvTlq7Zb0EZ@cluster0.e2j9t.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client.get_database("phone_data")
valid_numbers_col = db.valid_numbers
invalid_numbers_col = db.invalid_numbers

# Ensure unique indexes to prevent duplicates
valid_numbers_col.create_index("phoneNumber", unique=True)
invalid_numbers_col.create_index("phoneNumber", unique=True)

# Helper Functions
def detect_phone_column(df):
    """
    Automatically detect the column that likely contains phone numbers.
    Checks only the first three rows of the DataFrame.
    """
    sample_df = df.head(3)
    for col in sample_df.columns:
        col_values = sample_df[col].astype(str)
        # Check if all values in the sample start with '+' (likely international format)
        if col_values.str.startswith("+").all():
            return col
        # Check if all values in the sample are digits and long enough to be phone numbers
        if col_values.str.isdigit().all() and col_values.str.len().mean() > 9:
            return col
        # Check for known country prefixes
        for prefix in COUNTRY_PREFIXES:
            if col_values.str.startswith(prefix).all():
                return col
    return None


COUNTRY_PREFIXES = {
    "212": "Morocco",
    "213": "Algeria",
    "216": "Tunisia",
    "218": "Libya",
    "225": "Ivory Coast",
    "590": "Guadeloupe",
    "393": "Italy",
    "31": "Netherlands",
    "1": "USA/Canada",
    "49": "Germany",
    "39": "Italy",
    "58": "Venezuela",
    "41": "Switzerland",
    "45": "Denmark",
    "46": "Sweden",
    "51": "Peru",
    "54": "Argentina",
    "55": "Brazil",
    "597": "Suriname",
    "598": "Uruguay",
}

def normalize_phone_number(phone_str: str) -> Optional[str]:
    if not phone_str:
        return None
    if any(char in phone_str for char in ["%", "&"]):
        return None
    for ch in [".", "-", " "]:
        phone_str = phone_str.replace(ch, "")
    phone_str = phone_str.lstrip("p:+")
    if "/" in phone_str:
        phone_str = phone_str.split("/")[0]
    if phone_str.startswith(("O6", "O7", "06", "07")):
        phone_str = "33" + phone_str[1:]
    elif (phone_str.startswith("6") or phone_str.startswith("7")) and len(phone_str) == 9:
        phone_str = "33" + phone_str
    elif phone_str.startswith("5") and len(phone_str) == 9:
        phone_str = "972" + phone_str
    elif phone_str.startswith("9726"):
        phone_str = "336" + phone_str[4:]
    return phone_str if phone_str.isdigit() else None

def infer_country_from_phone(phone_number: str) -> str:
    parse_number = "+" + phone_number
    try:
        parsed = phonenumbers.parse(parse_number, None)
        if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
            return ""
        return geocoder.description_for_number(parsed, "en") or ""
    except phonenumbers.NumberParseException:
        return ""

def guess_country_from_prefix(phone: str) -> str:
    if phone.startswith("393") and len(phone) == 12:
        return "Italy"
    for prefix in sorted(COUNTRY_PREFIXES.keys(), key=len, reverse=True):
        if phone.startswith(prefix):
            return COUNTRY_PREFIXES[prefix]
    return "Unknown"

def setup_browser():
    chrome_options = Options()
    # Adjust this to your Chrome profile path
    chrome_profile_path = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
    
    # Important Chrome options for session persistence
    chrome_options.add_argument(f"user-data-dir={chrome_profile_path}")
    chrome_options.add_argument("--profile-directory=Default")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

@app.route('/process', methods=['POST'])
def process_numbers():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    temp_file_path = f"temp/{file.filename}"
    os.makedirs("temp", exist_ok=True)
    file.save(temp_file_path)

    try:
        df = pd.read_excel(temp_file_path)
        phone_col = detect_phone_column(df)
        if not phone_col:
            return jsonify({"error": "No valid phone number column detected"}), 400

        # Fetch existing phone numbers from the database
        existing_valid_numbers = set(
            entry["phoneNumber"] for entry in valid_numbers_col.find({}, {"phoneNumber": 1})
        )
        existing_invalid_numbers = set(
            entry["phoneNumber"] for entry in invalid_numbers_col.find({}, {"phoneNumber": 1})
        )

        processed_numbers = set()
        valid_entries = []
        invalid_entries = []

        for _, row in df.iterrows():
            raw_phone = str(row[phone_col]).strip()
            
            # Skip rows with 'nan' or empty phone numbers
            if raw_phone.lower() in {"nan", "", "none"}:
                continue

            normalized = normalize_phone_number(raw_phone)

            if normalized and normalized not in processed_numbers:
                processed_numbers.add(normalized)

                # Skip duplicates in both valid and invalid collections
                if normalized in existing_valid_numbers or normalized in existing_invalid_numbers:
                    continue

                country = infer_country_from_phone(normalized) or guess_country_from_prefix(normalized)
                if country and country != "Unknown":
                    valid_entries.append({
                        "phoneNumber": normalized, 
                        "country": country, 
                        "is_whatsapp": "unknown"  # Set initial status to unknown
                    })
                    existing_valid_numbers.add(normalized)
                else:
                    # Only add to invalid_entries if not already in invalid numbers
                    raw_phone_processed = normalize_phone_number(raw_phone) or raw_phone
                    if raw_phone_processed not in existing_invalid_numbers:
                        invalid_entries.append({"phoneNumber": raw_phone_processed, "reason": "No country detected"})
                        existing_invalid_numbers.add(raw_phone_processed)
            elif not normalized:
                # Similarly, prevent duplicate invalid entries
                raw_phone_processed = normalize_phone_number(raw_phone) or raw_phone
                if raw_phone_processed not in existing_invalid_numbers:
                    invalid_entries.append({"phoneNumber": raw_phone_processed, "reason": "Invalid format"})
                    existing_invalid_numbers.add(raw_phone_processed)

        # Insert valid and invalid entries in bulk
        if valid_entries:
            try:
                valid_numbers_col.insert_many(valid_entries, ordered=False)
            except Exception as e:
                return jsonify({"error": "Error inserting valid entries", "details": str(e)}), 500

        if invalid_entries:
            try:
                invalid_numbers_col.insert_many(invalid_entries, ordered=False)
            except Exception as e:
                return jsonify({"error": "Error inserting invalid entries", "details": str(e)}), 500

        # Get updated counts
        valid_count = valid_numbers_col.count_documents({})
        invalid_count = invalid_numbers_col.count_documents({})

        return jsonify({
            "message": "Processing completed",
            "new_valid_count": len(valid_entries),
            "new_invalid_count": len(invalid_entries),
            "total_valid_count": valid_count,
            "total_invalid_count": invalid_count,
        }), 200
    finally:
        os.remove(temp_file_path)

@app.route('/validate', methods=['POST'])
def validate_whatsapp_numbers():
    def background_validation():
        driver = None
        try:
            # Setup browser with persistent session
            driver = setup_browser()
            
            # Navigate to WhatsApp Web
            driver.get("https://web.whatsapp.com")
            
            # Check if already logged in or need to log in
            try:
                # Try to find the chats header quickly
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'span[aria-hidden="true"][data-icon="lock-small"]'))
                )
                print("Already logged in to WhatsApp Web")
            except TimeoutException:
                # If not logged in, wait for QR code scanning
                try:
                    print("Please scan the QR code to log in")
                    WebDriverWait(driver, 120).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'span[aria-hidden="true"][data-icon="lock-small"]'))
                    )
                    print("Login successful")
                except TimeoutException:
                    print("Login failed: Could not log in to WhatsApp Web")
                    return
            
            # Fetch numbers where is_whatsapp is "unknown"
            to_validate = list(valid_numbers_col.find({"is_whatsapp": "unknown"}))
            
            validated_count = 0
            for entry in to_validate:
                phone_number = entry["phoneNumber"]
                url = f"https://web.whatsapp.com/send?phone={phone_number}"
                driver.get(url)
                
                try:
                    # Wait for conversation header or error state
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//header[@class='_amid']"))
                    )
                    # Number is valid on WhatsApp
                    valid_numbers_col.update_one(
                        {"_id": entry["_id"]}, 
                        {"$set": {"is_whatsapp": True}}
                    )
                    validated_count += 1
                except TimeoutException:
                    # Number is not valid on WhatsApp
                    valid_numbers_col.update_one(
                        {"_id": entry["_id"]}, 
                        {"$set": {"is_whatsapp": False}}
                    )
            
            print({
                "message": "WhatsApp validation completed",
                "total_checked": len(to_validate),
                "validated_count": validated_count
            })
        
        except Exception as e:
            print({
                "error": "Validation failed",
                "details": str(e)
            })
        
        finally:
            if driver:
                driver.quit()

    # Start the background validation in a new thread
    thread = threading.Thread(target=background_validation)
    thread.start()

    # Immediate response to the client
    return jsonify({
        "message": "Scanning started, we will notify you when the job is done"
    }), 202
@app.route('/send', methods=['POST'])
def send_messages():
    data = request.json
    message = data.get("message")
    if not message:
        return jsonify({"error": "Message content is required"}), 400
    
    driver = None
    try:
        driver = setup_browser()
        driver.get("https://web.whatsapp.com")
        
        # Check login status
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//h1[normalize-space()='Chats']"))
            )
        except TimeoutException:
            return jsonify({
                "error": "Login failed",
                "message": "Could not log in to WhatsApp Web. Please try again."
            }), 400
        
        # Find numbers valid on WhatsApp
        valid_numbers = valid_numbers_col.find({"is_whatsapp": True})
        
        send_count = 0
        for entry in valid_numbers:
            phone_number = entry["phoneNumber"]
            url = f"https://web.whatsapp.com/send?phone={phone_number}&text={message}"
            driver.get(url)
            
            try:
                send_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Send']"))
                )
                send_button.click()
                send_count += 1
            except TimeoutException:
                print(f"Failed to send message to {phone_number}")
        
        return jsonify({
            "message": "Messages sent",
            "total_sent": send_count
        }), 200
    
    except Exception as e:
        return jsonify({
            "error": "Message sending failed",
            "details": str(e)
        }), 500
    
    finally:
        if driver:
            driver.quit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)