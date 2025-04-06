// SymbolSelector.jsx
import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Plus } from 'lucide-react';

const SymbolSelector = ({ 
  value, 
  onChange, 
  disabled = false,
  className = ""
}) => {
  // Common symbols by category
  const symbolCategories = {
    "Major Forex": ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD"],
    "Crypto": ["BTCUSD"],
    "Indices": ["NAS100"]
  };

  // Flatten all symbols for easy access
  const allCommonSymbols = Object.values(symbolCategories).flat();
  
  // State to track selected symbols via checkboxes
  const [selectedSymbols, setSelectedSymbols] = useState({});
  
  // State for custom symbol input
  const [customSymbol, setCustomSymbol] = useState("");
  
  // State to track expanded categories
  const [expandedCategories, setExpandedCategories] = useState(
    Object.keys(symbolCategories).reduce((acc, category) => {
      acc[category] = true; // Default all categories to expanded
      return acc;
    }, {})
  );

  // Initialize selected symbols based on the initial value
  useEffect(() => {
    const initialSelected = {};
    const symbolsArray = value.split(',').map(s => s.trim()).filter(Boolean);
    
    allCommonSymbols.forEach(symbol => {
      initialSelected[symbol] = symbolsArray.includes(symbol);
    });
    
    setSelectedSymbols(initialSelected);
  }, []);

  // Toggle a category's expanded state
  const toggleCategory = (category) => {
    setExpandedCategories({
      ...expandedCategories,
      [category]: !expandedCategories[category]
    });
  };

  // Handle checkbox changes
  const handleSymbolToggle = (symbol) => {
    if (disabled) return;
    
    const newSelectedSymbols = {
      ...selectedSymbols,
      [symbol]: !selectedSymbols[symbol]
    };
    
    setSelectedSymbols(newSelectedSymbols);
    updateSymbolInput(newSelectedSymbols);
  };
  
  // Update the symbol input based on selected checkboxes and custom symbols
  const updateSymbolInput = (newSelectedSymbols = selectedSymbols) => {
    // Get selected symbols from checkboxes
    const checkedSymbols = Object.keys(newSelectedSymbols)
      .filter(key => newSelectedSymbols[key]);
    
    // Get custom symbols that aren't in the predefined list
    const currentCustomSymbols = value
      .split(',')
      .map(s => s.trim())
      .filter(s => s && !allCommonSymbols.includes(s));
    
    // Combine checked symbols and custom symbols
    const allSymbols = [...checkedSymbols, ...currentCustomSymbols];
    onChange(allSymbols.join(','));
  };

  // Handle adding a custom symbol
  const handleAddCustomSymbol = () => {
    if (!customSymbol || disabled) return;
    
    // Add to input if not already there
    const symbols = value.split(',').map(s => s.trim()).filter(Boolean);
    if (!symbols.includes(customSymbol)) {
      const newSymbols = [...symbols, customSymbol];
      onChange(newSymbols.join(','));
    }
    
    // Update checkbox state if it's a common symbol
    if (allCommonSymbols.includes(customSymbol)) {
      setSelectedSymbols({
        ...selectedSymbols,
        [customSymbol]: true
      });
    }
    
    setCustomSymbol("");
  };

  // Handle direct text input changes
  const handleDirectInputChange = (e) => {
    const newInput = e.target.value;
    onChange(newInput);
    
    // Update checkboxes based on text input
    const symbolsArray = newInput.split(',').map(s => s.trim()).filter(Boolean);
    const newSelectedSymbols = { ...selectedSymbols };
    
    allCommonSymbols.forEach(symbol => {
      newSelectedSymbols[symbol] = symbolsArray.includes(symbol);
    });
    
    setSelectedSymbols(newSelectedSymbols);
  };

  // Calculate how many symbols are selected in each category
  const getSelectedCountByCategory = (category) => {
    return (symbolCategories[category] || []).filter(symbol => selectedSymbols[symbol] || false).length;
  };

  return (
    <div className={className}>
      {/* Larger text input */}
      <textarea 
        className="w-full p-2 border rounded focus:ring focus:ring-blue-300 mb-3"
        value={value}
        onChange={handleDirectInputChange}
        disabled={disabled}
        rows={3}
        placeholder="Enter symbols separated by commas (e.g., EURUSD,GBPUSD)"
      />
      
      {/* Categories of symbols */}
      <div className="space-y-4">
        {Object.entries(symbolCategories).map(([category, symbols]) => (
          <div key={category} className="border rounded-lg overflow-hidden">
            <div 
              className="flex justify-between items-center bg-gray-50 p-3 cursor-pointer border-b"
              onClick={() => toggleCategory(category)}
            >
              <div className="font-medium">{category}</div>
              <div className="flex items-center space-x-2">
                <span className="text-sm text-gray-500">
                  {getSelectedCountByCategory(category)} of {symbols.length} selected
                </span>
                <span className="text-gray-400">
                  {expandedCategories[category] ? '▼' : '►'}
                </span>
              </div>
            </div>
            
            {expandedCategories[category] && (
              <div className="p-3">
                <div className="flex flex-wrap gap-2">
                  {symbols.map(symbol => (
                    <div 
                      key={symbol} 
                      onClick={() => handleSymbolToggle(symbol)}
                      className={`
                        px-3 py-2 rounded-md text-sm cursor-pointer select-none
                        transition-colors duration-200 flex items-center space-x-1
                        ${disabled ? 'opacity-60 cursor-not-allowed' : ''}
                        ${selectedSymbols[symbol] 
                          ? 'bg-blue-100 text-blue-800 border border-blue-300' 
                          : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'}
                      `}
                    >
                      <span className="w-4 h-4 flex items-center justify-center">
                        {selectedSymbols[symbol] && (
                          <CheckCircle size={16} className="text-blue-600" />
                        )}
                      </span>
                      <span>{symbol}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      
      {/* Custom symbol input */}
      <div className="mt-4">
        <div className="flex space-x-2">
          <input
            type="text"
            value={customSymbol}
            onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())}
            disabled={disabled}
            placeholder="Add custom symbol..."
            className="flex-1 p-2 border rounded focus:ring focus:ring-blue-300"
            onKeyPress={(e) => e.key === 'Enter' && handleAddCustomSymbol()}
          />
          <button
            onClick={handleAddCustomSymbol}
            disabled={disabled || !customSymbol}
            className={`
              px-3 py-2 rounded flex items-center
              ${disabled || !customSymbol 
                ? 'bg-gray-200 text-gray-500 cursor-not-allowed' 
                : 'bg-blue-600 text-white hover:bg-blue-700'}
            `}
          >
            <Plus size={16} className="mr-1" />
            Add
          </button>
        </div>
        <div className="mt-1 text-xs text-gray-500">
          Enter symbol and press Enter or click Add to include a custom symbol
        </div>
      </div>
    </div>
  );
};

export default SymbolSelector;