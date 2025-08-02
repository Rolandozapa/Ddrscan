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
    TWENTY_FOUR_HOURS = "24h"
    ONE_WEEK = "7d"
    ONE_MONTH = "30d"
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
    percent_change_24h: float
    percent_change_7d: float
    percent_change_30d: float
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
                        
                        # Fill in missing longer-term data from CoinGecko
                        if not quote.get('percent_change_180d'):
                            quote['percent_change_180d'] = coingecko_data.get('percent_change_180d')
                        if not quote.get('percent_change_365d'):
                            quote['percent_change_365d'] = coingecko_data.get('percent_change_365d')
                        
                        logger.info(f"Enhanced {crypto.get('symbol')} with CoinGecko historical data")
                        
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
                
                # Get historical price data
                history_url = f"{self.coingecko_base_url}/coins/{coin_id}"
                history_params = {
                    'localization': 'false',
                    'tickers': 'false',
                    'market_data': 'true',
                    'community_data': 'false',
                    'developer_data': 'false'
                }
                
                async with session.get(history_url, params=history_params) as history_response:
                    if history_response.status != 200:
                        return None
                    
                    history_data = await history_response.json()
                    market_data = history_data.get('market_data', {})
                    
                    # Extract percentage changes
                    price_changes = market_data.get('price_change_percentage_24h_in_currency', {})
                    
                    return {
                        'percent_change_180d': market_data.get('price_change_percentage_200d', {}).get('usd'),
                        'percent_change_365d': market_data.get('price_change_percentage_1y', {}).get('usd'),
                        'source': 'coingecko'
                    }
                    
        except Exception as e:
            logger.warning(f"CoinGecko API error for {symbol}: {e}")
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
                percent_change_24h=quote.get('percent_change_24h'),
                percent_change_7d=quote.get('percent_change_7d'),
                percent_change_30d=quote.get('percent_change_30d'),
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
    """Calculate comprehensive score for a crypto"""
    try:
        # Get the appropriate percentage change based on period
        percent_change = get_percent_change_for_period(crypto_data, period)
        if percent_change is None:
            return None
            
        # Calculate individual scores
        performance_score = scoring_service.calculate_performance_score(percent_change)
        
        # Use volume as volatility proxy
        volatility_proxy = min(2.0, crypto_data.get('volume_24h', 0) / max(crypto_data.get('market_cap', 1), 1))
        drawdown_score = scoring_service.calculate_drawdown_score(percent_change, volatility_proxy)
        
        rebound_potential_score = scoring_service.calculate_rebound_potential_score(
            percent_change, crypto_data.get('market_cap', 0)
        )
        
        # Use 24h vs longer term for momentum
        short_change = crypto_data.get('percent_change_24h')
        momentum_score = scoring_service.calculate_momentum_score(short_change, percent_change)
        
        # Weighted total score
        total_score = (
            performance_score * 0.25 +
            drawdown_score * 0.20 +
            rebound_potential_score * 0.35 +
            momentum_score * 0.20
        )
        
        return CryptoScore(
            crypto_id=crypto_data['id'],
            symbol=crypto_data['symbol'],
            name=crypto_data['name'],
            market_cap=crypto_data['market_cap'],
            price=crypto_data['price'],
            period=period,
            performance_score=performance_score,
            drawdown_score=drawdown_score,
            rebound_potential_score=rebound_potential_score,
            momentum_score=momentum_score,
            total_score=total_score
        )
    except Exception as e:
        logger.error(f"Error calculating score for {crypto_data.get('symbol', 'unknown')}: {e}")
        return None

def get_percent_change_for_period(crypto_data: dict, period: TimePeriod) -> Optional[float]:
    """Get percentage change for specified period with intelligent calculation fallback"""
    # Direct mapping for available fields
    period_map = {
        TimePeriod.TWENTY_FOUR_HOURS: 'percent_change_24h',
        TimePeriod.ONE_WEEK: 'percent_change_7d',
        TimePeriod.ONE_MONTH: 'percent_change_30d',
        TimePeriod.THREE_MONTHS: 'percent_change_90d',
        TimePeriod.SIX_MONTHS: 'percent_change_180d',
        TimePeriod.NINE_MONTHS: 'percent_change_270d',
        TimePeriod.ONE_YEAR: 'percent_change_365d'
    }
    
    field = period_map.get(period)
    if field and crypto_data.get(field) is not None:
        return crypto_data.get(field)
    
    # Fallback calculations for missing long-term data
    if period == TimePeriod.SIX_MONTHS:
        return calculate_six_month_change(crypto_data)
    elif period == TimePeriod.NINE_MONTHS:
        return calculate_nine_month_change(crypto_data)
    elif period == TimePeriod.ONE_YEAR:
        return calculate_one_year_change(crypto_data)
    
    return None

def calculate_six_month_change(crypto_data: dict) -> Optional[float]:
    """Calculate 6-month change using available data"""
    # Method 1: Use 90d data and extrapolate
    change_90d = crypto_data.get('percent_change_90d')
    change_30d = crypto_data.get('percent_change_30d')
    
    if change_90d is not None and change_30d is not None:
        # Extrapolate based on quarterly trend
        # 6 months = 2 * 3 months, but with diminishing effect
        extrapolated = change_90d * 1.8  # Conservative multiplier
        return max(-95, min(1000, extrapolated))  # Cap extremes
    
    # Method 2: Conservative estimation from monthly data
    if change_30d is not None:
        # Very conservative: assume slower growth over longer periods
        return change_30d * 4.5  # Less than linear growth
    
    return None

def calculate_nine_month_change(crypto_data: dict) -> Optional[float]:
    """Calculate 9-month change using available data"""
    change_90d = crypto_data.get('percent_change_90d')
    change_30d = crypto_data.get('percent_change_30d')
    
    if change_90d is not None:
        # 9 months = 3 * 3 months, with market cycle consideration
        extrapolated = change_90d * 2.5  # Account for market cycles
        return max(-95, min(1500, extrapolated))
    
    if change_30d is not None:
        # Conservative monthly-based estimation
        return change_30d * 6.0
    
    return None

def calculate_one_year_change(crypto_data: dict) -> Optional[float]:
    """Calculate 1-year change using sophisticated estimation"""
    change_90d = crypto_data.get('percent_change_90d')
    change_30d = crypto_data.get('percent_change_30d')
    change_7d = crypto_data.get('percent_change_7d')
    
    # Method 1: Quarterly-based calculation (most reliable)
    if change_90d is not None:
        # 1 year = 4 quarters, but crypto markets are cyclical
        # Use a conservative multiplier that accounts for mean reversion
        if change_90d > 0:
            # Positive trends tend to moderate over time
            extrapolated = change_90d * 3.2
        else:
            # Negative trends also moderate, but slower recovery
            extrapolated = change_90d * 2.8
        
        return max(-95, min(2000, extrapolated))
    
    # Method 2: Monthly-based with market cycle adjustment
    if change_30d is not None:
        cycle_factor = calculate_market_cycle_factor(crypto_data)
        base_multiplier = 8.0  # Base 12 months, reduced for market reality
        adjusted_multiplier = base_multiplier * cycle_factor
        return change_30d * adjusted_multiplier
    
    # Method 3: Weekly trend analysis (least reliable)
    if change_7d is not None:
        # Very conservative approach from weekly data
        volatility_adjustment = 0.6  # Reduce for high volatility
        return change_7d * 30 * volatility_adjustment  # ~30 weeks adjusted
    
    return None

def calculate_market_cycle_factor(crypto_data: dict) -> float:
    """Calculate market cycle adjustment factor based on market cap and volatility"""
    market_cap = crypto_data.get('market_cap', 0)
    
    # Larger market cap = more stable, smaller multiplier
    if market_cap > 10_000_000_000:  # >10B
        return 0.7  # More conservative for large caps
    elif market_cap > 1_000_000_000:  # 1-10B
        return 0.85
    elif market_cap > 100_000_000:   # 100M-1B
        return 1.0   # Standard multiplier
    else:  # <100M
        return 1.2   # Higher potential for small caps

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

def get_period_label(period: TimePeriod) -> str:
    """Get human-readable label for time period"""
    labels = {
        TimePeriod.TWENTY_FOUR_HOURS: "24 heures",
        TimePeriod.ONE_WEEK: "1 semaine",
        TimePeriod.ONE_MONTH: "1 mois",
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