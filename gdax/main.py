import gdax
import numpy as np
import openpyxl
from openpyxl.workbook import Workbook
import time
from datetime import datetime, timedelta

VOLUME_ORDER_DIFFERENCE = 3
STREAK_TRESHOLD = 10
BUY_SELL_SIZE = '0.001'
WAIT_ORDER_THRESHOLD_MINUTES = 3  # will wait _ mins until order get executed, or cancel

# buy/sell tolerance
MAX_PRICE_TOLERANCE_DIFFERENCE = 2
INCREMENT_PRICE = 0.05

# get last lowest and highest price
LOW_HIGH_GRANULARITY = 900  # in seconds
HOURS_BEFORE = 12

BITCOIN = 'BTC-USD'
OUTPUT_FILE = 'bitcoin-trading-history.xlsx'

# key = '8702bbde64ca974ebdc9f6b71e39a908'
# b64secret = '/DIU7Q3JGSDeCix63O/IK27yDlod2DuvmBMjG80gN4QFynMAq3e7YmXP6eYeyadhBhOJEs0Kc8jz6NZ/3Q5KKA=='
# passphrase = 'svak93wz3x'
# API_URL = 'https://api-public.sandbox.gdax.com'






########################################## PRODUCTION KEY #############################################################

########################################## PRODUCTION KEY #############################################################





def create_new_file():
    new_book = Workbook()
    new_sheet = new_book.worksheets[0]
    new_sheet.title = BITCOIN
    new_sheet.append(
        ['Timestamp', 'Bidding average price', 'Bidding total volume', 'Asking average price', 'Asking total volume',
         'Current price', 'Action'])
    new_book.save(filename=OUTPUT_FILE)


def write_to_file(bids, asks, current_price, action):
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
    volume = np.multiply(order_book[:, 2], order_book[:, 1])
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


def get_high_low_price():
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


def run(been_bought_streak):
    order_book = public_client.get_product_order_book(BITCOIN, level=2)
    bids_order_book = np.array(order_book["bids"], dtype=float)
    asks_order_book = np.array(order_book["asks"], dtype=float)

    time = public_client.get_time()
    bids = get_average_price(bids_order_book)
    asks = get_average_price(asks_order_book)
    current_price = public_client.get_product_ticker(product_id=BITCOIN)["price"]
    # recent_trade = get_recent_trade()
    low, high = get_high_low_price()
    print ''
    print 'time:', time['iso']
    print 'bids:', bids
    print 'asks:', asks
    print 'last 1 hour info | low:', low, 'high:', high
    print 'price:', current_price
    # print 'trade quantity', recent_trade
    bought_streak = buy_sell(bids[1], asks[1], current_price, been_bought_streak[0], been_bought_streak[1],
                             been_bought_streak[2], been_bought_streak[3], low, high)
    print bought_streak
    print '--------------------------------'

    if bought_streak[0] > 0 and been_bought_streak[0] < 0:
        action = 'BUY'
    elif bought_streak[0] < 0 and been_bought_streak[0] > 0:
        action = 'SELL'
    else:
        action = ''

    return bought_streak


def buy_sell(bids_volume, asks_volume, price, bought_price, bought_size, buy_streak, sell_streak, low, high):
    # price going up potential
    if bids_volume > VOLUME_ORDER_DIFFERENCE * asks_volume:
        buy_streak += 1
        sell_streak = 0
        if bought_price < 0 and buy_streak >= STREAK_TRESHOLD and float(price) < float(high):
            filled_size = buy(price)
            if float(filled_size) > 0:
                print 'BUY', price
                bought_price = price
                bought_size = filled_size
                buy_streak = 0
                sell_streak = 0

    # price going down potential
    elif asks_volume > VOLUME_ORDER_DIFFERENCE * bids_volume:
        buy_streak = 0
        sell_streak += 1
        if bought_price > 0 and float(bought_price) <= float(price) and sell_streak >= STREAK_TRESHOLD:
            filled_size = sell(price, bought_size, bought_price)
            if float(filled_size) > 0:
                print 'SELL', price
                if float(filled_size) < float(bought_size):
                    bought_size = float(filled_size) - float(bought_size)
                else:
                    bought_price = -1
                    bought_size = 0
                    buy_streak = 0
                    sell_streak = 0

    else:
        sell_streak = 0
        buy_streak = 0

    return bought_price, bought_size, buy_streak, sell_streak


def buy(buy_price):
    buy_price = "{0:.2f}".format(float(buy_price))
    response = auth_client.buy(price=buy_price, size=BUY_SELL_SIZE, product_id=BITCOIN, type='limit', post_only='true')
    print response
    original_buy_price = float(buy_price) + float(MAX_PRICE_TOLERANCE_DIFFERENCE)
    current_price = public_client.get_product_ticker(product_id=BITCOIN)["price"]

    while response['status'] == 'rejected' and float(original_buy_price) >= float(buy_price):
        print 'Trying to buy with buy price=', buy_price, ', original buy price=', original_buy_price, ' current price=', current_price
        response = auth_client.buy(price=buy_price, size=BUY_SELL_SIZE, product_id=BITCOIN, type='limit', post_only='true')
        print response
        buy_price = float(buy_price) + float(INCREMENT_PRICE)
        buy_price = "{0:.2f}".format(float(buy_price))
        current_price = public_client.get_product_ticker(product_id=BITCOIN)["price"]

    order_id = response['id']
    return check_order(order_id, buy_price, True)


def sell(sell_price, bought_size, bought_price):
    sell_price = "{0:.2f}".format(float(sell_price))
    response = auth_client.sell(price=sell_price, size=bought_size, product_id=BITCOIN, type='limit', post_only='true')
    print response
    original_sell_price = float(sell_price) - float(MAX_PRICE_TOLERANCE_DIFFERENCE)
    current_price = public_client.get_product_ticker(product_id=BITCOIN)["price"]

    while response['status'] == 'rejected' and float(original_sell_price) <= float(sell_price) and float(sell_price) >= float(bought_price):
        print 'Trying to sell with sell price=', sell_price, ', original sell price=', original_sell_price, ' current price=', current_price
        response = auth_client.buy(price=sell_price, size=BUY_SELL_SIZE, product_id=BITCOIN, type='limit', post_only='true')
        print response
        sell_price = float(sell_price) - float(INCREMENT_PRICE)
        sell_price = "{0:.2f}".format(float(sell_price))
        current_price = public_client.get_product_ticker(product_id=BITCOIN)["price"]

    order_id = response['id']
    return check_order(order_id, sell_price, False)


def check_order(order_id, transaction_price, buying):
    filled_size = 0
    end_time = datetime.today() + timedelta(minutes=WAIT_ORDER_THRESHOLD_MINUTES)
    current_price = public_client.get_product_ticker(product_id=BITCOIN)["price"]
    keep_trying = float(current_price) <= float(transaction_price) if buying else float(current_price) >= float(transaction_price)
    while auth_client.get_order(order_id)['status'] == 'open' and datetime.today() < end_time and keep_trying:
        print 'waiting for someone to pickup the order, transaction price=', transaction_price, 'current price=', current_price, ' time left=', end_time - datetime.today()
        if auth_client.get_order(order_id)['status'] == 'done':
            print order_id
            response = auth_client.get_order(order_id)
            print response
            filled_size = response["filled_size"]
            price = response['price']
            print 'ordered! transaction price=', price, ' filled size=', filled_size
            break
        current_price = public_client.get_product_ticker(product_id=BITCOIN)["price"]
        keep_trying = float(current_price) <= float(transaction_price) if buying else float(current_price) >= float(transaction_price)

    if auth_client.get_order(order_id)['status'] == 'open':
        print order_id
        auth_client.cancel_order(order_id)
        try:
            response = auth_client.get_order(order_id)
            filled_size = response["filled_size"]
        # throws KeyError if cancelled successfully
        except KeyError:
            filled_size = 0

        print 'Canceling order_id=', order_id, ' filled_size=', filled_size

    return filled_size


if __name__ == '__main__':
    create_new_file()
    public_client = gdax.PublicClient()
    # Use the sandbox API (requires a different set of API access credentials)
    auth_client = gdax.AuthenticatedClient(key, b64secret, passphrase, api_url=API_URL)

    bought_streak = -1, 0, 0, 0
    while True:
        bought_streak = run(bought_streak)
        time.sleep(1)
