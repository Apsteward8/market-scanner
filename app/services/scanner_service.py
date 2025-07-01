#!/usr/bin/env python3
"""
Market Scanner Service
Handles ProphetX market scanning and opportunity identification
"""

import requests
import time
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import HTTPException

from app.core.config import get_settings
from app.services.auth_service import auth_service
from app.services.odds_validator_service import odds_validator_service
from app.models.responses import TournamentInfo, EventInfo, BettingOpportunity, OriginalBet, OurBet, BetPlacementInfo, OpportunityAnalysis

class MarketScannerService:
    """Service for scanning ProphetX markets for opportunities"""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.prophetx_base_url
    
    async def get_tournaments(self) -> List[TournamentInfo]:
        """
        Get all available tournaments/leagues
        
        Returns:
            List of tournament information
        """
        url = f"{self.base_url}/partner/mm/get_tournaments"
        headers = await auth_service.get_auth_headers()
        
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                tournaments = data.get('data', {}).get('tournaments', [])
                
                # Filter for target sports and convert to TournamentInfo
                filtered_tournaments = []
                for tournament in tournaments:
                    sport_name = tournament.get('sport', {}).get('name', '')
                    if sport_name in self.settings.target_sports:
                        filtered_tournaments.append(TournamentInfo(
                            id=tournament.get('id'),
                            name=tournament.get('name', 'Unknown'),
                            sport_name=sport_name,
                            category_name=tournament.get('category', {}).get('name')
                        ))
                
                return filtered_tournaments
                
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error fetching tournaments: {response.text}"
                )
                
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"Network error fetching tournaments: {str(e)}")
    
    async def get_events_for_tournament(self, tournament_id: int) -> List[EventInfo]:
        """
        Get all events/games for a specific tournament
        
        Args:
            tournament_id: Tournament ID to fetch events for
            
        Returns:
            List of event information
        """
        url = f"{self.base_url}/partner/mm/get_sport_events"
        headers = await auth_service.get_auth_headers()
        params = {"tournament_id": tournament_id}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                events = data.get('data', {}).get('sport_events', [])
                
                # Filter for upcoming events and convert to EventInfo
                upcoming_events = []
                for event in events:
                    if event.get('status') == 'not_started':
                        upcoming_events.append(EventInfo(
                            event_id=event.get('event_id'),
                            display_name=event.get('display_name', 'Unknown Event'),
                            tournament_name=event.get('tournament_name'),
                            scheduled=event.get('scheduled'),
                            status=event.get('status')
                        ))
                
                return upcoming_events
                
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error fetching events for tournament {tournament_id}: {response.text}"
                )
                
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"Network error fetching events: {str(e)}")
    
    async def get_markets_for_event(self, event_id: int) -> Optional[Dict]:
        """
        Get markets for a specific event
        
        Args:
            event_id: Event ID to fetch markets for
            
        Returns:
            Markets data dictionary or None
        """
        url = f"{self.base_url}/partner/v2/mm/get_markets"
        headers = await auth_service.get_auth_headers()
        params = {"event_id": event_id}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                # Don't raise exception for individual market failures
                return None
                
        except requests.exceptions.RequestException:
            # Don't raise exception for individual market failures
            return None
    
    def convert_liquidity_to_original_bet(self, selection: Dict) -> Dict:
        """
        Convert liquidity data to original bet information
        
        When we see "Jets +101 with $500 liquidity", this means:
        - Someone originally bet "Steelers -101 for $500" 
        
        Args:
            selection: The selection showing liquidity
            
        Returns:
            dict: Original bet information
        """
        liquidity_odds = selection.get('odds', 0)
        liquidity_team = selection.get('name', '')
        liquidity_stake = selection.get('stake', 0)
        
        # Convert liquidity odds to original bet odds
        if liquidity_odds > 0:
            original_bet_odds = -liquidity_odds
        else:
            original_bet_odds = abs(liquidity_odds)
        
        return {
            'original_bet_odds': original_bet_odds,
            'original_bet_stake': liquidity_stake,
            'original_bet_team': f"Opposite of {liquidity_team}",
            'liquidity_team': liquidity_team,
            'liquidity_odds': liquidity_odds,
            'liquidity_stake': liquidity_stake
        }
    
    def find_opposite_team_info(self, current_selection: Dict, all_selections: List) -> Optional[Dict]:
        """
        Find the opposite team/outcome information in the same market
        
        Args:
            current_selection: The selection where we see liquidity
            all_selections: All selection groups from this market
            
        Returns:
            dict: Opposite team/outcome information or None
        """
        current_competitor_id = current_selection.get('competitor_id')
        current_outcome_id = current_selection.get('outcome_id')
        current_name = current_selection.get('name', '')
        
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
                
                # Team-based markets (different competitor_id)
                if current_competitor_id is not None and selection_competitor_id is not None:
                    if selection_competitor_id != current_competitor_id:
                        return {
                            'line_id': selection.get('line_id'),
                            'name': selection_name,
                            'competitor_id': selection_competitor_id,
                            'outcome_id': selection_outcome_id
                        }
                
                # Prop markets (different outcome_id, no competitor_id)
                elif current_competitor_id is None and selection_competitor_id is None:
                    if selection_outcome_id != current_outcome_id:
                        return {
                            'line_id': selection.get('line_id'),
                            'name': selection_name,
                            'competitor_id': None,
                            'outcome_id': selection_outcome_id
                        }
                
                # Over/Under logic (backup)
                elif self.is_opposite_over_under(current_name, selection_name):
                    return {
                        'line_id': selection.get('line_id'),
                        'name': selection_name,
                        'competitor_id': selection_competitor_id,
                        'outcome_id': selection_outcome_id
                    }
        
        return None
    
    def is_opposite_over_under(self, name1: str, name2: str) -> bool:
        """Check if two names are opposite over/under bets"""
        name1_lower = name1.lower()
        name2_lower = name2.lower()
        
        if 'over' in name1_lower and 'under' in name2_lower:
            return True
        if 'under' in name1_lower and 'over' in name2_lower:
            return True
            
        return False
    
    async def analyze_market_for_opportunities(self, market_data: Dict, event_info: EventInfo) -> List[BettingOpportunity]:
        """
        Analyze a market for undercut opportunities
        
        Args:
            market_data: Market data from API
            event_info: Event information
            
        Returns:
            List of betting opportunities
        """
        opportunities = []
        
        if not market_data or 'data' not in market_data:
            return opportunities
        
        event_data = market_data['data']
        markets = event_data.get('markets', [])
        
        for market in markets:
            market_name = market.get('name', 'Unknown Market')
            market_type = market.get('type', 'unknown')
            
            # Handle different selection structures
            selection_groups = []
            
            # Standard structure (moneyline, spread, etc.)
            if 'selections' in market:
                selections = market.get('selections', [])
                selection_groups.append({
                    'selections': selections,
                    'line_info': {'name': market_name, 'line': 0}
                })
                
            # Player props structure with market_lines
            elif 'market_lines' in market:
                market_lines = market.get('market_lines', [])
                for market_line in market_lines:
                    line_selections = market_line.get('selections', [])
                    if line_selections:
                        selection_groups.append({
                            'selections': line_selections,
                            'line_info': {
                                'name': market_line.get('name', 'Unknown Line'),
                                'line': market_line.get('line', 0)
                            }
                        })
            
            if not selection_groups:
                continue
            
            # Analyze each line group separately
            for selection_group in selection_groups:
                selections = selection_group['selections']
                line_info = selection_group['line_info']
                
                for selection_list in selections:
                    if not isinstance(selection_list, list):
                        continue
                    
                    for selection in selection_list:
                        stake = selection.get('stake', 0)
                        
                        # Only analyze high-stake bets
                        if stake >= self.settings.min_stake_threshold:
                            
                            # Convert liquidity to original bet information
                            original_bet_info = self.convert_liquidity_to_original_bet(selection)
                            
                            # Find opposite team info within the same line group
                            opposite_team_info = self.find_opposite_team_info(selection, selections)
                            if opposite_team_info is None:
                                continue
                            
                            # Update original bet team name with actual team name
                            original_bet_team_name = opposite_team_info['name']
                            
                            # Calculate our undercut odds
                            our_odds = odds_validator_service.calculate_undercut_odds(
                                original_bet_info['original_bet_odds'],
                                self.settings.undercut_amount
                            )
                            
                            if our_odds is None:
                                continue
                            
                            # Calculate bet sizing
                            max_bet_size = min(stake * 0.5, self.settings.max_bet_size)
                            
                            # Calculate metrics
                            profit_metrics = odds_validator_service.calculate_profit_metrics(
                                original_bet_info['original_bet_odds'], our_odds, max_bet_size
                            )
                            
                            # Get explanation
                            undercut_explanation = odds_validator_service.explain_undercut(
                                original_bet_info['original_bet_odds'], our_odds
                            )
                            
                            # Create opportunity
                            opportunity = BettingOpportunity(
                                event_id=event_info.event_id,
                                event_name=event_info.display_name,
                                market_name=f"{market_name} - {line_info['name']}",
                                market_type=market_type,
                                market_id=market.get('id'),
                                
                                original_bet=OriginalBet(
                                    team_name=original_bet_team_name,
                                    odds=original_bet_info['original_bet_odds'],
                                    stake=stake,
                                    display=f"{original_bet_team_name} {original_bet_info['original_bet_odds']:+d} for ${stake:,}"
                                ),
                                
                                our_bet=OurBet(
                                    team_name=original_bet_team_name,
                                    odds=our_odds,
                                    stake=max_bet_size,
                                    display=f"{original_bet_team_name} {our_odds:+d} for ${max_bet_size:,}"
                                ),
                                
                                bet_placement=BetPlacementInfo(
                                    line_id=opposite_team_info['line_id'],
                                    competitor_id=opposite_team_info['competitor_id'],
                                    outcome_id=opposite_team_info['outcome_id'],
                                    odds=our_odds,
                                    stake=max_bet_size
                                ),
                                
                                analysis=OpportunityAnalysis(
                                    value_score=stake / 1000,
                                    potential_profit=profit_metrics['potential_profit'],
                                    potential_win=profit_metrics['potential_win'],
                                    roi_percent=profit_metrics['roi_percent'],
                                    undercut_explanation=undercut_explanation,
                                    follow_money_logic=f"Following ${stake:,} bet: {original_bet_team_name} {original_bet_info['original_bet_odds']:+d} → {our_odds:+d}"
                                ),
                                
                                updated_at=selection.get('updated_at'),
                                is_valid_follow=True
                            )
                            
                            opportunities.append(opportunity)
        
        return opportunities
    
    async def scan_tournament(self, tournament_id: int, limit_events: Optional[int] = None) -> List[BettingOpportunity]:
        """
        Scan a specific tournament for opportunities
        
        Args:
            tournament_id: Tournament ID to scan
            limit_events: Maximum number of events to scan
            
        Returns:
            List of betting opportunities
        """
        all_opportunities = []
        
        # Get events for this tournament
        events = await self.get_events_for_tournament(tournament_id)
        
        if not events:
            return []
        
        events_to_scan = events if limit_events is None else events[:limit_events]
        
        # Scan each event
        for event in events_to_scan:
            # Get markets for this event
            markets_data = await self.get_markets_for_event(event.event_id)
            
            if markets_data:
                # Analyze for opportunities
                opportunities = await self.analyze_market_for_opportunities(markets_data, event)
                all_opportunities.extend(opportunities)
            
            # Rate limiting
            await asyncio.sleep(0.5)
        
        return all_opportunities
    
    async def scan_event(self, event_id: int) -> List[BettingOpportunity]:
        """
        Scan a specific event for opportunities
        
        Args:
            event_id: Event ID to scan
            
        Returns:
            List of betting opportunities
        """
        # Get markets for this event
        markets_data = await self.get_markets_for_event(event_id)
        
        if not markets_data:
            return []
        
        # Create event info
        event_info = EventInfo(
            event_id=event_id,
            display_name=f'Event {event_id}',
            tournament_name=None,
            scheduled=None,
            status=None
        )
        
        # Analyze for opportunities
        opportunities = await self.analyze_market_for_opportunities(markets_data, event_info)
        
        return opportunities
    
    async def scan_all_markets(self) -> List[BettingOpportunity]:
        """
        Scan all available markets for opportunities
        
        Returns:
            List of all betting opportunities found
        """
        all_opportunities = []
        
        # Get all tournaments
        tournaments = await self.get_tournaments()
        
        if not tournaments:
            return []
        
        # Scan each tournament
        for tournament in tournaments:
            # Get events for this tournament
            events = await self.get_events_for_tournament(tournament.id)
            
            if not events:
                continue
            
            # Scan each event
            for event in events:
                # Get markets for this event
                markets_data = await self.get_markets_for_event(event.event_id)
                
                if markets_data:
                    # Analyze for opportunities
                    opportunities = await self.analyze_market_for_opportunities(markets_data, event)
                    all_opportunities.extend(opportunities)
                
                # Rate limiting
                await asyncio.sleep(0.5)
            
            # Rate limiting between tournaments
            await asyncio.sleep(1)
        
        return all_opportunities

# Global scanner service instance
scanner_service = MarketScannerService()

# Import asyncio at the end to avoid circular imports
import asyncio