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

    # Detect candle patterns - IMPROVED LOGIC
    # Engulfing patterns
    bull_engulfing = low0 < low1 and high0 > high1 and close0 > open0 and close0 > close1
    bear_engulfing = high0 > high1 and low0 < low1 and close0 < open0 and close0 < close1

    # Inside failure candles (IFC) - more restrictive
    large_body = abs(close0 - open0) >= 0.5 * (high0 - low0)
    bull_ifc = close0 > high1 and close0 > high2 and large_body and close0 > open0 and (close0 - open0) > (high0 - low0) * 0.6
    bear_ifc = close0 < low1 and close0 < low2 and large_body and close0 < open0 and (open0 - close0) > (high0 - low0) * 0.6

    # Determine candle type
    candle_type = "bull" if bull_engulfing or bull_ifc else "bear" if bear_engulfing or bear_ifc else "none"

    # CRITICAL REQUIREMENT: Only generate signals if the CURRENT candle is a pattern
    if candle_type == "none":
        print(f"\n🚫 NO SIGNAL: Current candle is not a bullish or bearish pattern")
        print(f"   Pattern required: Engulfing or IFC")
        print(f"   Current candle: {candle_type}")
        return candle_type, []

    # If no price levels are provided, skip level detection
    if not price_levels:
        return candle_type, []

    # Get configurable threshold from environment
    level_touch_threshold_pct = float(os.getenv('LEVEL_TOUCH_THRESHOLD', '0.05'))
    
    # STEP 1: First find which levels are touched by ANY candle in lookback period
    # STEP 2: Then apply directional criteria only if a pattern is detected
    
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
    print(f"\n--- Analyzing touched levels (IMPROVED LOGIC) ---")
    print(f"Current Candle OHLC: Open={open0:.5f}, High={high0:.5f}, Low={low0:.5f}, Close={close0:.5f}")
    print(f"Candle Type: {candle_type}")
    print(f"Level touch threshold: {level_touch_threshold_pct}%")
    print(f"Total price levels: {len(price_levels)} (Weekly: {len(weekly_levels)}, Other: {len(other_levels)})")

    # IMPROVED LEVEL TOUCHING LOGIC
    touch_levels = set()
    all_levels_to_check = {**weekly_levels, **other_levels}
    
    for level_name, level_value in all_levels_to_check.items():
        level_touched = False
        touching_candle_info = None

        # Check all relevant candles for basic level interaction
        for i in range(lookback + 1):
            if i >= len(df) or abs(index - i) >= len(df):
                break

            check_candle = df.iloc[index - i]
            check_high = check_candle["High"]
            check_low = check_candle["Low"]
            check_close = check_candle["Close"]

            # Calculate threshold - improved to handle different price ranges
            if level_value > 1000:  # For high-value instruments (indices, etc.)
                threshold = level_value * (level_touch_threshold_pct / 100)
            else:  # For forex and lower-value instruments
                threshold = max(level_value * (level_touch_threshold_pct / 100), 0.0001)

            # Check if candle range intersects with level threshold
            level_range_low = level_value - threshold
            level_range_high = level_value + threshold
            
            # Basic proximity check: does the candle touch the level within threshold?
            candle_touches_level_basic = (check_low <= level_range_high and check_high >= level_range_low)
            
            if candle_touches_level_basic:
                # APPLY DIRECTIONAL CRITERIA ONLY FOR PATTERN CANDLES
                passes_directional_check = True
                
                # Only apply directional criteria to the current candle (i=0) when pattern is detected
                if i == 0 and candle_type != "none":
                    if candle_type == "bull":
                        # For bullish patterns, current candle close must be above the level
                        passes_directional_check = check_close > level_value
                    elif candle_type == "bear":
                        # For bearish patterns, current candle close must be below the level
                        passes_directional_check = check_close < level_value
                
                if passes_directional_check:
                    touch_levels.add(level_name)
                    touching_candle_info = "current candle" if i == 0 else f"previous candle {i}"
                    level_touched = True
                    
                    # Enhanced logging
                    importance = " [WEEKLY LEVEL]" if level_name in weekly_levels else ""
                    direction_info = f" (close={check_close:.5f} vs level={level_value:.5f}, threshold=±{threshold:.5f})"
                    pattern_info = f" [PATTERN: {candle_type.upper()}]" if candle_type != "none" and i == 0 else ""
                    print(f"✓ Level {level_name} = {level_value:.5f} TOUCHED by {touching_candle_info}{importance}{direction_info}{pattern_info}")
                    break
                else:
                    # Level was touched but failed directional criteria
                    print(f"✗ Level {level_name} = {level_value:.5f} touched by {touching_candle_info} but failed directional criteria (close={check_close:.5f})")

        if not level_touched:
            print(f"○ Level {level_name} = {level_value:.5f} NOT touched")

    # Convert to list and prioritize weekly levels
    touched_levels_list = []
    weekly_touched = [level for level in touch_levels if level in weekly_levels]
    other_touched = [level for level in touch_levels if level in other_levels]
    
    # Add weekly levels first (higher priority)
    touched_levels_list.extend(sorted(weekly_touched))
    touched_levels_list.extend(sorted(other_touched))

    print(f"\n📊 SUMMARY:")
    print(f"   Pattern: {candle_type.upper() if candle_type != 'none' else 'No pattern detected'}")
    print(f"   Weekly levels touched: {weekly_touched}")
    print(f"   Other levels touched: {other_touched}")
    print(f"   Total levels: {len(touched_levels_list)}")

    return candle_type, touched_levels_list