import MetaTrader5 as mt5
from datetime import datetime, timedelta

import market_utils
import pivots
import asian_session


def main():
    """
    Main function to run the combined pivot and Asian session analysis
    """
    # Initialize MT5
    if not market_utils.initialize_mt5():
        print("Failed to initialize MT5")
        return

    # Get user input for symbol
    symbol = input("Enter symbol (e.g., EURUSD): ")

    # Check market status
    market_status = market_utils.get_current_market_status(symbol)
    print(f"Current market status for {symbol}: {market_status}")
    print("Calculating levels using last available data...\n")

    # Get current price
    current_price = market_utils.get_current_price(symbol)
    if current_price is not None:
        print(f"Current price for {symbol}: {current_price:.5f}\n")

    # Initialize signal collection
    all_signals = []

    # ===== Get Fibonacci Pivot Levels =====
    daily_pivots, weekly_pivots, pivot_signals = pivots.get_pivot_levels(symbol)

    # Add pivot signals to all signals
    all_signals.extend(pivot_signals)

    # Print pivot levels
    pivots.print_pivot_levels(symbol, daily_pivots, weekly_pivots)

    # ===== Get Asian Session Levels =====
    asian_data, asian_signals = asian_session.get_asian_session_levels(symbol)

    # Add Asian session signals to all signals
    all_signals.extend(asian_signals)

    # Print Asian session levels
    asian_session.print_asian_session_levels(asian_data)

    # ===== Send batch notification for all signals =====
    if all_signals:
        print("\n=== Signal Summary ===")
        market_utils.send_batch_notification(symbol, all_signals, "print")
    else:
        print("\nNo signals detected at current price level.")

    # ===== Market status message =====
    current_time = datetime.now()
    today = current_time.date()
    weekday = today.weekday()

    if weekday >= 5:  # Weekend
        days_until_market_opens = 7 - weekday  # Days until Monday
        next_market_day = today + timedelta(days=days_until_market_opens)
        print(
            f"\nNote: Markets are currently closed for the weekend. Next trading day: Monday {next_market_day.strftime('%Y-%m-%d')}")

    # ===== Shutdown MT5 =====
    market_utils.shutdown_mt5()


if __name__ == "__main__":
    main()