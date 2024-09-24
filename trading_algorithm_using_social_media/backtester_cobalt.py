from openai import OpenAI
import openai
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
pd.set_option('display.max_columns', None)

# Define folder path and construct file path
folder_path = 'replace_with_folder_path' # Replace with your actual directory path
file_name = 'backtest_data.csv'
file_path = folder_path + file_name

# Load tweets from CSV file
tweets = pd.read_csv(file_path, encoding='latin-1')
# Remove commas and convert the 'Price' column to float
tweets['Price'] = tweets['Price'].str.replace(',', '').astype(float)

# Example tweets
openai_api_key = "api_key"  # Replace with your actual OpenAI API key

# Instantiate OpenAI API client
openai_client = OpenAI(api_key=openai_api_key)

responses = []
for tweet in tweets['Text']:
    tweet = str(tweet)
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system",
                "content": "I'm analyzing tweets. I want you to reply 'yes' if the tweet below indicates a harmful event for at least hundreds of thousands of people. Reply 'no' if the tweet is about any other topic."},
                {"role": "user", "content": tweet}
            ]
        )
        response = completion.choices[0].message.content.strip().lower()
    except Exception as e:
        print(f"Error occurred while processing tweet: {e}")
        response = "no"  # Default to 'no' in case of error
    responses.append(response)
tweets['signal'] = responses

local_max =20
short = 10
long = 40
threshold = .85

# local_max calculation
tweets['local_max'] = tweets['Price'].rolling(window=local_max).max()

# short_ma calculation
tweets['short_ma'] = tweets['Price'].rolling(window=short).mean()

# long_ma calculation
tweets['long_ma'] = tweets['Price'].rolling(window=long).mean()

# is_short_greater
tweets['is_short_greater'] = (tweets['short_ma'] > tweets['long_ma']).astype(int)

# ma_diff
tweets['ma_diff'] = tweets['is_short_greater'].diff()

# criss cross signal
tweets['signal1'] = (tweets['ma_diff'] < 0).astype(int)

# trailing stop signal
tweets['signal2'] = (tweets['Price'] < threshold * tweets['local_max']).astype(int)

# sell_signal
tweets['sell_signal'] = (tweets['signal1'] + tweets['signal2'] > 0).astype(int)

# PnL Section
initial_capital = float(1000000.0)

# Positions df with same index as signals
# positions = pd.DataFrame(columns=['positions'],index=tweets.index)
tweets['positions'] = 0

# master signal # no sell when positions = 0 # no buy signal when sell signal = 1
tweets['master_signal'] = 0

# Set 'master_signal' to 1 where 'sell_signal' is 0 and 'signal' is 'yes'
tweets.loc[(tweets['sell_signal'] == 0) & (tweets['signal'] == 'yes'), 'master_signal'] = 1

# Set 'master_signal' to -1 where 'sell_signal' is 1
tweets.loc[tweets['sell_signal'] == 1, 'master_signal'] = -1

# adjust positions according to master signal
# Increment 'positions' by 1 where 'master_signal' is 1
# tweets.loc[tweets['master_signal'] == 1, 'positions'] = tweets['positions'].shift(1).fillna(0) + 1
#
# # Carry forward the 'positions' where 'master_signal' is 0
# tweets.loc[tweets['master_signal'] == 0, 'positions'] = tweets['positions'].shift(1).fillna(0)
#
# # Set 'positions' to 0 where 'master_signal' is -1
# tweets.loc[tweets['master_signal'] == -1, 'positions'] = 0

for index, row in tweets.iterrows():
    if index > 0:
        previous_position = tweets.at[index - 1, 'positions']
    else:
        previous_position = 0

    if row['master_signal'] == 1:
        # Increment 'positions' by 1
        tweets.at[index, 'positions'] = previous_position + 1
    elif row['master_signal'] == -1:
        # Set 'positions' to 0
        tweets.at[index, 'positions'] = 0
    else:
        # Carry forward the 'positions'
        tweets.at[index, 'positions'] = previous_position

print(tweets) #test

# You are now going to calculate the notional (quantity x price)
# for your portfolio. You will multiply Adj Close from
# the dataframe containing prices and the positions (10 shares)
# You will store it into the variable portfolio
portfolio = pd.DataFrame(columns=['holdings'],index=tweets.index)
portfolio['date'] = tweets['Date']
portfolio['holdings'] = tweets['positions']*(tweets['Price'])

# You will store positions.diff into pos_diff
tweets['pos_diff'] = tweets['positions'].diff().fillna(0)

# You will now add a column cash in your dataframe portfolio
# which will calculate the amount of cash you have
# initial_capital - (the notional you use for your different buy/sell)
portfolio['cash'] = initial_capital - (tweets['pos_diff']*(tweets['Price'])).cumsum()

# You will now add a column total to your portfolio calculating the part of holding
# and the part of cash
portfolio['total'] = portfolio['cash'] + portfolio['holdings']

# Add returns to portfolio
portfolio['returns'] = portfolio['total'].pct_change()

# Redfine according to positions
if (tweets['pos_diff'] == 1).any():
    first_one_index = tweets['pos_diff'][tweets['pos_diff'] == 1].idxmax()
else:
    first_one_index = None

for index, row in tweets.iterrows():
    if first_one_index is not None and index < first_one_index:
        tweets.at[index, 'local_max'] = 0
    else:
        tweets.at[index, 'local_max'] = tweets['Price'].rolling(window=local_max, min_periods=1).max().iloc[index]
# if positions['positions'] == 0:
#     tweets['local_max'] = 0
# else:
#     tweets['local_max'] = tweets['Price'].rolling(window=local_max).max()



# Print the first lines of portfolio
print(tweets)
print(portfolio)

portfolio['holdings'].plot( color='g', lw=.5)
portfolio['cash'].plot(color='r', lw=.5)
portfolio['total'].plot(color='g', lw=.5)
plt.title("Backtester")
plt.legend()
plt.show()