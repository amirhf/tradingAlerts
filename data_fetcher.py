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
import pytz

# Global variables to track when levels were last updated
_last_daily_candle_time = None
_last_weekly_candle_time = None
_cached_daily_levels = {}
_cached_weekly_levels = {}
_cached_pivot_levels = {}
_cached_asian_levels = {}
_asian_session_status = {}

def is_after_2am_est():
    """
    Check if the current time is after 2:00 AM EST (Eastern Standard Time)
    This is specifically for determining Asian session completion

    Returns:
        bool: True if current time is after 2:00 AM EST, False otherwise
    """
    # Get current local time
    local_time = datetime.now()

    # Define EST timezone (UTC-5)
    est = pytz.timezone('US/Eastern')

    # Convert local time to EST
    local_time_aware = pytz.timezone('UTC').localize(local_time).astimezone(pytz.utc)
    est_time = local_time_aware.astimezone(est)

    # Check if time is after 2 AM EST
    is_after_2am = est_time.hour >= 2

    print(f"Current EST time: {est_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Is after 2 AM EST: {is_after_2am}")

    return is_after_2am

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
    global _last_daily_candle_time

    # Fetch the latest daily candles
    try:
        # Get today and yesterday's daily candles (we need at least 2)
        daily_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3)

        if daily_bars is None or len(daily_bars) < 2:
            print(f"Not enough daily candles for {symbol}, can't determine if update needed")
            return False

        # Convert to DataFrame
        daily_df = pd.DataFrame(daily_bars)
        daily_df['time'] = pd.to_datetime(daily_df['time'], unit='s')
        daily_df = daily_df.sort_values('time', ascending=False)

        # Get the time of the most recent daily candle
        current_daily_candle_time = daily_df.iloc[0]['time']

        # If this is our first check or the newest candle time is different from our last check
        # it means a new daily candle has been formed in MT5's time
        if _last_daily_candle_time is None or current_daily_candle_time > _last_daily_candle_time:
            print(f"New daily candle detected: {current_daily_candle_time} vs last: {_last_daily_candle_time}")
            _last_daily_candle_time = current_daily_candle_time
            return True

        return False
    except Exception as e:
        print(f"Error checking daily candle update: {e}")
        return False

def should_update_weekly_levels(symbol):
    """
    Check if weekly levels should be updated

    Args:
        symbol (str): The trading symbol

    Returns:
        bool: True if levels should be updated, False otherwise
    """
    global _last_weekly_candle_time

    # Fetch the latest weekly candles
    try:
        # Get the latest weekly candles (we need at least 2)
        weekly_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 0, 3)

        if weekly_bars is None or len(weekly_bars) < 2:
            print(f"Not enough weekly candles for {symbol}, can't determine if update needed")
            return False

        # Convert to DataFrame
        weekly_df = pd.DataFrame(weekly_bars)
        weekly_df['time'] = pd.to_datetime(weekly_df['time'], unit='s')
        weekly_df = weekly_df.sort_values('time', ascending=False)

        # Get the time of the most recent weekly candle
        current_weekly_candle_time = weekly_df.iloc[0]['time']

        # If this is our first check or the newest candle time is different from our last check
        # it means a new weekly candle has been formed in MT5's time
        if _last_weekly_candle_time is None or current_weekly_candle_time > _last_weekly_candle_time:
            print(f"New weekly candle detected: {current_weekly_candle_time} vs last: {_last_weekly_candle_time}")
            _last_weekly_candle_time = current_weekly_candle_time
            return True

        return False
    except Exception as e:
        print(f"Error checking weekly candle update: {e}")
        return False

def is_asian_session_complete():
    """
    Check if the Asian session for today is complete (after 02:00 EST)

    Returns:
        bool: True if the Asian session is complete, False otherwise
    """
    # Simply check if current time is after 2 AM EST
    return is_after_2am_est()

def fetch_daily_candles(symbol, days_back=10):
    """Fetch daily candles for the symbol"""
    # Get daily bars
    daily_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, days_back)

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
        # Get the daily candles (most recent first)
        daily_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3)

        if daily_bars is None or len(daily_bars) < 2:
            print(f"Not enough daily bars for {symbol}")
            return {}

        # Convert to DataFrame
        daily_df = pd.DataFrame(daily_bars)
        daily_df['time'] = pd.to_datetime(daily_df['time'], unit='s')

        # Sort by time (most recent first)
        daily_df = daily_df.sort_values('time', ascending=False)

        # Today and yesterday bars
        today_bar = daily_df.iloc[0]
        yesterday_bar = daily_df.iloc[1]

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
        current_date = datetime.now().date()

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


def update_all_levels(symbol):
    """
    Update all levels (daily, weekly, pivot) for the symbol using consistent data

    Args:
        symbol (str): Trading symbol to update levels for

    Returns:
        dict: Combined dictionary of all updated levels
    """
    all_levels = {}

    try:
        # 1. Get daily candles - get enough for both daily levels and pivot calculations
        daily_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 5)

        if daily_bars is None or len(daily_bars) < 3:
            print(f"Not enough daily bars for {symbol} to calculate levels")
            return all_levels

        # Convert to DataFrame
        daily_df = pd.DataFrame(daily_bars)
        daily_df['time'] = pd.to_datetime(daily_df['time'], unit='s')
        daily_df = daily_df.sort_values('time', ascending=False)

        # 2. Extract today and yesterday's data for daily levels
        today_bar = daily_df.iloc[0]  # Most recent candle
        yesterday_bar = daily_df.iloc[1]  # Second most recent candle

        # Calculate daily levels
        daily_levels = {
            'today_open': today_bar['open'],
            'yesterday_open': yesterday_bar['open'],
            'yesterday_high': yesterday_bar['high'],
            'yesterday_low': yesterday_bar['low'],
            'yesterday_close': yesterday_bar['close']
        }

        # Add daily levels to result
        all_levels.update(daily_levels)

        # 3. Calculate pivot levels using yesterday's data
        # Create OHLC dict that pivots.calculate_fibonacci_pivots expects
        yesterday_ohlc = {
            "high": yesterday_bar['high'],
            "low": yesterday_bar['low'],
            "close": yesterday_bar['close']
        }

        # Calculate daily pivot points directly
        from pivots import calculate_fibonacci_pivots
        daily_pivot_levels = calculate_fibonacci_pivots(yesterday_ohlc)

        # Format and add pivot levels
        pivot_levels = {}
        for level_name, level_value in daily_pivot_levels.items():
            pivot_levels[f'daily_pivot_{level_name}'] = level_value

        # Add pivot levels to result
        all_levels.update(pivot_levels)

        # 4. Calculate weekly levels
        try:
            # Get weekly candles
            weekly_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 0, 5)

            if weekly_bars is not None and len(weekly_bars) >= 2:
                # Convert to DataFrame
                weekly_df = pd.DataFrame(weekly_bars)
                weekly_df['time'] = pd.to_datetime(weekly_df['time'], unit='s')
                weekly_df = weekly_df.sort_values('time', ascending=False)

                # Get data for the previous completed week
                prev_week_bar = weekly_df.iloc[1]

                # Calculate weekly levels
                weekly_levels = {
                    'prev_week_high': prev_week_bar['high'],
                    'prev_week_low': prev_week_bar['low']
                }

                # Calculate weekly pivot points
                prev_week_ohlc = {
                    "high": prev_week_bar['high'],
                    "low": prev_week_bar['low'],
                    "close": prev_week_bar['close']
                }

                weekly_pivot_levels = calculate_fibonacci_pivots(prev_week_ohlc)

                # Format and add weekly pivot levels
                for level_name, level_value in weekly_pivot_levels.items():
                    pivot_levels[f'weekly_pivot_{level_name}'] = level_value

                # Add weekly levels to result
                all_levels.update(weekly_levels)
                all_levels.update(pivot_levels)
        except Exception as e:
            print(f"Error calculating weekly levels: {e}")

        print(f"All levels calculated for {symbol}: {all_levels}")
        return all_levels

    except Exception as e:
        print(f"Error in update_all_levels for {symbol}: {e}")
        return all_levels


def get_price_levels(symbol):
    """
    Get important price levels including daily, weekly, pivot points, and Asian session ranges

    Args:
        symbol (str): The trading symbol to fetch data for

    Returns:
        dict: Dictionary containing price levels or None if data not available
    """
    global _cached_daily_levels, _cached_weekly_levels, _cached_pivot_levels, _cached_asian_levels

    # Initialize empty dictionary for the levels
    price_levels = {}

    # Log the begin of level fetching
    current_time = get_mt5_server_time()
    print(f"\n--- Fetching price levels for {symbol} at {current_time} ---")

    # Update all main levels if needed - this ensures we use consistent data
    should_update = should_update_daily_levels(symbol) or should_update_weekly_levels(symbol)
    if should_update or symbol not in _cached_daily_levels:
        # Calculate all levels together using the same data source
        updated_levels = update_all_levels(symbol)

        # Extract and cache the different level types

        # Daily levels
        daily_levels = {k: v for k, v in updated_levels.items() if k in [
            'today_open', 'yesterday_open', 'yesterday_high',
            'yesterday_low', 'yesterday_close'
        ]}
        if daily_levels:
            _cached_daily_levels[symbol] = daily_levels

        # Weekly levels
        weekly_levels = {k: v for k, v in updated_levels.items() if k in [
            'prev_week_high', 'prev_week_low'
        ]}
        if weekly_levels:
            _cached_weekly_levels[symbol] = weekly_levels

        # Pivot levels (both daily and weekly)
        pivot_levels = {k: v for k, v in updated_levels.items() if 'pivot' in k.lower()}
        if pivot_levels:
            _cached_pivot_levels[symbol] = pivot_levels

        # Add all updated levels to price_levels
        price_levels.update(updated_levels)
    else:
        # Use cached values
        if symbol in _cached_daily_levels:
            price_levels.update(_cached_daily_levels[symbol])

        if symbol in _cached_weekly_levels:
            price_levels.update(_cached_weekly_levels[symbol])

        if symbol in _cached_pivot_levels:
            price_levels.update(_cached_pivot_levels[symbol])

    # Update Asian session levels - check if the Asian session is complete
    current_date = datetime.now().date()
    asian_levels = _cached_asian_levels.get(symbol, {})

    # Check if Asian levels are needed and available
    asian_complete = is_after_2am_est()
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

if __name__ == "__main__":
    """
    This main function tests the price level functionality directly.
    Run this script directly to check if levels are being calculated correctly.
    """
    import sys

    # Initialize MT5 terminal
    if not mt5.initialize():
        print("Failed to initialize MT5 connection")
        sys.exit(1)

    try:
        # Symbol to test (default to EURUSD or use command line argument)
        symbol = sys.argv[1] if len(sys.argv) > 1 else "USDJPY"

        # Get current MT5 server time
        server_time = get_mt5_server_time()
        print(f"\n{'='*80}")
        print(f"MT5 PRICE LEVEL TEST - {server_time}")
        print(f"{'='*80}")
        print(f"Testing price levels for: {symbol}")

        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"Symbol {symbol} not found")
            sys.exit(1)

        digits = symbol_info.digits
        print(f"Symbol precision: {digits} digits")

        # Check Asian session status
        asian_complete = is_asian_session_complete()
        print(f"\nAsian session status: {'COMPLETE' if asian_complete else 'NOT COMPLETE'}")
        print(f"Server time: {server_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Server hour: {server_time.hour}")

        # Get and display all price levels
        print(f"\n--- Retrieving all price levels for {symbol} ---")
        all_levels = get_price_levels(symbol)

        # Display levels by category
        print(f"\n{'='*80}")
        print("PRICE LEVELS SUMMARY")
        print(f"{'='*80}")

        # Define level categories for organized display
        categories = {
            "Daily Levels": [
                'today_open', 'yesterday_open', 'yesterday_high',
                'yesterday_low', 'yesterday_close'
            ],
            "Weekly Levels": [
                'prev_week_high', 'prev_week_low'
            ],
            "Daily Pivot Levels": [
                'daily_pivot_P', 'daily_pivot_R1', 'daily_pivot_R2',
                'daily_pivot_S1', 'daily_pivot_S2'
            ],
            "Weekly Pivot Levels": [
                'weekly_pivot_P', 'weekly_pivot_R1', 'weekly_pivot_R2',
                'weekly_pivot_S1', 'weekly_pivot_S2'
            ],
            "Asian Session Levels": [
                'asian_high', 'asian_low', 'asian_mid'
            ]
        }

        # Print levels by category
        for category, level_names in categories.items():
            print(f"\n{category}:")
            print("-" * 40)
            found_levels = False

            for level_name in level_names:
                if level_name in all_levels:
                    value = all_levels[level_name]
                    print(f"{level_name:20}: {value:.{digits}f}")
                    found_levels = True

            if not found_levels:
                print("None available")

        # Get current price for context
        last_tick = mt5.symbol_info_tick(symbol)
        if last_tick is not None:
            current_price = (last_tick.bid + last_tick.ask) / 2
            print(f"\nCurrent price: {current_price:.{digits}f}")

            # Show which levels are close to current price
            print(f"\nLevels close to current price:")
            threshold = current_price * 0.0015  # 0.15% threshold
            close_levels = []

            for level_name, level_value in all_levels.items():
                distance = abs(current_price - level_value)
                distance_pct = (distance / current_price) * 100

                if distance < threshold:
                    close_levels.append((level_name, level_value, distance_pct))

            # Sort by distance
            close_levels.sort(key=lambda x: x[2])

            if close_levels:
                for level_name, level_value, distance_pct in close_levels:
                    print(f"{level_name:20}: {level_value:.{digits}f} (distance: {distance_pct:.3f}%)")
            else:
                print("No levels within 0.15% of current price")

        print(f"\n{'='*80}")
        print(f"Test completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Shutdown MT5 connection
        mt5.shutdown()
        print("\nMT5 connection closed")