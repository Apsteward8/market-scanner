#!/usr/bin/env python3
"""
Market Scanning Service
Orchestrates the process of finding high wager opportunities on ProphetX
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

from app.services.prophetx_service import prophetx_service

logger = logging.getLogger(__name__)

@dataclass
class SportEvent:
    """Represents a sport event from ProphetX"""
    event_id: str
    display_name: str
    scheduled_time: datetime
    home_team: str
    away_team: str
    status: str
    tournament_id: str
    tournament_name: str

@dataclass  
class HighWagerOpportunity:
    """Represents a high wager opportunity found in the market"""
    # Event details
    event_id: str
    event_name: str
    scheduled_time: datetime
    tournament_name: str
    
    # Market details
    market_id: str
    market_name: str
    market_type: str  # moneyline, spread, total
    line_info: str  # Additional line information (e.g., "-6.5", "Over 45.5")
    
    # Large bet information (the bet we're following)
    large_bet_side: str
    large_bet_stake_amount: float  # Original bet stake
    large_bet_liquidity_value: float  # Available liquidity created
    large_bet_combined_size: float  # stake + value
    large_bet_odds: int  # Odds the large bettor got
    
    # Available opportunity (what we can take)
    available_side: str
    available_odds: int
    available_liquidity_amount: float
    
    # Our proposed action
    our_proposed_odds: int  # Better odds we'll offer

class MarketScanningService:
    """Service for scanning ProphetX markets for high wager opportunities"""
    
    def __init__(self):
        from app.core.config import get_settings
        self.settings = get_settings()
        
        # Tournament IDs (start with NCAAF)
        self.ncaaf_tournament_id = "27653"
        
        # Scanning parameters from settings
        self.min_stake_threshold = self.settings.min_stake_threshold  # $7500 -> $10000
        self.min_individual_threshold = 2500.0  # New: both stake and value must be > $2500
        self.undercut_improvement = self.settings.undercut_improvement  # 1 point
        self.commission_rate = self.settings.prophetx_commission_rate  # 3%
        
        # Time window for events (next 24 hours)
        self.scan_window_hours = 24
        
        # Focus on main line markets
        self.main_line_categories = {"Game Lines"}
        self.main_line_types = {"moneyline", "spread", "total", "totals"}  # Added "totals" as backup
        
    async def scan_for_opportunities(self) -> List[HighWagerOpportunity]:
        """
        Main scanning function - finds all high wager opportunities
        
        Returns:
            List of high wager opportunities found
        """
        try:
            logger.info("🔍 Starting market scan for high wager opportunities...")
            
            # Step 1: Get upcoming NCAAF events
            upcoming_events = await self._get_upcoming_events()
            if not upcoming_events:
                logger.info("No upcoming events found in scan window")
                return []
            
            logger.info(f"📅 Found {len(upcoming_events)} upcoming NCAAF events")
            for event in upcoming_events:
                logger.info(f"  - {event.display_name} (ID: {event.event_id}) in {(event.scheduled_time - datetime.now(timezone.utc)).total_seconds() / 3600:.1f} hours")
            
            # Step 2: Get market data for these events
            event_ids = [event.event_id for event in upcoming_events]
            logger.info(f"📊 Fetching market data for event IDs: {event_ids}")
            
            market_data = await self._get_market_data(event_ids)
            
            if not market_data:
                logger.warning("No market data returned from API")
                return []
                
            logger.info(f"📊 Market data received for {len(market_data)} events")
            
            # Step 3: Filter for main line markets and find high wagers
            opportunities = await self._find_high_wager_opportunities(upcoming_events, market_data)
            
            # Step 4: Deduplicate opportunities to keep only best odds per line
            if opportunities:
                logger.info(f"Before deduplication: {len(opportunities)} opportunities")
                opportunities = self._deduplicate_opportunities(opportunities)
                logger.info(f"After deduplication: {len(opportunities)} opportunities")
            
            logger.info(f"💰 Found {len(opportunities)} high wager opportunities")
            
            return opportunities
        except Exception as e:
            logger.error(f"Error during market scan: {e}", exc_info=True)
            return []
    
    def _deduplicate_opportunities(self, opportunities: List[HighWagerOpportunity]) -> List[HighWagerOpportunity]:
        """
        Remove duplicate opportunities on the same line, keeping only the one with best odds
        
        For each unique combination of (event_id, market_type, line_value, side), keep only
        the opportunity with the best odds for the bettor.
        """
        # Group opportunities by unique line identifier
        line_groups = {}
        
        for opp in opportunities:
            # Create unique key for this line and side
            line_key = (
                opp.event_id,
                opp.market_type,
                opp.line_info,  # This includes spread value or total info
                opp.available_side.split()[0] if ' ' in opp.available_side else opp.available_side  # Team name without odds
            )
            
            if line_key not in line_groups:
                line_groups[line_key] = []
            line_groups[line_key].append(opp)
        
        # For each group, keep only the opportunity with the best odds
        deduplicated = []
        
        for line_key, group_opportunities in line_groups.items():
            if len(group_opportunities) == 1:
                # Only one opportunity on this line, keep it
                deduplicated.extend(group_opportunities)
            else:
                # Multiple opportunities on same line, keep the one with best odds
                best_opportunity = self._find_best_odds_opportunity(group_opportunities)
                if best_opportunity:
                    deduplicated.append(best_opportunity)
                    logger.info(f"Deduplicated {len(group_opportunities)} opportunities on {line_key}, kept best odds: {best_opportunity.our_proposed_odds:+d}")
        
        return deduplicated
    
    def _find_best_odds_opportunity(self, opportunities: List[HighWagerOpportunity]) -> Optional[HighWagerOpportunity]:
        """Find the opportunity with the best odds for the bettor"""
        if not opportunities:
            return None
            
        best_opp = opportunities[0]
        
        for opp in opportunities[1:]:
            # For positive odds, higher is better for the bettor
            # For negative odds, closer to 0 (less negative) is better for the bettor
            if self._is_better_odds(opp.our_proposed_odds, best_opp.our_proposed_odds):
                best_opp = opp
                
        return best_opp
    
    def _is_better_odds(self, odds1: int, odds2: int) -> bool:
        """Determine if odds1 is better than odds2 for the bettor"""
        # If both positive, higher is better
        if odds1 > 0 and odds2 > 0:
            return odds1 > odds2
        # If both negative, less negative (closer to 0) is better
        elif odds1 < 0 and odds2 < 0:
            return odds1 > odds2  # -107 > -122
        # If one positive and one negative, positive is generally better
        else:
            return odds1 > odds2
    
    async def _get_upcoming_events(self) -> List[SportEvent]:
        """Get upcoming NCAAF events in the next 24 hours"""
        try:
            # Get sport events from ProphetX (uses 1-hour cache)
            response = await prophetx_service.get_sport_events(self.ncaaf_tournament_id)
            raw_events = response.get('data', {}).get('sport_events', [])
            
            # Filter for events in our time window
            now = datetime.now(timezone.utc)
            scan_end_time = now + timedelta(hours=self.scan_window_hours)
            
            upcoming_events = []
            
            for event in raw_events:
                try:
                    # Parse scheduled time
                    scheduled_str = event.get('scheduled', '')
                    scheduled_time = datetime.fromisoformat(scheduled_str.replace('Z', '+00:00'))
                    
                    # Check if event is in our scan window
                    if now <= scheduled_time <= scan_end_time:
                        # Extract team information
                        competitors = event.get('competitors', [])
                        home_team = ""
                        away_team = ""
                        
                        for competitor in competitors:
                            if competitor.get('side') == 'home':
                                home_team = competitor.get('display_name', '')
                            elif competitor.get('side') == 'away':
                                away_team = competitor.get('display_name', '')
                        
                        sport_event = SportEvent(
                            event_id=str(event.get('event_id', '')),
                            display_name=event.get('display_name', ''),
                            scheduled_time=scheduled_time,
                            home_team=home_team,
                            away_team=away_team,
                            status=event.get('status', ''),
                            tournament_id=str(event.get('tournament_id', '')),
                            tournament_name=event.get('tournament_name', '')
                        )
                        
                        upcoming_events.append(sport_event)
                        
                except Exception as e:
                    logger.warning(f"Error parsing event {event.get('display_name', 'Unknown')}: {e}")
                    continue
            
            return upcoming_events
            
        except Exception as e:
            logger.error(f"Error getting upcoming events: {e}")
            return []
    
    async def _get_market_data(self, event_ids: List[str]) -> Dict[str, Any]:
        """Get market data for multiple events"""
        try:
            if not event_ids:
                return {}
                
            # Batch event IDs to avoid overly large requests
            batch_size = 10  # Process 10 events at a time
            all_market_data = {}
            
            for i in range(0, len(event_ids), batch_size):
                batch_ids = event_ids[i:i + batch_size]
                
                logger.info(f"📊 Fetching market data for batch {i//batch_size + 1} ({len(batch_ids)} events)")
                
                response = await prophetx_service.get_multiple_markets(batch_ids)
                batch_data = response.get('data', {})
                
                all_market_data.update(batch_data)
                
                # Small delay between batches to be API-friendly
                if i + batch_size < len(event_ids):
                    await asyncio.sleep(1)
            
            return all_market_data
            
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return {}
    
    async def _find_high_wager_opportunities(self, events: List[SportEvent], 
                                           market_data: Dict[str, Any]) -> List[HighWagerOpportunity]:
        """Find high wager opportunities in the market data"""
        opportunities = []
        
        logger.info(f"Processing {len(events)} events for opportunities")
        
        for event in events:
            logger.info(f"Processing event: {event.display_name} (ID: {event.event_id})")
            
            event_market_data = market_data.get(event.event_id, [])
            if not event_market_data:
                logger.warning(f"No market data found for event {event.event_id}")
                continue
                
            logger.info(f"Found {len(event_market_data)} markets for event {event.event_id}")
            
            event_opportunities = await self._scan_event_markets(event, event_market_data)
            logger.info(f"Found {len(event_opportunities)} opportunities for event {event.display_name}")
            
            opportunities.extend(event_opportunities)
        
        logger.info(f"Total opportunities found across all events: {len(opportunities)}")
        return opportunities
    
    async def _scan_event_markets(self, event: SportEvent, 
                                markets: List[Dict[str, Any]]) -> List[HighWagerOpportunity]:
        """Scan markets for a single event"""
        opportunities = []
        
        # Debug: Log all market types we're seeing
        market_types_found = set()
        game_line_markets = []
        
        for market in markets:
            category_name = market.get('category_name', '')
            market_type = market.get('type', '').lower()
            market_types_found.add(f"{category_name}:{market_type}")
            
            # Collect all Game Lines markets
            if category_name == "Game Lines":
                game_line_markets.append(market)
        
        logger.info(f"Event {event.display_name}: Found {len(markets)} total markets, {len(game_line_markets)} Game Lines markets")
        logger.debug(f"Market types found: {sorted(market_types_found)}")
        
        # Process all Game Lines markets
        for market in game_line_markets:
            try:
                market_type = (market.get('type') or '').lower()
                if market_type not in self.main_line_types:
                    continue

                async def process_selection_groups(selections: list, market_ctx: dict):
                    # selections is a list of [side0[], side1[]]
                    for side_group in selections or []:
                        if not side_group:
                            continue
                        for selection in side_group:
                            stake = float(selection.get('stake', 0) or 0)
                            value = float(selection.get('value', 0) or 0)
                            combined = stake + value

                            # Use both the combined and individual thresholds (you already defined min_individual_threshold)
                            if (
                                combined >= self.min_stake_threshold
                                and stake >= self.min_individual_threshold
                                and value >= self.min_individual_threshold
                            ):
                                opp = await self._create_opportunity(
                                    event=event,
                                    market=market_ctx,          # important: this may include 'line_value'
                                    selections=selections,      # pass the current line's selections
                                    liquidity_selection=selection
                                )
                                if opp and abs(opp.our_proposed_odds) <= 400:
                                    opportunities.append(opp)

                if market_type == 'moneyline':
                    # Moneylines: selections live at the market level
                    selection_groups = market.get('selections', [])
                    await process_selection_groups(selection_groups, market)
                else:
                    # Spreads / Totals: iterate each market line, and use its selections
                    for line in market.get('market_lines', []) or []:
                        line_selections = line.get('selections', [])
                        if not line_selections:
                            continue
                        # Pass the line value so _extract_line_info can print "Over 47.5" / "+6.5" nicely
                        market_with_line = dict(market)
                        market_with_line['line_value'] = line.get('line', 0)
                        await process_selection_groups(line_selections, market_with_line)
            except Exception as e:
                logger.warning(
                    f"Error scanning market {market.get('category_name', 'Unknown')} - {market.get('type', 'Unknown')}: {e}",
                    exc_info=True
                )
                continue
        
        return opportunities
    
    async def _create_opportunity(self, event: SportEvent, market: Dict[str, Any], 
                                selections: List[List[Dict[str, Any]]], 
                                liquidity_selection: Dict[str, Any]) -> Optional[HighWagerOpportunity]:
        """Create an opportunity from identified high stakes"""
        
        try:
            # The selection with available liquidity
            available_side = liquidity_selection.get('display_name', '')
            available_odds = int(liquidity_selection.get('odds', 0))
            available_liquidity = float(liquidity_selection.get('value', 0))
            
            # The original bet details (stake represents the large bet size)
            large_bet_stake = float(liquidity_selection.get('stake', 0))
            large_bet_value = float(liquidity_selection.get('value', 0))
            combined_size = large_bet_stake + large_bet_value
            
            # The large bettor got the opposite odds of what's available
            large_bet_odds = -available_odds if available_odds > 0 else abs(available_odds)
            
            # Calculate our undercut odds (better for the bettor)
            our_proposed_odds = self._calculate_undercut_odds(large_bet_odds)
            
            # Extract line information for spreads and totals
            line_info = self._extract_line_info(market, available_side)
            
            return HighWagerOpportunity(
                event_id=event.event_id,
                event_name=event.display_name,
                scheduled_time=event.scheduled_time,
                tournament_name=event.tournament_name,
                market_id=str(market.get('id', '')),
                market_name=market.get('category_name', ''),
                market_type=market.get('type', ''),
                line_info=line_info,
                large_bet_side=self._get_opposite_side(available_side, market.get('type', '')),
                large_bet_stake_amount=large_bet_stake,
                large_bet_liquidity_value=large_bet_value,
                large_bet_combined_size=combined_size,
                large_bet_odds=large_bet_odds,
                available_side=available_side,
                available_odds=available_odds,
                available_liquidity_amount=available_liquidity,
                our_proposed_odds=our_proposed_odds
            )
            
        except Exception as e:
            logger.error(f"Error creating opportunity: {e}")
            return None
    
    def _calculate_undercut_odds(self, original_odds: int) -> int:
        """Calculate our undercut odds to offer better value"""
        if original_odds > 0:
            # For positive odds, reduce to make it better for the bettor
            return max(original_odds - self.undercut_improvement, -110)  # Don't go below -110
        else:
            # For negative odds, make less negative (better for bettor)
            return min(original_odds + self.undercut_improvement, 110)  # Don't go above +110
    
    def _extract_line_info(self, market: Dict[str, Any], selection_side: str) -> str:
        """Extract line information for spreads and totals"""
        market_type = market.get('type', '').lower()
        
        if market_type == 'spread':
            # For spreads, check if we have line info from market_lines structure
            if 'line_value' in market:
                line_val = market.get('line_value', 0)
                if line_val > 0:
                    return f"+{line_val}"
                elif line_val < 0:
                    return str(line_val)
                else:
                    return "PK"
            else:
                # Fallback: extract from selection name
                if '+' in selection_side:
                    return selection_side.split()[-1]
                elif '-' in selection_side and selection_side.count('-') > selection_side.count(' at '):
                    return selection_side.split()[-1]
                else:
                    return "PK"
                    
        elif market_type in ['total', 'totals']:
            # For totals, check if we have line info from market_lines structure
            if 'line_value' in market:
                line_val = market.get('line_value', 0)
                if 'Over' in selection_side:
                    return f"Over {line_val}"
                elif 'Under' in selection_side:
                    return f"Under {line_val}"
                else:
                    return f"Total {line_val}"
            else:
                # Fallback: extract from selection name
                if 'Over' in selection_side or 'Under' in selection_side:
                    parts = selection_side.split()
                    for i, part in enumerate(parts):
                        if part in ['Over', 'Under'] and i + 1 < len(parts):
                            return f"{part} {parts[i+1]}"
                return "Total"
                
        else:
            # Moneyline - no additional line info needed
            return ""
    
    def _get_opposite_side(self, available_side: str, market_type: str) -> str:
        """Get the opposite side of a bet based on market type"""
        
        if market_type.lower() == 'spread':
            # For spreads, flip the sign
            if '+' in available_side:
                return available_side.replace('+', '-')
            elif '-' in available_side:
                return available_side.replace('-', '+')
            else:
                return "Opposite Side"
                
        elif market_type.lower() == 'total':
            # For totals, flip Over/Under
            if 'Over' in available_side:
                return available_side.replace('Over', 'Under')
            elif 'Under' in available_side:
                return available_side.replace('Under', 'Over')
            else:
                return "Opposite Total"
                
        else:
            # For moneylines, this would need team name mapping
            # This is more complex and would require parsing team names
            return "Opposite Side"

# Global instance
market_scanning_service = MarketScanningService()