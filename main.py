import csv
import yfinance as yf
import os
import requests

# GitHub repository information
github_username = 'SoloSaudiDeveloper-shares'
github_repo = 'stockchart'
github_pat = 'YOUR_PERSONAL_ACCESS_TOKEN'  # Replace with your PAT

def update_csv_file(symbol, data):
    csv_file_path = f'charts/{symbol}/financial_data.csv'
    
    with open(csv_file_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits'])
        for date, row in data.iterrows():
            writer.writerow([date, row['Open'], row['High'], row['Low'], row['Close'], row['Volume'], row['Dividends'], row['Stock Splits']])

def create_or_locate_folder(symbol):
    folder_path = os.path.join("charts", symbol)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path

def fetch_financial_data(symbol):
    stock = yf.Ticker(symbol)
    # Get historical market data, here max is used to get all available data
    data = stock.history(period="max")
    return data

# Read symbols from the CSV file
csv_file_path = 'Symbols.csv'
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
    for symbol in symbols:
        print(f"Processing symbol {symbol}...")
        folder_path = create_or_locate_folder(symbol)
        data = fetch_financial_data(symbol)
        update_csv_file(symbol, data)
else:
    print("No symbols to process.")
