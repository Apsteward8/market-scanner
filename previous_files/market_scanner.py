#!/usr/bin/env python3
"""
Simple ProphetX Market Scanner
Start here - just scan markets and identify opportunities without placing bets
"""

import requests
import json
from datetime import datetime

class SimpleProphetXScanner:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://sandbox-api.prophetx.com"  # Use sandbox for testing
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        # Simple settings
        self.min_stake_to_undercut = 5000  # Only look at bets $5k+
        self.undercut_amount = 1  # Improve odds by 1
    
    def get_markets(self):
        """Get list of available markets"""
        print("🔍 Fetching available markets...")
        
        url = f"{self.base_url}/markets"
        params = {
            'sport': 'baseball',
            'status': 'open'
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code == 200:
                markets = response.json()
                print(f"✅ Found {len(markets.get('data', []))} open baseball markets")
                return markets.get('data', [])
            else:
                print(f"❌ Error fetching markets: {response.status_code}")
                print(f"Response: {response.text}")
                return []
                
        except Exception as e:
            print(f"💥 Exception fetching markets: {e}")
            return []
    
    def get_market_details(self, market_id):
        """Get detailed info for a specific market"""
        url = f"{self.base_url}/markets/{market_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error fetching market {market_id}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"💥 Exception fetching market {market_id}: {e}")
            return None
    
    def find_undercut_opportunities(self, market_data):
        """Look for bets worth undercutting"""
        opportunities = []
        
        if not market_data or 'outcomes' not in market_data:
            return opportunities
        
        market_id = market_data.get('id', 'unknown')
        home_team = market_data.get('home_team', '')
        away_team = market_data.get('away_team', '')
        game_name = f"{away_team} @ {home_team}"
        
        print(f"\n📊 Analyzing: {game_name}")
        
        for outcome in market_data['outcomes']:
            stake = outcome.get('stake', 0)
            odds = outcome.get('odds', 0)
            display_name = outcome.get('display_name', 'Unknown')
            
            # Only look at high-value bets
            if stake >= self.min_stake_to_undercut:
                
                # Calculate what our undercut odds would be
                if odds > 0:  # Positive odds (underdog)
                    our_odds = odds - self.undercut_amount
                else:  # Negative odds (favorite)  
                    our_odds = odds + self.undercut_amount
                
                # Calculate potential profit if we get matched
                bet_amount = min(stake * 0.5, 1000)  # Bet up to half their stake, max $1000
                
                if our_odds > 0:
                    potential_win = bet_amount * (our_odds / 100)
                else:
                    potential_win = bet_amount * (100 / abs(our_odds))
                
                potential_profit = potential_win - bet_amount
                
                opportunity = {
                    'game': game_name,
                    'market_id': market_id,
                    'team': display_name,
                    'their_odds': odds,
                    'our_odds': our_odds,
                    'their_stake': stake,
                    'our_bet_size': bet_amount,
                    'potential_profit': potential_profit,
                    'roi_percent': (potential_profit / bet_amount) * 100 if bet_amount > 0 else 0
                }
                
                opportunities.append(opportunity)
                
                print(f"  🎯 OPPORTUNITY: {display_name}")
                print(f"     Their bet: ${stake:,} at {odds:+d}")
                print(f"     Our bet: ${bet_amount:,} at {our_odds:+d}")
                print(f"     Potential profit: ${potential_profit:,.2f} ({opportunity['roi_percent']:.1f}%)")
        
        return opportunities
    
    def scan_all_markets(self):
        """Main scanning function"""
        print("🚀 Starting ProphetX Market Scan")
        print("=" * 50)
        
        # Get all available markets
        markets = self.get_markets()
        
        if not markets:
            print("No markets found. Check your API key and connection.")
            return
        
        all_opportunities = []
        
        # Scan each market
        for i, market in enumerate(markets[:5], 1):  # Limit to first 5 markets for testing
            market_id = market.get('id')
            print(f"\n[{i}/{min(len(markets), 5)}] Scanning market: {market_id}")
            
            # Get detailed market data
            market_details = self.get_market_details(market_id)
            
            if market_details:
                # Find opportunities
                opportunities = self.find_undercut_opportunities(market_details)
                all_opportunities.extend(opportunities)
            
            # Be nice to the API
            import time
            time.sleep(1)
        
        # Summary
        print("\n" + "=" * 50)
        print("📋 SCAN SUMMARY")
        print("=" * 50)
        
        if all_opportunities:
            print(f"🎯 Found {len(all_opportunities)} undercut opportunities!")
            
            # Sort by potential profit
            all_opportunities.sort(key=lambda x: x['potential_profit'], reverse=True)
            
            print(f"\n🏆 TOP OPPORTUNITIES:")
            for i, opp in enumerate(all_opportunities[:5], 1):
                print(f"{i}. {opp['game']} - {opp['team']}")
                print(f"   Bet ${opp['our_bet_size']:,} at {opp['our_odds']:+d} → ${opp['potential_profit']:,.2f} profit")
                print(f"   (Undercutting ${opp['their_stake']:,} bet at {opp['their_odds']:+d})")
                print()
        else:
            print("❌ No opportunities found.")
            print("This could mean:")
            print("- No large bets (>${:,}) are available".format(self.min_stake_to_undercut))
            print("- Markets are efficient right now")
            print("- Try again during peak betting hours")
        
        return all_opportunities

def main():
    print("ProphetX Simple Market Scanner")
    print("This script will scan for undercut opportunities WITHOUT placing any bets")
    print()
    
    # Get API key
    api_key = input("Enter your ProphetX Sandbox API key: ").strip()
    
    if not api_key:
        print("❌ API key required!")
        return
    
    # Create scanner
    scanner = SimpleProphetXScanner(api_key)
    
    # Run scan
    try:
        opportunities = scanner.scan_all_markets()
        
        # Save results to file for review
        if opportunities:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"opportunities_{timestamp}.json"
            
            with open(filename, 'w') as f:
                json.dump(opportunities, f, indent=2, default=str)
            
            print(f"💾 Results saved to: {filename}")
        
    except KeyboardInterrupt:
        print("\n🛑 Scan interrupted by user")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")

if __name__ == "__main__":
    main()