import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import market_utils
from connection import mt5_connection


def get_asian_session_range(symbol, days_back=0):
    """
    Calculate Asian session high, low, and mid range.
    Asian session is defined as 20:00-02:00 EST.

    Args:
        symbol (str): The trading symbol
        days_back (int): 0 for current day, 1 for previous day, etc.

    Returns:
        dict: Dictionary with high, low, and mid values for the Asian session
    """
    try:
        with mt5_connection():
            # Get current date in server time
            server_time = datetime.now()

            # Calculate the target date (today or previous days)
            target_date = (server_time - timedelta(days=days_back)).date()

            # Asian session spans across two calendar days
            # Session start: previous day 20:00 EST
            # Session end: target day 02:00 EST

            # Create datetime objects for the session boundaries
            session_start = datetime.combine(target_date - timedelta(days=1), datetime.min.time())
            session_start = session_start.replace(hour=20, minute=0, second=0)  # 20:00 EST

            session_end = datetime.combine(target_date, datetime.min.time())
            session_end = session_end.replace(hour=2, minute=0, second=0)  # 02:00 EST

            # Convert to timestamp
            start_timestamp = int(session_start.timestamp())
            end_timestamp = int(session_end.timestamp())

            # Request H1 data from MT5
            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start_timestamp, end_timestamp)

            if rates is None or len(rates) == 0:
                print(f"No data available for Asian session on {target_date}")
                return None

            # Convert to DataFrame
            rates_df = pd.DataFrame(rates)

            # Calculate session high, low and mid
            session_high = rates_df['high'].max()
            session_low = rates_df['low'].min()
            session_mid = (session_high + session_low) / 2

            # Return results
            return {
                "date": target_date,
                "session_start": session_start,
                "session_end": session_end,
                "high": session_high,
                "low": session_low,
                "mid": session_mid,
                "range": session_high - session_low
            }

    except Exception as e:
        print(f"Error getting Asian session range: {e}")
        return None


def check_asian_session_signals(symbol, current_price, asian_data, days_back=0):
    """
    Check for signals based on Asian session levels.

    Args:
        symbol (str): The trading symbol
        current_price (float): Current price of the symbol
        asian_data (dict): Asian session data
        days_back (int): 0 for current day, 1 for previous day, etc.

    Returns:
        list: List of signal dictionaries
    """
    if asian_data is None or current_price is None:
        return []

    signals = []
    timeframe_prefix = "previous " if days_back > 0 else ""
    timeframe_base = f"{timeframe_prefix}asian (day {asian_data['date']})"

    try:
        # Check high level
        high_signal = market_utils.check_proximity_to_level(
            current_price,
            asian_data['high'],
            "high",
            timeframe_base
        )
        if high_signal:
            high_signal["description"] = f"Price near {timeframe_prefix}Asian session high ({asian_data['high']:.5f})"
            signals.append(high_signal)

        # Check low level
        low_signal = market_utils.check_proximity_to_level(
            current_price,
            asian_data['low'],
            "low",
            timeframe_base
        )
        if low_signal:
            low_signal["description"] = f"Price near {timeframe_prefix}Asian session low ({asian_data['low']:.5f})"
            signals.append(low_signal)

        # Check mid level
        mid_signal = market_utils.check_proximity_to_level(
            current_price,
            asian_data['mid'],
            "mid",
            timeframe_base
        )
        if mid_signal:
            mid_signal["description"] = f"Price near {timeframe_prefix}Asian session midpoint ({asian_data['mid']:.5f})"
            signals.append(mid_signal)

        return signals
    except Exception as e:
        print(f"Error checking Asian session signals: {e}")
        return []


def get_asian_session_levels(symbol):
    """
    Get Asian session levels for the current and previous days.

    Args:
        symbol (str): The trading symbol

    Returns:
        tuple: (asian_data, all_signals)
        - asian_data: dict with current and previous Asian session data
        - all_signals: list of all signals detected
    """
    try:
        with mt5_connection():
            # Get current price
            current_price = market_utils.get_current_price(symbol)
            all_signals = []

            # Initialize result container
            asian_data = {
                "current": None,
                "previous": None
            }

            # Current day Asian session
            current_asian = get_asian_session_range(symbol, 0)
            if current_asian:
                asian_data["current"] = current_asian

                # Check for signals with current Asian session levels
                if current_price is not None:
                    current_signals = check_asian_session_signals(symbol, current_price, current_asian, 0)
                    all_signals.extend(current_signals)

            # Previous day Asian session
            previous_asian = get_asian_session_range(symbol, 1)
            if previous_asian:
                asian_data["previous"] = previous_asian

                # Check for signals with previous Asian session levels
                if current_price is not None:
                    previous_signals = check_asian_session_signals(symbol, current_price, previous_asian, 1)
                    all_signals.extend(previous_signals)

            return asian_data, all_signals
    except Exception as e:
        print(f"Error in get_asian_session_levels: {e}")
        return {"current": None, "previous": None}, []


def print_asian_session_levels(asian_data):
    """
    Print the calculated Asian session levels in a formatted way.

    Args:
        asian_data (dict): Asian session data dictionary
    """
    print("\n=== Asian Session Data ===")

    # Print current day data
    if asian_data["current"]:
        current = asian_data["current"]
        print(f"\nCurrent Day Asian Session ({current['date']}):")
        print(f"High: {current['high']:.5f}")
        print(f"Low: {current['low']:.5f}")
        print(f"Mid: {current['mid']:.5f}")
        print(f"Range: {current['range']:.5f}")

    # Print previous day data
    if asian_data["previous"]:
        previous = asian_data["previous"]
        print(f"\nPrevious Day Asian Session ({previous['date']}):")
        print(f"High: {previous['high']:.5f}")
        print(f"Low: {previous['low']:.5f}")
        print(f"Mid: {previous['mid']:.5f}")
        print(f"Range: {previous['range']:.5f}")