import csv
import os
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# GitHub repository information
github_username = 'SoloSaudiDeveloper-shares'
github_repo = 'stockchart'
github_pat = 'YOUR_PERSONAL_ACCESS_TOKEN'  # Replace with your PAT

def check_and_create_folder(symbol_number):
    folder_name = str(symbol_number)
    
    # Check if the folder exists in the repository
    url = f'https://api.github.com/repos/{github_username}/{github_repo}/contents/charts/{folder_name}'
    response = requests.get(url, headers={'Authorization': f'token {github_pat}'})
    
    if response.status_code == 200:
        # Folder exists, no need to create it
        print(f"Folder '{folder_name}' already exists in the repository.")
    elif response.status_code == 404:
        # Folder doesn't exist, create it
        create_folder_url = f'https://api.github.com/repos/{github_username}/{github_repo}/contents/charts/{folder_name}'
        data = {
            "message": f"Create folder for symbol {symbol_number}",
            "content": "",
            "branch": "main"
        }
        create_response = requests.put(create_folder_url, headers={'Authorization': f'token {github_pat}'}, json=data)
        
        if create_response.status_code == 201:
            print(f"Folder '{folder_name}' created in the repository.")
        else:
            print(f"Failed to create folder '{folder_name}' in the repository.")
    
    return f'charts/{folder_name}'

def take_screenshot(browser, xpath, symbol_number, folder_path):
    try:
        element = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.XPATH, xpath)))
    except Exception:
        print("Element not found, attempting to scroll.")
        body = browser.find_element(By.TAG_NAME, "body")
        for _ in range(10):  # Adjust the number of scrolls as necessary
            body.send_keys(Keys.PAGE_DOWN)
            try:
                element = WebDriverWait(browser, 2).until(
                    EC.presence_of_element_located((By.XPATH, xpath)))
                break
            except Exception:
                continue
        else:
            print(
                f"Element with XPath {xpath} not found for symbol {symbol_number} after scrolling."
            )
            return

    filename = f"{folder_path}/screenshot_{symbol_number}.png"
    element.screenshot(filename)
    print(f"Screenshot saved: {filename}")

# Initialize Selenium WebDriver
chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument("--disable-gpu")
browser = webdriver.Chrome(options=chrome_options)

# Path to the input CSV file
csv_file_path = 'Symbols.csv'

# Read symbols from the CSV file
print("Reading symbols from the CSV file...")
symbols = []
try:
    with open(csv_file_path, newline='') as csvfile:
        csv_reader = csv.reader(csvfile)
        next(csv_reader, None)  # Skip the header if there is one
        symbols = [row[0] for row in csv_reader]
    print(f"Symbols loaded: {symbols}")
except FileNotFoundError:
    print(f"Error: File not found - {csv_file_path}")

# Process each symbol
if symbols:
    for number in symbols:
        folder_path = check_and_create_folder(number)
        process_url(number, browser, folder_path)
else:
    print("No symbols to process.")

browser.quit()
