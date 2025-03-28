def detect_reversal_pattern(df, i):
    """
    Detect bullish or bearish reversal patterns for a candle.

    Args:
        df: DataFrame with OHLC data
        i: Index of the current candle to analyze

    Returns:
        tuple: (is_bearish_reversal, is_bullish_reversal)
    """
    if i <= 0 or i >= len(df):
        return False, False

    high = float(df['High'].iloc[i])
    low = float(df['Low'].iloc[i])
    close = float(df['Close'].iloc[i])
    open = float(df['Open'].iloc[i])
    prev_high = float(df['High'].iloc[i - 1])
    prev_low = float(df['Low'].iloc[i - 1])

    # Bearish failure: high > prev high but close < prev low
    is_bearish_reversal = high > prev_high and low < prev_low and close<open

    # Bullish failure: low < prev low but close > prev high
    is_bullish_reversal = low < prev_low and high > prev_high and close>open

    large_body = abs(close-open) >= 0.5*(high-low)
    is_bullish_ifc = close>prev_high and close>float(df['High'].iloc[i-2]) and large_body
    is_bearish_ifc = close<prev_low and close<float(df['Low'].iloc[i-2]) and large_body

    return is_bullish_reversal or is_bullish_ifc, is_bearish_reversal or is_bearish_ifc


def analyse_candle(closed_candle, previous_candle, previous2_candle, price_levels):
    """
    Analyze a closed candle to detect bullish or bearish patterns and touched levels.

    Args:
        closed_candle: The latest closed candle
        previous_candle: The previous closed candle
        previous2_candle: The 2nd previous closed candle
        price_levels: Dictionary containing important price levels

    Returns:
        tuple: (candle_type, touched_levels)
            candle_type: "bull", "bear", or "none"
            touched_levels: List of levels touched by the candles
    """
    # Extract OHLC values from candles
    high0, low0, close0, open0 = closed_candle["High"], closed_candle["Low"], closed_candle["Close"], closed_candle[
        "Open"]
    high1, low1, close1, open1 = previous_candle["High"], previous_candle["Low"], previous_candle["Close"], \
    previous_candle["Open"]
    high2, low2, close2, open2 = previous2_candle["High"], previous2_candle["Low"], previous2_candle["Close"], \
    previous2_candle["Open"]

    # Detect candle patterns
    bull_engulfing = low0 < low1 and high0 > high1 and close0 > open0
    bear_engulfing = high0 > high1 and low0 < low1 and close0 < open0

    large_body = abs(close0 - open0) >= 0.5 * (high0 - low0)
    bull_ifc = close0 > high1 and close0 > high2 and large_body and close0 > open0
    bear_ifc = close0 < low1 and close0 < low2 and large_body and close0 < open0

    # Determine candle type
    candle_type = "bull" if bull_engulfing or bull_ifc else "bear" if bear_engulfing or bear_ifc else "none"

    # Detect touched levels
    touch_levels = set()

    # Print some information for debugging
    print(f"\n--- Analyzing touched levels ---")
    print(f"Candle OHLC: Open={open0}, High={high0}, Low={low0}, Close={close0}")
    print(f"Price levels count: {len(price_levels)}")

    # Check each price level
    for level_name, level_value in price_levels.items():
        # Skip if level value is None or not a number
        if level_value is None or not isinstance(level_value, (int, float)):
            continue

        # Consider a level touched if it falls within the price range of any of the 3 candles
        # or if price closes very close to it (within 0.05% range)
        threshold = level_value * 0.0005  # 0.05% threshold for "close enough"

        if (low0 <= level_value <= high0) or abs(close0 - level_value) <= threshold:
            # Current candle touches the level
            touch_levels.add(level_name)
            print(f"Level {level_name} = {level_value} touched by current candle")
        elif (low1 <= level_value <= high1) or abs(close1 - level_value) <= threshold:
            # Previous candle touches the level
            touch_levels.add(level_name)
            print(f"Level {level_name} = {level_value} touched by previous candle")
        elif (low2 <= level_value <= high2) or abs(close2 - level_value) <= threshold:
            # Previous to previous candle touches the level
            touch_levels.add(level_name)
            print(f"Level {level_name} = {level_value} touched by previous to previous candle")

    print(f"Found {len(touch_levels)} touched levels: {touch_levels}")

    return candle_type, list(touch_levels)