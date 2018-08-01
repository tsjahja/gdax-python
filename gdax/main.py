import gdax
import json
import numpy as np
import openpyxl
from openpyxl.workbook import Workbook
import time
from datetime import datetime, timedelta


VOLUME_ORDER_DIFFERENCE = 10
STREAK_TRESHOLD = 10
BUY_SELL_SIZE = '0.1'
WAIT_ORDER_THRESHOLD_MINUTES = 1 # will wait _ mins until order get executed, or cancel

# get last lowest and highest price
LOW_HIGH_GRANULARITY = 900 # in seconds
HOURS_BEFORE = 12

BITCOIN = 'BTC-USD'
OUTPUT_FILE = 'bitcoin-trading-history.xlsx'

# key = '192671a0ea24774849d376976cf496f0'
# b64secret = 'cnkkWLCJQRg6xomQuNKvFKA9eU8jgttkMD79QPjcQYJuXYMspqn+YbUJ7oNylANGwjpeF/cxSDjv6FBv7G20Mg=='
# passphrase = 'gphtdf2hxk8'
# API_URL = 'https://api-public.sandbox.gdax.com'


def create_new_file():
    new_book = Workbook()
    new_sheet = new_book.worksheets[0]
    new_sheet.title = BITCOIN
    new_sheet.append(['Timestamp', 'Bidding average price', 'Bidding total volume', 'Asking average price', 'Asking total volume', 'Current price', 'Action'])
    new_book.save(filename = OUTPUT_FILE)

def write_to_file(time, bids, asks, current_price, action):
    book = openpyxl.load_workbook(OUTPUT_FILE)
    sheet = book.active

    if action == 'BUY':
        sign = 1
    elif action == 'SELL':
        sign = -1
    else:
        sign = 0

    sheet.append([time['iso'], bids[0], bids[1], asks[0], asks[1], current_price, action, current_price * sign])
    book.save(OUTPUT_FILE)

def get_average_price(order_book):
    volume =  np.multiply(order_book[:, 2], order_book[:, 1])
    total_volume = sum(volume)
    total_price = sum(np.multiply(order_book[:, 0], volume))
    return [total_price / total_volume, total_volume]

def get_recent_trade():
    trades = np.array(public_client.get_product_trades(product_id=BITCOIN))
    sell_size = 0.00
    buy_size = 0.00
    for trade in trades:
        if trade['side'] == 'buy':
            buy_size = buy_size + float(trade['size'])
        else:
            sell_size = sell_size + float(trade['size'])
    return buy_size, sell_size

def get_high_low_price(public_client):
    start = datetime.today() - timedelta(hours=HOURS_BEFORE)
    last_one_hour = public_client.get_product_historic_rates(BITCOIN, start=start, granularity=LOW_HIGH_GRANULARITY)
    most_low = last_one_hour[0][1]
    most_high = last_one_hour[0][2]
    for x in range(0, (HOURS_BEFORE * 60 * 60) / LOW_HIGH_GRANULARITY):
        if last_one_hour[x][1] < most_low:
            most_low = last_one_hour[x][1]
        if last_one_hour[x][2] > most_high:
            most_high = last_one_hour[x][2]

    return most_low, most_high

def run(auth_client, public_client, been_bought_streak):

    order_book = public_client.get_product_order_book(BITCOIN, level=2)
    bids_order_book = np.array(order_book["bids"], dtype=float)
    asks_order_book = np.array(order_book["asks"], dtype=float)

    time = public_client.get_time()
    bids = get_average_price(bids_order_book)
    asks = get_average_price(asks_order_book)
    current_price = public_client.get_product_ticker(product_id=BITCOIN)["price"]
    # recent_trade = get_recent_trade()
    low, high = get_high_low_price(public_client)
    print ''
    print 'time:', time['iso']
    print 'bids:', bids
    print 'asks:', asks
    print 'price:', current_price
    print 'last 1 hour info | low:', low, 'high:', high
    # print 'trade quantity', recent_trade
    bought_streak = buy_sell(auth_client, bids[1], asks[1], current_price, been_bought_streak[0], been_bought_streak[1], been_bought_streak[2], been_bought_streak[3], low, high)
    print bought_streak
    print '--------------------------------'

    if (bought_streak[0] > 0 and been_bought_streak[0] < 0):
        action = 'BUY'
    elif (bought_streak[0] < 0 and been_bought_streak[0] > 0):
        action = 'SELL'
    else:
        action = ''

    write_to_file(time, bids, asks, current_price, action)
    return bought_streak

def buy_sell(auth_client, bids_volume, asks_volume, price, bought_price, bought_size, buy_streak, sell_streak, low, high):

    # price going up potential
    if (bids_volume > VOLUME_ORDER_DIFFERENCE * asks_volume):
        buy_streak += 1
        sell_streak = 0
        if (bought_price < 0 and buy_streak >= STREAK_TRESHOLD and float(price) < float(high)):
            filled_size = buy(auth_client, price)
            if float(filled_size) > 0:
                print 'BUY', price
                bought_price = price
                bought_size = filled_size
                buy_streak = 0
                sell_streak = 0

    # price going down potential
    elif (asks_volume > VOLUME_ORDER_DIFFERENCE * bids_volume):
        buy_streak = 0
        sell_streak += 1
        if (bought_price > 0 and float(bought_price) < float(price) and sell_streak >= STREAK_TRESHOLD):
            filled_size = sell(auth_client, price, bought_size)
            if float(filled_size) > 0:
                print 'SELL', price
                bought_price = -1
                bought_size = filled_size
                buy_streak = 0
                sell_streak = 0

    else:
        sell_streak = 0
        buy_streak = 0

    return bought_price, bought_size, buy_streak, sell_streak

def buy(auth_client, buy_price):
    order_id = auth_client.buy(price=buy_price, size=BUY_SELL_SIZE, product_id=BITCOIN, type='limit', post_only='true')['id']
    return check_order(order_id)

def sell(auth_client, sell_price, bought_size):
    order_id = auth_client.sell(price=sell_price, size=bought_size, product_id=BITCOIN, type='limit', post_only='true')['id']
    return check_order(order_id)

def check_order(order_id):
    end_time = datetime.today() + timedelta(minutes=WAIT_ORDER_THRESHOLD_MINUTES)
    while auth_client.get_order(order_id)['status'] == 'open' and datetime.today() < end_time:
        print 'waiting for someone to pickup the order, time left=', end_time - datetime.today()
        if auth_client.get_order(order_id)['status'] == 'done':
            print 'ordered!'
            filled_size = auth_client.get_order(order_id)['filled_size']
            break

    if auth_client.get_order(order_id)['status'] == 'open':
        filled_size = auth_client.get_order(order_id)['filled_size']
        order_id = auth_client.cancel_order(order_id)
        print 'Canceling order_id=', order_id

    return filled_size


if __name__ == '__main__':
    create_new_file()
    public_client = gdax.PublicClient()
    # Use the sandbox API (requires a different set of API access credentials)
    auth_client = gdax.AuthenticatedClient(key, b64secret, passphrase, api_url=API_URL)

    bought_streak = -1, 0, 0, 0
    while True:
        bought_streak = run(auth_client, public_client, bought_streak)
        time.sleep(1)