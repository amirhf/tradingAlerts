"""
Data fetching functions for MT5 Chart Application
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, time
# Import the pivot and Asian session calculations
from pivots import calculate_fibonacci_pivots, get_pivot_levels
from asian_session import get_asian_session_range

def get_10min_data(symbol, num_bars=100):
    """
    Get 10-minute data for the specified symbol

    Args:
        symbol (str): The trading symbol to fetch data for
        num_bars (int): Number of bars to retrieve

    Returns:
        pandas.DataFrame: DataFrame with OHLC and volume data
    """
    timeframe = mt5.TIMEFRAME_M10
    bars = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)

    if bars is None or len(bars) == 0:
        print(f"Failed to retrieve data for {symbol}, error code: {mt5.last_error()}")
        return None

    # Convert to DataFrame
    df = pd.DataFrame(bars)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # Format according to symbol precision
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is not None:
        digits = symbol_info.digits
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = df[col].round(digits)

    # Set time as index and rename columns
    df = df.set_index('time')
    df.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'tick_volume': 'Volume'
    }, inplace=True)

    # Sort by time
    df.sort_index(inplace=True)

    return df


def get_price_levels(symbol):
    """
    Get important price levels including daily, weekly, pivot points, and Asian session ranges

    Args:
        symbol (str): The trading symbol to fetch data for

    Returns:
        dict: Dictionary containing price levels or None if data not available
    """
    # Get current date info
    today = datetime.now().date()

    # Get daily bars (last 10 days to ensure we have enough data for weekly calculations)
    ten_days_ago = today - timedelta(days=10)
    daily_bars = mt5.copy_rates_range(
        symbol,
        mt5.TIMEFRAME_D1,
        datetime.combine(ten_days_ago, time(0)),
        datetime.now()
    )

    if daily_bars is None or len(daily_bars) == 0:
        print(f"Failed to retrieve daily data for {symbol}, error code: {mt5.last_error()}")
        return None

    # Convert to DataFrame
    daily_df = pd.DataFrame(daily_bars)
    daily_df['time'] = pd.to_datetime(daily_df['time'], unit='s')
    daily_df = daily_df.set_index('time')
    daily_df.sort_index(inplace=True)

    # Get weekly data directly using MT5's weekly timeframe
    # Get a month's worth of weekly data to ensure we have the previous week
    weekly_bars = mt5.copy_rates_from_pos(
        symbol,
        mt5.TIMEFRAME_W1,
        0,
        5  # Get last 5 weeks to ensure we have enough data
    )

    if weekly_bars is None or len(weekly_bars) < 2:
        print(f"Failed to retrieve weekly data for {symbol}, error code: {mt5.last_error()}")
        prev_week_high = None
        prev_week_low = None
    else:
        # Convert to DataFrame
        weekly_df = pd.DataFrame(weekly_bars)
        weekly_df['time'] = pd.to_datetime(weekly_df['time'], unit='s')
        weekly_df = weekly_df.sort_values('time', ascending=False)

        # Previous week is the second row (index 1) since they're sorted newest first
        prev_week_data = weekly_df.iloc[1]  # Previous completed week
        prev_week_high = prev_week_data['high']
        prev_week_low = prev_week_data['low']

    # Initialize the price levels dictionary
    price_levels = {}

    # If we have at least 2 bars, add the standard levels
    if len(daily_df) >= 2:
        today_bar = daily_df.iloc[-1]
        yesterday_bar = daily_df.iloc[-2]

        # Add standard price levels
        price_levels.update({
            'today_open': today_bar['open'],
            'yesterday_open': yesterday_bar['open'],
            'yesterday_high': yesterday_bar['high'],
            'yesterday_low': yesterday_bar['low'],
            'yesterday_close': yesterday_bar['close']
        })

        # Add weekly levels if available
        if prev_week_high is not None:
            price_levels['prev_week_high'] = prev_week_high
            price_levels['prev_week_low'] = prev_week_low
    else:
        print("Not enough daily bars to determine standard price levels")
        return price_levels  # Return empty dict if we can't get standard levels

    # Add pivot levels
    try:
        # Get pivot levels for daily and weekly timeframes
        daily_pivots, weekly_pivots, _ = get_pivot_levels(symbol)

        # Add daily pivot levels if available
        if daily_pivots.get("current") and daily_pivots["current"].get("levels"):
            daily_levels = daily_pivots["current"]["levels"]
            for level_name, level_value in daily_levels.items():
                price_levels[f'daily_pivot_{level_name}'] = level_value

        # Add weekly pivot levels if available
        if weekly_pivots.get("current") and weekly_pivots["current"].get("levels"):
            weekly_levels = weekly_pivots["current"]["levels"]
            for level_name, level_value in weekly_levels.items():
                price_levels[f'weekly_pivot_{level_name}'] = level_value
    except Exception as e:
        print(f"Error adding pivot levels: {e}")

    # Add Asian session ranges
    try:
        # Current day Asian session
        current_asian = get_asian_session_range(symbol, 0)
        if current_asian:
            price_levels['asian_high'] = current_asian['high']
            price_levels['asian_low'] = current_asian['low']
            price_levels['asian_mid'] = current_asian['mid']

    except Exception as e:
        print(f"Error adding Asian session levels: {e}")

    return price_levels