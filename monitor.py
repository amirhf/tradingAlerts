"""
Multi-symbol monitoring functionality for MT5 Chart Application
"""
import time
import threading
from datetime import datetime
import MetaTrader5 as mt5

from data_fetcher import get_10min_data, get_price_levels
from candle_patterns import analyse_candle
from notifications import send_notification


def monitor_symbol(symbol, symbol_data, stop_event):
    """
    Monitor a single symbol for candle pattern signals

    Args:
        symbol (str): Symbol to monitor
        symbol_data (dict): Dictionary to store data for this symbol
        stop_event (threading.Event): Event to signal thread to stop
    """
    print(f"Started monitoring {symbol}")

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
                    # A new candle has appeared, which means the previous one has closed
                    closed_candle = current_df.iloc[-1]

                    # Ensure we have at least 3 candles for analysis
                    if len(current_df) >= 3:
                        previous_candle = current_df.iloc[-2]
                        previous2_candle = current_df.iloc[-3]

                        # Analyze closed candle
                        candle_type, touch_levels = analyse_candle(
                            closed_candle, previous_candle, previous2_candle, price_levels
                        )

                        # Log the analysis results
                        print(
                            f"{symbol} candle closed at {last_candle_time}, type: {candle_type}, touch levels: {touch_levels}")

                        # Send notification if it's a significant candle
                        if candle_type != "none" and len(touch_levels) >= 1:
                            # Store the signal in symbol data
                            symbol_data['last_signal'] = {
                                'time': last_candle_time,
                                'type': candle_type,
                                'levels': touch_levels
                            }

                            # Send notification
                            send_notification(
                                subject=f"{symbol}: {candle_type.upper()} Pattern Detected",
                                body=f"Symbol: {symbol}\nTime: {last_candle_time}\nPattern: {candle_type}\nTouched levels: {touch_levels}\n\nPrice: {closed_candle['Close']}",
                            )

                    # Update the last candle time
                    symbol_data['last_candle_time'] = new_df.index[-1]

            # Update current dataframe
            current_df = new_df

            # Sleep to avoid excessive CPU usage
            time.sleep(10)

        except Exception as e:
            print(f"Error in {symbol} monitoring thread: {e}")
            time.sleep(30)  # Longer sleep on error


def monitor_multiple_symbols(symbols):
    """
    Monitor multiple symbols for trading signals

    Args:
        symbols (list): List of symbols to monitor
    """
    # Dictionary to store data for each symbol
    symbols_data = {symbol: {} for symbol in symbols}

    # Event to signal threads to stop
    stop_event = threading.Event()

    # Create and start a thread for each symbol
    threads = []
    for symbol in symbols:
        thread = threading.Thread(
            target=monitor_symbol,
            args=(symbol, symbols_data[symbol], stop_event),
            daemon=True
        )
        thread.start()
        threads.append(thread)

    try:
        print(f"Monitoring {len(symbols)} symbols. Press Ctrl+C to stop.")

        # Main loop - just keep the main thread alive and show status periodically
        while True:
            time.sleep(60)  # Check status every minute

            # Print status
            print("\n--- Status Update ---")
            print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            for symbol in symbols:
                last_signal = symbols_data[symbol].get('last_signal')
                if last_signal:
                    print(f"{symbol}: Last signal at {last_signal['time']} - {last_signal['type']}")
                else:
                    print(f"{symbol}: No signals yet, close time: {symbols_data[symbol].get('last_candle_time')}")

            print("--------------------\n")

    except KeyboardInterrupt:
        print("\nStopping monitoring...")
        stop_event.set()

        # Wait for threads to finish
        for thread in threads:
            thread.join(timeout=1.0)

        print("Monitoring stopped.")


if __name__ == "__main__":
    # This allows running the monitor directly for testing
    if not mt5.initialize():
        print("Failed to connect to MetaTrader 5. Exiting.")
        exit()

    try:
        default_symbols = "EURUSD,GBPUSD,XAUUSD,USDCHF"
        symbols_input = input(f"Enter symbols to monitor (comma-separated, default: {default_symbols}): ") or default_symbols
        symbols = [s.strip().upper() for s in symbols_input.split(",")]
        send_notification("MT5 Monitor Started", f"Monitoring symbols: {', '.join(symbols)}")

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
            monitor_multiple_symbols(valid_symbols)
        else:
            print("No valid symbols found. Exiting.")

    finally:
        mt5.shutdown()