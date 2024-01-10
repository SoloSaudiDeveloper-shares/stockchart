import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def take_screenshot(browser, xpath, symbol_number):
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

  filename = f"screenshot_{symbol_number}.png"
  element.screenshot(filename)
  print(f"Screenshot saved: {filename}")


def process_url(number, browser):
  print(f"Processing symbol {number}...")
  url = f"https://www.tradingview.com/symbols/TADAWUL-{number}/financials-dividends/"
  browser.get(url)

  screenshot_xpath = "//*[@id='js-category-content']/div[2]/div/div/div[3]/div"
  take_screenshot(browser, screenshot_xpath, number)


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
    process_url(number, browser)
else:
  print("No symbols to process.")

browser.quit()
