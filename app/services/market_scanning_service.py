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

# ProphetX Valid Odds Ladder
PROPHETX_ODDS_LADDER = [
    -25000, -24500, -24000, -23500, -23000, -22500, -22000, -21500, -21000, -20500,
    -20000, -19500, -19000, -18500, -18000, -17500, -17000, -16500, -16000, -15500,
    -15000, -14500, -14000, -13500, -13000, -12500, -12000, -11500, -11000, -10500,
    -10000, -9750, -9500, -9250, -9000, -8750, -8500, -8250, -8000, -7750,
    -7500, -7250, -7000, -6750, -6500, -6250, -6000, -5750, -5500, -5250,
    -5000, -4900, -4800, -4700, -4600, -4500, -4400, -4300, -4200, -4100,
    -4000, -3900, -3800, -3700, -3600, -3500, -3400, -3300, -3200, -3100,
    -3000, -2900, -2800, -2750, -2700, -2600, -2500, -2400, -2300, -2250,
    -2200, -2100, -2000, -1950, -1900, -1850, -1800, -1750, -1700, -1650,
    -1600, -1550, -1500, -1450, -1400, -1350, -1300, -1250, -1200, -1150,
    -1100, -1050, -1000, -990, -980, -970, -960, -950, -940, -930,
    -920, -910, -900, -890, -880, -870, -860, -850, -840, -830,
    -820, -810, -800, -790, -780, -770, -760, -750, -740, -730,
    -720, -710, -700, -690, -680, -670, -660, -650, -640, -630,
    -620, -610, -600, -590, -580, -570, -560, -550, -540, -530,
    -520, -510, -500, -495, -490, -485, -480, -475, -470, -465,
    -460, -455, -450, -445, -440, -435, -430, -425, -420, -415,
    -410, -405, -400, -395, -390, -385, -380, -375, -370, -365,
    -360, -355, -350, -345, -340, -335, -330, -325, -320, -315,
    -310, -305, -300, -295, -290, -285, -280, -275, -270, -265,
    -260, -255, -250, -245, -240, -235, -230, -225, -220, -215,
    -210, -205, -200, -198, -196, -194, -192, -190, -188, -186,
    -184, -182, -180, -178, -176, -174, -172, -170, -168, -166,
    -164, -162, -160, -158, -156, -154, -152, -150, -148, -146,
    -144, -142, -140, -138, -136, -134, -132, -130, -129, -128,
    -127, -126, -125, -124, -123, -122, -121, -120, -119, -118,
    -117, -116, -115, -114, -113, -112, -111, -110, -109, -108,
    -107, -106, -105, -104, -103, -102, -101, -100,
    100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
    110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
    120, 121, 122, 123, 124, 125, 126, 127, 128, 129,
    130, 132, 134, 136, 138, 140, 142, 144, 146, 148,
    150, 152, 154, 156, 158, 160, 162, 164, 166, 168,
    170, 172, 174, 176, 178, 180, 182, 184, 186, 188,
    190, 192, 194, 196, 198, 200, 205, 210, 215, 220,
    225, 230, 235, 240, 245, 250, 255, 260, 265, 270,
    275, 280, 285, 290, 295, 300, 305, 310, 315, 320,
    325, 330, 335, 340, 345, 350, 355, 360, 365, 370,
    375, 380, 385, 390, 395, 400, 405, 410, 415, 420,
    425, 430, 435, 440, 445, 450, 455, 460, 465, 470,
    475, 480, 485, 490, 495, 500, 510, 520, 530, 540,
    550, 560, 570, 580, 590, 600, 610, 620, 630, 640,
    650, 660, 670, 680, 690, 700, 710, 720, 730, 740,
    750, 760, 770, 780, 790, 800, 810, 820, 830, 840,
    850, 860, 870, 880, 890, 900, 910, 920, 930, 940,
    950, 960, 970, 980, 990, 1000, 1050, 1100, 1150, 1200,
    1250, 1300, 1350, 1400, 1450, 1500, 1550, 1600, 1650, 1700,
    1750, 1800, 1850, 1900, 1950, 2000, 2100, 2200, 2250, 2300,
    2400, 2500, 2600, 2700, 2750, 2800, 2900, 3000, 3100, 3200,
    3300, 3400, 3500, 3600, 3700, 3800, 3900, 4000, 4100, 4200,
    4300, 4400, 4500, 4600, 4700, 4800, 4900, 5000, 5250, 5500,
    5750, 6000, 6250, 6500, 6750, 7000, 7250, 7500, 7750, 8000,
    8250, 8500, 8750, 9000, 9250, 9500, 9750, 10000, 10500, 11000,
    11500, 12000, 12500, 13000, 13500, 14000, 14500, 15000, 15500, 16000,
    16500, 17000, 17500, 18000, 18500, 19000, 19500, 20000, 20500, 21000,
    21500, 22000, 22500, 23000, 23500, 24000, 24500, 25000
]

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
    sport_name: str

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
    line_id: str 
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
        
        # Get sport/tournament configuration from settings
        self.sport_tournament_mapping = self.settings.sport_tournament_mapping
        
        # Scanning parameters from settings
        self.min_stake_threshold = self.settings.min_stake_threshold  # $10000
        self.min_individual_threshold = 2500.0  # Both stake and value must be > $2500
        self.undercut_improvement = self.settings.undercut_improvement  # 1 point
        self.commission_rate = self.settings.prophetx_commission_rate  # 3%
        
        # Time window for events (next 24 hours)
        self.scan_window_hours = 24
        
        # Focus on main line markets
        self.main_line_categories = {"Game Lines"}
        self.main_line_types = {"moneyline", "spread", "total", "totals"}  # Added "totals" as backup
        
    def _find_next_valid_odds(self, target_odds: int, better_for_bettor: bool = True) -> int:
        """
        Find the next valid odds on ProphetX's odds ladder
        
        Args:
            target_odds: The odds we want to improve upon
            better_for_bettor: True for better odds for bettor, False for worse odds
            
        Returns:
            Next valid odds that's better/worse for the bettor
        """
        try:
            # Find current position in odds ladder
            if target_odds not in PROPHETX_ODDS_LADDER:
                # If exact odds not found, find closest
                closest_index = min(range(len(PROPHETX_ODDS_LADDER)), 
                                  key=lambda i: abs(PROPHETX_ODDS_LADDER[i] - target_odds))
            else:
                closest_index = PROPHETX_ODDS_LADDER.index(target_odds)
            
            if better_for_bettor:
                # Better for bettor means:
                # - For negative odds: less negative (closer to 0) -> higher index
                # - For positive odds: more positive (further from 0) -> higher index
                new_index = closest_index + 1
            else:
                # Worse for bettor means:
                # - For negative odds: more negative (further from 0) -> lower index  
                # - For positive odds: less positive (closer to 0) -> lower index
                new_index = closest_index - 1
            
            # Ensure we stay within bounds
            new_index = max(0, min(len(PROPHETX_ODDS_LADDER) - 1, new_index))
            
            return PROPHETX_ODDS_LADDER[new_index]
            
        except Exception as e:
            logger.warning(f"Error finding next valid odds for {target_odds}: {e}")
            # Fallback logic
            if better_for_bettor:
                return target_odds + (1 if target_odds >= 0 else 1)
            else:
                return target_odds - (1 if target_odds >= 0 else 1)

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
        Remove duplicate opportunities on the same side, keeping only the one with best odds for other users
        
        For each unique combination of (event_id, market_type, large_bet_side), keep only
        the opportunity that creates the best liquidity odds for opposing bettors.
        
        This groups ALL opportunities for the same side (e.g., all "Philadelphia Eagles" moneyline bets)
        regardless of specific line odds (-330, -340, etc.) and keeps the best one.
        
        Logic: Higher absolute value of our_proposed_odds creates better odds for the opposing side.
        Example: our_proposed_odds of -375 creates +375 liquidity, which is better than -335 creating +335.
        """
        if not opportunities:
            logger.info("🔍 No opportunities to deduplicate")
            return opportunities
        
        logger.info(f"🔍 Starting deduplication of {len(opportunities)} opportunities")
        
        # Group opportunities by unique line identifier
        grouped_opportunities = {}
        
        for i, opp in enumerate(opportunities):
            # Create key based on event, market type, and the side we're betting on
            # EXCLUDE line_info to group different odds for the same underlying bet
            key = (opp.event_id, opp.market_type, opp.large_bet_side)
            
            # DEBUG: Log each opportunity being processed
            logger.info(f"🔍 [{i+1}] Processing: {opp.event_name} | {opp.market_type} | large_bet_side='{opp.large_bet_side}' | our_odds={opp.our_proposed_odds:+d} | line_info='{opp.line_info}'")
            logger.info(f"    → Grouping key: {key}")
            
            if key not in grouped_opportunities:
                grouped_opportunities[key] = []
            grouped_opportunities[key].append(opp)
        
        logger.info(f"🔍 Created {len(grouped_opportunities)} groups from {len(opportunities)} opportunities")
        
        # Keep only the best opportunity from each group
        deduplicated_opportunities = []
        duplicates_removed = 0
        
        for i, (key, group) in enumerate(grouped_opportunities.items()):
            logger.info(f"🔍 Group {i+1}: key={key} has {len(group)} opportunities")
            
            if len(group) == 1:
                # No duplicates, keep the single opportunity
                deduplicated_opportunities.append(group[0])
                logger.info(f"    → No duplicates, keeping single opportunity")
            else:
                # Multiple opportunities for the same line - keep the one with best odds for other users
                # Higher absolute value of our_proposed_odds creates better opposing odds
                best_opportunity = max(group, key=lambda opp: abs(opp.our_proposed_odds))
                
                deduplicated_opportunities.append(best_opportunity)
                duplicates_removed += len(group) - 1
                
                # Log the deduplication decision
                event_name = best_opportunity.event_name
                market_type = best_opportunity.market_type
                side = best_opportunity.large_bet_side
                
                logger.info(f"🔄 Deduplicated {len(group)} opportunities for {event_name} {market_type} {side}")
                logger.info(f"   → Kept: {best_opportunity.line_info} (our_odds={best_opportunity.our_proposed_odds:+d} → creates liquidity at {(-best_opportunity.our_proposed_odds):+d})")
                
                # Log what was discarded
                discarded = [opp for opp in group if opp != best_opportunity]
                for disc_opp in discarded:
                    logger.info(f"   × Discarded: {disc_opp.line_info} (our_odds={disc_opp.our_proposed_odds:+d} → creates liquidity at {(-disc_opp.our_proposed_odds):+d})")
        
        if duplicates_removed > 0:
            logger.info(f"📊 Deduplication complete: Removed {duplicates_removed} duplicate opportunities, kept {len(deduplicated_opportunities)}")
        else:
            logger.info(f"📊 Deduplication complete: No duplicates found, kept all {len(deduplicated_opportunities)} opportunities")
        
        return deduplicated_opportunities
    
# CORRECTED version for app/services/market_scanning_service.py

    async def _get_upcoming_events(self) -> List[SportEvent]:
        """Get upcoming events for all configured sports"""
        all_events = []
        
        # Check if we have any sports configured
        if not self.sport_tournament_mapping:
            logger.error("❌ No sports configured! Check TARGET_SPORTS and tournament ID environment variables")
            return []
        
        # Fetch events for each configured sport
        for sport, tournament_id in self.sport_tournament_mapping.items():
            try:
                sport_display = self.settings.get_sport_display_name(sport)
                logger.info(f"🗓️  Fetching {sport_display} events from tournament {tournament_id}")
                
                # Get current time and scan window end
                now = datetime.now(timezone.utc)
                scan_end = now + timedelta(hours=self.scan_window_hours)
                
                logger.info(f"   Time window: {now.strftime('%Y-%m-%d %H:%M UTC')} to {scan_end.strftime('%Y-%m-%d %H:%M UTC')}")
                
                # Fetch events from ProphetX using the tournament ID
                response = await prophetx_service.get_sport_events(tournament_id)
                events_data = response.get('data', {}).get('sport_events', [])
                
                if not events_data:
                    logger.warning(f"⚠️  No {sport_display} events found for tournament {tournament_id}")
                    continue
                
                # Process events for this sport
                sport_events = []
                for event_dict in events_data:
                    try:
                        # Parse the scheduled time
                        scheduled_time_str = event_dict.get('scheduled', '')
                        if scheduled_time_str:
                            scheduled_time = datetime.fromisoformat(scheduled_time_str.replace('Z', '+00:00'))
                        else:
                            logger.debug(f"Event missing scheduled time: {event_dict.get('id', 'unknown')}")
                            continue
                        
                        # Check if event is within our scan window
                        if not (now <= scheduled_time <= scan_end):
                            continue
                        
                        # Extract team/competitor information - CORRECTED METHOD NAME
                        home_team, away_team = self._extract_team_names(event_dict)
                        
                        # Create SportEvent with ALL REQUIRED FIELDS
                        event = SportEvent(
                            event_id=str(event_dict.get('event_id', '')),
                            display_name=event_dict.get('name', f'{away_team} vs {home_team}'),
                            scheduled_time=scheduled_time,
                            home_team=home_team,
                            away_team=away_team,
                            status=event_dict.get('status', 'not_started'),
                            tournament_id=str(tournament_id),  # ← ADDED: Use the tournament_id we're querying
                            tournament_name=event_dict.get('tournament', {}).get('name', f'{sport_display} Tournament'),
                            sport_name=sport_display
                            # Note: Removed sport_name as it's not in the existing SportEvent dataclass
                        )
                        sport_events.append(event)
                        
                    except Exception as e:
                        logger.warning(f"Error parsing {sport_display} event: {e}")
                        continue
                
                logger.info(f"✅ Found {len(sport_events)} upcoming {sport_display} events")
                all_events.extend(sport_events)
                
            except Exception as e:
                logger.error(f"❌ Error fetching {sport.upper()} events from tournament {tournament_id}: {e}")
                continue
        
        # Sort all events by scheduled time
        all_events.sort(key=lambda x: x.scheduled_time)
        logger.info(f"🎯 Total events across all configured sports: {len(all_events)}")
        
        return all_events

    def _extract_team_names(self, event_dict: Dict[str, Any]) -> Tuple[str, str]:
        """Extract home and away team names from event data"""
        try:
            # Try to get from competitors array (most common structure)
            competitors = event_dict.get('competitors', [])
            home_team = "Unknown Home"
            away_team = "Unknown Away"
            
            for competitor in competitors:
                if isinstance(competitor, dict):
                    team_name = competitor.get('display_name') or competitor.get('name', 'Unknown')
                    side = competitor.get('side', '').lower()
                    
                    if side == 'home':
                        home_team = team_name
                    elif side == 'away':
                        away_team = team_name
            
            # Fallback: try direct fields
            if home_team == "Unknown Home":
                home_team = event_dict.get('home_team', event_dict.get('home_competitor', {}).get('name', 'Unknown Home'))
            if away_team == "Unknown Away":  
                away_team = event_dict.get('away_team', event_dict.get('away_competitor', {}).get('name', 'Unknown Away'))
            
            # Handle dict structures
            if isinstance(home_team, dict):
                home_team = home_team.get('name', 'Unknown Home')
            if isinstance(away_team, dict):
                away_team = away_team.get('name', 'Unknown Away')
            
            return str(home_team), str(away_team)
            
        except Exception as e:
            logger.warning(f"Error extracting team names: {e}")
            return "Unknown Home", "Unknown Away"

    def _should_process_opportunity(self, opportunity: HighWagerOpportunity, sport: str) -> bool:
        """Check if opportunity meets sport-specific thresholds"""
        # Since SportEvent doesn't have sport_name, we need to determine sport from tournament_id
        # We can pass the sport from the calling context or determine it from tournament_id
        tournament_id = getattr(opportunity, 'tournament_id', '')
        
        # Map tournament_id back to sport
        sport_from_tournament = None
        for s, tid in self.sport_tournament_mapping.items():
            if tid == tournament_id:
                sport_from_tournament = s
                break
        
        # Use the passed sport parameter or the one determined from tournament
        sport_key = sport.lower() if sport else sport_from_tournament
        
        # Get sport-specific minimum stake or use default
        min_stake = self.sport_min_stakes.get(sport_key, self.settings.min_stake_threshold)
        combined_size = opportunity.large_bet_combined_size
        
        # Check if opportunity meets the threshold for this sport
        meets_threshold = combined_size >= min_stake
        
        if not meets_threshold:
            logger.debug(f"Opportunity below {sport_key.upper()} threshold: ${combined_size:,.0f} < ${min_stake:,.0f}")
        
        return meets_threshold

    # async def _get_upcoming_events(self) -> List[SportEvent]:
    #     """Get upcoming NCAAF events in the scan window"""
    #     try:
    #         # Get current time and scan window end
    #         now = datetime.now(timezone.utc)
    #         scan_end = now + timedelta(hours=self.scan_window_hours)
            
    #         logger.info(f"🗓️  Fetching NCAAF events from {now.strftime('%Y-%m-%d %H:%M UTC')} to {scan_end.strftime('%Y-%m-%d %H:%M UTC')}")
            
    #         # Fetch events from ProphetX using the correct method
    #         response = await prophetx_service.get_sport_events(self.ncaaf_tournament_id)
    #         events_data = response.get('data', {}).get('sport_events', [])
            
    #         if not events_data:
    #             logger.warning("No sport events data returned")
    #             return []
            
    #         events = []
    #         for event_dict in events_data:
    #             try:
    #                 # Parse the scheduled time
    #                 scheduled_time_str = event_dict.get('scheduled', '')
    #                 if scheduled_time_str:
    #                     scheduled_time = datetime.fromisoformat(scheduled_time_str.replace('Z', '+00:00'))
    #                 else:
    #                     logger.warning(f"Event {event_dict.get('event_id')} has no scheduled time")
    #                     continue
                    
    #                 # Only include events in our scan window
    #                 if not (now <= scheduled_time <= scan_end):
    #                     logger.debug(f"Skipping event outside time window: {event_dict.get('display_name')} at {scheduled_time}")
    #                     continue
                    
    #                 # Extract team names from competitors
    #                 competitors = event_dict.get('competitors', [])
    #                 home_team = ""
    #                 away_team = ""
                    
    #                 for competitor in competitors:
    #                     side = competitor.get('side', '').lower()
    #                     team_name = competitor.get('display_name', competitor.get('name', ''))
                        
    #                     if side == 'home':
    #                         home_team = team_name
    #                     elif side == 'away':
    #                         away_team = team_name
                    
    #                 # Create display name if not provided
    #                 display_name = event_dict.get('display_name', f"{away_team} @ {home_team}")
                    
    #                 event = SportEvent(
    #                     event_id=str(event_dict.get('event_id', '')),
    #                     display_name=display_name,
    #                     scheduled_time=scheduled_time,
    #                     home_team=home_team,
    #                     away_team=away_team,
    #                     status=event_dict.get('status', ''),
    #                     tournament_id=str(event_dict.get('tournament_id', self.ncaaf_tournament_id)),
    #                     tournament_name=event_dict.get('tournament_name', 'NCAAF')
    #                 )
    #                 events.append(event)
                    
    #             except Exception as e:
    #                 logger.warning(f"Error parsing event {event_dict.get('event_id', 'unknown')}: {e}")
    #                 continue
            
    #         logger.info(f"📅 Found {len(events)} events in scan window")
    #         return events
            
    #     except Exception as e:
    #         logger.error(f"Error fetching upcoming events: {e}", exc_info=True)
    #         return []
    
    async def _get_market_data(self, event_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Get market data for multiple events"""
        try:
            market_data = await prophetx_service.get_multiple_markets(event_ids)
            return market_data.get('data', {})
        except Exception as e:
            logger.error(f"Error fetching market data: {e}", exc_info=True)
            return {}
    
    async def _find_high_wager_opportunities(self, events: List[SportEvent], 
                                          market_data: Dict[str, List[Dict[str, Any]]]) -> List[HighWagerOpportunity]:
        """Find high wager opportunities across all events"""
        all_opportunities = []
        
        for event in events:
            event_markets = market_data.get(event.event_id, [])
            if not event_markets:
                logger.debug(f"No market data for event {event.display_name}")
                continue
            
            opportunities = await self._scan_event_markets(event, event_markets)
            all_opportunities.extend(opportunities)
            
            if opportunities:
                logger.info(f"🎯 Event {event.display_name}: Found {len(opportunities)} opportunities")
        
        logger.info(f"📊 Total opportunities found across all events: {len(all_opportunities)}")
        return all_opportunities
    
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

                            # Use both the combined and individual thresholds
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
            # The selection with available liquidity (created by the large bet)
            available_side = liquidity_selection.get('display_name', '')
            available_odds = int(liquidity_selection.get('odds', 0))
            available_liquidity = float(liquidity_selection.get('value', 0))
            
            # The original bet details (stake represents the large bet size)
            large_bet_stake = float(liquidity_selection.get('stake', 0))
            large_bet_value = float(liquidity_selection.get('value', 0))
            combined_size = large_bet_stake + large_bet_value
            
            # CORRECTED LOGIC: The large bettor bet the OPPOSITE side of available liquidity
            large_bet_side = self._get_opposite_side_with_context(
                available_side, 
                market.get('type', ''), 
                event.home_team, 
                event.away_team
            )
            
            # The large bettor got the opposite odds of what's available
            large_bet_odds = -available_odds if available_odds > 0 else abs(available_odds)
            
            # OUR STRATEGY: Bet the same side as large bettor, but at worse odds for us
            our_proposed_odds = self._find_next_valid_odds(large_bet_odds, better_for_bettor=False)
            
            # Extract line information
            line_info = self._extract_line_info(market, available_side)
            
            # FIXED: Find the line_id for the side we want to bet on (large_bet_side)
            line_id_for_betting = None
            market_id_for_arbitrage = str(market.get('id', ''))
            
            # Search through all selections to find the one matching large_bet_side
            for side_group in selections:
                if not side_group:
                    continue
                for selection in side_group:
                    selection_name = selection.get('display_name', '').strip()
                    
                    # Check if this selection matches the large_bet_side
                    if self._is_same_side(selection_name, large_bet_side, market.get('type', '')):
                        line_id_for_betting = str(selection.get('line_id', ''))
                        logger.info(f"✅ Found betting line_id: {line_id_for_betting} for {large_bet_side}")
                        break
                if line_id_for_betting:
                    break
            
            # Validation
            if not line_id_for_betting:
                logger.error(f"❌ Could not find line_id for large_bet_side '{large_bet_side}' in selections")
                logger.error(f"   Available selections: {[s.get('display_name') for side_group in selections for s in side_group if s]}")
                return None
                
            if not market_id_for_arbitrage:
                logger.error(f"No market_id found in market: {market}")
                return None

            logger.debug(f"Creating opportunity: market_id={market_id_for_arbitrage}, line_id={line_id_for_betting}, betting_on={large_bet_side}")
            
            return HighWagerOpportunity(
                event_id=event.event_id,
                event_name=event.display_name,
                scheduled_time=event.scheduled_time,
                tournament_name=event.tournament_name,
                market_id=market_id_for_arbitrage,     # For arbitrage detection (market ID)
                line_id=line_id_for_betting,          # For bet placement (correct team's line_id)
                market_name=market.get('category_name', ''),
                market_type=market.get('type', ''),
                line_info=line_info,
                large_bet_side=large_bet_side,        # Who we're betting on
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
        
    def _is_same_side(self, selection_name: str, target_side: str, market_type: str) -> bool:
        """Check if a selection name matches the target side we want to bet on"""
        
        # Clean both names for comparison
        selection_clean = selection_name.lower().strip()
        target_clean = target_side.lower().strip()
        
        # Direct match - this should catch most cases
        if selection_clean == target_clean:
            return True
        
        # Special handling for totals markets to distinguish Over vs Under
        market_type_lower = market_type.lower()
        if market_type_lower in ['total', 'totals']:
            # For totals, we need to match both the direction (Over/Under) AND the line value
            target_is_over = 'over' in target_clean
            target_is_under = 'under' in target_clean
            selection_is_over = 'over' in selection_clean
            selection_is_under = 'under' in selection_clean
            
            # Must match the Over/Under direction
            if target_is_over and not selection_is_over:
                return False
            if target_is_under and not selection_is_under:
                return False
            if selection_is_over and not target_is_over:
                return False
            if selection_is_under and not target_is_under:
                return False
            
            # If directions match, check if the line values match
            import re
            target_numbers = re.findall(r'\d+(?:\.\d+)?', target_clean)
            selection_numbers = re.findall(r'\d+(?:\.\d+)?', selection_clean)
            
            # Both should have exactly one number (the line value)
            if len(target_numbers) == 1 and len(selection_numbers) == 1:
                return target_numbers[0] == selection_numbers[0]
            
            # If we can't extract numbers properly, fall back to exact match
            return selection_clean == target_clean
        
        # For team names and spread markets, check if team name is contained in selection
        # Handle cases like "TCU Horned Frogs" vs "TCU Horned Frogs -1.5"
        target_words = [word for word in target_clean.split() if len(word) > 2]
        
        # Check if significant words from target are in selection
        if target_words and any(word in selection_clean for word in target_words):
            # Additional validation for spread markets
            if market_type_lower == 'spread':
                # For spreads, also check that the spread direction matches if present
                import re
                target_spread = re.findall(r'[+-]\d+(?:\.\d+)?', target_clean)
                selection_spread = re.findall(r'[+-]\d+(?:\.\d+)?', selection_clean)
                
                # If both have spreads, they must match
                if target_spread and selection_spread:
                    return target_spread[0] == selection_spread[0]
            
            return True
        
        # Check if target is contained in selection (like "TCU" in "TCU Horned Frogs")  
        if target_clean in selection_clean or selection_clean in target_clean:
            return True
            
        return False
        
    def _calculate_undercut_odds(self, original_odds: int) -> int:
        """Calculate our undercut odds using ProphetX odds ladder - DEPRECATED"""
        # This method is deprecated - use _find_next_valid_odds instead
        return self._find_next_valid_odds(original_odds, better_for_bettor=True)
    
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
                    return "0"
            else:
                # Try to extract from selection name
                if 'spread' in selection_side.lower() or any(char in selection_side for char in ['+', '-']):
                    return selection_side
                return "Unknown Spread"
        
        elif market_type in ['total', 'totals']:
            # For totals, show Over/Under with line value
            if 'line_value' in market:
                line_val = market.get('line_value', 0)
                over_under = "Over" if "over" in selection_side.lower() else "Under"
                return f"{over_under} {line_val}"
            else:
                # Try to extract from selection name
                return selection_side
        
        else:
            # For moneyline, just return the team name
            return selection_side
    
    def _get_opposite_side(self, available_side: str, market_type: str) -> str:
        """Determine the opposite side that placed the large bet"""
        market_type = market_type.lower()
        
        if market_type == 'moneyline':
            # For moneylines, extract the team name and find the opposite team
            # available_side might be "Charlotte 49ers" or similar
            return f"vs {available_side}"
        
        elif market_type == 'spread':
            # For spreads, we need to find the opposite team with opposite spread
            # available_side might be "Central Michigan Chippewas +14"
            # We need to return "San Jose State Spartans -14"
            
            # Try to extract the spread value and team
            import re
            
            # Look for team name and spread (e.g., "Central Michigan Chippewas +14")
            spread_match = re.search(r'(.+?)\s*([+-]\d+(?:\.\d+)?)', available_side.strip())
            
            if spread_match:
                team_with_spread = spread_match.group(1).strip()
                spread_value = spread_match.group(2)
                
                # Flip the spread sign
                if spread_value.startswith('+'):
                    opposite_spread = spread_value.replace('+', '-')
                elif spread_value.startswith('-'):
                    opposite_spread = spread_value.replace('-', '+')
                else:
                    opposite_spread = f"-{spread_value}"
                
                # Try to determine the opposite team name from the available team
                # This is tricky without knowing both team names, so we'll make a best guess
                if "central michigan" in team_with_spread.lower():
                    opposite_team = "San Jose State Spartans"
                elif "san jose state" in team_with_spread.lower():
                    opposite_team = "Central Michigan Chippewas"
                else:
                    # Fallback - try to extract from event context if possible
                    # For now, use a generic opposite
                    opposite_team = f"Opponent of {team_with_spread}"
                
                return f"{opposite_team} {opposite_spread}"
            else:
                # Fallback if we can't parse the spread
                return f"Opposite of {available_side}"
        
        elif market_type in ['total', 'totals']:
            # For totals, it's Over vs Under with same number
            if 'over' in available_side.lower():
                return available_side.replace('Over', 'Under').replace('over', 'Under')
            elif 'under' in available_side.lower():
                return available_side.replace('Under', 'Over').replace('under', 'Over')
            else:
                return f"Opposite of {available_side}"
        
        return f"Opposite of {available_side}"
    
    def _get_opposite_side_with_context(self, available_side: str, market_type: str, 
                                      home_team: str, away_team: str) -> str:
        """
        Determine the opposite side with event context for better team name resolution
        """
        market_type = market_type.lower()
        
        if market_type == 'moneyline':
            # For moneylines, if available_side matches one team, return the other team directly
            # No "vs" prefix needed - just the team name
            if home_team.lower() in available_side.lower():
                return away_team
            elif away_team.lower() in available_side.lower():
                return home_team
            else:
                # Fallback - try to extract team name from available_side and find opposite
                # Remove any odds info (like "+140") to get clean team name
                import re
                team_match = re.match(r'^(.+?)\s*[+-]\d+', available_side)
                if team_match:
                    clean_team_name = team_match.group(1).strip()
                    if home_team.lower() in clean_team_name.lower():
                        return away_team
                    elif away_team.lower() in clean_team_name.lower():
                        return home_team
                
                # Last fallback
                return f"vs {available_side}"
        
        elif market_type == 'spread':
            # For spreads with team context
            import re
            
            # Extract spread value
            spread_match = re.search(r'([+-]\d+(?:\.\d+)?)', available_side)
            
            if spread_match:
                spread_value = spread_match.group(1)
                
                # Flip the spread sign
                if spread_value.startswith('+'):
                    opposite_spread = spread_value.replace('+', '-')
                elif spread_value.startswith('-'):
                    opposite_spread = spread_value.replace('-', '+')
                else:
                    opposite_spread = f"-{spread_value}"
                
                # Determine which team is in available_side and use the other
                if home_team.lower() in available_side.lower():
                    return f"{away_team} {opposite_spread}"
                elif away_team.lower() in available_side.lower():
                    return f"{home_team} {opposite_spread}"
                else:
                    # Fallback
                    return f"Opposite team {opposite_spread}"
            else:
                return f"Opposite of {available_side}"
        
        elif market_type in ['total', 'totals']:
            # For totals, it's Over vs Under
            if 'over' in available_side.lower():
                return available_side.replace('Over', 'Under').replace('over', 'Under')
            elif 'under' in available_side.lower():
                return available_side.replace('Under', 'Over').replace('under', 'Over')
            else:
                return f"Opposite of {available_side}"
        
        return f"Opposite of {available_side}"


# Create global service instance
market_scanning_service = MarketScanningService()