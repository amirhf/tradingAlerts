import MetaTrader5 as mt5
import numpy as np
import pandas as pd


def laplace_kernel(source, bandwidth):
    """
    Laplace kernel function as defined in the TradingView indicator.
    """
    return (1 / (2 * bandwidth)) * np.exp(-np.abs(source / bandwidth))


def calculate_multi_kernel_regression(symbol, timeframe, bandwidth=25):
    """
    Calculate Multi Kernel Regression using Laplace kernel with no repainting.

    Args:
        symbol: Trading symbol (e.g., "EURUSD")
        timeframe: Timeframe constant from MT5 (e.g., mt5.TIMEFRAME_H1)
        bandwidth: Bandwidth parameter (default: 25)

    Returns:
        Tuple containing (current_value, color, direction)
    """
    # Initialize MT5 if not already done
    if not mt5.initialize():
        print("MT5 initialization failed")
        return None, None, None

    # Get historical data (need bandwidth+1 bars to calculate current and previous values)
    bars = mt5.copy_rates_from_pos(symbol, timeframe, 0, bandwidth + 1)

    if bars is None or len(bars) < bandwidth + 1:
        print(f"Failed to get {bandwidth + 1} historical bars for {symbol}")
        return None, None, None

    # Convert to pandas DataFrame
    df = pd.DataFrame(bars)

    # Get open prices (ordered from oldest to newest)
    open_prices = df['open'].values

    # Calculate weights using Laplace kernel
    weights = np.zeros(bandwidth)
    sumw = 0
    for i in range(bandwidth):
        # Square of index relative to square of bandwidth (as in original code)
        j = (i ** 2) / (bandwidth ** 2)
        weights[i] = laplace_kernel(j, 1)  # Using 1 as bandwidth parameter in kernel function
        sumw += weights[i]

    # Calculate current value (using most recent bars)
    current_sum = 0
    for i in range(bandwidth):
        # Use the most recent bars (from the end of the array)
        current_sum += open_prices[-(i + 1)] * weights[i]

    current_value = current_sum / sumw

    # Calculate previous value (one bar back)
    previous_sum = 0
    for i in range(bandwidth):
        # Use bars starting from the second most recent (from the end of the array)
        previous_sum += open_prices[-(i + 2)] * weights[i]

    previous_value = previous_sum / sumw

    # Determine direction and color
    direction = current_value > previous_value
    color = "green" if direction else "red"

    return current_value, color, direction


# Example usage
if __name__ == "__main__":
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
    else:
        try:
            # Example calculation for EURUSD on H1 timeframe
            symbol =  input("Enter symbol (e.g., EURUSD): ")
            timeframe = mt5.TIMEFRAME_M10
            value, color, direction = calculate_multi_kernel_regression(symbol, timeframe, bandwidth=25)

            if value is not None:
                print(f"Symbol: {symbol}")
                print(f"Multi Kernel Regression value: {value:.5f}")
                print(f"Color: {color}")
                print(f"Direction: {'Up' if direction else 'Down'}")

        finally:
            # Shutdown MT5
            mt5.shutdown()