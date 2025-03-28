"""
Multi-symbol monitoring functionality for MT5 Chart Application
"""
import time
import threading
from datetime import datetime
import MetaTrader5 as mt5
import math

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
    if symbol in ["XAUUSD", "GOLD"]:
        # For gold, each point is usually $0.01 per oz, and contract size is 100 oz
        pip_value = contract_size * 0.01
        print(f"Gold: 1 point = ${pip_value:.2f}")
    elif symbol in ["XAGUSD", "SILVER"]:
        # For silver, each point is usually $0.01 per oz, and contract size is 5000 oz
        pip_value = contract_size * 0.01
        print(f"Silver: 1 point = ${pip_value:.2f}")

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

def monitor_symbol(symbol, symbol_data, stop_event, risk_percentage=0.5, account_size=100000):
    """
    Monitor a single symbol for candle pattern signals

    Args:
        symbol (str): Symbol to monitor
        symbol_data (dict): Dictionary to store data for this symbol
        stop_event (threading.Event): Event to signal thread to stop
        risk_percentage (float): Risk per trade as percentage of account
        account_size (float): Total account size in base currency
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

                            # Calculate true range for stop loss suggestion
                            true_range = max(closed_candle['High'], previous_candle['High']) - min(closed_candle['Low'], previous_candle['Low'])

                            # Get symbol point value for proper stop loss calculation
                            symbol_info = mt5.symbol_info(symbol)
                            if symbol_info is not None:
                                # Calculate suggested stop loss distance (1.5x the true range)
                                stop_distance_price = true_range * 1.5

                                # Calculate position size based on risk management
                                position_size, stop_points, risk_amount = calculate_position_size(
                                    symbol,
                                    stop_distance_price,
                                    risk_percentage,
                                    account_size
                                )

                                position_info = (
                                    f"\nRisk: {risk_percentage}% (${risk_amount:.2f})"
                                    f"\nStop Loss: {stop_points} points ({stop_distance_price:.5f} price)"
                                    f"\nPosition Size: {position_size:.2f} lots"
                                )
                            else:
                                position_info = "\nCouldn't calculate position size (symbol info unavailable)"

                            # Calculate regression indicator values
                            try:
                                regression_value, regression_color, regression_direction = calculate_multi_kernel_regression(
                                    symbol,
                                    mt5.TIMEFRAME_M10,  # Use the same timeframe as the chart
                                    bandwidth=25
                                )
                                regression_trend = "UPTREND" if regression_direction else "DOWNTREND"
                                regression_info = f"\nRegression Indicator: {regression_value:.5f} ({regression_trend})"
                            except Exception as e:
                                print(f"Error calculating regression for {symbol}: {e}")
                                regression_info = "\nRegression Indicator: Calculation failed"

                            # Current price for reference
                            current_price = closed_candle['Close']

                            # Send notification with regression and position information
                            send_notification(
                                subject=f"{symbol}: {candle_type.upper()} Pattern Detected",
                                body=(
                                    f"Symbol: {symbol}\n"
                                    f"Time: {last_candle_time}\n"
                                    f"Pattern: {candle_type}\n"
                                    f"Touched levels: {touch_levels}\n"
                                    f"Price: {current_price:.5f}"
                                    f"{regression_info}"
                                    f"{position_info}"
                                ),
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

    # Event to signal threads to stop
    stop_event = threading.Event()

    # Create and start a thread for each symbol
    threads = []
    for symbol in symbols:
        thread = threading.Thread(
            target=monitor_symbol,
            args=(symbol, symbols_data[symbol], stop_event, risk_percentage, account_size),
            daemon=True
        )
        thread.start()
        threads.append(thread)

    try:
        print(f"Monitoring {len(symbols)} symbols. Press Ctrl+C to stop.")
        print(f"Risk per trade: {risk_percentage}% of ${account_size}")

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