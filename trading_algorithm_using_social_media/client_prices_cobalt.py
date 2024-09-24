import logging
import pandas as pd
import socket
import matplotlib.pyplot as plt
from openai import OpenAI
from datetime import datetime, timedelta

logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)


class TradingClient:
    def __init__(self, host, port, openai_api_key, initial_capital=1000000.0):
        self.list_bid = []
        self.list_ask = []
        self.list_settlement_prices = []
        self.list_responses = []
        self.list_date = []
        self.buy_signal = []
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.initial_capital = float(initial_capital)
        self.buy_df = pd.DataFrame(
            columns=['date', 'settlement_price', 'purchase_price', 'signal', 'buy_signal', 'qty'])
        self.portfolio = pd.DataFrame(columns=['holdings', 'cash', 'total', 'returns'])
        self.connect_to_server(host, port)

    def connect_to_server(self, host, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
            self.listen_to_orders(sock)

    def listen_to_orders(self, sock):
        while True:
            data = sock.recv(1024)
            if not data:
                break
            received_data = data.decode('utf-8').strip()

            if self.is_order_data(received_data):
                order = self.parse_order(received_data)
                logging.info('bid/ask')
                self.add_order(order)
                self.remove_old_orders()

                if order['side'] == 'ask':
                    self.buy_df = self.buy_df.append({
                        'date': order['date'],
                        'settlement_price': self.list_settlement_prices[-1],
                        'purchase_price': order['price']
                    }, ignore_index=True)
            else:
                self.buy_df = self.handle_tweet(received_data, self.buy_df)

            self.update_portfolio()
            print(self.buy_df)
            print(self.portfolio)

    def is_order_data(self, data_str):
        return ',' in data_str and len(data_str.split(',')) == 6

    def handle_tweet(self, tweet, buy_df):
        completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system",
                 "content": "I'm analyzing tweets. I want you to reply 'yes' if the tweet below indicates a harmful event for at least hundreds of thousands of people. Reply 'no' if the tweet is about any other topic."},
                {"role": "user", "content": tweet}
            ]
        )
        response_content = completion.choices[0].message.content.strip().lower()

        buy_df = buy_df.append({
            'date': self.list_date[-1] if self.list_date else None,
            'settlement_price': self.list_settlement_prices[-1] if self.list_settlement_prices else None,
            'signal': response_content,
            'buy_signal': 1 if response_content == 'yes' else 0
        }, ignore_index=True)

        buy_df['qty'] = buy_df['buy_signal'].cumsum()
        return buy_df

    def parse_order(self, order_str):
        type, price, settlement_price, quantity, date, order_id = order_str.split(',')
        self.list_settlement_prices.append(float(settlement_price))
        self.list_date.append(date)
        return {
            'side': type.lower(),
            'price': float(price),
            'quantity': int(quantity),
            'date': date,
            'id': int(order_id)
        }

    def add_order(self, o):
        if o['side'] == 'bid':
            self.list_bid.append(o)
            self.list_bid.sort(key=lambda x: x['price'], reverse=True)
        elif o['side'] == 'ask':
            self.list_ask.append(o)
            self.list_ask.sort(key=lambda x: x['price'])
        else:
            raise Exception('Not a known side')

    def remove_old_orders(self):
        max_date = self.get_max_date()
        if max_date:
            cutoff_date = max_date - timedelta(days=4)
            self.list_bid = [o for o in self.list_bid if datetime.strptime(o['date'], '%Y-%m-%d') > cutoff_date]
            self.list_ask = [o for o in self.list_ask if datetime.strptime(o['date'], '%Y-%m-%d') > cutoff_date]

    def get_max_date(self):
        dates = [datetime.strptime(o['date'], '%Y-%m-%d') for o in self.list_bid + self.list_ask]
        return max(dates) if dates else None

    def update_portfolio(self):
        if len(self.buy_df) < 2:
            return

        self.buy_df['master_signal'] = self.buy_df['buy_signal']

        positions = pd.DataFrame(index=self.buy_df.index)
        positions['positions'] = self.buy_df['master_signal'].cumsum()

        self.portfolio = pd.DataFrame(index=self.buy_df.index)
        self.portfolio['holdings'] = positions['positions'] * self.buy_df['settlement_price']

        positions['pos_diff'] = positions['positions'].diff()

        self.portfolio['cash'] = self.initial_capital - (
                    positions['pos_diff'] * self.buy_df['settlement_price']).cumsum()
        self.portfolio['total'] = self.portfolio['cash'] + self.portfolio['holdings']
        self.portfolio['returns'] = self.portfolio['total'].pct_change()

        # Calculate sell signals (simplified version)
        self.buy_df['sell_signal'] = ((self.buy_df['settlement_price'].pct_change() < -0.15) |
                                      (self.buy_df['settlement_price'].pct_change() > 0.15)).astype(int)

    def plot_portfolio(self):
        plt.figure(figsize=(12, 8))
        self.portfolio['total'].plot(color='g', lw=2, label='Total')
        self.portfolio['holdings'].plot(color='b', lw=1, label='Holdings')
        self.portfolio['cash'].plot(color='r', lw=1, label='Cash')
        plt.title("Portfolio Performance")
        plt.legend()
        plt.show()


# Usage
if __name__ == "__main__":
    HOST, PORT = "localhost", 9999
    openai_api_key = "your_openai_api_key_here"
    ob = TradingClient(HOST, PORT, openai_api_key)
    ob.plot_portfolio()