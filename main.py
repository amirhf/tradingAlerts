"""
Main entry point for the MT5 Chart Application
"""
import MetaTrader5 as mt5
from data_fetcher import get_10min_data
from chart_renderer import plot_candlestick_chart


def main():
    """Main function to initialize MT5 and run the chart application"""
    # Initialize MT5 connection
    if not mt5.initialize():
        print("Failed to connect to MetaTrader 5. Exiting.")
        return

    try:
        # Get user input for symbol
        symbol = input("Enter the symbol to plot (e.g., EURUSD): ").upper()

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


if __name__ == "__main__":
    main()