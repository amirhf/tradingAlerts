"""
Main entry point for the MT5 Chart Application
"""
import MetaTrader5 as mt5
from data_fetcher import get_10min_data
from chart_renderer import plot_candlestick_chart
import threading
import time
from monitor import monitor_multiple_symbols

def main():
    """Main function to initialize MT5 and run the chart application"""
    # Initialize MT5 connection
    if not mt5.initialize():
        print("Failed to connect to MetaTrader 5. Exiting.")
        return

    try:
        # Ask for operation mode
        mode = input("Choose mode (1: Single chart, 2: Multi-symbol monitoring): ")

        if mode == "1":
            # Single chart mode - original functionality
            symbol = input("Enter the symbol to plot (e.g., EURUSD): ").upper()
            run_single_chart(symbol)
        elif mode == "2":
            # Multi-symbol monitoring mode
            symbols_input = input("Enter symbols to monitor (comma-separated, e.g., EURUSD,GBPUSD,XAUUSD): ")
            symbols = [s.strip().upper() for s in symbols_input.split(",")]
            run_multi_monitoring(symbols)
        else:
            print("Invalid mode selection. Exiting.")
            return

    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        print(traceback.format_exc())
    finally:
        # Clean up MT5 connection
        mt5.shutdown()
        print("MetaTrader 5 connection closed.")


def run_single_chart(symbol):
    """Run the application in single chart mode"""
    # Verify symbol exists
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Symbol {symbol} not found. Please check the symbol name.")
        return

    # Add symbol to MarketWatch if needed
    if not symbol_info.visible:
        print(f"Symbol {symbol} is not visible, trying to add it to MarketWatch...")
        if not mt5.symbol_select(symbol, True):
            print(f"Failed to add {symbol} to MarketWatch, error code: {mt5.last_error()}")
            return

    # Get initial data
    initial_data = get_10min_data(symbol)
    if initial_data is None or initial_data.empty:
        print(f"Failed to retrieve initial data for {symbol}. Exiting.")
        return

    # Set refresh interval (in seconds)
    refresh_interval = 15

    # Display chart
    plot_candlestick_chart(initial_data, symbol, refresh_interval)


def run_multi_monitoring(symbols):
    """Run the application in multi-symbol monitoring mode"""
    # Verify all symbols exist and add to MarketWatch if needed
    valid_symbols = []
    for symbol in symbols:
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"Symbol {symbol} not found. Skipping.")
            continue

        # Add symbol to MarketWatch if needed
        if not symbol_info.visible:
            print(f"Symbol {symbol} is not visible, trying to add it to MarketWatch...")
            if not mt5.symbol_select(symbol, True):
                print(f"Failed to add {symbol} to MarketWatch, error code: {mt5.last_error()}")
                continue

        valid_symbols.append(symbol)

    if not valid_symbols:
        print("No valid symbols found. Exiting.")
        return

    print(f"Starting monitoring for: {', '.join(valid_symbols)}")

    # Optional: Display chart for one symbol while monitoring all
    display_chart = input("Display chart for one symbol while monitoring? (y/n): ").lower() == 'y'

    if display_chart:
        display_symbol = input(f"Choose symbol to display (one of {', '.join(valid_symbols)}): ").upper()
        if display_symbol in valid_symbols:
            # Start monitoring thread for all symbols
            monitor_thread = threading.Thread(
                target=monitor_multiple_symbols,
                args=(valid_symbols,),
                daemon=True
            )
            monitor_thread.start()

            # Display chart for selected symbol
            initial_data = get_10min_data(display_symbol)
            if initial_data is not None and not initial_data.empty:
                plot_candlestick_chart(initial_data, display_symbol, 15)
            else:
                print(f"Failed to retrieve initial data for {display_symbol}. Falling back to monitoring only.")
                monitor_multiple_symbols(valid_symbols)
        else:
            print(f"Symbol {display_symbol} not in valid symbols list. Falling back to monitoring only.")
            monitor_multiple_symbols(valid_symbols)
    else:
        # Just monitor all symbols without displaying chart
        monitor_multiple_symbols(valid_symbols)


if __name__ == "__main__":
    main()