"""
Data fetching functions for MT5 Chart Application
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, time, date
# Import the pivot and Asian session calculations
from pivots import calculate_fibonacci_pivots, get_pivot_levels
from asian_session import get_asian_session_range

# Global variables to track when levels were last updated
_last_daily_update_date = None
_last_weekly_update_date = None
_cached_daily_levels = {}
_cached_weekly_levels = {}
_cached_pivot_levels = {}
_cached_asian_levels = {}

def get_mt5_server_time():
    """
    Get the current time from the MT5 server to ensure timezone alignment

    Returns:
        datetime: Current MT5 server time
    """
    # Get MT5 terminal info
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        print("Failed to get MT5 terminal info, falling back to local time")
        return datetime.now()

    # Get the timezone offset in seconds
    timezone_offset = terminal_info.timezone

    # Get the GMT time
    gmt_time = datetime.utcnow()

    # Apply the timezone offset to get server time
    server_time = gmt_time + timedelta(seconds=timezone_offset)

    return server_time

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

    # If we haven't updated today or haven't updated at all, we should update
    if _last_daily_update_date is None or _last_daily_update_date < current_date:
        # Check if the current day's daily candle is closed
        yesterday = current_date - timedelta(days=1)
        daily_bars = mt5.copy_rates_range(
            symbol,
            mt5.TIMEFRAME_D1,
            datetime.combine(yesterday, time(0)),
            server_time
        )

        if daily_bars is not None and len(daily_bars) > 0:
            # Convert to DataFrame for easier handling
            daily_df = pd.DataFrame(daily_bars)
            daily_df['time'] = pd.to_datetime(daily_df['time'], unit='s')
            daily_df = daily_df.sort_values('time')

            # Check if we have a daily candle that closed yesterday
            for i in range(len(daily_df)):
                candle_date = daily_df['time'].iloc[i].date()
                if candle_date < current_date:  # This is a completed candle from a previous day
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
    current_weekday = current_date.weekday()  # 0 = Monday, 6 = Sunday

    # If we haven't updated this week or haven't updated at all, we should check
    if _last_weekly_update_date is None or (_last_weekly_update_date.isocalendar()[1] < current_date.isocalendar()[1]):
        # A new weekly candle starts on Monday, check if we have a completed weekly candle
        # We consider a weekly candle complete if today is Monday or later and we have data from last week
        if current_weekday >= 0:  # Monday or later
            # Get weekly data
            two_weeks_ago = current_date - timedelta(days=14)  # Go back two weeks to ensure we have last week's data
            weekly_bars = mt5.copy_rates_range(
                symbol,
                mt5.TIMEFRAME_W1,
                datetime.combine(two_weeks_ago, time(0)),
                server_time
            )

            if weekly_bars is not None and len(weekly_bars) > 0:
                # Convert to DataFrame for easier handling
                weekly_df = pd.DataFrame(weekly_bars)
                weekly_df['time'] = pd.to_datetime(weekly_df['time'], unit='s')
                weekly_df = weekly_df.sort_values('time', ascending=False)

                # Check if we have a weekly candle that closed last week
                if len(weekly_df) > 0:
                    last_candle_date = weekly_df['time'].iloc[0].date()
                    last_candle_week = last_candle_date.isocalendar()[1]
                    current_week = current_date.isocalendar()[1]

                    if last_candle_week < current_week:  # This is a completed candle from the previous week
                        _last_weekly_update_date = current_date
                        return True

    return False


def is_asian_session_complete():
    """
    Check if the Asian session for today is complete (after 02:00 EST)

    Returns:
        bool: True if the Asian session is complete, False otherwise
    """
    # Get current time in server time
    server_time = get_mt5_server_time()

    # Convert to NY time (EST/EDT) - MT5 times are in broker server time
    # We need to check market conventions, not just timezone math
    # For forex, Asian session is considered over at 2AM New York time

    # Get actual market-relevant time information from MT5 (if available)
    symbol_info = mt5.symbol_info("EURUSD")  # Use a major forex pair as reference
    if symbol_info is not None and hasattr(symbol_info, 'time'):
        # Some MT5 implementations provide trade server time, which can be used as reference
        # But we still need to adjust for the targeted NY time
        try:
            # Check if current trading session includes New York
            sessions = symbol_info.session_deals
            # This is complex; for simplicity we'll use a time-based approach

            # Convert broker time to NY (EST/EDT) time estimate
            # This is approximate - we need to know broker's timezone to be exact
            # For major brokers using GMT+2/GMT+3 during summer/winter:
            if server_time.hour < 7:  # Before 7AM server time is likely before 2AM NY
                return False
            else:
                return True

        except AttributeError:
            # If we can't get session info, use a simplified approach
            pass

    # Simplified fallback approach - assume server is on GMT+2 (common for forex brokers)
    # and convert to NY time (GMT-4/GMT-5)
    # This has a 6-7 hour difference depending on DST
    est_hour = (server_time.hour - 6) % 24  # Rough estimate, 6 hours difference to NY

    # Asian session ends at 02:00 NY time
    return est_hour >= 2


def get_price_levels(symbol):
    """
    Get important price levels including daily, weekly, pivot points, and Asian session ranges

    Args:
        symbol (str): The trading symbol to fetch data for

    Returns:
        dict: Dictionary containing price levels or None if data not available
    """
    global _cached_daily_levels, _cached_weekly_levels, _cached_pivot_levels, _cached_asian_levels

    # Initialize with cached values or empty dicts if not yet cached
    daily_levels = _cached_daily_levels.get(symbol, {})
    weekly_levels = _cached_weekly_levels.get(symbol, {})
    pivot_levels = _cached_pivot_levels.get(symbol, {})
    asian_levels = _cached_asian_levels.get(symbol, {})

    # Get current server time from MT5
    server_time = get_mt5_server_time()
    current_date = server_time.date()

    # Log the server time for debugging
    print(f"MT5 Server time: {server_time}, Date: {current_date}")

    # Initialize the price levels dictionary
    price_levels = {}

    # Update daily levels if needed
    if should_update_daily_levels(symbol):
        print(f"Updating daily levels for {symbol} - new day detected")
        try:
            # Get daily bars (last 10 days to ensure we have enough data)
            ten_days_ago = current_date - timedelta(days=10)
            daily_bars = mt5.copy_rates_range(
                symbol,
                mt5.TIMEFRAME_D1,
                datetime.combine(ten_days_ago, time(0)),
                server_time
            )

            if daily_bars is not None and len(daily_bars) > 0:
                # Convert to DataFrame
                daily_df = pd.DataFrame(daily_bars)
                daily_df['time'] = pd.to_datetime(daily_df['time'], unit='s')
                daily_df = daily_df.set_index('time')
                daily_df.sort_index(inplace=True)

                # If we have at least 2 bars, update daily levels
                if len(daily_df) >= 2:
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

                    # Cache the updated daily levels
                    _cached_daily_levels[symbol] = daily_levels
                    print(f"Daily levels updated for {symbol}")
            else:
                print(f"Failed to retrieve daily data for {symbol}, using cached daily levels")
        except Exception as e:
            print(f"Error updating daily levels: {e}")

    # Update weekly levels if needed
    if should_update_weekly_levels(symbol):
        print(f"Updating weekly levels for {symbol} - new week detected")
        try:
            # Get weekly data (last 5 weeks to ensure we have enough data)
            weekly_bars = mt5.copy_rates_from_pos(
                symbol,
                mt5.TIMEFRAME_W1,
                0,
                5
            )

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
                print(f"Weekly levels updated for {symbol}")
            else:
                print(f"Failed to retrieve weekly data for {symbol}, using cached weekly levels")
        except Exception as e:
            print(f"Error updating weekly levels: {e}")

    # Add standard levels to price_levels
    price_levels.update(daily_levels)
    price_levels.update(weekly_levels)

    # Update pivot levels
    try:
        # Check if we need to update daily pivot levels
        if should_update_daily_levels(symbol) or len(pivot_levels) == 0:
            print(f"Updating pivot levels for {symbol}")
            # Get pivot levels for daily and weekly timeframes
            daily_pivots, weekly_pivots, _ = get_pivot_levels(symbol)

            new_pivot_levels = {}

            # Add daily pivot levels if available
            if daily_pivots.get("current") and daily_pivots["current"].get("levels"):
                daily_levels_data = daily_pivots["current"]["levels"]
                for level_name, level_value in daily_levels_data.items():
                    new_pivot_levels[f'daily_pivot_{level_name}'] = level_value

            # Add weekly pivot levels if available
            if weekly_pivots.get("current") and weekly_pivots["current"].get("levels"):
                weekly_levels_data = weekly_pivots["current"]["levels"]
                for level_name, level_value in weekly_levels_data.items():
                    new_pivot_levels[f'weekly_pivot_{level_name}'] = level_value

            # Cache the updated pivot levels
            pivot_levels = new_pivot_levels
            _cached_pivot_levels[symbol] = pivot_levels
            print(f"Pivot levels updated for {symbol}")
    except Exception as e:
        print(f"Error updating pivot levels: {e}")

    # Add pivot levels to price_levels
    price_levels.update(pivot_levels)

    # Update Asian session ranges
    try:
        # Check if the Asian session is complete for today
        is_asian_complete = is_asian_session_complete()
        print(f"Asian session complete: {is_asian_complete}")

        if is_asian_complete:
            # If the date has changed, clear the old Asian levels
            if 'date' in asian_levels and asian_levels['date'] != current_date:
                print(f"Clearing old Asian levels for {symbol} - date changed")
                asian_levels = {}

            # Only calculate if we don't have current day's data or it's incomplete
            if 'date' not in asian_levels or asian_levels['date'] != current_date:
                print(f"Calculating new Asian levels for {symbol}")
                # Current day Asian session
                current_asian = get_asian_session_range(symbol, 0)
                if current_asian:
                    asian_levels = {
                        'date': current_date,
                        'asian_high': current_asian['high'],
                        'asian_low': current_asian['low'],
                        'asian_mid': current_asian['mid']
                    }

                    # Cache the updated Asian levels
                    _cached_asian_levels[symbol] = asian_levels
                    print(f"Asian levels updated for {symbol}")
        else:
            # Asian session is not complete yet, clear any Asian levels for today
            if 'date' in asian_levels and asian_levels['date'] == current_date:
                print(f"Asian session not complete yet, clearing today's Asian levels for {symbol}")
                asian_levels = {}
                _cached_asian_levels[symbol] = asian_levels
    except Exception as e:
        print(f"Error updating Asian session levels: {e}")

    # Add Asian levels to price_levels if available
    if 'asian_high' in asian_levels:
        price_levels.update({
            'asian_high': asian_levels['asian_high'],
            'asian_low': asian_levels['asian_low'],
            'asian_mid': asian_levels['asian_mid']
        })

    return price_levels