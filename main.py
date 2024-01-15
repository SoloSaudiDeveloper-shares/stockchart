import csv
import yfinance as yf
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

def update_csv_file(symbol, data):
    folder_path = create_or_locate_folder(symbol)
    csv_file_path = f'{folder_path}/financial_data.csv'
    
    with open(csv_file_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits'])
        for date, row in data.iterrows():
            writer.writerow([date, row['Open'], row['High'], row['Low'], row['Close'], row['Volume'], row['Dividends'], row['Stock Splits']])
    logging.info(f"CSV file updated for {symbol}")

def create_or_locate_folder(symbol):
    folder_path = os.path.join("charts", symbol)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path

def fetch_financial_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="max")
        return data
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        return None

# Read symbols from the CSV file
csv_file_path = 'Symbols.csv'
symbols = []
try:
    with open(csv_file_path, newline='') as csvfile:
        csv_reader = csv.reader(csvfile)
        next(csv_reader, None)  # Skip the header if there is one
        symbols = [row[0] for row in csv_reader]
    logging.info(f"Symbols loaded: {symbols}")
except FileNotFoundError:
    logging.error(f"Error: File not found - {csv_file_path}")

# Process each symbol
if symbols:
    for symbol in symbols:
        logging.info(f"Processing symbol {symbol}...")
        data = fetch_financial_data(symbol)
        if data is not None:
            update_csv_file(symbol, data)
        else:
            logging.error(f"No data fetched for {symbol}.")
else:
    logging.info("No symbols to process.")
