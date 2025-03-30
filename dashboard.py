"""
Console dashboard for multi-symbol monitoring
"""
import os
import time
import threading
from datetime import datetime
import MetaTrader5 as mt5

from data_fetcher import get_10min_data
from candle_patterns import analyse_candle


class ConsoleDashboard:
    """
    A simple console-based dashboard for monitoring multiple symbols
    """

    def __init__(self, symbols):
        """
        Initialize the dashboard

        Args:
            symbols (list): List of symbols to monitor
        """
        self.symbols = symbols
        self.symbols_data = {symbol: {} for symbol in symbols}
        self.stop_event = threading.Event()
        self.update_interval = 5  # seconds
        self.max_candles_to_show = 5

    def start(self):
        """Start the dashboard"""
        # Fetch initial data for all symbols
        for symbol in self.symbols:
            self._update_symbol_data(symbol)

        try:
            # Main loop
            while not self.stop_event.is_set():
                self._clear_console()
                self._display_header()
                self._display_symbols_status()

                # Sleep for the update interval
                for _ in range(self.update_interval):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)

                # Update data for each symbol
                for symbol in self.symbols:
                    self._update_symbol_data(symbol)

        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the dashboard"""
        self.stop_event.set()
        print("\nDashboard stopped.")

    def _update_symbol_data(self, symbol):
        """Update data for a symbol"""
        try:
            # Get latest data
            data = get_10min_data(symbol, num_bars=self.max_candles_to_show + 3)
            if data is not None and not data.empty:
                self.symbols_data[symbol]['data'] = data
                self.symbols_data[symbol]['last_update'] = datetime.now()

                # Get symbol info for formatting
                symbol_info = mt5.symbol_info(symbol)
                self.symbols_data[symbol]['digits'] = symbol_info.digits if symbol_info else 5

                # Update last price
                self.symbols_data[symbol]['last_price'] = data['Close'].iloc[-1]

                # Update daily change
                if 'Open' in data.columns:
                    day_open = data['Open'].iloc[0]  # First candle open as approximate day open
                    last_price = data['Close'].iloc[-1]
                    if day_open > 0:
                        daily_change_pct = (last_price - day_open) / day_open * 100
                        self.symbols_data[symbol]['daily_change'] = daily_change_pct
        except Exception as e:
            print(f"Error updating {symbol} data: {e}")

    def _clear_console(self):
        """Clear the console screen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _display_header(self):
        """Display the dashboard header"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("=" * 80)
        print(f"MT5 MULTI-SYMBOL MONITOR - {now}")
        print("=" * 80)
        print(f"Monitoring {len(self.symbols)} symbols: {', '.join(self.symbols)}")
        print("=" * 80)

    def _display_symbols_status(self):
        """Display status for all symbols"""
        for symbol in self.symbols:
            self._display_symbol_status(symbol)
            print("-" * 80)

    def _display_symbol_status(self, symbol):
        """Display status for a single symbol"""
        data = self.symbols_data.get(symbol, {})

        # Display symbol header
        print(f"\n{symbol} ", end="")

        # Display last price
        if 'last_price' in data and 'digits' in data:
            digits = data['digits']
            price = data['last_price']
            print(f"Last: {price:.{digits}f}", end="")

        # Display daily change
        if 'daily_change' in data:
            change = data['daily_change']
            color = "\033[92m" if change >= 0 else "\033[91m"  # Green for positive, red for negative
            reset = "\033[0m"
            print(f" | Daily: {color}{change:+.2f}%{reset}", end="")

        # Display last update time
        if 'last_update' in data:
            update_time = data['last_update'].strftime("%H:%M:%S")
            print(f" | Updated: {update_time}")
        else:
            print(" | No data")

        # Display recent candles
        if 'data' in data and not data['data'].empty:
            df = data['data']
            digits = data['digits']

            # Header for candles
            print("\nTime           | Open      | High      | Low       | Close     | Type")
            print("-" * 75)

            # Display last few candles
            for i in range(min(self.max_candles_to_show, len(df))):
                idx = -min(self.max_candles_to_show, len(df)) + i
                candle = df.iloc[idx]
                candle_time = df.index[idx].strftime("%H:%M:%S")

                # Determine candle type
                if len(df) >= 3 and idx >= -len(df) + 2:  # Make sure we have enough candles for analysis
                    if idx == -1:  # Current candle - still forming
                        candle_type = "forming"
                    else:
                        # Get candles for analysis
                        current = df.iloc[idx]
                        previous = df.iloc[idx - 1] if idx > -len(df) + 1 else None
                        previous2 = df.iloc[idx - 2] if idx > -len(df) + 2 else None

                        # Since idx already indicates position in df, we can use it directly
                        type_result, _ = analyse_candle(
                            df,
                            index=idx,
                            lookback=2,
                            price_levels={}
                        )
                        candle_type = type_result
                else:
                    candle_type = "unknown"

                # Format candle type with color
                if candle_type == "bull":
                    type_formatted = "\033[92mbull\033[0m"  # Green
                elif candle_type == "bear":
                    type_formatted = "\033[91mbear\033[0m"  # Red
                elif candle_type == "forming":
                    type_formatted = "\033[93mforming\033[0m"  # Yellow
                else:
                    type_formatted = "none"

                # Print candle data
                print(f"{candle_time} | {candle['Open']:{digits + 6}.{digits}f} | "
                      f"{candle['High']:{digits + 6}.{digits}f} | "
                      f"{candle['Low']:{digits + 6}.{digits}f} | "
                      f"{candle['Close']:{digits + 6}.{digits}f} | "
                      f"{type_formatted}")

        # Display any signals
        if 'last_signal' in data:
            signal = data['last_signal']
            signal_time = signal['time'].strftime("%Y-%m-%d %H:%M:%S")
            print(f"\nLast Signal: {signal['type']} at {signal_time}")
            print(f"Touched levels: {', '.join(signal['levels'])}")


# Testing
if __name__ == "__main__":
    if not mt5.initialize():
        print("Failed to connect to MetaTrader 5. Exiting.")
        exit()

    try:
        symbols_input = input("Enter symbols to monitor (comma-separated, e.g., EURUSD,GBPUSD,XAUUSD): ")
        symbols = [s.strip().upper() for s in symbols_input.split(",")]

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
            dashboard = ConsoleDashboard(valid_symbols)
            dashboard.start()
        else:
            print("No valid symbols found. Exiting.")

    finally:
        mt5.shutdown()