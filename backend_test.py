#!/usr/bin/env python3
"""
Comprehensive Backend Testing for Crypto Rebound Ranking System
Tests CoinMarketCap API integration, scoring algorithms, and API endpoints
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime
from typing import Dict, List, Any

# Backend API base URL from frontend .env
BASE_URL = "https://69332b54-6c73-41b4-ab62-39582afa3ee4.preview.emergentagent.com/api"

class CryptoBackendTester:
    def __init__(self):
        self.session = None
        self.test_results = {
            "cmc_api_integration": {"status": "pending", "details": []},
            "data_storage": {"status": "pending", "details": []},
            "scoring_algorithm": {"status": "pending", "details": []},
            "api_endpoints": {"status": "pending", "details": []},
            "overall_status": "pending"
        }
    
    async def setup(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        )
    
    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
    
    async def test_cmc_api_integration(self):
        """Test CoinMarketCap API Integration"""
        print("🔄 Testing CoinMarketCap API Integration...")
        
        try:
            # Test the refresh endpoint to trigger CMC API call
            print("  - Testing /refresh-crypto-data endpoint...")
            async with self.session.post(f"{BASE_URL}/refresh-crypto-data") as response:
                if response.status == 200:
                    data = await response.json()
                    self.test_results["cmc_api_integration"]["details"].append(
                        f"✅ Refresh endpoint responded: {data.get('message', 'Success')}"
                    )
                    
                    # Wait a bit for background task to process
                    print("  - Waiting for background data processing...")
                    await asyncio.sleep(10)
                    
                    # Check if data was actually fetched by testing periods endpoint
                    async with self.session.get(f"{BASE_URL}/periods") as periods_response:
                        if periods_response.status == 200:
                            periods_data = await periods_response.json()
                            if periods_data.get("periods"):
                                self.test_results["cmc_api_integration"]["details"].append(
                                    f"✅ Periods endpoint working: {len(periods_data['periods'])} periods available"
                                )
                                self.test_results["cmc_api_integration"]["status"] = "success"
                            else:
                                self.test_results["cmc_api_integration"]["details"].append(
                                    "❌ No periods data found after refresh"
                                )
                                self.test_results["cmc_api_integration"]["status"] = "failed"
                        else:
                            self.test_results["cmc_api_integration"]["details"].append(
                                f"❌ Periods endpoint failed: {periods_response.status}"
                            )
                            self.test_results["cmc_api_integration"]["status"] = "failed"
                else:
                    self.test_results["cmc_api_integration"]["details"].append(
                        f"❌ Refresh endpoint failed: {response.status}"
                    )
                    self.test_results["cmc_api_integration"]["status"] = "failed"
                    
        except Exception as e:
            self.test_results["cmc_api_integration"]["details"].append(f"❌ Exception: {str(e)}")
            self.test_results["cmc_api_integration"]["status"] = "failed"
    
    async def test_data_storage(self):
        """Test Data Storage and Models"""
        print("🔄 Testing Data Storage and Models...")
        
        try:
            # Test if we can get rankings data (which indicates successful storage)
            print("  - Testing data retrieval from storage...")
            async with self.session.get(f"{BASE_URL}/rankings/24h?limit=10") as response:
                if response.status == 200:
                    data = await response.json()
                    rankings = data.get("rankings", [])
                    
                    if rankings:
                        # Validate data structure
                        first_crypto = rankings[0]
                        required_fields = ["symbol", "name", "market_cap", "price", "total_score", 
                                         "performance_score", "drawdown_score", "rebound_potential_score", 
                                         "momentum_score", "rank"]
                        
                        missing_fields = [field for field in required_fields if field not in first_crypto]
                        
                        if not missing_fields:
                            self.test_results["data_storage"]["details"].append(
                                f"✅ Data structure valid: {len(rankings)} cryptos retrieved"
                            )
                            self.test_results["data_storage"]["details"].append(
                                f"✅ Sample crypto: {first_crypto['symbol']} - Score: {first_crypto['total_score']:.2f}"
                            )
                            self.test_results["data_storage"]["status"] = "success"
                        else:
                            self.test_results["data_storage"]["details"].append(
                                f"❌ Missing required fields: {missing_fields}"
                            )
                            self.test_results["data_storage"]["status"] = "failed"
                    else:
                        self.test_results["data_storage"]["details"].append(
                            "❌ No ranking data found in storage"
                        )
                        self.test_results["data_storage"]["status"] = "failed"
                else:
                    self.test_results["data_storage"]["details"].append(
                        f"❌ Rankings endpoint failed: {response.status}"
                    )
                    self.test_results["data_storage"]["status"] = "failed"
                    
        except Exception as e:
            self.test_results["data_storage"]["details"].append(f"❌ Exception: {str(e)}")
            self.test_results["data_storage"]["status"] = "failed"
    
    async def test_scoring_algorithm(self):
        """Test Scoring Algorithm Implementation"""
        print("🔄 Testing Scoring Algorithm...")
        
        try:
            # Get rankings for different periods to test scoring
            periods_to_test = ["24h", "7d", "30d"]
            
            for period in periods_to_test:
                print(f"  - Testing scoring for {period} period...")
                async with self.session.get(f"{BASE_URL}/rankings/{period}?limit=5") as response:
                    if response.status == 200:
                        data = await response.json()
                        rankings = data.get("rankings", [])
                        
                        if rankings:
                            # Validate scoring components
                            for crypto in rankings[:3]:  # Check top 3
                                scores = {
                                    "performance": crypto.get("performance_score", 0),
                                    "drawdown": crypto.get("drawdown_score", 0),
                                    "rebound_potential": crypto.get("rebound_potential_score", 0),
                                    "momentum": crypto.get("momentum_score", 0),
                                    "total": crypto.get("total_score", 0)
                                }
                                
                                # Validate score ranges (0-100)
                                valid_scores = all(0 <= score <= 100 for score in scores.values())
                                
                                if valid_scores:
                                    # Calculate expected total score with weights
                                    expected_total = (
                                        scores["performance"] * 0.25 +
                                        scores["drawdown"] * 0.20 +
                                        scores["rebound_potential"] * 0.35 +
                                        scores["momentum"] * 0.20
                                    )
                                    
                                    # Allow small floating point differences
                                    if abs(scores["total"] - expected_total) < 0.1:
                                        self.test_results["scoring_algorithm"]["details"].append(
                                            f"✅ {period} - {crypto['symbol']}: Scoring calculation correct"
                                        )
                                    else:
                                        self.test_results["scoring_algorithm"]["details"].append(
                                            f"❌ {period} - {crypto['symbol']}: Score calculation mismatch. Expected: {expected_total:.2f}, Got: {scores['total']:.2f}"
                                        )
                                        self.test_results["scoring_algorithm"]["status"] = "failed"
                                        return
                                else:
                                    self.test_results["scoring_algorithm"]["details"].append(
                                        f"❌ {period} - {crypto['symbol']}: Invalid score ranges: {scores}"
                                    )
                                    self.test_results["scoring_algorithm"]["status"] = "failed"
                                    return
                        else:
                            self.test_results["scoring_algorithm"]["details"].append(
                                f"❌ No rankings data for {period}"
                            )
                            self.test_results["scoring_algorithm"]["status"] = "failed"
                            return
                    else:
                        self.test_results["scoring_algorithm"]["details"].append(
                            f"❌ Rankings endpoint failed for {period}: {response.status}"
                        )
                        self.test_results["scoring_algorithm"]["status"] = "failed"
                        return
            
            self.test_results["scoring_algorithm"]["status"] = "success"
            
        except Exception as e:
            self.test_results["scoring_algorithm"]["details"].append(f"❌ Exception: {str(e)}")
            self.test_results["scoring_algorithm"]["status"] = "failed"
    
    async def test_api_endpoints(self):
        """Test All API Endpoints"""
        print("🔄 Testing API Endpoints...")
        
        endpoints_to_test = [
            {"method": "GET", "path": "/", "name": "Root endpoint"},
            {"method": "GET", "path": "/periods", "name": "Periods endpoint"},
            {"method": "GET", "path": "/rankings/24h", "name": "Rankings 24h endpoint"},
            {"method": "GET", "path": "/rankings/7d", "name": "Rankings 7d endpoint"},
            {"method": "GET", "path": "/rankings/30d", "name": "Rankings 30d endpoint"},
        ]
        
        try:
            for endpoint in endpoints_to_test:
                print(f"  - Testing {endpoint['name']}...")
                
                if endpoint["method"] == "GET":
                    async with self.session.get(f"{BASE_URL}{endpoint['path']}") as response:
                        if response.status == 200:
                            data = await response.json()
                            self.test_results["api_endpoints"]["details"].append(
                                f"✅ {endpoint['name']}: Status 200, Response received"
                            )
                        else:
                            self.test_results["api_endpoints"]["details"].append(
                                f"❌ {endpoint['name']}: Status {response.status}"
                            )
                            self.test_results["api_endpoints"]["status"] = "failed"
                            return
            
            # Test individual crypto score endpoint if we have data
            print("  - Testing individual crypto score endpoint...")
            async with self.session.get(f"{BASE_URL}/rankings/24h?limit=1") as response:
                if response.status == 200:
                    data = await response.json()
                    rankings = data.get("rankings", [])
                    if rankings:
                        test_symbol = rankings[0]["symbol"]
                        async with self.session.get(f"{BASE_URL}/crypto/{test_symbol}/score/24h") as score_response:
                            if score_response.status == 200:
                                score_data = await score_response.json()
                                self.test_results["api_endpoints"]["details"].append(
                                    f"✅ Individual crypto score endpoint: {test_symbol} score retrieved"
                                )
                            else:
                                self.test_results["api_endpoints"]["details"].append(
                                    f"❌ Individual crypto score endpoint failed: {score_response.status}"
                                )
                                self.test_results["api_endpoints"]["status"] = "failed"
                                return
            
            self.test_results["api_endpoints"]["status"] = "success"
            
        except Exception as e:
            self.test_results["api_endpoints"]["details"].append(f"❌ Exception: {str(e)}")
            self.test_results["api_endpoints"]["status"] = "failed"
    
    async def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting Crypto Backend Testing Suite")
        print(f"📍 Testing against: {BASE_URL}")
        print("=" * 60)
        
        await self.setup()
        
        try:
            # Test in order of dependencies
            await self.test_cmc_api_integration()
            await self.test_data_storage()
            await self.test_scoring_algorithm()
            await self.test_api_endpoints()
            
            # Determine overall status
            all_tests = [
                self.test_results["cmc_api_integration"]["status"],
                self.test_results["data_storage"]["status"],
                self.test_results["scoring_algorithm"]["status"],
                self.test_results["api_endpoints"]["status"]
            ]
            
            if all(status == "success" for status in all_tests):
                self.test_results["overall_status"] = "success"
            elif any(status == "failed" for status in all_tests):
                self.test_results["overall_status"] = "failed"
            else:
                self.test_results["overall_status"] = "partial"
                
        finally:
            await self.cleanup()
    
    def print_results(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 60)
        print("📊 BACKEND TEST RESULTS")
        print("=" * 60)
        
        status_emoji = {
            "success": "✅",
            "failed": "❌",
            "pending": "⏳",
            "partial": "⚠️"
        }
        
        for test_name, result in self.test_results.items():
            if test_name == "overall_status":
                continue
                
            status = result["status"]
            emoji = status_emoji.get(status, "❓")
            
            print(f"\n{emoji} {test_name.upper().replace('_', ' ')}: {status.upper()}")
            for detail in result["details"]:
                print(f"   {detail}")
        
        print(f"\n🎯 OVERALL STATUS: {status_emoji.get(self.test_results['overall_status'], '❓')} {self.test_results['overall_status'].upper()}")
        print("=" * 60)

async def main():
    """Main test execution"""
    tester = CryptoBackendTester()
    await tester.run_all_tests()
    tester.print_results()
    
    return tester.test_results

if __name__ == "__main__":
    results = asyncio.run(main())