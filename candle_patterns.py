import os


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


def analyse_candle(df, index=-1, lookback=2, price_levels=None):
    """
    Analyze a candle to detect bullish or bearish patterns and touched levels.

    Args:
        df: DataFrame with OHLC data
        index: Index of the candle to analyze in df (default -1 for most recent)
        lookback: Number of previous candles to consider for level touches (default 2)
        price_levels: Dictionary containing important price levels (default None)

    Returns:
        tuple: (candle_type, touched_levels)
            candle_type: "bull", "bear", or "none"
            touched_levels: List of levels touched by the candles
    """
    # Ensure we have enough data for analysis
    if price_levels is None:
        price_levels = {}

    if len(df) < 3 or abs(index) >= len(df):
        print(f"Insufficient data for analysis. DataFrame length: {len(df)}, index: {index}")
        return "none", []

    # Extract individual candles from DataFrame
    current = df.iloc[index]
    prev1 = df.iloc[index - 1]
    prev2 = df.iloc[index - 2]

    # Extract OHLC values from candles
    high0, low0, close0, open0 = current["High"], current["Low"], current["Close"], current["Open"]
    high1, low1, close1, open1 = prev1["High"], prev1["Low"], prev1["Close"], prev1["Open"]
    high2, low2, close2, open2 = prev2["High"], prev2["Low"], prev2["Close"], prev2["Open"]

    # Detect candle patterns
    bull_engulfing = low0 < low1 and high0 > high1 and close0 > open0
    bear_engulfing = high0 > high1 and low0 < low1 and close0 < open0

    large_body = abs(close0 - open0) >= 0.5 * (high0 - low0)
    bull_ifc = close0 > high1 and close0 > high2 and large_body and close0 > open0
    bear_ifc = close0 < low1 and close0 < low2 and large_body and close0 < open0

    # Determine candle type
    candle_type = "bull" if bull_engulfing or bull_ifc else "bear" if bear_engulfing or bear_ifc else "none"

    # If no price levels are provided, skip level detection
    if not price_levels:
        return candle_type, []

    # Get configurable threshold from environment
    level_touch_threshold_pct = float(os.getenv('LEVEL_TOUCH_THRESHOLD', '0.05'))
    
    # Detect touched levels - ADVANCED TOUCHING LOGIC WITH DIRECTIONAL CRITERIA
    touch_levels = set()
    
    # Separate weekly levels for priority handling
    weekly_levels = {}
    other_levels = {}
    
    for level_name, level_value in price_levels.items():
        if level_value is None or not isinstance(level_value, (int, float)):
            continue
            
        if 'weekly' in level_name.lower() or 'week' in level_name.lower():
            weekly_levels[level_name] = level_value
        else:
            other_levels[level_name] = level_value

    # Print some information for debugging
    print(f"\n--- Analyzing touched levels (ADVANCED TOUCHING LOGIC) ---")
    print(f"Candle OHLC: Open={open0}, High={high0}, Low={low0}, Close={close0}")
    print(f"Candle Type: {candle_type}")
    print(f"Level touch threshold: {level_touch_threshold_pct}%")
    print(f"Total price levels: {len(price_levels)} (Weekly: {len(weekly_levels)}, Other: {len(other_levels)})")

    # Check each price level for advanced touching logic
    all_levels_to_check = {**weekly_levels, **other_levels}
    
    for level_name, level_value in all_levels_to_check.items():
        # Check if the level is touched by any candle up to lookback
        level_touched = False
        touching_candle = None

        # Check all relevant candles
        for i in range(lookback + 1):
            if i >= len(df) or abs(index - i) >= len(df):
                break

            check_candle = df.iloc[index - i]
            check_high = check_candle["High"]
            check_low = check_candle["Low"]
            check_close = check_candle["Close"]

            # Calculate threshold as percentage of level value
            threshold = level_value * (level_touch_threshold_pct / 100)

            # ADVANCED TOUCHING LOGIC WITH DIRECTIONAL CRITERIA
            candle_touches_level = False
            
            # Check if candle range intersects with level threshold
            level_range_low = level_value - threshold
            level_range_high = level_value + threshold
            
            # Basic range check: does the candle's high-low range overlap with level threshold range?
            if check_low <= level_range_high and check_high >= level_range_low:
                # Now apply directional criteria based on candle type
                if candle_type == "bull":
                    # For bullish patterns, level is only considered touched if close is ABOVE the level
                    if check_close > level_value:
                        candle_touches_level = True
                elif candle_type == "bear":
                    # For bearish patterns, level is only considered touched if close is BELOW the level
                    if check_close < level_value:
                        candle_touches_level = True
                else:
                    # For non-pattern candles, use basic proximity check
                    candle_touches_level = False

            if candle_touches_level:
                touch_levels.add(level_name)
                touching_candle = "current candle" if i == 0 else f"previous candle {i}"
                level_touched = True
                
                # Mark weekly levels as important
                importance = " [WEEKLY LEVEL]" if level_name in weekly_levels else ""
                direction_info = f" (close={check_close:.5f} vs level={level_value:.5f})"
                print(f"Level {level_name} = {level_value} TOUCHED by {touching_candle}{importance}{direction_info}")
                break

        if not level_touched:
            print(f"Level {level_name} = {level_value} NOT touched")

    # Convert to list and prioritize weekly levels
    touched_levels_list = []
    weekly_touched = [level for level in touch_levels if level in weekly_levels]
    other_touched = [level for level in touch_levels if level in other_levels]
    
    # Add weekly levels first (higher priority)
    touched_levels_list.extend(sorted(weekly_touched))
    touched_levels_list.extend(sorted(other_touched))

    print(f"Final touched levels: {touched_levels_list}")
    print(f"Weekly levels touched: {weekly_touched}")
    print(f"Other levels touched: {other_touched}")

    return candle_type, touched_levels_list