from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import uuid
from datetime import datetime, timedelta
import aiohttp
import asyncio
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(title="DDRscan - Crypto Drawdown & Rebound Scanner", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Models
class CryptoData(BaseModel):
    id: str
    symbol: str
    name: str
    current_price: float
    price_change_percentage_24h: float
    price_change_percentage_7d: float
    price_change_percentage_30d: float
    market_cap: int
    volume_24h: float
    drawdown_percentage: Optional[float] = None
    rebound_score: Optional[float] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)

class OpportunityFilter(BaseModel):
    min_drawdown: float = 10.0
    max_drawdown: float = 80.0
    min_market_cap: int = 1000000
    min_volume: float = 100000
    top_n: int = 50

class CryptoOpportunity(BaseModel):
    crypto: CryptoData
    opportunity_score: float
    risk_level: str
    recommended_action: str

# Cache for API calls
crypto_cache = {}
cache_timestamp = None
CACHE_DURATION = 300  # 5 minutes

async def fetch_crypto_data():
    """Fetch cryptocurrency data from CoinGecko"""
    global crypto_cache, cache_timestamp
    
    # Check cache
    if cache_timestamp and (datetime.utcnow() - cache_timestamp).seconds < CACHE_DURATION:
        return crypto_cache
    
    try:
        async with aiohttp.ClientSession() as session:
            # Get top 250 cryptocurrencies
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': 250,
                'page': 1,
                'sparkline': False,
                'price_change_percentage': '1h,24h,7d,30d'
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    crypto_cache = data
                    cache_timestamp = datetime.utcnow()
                    return data
                else:
                    raise HTTPException(status_code=500, detail="Failed to fetch crypto data")
    except Exception as e:
        logging.error(f"Error fetching crypto data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch crypto data")

def calculate_drawdown_and_score(crypto_data):
    """Calculate drawdown percentage and rebound opportunity score"""
    try:
        # Extract price changes
        change_24h = crypto_data.get('price_change_percentage_24h', 0) or 0
        change_7d = crypto_data.get('price_change_percentage_7d', 0) or 0
        change_30d = crypto_data.get('price_change_percentage_30d', 0) or 0
        
        # Calculate maximum drawdown (most negative change)
        drawdown = min(change_24h, change_7d, change_30d)
        
        # Calculate rebound score based on multiple factors
        volume = crypto_data.get('total_volume', 0) or 0
        market_cap = crypto_data.get('market_cap', 0) or 0
        
        # Base score from drawdown (higher drawdown = higher opportunity)
        drawdown_score = abs(drawdown) if drawdown < 0 else 0
        
        # Volume factor (higher volume = more reliable)
        volume_score = min(np.log10(volume + 1) / 10, 1.0) if volume > 0 else 0
        
        # Market cap stability factor
        mcap_score = min(np.log10(market_cap + 1) / 12, 1.0) if market_cap > 0 else 0
        
        # Recent momentum (if 24h is better than 7d/30d, it might be recovering)
        momentum_score = 0
        if change_24h > change_7d and change_24h > change_30d:
            momentum_score = 0.3
        
        # Final opportunity score (0-100)
        opportunity_score = (
            drawdown_score * 0.4 +  # 40% weight on drawdown
            volume_score * 20 +     # 20% weight on volume
            mcap_score * 20 +       # 20% weight on market cap
            momentum_score * 20     # 20% weight on momentum
        )
        
        return abs(drawdown), min(opportunity_score, 100)
        
    except Exception as e:
        logging.error(f"Error calculating drawdown: {e}")
        return 0, 0

def determine_risk_level(drawdown, market_cap, volume):
    """Determine risk level based on drawdown and market metrics"""
    if drawdown > 50 or market_cap < 10000000:
        return "HIGH"
    elif drawdown > 30 or market_cap < 100000000:
        return "MEDIUM"
    else:
        return "LOW"

def get_recommendation(score, risk_level, drawdown):
    """Generate trading recommendation"""
    if score > 70 and risk_level in ["LOW", "MEDIUM"]:
        return "STRONG BUY - Great rebound opportunity"
    elif score > 50 and drawdown > 20:
        return "BUY - Good opportunity with caution"
    elif score > 30:
        return "WATCH - Monitor for entry point"
    else:
        return "AVOID - Low probability opportunity"

@api_router.get("/")
async def root():
    return {"message": "DDRscan API - Crypto Drawdown Scanner", "version": "1.0.0"}

@api_router.get("/crypto/all", response_model=List[CryptoData])
async def get_all_cryptos():
    """Get all cryptocurrency data with drawdown analysis"""
    raw_data = await fetch_crypto_data()
    
    processed_cryptos = []
    for crypto in raw_data:
        try:
            drawdown, score = calculate_drawdown_and_score(crypto)
            
            crypto_data = CryptoData(
                id=crypto.get('id', ''),
                symbol=crypto.get('symbol', '').upper(),
                name=crypto.get('name', ''),
                current_price=crypto.get('current_price', 0),
                price_change_percentage_24h=crypto.get('price_change_percentage_24h', 0) or 0,
                price_change_percentage_7d=crypto.get('price_change_percentage_7d', 0) or 0,
                price_change_percentage_30d=crypto.get('price_change_percentage_30d', 0) or 0,
                market_cap=crypto.get('market_cap', 0) or 0,
                volume_24h=crypto.get('total_volume', 0) or 0,
                drawdown_percentage=drawdown,
                rebound_score=score
            )
            processed_cryptos.append(crypto_data)
        except Exception as e:
            logging.error(f"Error processing crypto {crypto.get('id', 'unknown')}: {e}")
            continue
    
    return processed_cryptos

@api_router.post("/opportunities", response_model=List[CryptoOpportunity])
async def get_opportunities(filters: OpportunityFilter):
    """Get filtered cryptocurrency opportunities"""
    all_cryptos = await get_all_cryptos()
    
    opportunities = []
    for crypto in all_cryptos:
        # Apply filters
        if (crypto.drawdown_percentage >= filters.min_drawdown and 
            crypto.drawdown_percentage <= filters.max_drawdown and
            crypto.market_cap >= filters.min_market_cap and
            crypto.volume_24h >= filters.min_volume):
            
            risk_level = determine_risk_level(
                crypto.drawdown_percentage, 
                crypto.market_cap, 
                crypto.volume_24h
            )
            
            recommendation = get_recommendation(
                crypto.rebound_score, 
                risk_level, 
                crypto.drawdown_percentage
            )
            
            opportunity = CryptoOpportunity(
                crypto=crypto,
                opportunity_score=crypto.rebound_score,
                risk_level=risk_level,
                recommended_action=recommendation
            )
            opportunities.append(opportunity)
    
    # Sort by opportunity score (highest first)
    opportunities.sort(key=lambda x: x.opportunity_score, reverse=True)
    
    # Return top N opportunities
    return opportunities[:filters.top_n]

@api_router.get("/crypto/{crypto_id}")
async def get_crypto_details(crypto_id: str):
    """Get detailed information for a specific cryptocurrency"""
    all_cryptos = await get_all_cryptos()
    
    for crypto in all_cryptos:
        if crypto.id == crypto_id or crypto.symbol.lower() == crypto_id.lower():
            return crypto
    
    raise HTTPException(status_code=404, detail="Cryptocurrency not found")

@api_router.get("/market/stats")
async def get_market_stats():
    """Get overall market statistics"""
    all_cryptos = await get_all_cryptos()
    
    if not all_cryptos:
        return {"error": "No data available"}
    
    total_cryptos = len(all_cryptos)
    avg_drawdown = sum(c.drawdown_percentage for c in all_cryptos) / total_cryptos
    
    opportunities = [c for c in all_cryptos if c.drawdown_percentage > 10]
    high_opportunities = [c for c in all_cryptos if c.rebound_score > 50]
    
    return {
        "total_cryptos_analyzed": total_cryptos,
        "average_drawdown": round(avg_drawdown, 2),
        "total_opportunities": len(opportunities),
        "high_score_opportunities": len(high_opportunities),
        "market_sentiment": "Bearish" if avg_drawdown > 15 else "Neutral" if avg_drawdown > 5 else "Bullish",
        "last_updated": datetime.utcnow()
    }

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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()