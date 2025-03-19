# MT5 Candlestick Chart Visualization

This application displays real-time candlestick charts for any symbol available in MetaTrader 5. It includes important reference levels like the daily open, previous day high, and previous day low.

## Features

- Real-time 10-minute candlestick charts
- Volume indicator
- Daily reference levels:
  - Daily open (yellow dashed line)
  - Previous day's high (lime solid line)
  - Previous day's low (red solid line)
- Automatic chart scaling and formatting
- Interactive chart updates

## File Structure

The application is organized into several modules for better maintainability:

- `main.py` - Entry point that initializes MT5 and handles user input
- `data_fetcher.py` - Functions to retrieve price data from MT5
- `chart_renderer.py` - Functions to render and update the candlestick chart

## Requirements

- Python 3.7+
- MetaTrader 5 (with active account)
- Required Python packages: `MetaTrader5`, `pandas`, `matplotlib`, `numpy`

## Installation

1. Ensure MetaTrader 5 is installed and properly configured
2. Install required packages:
   ```
   pip install pandas matplotlib numpy MetaTrader5
   ```

## Usage

1. Start MetaTrader 5 and log in to your account
2. Run the script:
   ```
   python main.py
   ```
3. Enter the symbol you want to chart (e.g., EURUSD, GBPUSD, XAUUSD)
4. The chart will display and update automatically
5. Press Ctrl+C in the terminal to exit

## Customization

You can customize the chart by modifying parameters in `chart_renderer.py`:

- Adjust `refresh_interval` in `main.py` to change how often the chart updates (in seconds)
- Modify colors and styles in the `draw_candles_and_volume` and `draw_daily_levels` functions
- Change the timeframe by modifying the `get_10min_data` function in `data_fetcher.py`

## Troubleshooting

- If the chart appears empty despite data being fetched, check your MetaTrader 5 connection and permissions
- If the symbol is not found, verify it's available in your MetaTrader 5 Market Watch
- For debugging issues, check the console output for detailed error messages

## License

This project is open-source and free to use.