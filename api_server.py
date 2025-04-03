"""
Integrated API server for MT5 monitoring and trading
"""
import os
import logging
import threading
import time
from datetime import datetime
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel, Field
from enum import Enum
import MetaTrader5 as mt5
import dotenv
from connection import mt5_connection

# Import from existing modules
from monitor import monitor_multiple_symbols, calculate_position_size
from data_fetcher import get_10min_data, get_price_levels
from candle_patterns import analyse_candle
from market_utils import get_current_price
from regression import calculate_multi_kernel_regression
from notifications import send_notification

# Load environment variables
dotenv.load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global variables for monitoring ---
monitor_thread = None
monitoring_active = False
monitoring_start_time = None
symbols_being_monitored = []
all_signals = {}
symbols_data = {}
stop_event = threading.Event()
signals_lock = threading.Lock()


# --- Pydantic Models ---
class TradeType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderTypeRequest(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class TradeRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., 'EURUSD', 'GBPUSD')")
    volume: float = Field(..., gt=0, description="Trade size in lots")
    trade_type: TradeType = Field(..., description="BUY or SELL")
    order_type: OrderTypeRequest = Field(..., description="MARKET, LIMIT, or STOP")
    price: Optional[float] = Field(None, description="Required price for LIMIT/STOP orders")
    sl: Optional[float] = Field(None, description="Stop Loss price level")
    tp: Optional[float] = Field(None, description="Take Profit price level")
    deviation: int = Field(20, description="Price deviation/slippage allowed for market orders (in points)")
    magic: int = Field(234000, description="Magic number for the order")
    comment: str = Field("API Trade", description="Order comment")


class TradeResponse(BaseModel):
    message: str
    order_ticket: Optional[int] = None
    mt5_result_comment: Optional[str] = None
    mt5_result_retcode: Optional[int] = None


class MonitorRequest(BaseModel):
    symbols: List[str] = Field(..., description="List of symbols to monitor")
    risk_percentage: float = Field(0.5, description="Risk percentage per trade")
    account_size: float = Field(100000, description="Account size in base currency")


class MonitorStatus(BaseModel):
    active: bool = Field(..., description="Whether monitoring is active")
    symbols: List[str] = Field(..., description="List of symbols being monitored")
    start_time: Optional[str] = Field(None, description="When monitoring was started")


class PriceRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol")


class PriceResponse(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    price: Optional[float] = Field(None, description="Current price")
    timestamp: str = Field(..., description="Timestamp of the price")


# --- FastAPI App ---
app = FastAPI(title="MT5 Trading and Monitoring API", version="1.0.0")


# Update the start_monitoring_background function in api_server.py

def start_monitoring_background(symbols: List[str], risk_percentage: float = 0.5, account_size: float = 100000):
    """
    Start monitoring in a background thread

    Args:
        symbols (List[str]): List of symbols to monitor
        risk_percentage (float): Risk percentage per trade
        account_size (float): Account size in base currency
    """
    global monitor_thread, monitoring_active, symbols_being_monitored, stop_event, all_signals, symbols_data, monitoring_start_time, signals_lock

    # Stop any existing monitoring
    if monitoring_active:
        stop_monitoring()

    # Reset variables
    stop_event = threading.Event()
    all_signals = {}
    symbols_data = {symbol: {} for symbol in symbols}
    symbols_being_monitored = symbols
    monitoring_start_time = datetime.now().isoformat()

    # Start monitoring in a new thread - FIXED PARAMETER PASSING
    monitor_thread = threading.Thread(
        target=monitor_multiple_symbols,
        args=(symbols, risk_percentage, account_size),
        kwargs={"all_signals": all_signals, "symbols_data": symbols_data, "stop_event": stop_event},
        daemon=True
    )
    monitor_thread.start()
    monitoring_active = True

    logging.info(f"Started monitoring for symbols: {symbols}")
    return True

def stop_monitoring():
    """Stop monitoring"""
    global monitor_thread, monitoring_active, symbols_being_monitored, stop_event

    if monitoring_active and stop_event:
        stop_event.set()
        if monitor_thread:
            monitor_thread.join(timeout=2.0)
        monitoring_active = False
        symbols_being_monitored = []
        logging.info("Stopped monitoring")
        return True
    return False


# --- API Endpoints ---

# Add this function to the API server
@app.post("/notification/test")
async def test_notification():
    """
    Test the notification system by sending a test message
    """
    try:
        from notifications import send_notification

        result = send_notification(
            "API Notification Test",
            "This is a test notification from the MT5 API server."
        )

        if result:
            return {"status": "success", "message": "Notification sent successfully"}
        else:
            return {"status": "error", "message": "Notification failed to send"}
    except Exception as e:
        logging.error(f"Error testing notification: {e}")
        raise HTTPException(status_code=500, detail=f"Error testing notification: {str(e)}")

@app.post("/trade/open", response_model=TradeResponse)
async def open_trade(trade_request: TradeRequest = Body(...)):
    """
    Opens a new trade on MetaTrader 5.
    Handles Market, Limit, and Stop orders.
    """
    logging.info(f"Received trade request: {trade_request.dict()}")

    try:
        with mt5_connection():  # Establish MT5 connection for this request
            # 1. Validate Symbol
            symbol_info = mt5.symbol_info(trade_request.symbol)
            if symbol_info is None:
                raise HTTPException(status_code=404, detail=f"Symbol '{trade_request.symbol}' not found.")
            if not symbol_info.visible:
                # Attempt to enable the symbol in MarketWatch
                if not mt5.symbol_select(trade_request.symbol, True):
                    raise HTTPException(status_code=400,
                                        detail=f"Failed to select/enable symbol '{trade_request.symbol}'. Check MarketWatch.")
                # Re-fetch info after selecting
                symbol_info = mt5.symbol_info(trade_request.symbol)
                if not symbol_info or not symbol_info.visible:
                    raise HTTPException(status_code=400,
                                        detail=f"Symbol '{trade_request.symbol}' is not visible/enabled in MarketWatch.")

            # 2. Determine MT5 Order Type and Price
            mt5_order_type = None
            price = 0.0
            point = symbol_info.point

            if trade_request.order_type == OrderTypeRequest.MARKET:
                if trade_request.trade_type == TradeType.BUY:
                    mt5_order_type = mt5.ORDER_TYPE_BUY
                    price = mt5.symbol_info_tick(trade_request.symbol).ask
                else:  # SELL
                    mt5_order_type = mt5.ORDER_TYPE_SELL
                    price = mt5.symbol_info_tick(trade_request.symbol).bid
                if price == 0:
                    raise HTTPException(status_code=503,
                                        detail="Could not retrieve market price (Bid/Ask is zero). Market might be closed or symbol unavailable.")

            elif trade_request.order_type == OrderTypeRequest.LIMIT:
                if trade_request.price is None:
                    raise HTTPException(status_code=400, detail="Parameter 'price' is required for LIMIT orders.")
                price = trade_request.price
                mt5_order_type = mt5.ORDER_TYPE_BUY_LIMIT if trade_request.trade_type == TradeType.BUY else mt5.ORDER_TYPE_SELL_LIMIT

            elif trade_request.order_type == OrderTypeRequest.STOP:
                if trade_request.price is None:
                    raise HTTPException(status_code=400, detail="Parameter 'price' is required for STOP orders.")
                price = trade_request.price
                mt5_order_type = mt5.ORDER_TYPE_BUY_STOP if trade_request.trade_type == TradeType.BUY else mt5.ORDER_TYPE_SELL_STOP

            # 3. Prepare Stop Loss and Take Profit
            sl_price = trade_request.sl if trade_request.sl is not None else 0.0
            tp_price = trade_request.tp if trade_request.tp is not None else 0.0

            # 4. Construct MT5 Request Dictionary
            mt5_request = {
                "action": mt5.TRADE_ACTION_DEAL if trade_request.order_type == OrderTypeRequest.MARKET else mt5.TRADE_ACTION_PENDING,
                "symbol": trade_request.symbol,
                "volume": trade_request.volume,
                "type": mt5_order_type,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": trade_request.deviation if trade_request.order_type == OrderTypeRequest.MARKET else 0,
                # Deviation only for market orders
                "magic": trade_request.magic,
                "comment": trade_request.comment,
                "type_time": mt5.ORDER_TIME_GTC,  # Good till cancelled
                "type_filling": mt5.ORDER_FILLING_IOC,
                # Fill or Kill; consider IOC if partial fills are acceptable mt5.ORDER_FILLING_IOC
            }

            logging.info(f"Constructed MT5 request: {mt5_request}")

            # 5. Send Order to MT5
            result = mt5.order_send(mt5_request)

            # 6. Process Result
            if result is None:
                last_error = mt5.last_error()
                logging.error(f"order_send failed, last error = {last_error}")
                raise HTTPException(status_code=500, detail=f"MT5 order_send call failed. Last error: {last_error}")

            logging.info(
                f"MT5 order_send result: Code={result.retcode}, Comment={result.comment}, Order Ticket={result.order}")

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                return TradeResponse(
                    message="Trade executed successfully." if trade_request.order_type == OrderTypeRequest.MARKET else "Pending order placed successfully.",
                    order_ticket=result.order,
                    mt5_result_comment=result.comment,
                    mt5_result_retcode=result.retcode
                )
            else:
                # Trade failed or partially filled etc.
                raise HTTPException(
                    status_code=400,  # Or 500 depending on if it's user error vs server error
                    detail=f"MT5 Order failed: {result.comment} (Code: {result.retcode})"
                )

    except ConnectionError as e:
        logging.exception("MT5 Connection failed.")  # Log the full traceback
        raise HTTPException(status_code=503, detail=f"MT5 connection error: {e}")
    except HTTPException as e:
        # Re-raise FastAPI's HTTPExceptions
        raise e
    except Exception as e:
        logging.exception("An unexpected error occurred during trade execution.")  # Log the full traceback
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")


@app.post("/monitor/start", response_model=MonitorStatus)
async def start_monitoring_endpoint(request: MonitorRequest, background_tasks: BackgroundTasks):
    """Start monitoring for a list of symbols"""
    global symbols_being_monitored, monitoring_active

    if monitoring_active:
        raise HTTPException(status_code=400, detail="Monitoring is already active. Stop it first.")

    # Send a notification when monitoring starts
    try:
        from notifications import send_notification
        send_notification(
            "MT5 Monitoring Started",
            f"Started monitoring symbols: {', '.join(request.symbols)}\n"
            f"Risk: {request.risk_percentage}% per trade on ${request.account_size:,.2f} account\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logging.error(f"Failed to send startup notification: {e}")

    # Verify all symbols
    valid_symbols = []
    try:
        with mt5_connection():
            for symbol in request.symbols:
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info is None:
                    logging.warning(f"Symbol '{symbol}' not found. Skipping.")
                    continue

                # Add to MarketWatch if needed
                if not symbol_info.visible:
                    mt5.symbol_select(symbol, True)

                valid_symbols.append(symbol)
    except Exception as e:
        logging.error(f"Error verifying symbols: {e}")
        raise HTTPException(status_code=503, detail=f"Error verifying symbols: {e}")

    if not valid_symbols:
        raise HTTPException(status_code=400, detail="No valid symbols found to monitor.")

    # Start monitoring in a background task
    background_tasks.add_task(
        start_monitoring_background,
        valid_symbols,
        request.risk_percentage,
        request.account_size
    )

    return MonitorStatus(
        active=True,
        symbols=valid_symbols,
        start_time=datetime.now().isoformat()
    )


@app.post("/monitor/stop")
async def stop_monitoring_endpoint():
    """Stop monitoring"""
    global monitoring_active

    if not monitoring_active:
        raise HTTPException(status_code=400, detail="Monitoring is not active.")

    success = stop_monitoring()
    if success:
        return {"message": "Monitoring stopped successfully."}
    else:
        raise HTTPException(status_code=500, detail="Failed to stop monitoring.")


@app.get("/monitor/status", response_model=MonitorStatus)
async def get_monitor_status():
    """Get current monitoring status"""
    global monitoring_active, symbols_being_monitored, monitoring_start_time

    return MonitorStatus(
        active=monitoring_active,
        symbols=symbols_being_monitored,
        start_time=monitoring_start_time
    )


@app.get("/monitor/signals")
async def get_signals():
    """Get current signals for all monitored symbols"""
    global all_signals, monitoring_active, signals_lock

    if not monitoring_active:
        raise HTTPException(status_code=400, detail="Monitoring is not active.")

    with signals_lock:
        result = {}
        for symbol, signals in all_signals.items():
            result[symbol] = list(signals)  # Convert deque to list

    return result


@app.post("/data/price", response_model=PriceResponse)
async def get_price(request: PriceRequest):
    """Get current price for a symbol"""
    try:
        with mt5_connection():
            # Make sure symbol is in MarketWatch
            symbol_info = mt5.symbol_info(request.symbol)
            if symbol_info is None:
                raise HTTPException(status_code=404, detail=f"Symbol '{request.symbol}' not found.")

            if not symbol_info.visible:
                mt5.symbol_select(request.symbol, True)

            # Get current price
            price = get_current_price(request.symbol)

            if price is None:
                raise HTTPException(status_code=400, detail=f"Could not get price for '{request.symbol}'.")

            return PriceResponse(
                symbol=request.symbol,
                price=price,
                timestamp=datetime.now().isoformat()
            )
    except Exception as e:
        logging.error(f"Error getting price: {e}")
        raise HTTPException(status_code=503, detail=f"Error getting price: {e}")


@app.post("/data/chart")
async def get_chart_data(symbol: str, timeframe: str = "M10", num_bars: int = 100):
    """Get chart data for a symbol"""
    try:
        with mt5_connection():
            # Make sure symbol is in MarketWatch
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found.")

            if not symbol_info.visible:
                mt5.symbol_select(symbol, True)

            # Get chart data
            data = get_10min_data(symbol, num_bars)

            if data is None or data.empty:
                raise HTTPException(status_code=400, detail=f"Could not get chart data for '{symbol}'.")

            # Convert DataFrame to list of dictionaries
            result = []
            for index, row in data.iterrows():
                result.append({
                    "time": index.isoformat(),
                    "open": row["Open"],
                    "high": row["High"],
                    "low": row["Low"],
                    "close": row["Close"],
                    "volume": row["Volume"] if "Volume" in row else None
                })

            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "data": result
            }
    except Exception as e:
        logging.error(f"Error getting chart data: {e}")
        raise HTTPException(status_code=503, detail=f"Error getting chart data: {e}")


@app.post("/data/levels")
async def get_levels(symbol: str):
    """Get price levels for a symbol"""
    try:
        with mt5_connection():
            # Make sure symbol is in MarketWatch
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found.")

            if not symbol_info.visible:
                mt5.symbol_select(symbol, True)

            # Get price levels
            levels = get_price_levels(symbol)

            if not levels:
                return {
                    "symbol": symbol,
                    "levels": {},
                    "message": "No price levels available for this symbol",
                    "timestamp": datetime.now().isoformat()
                }

            return {
                "symbol": symbol,
                "levels": levels,
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        logging.error(f"Error getting price levels: {e}")
        raise HTTPException(status_code=503, detail=f"Error getting price levels: {e}")

"""
Updates to the /data/analyze endpoint in api_server.py
"""
@app.post("/data/analyze")
async def analyze_symbol(symbol: str, risk_percentage: float = 0.5, account_size: float = 100000):
    """Analyze a symbol for trading signals"""
    logging.info(f"Analyzing symbol: {symbol} with risk {risk_percentage}% on ${account_size} account")

    try:
        with mt5_connection():
            # Make sure symbol is in MarketWatch
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found.")

            if not symbol_info.visible:
                mt5.symbol_select(symbol, True)

            # Get chart data
            data = get_10min_data(symbol)

            if data is None or data.empty:
                raise HTTPException(status_code=400, detail=f"Could not get chart data for '{symbol}'.")

            # Get price levels
            levels = get_price_levels(symbol)

            # Analyze candle patterns
            candle_type, touch_levels = analyse_candle(
                data,
                index=-1,
                lookback=2,
                price_levels=levels
            )

            # Get current price
            current_price = (symbol_info.bid + symbol_info.ask) / 2

            result = {
                "symbol": symbol,
                "current_price": current_price,
                "candle_type": candle_type,
                "touch_levels": touch_levels,
                "price_levels": levels,
                "timestamp": datetime.now().isoformat()
            }

            # Calculate position size if we have a signal
            if candle_type != "none" and len(touch_levels) > 0 and current_price is not None:
                # Calculate true range for stop loss suggestion
                true_range = max(data.iloc[-1]['High'], data.iloc[-2]['High']) - min(data.iloc[-1]['Low'],
                                                                                     data.iloc[-2]['Low'])

                logging.info(f"True range: {true_range}")

                # Calculate suggested stop loss distance (1.5x the true range)
                stop_distance_price = true_range * 1.5

                logging.info(f"Stop distance price: {stop_distance_price}")

                if stop_distance_price <= 0:
                    # Use fallback method - percentage of current price
                    stop_distance_price = current_price * 0.01  # 1% of current price
                    logging.info(f"Using fallback stop distance: {stop_distance_price} (1% of price)")

                # Calculate stop loss level
                stop_loss = current_price - stop_distance_price if candle_type == "bull" else current_price + stop_distance_price

                # Calculate position size - IMPORTANT: Make sure risk_percentage is passed correctly
                logging.info(
                    f"Calculating position size with risk_percentage={risk_percentage}, account_size={account_size}")
                position_size, stop_points, risk_amount = calculate_position_size(
                    symbol,
                    stop_distance_price,
                    risk_percentage,  # Already in percentage form (e.g., 0.5 for 0.5%)
                    account_size
                )

                logging.info(f"Position size calculation result: {position_size} lots")

                # Calculate regression indicator
                try:
                    regression_value, regression_color, regression_direction = calculate_multi_kernel_regression(
                        symbol, mt5.TIMEFRAME_M10, bandwidth=25
                    )
                    regression_trend = "UPTREND" if regression_direction else "DOWNTREND"
                except Exception as e:
                    logging.error(f"Error calculating regression: {e}")
                    regression_value = None
                    regression_trend = "UNKNOWN"

                result["trade_recommendation"] = {
                    "direction": "BUY" if candle_type == "bull" else "SELL",
                    "entry_price": current_price,
                    "stop_loss": stop_loss,
                    "stop_distance_price": stop_distance_price,
                    "stop_distance_points": stop_points,
                    "position_size": position_size,
                    "risk_amount": risk_amount,
                    "regression_trend": regression_trend
                }

            return result
    except Exception as e:
        logging.error(f"Error analyzing symbol: {e}")
        raise HTTPException(status_code=503, detail=f"Error analyzing symbol: {e}")


# --- Health Check Endpoint ---
@app.get("/health", status_code=200)
async def health_check():
    """Basic health check endpoint."""
    global monitoring_active, symbols_being_monitored

    # Try a basic MT5 connection test
    mt5_status = "Unknown"
    try:
        with mt5_connection():
            mt5_status = "Connected"
    except Exception as e:
        mt5_status = f"Connection Error: {str(e)}"

    return {
        "status": "ok",
        "monitoring_active": monitoring_active,
        "symbols_being_monitored": symbols_being_monitored,
        "mt5_status": mt5_status
    }


# --- Run the API (using uvicorn) ---
if __name__ == "__main__":
    import uvicorn

    # Make sure MT5 credentials are set as environment variables before running!
    print("Starting FastAPI server for MT5 Trading & Monitoring API...")
    print("Ensure MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER environment variables are set.")
    print("API documentation will be available at http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)