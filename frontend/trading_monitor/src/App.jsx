import React, { useState, useEffect } from 'react';
import { XCircle, CheckCircle, PlayCircle, StopCircle, Settings, RefreshCw, ChevronRight, BarChart2, Clock, DollarSign, ArrowUp, ArrowDown, AlertCircle, TrendingUp, TrendingDown } from 'lucide-react';

// Main App Component
const App = () => {
  // State for API data
  const [monitorStatus, setMonitorStatus] = useState({ active: false, symbols: [], start_time: null });
  const [signals, setSignals] = useState({});
  const [healthStatus, setHealthStatus] = useState({ status: 'unknown', mt5_status: 'Unknown' });
  const [symbolDetails, setSymbolDetails] = useState({});
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Symbol input state
  const [symbolInput, setSymbolInput] = useState('EURUSD,GBPUSD,USDJPY,XAUUSD');
  const [riskPercentage, setRiskPercentage] = useState(0.5);
  const [accountSize, setAccountSize] = useState(100000);
  
  // View state
  const [activeView, setActiveView] = useState('dashboard'); // 'dashboard', 'symbolDetail'

  // API base URL
  const API_BASE_URL = 'http://localhost:8000';

  // Fetch health status
  const fetchHealthStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`, {
        // Adding these options won't solve CORS but will make the error more descriptive
        mode: 'cors',
        headers: {
          'Content-Type': 'application/json'
        },
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      
      const data = await response.json();
      setHealthStatus(data);
      setError(null); // Clear any previous errors
    } catch (err) {
      console.error('Error fetching health status:', err);
      if (err.message.includes('Failed to fetch') || err.name === 'TypeError') {
        setError('CORS Error: Cannot connect to API server. Make sure the API server is running and has CORS enabled.');
        setHealthStatus({ status: 'error', mt5_status: 'Unknown' });
      } else {
        setError(`Could not connect to API server: ${err.message}`);
      }
    }
  };

  // Fetch monitor status
  const fetchMonitorStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/monitor/status`);
      const data = await response.json();
      setMonitorStatus(data);
    } catch (err) {
      console.error('Error fetching monitor status:', err);
    }
  };

  // Fetch signals
  const fetchSignals = async () => {
    if (!monitorStatus.active) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/monitor/signals`);
      const data = await response.json();
      setSignals(data);
    } catch (err) {
      console.error('Error fetching signals:', err);
    }
  };

  // Start monitoring
  const startMonitoring = async () => {
    setIsLoading(true);
    try {
      const symbols = symbolInput.split(',').map(s => s.trim());
      
      const response = await fetch(`${API_BASE_URL}/monitor/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbols: symbols,
          risk_percentage: parseFloat(riskPercentage),
          account_size: parseFloat(accountSize)
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start monitoring');
      }

      await fetchMonitorStatus();
      setError(null);
    } catch (err) {
      console.error('Error starting monitoring:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Stop monitoring
  const stopMonitoring = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/monitor/stop`, {
        method: 'POST',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to stop monitoring');
      }

      await fetchMonitorStatus();
      setError(null);
    } catch (err) {
      console.error('Error stopping monitoring:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch symbol details
  const fetchSymbolDetails = async (symbol) => {
    setIsLoading(true);
    
    try {
      // Fetch chart data - using query parameters instead of body
      const chartResponse = await fetch(
        `${API_BASE_URL}/data/chart?symbol=${encodeURIComponent(symbol)}&timeframe=M10&num_bars=50`, 
        { method: 'POST' }
      );
      
      // Fetch levels - using query parameters
      const levelsResponse = await fetch(
        `${API_BASE_URL}/data/levels?symbol=${encodeURIComponent(symbol)}`, 
        { method: 'POST' }
      );

      // Fetch analysis - using query parameters
      const analysisResponse = await fetch(
        `${API_BASE_URL}/data/analyze?symbol=${encodeURIComponent(symbol)}&risk_percentage=${riskPercentage}&account_size=${accountSize}`, 
        { method: 'POST' }
      );

      // Fetch current price - this endpoint expects a body
      const priceResponse = await fetch(`${API_BASE_URL}/data/price`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: symbol
        }),
      });

      // Process all data
      const [chartData, levelsData, analysisData, priceData] = await Promise.all([
        chartResponse.json(),
        levelsResponse.json(),
        analysisResponse.json(),
        priceResponse.json()
      ]);

      setSymbolDetails({
        ...symbolDetails,
        [symbol]: {
          chart: chartData,
          levels: levelsData,
          analysis: analysisData,
          price: priceData
        }
      });
      
      setSelectedSymbol(symbol);
      setActiveView('symbolDetail');
      setError(null);
    } catch (err) {
      console.error('Error fetching symbol details:', err);
      setError(`Failed to fetch details for ${symbol}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Refresh all data
  const refreshData = async () => {
    await fetchHealthStatus();
    await fetchMonitorStatus();
    if (monitorStatus.active) {
      await fetchSignals();
    }
  };

  // Initialize and refresh data at intervals
  useEffect(() => {
    refreshData();
    
    const interval = setInterval(() => {
      refreshData();
    }, 10000); // Refresh every 10 seconds

    return () => clearInterval(interval);
  }, [monitorStatus.active]);

  // Format timestamp for display
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleString();
  };

  // Get signal count
  const getSignalCount = () => {
    return Object.values(signals).reduce((count, symbolSignals) => count + (symbolSignals.length || 0), 0);
  };

  // Dashboard View
  const renderDashboard = () => (
    <div className="space-y-6">
      {/* System Status */}
      <div className="bg-white shadow rounded-lg p-4">
        <h2 className="text-lg font-medium mb-4">System Status</h2>
        
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4 relative">
            <strong className="font-bold">Error: </strong>
            <span className="block sm:inline">{error}</span>
            {error.includes('CORS') && (
              <div className="mt-2 text-sm">
                <p>To fix CORS issues, add the following code to your api_server.py file:</p>
                <pre className="bg-gray-800 text-white p-2 rounded mt-1 overflow-x-auto text-xs">
                  {`from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)`}
                </pre>
              </div>
            )}
          </div>
        )}
        
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center space-x-2">
            <div className="flex items-center">
              <span className="font-medium mr-2">API Server:</span>
              {healthStatus.status === 'ok' ? 
                <span className="text-green-500 flex items-center"><CheckCircle size={18} className="mr-1"/> Connected</span> : 
                <span className="text-red-500 flex items-center"><XCircle size={18} className="mr-1"/> Disconnected</span>
              }
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <div className="flex items-center">
              <span className="font-medium mr-2">MT5 Status:</span>
              {healthStatus.mt5_status === 'Connected' ? 
                <span className="text-green-500 flex items-center"><CheckCircle size={18} className="mr-1"/> Connected</span> : 
                <span className="text-red-500 flex items-center"><XCircle size={18} className="mr-1"/> {healthStatus.mt5_status}</span>
              }
            </div>
          </div>
        </div>
      </div>

      {/* Monitoring Control */}
      <div className="bg-white shadow rounded-lg p-4">
        <h2 className="text-lg font-medium mb-4">Monitoring Control</h2>
        {error && <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">{error}</div>}
        
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Symbols to Monitor (comma-separated)</label>
          <input 
            type="text" 
            className="w-full p-2 border rounded focus:ring focus:ring-blue-300"
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value)}
            disabled={monitorStatus.active || isLoading}
          />
        </div>
        
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Risk Percentage (%)</label>
            <input 
              type="number" 
              className="w-full p-2 border rounded focus:ring focus:ring-blue-300"
              value={riskPercentage}
              onChange={(e) => setRiskPercentage(e.target.value)}
              disabled={monitorStatus.active || isLoading}
              step="0.1"
              min="0.1"
              max="5"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Account Size ($)</label>
            <input 
              type="number" 
              className="w-full p-2 border rounded focus:ring focus:ring-blue-300"
              value={accountSize}
              onChange={(e) => setAccountSize(e.target.value)}
              disabled={monitorStatus.active || isLoading}
              step="1000"
              min="1000"
            />
          </div>
        </div>
        
        <div className="flex space-x-4">
          <button
            className={`flex items-center px-4 py-2 rounded ${monitorStatus.active ? 'bg-gray-300 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700 text-white'}`}
            onClick={startMonitoring}
            disabled={monitorStatus.active || isLoading}
          >
            <PlayCircle size={18} className="mr-2" />
            Start Monitoring
          </button>
          
          <button
            className={`flex items-center px-4 py-2 rounded ${!monitorStatus.active ? 'bg-gray-300 cursor-not-allowed' : 'bg-red-600 hover:bg-red-700 text-white'}`}
            onClick={stopMonitoring}
            disabled={!monitorStatus.active || isLoading}
          >
            <StopCircle size={18} className="mr-2" />
            Stop Monitoring
          </button>
          
          <button
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            onClick={refreshData}
            disabled={isLoading}
          >
            <RefreshCw size={18} className={`mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
        
        {monitorStatus.active && (
          <div className="mt-4 text-sm">
            <div className="flex items-center text-green-600">
              <CheckCircle size={16} className="mr-1" />
              <span>Monitoring Active</span>
            </div>
            <div>Started: {formatTimestamp(monitorStatus.start_time)}</div>
            <div>Monitoring {monitorStatus.symbols.length} symbols: {monitorStatus.symbols.join(', ')}</div>
          </div>
        )}
      </div>
      
      {/* Monitored Symbols */}
      {monitorStatus.active && (
        <div className="bg-white shadow rounded-lg p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-medium">Monitored Symbols ({monitorStatus.symbols.length})</h2>
            <div className="text-sm text-gray-500">
              <span className="font-medium">{getSignalCount()}</span> active signals
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {monitorStatus.symbols.map((symbol) => {
              const symbolSignals = signals[symbol] || [];
              const hasSignals = symbolSignals.length > 0;
              const latestSignal = hasSignals ? symbolSignals[0] : null;
              const signalType = latestSignal ? latestSignal.type : null;
              
              return (
                <div 
                  key={symbol}
                  className="border rounded p-3 hover:shadow-md cursor-pointer transition-shadow"
                  onClick={() => fetchSymbolDetails(symbol)}
                >
                  <div className="flex justify-between items-center mb-2">
                    <div className="font-bold text-lg">{symbol}</div>
                    {hasSignals && (
                      <div className={`flex items-center ${signalType === 'bull' ? 'text-green-600' : 'text-red-600'}`}>
                        {signalType === 'bull' ? 
                          <ArrowUp size={18} /> : 
                          <ArrowDown size={18} />
                        }
                      </div>
                    )}
                  </div>
                  
                  {hasSignals ? (
                    <div className="text-sm">
                      <div className="flex justify-between">
                        <div className="flex items-center text-gray-600">
                          <Clock size={14} className="mr-1" />
                          {new Date(latestSignal.time).toLocaleTimeString()}
                        </div>
                        <div className="flex items-center">
                          <DollarSign size={14} className="mr-1" />
                          {latestSignal.position_size.toFixed(2)} lots
                        </div>
                      </div>
                      <div className="mt-1 flex justify-between">
                        <div className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                          {latestSignal.levels.join(', ')}
                        </div>
                        <div className={`text-xs flex items-center ${latestSignal.regression_trend === 'UPTREND' ? 'text-green-600' : 'text-red-600'}`}>
                          {latestSignal.regression_trend === 'UPTREND' ? 
                            <><TrendingUp size={14} className="mr-1" /> Uptrend</> : 
                            <><TrendingDown size={14} className="mr-1" /> Downtrend</>
                          }
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500 flex items-center">
                      <AlertCircle size={14} className="mr-1" />
                      No active signals
                    </div>
                  )}
                  
                  <div className="flex justify-end mt-2">
                    <ChevronRight size={16} className="text-gray-400" />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );

  // Symbol Detail View
  const renderSymbolDetail = () => {
    if (!selectedSymbol || !symbolDetails[selectedSymbol]) {
      return <div>Loading symbol details...</div>;
    }

    const details = symbolDetails[selectedSymbol];
    const analysis = details.analysis || {};
    const levels = details.levels?.levels || {};
    
    // Group levels by category
    const levelCategories = {
      "Daily Levels": ['today_open', 'yesterday_open', 'yesterday_high', 'yesterday_low', 'yesterday_close'],
      "Pivot Levels": Object.keys(levels).filter(k => k.includes('pivot')),
      "Asian Session": Object.keys(levels).filter(k => k.includes('asian'))
    };

    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <button 
            className="flex items-center text-blue-600 hover:text-blue-800"
            onClick={() => setActiveView('dashboard')}
          >
            <ChevronRight size={18} className="transform rotate-180 mr-1" />
            Back to Dashboard
          </button>
          
          <button
            className="flex items-center px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
            onClick={() => fetchSymbolDetails(selectedSymbol)}
            disabled={isLoading}
          >
            <RefreshCw size={14} className={`mr-1 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
        
        {/* Symbol Overview */}
        <div className="bg-white shadow rounded-lg p-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-bold">{selectedSymbol}</h2>
            <div className="text-lg font-medium">
              {details.price?.price ? `$${details.price.price.toFixed(5)}` : 'Price unavailable'}
            </div>
          </div>
          
          {analysis.trade_recommendation && (
            <div className={`mt-4 border p-3 rounded-lg ${analysis.trade_recommendation.direction === 'BUY' ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
              <h3 className={`font-bold ${analysis.trade_recommendation.direction === 'BUY' ? 'text-green-700' : 'text-red-700'}`}>
                {analysis.trade_recommendation.direction} Signal
              </h3>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 mt-2 text-sm">
                <div className="flex items-center">
                  <span className="font-medium mr-1">Entry:</span>
                  ${analysis.trade_recommendation.entry_price.toFixed(5)}
                </div>
                <div className="flex items-center">
                  <span className="font-medium mr-1">Stop Loss:</span>
                  ${analysis.trade_recommendation.stop_loss.toFixed(5)}
                </div>
                <div className="flex items-center">
                  <span className="font-medium mr-1">Position Size:</span>
                  {analysis.trade_recommendation.position_size.toFixed(2)} lots
                </div>
                <div className="flex items-center">
                  <span className="font-medium mr-1">Risk Amount:</span>
                  ${analysis.trade_recommendation.risk_amount.toFixed(2)}
                </div>
                <div className="flex items-center col-span-2">
                  <span className="font-medium mr-1">Trend:</span>
                  <span className={`flex items-center ${analysis.trade_recommendation.regression_trend === 'UPTREND' ? 'text-green-600' : 'text-red-600'}`}>
                    {analysis.trade_recommendation.regression_trend === 'UPTREND' ? 
                      <><TrendingUp size={14} className="mr-1" /> Uptrend</> : 
                      <><TrendingDown size={14} className="mr-1" /> Downtrend</>
                    }
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
        
        {/* Price Chart Placeholder */}
        <div className="bg-white shadow rounded-lg p-4">
          <h2 className="text-lg font-medium mb-4 flex items-center">
            <BarChart2 size={18} className="mr-2" />
            Price Chart
          </h2>
          
          <div className="h-64 bg-gray-100 rounded flex items-center justify-center">
            <div className="text-center text-gray-500">
              <p>Chart visualization would be implemented here</p>
              <p className="text-sm">Last {details.chart?.data?.length || 0} candles available via API</p>
            </div>
          </div>
        </div>
        
        {/* Price Levels */}
        <div className="bg-white shadow rounded-lg p-4">
          <h2 className="text-lg font-medium mb-4">Price Levels</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(levelCategories).map(([category, levelKeys]) => (
              <div key={category} className="border rounded-lg p-3">
                <h3 className="font-medium text-gray-700 mb-2">{category}</h3>
                <ul className="space-y-1 text-sm">
                  {levelKeys.map(key => {
                    if (!levels[key]) return null;
                    
                    // Calculate distance from current price
                    const distance = details.price?.price 
                      ? ((levels[key] - details.price.price) / details.price.price * 100).toFixed(2) + '%'
                      : 'N/A';
                    
                    // Determine if price is near this level (within 0.15%)
                    const isNearby = details.price?.price 
                      ? Math.abs(levels[key] - details.price.price) / details.price.price < 0.0015
                      : false;
                    
                    return (
                      <li key={key} className={`flex justify-between ${isNearby ? 'font-bold text-blue-700' : ''}`}>
                        <span>{key.replace(/_/g, ' ')}:</span>
                        <span>${levels[key].toFixed(5)} <span className="text-xs text-gray-500">({distance})</span></span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </div>
        
        {/* Signals */}
        <div className="bg-white shadow rounded-lg p-4">
          <h2 className="text-lg font-medium mb-4">Signal History</h2>
          
          {signals[selectedSymbol] && signals[selectedSymbol].length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Price</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Stop Loss</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Size</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Levels</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Trend</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {signals[selectedSymbol].map((signal, index) => (
                    <tr key={index}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {new Date(signal.time).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          signal.type === 'bull' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
                          {signal.type === 'bull' ? 'BUY' : 'SELL'}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        ${signal.price.toFixed(5)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        ${signal.stop_loss.toFixed(5)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {signal.position_size.toFixed(2)} lots
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {signal.levels.join(', ')}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`flex items-center text-xs ${
                          signal.regression_trend === 'UPTREND' ? 'text-green-600' : 'text-red-600'
                        }`}>
                          {signal.regression_trend === 'UPTREND' ? 
                            <><TrendingUp size={14} className="mr-1" /> Uptrend</> : 
                            <><TrendingDown size={14} className="mr-1" /> Downtrend</>
                          }
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              No signals recorded for this symbol
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="bg-gray-100 min-h-screen pb-6">
      {/* Header */}
      <header className="bg-blue-800 text-white shadow">
        <div className="max-w-7xl mx-auto py-4 px-4 sm:px-6 lg:px-8 flex justify-between items-center">
          <h1 className="text-2xl font-bold">MT5 Monitoring System</h1>
          <div className="flex items-center space-x-4">
            <div className={`flex items-center ${monitorStatus.active ? 'text-green-300' : 'text-red-300'}`}>
              <span className="mr-1">Status:</span>
              {monitorStatus.active ? 'Active' : 'Inactive'}
            </div>
          </div>
        </div>
      </header>
      
      {/* Main Content */}
      <main className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        {activeView === 'dashboard' ? renderDashboard() : renderSymbolDetail()}
      </main>
    </div>
  );
};

export default App;