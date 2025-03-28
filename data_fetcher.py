"""
Data fetching functions for MT5 Chart Application
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, time, date
# Import the pivot and Asian session calculations
from pivots import calculate_fibonacci_pivots, get_pivot_levels
from asian_session import get_asian_session_range
import math

# Global variables to track when levels were last updated
_last_daily_update_date = None
_last_weekly_update_date = None
_cached_daily_levels = {}
_cached_weekly_levels = {}
_cached_pivot_levels = {}
_cached_asian_levels = {}
_asian_session_status = {}

def get_mt5_server_time():
    """
    Get the current time from the MT5 server to ensure timezone alignment

    Returns:
        datetime: Current MT5 server time or local time if server time is unavailable
    """
    try:
        # Method 1: Try to get time from a recent tick for a major symbol
        last_tick = mt5.symbol_info_tick("EURUSD")
        if last_tick is not None and hasattr(last_tick, 'time'):
            # Convert from timestamp to datetime
            server_time = datetime.fromtimestamp(last_tick.time)
            return server_time

        # Method 2: Try to get time from recent candle data
        candles = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M1, 0, 1)
        if candles is not None and len(candles) > 0:
            # Convert from timestamp to datetime
            server_time = datetime.fromtimestamp(candles[0]['time'])
            return server_time

        # Method 3: Use local time, but print a warning
        print("Warning: Could not determine MT5 server time, using local time")
        return datetime.now()

    except Exception as e:
        print(f"Error getting MT5 server time: {e}, falling back to local time")
        return datetime.now()


def get_10min_data(symbol, num_bars=100):
    """
    Get 10-minute data for the specified symbol

    Args:
        symbol (str): The trading symbol to fetch data for
        num_bars (int): Number of bars to retrieve

    Returns:
        pandas.DataFrame: DataFrame with OHLC and volume data
    """
    # First try using copy_rates_from_pos which gets the most recent data
    timeframe = mt5.TIMEFRAME_M10
    bars = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)

    if bars is None or len(bars) == 0:
        print(f"Failed to retrieve data for {symbol}, error code: {mt5.last_error()}")
        return None

    # Convert to DataFrame
    df = pd.DataFrame(bars)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # Check for gaps in the data
    if len(df) > 1:
        # Sort by time to ensure proper order
        df = df.sort_values('time')

        # Calculate time differences between consecutive bars
        time_diffs = [(df['time'].iloc[i] - df['time'].iloc[i-1]).total_seconds() / 60
                     for i in range(1, len(df))]

        # Check if there are any gaps larger than expected (> 15 minutes for 10-minute bars)
        has_gaps = any(diff > 15 for diff in time_diffs)

        # If we detect gaps and we have at least some data, try an alternative approach
        if has_gaps and len(df) > 0:
            print(f"Detected gaps in data for {symbol}, trying alternative retrieval method...")

            # Get the earliest and latest timestamps
            earliest_time = df['time'].min()
            latest_time = df['time'].max()

            # Extend the range to ensure we get all data
            start_time = earliest_time - pd.Timedelta(minutes=30)
            end_time = latest_time + pd.Timedelta(minutes=30)

            # Try to get data within this specific range to fill gaps
            try:
                range_bars = mt5.copy_rates_range(
                    symbol,
                    timeframe,
                    start_time.to_pydatetime(),
                    end_time.to_pydatetime()
                )

                if range_bars is not None and len(range_bars) > 0:
                    range_df = pd.DataFrame(range_bars)
                    range_df['time'] = pd.to_datetime(range_df['time'], unit='s')

                    # Combine with original data and remove duplicates
                    combined_df = pd.concat([df, range_df]).drop_duplicates(subset=['time'])
                    df = combined_df
            except Exception as e:
                print(f"Error trying to fill data gaps: {e}")

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


def should_update_daily_levels(symbol):
    """
    Check if daily levels should be updated

    Args:
        symbol (str): The trading symbol

    Returns:
        bool: True if levels should be updated, False otherwise
    """
    global _last_daily_update_date

    # Get current server time from MT5
    server_time = get_mt5_server_time()
    current_date = server_time.date()

    # Always update if we haven't updated today
    if _last_daily_update_date is None or _last_daily_update_date < current_date:
        print(f"Daily levels update check: New day detected ({current_date} vs last update {_last_daily_update_date})")
        _last_daily_update_date = current_date
        return True

    return False


def should_update_weekly_levels(symbol):
    """
    Check if weekly levels should be updated

    Args:
        symbol (str): The trading symbol

    Returns:
        bool: True if levels should be updated, False otherwise
    """
    global _last_weekly_update_date

    # Get current server time from MT5
    server_time = get_mt5_server_time()
    current_date = server_time.date()

    # Get current ISO week
    current_week = current_date.isocalendar()[1]

    # Always update if we haven't updated this week
    if _last_weekly_update_date is None or _last_weekly_update_date.isocalendar()[1] < current_week:
        print(f"Weekly levels update check: New week detected (week {current_week} vs last update week {_last_weekly_update_date.isocalendar()[1] if _last_weekly_update_date else None})")
        _last_weekly_update_date = current_date
        return True

    return False


def is_asian_session_complete():
    """
    Check if the Asian session for today is complete (after 02:00 EST)

    Returns:
        bool: True if the Asian session is complete, False otherwise
    """
    global _asian_session_status

    # Get current time
    current_time = get_mt5_server_time()
    current_date = current_time.date()

    # If we've already checked today and confirmed Asian session is complete, return cached result
    if current_date in _asian_session_status and _asian_session_status[current_date]:
        return True

    # Check if we're likely past Asian session hours
    # Most brokers show 7-9 AM in their time when Asian session ends
    # This corresponds to ~2AM EST (rough approximation)

    # Get the hour in broker time
    broker_hour = current_time.hour

    # For most brokers, Asian session is complete after 7 AM broker time
    is_complete = broker_hour >= 7

    # Update our cache
    _asian_session_status[current_date] = is_complete

    # Cleanup old dates from cache
    for old_date in list(_asian_session_status.keys()):
        if old_date < current_date:
            del _asian_session_status[old_date]

    return is_complete


def fetch_daily_candles(symbol, days_back=10):
    """Fetch daily candles for the symbol"""
    server_time = get_mt5_server_time()
    current_date = server_time.date()
    days_ago = current_date - timedelta(days=days_back)

    # Get daily bars
    daily_bars = mt5.copy_rates_range(
        symbol,
        mt5.TIMEFRAME_D1,
        datetime.combine(days_ago, time(0)),
        server_time
    )

    if daily_bars is None or len(daily_bars) == 0:
        print(f"Failed to retrieve daily data for {symbol}")
        return None

    # Convert to DataFrame
    daily_df = pd.DataFrame(daily_bars)
    daily_df['time'] = pd.to_datetime(daily_df['time'], unit='s')
    daily_df = daily_df.set_index('time')
    daily_df.sort_index(inplace=True)

    return daily_df


def update_daily_levels(symbol):
    """Update daily levels for the symbol"""
    global _cached_daily_levels

    try:
        daily_df = fetch_daily_candles(symbol)
        if daily_df is None or len(daily_df) < 2:
            print(f"Not enough daily bars for {symbol}")
            return {}

        # Today and yesterday bars
        today_bar = daily_df.iloc[-1]
        yesterday_bar = daily_df.iloc[-2]

        # Update daily levels
        daily_levels = {
            'today_open': today_bar['open'],
            'yesterday_open': yesterday_bar['open'],
            'yesterday_high': yesterday_bar['high'],
            'yesterday_low': yesterday_bar['low'],
            'yesterday_close': yesterday_bar['close']
        }

        # Cache the updated levels
        _cached_daily_levels[symbol] = daily_levels
        print(f"Daily levels updated for {symbol}: {daily_levels}")

        return daily_levels

    except Exception as e:
        print(f"Error updating daily levels for {symbol}: {e}")
        return {}


def update_asian_levels(symbol):
    """Update Asian session levels for the symbol"""
    global _cached_asian_levels

    try:
        # Get current date
        current_date = get_mt5_server_time().date()

        # Check for Asian session completion
        if is_asian_session_complete():
            # Get current day Asian session
            current_asian = get_asian_session_range(symbol, 0)
            if current_asian:
                asian_levels = {
                    'date': current_date,
                    'asian_high': current_asian['high'],
                    'asian_low': current_asian['low'],
                    'asian_mid': current_asian['mid']
                }

                # Cache the updated levels
                _cached_asian_levels[symbol] = asian_levels
                print(f"Asian levels updated for {symbol}: {asian_levels}")

                return asian_levels
            else:
                print(f"No Asian session data available for {symbol}")
        else:
            print(f"Asian session not complete yet for {symbol}")

        return {}

    except Exception as e:
        print(f"Error updating Asian levels for {symbol}: {e}")
        return {}


def get_price_levels(symbol):
    """
    Get important price levels including daily, weekly, pivot points, and Asian session ranges

    Args:
        symbol (str): The trading symbol to fetch data for

    Returns:
        dict: Dictionary containing price levels or None if data not available
    """
    # Initialize empty dictionary for the levels
    price_levels = {}

    # Log the begin of level fetching
    current_time = get_mt5_server_time()
    print(f"\n--- Fetching price levels for {symbol} at {current_time} ---")

    # Update daily levels if needed
    if should_update_daily_levels(symbol):
        daily_levels = update_daily_levels(symbol)
    else:
        daily_levels = _cached_daily_levels.get(symbol, {})

    # Add daily levels to price_levels
    price_levels.update(daily_levels)

    # Update weekly levels if needed
    if should_update_weekly_levels(symbol):
        try:
            # Get weekly data
            weekly_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 0, 5)

            if weekly_bars is not None and len(weekly_bars) >= 2:
                # Convert to DataFrame
                weekly_df = pd.DataFrame(weekly_bars)
                weekly_df['time'] = pd.to_datetime(weekly_df['time'], unit='s')
                weekly_df = weekly_df.sort_values('time', ascending=False)

                # Previous week is the second row (index 1) since they're sorted newest first
                prev_week_data = weekly_df.iloc[1]  # Previous completed week
                prev_week_high = prev_week_data['high']
                prev_week_low = prev_week_data['low']

                # Update weekly levels
                weekly_levels = {
                    'prev_week_high': prev_week_high,
                    'prev_week_low': prev_week_low
                }

                # Cache the updated weekly levels
                _cached_weekly_levels[symbol] = weekly_levels
                print(f"Weekly levels updated for {symbol}: {weekly_levels}")
            else:
                weekly_levels = _cached_weekly_levels.get(symbol, {})
                print(f"Using cached weekly levels for {symbol}")
        except Exception as e:
            print(f"Error updating weekly levels: {e}")
            weekly_levels = _cached_weekly_levels.get(symbol, {})
    else:
        weekly_levels = _cached_weekly_levels.get(symbol, {})

    # Add weekly levels to price_levels
    price_levels.update(weekly_levels)

    # Update pivot levels - do this daily
    if should_update_daily_levels(symbol) or symbol not in _cached_pivot_levels:
        try:
            # Get pivot levels
            daily_pivots, weekly_pivots, _ = get_pivot_levels(symbol)

            pivot_levels = {}

            # Add daily pivot levels if available
            if daily_pivots.get("current") and daily_pivots["current"].get("levels"):
                daily_levels_data = daily_pivots["current"]["levels"]
                for level_name, level_value in daily_levels_data.items():
                    pivot_levels[f'daily_pivot_{level_name}'] = level_value

            # Add weekly pivot levels if available
            if weekly_pivots.get("current") and weekly_pivots["current"].get("levels"):
                weekly_levels_data = weekly_pivots["current"]["levels"]
                for level_name, level_value in weekly_levels_data.items():
                    pivot_levels[f'weekly_pivot_{level_name}'] = level_value

            # Cache the updated pivot levels
            _cached_pivot_levels[symbol] = pivot_levels
            print(f"Pivot levels updated for {symbol}: {pivot_levels}")
        except Exception as e:
            print(f"Error updating pivot levels: {e}")
            pivot_levels = _cached_pivot_levels.get(symbol, {})
    else:
        pivot_levels = _cached_pivot_levels.get(symbol, {})

    # Add pivot levels to price_levels
    price_levels.update(pivot_levels)

    # Update Asian session levels - check if the Asian session is complete
    # Only update if we don't have today's levels or if they're not in the price levels
    current_date = current_time.date()
    asian_levels = _cached_asian_levels.get(symbol, {})

    # Check if Asian levels are needed and available
    asian_complete = is_asian_session_complete()
    if asian_complete:
        # Check if we need to update (new day or missing levels)
        if not asian_levels or asian_levels.get('date') != current_date:
            asian_levels = update_asian_levels(symbol)

        # Add Asian levels to price_levels if they exist
        if asian_levels and 'asian_high' in asian_levels:
            # Add only the price values (skip metadata like 'date')
            for key in ['asian_high', 'asian_low', 'asian_mid']:
                if key in asian_levels:
                    price_levels[key] = asian_levels[key]

            print(f"Asian levels added to price_levels for {symbol}: {asian_levels}")
        else:
            print(f"No Asian levels available for {symbol} today")
    else:
        print(f"Asian session not complete for {symbol}, not adding Asian levels")

    # Log all the levels we're returning
    print(f"Final price levels for {symbol}: {price_levels}")
    print(f"Total levels: {len(price_levels)}")

    return price_levels