"""
Multi-symbol monitoring functionality for MT5 Chart Application
"""
import time
import threading
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import math
from collections import deque
import pandas as pd

from data_fetcher import get_10min_data, get_price_levels
from candle_patterns import analyse_candle
from notifications import send_notification
# Import the regression indicator function
from regression import calculate_multi_kernel_regression


def calculate_position_size(symbol, stop_distance_price, risk_percentage=0.5, account_size=100000):
    """
    Calculate recommended position size based on risk management parameters

    Args:
        symbol (str): Trading symbol
        stop_distance_price (float): Stop loss distance in price terms
        risk_percentage (float): Risk per trade as percentage of account (default 0.5%)
        account_size (float): Total account size in base currency (default $100,000)

    Returns:
        tuple: (position_size, stop_points, risk_amount)
            position_size: Recommended position size in lots
            stop_points: Stop loss distance in points
            risk_amount: Amount risked in account currency
    """
    # Get symbol info
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Error: Unable to get symbol info for {symbol}")
        return 0, 0, 0

    # Print symbol properties for debugging
    print(f"Symbol: {symbol}")
    print(f"Point: {symbol_info.point}")
    print(f"Contract size: {symbol_info.trade_contract_size}")
    print(f"Tick size: {symbol_info.trade_tick_size}")
    print(f"Tick value: {symbol_info.trade_tick_value}")

    # Get point value (minimum price change)
    point = symbol_info.point

    # Convert price-based stop to points
    stop_points = int(stop_distance_price / point)
    print(f"Stop distance: {stop_distance_price:.5f} price = {stop_points} points")

    # Calculate risk amount in account currency
    risk_amount = account_size * (risk_percentage / 100)
    print(f"Risk amount: ${risk_amount:.2f}")

    # Get contract specifications
    contract_size = symbol_info.trade_contract_size  # Standard lot size

    # For forex pairs, we need to handle the different quote currencies
    # The symbol base currency is the first 3 letters (e.g., EUR in EURUSD)
    # The quote currency is the last 3 letters (e.g., USD in EURUSD)
    base_currency = symbol[:3] if len(symbol) >= 6 else ""
    quote_currency = symbol[3:6] if len(symbol) >= 6 else ""
    account_currency = "USD"  # Assuming USD account

    # Calculate pip value (point value in account currency)
    # For major forex pairs, we need to consider the quote currency
    pip_value = 0

    if quote_currency == account_currency:
        # Direct quote (e.g., EURUSD for USD account)
        pip_value = contract_size * point
        print(f"Direct quote: 1 point = ${pip_value:.5f}")
    elif base_currency == account_currency:
        # Indirect quote (e.g., USDCHF for USD account)
        # Need to convert from quote currency to account currency
        current_price = (symbol_info.bid + symbol_info.ask) / 2
        pip_value = (contract_size * point) / current_price
        print(f"Indirect quote: 1 point = ${pip_value:.5f} at price {current_price:.5f}")
    else:
        # Cross rates (e.g., EURGBP for USD account)
        # We need to find conversion rate to USD
        # This is simplified - in production you might need to get actual conversion rates
        try:
            # Try to get conversion rate via USD pairs
            conversion_symbol = f"{quote_currency}{account_currency}"
            conversion_info = mt5.symbol_info(conversion_symbol)

            if conversion_info is not None:
                # Convert using the quote currency to USD rate
                conversion_rate = (conversion_info.bid + conversion_info.ask) / 2
                pip_value = contract_size * point * conversion_rate
                print(f"Cross rate: 1 point = ${pip_value:.5f} via {conversion_symbol}")
            else:
                # Try reverse conversion
                conversion_symbol = f"{account_currency}{quote_currency}"
                conversion_info = mt5.symbol_info(conversion_symbol)

                if conversion_info is not None:
                    conversion_rate = (conversion_info.bid + conversion_info.ask) / 2
                    pip_value = (contract_size * point) / conversion_rate
                    print(f"Cross rate (reverse): 1 point = ${pip_value:.5f} via {conversion_symbol}")
                else:
                    # Fallback to estimation
                    pip_value = contract_size * point * 1.0  # Rough estimate
                    print(f"Warning: Couldn't determine accurate pip value, using estimate")
        except Exception as e:
            print(f"Error in currency conversion: {e}")
            pip_value = contract_size * point  # Rough fallback

    # Special handling for gold and other commodities
    if symbol in ["XAUUSD", "GOLD","BTCUSD","USTEC","XAGUSD", "SILVER"]:
        # For gold, each point is usually $0.01 per oz, and contract size is 100 oz
        pip_value = contract_size * 0.01
        print(f"{symbol}: 1 point = ${pip_value:.2f}")

    # Calculate position size in lots
    if stop_points > 0 and pip_value > 0:
        # Risk per position = stop_points * pip_value * position_size_in_lots
        # So position_size_in_lots = risk_amount / (stop_points * pip_value)
        position_size = risk_amount / (stop_points * pip_value)
        print(
            f"Position size calculation: {risk_amount:.2f} / ({stop_points} * {pip_value:.5f}) = {position_size:.2f} lots")
    else:
        position_size = 0
        print("Warning: Could not calculate position size (zero stop points or pip value)")

    # Round to nearest valid lot step
    volume_step = symbol_info.volume_step
    if volume_step > 0:
        position_size = math.floor(position_size / volume_step) * volume_step
        print(f"Rounded down to volume step {volume_step}: {position_size:.2f} lots")

    # Ensure position size is within allowed limits
    position_size = max(position_size, symbol_info.volume_min)
    position_size = min(position_size, symbol_info.volume_max)
    print(
        f"Final position size: {position_size:.2f} lots (min: {symbol_info.volume_min}, max: {symbol_info.volume_max})")

    return position_size, stop_points, risk_amount

def is_candle_close_time(current_time):
    """
    Check if the current time is within 5 seconds after a 10-minute candle close

    Args:
        current_time (datetime): The current time to check

    Returns:
        bool: True if it's within 5 seconds of a 10-minute candle close
    """
    # 10-minute candles close at 00, 10, 20, 30, 40, 50 minutes
    minute = current_time.minute
    second = current_time.second

    # Check if minute is divisible by 10 and seconds are less than 5
    is_candle_close = minute % 10 == 0 and second < 5

    return is_candle_close

def monitor_symbol(symbol, symbol_data, all_signals, signals_lock, stop_event, risk_percentage=0.5, account_size=100000):
    """
    Monitor a single symbol for candle pattern signals

    Args:
        symbol (str): Symbol to monitor
        symbol_data (dict): Dictionary to store data for this symbol
        all_signals (dict): Shared dictionary to store signals for all symbols
        signals_lock (threading.Lock): Lock for thread-safe access to all_signals
        stop_event (threading.Event): Event to signal thread to stop
        risk_percentage (float): Risk per trade as percentage of account
        account_size (float): Total account size in base currency
    """
    print(f"Started monitoring {symbol}")

    # Maximum number of signals to store per symbol
    max_signals_per_symbol = 10

    # Initialize with current data
    current_df = get_10min_data(symbol)
    if current_df is None or current_df.empty:
        print(f"Could not retrieve initial data for {symbol}. Will retry.")
        current_df = None
    else:
        symbol_data['last_candle_time'] = current_df.index[-1]

    # Get price levels for this symbol
    price_levels = get_price_levels(symbol)
    if not price_levels:
        print(f"Could not retrieve price levels for {symbol}. Will use empty levels.")
        price_levels = {}

    symbol_data['price_levels'] = price_levels

    # Main monitoring loop
    while not stop_event.is_set():
        try:
            # Get fresh data
            new_df = get_10min_data(symbol)

            # Skip if no data
            if new_df is None or new_df.empty:
                time.sleep(5)
                continue

            # Check if we have current data to compare with
            if current_df is not None and not current_df.empty:
                last_candle_time = symbol_data.get('last_candle_time')

                # If we have a new candle (last candle time has changed)
                if new_df.index[-1] > last_candle_time:
                    # Ensure we have at least 3 candles for analysis
                    if len(current_df) >= 3:
                        # Analyze closed candle using the DataFrame approach
                        candle_type, touch_levels = analyse_candle(
                            current_df,
                            index=-1,
                            lookback=2,
                            price_levels=price_levels
                        )

                        # Log the analysis results
                        print(
                            f"{symbol} candle closed at {last_candle_time}, type: {candle_type}, touch levels: {touch_levels}")

                        # Process and store signal if it's significant
                        if candle_type != "none" and len(touch_levels) >= 1:
                            # Current price
                            current_price = current_df.iloc[-1]['Close']

                            # Calculate true range for stop loss suggestion
                            true_range = max(current_df.iloc[-1]['High'], current_df.iloc[-2]['High']) - min(current_df.iloc[-1]['Low'], current_df.iloc[-2]['Low'])

                            # Calculate suggested stop loss distance (1.5x the true range)
                            stop_distance_price = true_range * 1.5

                            # Calculate position size based on risk management
                            position_size, stop_points, risk_amount = calculate_position_size(
                                symbol,
                                stop_distance_price,
                                risk_percentage,
                                account_size
                            )

                            # Calculate stop loss level
                            stop_loss = current_price - stop_distance_price if candle_type == "bull" else current_price + stop_distance_price

                            # Calculate regression indicator values
                            try:
                                regression_value, regression_color, regression_direction = calculate_multi_kernel_regression(
                                    symbol, mt5.TIMEFRAME_M10, bandwidth=25
                                )
                                regression_trend = "UPTREND" if regression_direction else "DOWNTREND"
                            except Exception as e:
                                print(f"Error calculating regression for {symbol}: {e}")
                                regression_value = None
                                regression_trend = "UNKNOWN"

                            # Create signal data
                            signal_data = {
                                'symbol': symbol,
                                'time': last_candle_time,
                                'current_time': datetime.now(),
                                'type': candle_type,
                                'levels': touch_levels,
                                'price': current_price,
                                'stop_loss': stop_loss,
                                'position_size': position_size,
                                'risk_amount': risk_amount,
                                'regression_value': regression_value,
                                'regression_trend': regression_trend,
                                'is_new': True  # Flag to indicate this is a new signal
                            }

                            # Store signal in shared dictionary (thread-safe)
                            with signals_lock:
                                if symbol not in all_signals:
                                    all_signals[symbol] = deque(maxlen=max_signals_per_symbol)
                                all_signals[symbol].appendleft(signal_data)

                            # Store the signal in symbol data for quick reference
                            symbol_data['last_signal'] = signal_data

                    # Update the last candle time
                    symbol_data['last_candle_time'] = new_df.index[-1]

            # Update current dataframe
            current_df = new_df

            # Sleep to avoid excessive CPU usage
            time.sleep(5)

        except Exception as e:
            print(f"Error in {symbol} monitoring thread: {e}")
            time.sleep(30)  # Longer sleep on error

def check_and_send_signals(all_signals, signals_lock, symbols_data, stop_event, risk_percentage, account_size):
    """
    Periodically check for new signals across all symbols and send consolidated notifications

    Args:
        all_signals (dict): Shared dictionary with signals for all symbols
        signals_lock (threading.Lock): Lock for thread-safe access to all_signals
        symbols_data (dict): Dictionary with data for all symbols
        stop_event (threading.Event): Event to signal thread to stop
        risk_percentage (float): Risk per trade as percentage of account
        account_size (float): Total account size in base currency
    """
    last_check_time = datetime.now()

    while not stop_event.is_set():
        current_time = datetime.now()

        # Check for signals 5 seconds after a 10-minute candle close
        if is_candle_close_time(current_time):
            # Only check once per candle close
            if (current_time - last_check_time).total_seconds() > 30:  # Ensure we don't check twice in same period
                # Sleep 5 seconds to allow all symbol threads to process their signals
                time.sleep(5)

                # Check for new signals (thread-safe)
                new_signals_found = False
                with signals_lock:
                    for symbol in all_signals:
                        for signal in all_signals[symbol]:
                            if signal.get('is_new', False):
                                new_signals_found = True
                                signal['is_new'] = False  # Mark as processed

                # If new signals found, send a consolidated notification
                if new_signals_found:
                    send_consolidated_notification(all_signals, symbols_data, risk_percentage, account_size)

                last_check_time = current_time

        # Sleep for a short time to check again
        time.sleep(1)

def format_summary_table(all_signals, symbols_data):
    """
    Format a summary table of all monitored symbols

    Args:
        all_signals (dict): Dictionary with signals for all symbols
        symbols_data (dict): Dictionary with data for all symbols

    Returns:
        str: Formatted summary table
    """
    # Create a list to hold table rows
    table_rows = []

    # Add header row
    table_rows.append(f"{'Symbol':<8} | {'Last Signal':<11} | {'Price':<10} | {'Direction':<9} | {'SL':<10} | {'Lots':<6} | {'Time':<16}")
    table_rows.append("-" * 80)

    # Add a row for each symbol
    for symbol in sorted(symbols_data.keys()):
        if symbol in all_signals and len(all_signals[symbol]) > 0:
            # Get most recent signal
            signal = all_signals[symbol][0]

            # Format time as HH:MM:SS
            time_str = signal['time'].strftime("%H:%M:%S")

            # Format direction
            direction = "BUY" if signal['type'] == "bull" else "SELL"

            # Format price and stop loss with appropriate precision
            symbol_info = mt5.symbol_info(symbol)
            digits = symbol_info.digits if symbol_info is not None else 5
            price_str = f"{signal['price']:.{digits}f}"
            sl_str = f"{signal['stop_loss']:.{digits}f}"

            # Add row
            table_rows.append(
                f"{symbol:<8} | {direction:<11} | {price_str:<10} | {signal['regression_trend']:<9} | "
                f"{sl_str:<10} | {signal['position_size']:<6.2f} | {time_str:<16}"
            )
        else:
            # No signals for this symbol
            table_rows.append(f"{symbol:<8} | {'NO SIGNAL':<11} | {'-':<10} | {'-':<9} | {'-':<10} | {'-':<6} | {'-':<16}")

    return "\n".join(table_rows)

def format_new_signals(all_signals):
    """
    Format details of new signals for notification

    Args:
        all_signals (dict): Dictionary with signals for all symbols

    Returns:
        str: Formatted signal details for notification
        int: Count of new signals
    """
    new_signals_text = []
    new_signals_count = 0

    for symbol in sorted(all_signals.keys()):
        for signal in all_signals[symbol]:
            # Only include recent signals (last 10 minutes)
            time_diff = datetime.now() - signal['current_time']
            if time_diff.total_seconds() < 600:  # 10 minutes in seconds
                new_signals_count += 1

                # Format signal details
                direction = "BUY" if signal['type'] == "bull" else "SELL"

                # Format price with appropriate precision
                symbol_info = mt5.symbol_info(symbol)
                digits = symbol_info.digits if symbol_info is not None else 5

                signal_text = [
                    f"SIGNAL: {symbol} {direction}",
                    f"Price: {signal['price']:.{digits}f}",
                    f"Stop Loss: {signal['stop_loss']:.{digits}f}",
                    f"Lots: {signal['position_size']:.2f}",
                    f"Risk: ${signal['risk_amount']:.2f}",
                    f"Regression: {signal['regression_trend']}",
                    f"Time: {signal['time'].strftime('%Y-%m-%d %H:%M:%S')}",
                    f"Levels: {', '.join(signal['levels'])}"
                ]

                new_signals_text.append("\n".join(signal_text))

    if new_signals_count > 0:
        return "\n\n".join(new_signals_text), new_signals_count
    else:
        return "No new signals in the last 10 minutes.", 0

def send_consolidated_notification(all_signals, symbols_data, risk_percentage, account_size):
    """
    Send a consolidated notification with all recent signals and a summary table

    Args:
        all_signals (dict): Dictionary with signals for all symbols
        symbols_data (dict): Dictionary with data for all symbols
        risk_percentage (float): Risk per trade as percentage of account
        account_size (float): Total account size in base currency
    """
    # Format new signals
    new_signals_text, new_signals_count = format_new_signals(all_signals)

    # Format summary table
    summary_table = format_summary_table(all_signals, symbols_data)

    # Create notification content
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    notification_body = (
        f"MT5 SIGNALS UPDATE - {current_time}\n"
        f"Risk: {risk_percentage}% per trade (${account_size:,.2f} account)\n\n"
        f"=== NEW SIGNALS ({new_signals_count}) ===\n"
        f"{new_signals_text}\n\n"
        f"=== SUMMARY TABLE ===\n"
        f"{summary_table}"
    )

    # Send notification
    subject = f"MT5 Signals Update - {new_signals_count} new signals" if new_signals_count > 0 else "MT5 Signals Update"
    send_notification(subject, notification_body)
    print(f"Sent consolidated notification with {new_signals_count} new signals at {current_time}")

def monitor_multiple_symbols(symbols, risk_percentage=0.5, account_size=100000):
    """
    Monitor multiple symbols for trading signals

    Args:
        symbols (list): List of symbols to monitor
        risk_percentage (float): Risk per trade as percentage of account
        account_size (float): Total account size in base currency
    """
    # Dictionary to store data for each symbol
    symbols_data = {symbol: {} for symbol in symbols}

    # Dictionary to store signals for all symbols
    all_signals = {}

    # Lock for thread-safe access to the signals dictionary
    signals_lock = threading.Lock()

    # Event to signal threads to stop
    stop_event = threading.Event()

    # Create and start a thread for each symbol
    symbol_threads = []
    for symbol in symbols:
        thread = threading.Thread(
            target=monitor_symbol,
            args=(symbol, symbols_data[symbol], all_signals, signals_lock, stop_event, risk_percentage, account_size),
            daemon=True
        )
        thread.start()
        symbol_threads.append(thread)

    # Create and start a thread for checking and sending signals
    signal_checker_thread = threading.Thread(
        target=check_and_send_signals,
        args=(all_signals, signals_lock, symbols_data, stop_event, risk_percentage, account_size),
        daemon=True
    )
    signal_checker_thread.start()

    try:
        print(f"Monitoring {len(symbols)} symbols. Press Ctrl+C to stop.")
        print(f"Risk per trade: {risk_percentage}% of ${account_size}")
        print("Signals will be consolidated and sent after each 10-minute candle closes")

        # Main loop - display periodic status updates
        while True:
            time.sleep(60)  # Check status every minute

            # Print status
            print("\n--- Status Update ---")
            print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # Show a mini version of the summary table in the console
            for symbol in symbols:
                if symbol in all_signals and len(all_signals[symbol]) > 0:
                    last_signal = all_signals[symbol][0]
                    signal_type = "BUY" if last_signal['type'] == "bull" else "SELL"
                    time_str = last_signal['time'].strftime("%H:%M:%S")
                    print(f"{symbol}: {signal_type} @ {last_signal['price']:.5f} - {time_str}")
                else:
                    print(f"{symbol}: No signals yet")

            print("--------------------\n")

    except KeyboardInterrupt:
        print("\nStopping monitoring...")
        stop_event.set()

        # Wait for threads to finish
        for thread in symbol_threads:
            thread.join(timeout=1.0)

        signal_checker_thread.join(timeout=1.0)

        print("Monitoring stopped.")


if __name__ == "__main__":
    # This allows running the monitor directly for testing
    if not mt5.initialize():
        print("Failed to connect to MetaTrader 5. Exiting.")
        exit()

    try:
        default_symbols = "EURUSD,GBPUSD,USDCHF,USDJPY,XAUUSD,NZDUSD"
        symbols_input = input(f"Enter symbols to monitor (comma-separated, default: {default_symbols}): ") or default_symbols
        symbols = [s.strip().upper() for s in symbols_input.split(",")]

        # Get risk parameters
        try:
            risk_input = input("Risk percentage per trade (default: 0.5%): ")
            risk_percentage = float(risk_input) if risk_input else 0.5

            account_input = input("Account size in base currency (default: $100,000): ")
            account_size = float(account_input.replace("$", "").replace(",", "")) if account_input else 100000
        except ValueError:
            print("Invalid input for risk parameters. Using defaults (0.5% risk on $100,000 account).")
            risk_percentage = 0.5
            account_size = 100000

        send_notification(
            "MT5 Monitor Started",
            f"Monitoring symbols: {', '.join(symbols)}\nRisk: {risk_percentage}% on ${account_size:,.2f}"
        )

        # Verify symbols
        valid_symbols = []
        for symbol in symbols:
            if mt5.symbol_info(symbol) is not None:
                valid_symbols.append(symbol)
                # Add to MarketWatch if needed
                if not mt5.symbol_info(symbol).visible:
                    mt5.symbol_select(symbol, True)
            else:
                print(f"Symbol {symbol} not found. Skipping.")

        if valid_symbols:
            monitor_multiple_symbols(valid_symbols, risk_percentage, account_size)
        else:
            print("No valid symbols found. Exiting.")

    finally:
        mt5.shutdown()