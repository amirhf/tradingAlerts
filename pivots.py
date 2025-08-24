import MetaTrader5 as mt5
from datetime import datetime, timedelta
import market_utils


def calculate_fibonacci_pivots(ohlc_data):
    """
    Calculate Fibonacci pivot points based on OHLC data.

    Args:
        ohlc_data (dict): Dictionary with high, low, close values

    Returns:
        dict: Dictionary containing the pivot levels (P, R1, R2, R3, S1, S2, S3)
    """
    high = ohlc_data["high"]
    low = ohlc_data["low"]
    close = ohlc_data["close"]

    # Calculate Fibonacci pivot points
    p = (high + low + close) / 3  # Pivot Point
    range_hl = high - low  # Range

    # Fibonacci ratios for pivot levels
    r1 = p + 0.382 * range_hl  # Resistance 1 - 38.2% Fibonacci ratio
    r2 = p + 0.618 * range_hl  # Resistance 2 - 61.8% Fibonacci ratio
    r3 = p + 1.000 * range_hl  # Resistance 3 - 100% Fibonacci ratio
    s1 = p - 0.382 * range_hl  # Support 1 - 38.2% Fibonacci ratio
    s2 = p - 0.618 * range_hl  # Support 2 - 61.8% Fibonacci ratio
    s3 = p - 1.000 * range_hl  # Support 3 - 100% Fibonacci ratio

    # Return the pivot levels
    return {
        "P": p,
        "R1": r1,
        "R2": r2,
        "R3": r3,
        "S1": s1,
        "S2": s2,
        "S3": s3
    }


def check_pivot_signals(symbol, current_price, pivot_data, timeframe):
    """
    Check for trading signals based on pivot points.

    Args:
        symbol (str): The trading symbol
        current_price (float): Current price of the symbol
        pivot_data (dict): Dictionary with pivot levels
        timeframe (str): Timeframe of the pivot data (daily, weekly)

    Returns:
        list: List of signal dictionaries
    """
    signals = []

    # Extract pivot levels
    levels = {
        "R3": pivot_data.get("R3"),
        "R2": pivot_data.get("R2"),
        "R1": pivot_data.get("R1"),
        "P": pivot_data.get("P"),
        "S1": pivot_data.get("S1"),
        "S2": pivot_data.get("S2"),
        "S3": pivot_data.get("S3")
    }

    # Check for price near pivot levels
    for level_name, level_value in levels.items():
        signal = market_utils.check_proximity_to_level(
            current_price,
            level_value,
            level_name,
            timeframe
        )
        if signal:
            signals.append(signal)

    return signals


def get_pivot_levels(symbol):
    """
    Get daily and weekly pivot levels for the current and previous periods.

    Args:
        symbol (str): The trading symbol

    Returns:
        tuple: (daily_pivots, weekly_pivots, all_signals)
        - daily_pivots: dict with current and previous daily pivots
        - weekly_pivots: dict with current and previous weekly pivots
        - all_signals: list of all signals detected
    """
    # Get current price
    current_price = market_utils.get_current_price(symbol)
    all_signals = []

    # Initialize result containers
    daily_pivots = {
        "current": None,
        "previous": None
    }

    weekly_pivots = {
        "current": None,
        "previous": None
    }

    # Get daily historical data (2 periods)
    daily_data = market_utils.get_historical_ohlc(symbol, "daily", 2)

    if daily_data and len(daily_data) >= 2:
        # Current daily pivots (based on previous day)
        current_daily_data = daily_data[0]
        current_daily_pivots = calculate_fibonacci_pivots(current_daily_data)
        daily_pivots["current"] = {
            "date": current_daily_data["date"],
            "levels": current_daily_pivots
        }

        # Check for signals with current daily pivots
        if current_price is not None:
            current_daily_signals = check_pivot_signals(
                symbol,
                current_price,
                current_daily_pivots,
                f"daily (based on {current_daily_data['date']})"
            )
            all_signals.extend(current_daily_signals)

        # Previous daily pivots (based on day before previous day)
        previous_daily_data = daily_data[1]
        previous_daily_pivots = calculate_fibonacci_pivots(previous_daily_data)
        daily_pivots["previous"] = {
            "date": previous_daily_data["date"],
            "levels": previous_daily_pivots
        }

        # Check for signals with previous daily pivots
        if current_price is not None:
            previous_daily_signals = check_pivot_signals(
                symbol,
                current_price,
                previous_daily_pivots,
                f"daily (based on {previous_daily_data['date']})"
            )
            all_signals.extend(previous_daily_signals)
    else:
        print("Warning: Unable to calculate daily pivots. Insufficient historical data.")

    # Get weekly historical data (2 periods)
    weekly_data = market_utils.get_historical_ohlc(symbol, "weekly", 4)

    if weekly_data and len(weekly_data) >= 2:
        # Current weekly pivots (based on most recent completed week)
        current_weekly_data = weekly_data[1]
        current_weekly_pivots = calculate_fibonacci_pivots(current_weekly_data)
        weekly_pivots["current"] = {
            "date": current_weekly_data["date"],
            "levels": current_weekly_pivots
        }

        # Check for signals with current weekly pivots
        if current_price is not None:
            current_weekly_signals = check_pivot_signals(
                symbol,
                current_price,
                current_weekly_pivots,
                f"weekly (completed week ending {current_weekly_data['date']})"
            )
            all_signals.extend(current_weekly_signals)

        # Previous weekly pivots (based on week before the most recent completed week)
        previous_weekly_data = weekly_data[2]
        previous_weekly_pivots = calculate_fibonacci_pivots(previous_weekly_data)
        weekly_pivots["previous"] = {
            "date": previous_weekly_data["date"],
            "levels": previous_weekly_pivots
        }

        # Check for signals with previous weekly pivots
        if current_price is not None:
            previous_weekly_signals = check_pivot_signals(
                symbol,
                current_price,
                previous_weekly_pivots,
                f"weekly (completed week ending {previous_weekly_data['date']})"
            )
            all_signals.extend(previous_weekly_signals)
    else:
        print("Warning: Unable to calculate weekly pivots. Insufficient historical data.")

        # Try alternative method using daily data aggregation
        print("Attempting alternative method for weekly data calculation...")

        # Get two weeks of daily data
        daily_data_extended = market_utils.get_historical_ohlc(symbol, "daily", 14)  # Get 14 days to cover ~2 weeks

        if daily_data_extended and len(daily_data_extended) >= 5:
            # Group by week
            for day in daily_data_extended:
                day['week'] = day['date'].isocalendar()[1]  # Get ISO week number
                day['year'] = day['date'].year

            # Create a unique identifier for each week
            for day in daily_data_extended:
                day['week_id'] = f"{day['year']}-{day['week']}"

            # Group by week_id
            weekly_groups = {}
            for day in daily_data_extended:
                week_id = day['week_id']
                if week_id not in weekly_groups:
                    weekly_groups[week_id] = []
                weekly_groups[week_id].append(day)

            # Calculate weekly OHLC for completed weeks only
            manual_weekly_data = []
            for week_id, days in sorted(weekly_groups.items(), reverse=True):
                if len(days) >= 3:  # Consider a week with at least 3 trading days as valid
                    week_high = max(day['high'] for day in days)
                    week_low = min(day['low'] for day in days)
                    # Sort days by date and use the most recent day's close
                    sorted_days = sorted(days, key=lambda x: x['date'])
                    week_close = sorted_days[-1]['close']
                    week_date = max(day['date'] for day in days)

                    manual_weekly_data.append({
                        'date': week_date,
                        'high': week_high,
                        'low': week_low,
                        'close': week_close
                    })

            # Take the two most recent completed weeks
            if len(manual_weekly_data) >= 2:
                current_weekly_data = manual_weekly_data[0]
                previous_weekly_data = manual_weekly_data[1]

                current_weekly_pivots = calculate_fibonacci_pivots(current_weekly_data)
                previous_weekly_pivots = calculate_fibonacci_pivots(previous_weekly_data)

                weekly_pivots["current"] = {
                    "date": current_weekly_data["date"],
                    "levels": current_weekly_pivots,
                    "note": "calculated from daily data"
                }

                weekly_pivots["previous"] = {
                    "date": previous_weekly_data["date"],
                    "levels": previous_weekly_pivots,
                    "note": "calculated from daily data"
                }

                # Check for signals with these pivots as well
                if current_price is not None:
                    current_weekly_signals = check_pivot_signals(
                        symbol,
                        current_price,
                        current_weekly_pivots,
                        f"weekly (aggregated from daily, ending {current_weekly_data['date']})"
                    )
                    all_signals.extend(current_weekly_signals)

                    previous_weekly_signals = check_pivot_signals(
                        symbol,
                        current_price,
                        previous_weekly_pivots,
                        f"weekly (aggregated from daily, ending {previous_weekly_data['date']})"
                    )
                    all_signals.extend(previous_weekly_signals)

    return daily_pivots, weekly_pivots, all_signals


def print_pivot_levels(symbol, daily_pivots, weekly_pivots):
    """
    Print the calculated pivot levels in a formatted way.

    Args:
        symbol (str): The trading symbol
        daily_pivots (dict): Daily pivot data
        weekly_pivots (dict): Weekly pivot data
    """
    # Print daily pivots
    if daily_pivots["current"]:
        current_date = daily_pivots["current"]["date"]
        current_levels = daily_pivots["current"]["levels"]

        print(f"\nCurrent Daily Fibonacci Pivots for {symbol} (based on {current_date}):")
        for level, value in current_levels.items():
            print(f"{level}: {value:.5f}")

    if daily_pivots["previous"]:
        previous_date = daily_pivots["previous"]["date"]
        previous_levels = daily_pivots["previous"]["levels"]

        print(f"\nPrevious Daily Fibonacci Pivots for {symbol} (based on {previous_date}):")
        for level, value in previous_levels.items():
            print(f"{level}: {value:.5f}")

    # Print weekly pivots
    if weekly_pivots["current"]:
        current_date = weekly_pivots["current"]["date"]
        current_levels = weekly_pivots["current"]["levels"]

        print(f"\nCurrent Weekly Fibonacci Pivots for {symbol} (week ending {current_date}):")
        for level, value in current_levels.items():
            print(f"{level}: {value:.5f}")

    if weekly_pivots["previous"]:
        previous_date = weekly_pivots["previous"]["date"]
        previous_levels = weekly_pivots["previous"]["levels"]

        print(f"\nPrevious Weekly Fibonacci Pivots for {symbol} (week ending {previous_date}):")
        for level, value in previous_levels.items():
            print(f"{level}: {value:.5f}")