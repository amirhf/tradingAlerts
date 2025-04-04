"""
Chart rendering functions for MT5 Chart Application
"""
import matplotlib
from datetime import datetime

from candle_patterns import detect_reversal_pattern
from notifications import send_notification

matplotlib.use('TkAgg')  # Force using TkAgg backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import MetaTrader5 as mt5

from data_fetcher import get_10min_data, get_price_levels
from candle_patterns import analyse_candle

def plot_candlestick_chart(initial_df, symbol, refresh_interval=60, send_notifications=True):
    """
    Plot and continuously update a live candlestick chart with daily levels

    Args:
        initial_df (pandas.DataFrame): Initial dataframe with OHLC data
        symbol (str): The trading symbol
        refresh_interval (int): Chart refresh interval in seconds
        send_notifications (bool): Whether to send email notifications for signals
    """
    # Setup style and get symbol information
    plt.style.use('dark_background')
    symbol_info = mt5.symbol_info(symbol)
    digits = symbol_info.digits if symbol_info is not None else 5

    # Create figure and subplots
    fig = plt.figure(figsize=(14, 8))
    price_ax = plt.subplot2grid((5, 1), (0, 0), rowspan=4)
    title = fig.suptitle(f'{symbol} 10-Minute Chart', fontsize=16)

    # Setup interactive mode
    plt.ion()
    plt.show(block=False)

    # Get price levels (daily, weekly, pivot, and asian session)
    price_levels = get_price_levels(symbol)
    if price_levels:
        print(f"Price levels for {symbol}:")
        for key, value in price_levels.items():
            print(f"  {key}: {value:.{digits}f}")
    else:
        print(f"Could not retrieve price levels for {symbol}")
        price_levels = {}  # Use empty dict if levels can't be retrieved

    # Use the initial dataframe as a starting point
    current_df = initial_df.copy() if initial_df is not None else None

    # Track the last candle we've seen to detect new closes
    last_seen_candle_time = None
    if current_df is not None and not current_df.empty:
        last_seen_candle_time = current_df.index[-1]

    # Main chart update loop
    while True:
        try:
            # Get updated data
            new_df = get_10min_data(symbol)

            # Update current_df if new data is available
            if new_df is not None and not new_df.empty:
                # Check for closed candles
                if current_df is not None and not current_df.empty and last_seen_candle_time is not None:
                    # Compare the latest candle timestamps
                    if new_df.index[-1] > last_seen_candle_time:
                        # A new candle has appeared, which means the previous one has closed
                        # The closed candle would be the last one from the previous dataframe
                        closed_candle = current_df.iloc[-1]

                        # Ensure we have enough data for analysis
                        if len(current_df) >= 3:
                            closed_time = last_seen_candle_time

                            # Create a dataframe slice with the necessary candles
                            candle_type, touch_levels = analyse_candle(
                                current_df,
                                index=-1,
                                lookback=2,
                                price_levels=price_levels
                            )

                            print(f"{symbol} Candle closed at {closed_time}, type: {candle_type}, touch levels: {touch_levels}")

                            # Send notification if it's a significant candle and notifications are enabled
                            if send_notifications and candle_type != "none" and len(touch_levels) >= 1:
                                send_notification(
                                    subject=f"{symbol}: {candle_type.upper()} Pattern Detected",
                                    body=f"Symbol: {symbol}\nTime: {closed_time}\nPattern: {candle_type}\nTouched levels: {touch_levels}\n\nPrice: {closed_candle['Close']}",
                                )

                        # Update our tracking variable to the latest candle time
                        last_seen_candle_time = new_df.index[-1]

                # Update the current dataframe with the new data
                current_df = new_df
            elif current_df is None or current_df.empty:
                print("No data available. Retrying...")
                plt.pause(0.1)
                continue

            # Update chart with latest data
            update_chart(fig, price_ax, title, current_df, symbol, digits, price_levels)

            # Pause for the specified refresh interval
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


def update_chart(fig, price_ax, title, df, symbol, digits, price_levels):
    """
    Update chart with new data

    Args:
        fig: Matplotlib figure object
        price_ax: Price axis subplot
        title: Chart title object
        df: DataFrame with current OHLC data
        symbol: Trading symbol
        digits: Price decimal digits
        price_levels: Dictionary with daily/weekly price levels
    """
    # Update chart title with latest info
    last_price = df['Close'].iloc[-1]
    price_str = f"{last_price:.{digits}f}"
    market_time = df.index[-1]
    chart_time_str = market_time.strftime("%Y-%m-%d %H:%M:%S")
    title.set_text(f'{symbol} 10-Minute Chart\nLast Price: {price_str} | Latest Bar Time: {chart_time_str}')

    # Clear previous plot contents
    price_ax.clear()

    # Convert index to matplotlib date numbers for plotting
    dates = [mdates.date2num(idx) for idx in df.index]

    # Calculate candle width
    if len(df) > 1:
        time_deltas = [(df.index[i] - df.index[i - 1]).total_seconds() / 60 for i in range(1, len(df))]
        avg_delta = np.mean(time_deltas) if time_deltas else 10
        width = (avg_delta / (24 * 60)) * 0.8
    else:
        width = (10 / (24 * 60)) * 0.8  # Default width if less than 2 data points

    # Draw candles and volume bars
    draw_candles_and_volume(price_ax, df, dates, width)

    # Calculate and set axis limits
    set_axis_limits(price_ax, df, dates, price_levels)

    # Draw price levels if available
    if price_levels:
        draw_price_levels(price_ax, price_levels, dates[0], digits)

    # Format axes
    format_axes(price_ax, digits)

    # Apply tight layout and refresh
    # plt.tight_layout()
    plt.subplots_adjust(top=0.90)  # More space for title
    fig.canvas.draw()
    fig.canvas.flush_events()

def draw_price_levels(price_ax, price_levels, x_min, digits):
    """Draw price levels on the chart"""
    level_styles = {
        # Standard levels
        'today_open': {'color': 'yellow', 'linestyle': '--', 'linewidth': 1.5, 'alpha': 0.8, 'label': 'Daily Open',
                       'valign': 'bottom'},
        'yesterday_open': {'color': 'orange', 'linestyle': '--', 'linewidth': 1.5, 'alpha': 0.8,
                           'label': 'Prev Day Open', 'valign': 'bottom'},
        'yesterday_high': {'color': 'lime', 'linestyle': '-', 'linewidth': 1.5, 'alpha': 0.8, 'label': 'Prev Day High',
                           'valign': 'bottom'},
        'yesterday_low': {'color': 'red', 'linestyle': '-', 'linewidth': 1.5, 'alpha': 0.8, 'label': 'Prev Day Low',
                          'valign': 'top'},
        'prev_week_high': {'color': 'cyan', 'linestyle': '-.', 'linewidth': 2.0, 'alpha': 0.8,
                           'label': 'Prev Week High', 'valign': 'bottom'},
        'prev_week_low': {'color': 'magenta', 'linestyle': '-.', 'linewidth': 2.0, 'alpha': 0.8,
                          'label': 'Prev Week Low', 'valign': 'top'},

        # Daily Pivot levels
        'daily_pivot_P': {'color': 'white', 'linestyle': '-', 'linewidth': 1.5, 'alpha': 0.8,
                          'label': 'Daily Pivot', 'valign': 'bottom'},
        'daily_pivot_R1': {'color': 'lightgreen', 'linestyle': '-', 'linewidth': 1.0, 'alpha': 0.8,
                           'label': 'Daily R1', 'valign': 'bottom'},
        'daily_pivot_R2': {'color': 'lightgreen', 'linestyle': '-', 'linewidth': 1.0, 'alpha': 0.8,
                           'label': 'Daily R2', 'valign': 'bottom'},
        'daily_pivot_S1': {'color': 'lightcoral', 'linestyle': '-', 'linewidth': 1.0, 'alpha': 0.8,
                           'label': 'Daily S1', 'valign': 'top'},
        'daily_pivot_S2': {'color': 'lightcoral', 'linestyle': '-', 'linewidth': 1.0, 'alpha': 0.8,
                           'label': 'Daily S2', 'valign': 'top'},

        # Weekly Pivot levels
        'weekly_pivot_P': {'color': 'white', 'linestyle': '--', 'linewidth': 1.5, 'alpha': 0.8,
                           'label': 'Weekly Pivot', 'valign': 'bottom'},
        'weekly_pivot_R1': {'color': 'lightgreen', 'linestyle': '--', 'linewidth': 1.0, 'alpha': 0.8,
                            'label': 'Weekly R1', 'valign': 'bottom'},
        'weekly_pivot_R2': {'color': 'lightgreen', 'linestyle': '--', 'linewidth': 1.0, 'alpha': 0.8,
                            'label': 'Weekly R2', 'valign': 'bottom'},
        'weekly_pivot_S1': {'color': 'lightcoral', 'linestyle': '--', 'linewidth': 1.0, 'alpha': 0.8,
                            'label': 'Weekly S1', 'valign': 'top'},
        'weekly_pivot_S2': {'color': 'lightcoral', 'linestyle': '--', 'linewidth': 1.0, 'alpha': 0.8,
                            'label': 'Weekly S2', 'valign': 'top'},

        # Asian session levels
        'asian_high': {'color': 'skyblue', 'linestyle': '-', 'linewidth': 1.5, 'alpha': 0.8,
                       'label': 'Asian High', 'valign': 'bottom'},
        'asian_low': {'color': 'skyblue', 'linestyle': '-', 'linewidth': 1.5, 'alpha': 0.8,
                      'label': 'Asian Low', 'valign': 'top'},
        'asian_mid': {'color': 'skyblue', 'linestyle': '--', 'linewidth': 1.0, 'alpha': 0.8,
                      'label': 'Asian Mid', 'valign': 'middle'},
        'prev_asian_high': {'color': 'steelblue', 'linestyle': '-', 'linewidth': 1.0, 'alpha': 0.7,
                            'label': 'Prev Asian High', 'valign': 'bottom'},
        'prev_asian_low': {'color': 'steelblue', 'linestyle': '-', 'linewidth': 1.0, 'alpha': 0.7,
                           'label': 'Prev Asian Low', 'valign': 'top'},
        'prev_asian_mid': {'color': 'steelblue', 'linestyle': '--', 'linewidth': 1.0, 'alpha': 0.7,
                           'label': 'Prev Asian Mid', 'valign': 'middle'}
    }

    levels_to_draw = []
    for level_name, style in level_styles.items():
        if level_name in price_levels:
            levels_to_draw.append({
                'name': level_name,
                'value': price_levels[level_name],
                'style': style
            })

    # Sort levels by value (highest to lowest) to help with label placement
    levels_to_draw.sort(key=lambda x: x['value'], reverse=True)

    # Ensure labels don't overlap too much
    min_gap_pct = 0.01
    price_range = price_ax.get_ylim()[1] - price_ax.get_ylim()[0]
    min_gap = price_range * min_gap_pct

    for i in range(1, len(levels_to_draw)):
        curr = levels_to_draw[i]
        prev = levels_to_draw[i - 1]
        if prev['value'] - curr['value'] < min_gap:
            if prev['style']['valign'] == curr['style']['valign']:
                curr['style']['valign'] = 'top' if prev['style']['valign'] == 'bottom' else 'bottom'

    # Draw the levels
    for level_info in levels_to_draw:
        level_name = level_info['name']
        level_value = level_info['value']
        style = level_info['style']

        price_ax.axhline(y=level_value, color=style['color'],
                         linestyle=style['linestyle'],
                         linewidth=style['linewidth'],
                         alpha=style['alpha'])

        formatted_price = f"{level_value:.{digits}f}"
        price_ax.text(x_min, level_value, f"{style['label']}: {formatted_price}",
                      color=style['color'], fontsize=9,
                      verticalalignment=style['valign'],
                      horizontalalignment='left', backgroundcolor='black', alpha=0.9)


def draw_candles_and_volume(price_ax, df, dates, width):
    """Draw candlesticks and volume bars"""
    # Define colors for up and down candles
    up_color = 'limegreen'
    down_color = 'crimson'
    wick_color = 'white'
    reversal_bearish_color = 'orange'  # For bearish failure
    reversal_bullish_color = 'white'  # For bullish failure

    # Draw each candle and volume bar
    for i in range(len(df)):
        date = dates[i]
        open_price = float(df['Open'].iloc[i])
        high = float(df['High'].iloc[i])
        low = float(df['Low'].iloc[i])
        close = float(df['Close'].iloc[i])
        volume = float(df['Volume'].iloc[i])

        # Determine if it's an up or down candle
        if close >= open_price:
            color = up_color
            body_bottom = open_price
            body_height = max(close - open_price, 0.000001)
        else:
            color = down_color
            body_bottom = close
            body_height = max(open_price - close, 0.000001)

        if i > 0:
            is_bullish_reversal, is_bearish_reversal  = detect_reversal_pattern(df, i)
            if is_bearish_reversal:
                color = reversal_bearish_color
            elif is_bullish_reversal:
                color = reversal_bullish_color

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


def set_axis_limits(price_ax, df, dates, price_levels):
    """Calculate and set axis limits"""
    price_min = df['Low'].min()
    price_max = df['High'].max()

    if price_levels:
        # Include all price levels in the axis limits calculation
        for level_name, level_value in price_levels.items():
            # Skip if the level is None
            if level_value is not None:
                price_min = min(price_min, level_value)
                price_max = max(price_max, level_value)

        # Add a small margin to ensure all levels are visible
        range_size = price_max - price_min
        price_min -= range_size * 0.02  # 2% margin at bottom
        price_max += range_size * 0.02  # 2% margin at top

    # Set y-axis limits
    price_ax.set_ylim(price_min, price_max)

    # Set x-axis limits
    if len(dates) > 0:
        price_ax.set_xlim(dates[0], dates[-1])


def format_axes(price_ax, digits):
    """Format chart axes"""
    price_ax.set_ylabel(f'Price (Digits: {digits})')
    price_ax.grid(True, alpha=0.3)
    plt.setp(price_ax.get_xticklabels(), visible=False)