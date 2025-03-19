import matplotlib

matplotlib.use('TkAgg')  # Force using TkAgg backend
import MetaTrader5 as mt5
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime, timedelta, time


def get_10min_data(symbol, num_bars=100):
    """Get 10-minute data for the specified symbol"""
    timeframe = mt5.TIMEFRAME_M10
    bars = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)

    if bars is None or len(bars) == 0:
        print(f"Failed to retrieve data for {symbol}, error code: {mt5.last_error()}")
        return None

    df = pd.DataFrame(bars)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is not None:
        digits = symbol_info.digits
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = df[col].round(digits)

    df = df.set_index('time')
    df.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'tick_volume': 'Volume'
    }, inplace=True)
    df.sort_index(inplace=True)
    print(f"Dataframe shape from get_10min_data: {df.shape}")  # Debug print
    return df


def get_daily_levels(symbol):
    """Get important daily price levels including today's open and previous day's high/low"""
    # Get the current date
    today = datetime.now().date()

    # Get 2 days ago (to make sure we have previous day data)
    two_days_ago = today - timedelta(days=2)

    # Get daily bars (last 3 days to ensure we have both today and yesterday)
    daily_bars = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1,
                                      datetime.combine(two_days_ago, time(0)),
                                      datetime.now())

    if daily_bars is None or len(daily_bars) == 0:
        print(f"Failed to retrieve daily data for {symbol}, error code: {mt5.last_error()}")
        return None

    # Convert to DataFrame
    daily_df = pd.DataFrame(daily_bars)
    daily_df['time'] = pd.to_datetime(daily_df['time'], unit='s')
    daily_df = daily_df.set_index('time')
    daily_df.sort_index(inplace=True)

    # If we have at least 2 bars (today and yesterday)
    if len(daily_df) >= 2:
        # Yesterday's data will be the second-to-last bar if today's bar exists
        # otherwise it will be the last bar
        today_index = daily_df.index[-1].date()

        if today_index == today:
            # We have today's bar, so yesterday is second-to-last
            today_bar = daily_df.iloc[-1]
            yesterday_bar = daily_df.iloc[-2]
        else:
            # We don't have today's bar yet, so yesterday is the last bar
            yesterday_bar = daily_df.iloc[-1]
            # Use yesterday's close as today's open if today's bar doesn't exist yet
            today_bar = yesterday_bar.copy()
            today_bar['open'] = yesterday_bar['close']

        return {
            'today_open': today_bar['open'],
            'yesterday_high': yesterday_bar['high'],
            'yesterday_low': yesterday_bar['low'],
            'yesterday_close': yesterday_bar['close']
        }
    else:
        print("Not enough daily bars to determine previous day's levels")
        return None

def get_weekly_levels(symbol):
    """Get important weekly price levels including previous week's high/low/close"""
    # Get the current date
    today = datetime.now().date()

    # Get 14 days ago (to ensure we have at least 2 complete weeks)
    two_weeks_ago = today - timedelta(days=14)

    # Get weekly bars (last 3 weeks to ensure we have current and previous week)
    weekly_bars = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_W1,
                                      datetime.combine(two_weeks_ago, time(0)),
                                      datetime.now())

    if weekly_bars is None or len(weekly_bars) == 0:
        print(f"Failed to retrieve weekly data for {symbol}, error code: {mt5.last_error()}")
        return None

    # Convert to DataFrame
    weekly_df = pd.DataFrame(weekly_bars)
    weekly_df['time'] = pd.to_datetime(weekly_df['time'], unit='s')
    weekly_df = weekly_df.set_index('time')
    weekly_df.sort_index(inplace=True)

    # Get previous week's data (second to last if we have current week)
    if len(weekly_df) >= 2:
        prev_week = weekly_df.iloc[-2]
        return {
            'prev_week_high': prev_week['high'],
            'prev_week_low': prev_week['low'],
            'prev_week_close': prev_week['close']
        }
    else:
        print("Not enough weekly bars to determine previous week's levels")
        return None

def plot_candlestick_chart(initial_df, symbol, refresh_interval=60):
    """Plot and continuously update a single live candlestick chart"""
    plt.style.use('dark_background')
    symbol_info = mt5.symbol_info(symbol)
    digits = symbol_info.digits if symbol_info is not None else 5

    # Create figure and subplots
    fig = plt.figure(figsize=(14, 8))
    price_ax = plt.subplot2grid((5, 1), (0, 0), rowspan=4)
    volume_ax = plt.subplot2grid((5, 1), (4, 0), rowspan=1, sharex=price_ax)
    title = fig.suptitle(f'{symbol} 10-Minute Chart', fontsize=16)

    plt.ion()  # Interactive mode
    plt.show(block=False)

    # Get daily price levels
    daily_levels = get_daily_levels(symbol)
    weekly_levels = get_weekly_levels(symbol)
    if daily_levels and weekly_levels:
        daily_levels.update(weekly_levels)
    if daily_levels:
        print(f"Daily levels for {symbol}:")
        for key, value in daily_levels.items():
            print(f"  {key}: {value}")
    else:
        print(f"Could not retrieve daily levels for {symbol}")

    if weekly_levels:
        print(f"Weekly levels for {symbol}:")
        for key, value in weekly_levels.items():
            print(f"  {key}: {value}")
    else:
        print(f"Could not retrieve weekly levels for {symbol}")

    # Use the initial dataframe as a starting point
    current_df = initial_df.copy() if initial_df is not None else pd.DataFrame()

    while True:
        try:
            # Get new data
            new_df = get_10min_data(symbol)
            print(f"New data retrieval: Shape={new_df.shape if new_df is not None else 'None'}")

            # Update current_df if new data is available
            if new_df is not None and not new_df.empty:
                current_df = new_df
            elif current_df.empty:
                print("No data available. Retrying...")
                plt.pause(0.1)
                continue

            # Update chart title with latest info
            last_price = current_df['Close'].iloc[-1]
            price_str = f"{last_price:.{digits}f}"
            market_time = current_df.index[-1]
            chart_time_str = market_time.strftime("%Y-%m-%d %H:%M:%S")
            title.set_text(f'{symbol} 10-Minute Chart\nLast Price: {price_str} | Latest Bar Time: {chart_time_str}')

            # Clear previous plot contents
            price_ax.clear()
            volume_ax.clear()

            # Calculate candle width
            if len(current_df) > 1:
                time_deltas = [(current_df.index[i] - current_df.index[i - 1]).total_seconds() / 60 for i in
                               range(1, len(current_df))]
                avg_delta = np.mean(time_deltas) if time_deltas else 10
                width = (avg_delta / (24 * 60)) * 0.8
            else:
                width = (10 / (24 * 60)) * 0.8  # Default width if less than 2 data points

            # Define colors for better visibility on dark background
            up_color = 'limegreen'
            down_color = 'crimson'
            wick_color = 'white'
            # Add these new colors to your existing color definitions
            reversal_bearish_color = 'orange'  # For bearish failure (high > prev high, close < prev low)
            reversal_bullish_color = 'cyan'  # For bullish failure (low < prev low, close > prev high)

            # Convert index to matplotlib date numbers for plotting
            dates = [mdates.date2num(idx) for idx in current_df.index]

            # Draw each candle and volume bar
            for i in range(len(current_df)):
                date = dates[i]
                open_price = float(current_df['Open'].iloc[i])
                high = float(current_df['High'].iloc[i])
                low = float(current_df['Low'].iloc[i])
                close = float(current_df['Close'].iloc[i])
                volume = float(current_df['Volume'].iloc[i])

                # Default coloring
                if close >= open_price:
                    color = up_color
                    vol_color = up_color
                else:
                    color = down_color
                    vol_color = down_color

                # Check for reversal patterns (skip first bar since we need a previous bar)
                if i > 0:
                    prev_high = float(current_df['High'].iloc[i - 1])
                    prev_low = float(current_df['Low'].iloc[i - 1])

                    # Bearish failure: high > prev high but close < prev low
                    if high > prev_high and close < prev_low:
                        color = reversal_bearish_color
                        vol_color = reversal_bearish_color

                    # Bullish failure: low < prev low but close > prev high
                    elif low < prev_low and close > prev_high:
                        color = reversal_bullish_color
                        vol_color = reversal_bullish_color

                # Calculate body positions
                body_bottom = min(open_price, close)
                body_height = max(abs(close - open_price), 0.000001)  # Ensure non-zero height

                # Draw candle body
                rect = plt.Rectangle(
                    (date - width / 2, body_bottom),
                    width,
                    body_height,
                    facecolor=color,
                    edgecolor='white',
                    linewidth=0.5,
                    alpha=1.0
                )
                price_ax.add_patch(rect)

                # Draw candle wick
                price_ax.plot(
                    [date, date],
                    [low, high],
                    color=wick_color,
                    linewidth=1.5,
                    solid_capstyle='round'
                )

                # Draw volume bar
                volume_ax.bar(
                    date,
                    volume,
                    width=width,
                    color=vol_color,
                    alpha=0.8
                )

            # Set proper axis limits with buffer for visibility
            price_min = current_df['Low'].min()
            price_max = current_df['High'].max()

            # Include daily levels in the range calculation if available
            if daily_levels:
                price_min = min(price_min, daily_levels['today_open'], daily_levels['yesterday_low'])
                price_max = max(price_max, daily_levels['today_open'], daily_levels['yesterday_high'])

            price_range = price_max - price_min
            price_margin = price_range * 0.05  # 5% margin

            # Explicitly set x and y axis limits
            price_ax.set_ylim(price_min - price_margin, price_max + price_margin)

            x_min = dates[0]
            x_max = dates[-1]
            x_margin = (x_max - x_min) * 0.05
            price_ax.set_xlim(x_min - x_margin, x_max + x_margin)

            # Draw daily levels
            if daily_levels:
                # Filter candles for current day
                today = datetime.now().date()
                current_day_candles = current_df[current_df.index.date == today]

                if not current_day_candles.empty:
                    # Define colors and styles for different levels
                    level_styles = {
                        'today_open': {'color': 'yellow', 'linestyle': '--', 'linewidth': 1.5, 'alpha': 0.8,
                                       'label': 'Daily Open'},
                        'yesterday_high': {'color': 'lime', 'linestyle': '-', 'linewidth': 1.5, 'alpha': 0.8,
                                           'label': 'Prev Day High'},
                        'yesterday_low': {'color': 'red', 'linestyle': '-', 'linewidth': 1.5, 'alpha': 0.8,
                                          'label': 'Prev Day Low'},
                        'prev_week_high': {'color': 'cyan', 'linestyle': '-.', 'linewidth': 2.0, 'alpha': 0.8,
                                           'label': 'Prev Week High'},
                        'prev_week_low': {'color': 'magenta', 'linestyle': '-.', 'linewidth': 2.0, 'alpha': 0.8,
                                          'label': 'Prev Week Low'},
                        'prev_week_close': {'color': 'white', 'linestyle': '-.', 'linewidth': 1.5, 'alpha': 0.8,
                                            'label': 'Prev Week Close'}
                    }

                    # Draw each level line and label
                    for level_name, style in level_styles.items():
                        level_value = daily_levels[level_name]

                        # Draw horizontal line
                        price_ax.axhline(y=level_value, color=style['color'],
                                         linestyle=style['linestyle'],
                                         linewidth=style['linewidth'],
                                         alpha=style['alpha'])

                        # Add text label
                        formatted_price = f"{level_value:.{digits}f}"
                        price_ax.text(x_min, level_value, f"{style['label']}: {formatted_price}",
                                      color=style['color'], fontsize=9,
                                      verticalalignment='bottom' if level_name != 'yesterday_low' else 'top',
                                      horizontalalignment='left', backgroundcolor='black', alpha=0.9)

            volume_max = current_df['Volume'].max()
            volume_ax.set_ylim(0, volume_max * 1.1)  # 10% margin on top

            # Format axes
            price_ax.set_ylabel(f'Price (Digits: {digits})')
            price_ax.grid(True, alpha=0.3)
            volume_ax.set_ylabel('Volume')
            volume_ax.grid(True, alpha=0.3)
            volume_ax.xaxis_date()
            volume_ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            plt.setp(volume_ax.get_xticklabels(), rotation=45, ha='right')
            plt.setp(price_ax.get_xticklabels(), visible=False)

            # Apply tight layout for better use of space
            plt.tight_layout()
            plt.subplots_adjust(top=0.90)  # More space for title

            # Force draw and refresh
            fig.canvas.draw()
            fig.canvas.flush_events()
            plt.pause(refresh_interval)

        except KeyboardInterrupt:
            print("\nChart plotting interrupted by user.")
            break
        except Exception as e:
            print(f"Error in chart plotting: {e}")
            import traceback
            print(traceback.format_exc())
            plt.pause(1)
            continue

    plt.close('all')


def main():
    if not mt5.initialize():
        print("Failed to connect to MetaTrader 5. Exiting.")
        return

    try:
        symbol = input("Enter the symbol to plot (e.g., EURUSD): ").upper()
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"Symbol {symbol} not found. Please check the symbol name.")
            return

        if not symbol_info.visible:
            print(f"Symbol {symbol} is not visible, trying to add it to MarketWatch...")
            if not mt5.symbol_select(symbol, True):
                print(f"Failed to add {symbol} to MarketWatch, error code: {mt5.last_error()}")
                return

        initial_data = get_10min_data(symbol)
        if initial_data is None or initial_data.empty:
            print(f"Failed to retrieve initial data for {symbol}. Exiting.")
            return

        # For debugging, you might reduce the refresh_interval
        refresh_interval = 3  # seconds
        plot_candlestick_chart(initial_data, symbol, refresh_interval)

    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        mt5.shutdown()
        print("MetaTrader 5 connection closed.")


if __name__ == "__main__":
    main()