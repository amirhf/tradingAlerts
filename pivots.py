import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta


def get_historical_ohlc(symbol, timeframe, lookback_periods=1):
    """
    Get historical OHLC data for the specified number of lookback periods.

    Args:
        symbol (str): The trading symbol
        timeframe (str): "daily" or "weekly"
        lookback_periods (int): Number of periods to look back

    Returns:
        list: List of dictionaries with OHLC data for each period
    """
    # Initialize MT5 if not already initialized
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return None

    today = datetime.now().date()
    results = []

    if timeframe.lower() == "daily":
        mt5_timeframe = mt5.TIMEFRAME_D1

        # Adjust for weekends and holidays
        for i in range(lookback_periods + 2):  # +2 to ensure we have enough data
            # Start checking from the previous day
            check_date = today - timedelta(days=i)
            weekday = check_date.weekday()

            # Skip weekends
            if weekday >= 5:  # Saturday or Sunday
                continue

            # Try to get data for this date
            start_time = datetime.combine(check_date, datetime.min.time())
            end_time = datetime.combine(check_date, datetime.max.time())

            rates = mt5.copy_rates_range(symbol, mt5_timeframe, start_time, end_time)

            if rates is not None and len(rates) > 0:
                rates_df = pd.DataFrame(rates)
                last_bar = rates_df.iloc[-1]

                results.append({
                    "date": check_date,
                    "high": last_bar['high'],
                    "low": last_bar['low'],
                    "close": last_bar['close']
                })

                if len(results) >= lookback_periods:
                    break

    elif timeframe.lower() == "weekly":
        mt5_timeframe = mt5.TIMEFRAME_W1

        # Use a more reliable approach for weekly data
        # Get several weeks of data and then filter
        current_time = datetime.now()
        # Go back 8 weeks to ensure we have enough data
        start_time = current_time - timedelta(days=56)  # 8 weeks

        # Get all weekly bars
        rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, 10)

        if rates is not None and len(rates) > 0:
            rates_df = pd.DataFrame(rates)
            # Convert time to datetime
            rates_df['time'] = pd.to_datetime(rates_df['time'], unit='s')

            # Sort by time descending to get the most recent weeks first
            rates_df = rates_df.sort_values('time', ascending=False)

            # Take the required number of weeks
            for i in range(min(lookback_periods, len(rates_df))):
                if i < len(rates_df):
                    bar = rates_df.iloc[i]
                    week_date = bar['time'].date()

                    results.append({
                        "date": week_date,
                        "high": bar['high'],
                        "low": bar['low'],
                        "close": bar['close']
                    })

    return results


def calculate_fibonacci_pivots(ohlc_data):
    """
    Calculate Fibonacci pivot points based on OHLC data.

    Args:
        ohlc_data (dict): Dictionary with high, low, close values

    Returns:
        dict: Dictionary containing the pivot levels (P, R1, R2, S1, S2)
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
    s1 = p - 0.382 * range_hl  # Support 1 - 38.2% Fibonacci ratio
    s2 = p - 0.618 * range_hl  # Support 2 - 61.8% Fibonacci ratio

    # Return the pivot levels
    return {
        "P": p,
        "R1": r1,
        "R2": r2,
        "S1": s1,
        "S2": s2
    }


def get_current_market_status(symbol):
    """
    Check if the market is currently open for the given symbol
    """
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return "Unknown"

    # Get symbol info
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return "Unknown"

    # Check if symbol is visible and trade is allowed
    if not symbol_info.visible:
        return "Not Visible"

    # Check trading session status
    if symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
        return "Open"
    elif symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        return "Closed"
    elif symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_CLOSEONLY:
        return "Close Only"
    else:
        return "Unknown"


def main():
    # Initialize MT5
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    # Get user input for symbol
    symbol = input("Enter symbol (e.g., EURUSD): ")

    # Check market status
    market_status = get_current_market_status(symbol)
    print(f"Current market status for {symbol}: {market_status}")
    print("Calculating pivot points using last available data...\n")

    # Get daily historical data (2 periods)
    daily_data = get_historical_ohlc(symbol, "daily", 2)

    if daily_data and len(daily_data) >= 2:
        # Current daily pivots (based on previous day)
        current_daily_data = daily_data[0]
        current_daily_pivots = calculate_fibonacci_pivots(current_daily_data)

        print(f"Current Daily Fibonacci Pivots for {symbol} (based on {current_daily_data['date']}):")
        for level, value in current_daily_pivots.items():
            print(f"{level}: {value:.5f}")

        # Previous daily pivots (based on day before previous day)
        previous_daily_data = daily_data[1]
        previous_daily_pivots = calculate_fibonacci_pivots(previous_daily_data)

        print(f"\nPrevious Daily Fibonacci Pivots for {symbol} (based on {previous_daily_data['date']}):")
        for level, value in previous_daily_pivots.items():
            print(f"{level}: {value:.5f}")
    else:
        print("Unable to get sufficient daily data for pivot calculations.")

    # Get weekly historical data (2 periods)
    weekly_data = get_historical_ohlc(symbol, "weekly", 2)

    if weekly_data and len(weekly_data) >= 2:
        # Current weekly pivots (based on previous week)
        current_weekly_data = weekly_data[0]
        current_weekly_pivots = calculate_fibonacci_pivots(current_weekly_data)

        print(f"\nCurrent Weekly Fibonacci Pivots for {symbol} (week ending {current_weekly_data['date']}):")
        for level, value in current_weekly_pivots.items():
            print(f"{level}: {value:.5f}")

        # Previous weekly pivots (based on week before previous week)
        previous_weekly_data = weekly_data[1]
        previous_weekly_pivots = calculate_fibonacci_pivots(previous_weekly_data)

        print(f"\nPrevious Weekly Fibonacci Pivots for {symbol} (week ending {previous_weekly_data['date']}):")
        for level, value in previous_weekly_pivots.items():
            print(f"{level}: {value:.5f}")
    else:
        # Fallback method for weekly data using daily aggregation
        print("\nAttempting alternative method for weekly data calculation...")

        # Get two weeks of daily data
        daily_data_extended = get_historical_ohlc(symbol, "daily", 14)  # Get 14 days to cover ~2 weeks

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

            # Calculate weekly OHLC
            manual_weekly_data = []
            for week_id, days in sorted(weekly_groups.items(), reverse=True):
                if len(days) > 0:
                    week_high = max(day['high'] for day in days)
                    week_low = min(day['low'] for day in days)
                    week_close = days[-1]['close']  # Last day's close
                    week_date = max(day['date'] for day in days)

                    manual_weekly_data.append({
                        'date': week_date,
                        'high': week_high,
                        'low': week_low,
                        'close': week_close
                    })

            # Take the two most recent weeks
            if len(manual_weekly_data) >= 2:
                current_weekly_data = manual_weekly_data[0]
                previous_weekly_data = manual_weekly_data[1]

                current_weekly_pivots = calculate_fibonacci_pivots(current_weekly_data)
                previous_weekly_pivots = calculate_fibonacci_pivots(previous_weekly_data)

                print(f"\nCurrent Weekly Fibonacci Pivots for {symbol} (week ending {current_weekly_data['date']}):")
                for level, value in current_weekly_pivots.items():
                    print(f"{level}: {value:.5f}")

                print(f"\nPrevious Weekly Fibonacci Pivots for {symbol} (week ending {previous_weekly_data['date']}):")
                for level, value in previous_weekly_pivots.items():
                    print(f"{level}: {value:.5f}")
            else:
                print("Unable to calculate weekly pivots from daily data.")
        else:
            print("Unable to get sufficient weekly data for pivot calculations.")

    current_time = datetime.now()
    today = current_time.date()
    weekday = today.weekday()

    if weekday >= 5:  # Weekend
        days_until_market_opens = 7 - weekday  # Days until Monday
        next_market_day = today + timedelta(days=days_until_market_opens)
        print(
            f"\nNote: Markets are currently closed for the weekend. Next trading day: Monday {next_market_day.strftime('%Y-%m-%d')}")

    # Shutdown MT5
    mt5.shutdown()


if __name__ == "__main__":
    main()