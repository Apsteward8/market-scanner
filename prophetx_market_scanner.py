#!/usr/bin/env python3
"""
ProphetX Market Scanner
Scans tournaments → events → markets for undercut opportunities
"""

import requests
import json
import time
from datetime import datetime
from typing import List, Dict, Optional
from prophetx_auth import ProphetXAuth

class ProphetXMarketScanner:
    def __init__(self, access_key: str, secret_key: str, sandbox: bool = True):
        """
        Initialize the market scanner
        
        Args:
            access_key: ProphetX access key
            secret_key: ProphetX secret key
            sandbox: Use sandbox environment
        """
        self.auth = ProphetXAuth(access_key, secret_key, sandbox)
        
        if sandbox:
            self.base_url = "https://api-ss-sandbox.betprophet.co"
        else:
            self.base_url = "https://api-ss.betprophet.co"
        
        # Configuration
        self.min_stake_threshold = 5000  # Only look at bets >= $5k
        self.undercut_amount = 1  # Improve odds by 1
        self.target_sports = ["Baseball", "American Football", "Basketball"]  # Focus on main sports
        
    def get_tournaments(self) -> List[Dict]:
        """
        Get all available tournaments/leagues
        
        Returns:
            List of tournament dictionaries
        """
        print("🏆 Fetching tournaments...")
        
        url = f"{self.base_url}/partner/mm/get_tournaments"
        headers = self.auth.get_auth_headers()
        
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                tournaments = data.get('data', {}).get('tournaments', [])
                
                # Filter for target sports
                filtered_tournaments = [
                    t for t in tournaments 
                    if t.get('sport', {}).get('name', '') in self.target_sports
                ]
                
                print(f"✅ Found {len(tournaments)} total tournaments, {len(filtered_tournaments)} in target sports")
                
                # Log tournaments for debugging
                for tournament in filtered_tournaments:
                    sport_name = tournament.get('sport', {}).get('name', 'Unknown')
                    print(f"   📋 {tournament.get('name', 'Unknown')} ({sport_name}) - ID: {tournament.get('id')}")
                
                return filtered_tournaments
                
            else:
                print(f"❌ Error fetching tournaments: {response.status_code}")
                print(f"Response: {response.text}")
                return []
                
        except Exception as e:
            print(f"💥 Exception fetching tournaments: {e}")
            return []
    
    def get_events_for_tournament(self, tournament_id: int) -> List[Dict]:
        """
        Get all events/games for a specific tournament
        
        Args:
            tournament_id: Tournament ID to fetch events for
            
        Returns:
            List of event dictionaries
        """
        url = f"{self.base_url}/partner/mm/get_sport_events"
        headers = self.auth.get_auth_headers()
        params = {"tournament_id": tournament_id}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                events = data.get('data', {}).get('sport_events', [])
                
                # Filter for upcoming events only
                upcoming_events = [
                    event for event in events 
                    if event.get('status') == 'not_started'
                ]
                
                return upcoming_events
                
            else:
                print(f"❌ Error fetching events for tournament {tournament_id}: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"💥 Exception fetching events for tournament {tournament_id}: {e}")
            return []
    
    def get_markets_for_event(self, event_id: int) -> Optional[Dict]:
        """
        Get markets for a specific event
        
        Args:
            event_id: Event ID to fetch markets for
            
        Returns:
            Markets data dictionary or None
        """
        url = f"{self.base_url}/partner/v2/mm/get_markets"
        headers = self.auth.get_auth_headers()
        params = {"event_id": event_id}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error fetching markets for event {event_id}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"💥 Exception fetching markets for event {event_id}: {e}")
            return None
    
    def analyze_market_for_opportunities(self, market_data: Dict, event_info: Dict) -> List[Dict]:
        """
        Analyze a market for undercut opportunities
        
        Args:
            market_data: Market data from API
            event_info: Event information (teams, etc.)
            
        Returns:
            List of opportunity dictionaries
        """
        opportunities = []
        
        if not market_data or 'data' not in market_data:
            return opportunities
        
        event_data = market_data['data']
        markets = event_data.get('markets', [])
        
        # Event details for logging
        event_name = event_info.get('display_name', 'Unknown Event')
        
        for market in markets:
            market_name = market.get('name', 'Unknown Market')
            market_type = market.get('type', 'unknown')
            
            # Focus on main markets (moneyline, spreads, totals)
            if market_type not in ['moneyline', 'spread', 'total']:
                continue
            
            selections = market.get('selections', [])
            
            for selection_group in selections:
                if not isinstance(selection_group, list):
                    continue
                
                for selection in selection_group:
                    stake = selection.get('stake', 0)
                    odds = selection.get('odds', 0)
                    display_name = selection.get('display_name', '')
                    competitor_name = selection.get('name', '')
                    
                    # Only analyze high-stake bets
                    if stake >= self.min_stake_threshold:
                        
                        # Calculate our undercut odds
                        if odds > 0:  # Positive odds (underdog)
                            our_odds = odds - self.undercut_amount
                        else:  # Negative odds (favorite)
                            our_odds = odds + self.undercut_amount
                        
                        # Calculate potential bet size and profit
                        max_bet_size = min(stake * 0.5, 1000)  # Bet up to 50% of their stake, max $1000
                        
                        if our_odds > 0:
                            potential_win = max_bet_size * (our_odds / 100)
                        else:
                            potential_win = max_bet_size * (100 / abs(our_odds))
                        
                        potential_profit = potential_win - max_bet_size
                        roi_percent = (potential_profit / max_bet_size) * 100 if max_bet_size > 0 else 0
                        
                        opportunity = {
                            'event_id': event_data.get('event_id'),
                            'event_name': event_name,
                            'market_name': market_name,
                            'market_type': market_type,
                            'market_id': market.get('id'),
                            'selection_info': {
                                'competitor_id': selection.get('competitor_id'),
                                'outcome_id': selection.get('outcome_id'),
                                'line_id': selection.get('line_id'),
                                'line': selection.get('line', 0)
                            },
                            'team_name': competitor_name,
                            'display_name': display_name,
                            'their_odds': odds,
                            'our_odds': our_odds,
                            'their_stake': stake,
                            'their_value': selection.get('value', 0),
                            'our_bet_size': max_bet_size,
                            'potential_profit': potential_profit,
                            'roi_percent': roi_percent,
                            'updated_at': selection.get('updated_at'),
                            'value_score': stake / 1000  # Simple scoring metric
                        }
                        
                        opportunities.append(opportunity)
        
        return opportunities
    
    def scan_all_markets(self) -> List[Dict]:
        """
        Scan all available markets for opportunities
        
        Returns:
            List of all opportunities found
        """
        print("🚀 Starting comprehensive market scan...")
        print("=" * 60)
        
        all_opportunities = []
        
        # Step 1: Get all tournaments
        tournaments = self.get_tournaments()
        
        if not tournaments:
            print("❌ No tournaments found!")
            return []
        
        # Step 2: Scan each tournament
        for tournament in tournaments:
            tournament_id = tournament.get('id')
            tournament_name = tournament.get('name', 'Unknown')
            sport_name = tournament.get('sport', {}).get('name', 'Unknown')
            
            print(f"\n🏟️  Scanning {tournament_name} ({sport_name})...")
            
            # Get events for this tournament
            events = self.get_events_for_tournament(tournament_id)
            
            if not events:
                print(f"   📅 No upcoming events in {tournament_name}")
                continue
            
            print(f"   📅 Found {len(events)} upcoming events")
            
            # Step 3: Scan each event
            for i, event in enumerate(events[:10], 1):  # Limit to 10 events per tournament for testing
                event_id = event.get('event_id')
                event_name = event.get('display_name', 'Unknown Event')
                scheduled_time = event.get('scheduled', '')
                
                print(f"   [{i}/{min(len(events), 10)}] Analyzing: {event_name}")
                
                # Get markets for this event
                markets_data = self.get_markets_for_event(event_id)
                
                if markets_data:
                    # Analyze for opportunities
                    opportunities = self.analyze_market_for_opportunities(markets_data, event)
                    
                    if opportunities:
                        print(f"      🎯 Found {len(opportunities)} opportunities!")
                        all_opportunities.extend(opportunities)
                        
                        # Show top opportunity for this event
                        top_opp = max(opportunities, key=lambda x: x['value_score'])
                        print(f"      💰 Best: {top_opp['display_name']} - ${top_opp['potential_profit']:.2f} profit")
                    else:
                        print(f"      ❌ No opportunities")
                else:
                    print(f"      ❌ No markets available")
                
                # Rate limiting
                time.sleep(0.5)
            
            # Rate limiting between tournaments
            time.sleep(1)
        
        return all_opportunities
    
    def print_opportunities_summary(self, opportunities: List[Dict]):
        """
        Print a formatted summary of opportunities
        """
        if not opportunities:
            print("\n❌ No opportunities found across all markets!")
            print("Possible reasons:")
            print("- No large bets (>$5k) currently available")
            print("- Markets are efficient right now")
            print("- Try again during peak betting hours")
            return
        
        print(f"\n🎯 FOUND {len(opportunities)} TOTAL OPPORTUNITIES!")
        print("=" * 60)
        
        # Sort by value score (highest first)
        opportunities.sort(key=lambda x: x['value_score'], reverse=True)
        
        print(f"\n🏆 TOP 10 OPPORTUNITIES:")
        print("-" * 60)
        
        for i, opp in enumerate(opportunities[:10], 1):
            print(f"{i:2d}. {opp['event_name']}")
            print(f"    Market: {opp['market_name']} - {opp['display_name']}")
            print(f"    Their bet: ${opp['their_stake']:,} at {opp['their_odds']:+d}")
            print(f"    Our bet: ${opp['our_bet_size']:,} at {opp['our_odds']:+d}")
            print(f"    Profit: ${opp['potential_profit']:,.2f} ({opp['roi_percent']:.1f}% ROI)")
            print(f"    Value Score: {opp['value_score']:.1f}")
            print()
        
        # Summary stats
        total_potential_profit = sum(opp['potential_profit'] for opp in opportunities)
        total_risk = sum(opp['our_bet_size'] for opp in opportunities)
        avg_roi = sum(opp['roi_percent'] for opp in opportunities) / len(opportunities)
        
        print(f"📊 SUMMARY STATISTICS:")
        print(f"   💰 Total Potential Profit: ${total_potential_profit:,.2f}")
        print(f"   🎲 Total Risk Required: ${total_risk:,.2f}")
        print(f"   📈 Average ROI: {avg_roi:.1f}%")
        print(f"   🎯 Opportunities per $1k risk: {len(opportunities) / (total_risk / 1000):.1f}")

def main():
    """
    Main scanning function
    """
    print("ProphetX Comprehensive Market Scanner")
    print("This will scan ALL tournaments and events for opportunities")
    print("=" * 60)
    
    # Get credentials
    access_key = input("Enter your ProphetX access key: ").strip()
    secret_key = input("Enter your ProphetX secret key: ").strip()
    
    if not access_key or not secret_key:
        print("❌ Both access key and secret key are required!")
        return
    
    # Initialize scanner
    scanner = ProphetXMarketScanner(access_key, secret_key, sandbox=True)
    
    try:
        # Run comprehensive scan
        start_time = datetime.now()
        opportunities = scanner.scan_all_markets()
        end_time = datetime.now()
        
        # Print results
        scanner.print_opportunities_summary(opportunities)
        
        print(f"\n⏱️  Scan completed in {(end_time - start_time).total_seconds():.1f} seconds")
        
        # Save results
        if opportunities:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"prophetx_opportunities_{timestamp}.json"
            
            with open(filename, 'w') as f:
                json.dump(opportunities, f, indent=2, default=str)
            
            print(f"💾 Results saved to: {filename}")
        
    except KeyboardInterrupt:
        print("\n🛑 Scan interrupted by user")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")

if __name__ == "__main__":
    main()