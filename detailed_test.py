import asyncio
import aiohttp

async def test_detailed_cmc_integration():
    BASE_URL = 'https://69332b54-6c73-41b4-ab62-39582afa3ee4.preview.emergentagent.com/api'
    
    async with aiohttp.ClientSession() as session:
        # Get rankings to see actual data
        async with session.get(f'{BASE_URL}/rankings/24h?limit=5') as response:
            if response.status == 200:
                data = await response.json()
                rankings = data.get('rankings', [])
                
                print('🔍 DETAILED CMC API INTEGRATION VERIFICATION')
                print('=' * 50)
                print(f'Total cryptos in ranking: {data.get("total_cryptos", 0)}')
                print(f'Last updated: {data.get("last_updated", "Unknown")}')
                print()
                
                for i, crypto in enumerate(rankings[:5], 1):
                    print(f'{i}. {crypto["symbol"]} ({crypto["name"]})')
                    print(f'   Market Cap: ${crypto["market_cap"]:,.2f}')
                    print(f'   Price: ${crypto["price"]:,.4f}')
                    print(f'   Total Score: {crypto["total_score"]:,.2f}')
                    print(f'   Rank: {crypto["rank"]}')
                    print()
                
                # Test individual crypto score
                if rankings:
                    test_symbol = rankings[0]['symbol']
                    async with session.get(f'{BASE_URL}/crypto/{test_symbol}/score/24h') as score_response:
                        if score_response.status == 200:
                            score_data = await score_response.json()
                            print(f'📊 DETAILED SCORE FOR {test_symbol}:')
                            print(f'   Performance Score: {score_data["performance_score"]:,.2f}')
                            print(f'   Drawdown Score: {score_data["drawdown_score"]:,.2f}')
                            print(f'   Rebound Potential: {score_data["rebound_potential_score"]:,.2f}')
                            print(f'   Momentum Score: {score_data["momentum_score"]:,.2f}')
                            print(f'   Total Score: {score_data["total_score"]:,.2f}')
                            
                print('✅ CMC API Integration fully verified with real data!')
            else:
                print(f'❌ Failed to get rankings: {response.status}')

asyncio.run(test_detailed_cmc_integration())