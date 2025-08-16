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
import os

from data_fetcher import get_10min_data, get_price_levels
from candle_patterns import analyse_candle
from notifications import send_notification
# Import the regression indicator function
from regression import calculate_multi_kernel_regression

"""
Fixed position size calculator with enhanced debugging and error handling
"""
import math
import logging
from connection import mt5_connection
import MetaTrader5 as mt5


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
    logging.info(f"🔶 Position size calculation for {symbol}")
    logging.info(
        f"🔶 Parameters: stop_distance={stop_distance_price}, risk_pct={risk_percentage}%, account=${account_size}")

    try:
        with mt5_connection():
            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logging.error(f"Error: Unable to get symbol info for {symbol}")
                return 0, 0, 0

            # Log symbol properties for debugging
            logging.info(f"Symbol: {symbol}")
            logging.info(f"Point: {symbol_info.point}")
            logging.info(f"Contract size: {symbol_info.trade_contract_size}")
            logging.info(f"Tick size: {symbol_info.trade_tick_size}")
            logging.info(f"Tick value: {symbol_info.trade_tick_value}")

            # Get point value (minimum price change)
            point = symbol_info.point

            # Ensure we have a valid point value
            if point <= 0:
                logging.error(f"Invalid point value: {point}")
                return 0, 0, 0

            # Convert price-based stop to points
            stop_points = int(stop_distance_price / point)
            logging.info(f"Stop distance: {stop_distance_price:.5f} price = {stop_points} points")

            # Check if stop_points is valid
            if stop_points <= 0:
                logging.error(f"Invalid stop points: {stop_points}. Stop distance too small.")
                return 0, 0, 0

            # Calculate risk amount in account currency
            # Important! risk_percentage is expected as a percentage value (e.g., 0.5 for 0.5%)
            risk_amount = account_size * (risk_percentage / 100)
            logging.info(f"Risk amount: ${risk_amount:.2f}")

            # Check if risk_amount is valid
            if risk_amount <= 0:
                logging.error(f"Invalid risk amount: {risk_amount}")
                return 0, 0, 0

            # Get contract specifications
            contract_size = symbol_info.trade_contract_size  # Standard lot size

            # Check contract size
            if contract_size <= 0:
                logging.error(f"Invalid contract size: {contract_size}")
                return 0, 0, 0

            # For forex pairs, we need to handle the different quote currencies
            # The symbol base currency is the first 3 letters (e.g., EUR in EURUSD)
            # The quote currency is the last 3 letters (e.g., USD in EURUSD)
            base_currency = symbol[:3] if len(symbol) >= 6 else ""
            quote_currency = symbol[3:6] if len(symbol) >= 6 else ""
            account_currency = "USD"  # Assuming USD account

            logging.info(f"Base currency: {base_currency}, Quote currency: {quote_currency}")

            # Calculate pip value (point value in account currency)
            # For major forex pairs, we need to consider the quote currency
            pip_value = 0

            # Get current price
            try:
                current_price = (symbol_info.bid + symbol_info.ask) / 2
                logging.info(f"Current price: {current_price}")
            except Exception as e:
                logging.error(f"Error getting current price: {e}")
                current_price = 0

            if quote_currency == account_currency:
                # Direct quote (e.g., EURUSD for USD account)
                pip_value = contract_size * point
                logging.info(f"Direct quote: 1 point = ${pip_value:.5f}")
            elif base_currency == account_currency:
                # Indirect quote (e.g., USDCHF for USD account)
                # Need to convert from quote currency to account currency
                if current_price > 0:
                    pip_value = (contract_size * point) / current_price
                    logging.info(f"Indirect quote: 1 point = ${pip_value:.5f} at price {current_price:.5f}")
                else:
                    logging.error("Invalid current price for indirect quote")
                    pip_value = contract_size * point  # Fallback
            else:
                # Cross rates (e.g., EURGBP for USD account)
                # We need to find conversion rate to USD
                # This is simplified - in production you might need to get actual conversion rates
                try:
                    # Try to get conversion rate via USD pairs
                    conversion_symbol = f"{quote_currency}{account_currency}"
                    logging.info(f"Trying conversion via {conversion_symbol}")
                    conversion_info = mt5.symbol_info(conversion_symbol)

                    if conversion_info is not None:
                        # Convert using the quote currency to USD rate
                        conversion_rate = (conversion_info.bid + conversion_info.ask) / 2
                        pip_value = contract_size * point * conversion_rate
                        logging.info(f"Cross rate: 1 point = ${pip_value:.5f} via {conversion_symbol}")
                    else:
                        # Try reverse conversion
                        conversion_symbol = f"{account_currency}{quote_currency}"
                        logging.info(f"Trying reverse conversion via {conversion_symbol}")
                        conversion_info = mt5.symbol_info(conversion_symbol)

                        if conversion_info is not None:
                            conversion_rate = (conversion_info.bid + conversion_info.ask) / 2
                            pip_value = (contract_size * point) / conversion_rate
                            logging.info(f"Cross rate (reverse): 1 point = ${pip_value:.5f} via {conversion_symbol}")
                        else:
                            # Fallback to estimation
                            pip_value = contract_size * point * 1.0  # Rough estimate
                            logging.warning(f"Couldn't determine accurate pip value, using estimate: {pip_value}")
                except Exception as e:
                    logging.error(f"Error in currency conversion: {e}")
                    pip_value = contract_size * point  # Rough fallback

            # Special handling for gold and other commodities
            if symbol in ["XAUUSD", "GOLD", "BTCUSD", "USTEC"]:
                # For gold, each point is usually $0.01 per oz, and contract size is 100 oz
                pip_value = contract_size * 0.01
                logging.info(f"Special instrument: 1 point = ${pip_value:.2f}")

            # Check if pip_value is valid
            if pip_value <= 0:
                logging.error(f"Invalid pip value: {pip_value}")
                return 0, 0, 0

            # Calculate position size in lots
            position_size = risk_amount / (stop_points * pip_value)
            logging.info(
                f"Position size calculation: {risk_amount:.2f} / ({stop_points} * {pip_value:.5f}) = {position_size:.2f} lots")

            if position_size <= 0:
                logging.error("Position size calculation resulted in zero or negative value")
                return 0, 0, 0

            # Round to nearest valid lot step
            volume_step = symbol_info.volume_step
            if volume_step > 0:
                position_size = math.floor(position_size / volume_step) * volume_step
                logging.info(f"Rounded down to volume step {volume_step}: {position_size:.2f} lots")
            else:
                logging.warning(f"Invalid volume step: {volume_step}, using unrounded position size")

            # Ensure position size is within allowed limits
            try:
                volume_min = symbol_info.volume_min
                volume_max = symbol_info.volume_max

                position_size = max(position_size, volume_min)
                position_size = min(position_size, volume_max)

                logging.info(f"Final position size: {position_size:.2f} lots (min: {volume_min}, max: {volume_max})")
            except Exception as e:
                logging.error(f"Error applying volume limits: {e}")

            return position_size, stop_points, risk_amount

    except Exception as e:
        logging.error(f"Error in calculate_position_size: {e}")
        return 0, 0, 0


# Test function to verify position size calculation
def test_position_size_calculation(symbol="EURUSD", risk_percentage=0.5, account_size=100000):
    """Test position size calculation with a fixed stop distance"""
    # Get symbol info and calculate a reasonable stop distance
    try:
        with mt5_connection():
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logging.error(f"Symbol {symbol} not found")
                return

            # Get current price
            current_price = (symbol_info.bid + symbol_info.ask) / 2

            # Use a 1% stop distance for testing
            stop_distance_price = current_price * 0.01  # 1% of current price

            logging.info(f"Testing position size calculation for {symbol}")
            logging.info(f"Stop distance: {stop_distance_price} ({current_price * 0.01:.5f})")
            logging.info(f"Risk: {risk_percentage}% of ${account_size}")

            # Calculate position size
            position_size, stop_points, risk_amount = calculate_position_size(
                symbol, stop_distance_price, risk_percentage, account_size
            )

            logging.info(
                f"Test results: Position size = {position_size}, Stop points = {stop_points}, Risk amount = ${risk_amount:.2f}")

            return position_size, stop_points, risk_amount
    except Exception as e:
        logging.error(f"Error in test_position_size_calculation: {e}")
        return 0, 0, 0




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

def get_level_proximity(current_price, price_levels, digits=5):
    """
    Get a list of levels that price is near to (within 0.15% range)

    Args:
        current_price (float): Current price to check
        price_levels (dict): Dictionary of price levels
        digits (int): Number of decimal places for formatting

    Returns:
        list: List of level names and their proximity to current price
    """
    close_levels = []

    if not price_levels:
        return close_levels

    # Define proximity threshold as 0.15%
    threshold_pct = 0.0015
    threshold = current_price * threshold_pct

    for level_name, level_value in price_levels.items():
        if level_value is None or not isinstance(level_value, (int, float)):
            continue

        distance = abs(current_price - level_value)
        distance_pct = (distance / current_price) * 100

        if distance <= threshold:
            close_levels.append({
                'name': level_name,
                'value': level_value,
                'distance': distance,
                'distance_pct': distance_pct
            })

    # Sort by proximity (closest first)
    close_levels.sort(key=lambda x: x['distance_pct'])

    # Format the results for logging
    formatted_levels = []
    for level in close_levels:
        formatted_levels.append(
            f"{level['name']}={level['value']:.{digits}f} ({level['distance_pct']:.2f}%)"
        )

    return formatted_levels

def analyze_candle_diagnostic(df, index, price_levels, symbol):
    """
    Analyze a candle with detailed diagnostics to help identify why signals might not be generated

    Args:
        df: DataFrame with OHLC data
        index: Index of the candle to analyze
        price_levels: Dictionary of price levels
        symbol: Symbol being analyzed

    Returns:
        dict: Diagnostic information
    """
    # Get symbol info for formatting
    symbol_info = mt5.symbol_info(symbol)
    digits = symbol_info.digits if symbol_info is not None else 5

    # Ensure we have enough data
    if len(df) < 3 or abs(index) >= len(df):
        return {
            'error': f"Insufficient data for analysis. DataFrame length: {len(df)}, index: {index}"
        }

    # Extract candles
    current = df.iloc[index]
    prev1 = df.iloc[index-1]
    prev2 = df.iloc[index-2]

    # Extract OHLC values
    high0, low0, close0, open0 = current["High"], current["Low"], current["Close"], current["Open"]
    high1, low1, close1, open1 = prev1["High"], prev1["Low"], prev1["Close"], prev1["Open"]
    high2, low2, close2, open2 = prev2["High"], prev2["Low"], prev2["Close"], prev2["Open"]

    # Check pattern conditions
    bull_engulfing = low0 < low1 and high0 > high1 and close0 > open0
    bear_engulfing = high0 > high1 and low0 < low1 and close0 < open0

    large_body = abs(close0 - open0) >= 0.5 * (high0 - low0)
    bull_ifc = close0 > high1 and close0 > high2 and large_body and close0 > open0
    bear_ifc = close0 < low1 and close0 < low2 and large_body and close0 < open0

    # Check proximity to levels
    close_levels = get_level_proximity(close0, price_levels, digits)

    # True range calculation
    true_range = max(high0, high1) - min(low0, low1)

    # Compile diagnostic results
    diagnostics = {
        'symbol': symbol,
        'time': df.index[index],
        'ohlc': {
            'open': f"{open0:.{digits}f}",
            'high': f"{high0:.{digits}f}",
            'low': f"{low0:.{digits}f}",
            'close': f"{close0:.{digits}f}"
        },
        'pattern_conditions': {
            'bull_engulfing': bull_engulfing,
            'bear_engulfing': bear_engulfing,
            'large_body': large_body,
            'bull_ifc': bull_ifc,
            'bear_ifc': bear_ifc,
            'candle_type': "bull" if bull_engulfing or bull_ifc else "bear" if bear_engulfing or bear_ifc else "none"
        },
        'level_proximity': {
            'close_levels': close_levels,
            'has_close_levels': len(close_levels) > 0
        },
        'true_range': f"{true_range:.{digits}f}",
        'would_signal': (bull_engulfing or bull_ifc or bear_engulfing or bear_ifc) and len(close_levels) > 0
    }

    return diagnostics

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

    # Set detailed diagnostic logging for specific symbols (especially XAUUSD)
    detailed_logging = symbol in ["XAUUSD", "GOLD"]

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
    else:
        # Log price levels for diagnostic purposes
        symbol_info = mt5.symbol_info(symbol)
        digits = symbol_info.digits if symbol_info is not None else 5

        print(f"\n === {symbol} Price Levels ===")
        for level_name, level_value in sorted(price_levels.items()):
            if level_value is not None:
                print(f"  {level_name}: {level_value:.{digits}f}")

    symbol_data['price_levels'] = price_levels

    # Get last tick info
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        current_price = (tick.bid + tick.ask) / 2
        symbol_data['current_price'] = current_price

        # Log nearby levels at startup
        symbol_info = mt5.symbol_info(symbol)
        digits = symbol_info.digits if symbol_info is not None else 5
        close_levels = get_level_proximity(current_price, price_levels, digits)

        if close_levels:
            print(f"\n{symbol} is currently near these levels:")
            for level in close_levels:
                print(f"  {level}")
        else:
            print(f"\n{symbol} is not currently near any significant levels")

    # Main monitoring loop
    while not stop_event.is_set():
        try:
            # Get fresh data
            new_df = get_10min_data(symbol)

            # Skip if no data
            if new_df is None or new_df.empty:
                time.sleep(5)
                continue

            # Update current price
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                current_price = (tick.bid + tick.ask) / 2
                symbol_data['current_price'] = current_price

            # Check if we have current data to compare with
            if current_df is not None and not current_df.empty:
                last_candle_time = symbol_data.get('last_candle_time')

                # If we have a new candle (last candle time has changed)
                if new_df.index[-1] > last_candle_time:
                    # Ensure we have at least 3 candles for analysis
                    if len(current_df) >= 3:
                        # Run diagnostic analysis for detailed logging
                        if detailed_logging:
                            diagnostics = analyze_candle_diagnostic(current_df, -1, price_levels, symbol)

                            print(f"\n=== DETAILED DIAGNOSTICS FOR {symbol} ===")
                            print(f"Time: {diagnostics['time']}")
                            print(f"OHLC: {diagnostics['ohlc']}")
                            print(f"Pattern conditions:")
                            for cond, value in diagnostics['pattern_conditions'].items():
                                print(f"  {cond}: {value}")

                            print(f"Level proximity:")
                            if diagnostics['level_proximity']['close_levels']:
                                for level in diagnostics['level_proximity']['close_levels']:
                                    print(f"  {level}")
                            else:
                                print("  No levels in proximity")

                            print(f"True range: {diagnostics['true_range']}")
                            print(f"Would generate signal: {diagnostics['would_signal']}")
                            print(f"========================================")

                        # Analyze closed candle using the DataFrame approach
                        lookback_candles = int(os.getenv('LOOKBACK_CANDLES', '2'))
                        candle_type, touch_levels = analyse_candle(
                            current_df,
                            index=-1,
                            lookback=lookback_candles,
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

                            print(f"*** NEW SIGNAL GENERATED for {symbol}: {candle_type.upper()} at {current_price} ***")
                        else:
                            # Log why signal wasn't generated
                            if candle_type == "none":
                                print(f"{symbol}: No pattern detected (not bull or bear)")
                            elif len(touch_levels) == 0:
                                print(f"{symbol}: Pattern {candle_type} detected but no price levels touched")

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

    # Add header row with signal strength column
    table_rows.append(f"{'Symbol':<8} | {'Last Signal':<11} | {'Strength':<8} | {'Price':<10} | {'Direction':<9} | {'SL':<10} | {'Lots':<6} | {'Time':<16} | {'Close Levels'}")
    table_rows.append("-" * 110)

    # Add a row for each symbol
    for symbol in sorted(symbols_data.keys()):
        symbol_info = mt5.symbol_info(symbol)
        digits = symbol_info.digits if symbol_info is not None else 5

        current_price = symbols_data[symbol].get('current_price', 0)
        price_levels = symbols_data[symbol].get('price_levels', {})

        if symbol in all_signals and len(all_signals[symbol]) > 0:
            # Get most recent signal
            signal = all_signals[symbol][0]

            # Format time as HH:MM:SS
            time_str = signal['time'].strftime("%H:%M:%S")

            # Format direction
            direction = "BUY" if signal['type'] == "bull" else "SELL"

            # Format price and stop loss with appropriate precision
            price_str = f"{signal['price']:.{digits}f}"
            sl_str = f"{signal['stop_loss']:.{digits}f}"

            # Get signal strength
            strength = signal.get('signal_strength', 'NORMAL')
            strength_short = strength[:8]  # Truncate for table formatting

            # Get levels close to current price
            close_levels = get_level_proximity(current_price, price_levels, digits)
            close_levels_str = ", ".join(close_levels) if close_levels else "None"

            # Add row
            table_rows.append(
                f"{symbol:<8} | {direction:<11} | {strength_short:<8} | {price_str:<10} | {signal['regression_trend']:<9} | "
                f"{sl_str:<10} | {signal['position_size']:<6.2f} | {time_str:<16} | {close_levels_str}"
            )
        else:
            # No signals for this symbol
            # Format current price
            price_str = f"{current_price:.{digits}f}" if current_price else "-"

            # Get levels close to current price
            close_levels = get_level_proximity(current_price, price_levels, digits)
            close_levels_str = ", ".join(close_levels) if close_levels else "None"

            table_rows.append(
                f"{symbol:<8} | {'NO SIGNAL':<11} | {'-':<8} | {price_str:<10} | {'-':<9} | {'-':<10} | {'-':<6} | {'-':<16} | {close_levels_str}"
            )

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

                # Get signal strength and weekly level information
                strength = signal.get('signal_strength', 'NORMAL')
                weekly_levels = signal.get('weekly_levels', [])
                other_levels = signal.get('other_levels', [])

                # Create strength indicator for display
                strength_indicator = f" [{strength}]" if strength != "NORMAL" else ""

                signal_text = [
                    f"SIGNAL: {symbol} {direction}{strength_indicator}",
                    f"Price: {signal['price']:.{digits}f}",
                    f"Stop Loss: {signal['stop_loss']:.{digits}f}",
                    f"Lots: {signal['position_size']:.2f}",
                    f"Risk: ${signal['risk_amount']:.2f}",
                    f"Regression: {signal['regression_trend']}",
                    f"Time: {signal['time'].strftime('%Y-%m-%d %H:%M:%S')}"
                ]

                # Add level information with emphasis on weekly levels
                if weekly_levels:
                    signal_text.append(f"🔥 WEEKLY LEVELS: {', '.join(weekly_levels)}")
                if other_levels:
                    signal_text.append(f"Other Levels: {', '.join(other_levels)}")
                if not weekly_levels and not other_levels:
                    signal_text.append(f"Levels: {', '.join(signal['levels'])}")

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

def print_symbol_status_update(symbol, symbols_data, all_signals):
    """
    Print detailed status update for a symbol including price levels

    Args:
        symbol (str): Symbol to print status for
        symbols_data (dict): Dictionary with data for all symbols
        all_signals (dict): Dictionary with signals for all symbols
    """
    symbol_info = mt5.symbol_info(symbol)
    digits = symbol_info.digits if symbol_info is not None else 5

    # Get current data
    current_price = symbols_data[symbol].get('current_price', 0)
    price_levels = symbols_data[symbol].get('price_levels', {})

    # Format current price
    price_str = f"{current_price:.{digits}f}" if current_price else "Unknown"

    # Get levels close to current price
    close_levels = get_level_proximity(current_price, price_levels, digits)

    print(f"\n=== {symbol} Status ===")
    print(f"Current price: {price_str}")

    # Print signal info if available
    if symbol in all_signals and len(all_signals[symbol]) > 0:
        signal = all_signals[symbol][0]
        signal_type = "BUY" if signal['type'] == "bull" else "SELL"
        signal_time = signal['time'].strftime("%H:%M:%S")
        print(f"Last signal: {signal_type} @ {signal['price']:.{digits}f} ({signal_time})")
        print(f"Stop loss: {signal['stop_loss']:.{digits}f}")
        print(f"Position size: {signal['position_size']:.2f} lots")
        print(f"Touched levels: {', '.join(signal['levels'])}")
        print(f"Regression trend: {signal['regression_trend']}")
    else:
        print("No signals yet")

    # Print price levels information
    if close_levels:
        print(f"Price is near these levels:")
        for level in close_levels:
            print(f"  {level}")
    else:
        print("Price is not near any significant levels")

    # Print some key price levels
    if price_levels:
        print("\nKey price levels:")
        important_levels = [
            'today_open', 'yesterday_high', 'yesterday_low',
            'daily_pivot_P', 'daily_pivot_R1', 'daily_pivot_S1',
            'asian_high', 'asian_low'
        ]

        for level in important_levels:
            if level in price_levels and price_levels[level] is not None:
                print(f"  {level}: {price_levels[level]:.{digits}f}")




# Modified monitor_multiple_symbols function that accepts external dictionaries
def monitor_multiple_symbols(symbols, risk_percentage=0.5, account_size=100000,
                             all_signals=None, symbols_data=None, stop_event=None):
    """
    Monitor multiple symbols for trading signals with external data storage

    Args:
        symbols (list): List of symbols to monitor
        risk_percentage (float): Risk per trade as percentage of account
        account_size (float): Total account size in base currency
        all_signals (dict, optional): External dictionary to store signals
        symbols_data (dict, optional): External dictionary to store symbol data
        stop_event (threading.Event, optional): External event to signal stop
    """
    # Initialize dictionaries if not provided
    if symbols_data is None:
        symbols_data = {symbol: {} for symbol in symbols}

    if all_signals is None:
        all_signals = {}

    # Create a local stop event if not provided
    if stop_event is None:
        stop_event = threading.Event()

    # Lock for thread-safe access to the signals dictionary
    signals_lock = threading.Lock()

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
        while not stop_event.is_set():
            time.sleep(60)  # Status update every minute

            # Print status
            print("\n" + "=" * 80)
            print(f"STATUS UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)

            # Print detailed status for each symbol
            for symbol in symbols:
                with signals_lock:  # Safely access shared signal data
                    print_symbol_status_update(symbol, symbols_data, all_signals)

            print("=" * 80)

    except KeyboardInterrupt:
        print("\nStopping monitoring...")
        stop_event.set()

        # Wait for threads to finish
        for thread in symbol_threads:
            thread.join(timeout=1.0)

        signal_checker_thread.join(timeout=1.0)

        print("Monitoring stopped.")


# Rest of the functions remain the same...
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