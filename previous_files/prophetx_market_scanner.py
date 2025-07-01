#!/usr/bin/env python3
"""
ProphetX Market Scanner
Scans tournaments → events → markets for undercut opportunities
Includes bet placement functionality
"""

import requests
import json
import time
from datetime import datetime
from typing import List, Dict, Optional
from prophetx_auth import ProphetXAuth
from prophetx_config_manager import ConfigManager, ProphetXConfig
from prophetx_odds_validator import ProphetXOddsValidator
from prophetx_bet_placer import ProphetXBetPlacer

class ProphetXMarketScanner:
    def __init__(self, config: ProphetXConfig):
        """
        Initialize the market scanner
        
        Args:
            config: ProphetXConfig object with credentials and settings
        """
        self.config = config
        self.auth = ProphetXAuth(config.access_key, config.secret_key, config.sandbox)
        self.odds_validator = ProphetXOddsValidator()
        self.bet_placer = ProphetXBetPlacer(self.auth, config.sandbox)
        
        if config.sandbox:
            self.base_url = "https://api-ss-sandbox.betprophet.co"
        else:
            self.base_url = "https://api-ss.betprophet.co"
        
        # Use configuration from config object
        self.min_stake_threshold = config.min_stake_threshold
        self.undercut_amount = config.undercut_amount
        self.target_sports = config.target_sports
        
        # Bet placement settings
        self.enable_bet_placement = False
        self.bet_placement_dry_run = True
        self.bet_size = 5.0  # Default $5 test bets
    
    def configure_bet_placement(self, enabled: bool = True, dry_run: bool = True, bet_size: float = 5.0):
        """
        Configure bet placement settings
        
        Args:
            enabled: Enable bet placement
            dry_run: Use dry run mode (simulate bets)
            bet_size: Bet size in dollars
        """
        self.enable_bet_placement = enabled
        self.bet_placement_dry_run = dry_run
        self.bet_size = bet_size
        
        self.bet_placer.set_dry_run(dry_run)
        self.bet_placer.set_default_bet_size(bet_size)
        
        print(f"🎯 Bet placement configured:")
        print(f"   Enabled: {enabled}")
        print(f"   Dry run: {dry_run}")
        print(f"   Bet size: ${bet_size}")
    
    def place_bets_for_opportunities(self, opportunities: List[Dict]) -> Optional[Dict]:
        """
        Place bets for a list of opportunities
        
        Args:
            opportunities: List of opportunities to bet on
            
        Returns:
            dict: Bet placement summary or None if not enabled
        """
        if not self.enable_bet_placement or not opportunities:
            return None
        
        print(f"\n💰 PLACING BETS FOR {len(opportunities)} OPPORTUNITIES")
        print("=" * 60)
        
        return self.bet_placer.place_multiple_bets(opportunities, self.bet_size)
    
    def convert_liquidity_to_original_bet(self, selection: Dict) -> Dict:
        """
        Convert liquidity data to original bet information
        
        When we see "Jets +101 with $500 liquidity", this means:
        - Someone originally bet "Steelers -101 for $500" 
        - We want to analyze and follow that original bet
        
        Args:
            selection: The selection showing liquidity (e.g., Jets +101)
            
        Returns:
            dict: Original bet information
        """
        liquidity_odds = selection.get('odds', 0)
        liquidity_team = selection.get('name', '')
        liquidity_stake = selection.get('stake', 0)
        
        # Convert liquidity odds to original bet odds
        # If we see Jets +101 liquidity, original bet was Steelers -101
        if liquidity_odds > 0:
            # Liquidity shows positive odds, original bet was negative
            original_bet_odds = -liquidity_odds
        else:
            # Liquidity shows negative odds, original bet was positive  
            original_bet_odds = abs(liquidity_odds)
        
        return {
            'original_bet_odds': original_bet_odds,
            'original_bet_stake': liquidity_stake,
            'original_bet_team': f"Opposite of {liquidity_team}",  # We'll fix this with proper team lookup
            'liquidity_team': liquidity_team,
            'liquidity_odds': liquidity_odds,
            'liquidity_stake': liquidity_stake
        }
    
    def find_opposite_within_line_group(self, current_selection: Dict, line_selections: List) -> Optional[Dict]:
        """
        Find the opposite outcome within the SAME line group
        
        This ensures we match the correct line:
        - over 6.5 matches with under 6.5 (same line)
        - NOT with under 5.5 (different line)
        
        Args:
            current_selection: The selection where we see liquidity
            line_selections: Selection groups from the SAME market line only
            
        Returns:
            dict: Opposite outcome information from same line
        """
        current_competitor_id = current_selection.get('competitor_id')
        current_outcome_id = current_selection.get('outcome_id')
        current_name = current_selection.get('name', '')
        
        print(f"               🔍 Looking for opposite of: {current_name} (within same line)")
        print(f"                  competitor_id: {current_competitor_id}")
        print(f"                  outcome_id: {current_outcome_id}")
        
        # Look through selections in THIS line group only
        for selection_group in line_selections:
            if not isinstance(selection_group, list):
                continue
                
            for selection in selection_group:
                selection_competitor_id = selection.get('competitor_id')
                selection_outcome_id = selection.get('outcome_id')
                selection_name = selection.get('name', '')
                
                # Skip the current selection
                if (selection_competitor_id == current_competitor_id and 
                    selection_outcome_id == current_outcome_id):
                    continue
                
                # CASE 1: Team-based markets (different competitor_id)
                if current_competitor_id is not None and selection_competitor_id is not None:
                    if selection_competitor_id != current_competitor_id:
                        print(f"               ✅ Found opposite team: {selection_name} (competitor_id: {selection_competitor_id})")
                        return {
                            'line_id': selection.get('line_id'),
                            'name': selection_name,
                            'competitor_id': selection_competitor_id,
                            'outcome_id': selection_outcome_id
                        }
                
                # CASE 2: Prop markets (different outcome_id, no competitor_id)
                elif current_competitor_id is None and selection_competitor_id is None:
                    if selection_outcome_id != current_outcome_id:
                        print(f"               ✅ Found opposite outcome: {selection_name} (outcome_id: {selection_outcome_id})")
                        return {
                            'line_id': selection.get('line_id'),
                            'name': selection_name,
                            'competitor_id': None,
                            'outcome_id': selection_outcome_id
                        }
                
                # CASE 3: Over/Under logic (backup for props)
                elif self.is_opposite_over_under(current_name, selection_name):
                    print(f"               ✅ Found opposite over/under: {selection_name}")
                    return {
                        'line_id': selection.get('line_id'),
                        'name': selection_name,
                        'competitor_id': selection_competitor_id,
                        'outcome_id': selection_outcome_id
                    }
        
        print(f"               ❌ Could not find opposite for: {current_name} within same line")
        return None
    
    def find_opposite_team_info(self, market: Dict, current_selection: Dict, all_selections: List) -> Optional[Dict]:
        """
        Find the opposite team/outcome information in the same market
        
        Handles both:
        - Team markets (different competitor_id) 
        - Prop markets (different outcome_id for over/under)
        
        Args:
            market: Market data containing all selections
            current_selection: The selection where we see liquidity
            all_selections: All selection groups from this market
            
        Returns:
            dict: Opposite team/outcome information including line_id and name
        """
        current_competitor_id = current_selection.get('competitor_id')
        current_outcome_id = current_selection.get('outcome_id')
        current_name = current_selection.get('name', '')
        
        print(f"         🔍 Looking for opposite of: {current_name}")
        print(f"            competitor_id: {current_competitor_id}")
        print(f"            outcome_id: {current_outcome_id}")
        
        # Look through all selection groups in this market
        for selection_group in all_selections:
            if not isinstance(selection_group, list):
                continue
                
            for selection in selection_group:
                selection_competitor_id = selection.get('competitor_id')
                selection_outcome_id = selection.get('outcome_id')
                selection_name = selection.get('name', '')
                
                # Skip the current selection
                if (selection_competitor_id == current_competitor_id and 
                    selection_outcome_id == current_outcome_id):
                    continue
                
                # CASE 1: Team-based markets (different competitor_id)
                if current_competitor_id is not None and selection_competitor_id is not None:
                    if selection_competitor_id != current_competitor_id:
                        print(f"         ✅ Found opposite team: {selection_name} (competitor_id: {selection_competitor_id})")
                        return {
                            'line_id': selection.get('line_id'),
                            'name': selection_name,
                            'competitor_id': selection_competitor_id,
                            'outcome_id': selection_outcome_id
                        }
                
                # CASE 2: Prop markets (different outcome_id, no competitor_id)
                elif current_competitor_id is None and selection_competitor_id is None:
                    if selection_outcome_id != current_outcome_id:
                        print(f"         ✅ Found opposite outcome: {selection_name} (outcome_id: {selection_outcome_id})")
                        return {
                            'line_id': selection.get('line_id'),
                            'name': selection_name,
                            'competitor_id': None,
                            'outcome_id': selection_outcome_id
                        }
                
                # CASE 3: Over/Under logic (backup for props)
                elif self.is_opposite_over_under(current_name, selection_name):
                    print(f"         ✅ Found opposite over/under: {selection_name}")
                    return {
                        'line_id': selection.get('line_id'),
                        'name': selection_name,
                        'competitor_id': selection_competitor_id,
                        'outcome_id': selection_outcome_id
                    }
        
        print(f"         ❌ Could not find opposite for: {current_name}")
        return None
    
    def is_opposite_over_under(self, name1: str, name2: str) -> bool:
        """
        Check if two names are opposite over/under bets
        
        Args:
            name1: First selection name
            name2: Second selection name
            
        Returns:
            bool: True if they are opposites (over/under)
        """
        name1_lower = name1.lower()
        name2_lower = name2.lower()
        
        # Check for over/under opposites
        if 'over' in name1_lower and 'under' in name2_lower:
            return True
        if 'under' in name1_lower and 'over' in name2_lower:
            return True
            
        # Could add more logic for other prop types
        # e.g., "yes"/"no", "team a"/"team b", etc.
        
        return False
    
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
            
            # COMPREHENSIVE SCAN - analyze ALL market types
            # Removed restriction: if market_type not in ['moneyline', 'spread', 'total']: continue
            print(f"      📊 Scanning market: {market_name} ({market_type})")
            
            # Handle different selection structures
            selection_groups = []
            
            # Standard structure (moneyline, spread, etc.)
            if 'selections' in market:
                selections = market.get('selections', [])
                # For standard markets, all selections are in one group
                selection_groups.append({
                    'selections': selections,
                    'line_info': {'name': market_name, 'line': 0}
                })
                print(f"         📋 Found selections directly (standard structure)")
                
            # Player props structure with market_lines
            elif 'market_lines' in market:
                print(f"         📋 Found market_lines structure (player props)")
                market_lines = market.get('market_lines', [])
                for market_line in market_lines:
                    line_selections = market_line.get('selections', [])
                    if line_selections:
                        # Keep each line's selections separate
                        selection_groups.append({
                            'selections': line_selections,
                            'line_info': {
                                'name': market_line.get('name', 'Unknown Line'),
                                'line': market_line.get('line', 0)
                            }
                        })
                        print(f"         📋 Added line group: {market_line.get('name', 'Unknown')} (line: {market_line.get('line', 0)})")
            
            if not selection_groups:
                print(f"         ❌ No selection groups found in market structure")
                continue
                
            print(f"         📊 Total line groups to analyze: {len(selection_groups)}")
            
            # Analyze each line group separately
            for group_idx, selection_group in enumerate(selection_groups):
                selections = selection_group['selections']
                line_info = selection_group['line_info']
                
                print(f"         📊 Analyzing line group {group_idx + 1}: {line_info['name']}")
                
                for selection_list in selections:
                    if not isinstance(selection_list, list):
                        continue
                    
                    for selection in selection_list:
                        stake = selection.get('stake', 0)
                        
                        # Only analyze high-stake bets
                        if stake >= self.min_stake_threshold:
                            
                            # STEP 1: Convert liquidity to original bet information
                            original_bet_info = self.convert_liquidity_to_original_bet(selection)
                            
                            print(f"            📊 Analyzing large bet in {line_info['name']}:")
                            print(f"               Liquidity: {original_bet_info['liquidity_team']} {original_bet_info['liquidity_odds']:+d} (${stake:,})")
                            print(f"               Original bet: {original_bet_info['original_bet_team']} {original_bet_info['original_bet_odds']:+d} for ${stake:,}")
                            
                            # STEP 2: Find opposite team info WITHIN THE SAME LINE GROUP
                            opposite_team_info = self.find_opposite_within_line_group(selection, selections)
                            if opposite_team_info is None:
                                print(f"               ❌ Could not find opposite within same line group")
                                continue
                            
                            # Update original bet team name with actual team name
                            original_bet_team_name = opposite_team_info['name']
                            current_selection_name = selection.get('name', '')
                            
                            print(f"               Following: {original_bet_team_name} {original_bet_info['original_bet_odds']:+d} for ${stake:,}")
                            print(f"               (Liquidity on {current_selection_name} = someone bet {original_bet_team_name})")
                            
                            # STEP 3: Calculate our undercut odds (undercut the ORIGINAL bet, not liquidity)
                            our_odds = self.odds_validator.calculate_undercut_odds(
                                original_bet_info['original_bet_odds'],  # Use original bet odds for undercutting
                                self.undercut_amount
                            )
                            
                            if our_odds is None:
                                print(f"               ❌ Could not calculate valid undercut for {original_bet_info['original_bet_odds']:+d}")
                                continue
                            
                            print(f"               Our bet: {original_bet_team_name} {our_odds:+d} (undercutting {original_bet_info['original_bet_odds']:+d})")
                            
                            # STEP 4: Calculate bet sizing
                            max_bet_size = min(stake * 0.5, self.config.max_bet_size)
                            
                            # STEP 5: Calculate metrics (for display purposes)
                            profit_metrics = self.odds_validator.calculate_profit_metrics(
                                original_bet_info['original_bet_odds'], our_odds, max_bet_size
                            )
                            
                            # STEP 6: Get explanation of the undercut strategy
                            undercut_explanation = self.odds_validator.explain_undercut(
                                original_bet_info['original_bet_odds'], our_odds
                            )
                            
                            # STEP 7: Create opportunity focused on ORIGINAL BET
                            opportunity = {
                                'event_id': event_data.get('event_id'),
                                'event_name': event_name,
                                'market_name': f"{market_name} - {line_info['name']}",  # Include line info
                                'market_type': market_type,
                                'market_id': market.get('id'),
                                
                                # Original bet information (what we're following)
                                'original_bet': {
                                    'team_name': original_bet_team_name,
                                    'odds': original_bet_info['original_bet_odds'],
                                    'stake': stake,
                                    'display': f"{original_bet_team_name} {original_bet_info['original_bet_odds']:+d} for ${stake:,}"
                                },
                                
                                # Our follow bet information
                                'our_bet': {
                                    'team_name': original_bet_team_name,  # Same team (following)
                                    'odds': our_odds,
                                    'stake': max_bet_size,
                                    'display': f"{original_bet_team_name} {our_odds:+d} for ${max_bet_size:,}"
                                },
                                
                                # Bet placement info
                                'bet_placement': {
                                    'line_id': opposite_team_info['line_id'],
                                    'competitor_id': opposite_team_info['competitor_id'],
                                    'outcome_id': opposite_team_info['outcome_id'],
                                    'odds': our_odds,
                                    'stake': max_bet_size
                                },
                                
                                # Analysis metrics
                                'analysis': {
                                    'value_score': stake / 1000,
                                    'potential_profit': profit_metrics['potential_profit'],
                                    'potential_win': profit_metrics['potential_win'],
                                    'roi_percent': profit_metrics['roi_percent'],
                                    'undercut_explanation': undercut_explanation,
                                    'follow_money_logic': f"Following ${stake:,} bet: {original_bet_team_name} {original_bet_info['original_bet_odds']:+d} → {our_odds:+d}"
                                },
                                
                                # Metadata
                                'updated_at': selection.get('updated_at'),
                                'is_valid_follow': True
                            }
                            
                            opportunities.append(opportunity)
        
        return opportunities
    
    def scan_specific_tournament(self, tournament_id: int, limit_events: int = None) -> List[Dict]:
        """
        Scan a specific tournament for opportunities
        
        Args:
            tournament_id: Specific tournament ID to scan
            limit_events: Maximum number of events to scan (None for all)
            
        Returns:
            List of opportunities found
        """
        print(f"🎯 Scanning tournament ID: {tournament_id}")
        print("=" * 60)
        
        all_opportunities = []
        
        # Get events for this specific tournament
        events = self.get_events_for_tournament(tournament_id)
        
        if not events:
            print(f"❌ No upcoming events found for tournament {tournament_id}")
            return []
        
        events_to_scan = events if limit_events is None else events[:limit_events]
        print(f"📅 Found {len(events)} total events, scanning {len(events_to_scan)}")
        
        # Scan each event
        for i, event in enumerate(events_to_scan, 1):
            event_id = event.get('event_id')
            event_name = event.get('display_name', 'Unknown Event')
            scheduled_time = event.get('scheduled', '')
            tournament_name = event.get('tournament_name', 'Unknown Tournament')
            
            print(f"\n[{i}/{len(events_to_scan)}] 🏈 {tournament_name}: {event_name}")
            print(f"    ⏰ Scheduled: {scheduled_time}")
            
            # Get markets for this event
            markets_data = self.get_markets_for_event(event_id)
            
            if markets_data:
                # Analyze for opportunities
                opportunities = self.analyze_market_for_opportunities(markets_data, event)
                
                if opportunities:
                    print(f"    🎯 Found {len(opportunities)} opportunities!")
                    all_opportunities.extend(opportunities)
                    
                    # Show all opportunities for this event
                    for opp in opportunities:
                        original_bet = opp['original_bet']['display']
                        our_bet = opp['our_bet']['display']
                        print(f"       💰 Original bet: {original_bet} (value score: {opp['analysis']['value_score']:.1f})")
                        print(f"          Our follow bet: {our_bet}")
                        print(f"          Strategy: {opp['analysis']['follow_money_logic']}")
                        print(f"          Undercut: {opp['analysis']['undercut_explanation']}")
                else:
                    print(f"    ❌ No opportunities (no bets ≥ ${self.min_stake_threshold:,})")
            else:
                print(f"    ❌ No markets available")
            
            # Rate limiting
            time.sleep(0.5)
        
        # Place bets for all opportunities found if enabled
        if all_opportunities:
            bet_summary = self.place_bets_for_opportunities(all_opportunities)
            if bet_summary:
                print(f"\n🎯 Bet placement summary for tournament {tournament_id}:")
                print(f"   Total opportunities: {len(all_opportunities)}")
                print(f"   Bets attempted: {bet_summary['total']}")
                print(f"   Successful: {bet_summary['successful']}")
                print(f"   Failed: {bet_summary['failed']}")
        
        return all_opportunities
    
    def scan_specific_event(self, event_id: int) -> List[Dict]:
        """
        Scan a specific event for opportunities
        
        Args:
            event_id: Specific event ID to scan
            
        Returns:
            List of opportunities found
        """
        print(f"🎯 Scanning event ID: {event_id}")
        print("=" * 60)
        
        # Get markets for this specific event
        markets_data = self.get_markets_for_event(event_id)
        
        if not markets_data:
            print(f"❌ No markets found for event {event_id}")
            return []
        
        # Create dummy event info for analysis
        event_info = {
            'event_id': event_id,
            'display_name': f'Event {event_id}'
        }
        
        # Try to extract real event info from markets data
        if 'data' in markets_data and 'event_id' in markets_data['data']:
            event_info['event_id'] = markets_data['data']['event_id']
        
        print(f"📊 Analyzing markets for event: {event_info['display_name']}")
        
        # Analyze for opportunities
        opportunities = self.analyze_market_for_opportunities(markets_data, event_info)
        
        if opportunities:
            print(f"🎯 Found {len(opportunities)} opportunities!")
            
            # Show detailed breakdown
            for i, opp in enumerate(opportunities, 1):
                original_bet = opp['original_bet']['display']
                our_bet = opp['our_bet']['display']
                print(f"\n{i}. {opp['market_name']} - Following Large Bet")
                print(f"   Original bet: {original_bet} (smart money)")
                print(f"   Our follow bet: {our_bet}")
                print(f"   Strategy: {opp['analysis']['follow_money_logic']}")
                print(f"   Undercut explanation: {opp['analysis']['undercut_explanation']}")
                print(f"   Value score: {opp['analysis']['value_score']:.1f}")
            
            # Place bets if enabled
            bet_summary = self.place_bets_for_opportunities(opportunities)
            if bet_summary:
                print(f"\n🎯 Bet placement completed!")
                
        else:
            print(f"❌ No opportunities found (no bets ≥ ${self.min_stake_threshold:,})")
        
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
            
            # Step 3: Scan each event - COMPREHENSIVE (all events)
            for i, event in enumerate(events, 1):  # Removed [:5] limit - scan ALL events
                event_id = event.get('event_id')
                event_name = event.get('display_name', 'Unknown Event')
                scheduled_time = event.get('scheduled', '')
                
                print(f"   [{i}/{len(events)}] Analyzing: {event_name}")
                
                # Get markets for this event
                markets_data = self.get_markets_for_event(event_id)
                
                if markets_data:
                    # Analyze for opportunities
                    opportunities = self.analyze_market_for_opportunities(markets_data, event)
                    
                    if opportunities:
                        print(f"      🎯 Found {len(opportunities)} opportunities!")
                        all_opportunities.extend(opportunities)
                        
                        # Show top opportunity for this event
                        top_opp = max(opportunities, key=lambda x: x['analysis']['value_score'])
                        original_bet = top_opp['original_bet']['display']
                        print(f"      💰 Best: {original_bet}")
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
        opportunities.sort(key=lambda x: x['analysis']['value_score'], reverse=True)
        
        print(f"\n🏆 TOP 10 FOLLOW OPPORTUNITIES:")
        print("-" * 60)
        
        for i, opp in enumerate(opportunities[:10], 1):
            original_bet = opp['original_bet']['display']
            our_bet = opp['our_bet']['display']
            print(f"{i:2d}. {opp['event_name']}")
            print(f"    Market: {opp['market_name']}")
            print(f"    Original bet: {original_bet} (smart money)")
            print(f"    Our follow bet: {our_bet}")
            print(f"    Strategy: {opp['analysis']['follow_money_logic']}")
            print(f"    Value Score: {opp['analysis']['value_score']:.1f} (based on original stake)")
            print()
        
        # Summary stats
        total_theoretical_profit = sum(opp['analysis']['potential_profit'] for opp in opportunities)
        total_risk = sum(opp['our_bet']['stake'] for opp in opportunities)
        avg_original_stake = sum(opp['original_bet']['stake'] for opp in opportunities) / len(opportunities)
        
        print(f"📊 SUMMARY STATISTICS:")
        print(f"   🎯 Total Follow Opportunities: {len(opportunities)}")
        print(f"   💰 Average Original Bet Size: ${avg_original_stake:,.0f}")
        print(f"   🎲 Our Total Risk: ${total_risk:,.2f}")
        print(f"   📈 Theoretical Profit: ${total_theoretical_profit:,.2f} (display only)")
        print(f"   🏆 Large Bets (>$10k): {len([o for o in opportunities if o['original_bet']['stake'] >= 10000])}")
        print()
        print("💡 FOLLOW THE MONEY STRATEGY:")
        print("   • Large stakes indicate smart money/insider information")
        print("   • We follow large bets by betting the SAME side as the large bettor")
        print("   • We accept worse odds to get priority queue position")
        print("   • Profit comes from being first to get matched when action flows")
        print("   • COMPREHENSIVE scan includes ALL market types: props, alternatives, futures, etc.")

def get_bet_placement_config():
    """
    Get bet placement configuration from user
    
    Returns:
        dict: Bet placement configuration
    """
    print("\n🎯 BET PLACEMENT CONFIGURATION:")
    
    # Ask if user wants to enable bet placement
    enable = input("Enable bet placement? (y/n): ").strip().lower()
    if enable not in ['y', 'yes']:
        return {'enabled': False}
    
    # Ask about dry run mode
    print("\n🧪 SAFETY OPTIONS:")
    print("   Dry run mode: Simulates bets without actually placing them (RECOMMENDED for testing)")
    print("   Live mode: Actually places real bets")
    
    dry_run = input("Use dry run mode? (y/n) [RECOMMENDED: y]: ").strip().lower()
    if dry_run == '':
        dry_run = 'y'  # Default to dry run
    
    dry_run_enabled = dry_run in ['y', 'yes']
    
    # Ask about bet size
    while True:
        bet_size_input = input("Bet size in dollars [default: $5]: ").strip()
        if bet_size_input == '':
            bet_size = 5.0
            break
        try:
            bet_size = float(bet_size_input)
            if bet_size <= 0:
                print("❌ Bet size must be positive")
                continue
            break
        except ValueError:
            print("❌ Invalid bet size. Please enter a number.")
    
    return {
        'enabled': True,
        'dry_run': dry_run_enabled,
        'bet_size': bet_size
    }

def get_user_choice():
    """
    Get user's choice for what to scan
    
    Returns:
        dict: User's choice and parameters
    """
    print("\n🎯 SCANNING OPTIONS:")
    print("1. Scan specific tournament (enter tournament ID)")
    print("2. Scan specific event (enter event ID)")  
    print("3. 🚨 COMPREHENSIVE scan - ALL tournaments, ALL events, ALL markets (LARGE!)")
    print("4. Quick NFL test (tournament ID 31)")
    print("5. Show available tournaments first")
    
    while True:
        choice = input("\nChoose option (1-5): ").strip()
        
        if choice == "1":
            tournament_id = input("Enter tournament ID: ").strip()
            try:
                tournament_id = int(tournament_id)
                limit = input("Limit number of events to scan (press Enter for all): ").strip()
                limit_events = int(limit) if limit else None
                return {
                    'type': 'tournament',
                    'tournament_id': tournament_id,
                    'limit_events': limit_events
                }
            except ValueError:
                print("❌ Invalid tournament ID. Please enter a number.")
                continue
                
        elif choice == "2":
            event_id = input("Enter event ID: ").strip()
            try:
                event_id = int(event_id)
                return {
                    'type': 'event',
                    'event_id': event_id
                }
            except ValueError:
                print("❌ Invalid event ID. Please enter a number.")
                continue
                
        elif choice == "3":
            print("⚠️  You've selected COMPREHENSIVE scan - this will scan:")
            print("   • ALL tournaments in target sports")
            print("   • ALL events in each tournament")  
            print("   • ALL market types (moneyline, props, alternatives, etc.)")
            print("   • Could generate hundreds of API calls and take 10+ minutes")
            confirm = input("Continue with comprehensive scan? (y/n): ").strip().lower()
            if confirm not in ['y', 'yes']:
                continue
            return {'type': 'all'}
            
        elif choice == "4":
            limit = input("Limit number of NFL events to scan (press Enter for all): ").strip()
            limit_events = int(limit) if limit else None
            return {
                'type': 'tournament',
                'tournament_id': 31,
                'limit_events': limit_events
            }
            
        elif choice == "5":
            return {'type': 'show_tournaments'}
            
        else:
            print("❌ Invalid choice. Please choose 1-5.")

def show_available_tournaments(scanner):
    """
    Show available tournaments to help user choose
    """
    print("🏆 Fetching available tournaments...")
    tournaments = scanner.get_tournaments()
    
    if not tournaments:
        print("❌ No tournaments found!")
        return
    
    print(f"\n📋 AVAILABLE TOURNAMENTS ({len(tournaments)} found):")
    print("-" * 60)
    
    for tournament in tournaments:
        tournament_id = tournament.get('id')
        tournament_name = tournament.get('name', 'Unknown')
        sport_name = tournament.get('sport', {}).get('name', 'Unknown')
        category = tournament.get('category', {}).get('name', 'Unknown')
        
        print(f"ID: {tournament_id:8d} | {sport_name:15s} | {tournament_name}")
        if category != 'Unknown':
            print(f"{'':20s} | Category: {category}")
    
    print("-" * 60)

def main():
    """
    Main scanning function with interactive options
    """
    print("ProphetX Market Scanner & Bet Placer")
    print("Focused testing with specific tournament/event options")
    print("=" * 60)
    
    # Load configuration
    config = ConfigManager.get_config()
    
    # Initialize scanner
    scanner = ProphetXMarketScanner(config)
    
    # Get bet placement configuration
    bet_config = get_bet_placement_config()
    
    if bet_config['enabled']:
        scanner.configure_bet_placement(
            enabled=True,
            dry_run=bet_config['dry_run'],
            bet_size=bet_config['bet_size']
        )
        
        if bet_config['dry_run']:
            print("\n⚠️  DRY RUN MODE: Bets will be simulated, not actually placed")
        else:
            print("\n🚨 LIVE MODE: Real bets will be placed!")
            confirm = input("Are you sure you want to place real bets? (type 'YES' to confirm): ")
            if confirm != 'YES':
                print("❌ Aborting for safety")
                return
    else:
        print("\n📊 SCAN ONLY MODE: No bets will be placed")
    
    try:
        while True:
            # Get user choice
            choice = get_user_choice()
            
            if choice['type'] == 'show_tournaments':
                show_available_tournaments(scanner)
                continue
            
            print(f"\n🚀 Starting scan...")
            start_time = datetime.now()
            
            # Execute based on choice
            if choice['type'] == 'tournament':
                opportunities = scanner.scan_specific_tournament(
                    choice['tournament_id'], 
                    choice.get('limit_events')
                )
            elif choice['type'] == 'event':
                opportunities = scanner.scan_specific_event(choice['event_id'])
            elif choice['type'] == 'all':
                opportunities = scanner.scan_all_markets()
            else:
                print("❌ Invalid choice")
                continue
            
            end_time = datetime.now()
            
            # Print results summary
            scanner.print_opportunities_summary(opportunities)
            
            print(f"\n⏱️  Scan completed in {(end_time - start_time).total_seconds():.1f} seconds")
            
            # Show bet placement stats if enabled
            if bet_config['enabled']:
                bet_stats = scanner.bet_placer.get_placement_stats()
                if bet_stats['total_attempts'] > 0:
                    print(f"\n🎯 BET PLACEMENT STATISTICS:")
                    print(f"   Total bets attempted: {bet_stats['total_attempts']}")
                    print(f"   Success rate: {bet_stats['success_rate']:.1f}%")
                    print(f"   Total stake: ${bet_stats['total_stake_placed']:.2f}")
            
            # Save results
            if opportunities:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                scan_type = choice['type']
                if choice['type'] == 'tournament':
                    filename = f"prophetx_tournament_{choice['tournament_id']}_opportunities_{timestamp}.json"
                elif choice['type'] == 'event':
                    filename = f"prophetx_event_{choice['event_id']}_opportunities_{timestamp}.json"
                else:
                    filename = f"prophetx_all_opportunities_{timestamp}.json"
                
                with open(filename, 'w') as f:
                    json.dump(opportunities, f, indent=2, default=str)
                
                print(f"💾 Results saved to: {filename}")
                
                # Save bet log if bets were placed
                if bet_config['enabled'] and scanner.bet_placer.get_placement_stats()['total_attempts'] > 0:
                    bet_log_file = scanner.bet_placer.save_bet_log()
                    print(f"📝 Bet log saved to: {bet_log_file}")
            
            # Ask if user wants to run another scan
            another = input("\nRun another scan? (y/n): ").strip().lower()
            if another not in ['y', 'yes']:
                break
        
        print("\n👋 Thanks for using ProphetX Market Scanner!")
        
    except KeyboardInterrupt:
        print("\n🛑 Scan interrupted by user")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")

if __name__ == "__main__":
    main()