import React, { useState, useEffect } from 'react';
import './App.css';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Components
const LoadingSpinner = () => (
  <div className="flex justify-center items-center p-8">
    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
  </div>
);

const StatCard = ({ title, value, subtitle, color = "blue" }) => (
  <div className={`bg-gradient-to-r from-${color}-500 to-${color}-600 rounded-lg p-6 text-white shadow-lg`}>
    <h3 className="text-lg font-semibold opacity-90">{title}</h3>
    <p className="text-3xl font-bold mt-2">{value}</p>
    {subtitle && <p className="text-sm opacity-80 mt-1">{subtitle}</p>}
  </div>
);

const CryptoCard = ({ opportunity }) => {
  const { crypto, opportunity_score, risk_level, recommended_action } = opportunity;
  
  const getRiskColor = (risk) => {
    switch(risk) {
      case 'LOW': return 'text-green-600 bg-green-100';
      case 'MEDIUM': return 'text-yellow-600 bg-yellow-100';
      case 'HIGH': return 'text-red-600 bg-red-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  const getScoreColor = (score) => {
    if (score >= 70) return 'text-green-600';
    if (score >= 50) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200 hover:shadow-lg transition-shadow">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-xl font-bold text-gray-800">{crypto.symbol}</h3>
          <p className="text-gray-600">{crypto.name}</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-gray-800">
            ${crypto.current_price.toFixed(4)}
          </p>
          <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${getRiskColor(risk_level)}`}>
            {risk_level} RISK
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <p className="text-sm text-gray-600">Drawdown</p>
          <p className="text-lg font-semibold text-red-600">
            -{crypto.drawdown_percentage.toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-600">Opportunity Score</p>
          <p className={`text-lg font-semibold ${getScoreColor(opportunity_score)}`}>
            {opportunity_score.toFixed(1)}/100
          </p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-4 text-center">
        <div>
          <p className="text-xs text-gray-500">24h</p>
          <p className={`text-sm font-semibold ${crypto.price_change_percentage_24h >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {crypto.price_change_percentage_24h >= 0 ? '+' : ''}{crypto.price_change_percentage_24h.toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">7d</p>
          <p className={`text-sm font-semibold ${crypto.price_change_percentage_7d >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {crypto.price_change_percentage_7d >= 0 ? '+' : ''}{crypto.price_change_percentage_7d.toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">30d</p>
          <p className={`text-sm font-semibold ${crypto.price_change_percentage_30d >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {crypto.price_change_percentage_30d >= 0 ? '+' : ''}{crypto.price_change_percentage_30d.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="border-t pt-3">
        <p className="text-sm font-semibold text-gray-700">Recommendation:</p>
        <p className="text-sm text-gray-600 mt-1">{recommended_action}</p>
      </div>

      <div className="flex justify-between items-center mt-3 text-xs text-gray-500">
        <span>Vol: ${(crypto.volume_24h / 1000000).toFixed(1)}M</span>
        <span>MCap: ${(crypto.market_cap / 1000000).toFixed(0)}M</span>
      </div>
    </div>
  );
};

const FilterPanel = ({ filters, setFilters, onApply }) => (
  <div className="bg-white rounded-lg shadow-md p-6 mb-6">
    <h3 className="text-lg font-semibold mb-4 text-gray-800">Filters & Settings</h3>
    <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Min Drawdown %</label>
        <input
          type="number"
          value={filters.min_drawdown}
          onChange={(e) => setFilters({...filters, min_drawdown: parseFloat(e.target.value)})}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Max Drawdown %</label>
        <input
          type="number"
          value={filters.max_drawdown}
          onChange={(e) => setFilters({...filters, max_drawdown: parseFloat(e.target.value)})}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Min Market Cap (M)</label>
        <input
          type="number"
          value={filters.min_market_cap / 1000000}
          onChange={(e) => setFilters({...filters, min_market_cap: parseFloat(e.target.value) * 1000000})}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Results</label>
        <select
          value={filters.top_n}
          onChange={(e) => setFilters({...filters, top_n: parseInt(e.target.value)})}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value={20}>Top 20</option>
          <option value={50}>Top 50</option>
          <option value={100}>Top 100</option>
        </select>
      </div>
      <div className="flex items-end">
        <button
          onClick={onApply}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 font-medium"
        >
          Apply Filters
        </button>
      </div>
    </div>
  </div>
);

function App() {
  const [opportunities, setOpportunities] = useState([]);
  const [marketStats, setMarketStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    min_drawdown: 10.0,
    max_drawdown: 80.0,
    min_market_cap: 1000000,
    min_volume: 100000,
    top_n: 50
  });

  const fetchMarketStats = async () => {
    try {
      const response = await axios.get(`${API}/market/stats`);
      setMarketStats(response.data);
    } catch (err) {
      console.error('Error fetching market stats:', err);
    }
  };

  const fetchOpportunities = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await axios.post(`${API}/opportunities`, filters);
      setOpportunities(response.data);
      
      await fetchMarketStats();
    } catch (err) {
      console.error('Error fetching opportunities:', err);
      setError('Failed to fetch crypto opportunities. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOpportunities();
  }, []);

  const handleApplyFilters = () => {
    fetchOpportunities();
  };

  const handleRefresh = () => {
    fetchOpportunities();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">DDRscan</h1>
              <p className="text-gray-600">Crypto Drawdown & Rebound Scanner</p>
            </div>
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 font-medium"
            >
              {loading ? 'Refreshing...' : 'Refresh Data'}
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Market Stats */}
        {marketStats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <StatCard
              title="Total Analyzed"
              value={marketStats.total_cryptos_analyzed}
              subtitle="Cryptocurrencies"
              color="blue"
            />
            <StatCard
              title="Opportunities"
              value={marketStats.total_opportunities}
              subtitle="Above threshold"
              color="green"
            />
            <StatCard
              title="High Score"
              value={marketStats.high_score_opportunities}
              subtitle="Score > 50"
              color="purple"
            />
            <StatCard
              title="Market Sentiment"
              value={marketStats.market_sentiment}
              subtitle={`Avg DD: ${marketStats.average_drawdown}%`}
              color={marketStats.market_sentiment === 'Bullish' ? 'green' : marketStats.market_sentiment === 'Bearish' ? 'red' : 'yellow'}
            />
          </div>
        )}

        {/* Filters */}
        <FilterPanel
          filters={filters}
          setFilters={setFilters}
          onApply={handleApplyFilters}
        />

        {/* Content */}
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-6">
            {error}
          </div>
        )}

        {loading ? (
          <LoadingSpinner />
        ) : (
          <div>
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-2xl font-bold text-gray-900">
                Rebound Opportunities ({opportunities.length})
              </h2>
              <p className="text-gray-600">
                Last updated: {new Date().toLocaleTimeString()}
              </p>
            </div>

            {opportunities.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-gray-500 text-lg">No opportunities found with current filters.</p>
                <p className="text-gray-400">Try adjusting your filter criteria.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {opportunities.map((opportunity, index) => (
                  <CryptoCard key={opportunity.crypto.id || index} opportunity={opportunity} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;