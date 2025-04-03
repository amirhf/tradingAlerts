import MetaTrader5 as mt5
import os
import logging
from fastapi import FastAPI, HTTPException, Body, Depends
from pydantic import BaseModel, Field
from enum import Enum
from contextlib import contextmanager
from typing import Optional, Union
import dotenv

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load credentials from environment variables
dotenv.load_dotenv()
MT5_ACCOUNT = int(os.getenv("MT5_ACCOUNT", 0))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")
MT5_PATH = os.getenv("MT5_PATH") # Optional, use None if not set

if not all([MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER]):
    logging.error("Missing MT5 credentials in environment variables (MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER)")
    # You might want to exit here in a real application
    # exit(1)

# --- Enums and Pydantic Models ---

class TradeType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderTypeRequest(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    # You could add STOP_LIMIT here if needed

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

# --- MT5 Connection Management ---

@contextmanager
def mt5_connection():
    """Context manager for establishing and closing MT5 connection."""
    initialized = False
    try:
        kwargs = {
            "login": MT5_ACCOUNT,
            "password": MT5_PASSWORD,
            "server": MT5_SERVER,
        }
        if MT5_PATH:
            kwargs["path"] = MT5_PATH

        initialized = mt5.initialize(**kwargs)

        if not initialized:
            error_code = mt5.last_error()
            logging.error(f"MT5 initialize() failed, error code = {error_code}")
            raise ConnectionError(f"Failed to connect to MT5: {error_code}")

        # Optional: Check login state
        if not mt5.login(MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER):
             error_code = mt5.last_error()
             logging.error(f"MT5 login failed for account {MT5_ACCOUNT}, error code = {error_code}")
             mt5.shutdown() # Ensure shutdown if login fails after init
             raise ConnectionError(f"Failed to login to MT5 account {MT5_ACCOUNT}: {error_code}")

        logging.info(f"MT5 Connection successful for account {MT5_ACCOUNT} on server {MT5_SERVER}")
        yield # Yield control back to the caller within the 'with' block
    except Exception as e:
        logging.error(f"An error occurred during MT5 connection or operation: {e}")
        # Re-raise the exception to be caught by FastAPI's error handling
        raise
    finally:
        if initialized:
            logging.info("Shutting down MT5 connection.")
            mt5.shutdown()

# --- FastAPI App ---
app = FastAPI(title="MT5 Trading API", version="1.0.0")

# --- API Endpoints ---

@app.post("/trade/open", response_model=TradeResponse)
async def open_trade(trade_request: TradeRequest = Body(...)):
    """
    Opens a new trade on MetaTrader 5.
    Handles Market, Limit, and Stop orders.
    """
    logging.info(f"Received trade request: {trade_request.dict()}")

    try:
        with mt5_connection(): # Establish MT5 connection for this request
            # 1. Validate Symbol
            symbol_info = mt5.symbol_info(trade_request.symbol)
            if symbol_info is None:
                raise HTTPException(status_code=404, detail=f"Symbol '{trade_request.symbol}' not found.")
            if not symbol_info.visible:
                # Attempt to enable the symbol in MarketWatch
                if not mt5.symbol_select(trade_request.symbol, True):
                     raise HTTPException(status_code=400, detail=f"Failed to select/enable symbol '{trade_request.symbol}'. Check MarketWatch.")
                # Re-fetch info after selecting
                symbol_info = mt5.symbol_info(trade_request.symbol)
                if not symbol_info or not symbol_info.visible:
                     raise HTTPException(status_code=400, detail=f"Symbol '{trade_request.symbol}' is not visible/enabled in MarketWatch.")


            # 2. Determine MT5 Order Type and Price
            mt5_order_type = None
            price = 0.0
            point = symbol_info.point

            if trade_request.order_type == OrderTypeRequest.MARKET:
                if trade_request.trade_type == TradeType.BUY:
                    mt5_order_type = mt5.ORDER_TYPE_BUY
                    price = mt5.symbol_info_tick(trade_request.symbol).ask
                else: # SELL
                    mt5_order_type = mt5.ORDER_TYPE_SELL
                    price = mt5.symbol_info_tick(trade_request.symbol).bid
                if price == 0:
                    raise HTTPException(status_code=503, detail="Could not retrieve market price (Bid/Ask is zero). Market might be closed or symbol unavailable.")

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

            # Basic validation for SL/TP placement (more advanced checks might be needed)
            # For BUY: SL < Price, TP > Price
            # For SELL: SL > Price, TP < Price
            # This needs careful handling especially for pending orders.
            # MT5 server often rejects invalid levels anyway.

            # 4. Construct MT5 Request Dictionary
            mt5_request = {
                "action": mt5.TRADE_ACTION_DEAL if trade_request.order_type == OrderTypeRequest.MARKET else mt5.TRADE_ACTION_PENDING,
                "symbol": trade_request.symbol,
                "volume": trade_request.volume,
                "type": mt5_order_type,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": trade_request.deviation if trade_request.order_type == OrderTypeRequest.MARKET else 0, # Deviation only for market orders
                "magic": trade_request.magic,
                "comment": trade_request.comment,
                "type_time": mt5.ORDER_TIME_GTC,  # Good till cancelled
                "type_filling": mt5.ORDER_FILLING_IOC, # Fill or Kill; consider IOC if partial fills are acceptable mt5.ORDER_FILLING_IOC
            }

            logging.info(f"Constructed MT5 request: {mt5_request}")

            # 5. Send Order to MT5
            result = mt5.order_send(mt5_request)

            # 6. Process Result
            if result is None:
                last_error = mt5.last_error()
                logging.error(f"order_send failed, last error = {last_error}")
                raise HTTPException(status_code=500, detail=f"MT5 order_send call failed. Last error: {last_error}")

            logging.info(f"MT5 order_send result: Code={result.retcode}, Comment={result.comment}, Order Ticket={result.order}")

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
                    status_code=400, # Or 500 depending on if it's user error vs server error
                    detail=f"MT5 Order failed: {result.comment} (Code: {result.retcode})"
                )

    except ConnectionError as e:
        logging.exception("MT5 Connection failed.") # Log the full traceback
        raise HTTPException(status_code=503, detail=f"MT5 connection error: {e}")
    except HTTPException as e:
        # Re-raise FastAPI's HTTPExceptions
        raise e
    except Exception as e:
        logging.exception("An unexpected error occurred during trade execution.") # Log the full traceback
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")

# --- Health Check Endpoint ---
@app.get("/health", status_code=200)
async def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}


# --- Run the API (using uvicorn) ---
if __name__ == "__main__":
    import uvicorn
    # Make sure MT5 credentials are set as environment variables before running!
    print("Starting FastAPI server for MT5 Trading API...")
    print("Ensure MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER environment variables are set.")
    print("API documentation will be available at http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)