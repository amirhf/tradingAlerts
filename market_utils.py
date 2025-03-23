import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

from notifications import send_notification


def initialize_mt5():
    """
    Initialize MT5 connection

    Returns:
        bool: True if successful, False otherwise
    """
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return False

    return True


def shutdown_mt5():
    """
    Shutdown MT5 connection
    """
    mt5.shutdown()


def get_current_market_status(symbol):
    """
    Check if the market is currently open for the given symbol

    Args:
        symbol (str): The trading symbol

    Returns:
        str: Market status (Open, Closed, Close Only, Unknown)
    """
    if not initialize_mt5():
        return "Unknown"

    # Get symbol info
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return "Unknown"

    # Check if symbol is visible
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


def get_current_price(symbol):
    """
    Get current price for a symbol

    Args:
        symbol (str): The trading symbol

    Returns:
        float: Current price or None if not available
    """
    if not initialize_mt5():
        return None

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is not None:
        # Use last price if available, otherwise fall back to bid
        if hasattr(symbol_info, 'last') and symbol_info.last > 0:
            return symbol_info.last
        # Use average of bid and ask if both are available
        elif hasattr(symbol_info, 'bid') and hasattr(symbol_info, 'ask'):
            return (symbol_info.bid + symbol_info.ask) / 2
        # Fallback to bid
        elif hasattr(symbol_info, 'bid'):
            return symbol_info.bid

    # If we couldn't get price from symbol_info, try to get the last tick
    try:
        ticks = mt5.symbol_info_tick(symbol)
        if ticks is not None:
            # Use last price if available
            if hasattr(ticks, 'last') and ticks.last > 0:
                return ticks.last
            # Use average of bid and ask
            elif hasattr(ticks, 'bid') and hasattr(ticks, 'ask'):
                return (ticks.bid + ticks.ask) / 2
            # Fallback to bid
            elif hasattr(ticks, 'bid'):
                return ticks.bid
    except:
        pass

    return None


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
    if not initialize_mt5():
        return None

    today = datetime.now().date()
    results = []

    if timeframe.lower() == "daily":
        mt5_timeframe = mt5.TIMEFRAME_D1

        # For Mondays, we need to go back at least 3 days to reach Friday
        weekday = today.weekday()  # 0=Monday, 6=Sunday

        # Start with more days to look back on Mondays to ensure we get Friday's data
        lookback_start = 3 if weekday == 0 else 1
        max_days_to_check = lookback_start + lookback_periods * 3  # Ensure we have enough days to check

        found_periods = 0

        # Try getting data for the past several days until we have enough periods
        for i in range(lookback_start, max_days_to_check):
            # Start checking from the previous days
            check_date = today - timedelta(days=i)
            check_weekday = check_date.weekday()

            # Skip weekends
            if check_weekday >= 5:  # Saturday or Sunday
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

                found_periods += 1
                if found_periods >= lookback_periods:
                    break

    elif timeframe.lower() == "weekly":
        mt5_timeframe = mt5.TIMEFRAME_W1

        # Get more historical data to ensure we have completed weeks
        current_time = datetime.now()
        from_date = current_time - timedelta(days=60)  # Go back further to ensure we have enough complete weeks

        # Get all weekly bars for the last 60 days
        rates = mt5.copy_rates_range(symbol, mt5_timeframe,
                                     int(from_date.timestamp()),
                                     int(current_time.timestamp()))

        if rates is not None and len(rates) > 0:
            rates_df = pd.DataFrame(rates)
            # Convert time to datetime
            rates_df['time'] = pd.to_datetime(rates_df['time'], unit='s')

            # Get the current day of week and time
            now = datetime.now()
            current_weekday = now.weekday()
            current_hour = now.hour

            # Determine if current week is complete (Friday after market close)
            current_week_complete = (current_weekday == 4 and current_hour >= 17) or current_weekday > 4

            # Filter out the current week if it's not complete
            if not current_week_complete:
                # Current week is not complete, skip the most recent bar
                current_week_time = rates_df.iloc[0]['time'].date()
                rates_df = rates_df[rates_df['time'].dt.date != current_week_time]

            # Sort by time descending to get the most recent completed weeks first
            rates_df = rates_df.sort_values('time', ascending=False)

            # Take the required number of completed weeks
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


def check_proximity_to_level(current_price, level_value, level_name, timeframe, proximity_threshold=0.0015):
    """
    Check if current price is near a specified level

    Args:
        current_price (float): Current price
        level_value (float): Level value to check
        level_name (str): Name of the level
        timeframe (str): Timeframe identifier for the signal
        proximity_threshold (float): Proximity threshold as percentage

    Returns:
        dict or None: Signal dictionary if proximity detected, None otherwise
    """
    if current_price is None or level_value is None:
        return None

    # Calculate percentage distance from level
    distance_pct = abs(current_price - level_value) / current_price

    # Check if price is very close to the level
    if distance_pct < proximity_threshold:
        signal_type = "support" if current_price > level_value else "resistance"
        return {
            "timeframe": timeframe,
            "level": level_name,
            "price": current_price,
            "pivot_value": level_value,
            "distance_pct": distance_pct * 100,  # Convert to percentage
            "type": "proximity",
            "description": f"Price near {level_name} {signal_type} ({level_value:.5f})"
        }

    return None


def send_batch_notification(symbol, signals, notification_method="print"):
    """
    Send a batch notification with multiple signals.

    Args:
        symbol (str): The trading symbol
        signals (list): List of signal dictionaries
        notification_method (str): Method to send notification (print, email, push, etc.)
    """
    if not signals:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"=== {symbol} Signals ({timestamp}) ===\n"

    # Group signals by timeframe
    grouped_signals = {}
    for signal in signals:
        timeframe = signal.get("timeframe", "unknown")
        if timeframe not in grouped_signals:
            grouped_signals[timeframe] = []
        grouped_signals[timeframe].append(signal)

    # Format the message with grouped signals
    for timeframe, timeframe_signals in grouped_signals.items():
        message += f"\n{timeframe.upper()} SIGNALS:\n"
        for signal in timeframe_signals:
            message += f"• {signal['description']}"
            if 'price' in signal:
                message += f" (Price: {signal['price']:.5f})"
            message += "\n"

    # Send the notification based on the selected method
    if notification_method == "print":
        print(message)
    elif notification_method == "email":
        # Implementation for email notification
        # This would require additional parameters like email credentials
        print("Email notification would be sent here.")
        print(message)
    elif notification_method == "push":
        # Implementation for push notification
        # This might use MT5's built-in notification system
        if initialize_mt5():
            # Note: terminal_info() is used to check if notifications are enabled
            terminal_info = mt5.terminal_info()
            if terminal_info.notifications_enabled:
                send_notification(f"{symbol} Signals", message)
    else:
        print(f"Unknown notification method: {notification_method}")
        print(message)