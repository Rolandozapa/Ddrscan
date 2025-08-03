import React, { useState, useEffect } from "react";
import "./App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const CryptoRankingApp = () => {
  const [rankings, setRankings] = useState([]);
  const [period, setPeriod] = useState("24h");
  const [periods, setPeriods] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchPeriods();
    fetchRankings();
  }, []);

  useEffect(() => {
    if (period) {
      fetchRankings();
    }
  }, [period]);

  const fetchPeriods = async () => {
    try {
      const response = await axios.get(`${API}/periods`);
      setPeriods(response.data.periods || []);
    } catch (error) {
      console.error("Erreur lors du chargement des périodes:", error);
    }
  };

  const fetchRankings = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API}/rankings/${period}?limit=50`);
      setRankings(response.data.rankings || []);
      setLastUpdated(new Date(response.data.last_updated));
    } catch (error) {
      console.error("Erreur lors du chargement des classements:", error);
      setRankings([]);
    } finally {
      setLoading(false);
    }
  };

  const refreshData = async () => {
    try {
      setRefreshing(true);
      await axios.post(`${API}/refresh-crypto-data`);
      // Wait a bit for data to process
      setTimeout(() => {
        fetchRankings();
        setRefreshing(false);
      }, 3000);
    } catch (error) {
      console.error("Erreur lors du rafraîchissement:", error);
      setRefreshing(false);
    }
  };

  const formatNumber = (num) => {
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
    return num?.toFixed(2) || '0';
  };

  const formatPrice = (price) => {
    if (price >= 1) return `$${price.toFixed(2)}`;
    return `$${price.toFixed(6)}`;
  };

  const formatPerformance = (performance) => {
    if (performance === null || performance === undefined) return 'N/A';
    const value = parseFloat(performance);
    const sign = value >= 0 ? '+' : '';
    const color = value >= 0 ? 'text-green-400' : 'text-red-400';
    return <span className={color}>{sign}{value.toFixed(2)}%</span>;
  };

  const getDataSourceIcon = (source) => {
    switch (source) {
      case 'direct_cmc':
        return '✅';
      case 'coingecko_historical':
        return '🌐';
      case 'yahoo_historical':
        return '📊';
      case 'calculated_from_cmc':
        return '🧮';
      default:
        return '❓';
    }
  };

  const formatRecoveryPotential = (potential) => {
    if (potential === null || potential === undefined) return 'N/A';
    const value = parseFloat(potential);
    if (value > 1000) return `+${(value/1000).toFixed(1)}K%`;
    if (value > 100) return `+${value.toFixed(0)}%`;
    if (value > 0) return `+${value.toFixed(1)}%`;
    return `${value.toFixed(1)}%`;
  };

  const getRecoveryPotentialColor = (potential) => {
    if (potential === null || potential === undefined) return 'text-gray-400';
    const value = parseFloat(potential);
    if (value > 500) return 'text-green-400 font-bold';
    if (value > 200) return 'text-green-300';
    if (value > 100) return 'text-yellow-400';
    if (value > 50) return 'text-orange-400';
    return 'text-red-400';
  };

  const getScoreColor = (score) => {
    if (score >= 80) return 'text-green-600 bg-green-100';
    if (score >= 60) return 'text-blue-600 bg-blue-100';
    if (score >= 40) return 'text-yellow-600 bg-yellow-100';
    return 'text-red-600 bg-red-100';
  };

  const getRankBadgeColor = (rank) => {
    if (rank === 1) return 'bg-gradient-to-r from-yellow-400 to-yellow-600 text-white';
    if (rank === 2) return 'bg-gradient-to-r from-gray-300 to-gray-500 text-white';
    if (rank === 3) return 'bg-gradient-to-r from-amber-600 to-amber-800 text-white';
    if (rank <= 10) return 'bg-gradient-to-r from-green-400 to-green-600 text-white';
    return 'bg-gradient-to-r from-blue-400 to-blue-600 text-white';
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-purple-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl md:text-6xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-600 mb-4">
            🚀 CryptoRebound Ranking
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto">
            Découvrez les meilleures opportunités de rebond crypto basées sur notre algorithme de scoring avancé
          </p>
        </div>

        {/* Controls */}
        <div className="flex flex-col md:flex-row justify-between items-center mb-8 space-y-4 md:space-y-0">
          <div className="flex items-center space-x-4">
            <label className="text-white font-semibold">Période:</label>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="bg-gray-800 text-white border border-gray-600 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              {periods.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center space-x-4">
            {lastUpdated && (
              <span className="text-gray-400 text-sm">
                Dernière mise à jour: {lastUpdated.toLocaleString('fr-FR')}
              </span>
            )}
            <button
              onClick={refreshData}
              disabled={refreshing}
              className="bg-gradient-to-r from-green-500 to-blue-600 hover:from-green-600 hover:to-blue-700 text-white font-bold py-2 px-6 rounded-lg transition duration-300 disabled:opacity-50"
            >
              {refreshing ? (
                <div className="flex items-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Actualisation...
                </div>
              ) : (
                '🔄 Actualiser'
              )}
            </button>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-500 mx-auto"></div>
            <p className="text-white mt-4">Chargement des données...</p>
          </div>
        )}

        {/* Rankings Table */}
        {!loading && rankings.length > 0 && (
          <div className="bg-gray-800 rounded-xl shadow-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-white">
                <thead className="bg-gradient-to-r from-gray-700 to-gray-800">
                  <tr>
                    <th className="px-6 py-4 text-left">Rang</th>
                    <th className="px-6 py-4 text-left">Crypto</th>
                    <th className="px-6 py-4 text-right">Prix</th>
                    <th className="px-6 py-4 text-right">Market Cap</th>
                    <th className="px-6 py-4 text-center">Score Total</th>
                    <th className="px-6 py-4 text-center">Performance ({period})</th>
                    <th className="px-6 py-4 text-center">Drawdown</th>
                    <th className="px-6 py-4 text-center">Potentiel Rebond</th>
                    <th className="px-6 py-4 text-center">Momentum</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {rankings.map((crypto, index) => (
                    <tr key={crypto.id} className="hover:bg-gray-700 transition duration-300">
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold ${getRankBadgeColor(crypto.rank)}`}>
                          {crypto.rank}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div>
                          <div className="font-bold text-white">{crypto.symbol}</div>
                          <div className="text-gray-400 text-sm truncate max-w-32">{crypto.name}</div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right font-mono">
                        {formatPrice(crypto.price)}
                      </td>
                      <td className="px-6 py-4 text-right">
                        ${formatNumber(crypto.market_cap)}
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getScoreColor(crypto.total_score)}`}>
                          {crypto.total_score.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className="flex flex-col items-center">
                          {formatPerformance(crypto.period_performance)}
                          <div className="text-xs text-gray-400 mt-1" title={`Source: ${crypto.data_source}`}>
                            {getDataSourceIcon(crypto.data_source)}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="text-sm font-mono">
                          {crypto.drawdown_score.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="text-sm font-mono">
                          {crypto.rebound_potential_score.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="text-sm font-mono">
                          {crypto.momentum_score.toFixed(1)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && rankings.length === 0 && (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">📊</div>
            <h3 className="text-2xl font-bold text-white mb-2">Aucune donnée disponible</h3>
            <p className="text-gray-400 mb-6">
              Cliquez sur "Actualiser" pour charger les données depuis CoinMarketCap
            </p>
            <button
              onClick={refreshData}
              className="bg-gradient-to-r from-green-500 to-blue-600 hover:from-green-600 hover:to-blue-700 text-white font-bold py-3 px-8 rounded-lg transition duration-300"
            >
              🔄 Charger les données
            </button>
          </div>
        )}

        {/* Enhanced Legend with Data Source Info */}
        <div className="mt-8 bg-gray-800 rounded-xl p-6">
          <h3 className="text-white text-xl font-bold mb-4">📋 Légende du Scoring Amélioré</h3>
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <div className="mb-4">
                <h4 className="font-semibold text-blue-400 mb-2">🎯 Score de Performance (25-30%)</h4>
                <p className="text-sm text-gray-300">Analyse avancée avec échelle logarithmique pour les performances positives</p>
              </div>
              <div className="mb-4">
                <h4 className="font-semibold text-red-400 mb-2">📉 Score Drawdown (15-25%)</h4>
                <p className="text-sm text-gray-300">Ajustement selon la période avec facteurs de volatilité</p>
              </div>
            </div>
            <div>
              <div className="mb-4">
                <h4 className="font-semibold text-green-400 mb-2">🚀 Potentiel de Rebond (30-40%)</h4>
                <p className="text-sm text-gray-300">Considère les cycles de marché et la capitalisation</p>
              </div>
              <div className="mb-4">
                <h4 className="font-semibold text-yellow-400 mb-2">⚡ Score Momentum (15-25%)</h4>
                <p className="text-sm text-gray-300">Analyse multi-période avec détection de tendance</p>
              </div>
            </div>
          </div>
          
          <div className="mt-6 pt-4 border-t border-gray-700">
            <h4 className="text-purple-400 font-semibold mb-2">📊 Sources de Données Améliorées</h4>
            <div className="grid md:grid-cols-4 gap-4 text-sm">
              <div className="bg-gray-700 p-3 rounded">
                <span className="text-green-400 font-semibold">✅ CoinMarketCap</span>
                <p className="text-gray-300 mt-1">1h, 24h, 7j, 30j, 60j, 90j - Données directes</p>
              </div>
              <div className="bg-gray-700 p-3 rounded">
                <span className="text-blue-400 font-semibold">🌐 CoinGecko</span>
                <p className="text-gray-300 mt-1">6 mois, 9 mois, 1 an - Données historiques réelles</p>
              </div>
              <div className="bg-gray-700 p-3 rounded">
                <span className="text-yellow-400 font-semibold">📊 Yahoo Finance</span>
                <p className="text-gray-300 mt-1">Fallback pour données crypto historiques</p>
              </div>
              <div className="bg-gray-700 p-3 rounded">
                <span className="text-orange-400 font-semibold">🧮 Calculé</span>
                <p className="text-gray-300 mt-1">Estimation basée sur données CMC disponibles</p>
              </div>
            </div>
            <div className="mt-4 p-3 bg-gradient-to-r from-green-900/30 to-blue-900/30 rounded-lg border border-green-500/30">
              <h5 className="text-green-300 font-semibold mb-2">🎯 Système Multi-Sources Intelligent</h5>
              <p className="text-xs text-gray-300">
                <strong>Priorité :</strong> CoinMarketCap → CoinGecko → Yahoo Finance → Calculs sophistiqués
              </p>
            </div>
          </div>
          
          <div className="mt-4 p-4 bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg border border-blue-500/30">
            <h5 className="text-blue-300 font-semibold mb-2">🎯 Pondérations Dynamiques</h5>
            <div className="grid md:grid-cols-3 gap-2 text-xs text-gray-300">
              <div><strong>Court terme (24h-7j):</strong> Focus rebond + momentum</div>
              <div><strong>Moyen terme (1-3 mois):</strong> Approche équilibrée</div>
              <div><strong>Long terme (6m-1an):</strong> Performance + résistance</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CryptoRankingApp;