from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta
import aiohttp
import asyncio
from enum import Enum
import json
import math

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# CoinMarketCap API Configuration
CMC_API_KEY = "70046baa-e887-42ee-a909-03c6b6afab67"
CMC_BASE_URL = "https://pro-api.coinmarketcap.com"

class TimePeriod(str, Enum):
    ONE_HOUR = "1h"
    TWENTY_FOUR_HOURS = "24h"
    ONE_WEEK = "7d"
    ONE_MONTH = "30d"
    TWO_MONTHS = "60d"  # Available from CMC
    THREE_MONTHS = "90d"

class CryptoData(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    name: str
    market_cap: float
    price: float
    volume_24h: float
    percent_change_1h: Optional[float] = None
    percent_change_24h: float
    percent_change_7d: float
    percent_change_30d: float
    percent_change_60d: Optional[float] = None
    percent_change_90d: Optional[float] = None
    percent_change_180d: Optional[float] = None
    percent_change_365d: Optional[float] = None
    max_supply: Optional[float] = None
    circulating_supply: float
    total_supply: Optional[float] = None
    cmc_rank: int
    last_updated: datetime = Field(default_factory=datetime.utcnow)

class CryptoScore(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    crypto_id: str
    symbol: str
    name: str
    market_cap: float
    price: float
    period: TimePeriod
    period_performance: Optional[float] = None  # Actual % change for the period
    data_source: str = "calculated"  # "direct", "coingecko", "calculated"
    performance_score: float
    drawdown_score: float
    rebound_potential_score: float
    momentum_score: float
    total_score: float
    rank: Optional[int] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)

class CryptoRanking(BaseModel):
    rankings: List[CryptoScore]
    period: TimePeriod
    total_cryptos: int
    last_updated: datetime
    
class CryptoAPIService:
    def __init__(self):
        self.cmc_headers = {
            'X-CMC_PRO_API_KEY': CMC_API_KEY,
            'Accept': 'application/json',
        }
        self.coingecko_base_url = "https://api.coingecko.com/api/v3"
        self.session_timeout = aiohttp.ClientTimeout(total=30)
    
    async def fetch_top_cryptos(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch top crypto data from CoinMarketCap API"""
        try:
            url = f"{CMC_BASE_URL}/v1/cryptocurrency/listings/latest"
            params = {
                'start': '1',
                'limit': str(limit),
                'convert': 'USD',
                'sort': 'market_cap'
            }
            
            async with aiohttp.ClientSession(timeout=self.session_timeout) as session:
                async with session.get(url, headers=self.cmc_headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        cryptos = data.get('data', [])
                        
                        # Enhance with CoinGecko data for better historical accuracy
                        enhanced_cryptos = await self.enhance_with_coingecko_data(session, cryptos)
                        return enhanced_cryptos
                    else:
                        logger.error(f"CoinMarketCap API error: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching crypto data: {e}")
            return []

    async def enhance_with_coingecko_data(self, session: aiohttp.ClientSession, cryptos: List[Dict]) -> List[Dict]:
        """Enhance CMC data with CoinGecko historical data for missing periods"""
        enhanced_cryptos = []
        
        # Get top cryptos first, then enhance selectively to avoid rate limits
        priority_cryptos = cryptos[:100]  # Focus on top 100 for CoinGecko enhancement
        
        for i, crypto in enumerate(cryptos):
            enhanced_crypto = crypto.copy()
            
            # Only enhance priority cryptos with CoinGecko data
            if i < len(priority_cryptos):
                try:
                    coingecko_data = await self.fetch_coingecko_historical(session, crypto.get('symbol', '').lower())
                    if coingecko_data:
                        # Add missing historical data
                        quote = enhanced_crypto.get('quote', {}).get('USD', {})
                        
                        # Fill in missing longer-term data from CoinGecko with real historical data
                        if coingecko_data.get('data_quality') == 'real_historical_data':
                            if not quote.get('percent_change_180d') and coingecko_data.get('percent_change_180d'):
                                quote['percent_change_180d'] = coingecko_data.get('percent_change_180d')
                                logger.info(f"✅ Added REAL 180d data for {crypto.get('symbol')}: {coingecko_data.get('percent_change_180d'):.2f}%")
                            
                            if not quote.get('percent_change_270d') and coingecko_data.get('percent_change_270d'):
                                quote['percent_change_270d'] = coingecko_data.get('percent_change_270d')
                                logger.info(f"✅ Added REAL 270d data for {crypto.get('symbol')}: {coingecko_data.get('percent_change_270d'):.2f}%")
                            
                            if not quote.get('percent_change_365d') and coingecko_data.get('percent_change_365d'):
                                quote['percent_change_365d'] = coingecko_data.get('percent_change_365d')
                                logger.info(f"✅ Added REAL 365d data for {crypto.get('symbol')}: {coingecko_data.get('percent_change_365d'):.2f}%")
                                
                                # Also store the historical price for reference
                                current_price = quote.get('price', 0)
                                if current_price > 0:
                                    historical_price_365d = calculate_historical_price_from_performance(
                                        current_price, coingecko_data.get('percent_change_365d')
                                    )
                                    if historical_price_365d:
                                        enhanced_crypto['historical_price_365d'] = historical_price_365d
                        
                        # Mark the enhanced crypto with data source info
                        enhanced_crypto['data_sources'] = enhanced_crypto.get('data_sources', ['coinmarketcap'])
                        if 'coingecko_historical' not in enhanced_crypto['data_sources']:
                            enhanced_crypto['data_sources'].append('coingecko_historical')
                        
                except Exception as e:
                    logger.warning(f"Failed to enhance {crypto.get('symbol')} with CoinGecko: {e}")
                    
                # Add small delay to respect rate limits
                if i % 10 == 0 and i > 0:
                    await asyncio.sleep(1)
            
            enhanced_cryptos.append(enhanced_crypto)
        
        return enhanced_cryptos

    async def fetch_coingecko_historical(self, session: aiohttp.ClientSession, symbol: str) -> Optional[Dict]:
        """Fetch historical data from CoinGecko for missing periods"""
        try:
            # First, get the coin ID from CoinGecko
            search_url = f"{self.coingecko_base_url}/search"
            params = {'query': symbol}
            
            async with session.get(search_url, params=params) as search_response:
                if search_response.status != 200:
                    return None
                
                search_data = await search_response.json()
                coins = search_data.get('coins', [])
                
                # Find exact symbol match
                coin_id = None
                for coin in coins:
                    if coin.get('symbol', '').lower() == symbol.lower():
                        coin_id = coin.get('id')
                        break
                
                if not coin_id:
                    return None
                
                # Get historical price data with market_chart endpoint for accurate 1-year data
                history_url = f"{self.coingecko_base_url}/coins/{coin_id}/market_chart"
                history_params = {
                    'vs_currency': 'usd',
                    'days': '365',
                    'interval': 'daily'
                }
                
                async with session.get(history_url, params=history_params) as history_response:
                    if history_response.status != 200:
                        logger.warning(f"CoinGecko market_chart failed for {symbol}: {history_response.status}")
                        return None
                    
                    history_data = await history_response.json()
                    prices = history_data.get('prices', [])
                    
                    if len(prices) < 2:
                        return None
                    
                    # Calculate actual percentage changes from price data
                    current_price = prices[-1][1]  # Latest price
                    price_365d = prices[0][1] if len(prices) >= 365 else prices[0][1]  # 365 days ago
                    price_180d = prices[len(prices)//2][1] if len(prices) >= 180 else None  # ~6 months ago
                    price_270d = prices[len(prices)//4][1] if len(prices) >= 270 else None  # ~9 months ago
                    
                    # Calculate percentage changes
                    percent_change_365d = ((current_price - price_365d) / price_365d) * 100 if price_365d > 0 else None
                    percent_change_180d = ((current_price - price_180d) / price_180d) * 100 if price_180d and price_180d > 0 else None
                    percent_change_270d = ((current_price - price_270d) / price_270d) * 100 if price_270d and price_270d > 0 else None
                    
                    return {
                        'percent_change_180d': percent_change_180d,
                        'percent_change_270d': percent_change_270d, 
                        'percent_change_365d': percent_change_365d,
                        'source': 'coingecko_historical',
                        'data_quality': 'real_historical_data'
                    }
                    
        except Exception as e:
            logger.warning(f"CoinGecko historical data error for {symbol}: {e}")
            return None
        
        return None

    async def fetch_historical_data(self, symbol: str, time_period: TimePeriod) -> Dict[str, Any]:
        """Fetch historical data for calculating drawdown and momentum"""
        # For now, we'll use the percentage changes from CMC/CoinGecko
        # In a full implementation, we'd fetch OHLC data
        return {}

crypto_service = CryptoAPIService()

class CryptoScoringService:
    @staticmethod
    def calculate_performance_score(percent_change: float) -> float:
        """Calculate performance score based on percentage change with improved scaling"""
        if percent_change is None:
            return 0.0
        
        # Improved scoring with better distribution
        # Use sigmoid-like function for more realistic scoring
        capped_change = max(-95, min(2000, percent_change))
        
        if capped_change >= 0:
            # Positive performance: logarithmic scaling to prevent extreme scores
            score = 50 + (math.log(1 + capped_change/10) * 15)
        else:
            # Negative performance: linear penalty
            score = 50 + (capped_change * 0.4)
        
        return max(0, min(100, score))
    
    @staticmethod
    def calculate_drawdown_score(percent_change: float, volatility_proxy: float, period: TimePeriod) -> float:
        """Calculate drawdown score with period-specific adjustments"""
        if percent_change is None:
            return 50.0
        
        # Period-specific risk adjustments
        period_multiplier = {
            TimePeriod.TWENTY_FOUR_HOURS: 1.0,
            TimePeriod.ONE_WEEK: 0.9,
            TimePeriod.ONE_MONTH: 0.8,
            TimePeriod.THREE_MONTHS: 0.7,
            TimePeriod.SIX_MONTHS: 0.65,
            TimePeriod.NINE_MONTHS: 0.6,
            TimePeriod.ONE_YEAR: 0.55
        }.get(period, 0.8)
        
        # Estimate maximum drawdown based on volatility and performance
        volatility_factor = min(3.0, volatility_proxy * 2)
        estimated_max_drawdown = abs(percent_change) * volatility_factor * period_multiplier
        
        # Convert to score (lower drawdown = higher score)
        if estimated_max_drawdown <= 10:
            score = 95 - (estimated_max_drawdown * 2)
        elif estimated_max_drawdown <= 30:
            score = 75 - ((estimated_max_drawdown - 10) * 1.5)
        elif estimated_max_drawdown <= 60:
            score = 45 - ((estimated_max_drawdown - 30) * 1.0)
        else:
            score = max(0, 15 - ((estimated_max_drawdown - 60) * 0.3))
        
        return max(0, min(100, score))
    
    @staticmethod
    def calculate_rebound_potential_score(current_change: float, market_cap: float, period: TimePeriod) -> float:
        """Enhanced rebound potential calculation considering market cycles"""
        if current_change is None:
            return 50.0
        
        # Market cap factor (smaller = higher rebound potential when down)
        if market_cap > 50_000_000_000:  # >50B (BTC, ETH tier)
            market_cap_factor = 0.7
            base_rebound = 40
        elif market_cap > 10_000_000_000:  # 10-50B
            market_cap_factor = 0.8
            base_rebound = 45
        elif market_cap > 1_000_000_000:   # 1-10B
            market_cap_factor = 1.0
            base_rebound = 50
        elif market_cap > 100_000_000:     # 100M-1B
            market_cap_factor = 1.3
            base_rebound = 55
        else:  # <100M
            market_cap_factor = 1.6
            base_rebound = 60
        
        # Period-specific rebound assessment
        period_factor = {
            TimePeriod.TWENTY_FOUR_HOURS: 0.8,  # Short-term noise
            TimePeriod.ONE_WEEK: 0.9,
            TimePeriod.ONE_MONTH: 1.0,
            TimePeriod.THREE_MONTHS: 1.2,       # Good indicator of trend reversal
            TimePeriod.SIX_MONTHS: 1.1,
            TimePeriod.NINE_MONTHS: 1.0,
            TimePeriod.ONE_YEAR: 0.9            # Long-term trends harder to reverse
        }.get(period, 1.0)
        
        # Calculate rebound score based on current position
        if current_change <= -50:  # Severe decline
            rebound_score = base_rebound + (40 * market_cap_factor * period_factor)
        elif current_change <= -30:  # Significant decline
            rebound_score = base_rebound + (30 * market_cap_factor * period_factor)
        elif current_change <= -15:  # Moderate decline
            rebound_score = base_rebound + (20 * market_cap_factor * period_factor)
        elif current_change <= -5:   # Minor decline
            rebound_score = base_rebound + (10 * market_cap_factor * period_factor)
        elif current_change <= 10:   # Slight positive
            rebound_score = base_rebound + (5 * market_cap_factor)
        else:  # Strong positive performance
            rebound_score = base_rebound - (current_change * 0.3)  # Less rebound potential when already up
        
        return max(0, min(100, rebound_score))
    
    @staticmethod
    def calculate_momentum_score(short_change: float, long_change: float, period: TimePeriod) -> float:
        """Enhanced momentum calculation with trend analysis"""
        if short_change is None or long_change is None:
            return 50.0
        
        # Calculate momentum differential
        momentum_diff = short_change - long_change
        
        # Period-specific momentum interpretation
        if period in [TimePeriod.TWENTY_FOUR_HOURS, TimePeriod.ONE_WEEK]:
            # For short periods, compare with 30d trend
            reference_period = "medium_term"
        else:
            # For longer periods, compare recent vs period performance
            reference_period = "long_term"
        
        # Momentum scoring
        if momentum_diff > 20:      # Strong positive momentum
            base_score = 85
        elif momentum_diff > 10:    # Good momentum
            base_score = 70
        elif momentum_diff > 0:     # Slight positive momentum
            base_score = 60
        elif momentum_diff > -10:   # Slight negative momentum
            base_score = 40
        elif momentum_diff > -20:   # Negative momentum
            base_score = 25
        else:                       # Strong negative momentum
            base_score = 10
        
        # Add trend consistency bonus/penalty
        if (short_change > 0 and long_change > 0) or (short_change < 0 and long_change < 0):
            # Consistent trend direction
            consistency_bonus = 5
        else:
            # Trend reversal (could be opportunity)
            consistency_bonus = -5 if period in [TimePeriod.TWENTY_FOUR_HOURS] else 10
        
        return max(0, min(100, base_score + consistency_bonus))

scoring_service = CryptoScoringService()

@api_router.get("/")
async def root():
    return {"message": "Crypto Rebound Ranking API"}

@api_router.post("/refresh-crypto-data")
async def refresh_crypto_data(background_tasks: BackgroundTasks):
    """Refresh crypto data from CoinMarketCap API"""
    background_tasks.add_task(update_crypto_data)
    return {"message": "Crypto data refresh initiated"}

async def update_crypto_data():
    """Background task to update crypto data"""
    try:
        logger.info("Starting crypto data refresh...")
        crypto_data = await crypto_service.fetch_top_cryptos()
        
        # Clear existing data
        await db.crypto_data.delete_many({})
        
        # Process and store new data
        for crypto in crypto_data:
            quote = crypto.get('quote', {}).get('USD', {})
            crypto_obj = CryptoData(
                symbol=crypto.get('symbol', ''),
                name=crypto.get('name', ''),
                market_cap=quote.get('market_cap', 0),
                price=quote.get('price', 0),
                volume_24h=quote.get('volume_24h', 0),
                percent_change_1h=quote.get('percent_change_1h'),
                percent_change_24h=quote.get('percent_change_24h'),
                percent_change_7d=quote.get('percent_change_7d'),
                percent_change_30d=quote.get('percent_change_30d'),
                percent_change_60d=quote.get('percent_change_60d'),
                percent_change_90d=quote.get('percent_change_90d'),
                max_supply=crypto.get('max_supply'),
                circulating_supply=crypto.get('circulating_supply', 0),
                total_supply=crypto.get('total_supply'),
                cmc_rank=crypto.get('cmc_rank', 0),
            )
            await db.crypto_data.insert_one(crypto_obj.dict())
        
        logger.info(f"Updated {len(crypto_data)} cryptocurrencies")
        
        # Calculate scores for all periods
        await calculate_all_scores()
        
    except Exception as e:
        logger.error(f"Error updating crypto data: {e}")

async def calculate_all_scores():
    """Calculate scores for all time periods"""
    cryptos = await db.crypto_data.find().to_list(None)
    
    for period in TimePeriod:
        scores = []
        for crypto in cryptos:
            score = calculate_crypto_score(crypto, period)
            if score:
                scores.append(score)
        
        # Sort by total score descending
        scores.sort(key=lambda x: x.total_score, reverse=True)
        
        # Add rankings
        for i, score in enumerate(scores):
            score.rank = i + 1
        
        # Clear existing scores for this period
        await db.crypto_scores.delete_many({"period": period.value})
        
        # Insert new scores
        if scores:
            await db.crypto_scores.insert_many([score.dict() for score in scores])

def calculate_crypto_score(crypto_data: dict, period: TimePeriod) -> Optional[CryptoScore]:
    """Calculate comprehensive score for a crypto with enhanced algorithms"""
    try:
        # Get the appropriate percentage change based on period with source info
        result = get_percent_change_for_period(crypto_data, period)
        if isinstance(result, tuple):
            percent_change, data_source = result
        else:
            percent_change = result
            data_source = "unknown"
            
        if percent_change is None:
            logger.warning(f"No data available for {crypto_data.get('symbol', 'unknown')} - {period.value}")
            return None
            
        # Calculate individual scores with enhanced algorithms
        performance_score = scoring_service.calculate_performance_score(percent_change)
        
        # Use volume as volatility proxy with market cap normalization
        volume_24h = crypto_data.get('volume_24h', 0)
        market_cap = crypto_data.get('market_cap', 1)
        volatility_proxy = min(3.0, volume_24h / max(market_cap, 1_000_000))
        
        drawdown_score = scoring_service.calculate_drawdown_score(
            percent_change, volatility_proxy, period
        )
        
        rebound_potential_score = scoring_service.calculate_rebound_potential_score(
            percent_change, market_cap, period
        )
        
        # Enhanced momentum calculation using multiple timeframes
        short_change = crypto_data.get('percent_change_24h')
        long_change = percent_change
        
        # For better momentum analysis, use different reference periods
        if period == TimePeriod.TWENTY_FOUR_HOURS:
            reference_change = crypto_data.get('percent_change_7d')
        elif period == TimePeriod.ONE_WEEK:
            reference_change = crypto_data.get('percent_change_30d')
        else:
            reference_change = crypto_data.get('percent_change_7d')
        
        if reference_change is not None:
            momentum_score = scoring_service.calculate_momentum_score(short_change, reference_change, period)
        else:
            momentum_score = scoring_service.calculate_momentum_score(short_change, long_change, period)
        
        # Enhanced weighted total score with period-specific adjustments
        period_weights = get_period_specific_weights(period)
        total_score = (
            performance_score * period_weights['performance'] +
            drawdown_score * period_weights['drawdown'] +
            rebound_potential_score * period_weights['rebound'] +
            momentum_score * period_weights['momentum']
        )
        
        logger.debug(f"{crypto_data['symbol']} - {period.value}: P:{performance_score:.1f}, D:{drawdown_score:.1f}, R:{rebound_potential_score:.1f}, M:{momentum_score:.1f}, Total:{total_score:.1f}")
        
        return CryptoScore(
            crypto_id=crypto_data['id'],
            symbol=crypto_data['symbol'],
            name=crypto_data['name'],
            market_cap=market_cap,
            price=crypto_data['price'],
            period=period,
            period_performance=percent_change,
            data_source=data_source,  # Include the data source info
            performance_score=performance_score,
            drawdown_score=drawdown_score,
            rebound_potential_score=rebound_potential_score,
            momentum_score=momentum_score,
            total_score=total_score
        )
    except Exception as e:
        logger.error(f"Error calculating score for {crypto_data.get('symbol', 'unknown')}: {e}")
        return None

def get_period_specific_weights(period: TimePeriod) -> Dict[str, float]:
    """Get period-specific weights for scoring components"""
    if period in [TimePeriod.ONE_HOUR, TimePeriod.TWENTY_FOUR_HOURS, TimePeriod.ONE_WEEK]:
        # Short-term: Focus more on momentum and rebound potential
        return {
            'performance': 0.20,
            'drawdown': 0.15,
            'rebound': 0.40,
            'momentum': 0.25
        }
    elif period in [TimePeriod.ONE_MONTH, TimePeriod.TWO_MONTHS, TimePeriod.THREE_MONTHS]:
        # Medium-term: Balanced approach
        return {
            'performance': 0.25,
            'drawdown': 0.20,
            'rebound': 0.35,
            'momentum': 0.20
        }
    else:
        # Long-term: Focus more on performance and drawdown resistance
        return {
            'performance': 0.30,
            'drawdown': 0.25,
            'rebound': 0.30,
            'momentum': 0.15
        }

def calculate_historical_performance_from_price(current_price: float, historical_price: float) -> float:
    """Calculate percentage change from historical price to current price"""
    if historical_price <= 0:
        return None
    return ((current_price - historical_price) / historical_price) * 100

def calculate_historical_price_from_performance(current_price: float, performance_percent: float) -> float:
    """Calculate historical price from current price and performance percentage"""
    if current_price <= 0:
        return None
    return current_price / (1 + performance_percent / 100)

def get_percent_change_for_period(crypto_data: dict, period: TimePeriod):
    """Get percentage change for specified period using available data and calculations"""
    # Direct mapping for available fields from CoinMarketCap
    period_map = {
        TimePeriod.ONE_HOUR: 'percent_change_1h',
        TimePeriod.TWENTY_FOUR_HOURS: 'percent_change_24h',
        TimePeriod.ONE_WEEK: 'percent_change_7d',
        TimePeriod.ONE_MONTH: 'percent_change_30d',
        TimePeriod.TWO_MONTHS: 'percent_change_60d',
        TimePeriod.THREE_MONTHS: 'percent_change_90d',
        TimePeriod.SIX_MONTHS: 'percent_change_180d',  # Rarely available from CMC
        TimePeriod.NINE_MONTHS: 'percent_change_270d', # Not available from CMC
        TimePeriod.ONE_YEAR: 'percent_change_365d'     # Not available from CMC
    }
    
    field = period_map.get(period)
    
    # Check for direct data first
    if field and crypto_data.get(field) is not None:
        # We have direct data from CoinMarketCap
        if period in [TimePeriod.ONE_HOUR, TimePeriod.TWENTY_FOUR_HOURS, TimePeriod.ONE_WEEK, TimePeriod.ONE_MONTH, TimePeriod.TWO_MONTHS, TimePeriod.THREE_MONTHS]:
            return crypto_data.get(field), "direct_cmc"
        else:
            # Check if this came from CoinGecko enhancement
            data_sources = crypto_data.get('data_sources', [])
            if 'coingecko_historical' in str(data_sources):
                return crypto_data.get(field), "coingecko_historical"
            else:
                return crypto_data.get(field), "direct_cmc"
    
    # For missing long-term data, try to calculate from available shorter periods
    current_price = crypto_data.get('price', 0)
    if current_price <= 0:
        return None, "unavailable"
    
    # Try to calculate based on available data
    if period == TimePeriod.SIX_MONTHS:
        # Try to estimate from 90d data
        change_90d = crypto_data.get('percent_change_90d')
        if change_90d is not None:
            # Simple estimation: 6 months ≈ 2 × 90 days with dampening
            estimated_180d = change_90d * 1.8  # Conservative estimate
            return max(-95, min(500, estimated_180d)), "calculated_from_90d"
        
        # Fallback: estimate from 30d data
        change_30d = crypto_data.get('percent_change_30d')
        if change_30d is not None:
            estimated_180d = change_30d * 5.0  # 6 months ≈ 6 × 30 days, conservative
            return max(-95, min(500, estimated_180d)), "calculated_from_30d"
    
    elif period == TimePeriod.NINE_MONTHS:
        # Try to estimate from 90d data
        change_90d = crypto_data.get('percent_change_90d')
        if change_90d is not None:
            # 9 months ≈ 3 × 90 days with market cycle considerations
            estimated_270d = change_90d * 2.5
            return max(-95, min(800, estimated_270d)), "calculated_from_90d"
        
        # Fallback: estimate from 30d data
        change_30d = crypto_data.get('percent_change_30d')
        if change_30d is not None:
            estimated_270d = change_30d * 7.0  # Conservative estimate
            return max(-95, min(800, estimated_270d)), "calculated_from_30d"
    
    elif period == TimePeriod.ONE_YEAR:
        # Priority 1: Try to calculate from 90d data (most reliable)
        change_90d = crypto_data.get('percent_change_90d')
        if change_90d is not None:
            # 1 year ≈ 4 × 90 days, but crypto markets have cycles
            if change_90d > 0:
                # Positive trends tend to moderate over time
                estimated_365d = change_90d * 3.0
            else:
                # Negative trends also moderate but recovery is slower
                estimated_365d = change_90d * 2.5
            
            return max(-95, min(1000, estimated_365d)), "calculated_from_90d"
        
        # Priority 2: Calculate from 30d data
        change_30d = crypto_data.get('percent_change_30d')
        if change_30d is not None:
            # 1 year ≈ 12 × 30 days, but apply market reality factor
            market_cap = crypto_data.get('market_cap', 0)
            
            # Adjust multiplier based on market cap (larger = more stable)
            if market_cap > 10_000_000_000:  # >10B
                multiplier = 7.0  # More conservative for large caps
            elif market_cap > 1_000_000_000:  # 1-10B
                multiplier = 8.0
            else:  # <1B
                multiplier = 9.0  # Higher volatility potential
            
            estimated_365d = change_30d * multiplier
            return max(-95, min(1000, estimated_365d)), "calculated_from_30d"
        
        # Priority 3: Very conservative estimate from 7d data
        change_7d = crypto_data.get('percent_change_7d')
        if change_7d is not None:
            # Extremely conservative: 1 year ≈ ~50 weeks with heavy dampening
            estimated_365d = change_7d * 25  # Very conservative multiplier
            return max(-95, min(500, estimated_365d)), "calculated_from_7d"
    
    return None, "unavailable"

# Removed old complex calculation functions - now using simple price/performance relationship

@api_router.get("/rankings/{period}", response_model=CryptoRanking)
async def get_rankings(period: TimePeriod, limit: int = 100):
    """Get crypto rankings for specified period"""
    try:
        scores = await db.crypto_scores.find(
            {"period": period.value}
        ).sort("rank", 1).limit(limit).to_list(None)
        
        if not scores:
            # If no scores exist, trigger data refresh
            await update_crypto_data()
            scores = await db.crypto_scores.find(
                {"period": period.value}
            ).sort("rank", 1).limit(limit).to_list(None)
        
        crypto_scores = [CryptoScore(**score) for score in scores]
        
        return CryptoRanking(
            rankings=crypto_scores,
            period=period,
            total_cryptos=len(crypto_scores),
            last_updated=datetime.utcnow()
        )
    except Exception as e:
        logger.error(f"Error getting rankings: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving rankings")

@api_router.get("/crypto/{symbol}/score/{period}")
async def get_crypto_score(symbol: str, period: TimePeriod):
    """Get detailed score for specific crypto"""
    try:
        score = await db.crypto_scores.find_one({
            "symbol": symbol.upper(),
            "period": period.value
        })
        
        if not score:
            raise HTTPException(status_code=404, detail="Crypto score not found")
        
        return CryptoScore(**score)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting crypto score: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving crypto score")

@api_router.get("/periods")
async def get_available_periods():
    """Get all available time periods"""
    return {
        "periods": [
            {"value": period.value, "label": get_period_label(period)}
            for period in TimePeriod
        ]
    }

@api_router.get("/crypto/{symbol}/historical/{period}")
async def get_historical_price_info(symbol: str, period: TimePeriod):
    """Get historical price information for debugging and validation"""
    try:
        # Get current crypto data
        crypto = await db.crypto_data.find_one({"symbol": symbol.upper()})
        if not crypto:
            raise HTTPException(status_code=404, detail="Crypto not found")
            
        current_price = crypto.get('price', 0)
        result = get_percent_change_for_period(crypto, period)
        
        if isinstance(result, tuple):
            performance, data_source = result
        else:
            performance = result
            data_source = "unknown"
            
        if performance is not None and current_price > 0:
            historical_price = calculate_historical_price_from_performance(current_price, performance)
            
            return {
                "symbol": symbol.upper(),
                "period": period.value,
                "current_price": current_price,
                "performance_percent": performance,
                "calculated_historical_price": historical_price,
                "data_source": data_source,
                "validation_note": f"If the price was ${historical_price:.6f} {period.value} ago, the performance would be {performance:.2f}%"
            }
        else:
            return {
                "symbol": symbol.upper(),
                "period": period.value,
                "error": "No performance data available for this period"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting historical price info: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving historical price information")

def get_period_label(period: TimePeriod) -> str:
    """Get human-readable label for time period"""
    labels = {
        TimePeriod.ONE_HOUR: "1 heure",
        TimePeriod.TWENTY_FOUR_HOURS: "24 heures",
        TimePeriod.ONE_WEEK: "1 semaine",
        TimePeriod.ONE_MONTH: "1 mois",
        TimePeriod.TWO_MONTHS: "2 mois",
        TimePeriod.THREE_MONTHS: "3 mois",
        TimePeriod.SIX_MONTHS: "6 mois",
        TimePeriod.NINE_MONTHS: "9 mois",
        TimePeriod.ONE_YEAR: "1 an"
    }
    return labels.get(period, period.value)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    logger.info("Starting Crypto Rebound Ranking API")
    # Trigger initial data load
    asyncio.create_task(update_crypto_data())

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()