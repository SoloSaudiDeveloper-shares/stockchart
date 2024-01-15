import csv
import os
import requests
import time  # Add this line to import the 'time' module
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

# GitHub repository information
github_username = 'SoloSaudiDeveloper-shares'
github_repo = 'stockchart'
github_pat = 'YOUR_PERSONAL_ACCESS_TOKEN'  # Replace with your PAT

def create_or_locate_folder(symbol_number):
    folder_name = str(symbol_number)
    
    # Check if the 'charts' folder exists in the repository
    url = f'https://api.github.com/repos/{github_username}/{github_repo}/contents/charts'
    response = requests.get(url, headers={'Authorization': f'token {github_pat}'})
    
    if response.status_code == 200:
        # 'charts' folder exists
        print("'charts' folder already exists in the repository.")
    elif response.status_code == 404:
        # 'charts' folder doesn't exist, create it
        create_folder_url = f'https://api.github.com/repos/{github_username}/{github_repo}/contents/charts'
        data = {
            "message": "Create 'charts' folder",
            "content": "",
            "branch": "main"
        }
        create_response = requests.put(create_folder_url, headers={'Authorization': f'token {github_pat}'}, json=data)
        
        if create_response.status_code == 201:
            print("'charts' folder created in the repository.")
        else:
            print("Failed to create 'charts' folder in the repository.")
    
    # Now, create or locate the folder for the symbol
    folder_path = os.path.join("charts", folder_name)

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    return folder_path

# Function to take a screenshot and save it with a given filename
def take_screenshot(browser, xpath, filename):
    retries = 3  # Number of retries to capture the screenshot
    for _ in range(retries):
        try:
            element = WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath)))

            # Introduce a delay to allow time for dynamic content to load
            time.sleep(5)  # Adjust the delay as needed

            element.screenshot(filename)
            print(f"Screenshot saved: {filename}")
            return  # Screenshot captured successfully
        except StaleElementReferenceException:
            print("Stale element reference, retrying...")
            continue
        except Exception as e:
            print(f"Error capturing screenshot: {str(e)}")
            break
    
    print(f"Failed to capture screenshot for filename: {filename}")

# Function to process the URL and capture "financials-overview" screenshot
def process_financials_overview(number, browser, folder_path):
    print(f"Processing symbol {number} for financials overview...")
    url = f"https://www.tradingview.com/symbols/TADAWUL-{number}/financials-overview/"
    browser.get(url)

    screenshot_xpath = "//*[@id='js-category-content']/div[2]/div/div/div[2]/section[3]/div[2]/div[1]/div[2]"
    filename = f"{folder_path}/financials_overview_Performance_{number}.png"
    take_screenshot(browser, screenshot_xpath, filename)

# Function to process the URL and capture a screenshot
def process_url(number, browser, folder_path):
    print(f"Processing symbol {number}...")
    url = f"https://www.tradingview.com/symbols/TADAWUL-{number}/financials-dividends/"
    browser.get(url)

    screenshot_xpath = "//*[@id='js-category-content']/div[2]/div/div/div[3]"
    filename = f"{folder_path}/financials_dividends_{number}.png"
    take_screenshot(browser, screenshot_xpath, filename)

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
        folder_path = create_or_locate_folder(number)
        process_url(number, browser, folder_path)
        process_financials_overview(number, browser, folder_path)
else:
    print("No symbols to process.")

browser.quit()
