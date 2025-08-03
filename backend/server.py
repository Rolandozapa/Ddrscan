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
    TWO_MONTHS = "60d"
    THREE_MONTHS = "90d"
    SIX_MONTHS = "180d"
    NINE_MONTHS = "270d"
    ONE_YEAR = "365d"

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
    percent_change_180d: Optional[float] = None  # 6 months - from CoinGecko/Yahoo
    percent_change_270d: Optional[float] = None  # 9 months - from CoinGecko/Yahoo  
    percent_change_365d: Optional[float] = None  # 1 year - from CoinGecko/Yahoo
    data_sources: Optional[List[str]] = None     # Track data sources
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
        self.yahoo_base_url = "https://query1.finance.yahoo.com/v8/finance/chart"
        self.session_timeout = aiohttp.ClientTimeout(total=30)
    
    async def fetch_top_cryptos(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch top crypto data from CoinMarketCap API and enhance with historical data"""
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
                        
                        # Enhance top 100 cryptos with historical data
                        enhanced_cryptos = await self.enhance_with_historical_data(session, cryptos)
                        return enhanced_cryptos
                    else:
                        logger.error(f"CoinMarketCap API error: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching crypto data: {e}")
            return []

    async def enhance_with_historical_data(self, session: aiohttp.ClientSession, cryptos: List[Dict]) -> List[Dict]:
        """Enhance crypto data with historical data from CoinGecko and Yahoo Finance"""
        enhanced_cryptos = []
        
        # Focus on top 20 cryptos for CoinGecko (to avoid rate limits)
        priority_cryptos = cryptos[:20]
        
        for i, crypto in enumerate(cryptos):
            enhanced_crypto = crypto.copy()
            
            # Only enhance top cryptos with external APIs
            if i < len(priority_cryptos):
                symbol = crypto.get('symbol', '').upper()
                
                try:
                    # Try CoinGecko first (most reliable for crypto)
                    coingecko_data = await self.fetch_coingecko_historical_data(session, symbol)
                    if coingecko_data:
                        self.apply_historical_data(enhanced_crypto, coingecko_data, "coingecko")
                        logger.info(f"✅ Enhanced {symbol} with CoinGecko data")
                    else:
                        # Fallback to calculations from CMC data
                        calculated_data = self.calculate_long_term_data(crypto)
                        if calculated_data:
                            self.apply_historical_data(enhanced_crypto, calculated_data, "calculated")
                            logger.info(f"📊 Enhanced {symbol} with calculated data")
                    
                    # Add delay every 5 requests to respect CoinGecko rate limits
                    if (i + 1) % 5 == 0:
                        await asyncio.sleep(3)
                        
                except Exception as e:
                    logger.warning(f"Failed to enhance {symbol} with historical data: {e}")
                    # Always fallback to calculations
                    calculated_data = self.calculate_long_term_data(crypto)
                    if calculated_data:
                        self.apply_historical_data(enhanced_crypto, calculated_data, "calculated")
            else:
                # For cryptos beyond top 20, use calculations only
                calculated_data = self.calculate_long_term_data(crypto)
                if calculated_data:
                    self.apply_historical_data(enhanced_crypto, calculated_data, "calculated")
            
            enhanced_cryptos.append(enhanced_crypto)
        
        return enhanced_cryptos

    async def fetch_coingecko_historical_data(self, session: aiohttp.ClientSession, symbol: str) -> Optional[Dict]:
        """Fetch real historical data from CoinGecko with 1 price per day"""
        try:
            # Direct mapping for major cryptos to avoid search API calls
            symbol_to_id = {
                'BTC': 'bitcoin',
                'ETH': 'ethereum', 
                'BNB': 'binancecoin',
                'XRP': 'ripple',
                'ADA': 'cardano',
                'SOL': 'solana',
                'DOT': 'polkadot',
                'DOGE': 'dogecoin',
                'AVAX': 'avalanche-2',
                'MATIC': 'matic-network',
                'LINK': 'chainlink',
                'UNI': 'uniswap'
            }
            
            coin_id = symbol_to_id.get(symbol)
            
            # If not in direct mapping, search for it
            if not coin_id:
                search_url = f"{self.coingecko_base_url}/search"
                params = {'query': symbol}
                
                async with session.get(search_url, params=params) as search_response:
                    if search_response.status != 200:
                        return None
                    
                    search_data = await search_response.json()
                    coins = search_data.get('coins', [])
                    
                    # Find exact symbol match
                    for coin in coins:
                        if coin.get('symbol', '').upper() == symbol:
                            coin_id = coin.get('id')
                            break
                    
                    if not coin_id:
                        return None
            
            # Get market chart data for the past year with daily interval (1 price/day)
            chart_url = f"{self.coingecko_base_url}/coins/{coin_id}/market_chart"
            chart_params = {
                'vs_currency': 'usd',
                'days': '365',
                'interval': 'daily'  # This ensures 1 price per day
            }
            
            async with session.get(chart_url, params=chart_params) as chart_response:
                if chart_response.status != 200:
                    logger.warning(f"CoinGecko chart API failed for {symbol}: {chart_response.status}")
                    return None
                
                chart_data = await chart_response.json()
                prices = chart_data.get('prices', [])
                
                if len(prices) < 180:  # Need at least 6 months of data
                    logger.warning(f"Insufficient data for {symbol}: {len(prices)} days")
                    return None
                
                # Calculate percentage changes from daily price data
                current_price = prices[-1][1]  # Latest price
                
                # Calculate historical prices for different periods
                price_180d = prices[-180][1] if len(prices) >= 180 else None  # 6 months ago
                price_270d = prices[-270][1] if len(prices) >= 270 else None  # 9 months ago  
                price_365d = prices[-365][1] if len(prices) >= 365 else prices[0][1]  # 1 year ago
                
                # Calculate percentage changes
                result = {}
                if price_180d and price_180d > 0:
                    result['percent_change_180d'] = ((current_price - price_180d) / price_180d) * 100
                if price_270d and price_270d > 0:
                    result['percent_change_270d'] = ((current_price - price_270d) / price_270d) * 100
                if price_365d and price_365d > 0:
                    result['percent_change_365d'] = ((current_price - price_365d) / price_365d) * 100
                
                if result:
                    logger.info(f"✅ CoinGecko: {symbol} enhanced with {len(prices)} days of data")
                    return result
                
        except Exception as e:
            logger.warning(f"CoinGecko error for {symbol}: {e}")
        
        return None

    # Removed Yahoo Finance integration due to rate limiting issues

    def calculate_long_term_data(self, crypto_data: Dict) -> Optional[Dict]:
        """Calculate long-term data from available shorter periods as last resort"""
        try:
            quote = crypto_data.get('quote', {}).get('USD', {})
            change_90d = quote.get('percent_change_90d')
            change_30d = quote.get('percent_change_30d')
            
            if not change_90d and not change_30d:
                return None
            
            result = {}
            market_cap = quote.get('market_cap', 0)
            
            # Calculate with conservative multipliers
            if change_90d is not None:
                # 6 months = 2 × 90 days (conservative)
                result['percent_change_180d'] = change_90d * 1.8
                # 9 months = 3 × 90 days (very conservative)
                result['percent_change_270d'] = change_90d * 2.5
                # 1 year = 4 × 90 days (with market cycle adjustment)
                multiplier = 3.0 if change_90d > 0 else 2.5
                result['percent_change_365d'] = change_90d * multiplier
            
            elif change_30d is not None:
                # More conservative estimates from monthly data
                cap_factor = 1.0 if market_cap > 1_000_000_000 else 1.2
                result['percent_change_180d'] = change_30d * 5.0 * cap_factor
                result['percent_change_270d'] = change_30d * 7.0 * cap_factor
                result['percent_change_365d'] = change_30d * 9.0 * cap_factor
            
            # Apply reasonable bounds
            for key in result:
                result[key] = max(-95, min(2000, result[key]))
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating long-term data: {e}")
            return None

    def apply_historical_data(self, crypto: Dict, historical_data: Dict, source: str):
        """Apply historical data to crypto object"""
        quote = crypto.get('quote', {}).get('USD', {})
        
        for period in ['percent_change_180d', 'percent_change_270d', 'percent_change_365d']:
            if period in historical_data and historical_data[period] is not None:
                quote[period] = historical_data[period]
        
        # Track data sources
        data_sources = crypto.get('data_sources', ['coinmarketcap'])
        if source not in data_sources:
            data_sources.append(source)
        crypto['data_sources'] = data_sources

    async def fetch_historical_data(self, symbol: str, time_period: TimePeriod) -> Dict[str, Any]:
        """Fetch historical data for calculating drawdown and momentum"""
        # For now, we'll use the percentage changes from CMC/CoinGecko
        # In a full implementation, we'd fetch OHLC data
        return {}

crypto_service = CryptoAPIService()

class CryptoScoringService:
    @staticmethod
    def calculate_performance_score(percent_change: float) -> float:
        """Calculate performance score - OPTIMIZED for rebound detection"""
        if percent_change is None:
            return 0.0
        
        # The key insight: cryptos that dropped significantly have higher rebound potential
        # But we need to reward recent recovery signs too
        
        if percent_change <= -50:  # Massive drop = huge rebound potential
            return 25.0  # Low performance score, but high rebound potential will compensate
        elif percent_change <= -30:  # Significant drop = good rebound potential  
            return 35.0
        elif percent_change <= -15:  # Moderate drop = some rebound potential
            return 45.0
        elif percent_change <= -5:   # Small drop = limited rebound potential
            return 50.0
        elif percent_change <= 10:   # Small gain = good performance
            return 65.0
        elif percent_change <= 25:   # Good gain = strong performance
            return 75.0
        else:  # Massive gain = excellent performance
            return min(95.0, 70.0 + math.log(1 + percent_change/25) * 10)
    
    @staticmethod
    def calculate_rebound_potential_score(current_change: float, market_cap: float, period: TimePeriod) -> float:
        """ENHANCED rebound potential - core of the scoring system"""
        if current_change is None:
            return 50.0
        
        # Market cap factor - smaller caps have exponentially higher rebound potential
        if market_cap > 50_000_000_000:  # >50B (BTC, ETH tier)
            market_cap_factor = 0.6
            base_potential = 30
        elif market_cap > 10_000_000_000:  # 10-50B
            market_cap_factor = 0.8
            base_potential = 40
        elif market_cap > 1_000_000_000:   # 1-10B
            market_cap_factor = 1.0
            base_potential = 50
        elif market_cap > 100_000_000:     # 100M-1B
            market_cap_factor = 1.4
            base_potential = 60
        elif market_cap > 10_000_000:      # 10M-100M - HIGH POTENTIAL ZONE
            market_cap_factor = 1.8
            base_potential = 70
        else:  # <10M - ULTRA HIGH POTENTIAL (but risky)
            market_cap_factor = 2.2
            base_potential = 75
        
        # Period-specific rebound logic
        period_multiplier = {
            TimePeriod.ONE_HOUR: 0.7,
            TimePeriod.TWENTY_FOUR_HOURS: 0.8,
            TimePeriod.ONE_WEEK: 0.9,
            TimePeriod.ONE_MONTH: 1.0,
            TimePeriod.TWO_MONTHS: 1.1,
            TimePeriod.THREE_MONTHS: 1.2,
            TimePeriod.SIX_MONTHS: 1.15,
            TimePeriod.NINE_MONTHS: 1.1,
            TimePeriod.ONE_YEAR: 1.0
        }.get(period, 1.0)
        
        # The CORE rebound logic: bigger drops = bigger rebound potential
        if current_change <= -70:  # Massive crash - MAXIMUM rebound potential
            rebound_score = base_potential + (60 * market_cap_factor * period_multiplier)
        elif current_change <= -50:  # Severe drop - very high rebound potential
            rebound_score = base_potential + (50 * market_cap_factor * period_multiplier)
        elif current_change <= -30:  # Significant drop - high rebound potential
            rebound_score = base_potential + (40 * market_cap_factor * period_multiplier)
        elif current_change <= -15:  # Moderate drop - good rebound potential
            rebound_score = base_potential + (25 * market_cap_factor * period_multiplier)
        elif current_change <= -5:   # Small drop - some rebound potential
            rebound_score = base_potential + (15 * market_cap_factor * period_multiplier)
        elif current_change <= 5:    # Flat - limited rebound potential
            rebound_score = base_potential + (5 * market_cap_factor)
        else:  # Already rebounded - lower rebound potential
            # But still give credit for momentum
            rebound_score = base_potential - (current_change * 0.3)
        
        return max(10, min(100, rebound_score))
    
    @staticmethod
    def calculate_momentum_score(short_change: float, long_change: float, period: TimePeriod) -> float:
        """ENHANCED momentum - detects early recovery signs"""
        if short_change is None or long_change is None:
            return 50.0
        
        # Key insight: positive short-term momentum after negative long-term = STRONG SIGNAL
        momentum_differential = short_change - long_change
        
        # Special case: Recovery momentum (positive recent, negative long-term)
        if short_change > 0 and long_change < -10:
            # This is a potential reversal signal!
            recovery_strength = abs(long_change)  # Deeper the fall, stronger the signal
            momentum_base = 80 + min(15, recovery_strength / 5)
        
        # Strong positive momentum differential
        elif momentum_differential > 20:
            momentum_base = 85
        elif momentum_differential > 10:
            momentum_base = 75
        elif momentum_differential > 5:
            momentum_base = 65
        elif momentum_differential > 0:
            momentum_base = 55
        elif momentum_differential > -5:
            momentum_base = 45
        elif momentum_differential > -15:
            momentum_base = 35
        else:
            momentum_base = 25
        
        # Boost for consistent direction (trend following)
        if (short_change > 0 and long_change > 0) or (short_change < 0 and long_change < 0):
            trend_consistency = 5
        else:
            # Trend reversal - can be positive or negative depending on context
            if short_change > 0 and long_change < 0:
                trend_consistency = 10  # Recovery signal!
            else:
                trend_consistency = -5  # Deterioration signal
        
        return max(0, min(100, momentum_base + trend_consistency))
    
    @staticmethod  
    def calculate_drawdown_score(percent_change: float, volatility_proxy: float, period: TimePeriod) -> float:
        """Enhanced drawdown score focusing on recovery resilience"""
        if percent_change is None:
            return 50.0
        
        # Period-specific risk adjustments
        period_multiplier = {
            TimePeriod.ONE_HOUR: 1.1,
            TimePeriod.TWENTY_FOUR_HOURS: 1.0,
            TimePeriod.ONE_WEEK: 0.9,
            TimePeriod.ONE_MONTH: 0.8,
            TimePeriod.TWO_MONTHS: 0.75,
            TimePeriod.THREE_MONTHS: 0.7,
            TimePeriod.SIX_MONTHS: 0.65,
            TimePeriod.NINE_MONTHS: 0.6,
            TimePeriod.ONE_YEAR: 0.55
        }.get(period, 0.8)
        
        # For rebound analysis, we want to reward cryptos that have shown they can recover
        # Even from significant drops
        if percent_change > 0:
            # Already recovered - high drawdown resistance score
            base_score = 85 - (percent_change * 0.1)  # Slight penalty for overextension
        elif percent_change > -20:
            # Small drop - good drawdown resistance
            base_score = 75 + abs(percent_change)
        elif percent_change > -50:
            # Moderate drop - still has some resistance
            base_score = 60 + (abs(percent_change) - 20) * 0.5
        else:
            # Large drop - but if it's a quality project, this could be opportunity
            base_score = 40 + (100 - abs(percent_change)) * 0.3
        
        # Adjust for volatility (higher volatility = more risky but more opportunity)
        volatility_adjustment = volatility_proxy * 10  # Small adjustment
        
        return max(10, min(100, base_score * period_multiplier + volatility_adjustment))

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
                percent_change_180d=quote.get('percent_change_180d'),  # From external APIs
                percent_change_270d=quote.get('percent_change_270d'),  # From external APIs
                percent_change_365d=quote.get('percent_change_365d'),  # From external APIs
                data_sources=crypto.get('data_sources', ['coinmarketcap']),
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
    
    # All supported periods including long-term with historical data
    supported_periods = [
        TimePeriod.ONE_HOUR,
        TimePeriod.TWENTY_FOUR_HOURS, 
        TimePeriod.ONE_WEEK,
        TimePeriod.ONE_MONTH,
        TimePeriod.TWO_MONTHS,
        TimePeriod.THREE_MONTHS,
        TimePeriod.SIX_MONTHS,      # Historical data from CoinGecko/Yahoo
        TimePeriod.NINE_MONTHS,     # Historical data from CoinGecko/Yahoo
        TimePeriod.ONE_YEAR         # Historical data from CoinGecko/Yahoo
    ]
    
    for period in supported_periods:
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
            logger.info(f"✅ Calculated {len(scores)} scores for {period.value}")

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
        if period == TimePeriod.ONE_HOUR:
            reference_change = crypto_data.get('percent_change_24h')
        elif period == TimePeriod.TWENTY_FOUR_HOURS:
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
    """OPTIMIZED weights focusing on REBOUND DETECTION"""
    if period in [TimePeriod.ONE_HOUR, TimePeriod.TWENTY_FOUR_HOURS]:
        # Very short-term: Focus HEAVILY on momentum and rebound potential
        return {
            'performance': 0.10,      # Less important for rebond detection
            'drawdown': 0.10,         # Less important for rebond detection  
            'rebound': 0.50,          # CORE: potentiel rebond
            'momentum': 0.30          # CORE: signes de reprise
        }
    elif period in [TimePeriod.ONE_WEEK, TimePeriod.ONE_MONTH]:
        # Short to medium-term: Rebound + Momentum focus
        return {
            'performance': 0.15,      # Reduced importance
            'drawdown': 0.10,         # Reduced importance
            'rebound': 0.45,          # PRIMARY: potentiel rebond  
            'momentum': 0.30          # PRIMARY: momentum de récupération
        }
    elif period in [TimePeriod.TWO_MONTHS, TimePeriod.THREE_MONTHS]:
        # Medium-term: Strong rebound focus with some performance consideration
        return {
            'performance': 0.15,      # Some importance for context
            'drawdown': 0.15,         # Some importance for risk
            'rebound': 0.45,          # MAIN: potentiel rebond
            'momentum': 0.25          # MAIN: momentum analysis
        }
    else:  # SIX_MONTHS, NINE_MONTHS, ONE_YEAR - Long term rebound opportunities
        # Long-term: Maximum rebound potential focus
        return {
            'performance': 0.10,      # Minimal - we WANT cryptos that dropped
            'drawdown': 0.15,         # Some risk assessment
            'rebound': 0.50,          # MAXIMUM: biggest rebound potential
            'momentum': 0.25          # Important: early recovery signs
        }

# Simplified approach - using only direct CoinMarketCap percentage data

def get_percent_change_for_period(crypto_data: dict, period: TimePeriod):
    """Get percentage change for specified period with multiple data sources"""
    # Direct mapping for all periods
    period_map = {
        TimePeriod.ONE_HOUR: 'percent_change_1h',
        TimePeriod.TWENTY_FOUR_HOURS: 'percent_change_24h',
        TimePeriod.ONE_WEEK: 'percent_change_7d',
        TimePeriod.ONE_MONTH: 'percent_change_30d',
        TimePeriod.TWO_MONTHS: 'percent_change_60d',
        TimePeriod.THREE_MONTHS: 'percent_change_90d',
        TimePeriod.SIX_MONTHS: 'percent_change_180d',
        TimePeriod.NINE_MONTHS: 'percent_change_270d',
        TimePeriod.ONE_YEAR: 'percent_change_365d'
    }
    
    field = period_map.get(period)
    if not field:
        return None, "unavailable"
    
    value = crypto_data.get(field)
    if value is not None:
        # Determine data source based on period and available sources
        data_sources = crypto_data.get('data_sources', ['coinmarketcap'])
        
        if period in [TimePeriod.ONE_HOUR, TimePeriod.TWENTY_FOUR_HOURS, TimePeriod.ONE_WEEK, 
                      TimePeriod.ONE_MONTH, TimePeriod.TWO_MONTHS, TimePeriod.THREE_MONTHS]:
            return value, "direct_cmc"
        elif 'coingecko' in data_sources:
            return value, "coingecko_historical"
        elif 'yahoo' in data_sources:
            return value, "yahoo_historical" 
        elif 'calculated' in data_sources:
            return value, "calculated_from_cmc"
        else:
            return value, "external_source"
    
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
    """Get performance information for debugging and validation - simplified approach"""
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
            
        if performance is not None:
            return {
                "symbol": symbol.upper(),
                "period": period.value,
                "current_price": current_price,
                "performance_percent": performance,
                "data_source": data_source,
                "note": f"Using direct CoinMarketCap percentage data: {performance:.2f}% change over {period.value}"
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