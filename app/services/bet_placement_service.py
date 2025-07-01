#!/usr/bin/env python3
"""
Bet Placement Service
Handles placing bets through the ProphetX API
"""

import requests
import time
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import HTTPException

from app.core.config import get_settings
from app.services.auth_service import auth_service
from app.models.responses import BettingOpportunity, BetResult, BetPlacementSummary

class BetPlacementService:
    """Service for placing bets on ProphetX"""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.prophetx_base_url
        
        # Configuration
        self.default_bet_size = self.settings.default_bet_size
        self.dry_run = self.settings.dry_run_mode
        
        # Tracking
        self.placed_bets: List[Dict] = []
        self.failed_bets: List[Dict] = []
    
    def set_dry_run(self, enabled: bool) -> None:
        """Enable or disable dry run mode"""
        self.dry_run = enabled
    
    def set_default_bet_size(self, size: float) -> None:
        """Set the default bet size"""
        self.default_bet_size = size
    
    def generate_external_id(self, opportunity: BettingOpportunity) -> str:
        """
        Generate a unique external ID for a bet
        
        Args:
            opportunity: Betting opportunity containing bet details
            
        Returns:
            str: Unique external ID (numbers, letters, -, . only)
        """
        timestamp = int(time.time() * 1000)  # Milliseconds for uniqueness
        event_id = opportunity.event_id
        market_id = opportunity.market_id or 0
        
        # Format: event_market_timestamp
        external_id = f"{event_id}-{market_id}-{timestamp}"
        
        return external_id
    
    async def place_single_bet(
        self, 
        opportunity: BettingOpportunity, 
        bet_size: Optional[float] = None
    ) -> BetResult:
        """
        Place a single bet based on an opportunity
        
        Args:
            opportunity: Betting opportunity from scanner
            bet_size: Bet size in dollars (uses default if None)
            
        Returns:
            BetResult: Result of bet placement
        """
        if bet_size is None:
            bet_size = self.default_bet_size
        
        # Extract required fields from opportunity
        bet_placement = opportunity.bet_placement
        line_id = bet_placement.line_id
        odds = bet_placement.odds
        
        if not line_id or odds is None:
            return BetResult(
                success=False,
                external_id=self.generate_external_id(opportunity),
                error_message='Missing required bet placement data (line_id or odds)',
                bet_data=None
            )
        
        external_id = self.generate_external_id(opportunity)
        
        # Prepare bet data
        bet_data = {
            "external_id": external_id,
            "line_id": line_id,
            "odds": odds,
            "stake": bet_size
        }
        
        # Log the follow-the-money action
        print(f"🎯 FOLLOWING THE MONEY:")
        print(f"   📊 Original bet: {opportunity.original_bet.display}")
        print(f"   💰 Our follow bet: {opportunity.our_bet.display}")
        print(f"   🎲 Bet details: {external_id}, odds: {odds:+d}, stake: ${bet_size}")
        
        if self.dry_run:
            print("   🧪 DRY RUN - Bet simulation only")
            result = BetResult(
                success=True,
                bet_id=f"dry_run_{external_id}",
                external_id=external_id,
                error_message=None,
                bet_data=bet_data,
                placed_at=datetime.now().isoformat()
            )
            self.placed_bets.append(result.dict())
            return result
        
        # Place the actual bet
        url = f"{self.base_url}/partner/mm/place_wager"
        
        try:
            headers = await auth_service.get_auth_headers()
            response = requests.post(url, headers=headers, json=bet_data)
            
            if response.status_code in [200, 201]:
                # Successful bet placement
                response_data = response.json()
                
                result = BetResult(
                    success=True,
                    bet_id=response_data.get('id', external_id),
                    external_id=external_id,
                    error_message=None,
                    bet_data=bet_data,
                    placed_at=datetime.now().isoformat()
                )
                
                self.placed_bets.append(result.dict())
                print(f"   ✅ Follow bet placed successfully! Bet ID: {result.bet_id}")
                
                return result
                
            else:
                # Failed bet placement
                error_msg = response.text
                print(f"   ❌ Bet placement failed: {response.status_code}")
                print(f"   Error: {error_msg}")
                
                result = BetResult(
                    success=False,
                    bet_id=None,
                    external_id=external_id,
                    error_message=f"HTTP {response.status_code}: {error_msg}",
                    bet_data=bet_data,
                    placed_at=None
                )
                
                self.failed_bets.append(result.dict())
                return result
                
        except requests.exceptions.RequestException as e:
            print(f"   💥 Network error placing bet: {e}")
            
            result = BetResult(
                success=False,
                bet_id=None,
                external_id=external_id,
                error_message=f"Network error: {str(e)}",
                bet_data=bet_data,
                placed_at=None
            )
            
            self.failed_bets.append(result.dict())
            return result
        
        except Exception as e:
            print(f"   💥 Unexpected error placing bet: {e}")
            
            result = BetResult(
                success=False,
                bet_id=None,
                external_id=external_id,
                error_message=f"Unexpected error: {str(e)}",
                bet_data=bet_data,
                placed_at=None
            )
            
            self.failed_bets.append(result.dict())
            return result
    
    async def place_multiple_bets(
        self, 
        opportunities: List[BettingOpportunity], 
        bet_size: Optional[float] = None,
        delay_seconds: float = 1.0
    ) -> BetPlacementSummary:
        """
        Place bets for multiple opportunities
        
        Args:
            opportunities: List of betting opportunities
            bet_size: Bet size for all bets (uses default if None)
            delay_seconds: Delay between bet placements
            
        Returns:
            BetPlacementSummary: Summary of bet placement results
        """
        if not opportunities:
            return BetPlacementSummary(
                total=0,
                successful=0,
                failed=0,
                bet_size_used=bet_size or self.default_bet_size,
                results=[]
            )
        
        print(f"\n🚀 FOLLOWING {len(opportunities)} LARGE BETS...")
        print("=" * 60)
        
        results = []
        successful_count = 0
        failed_count = 0
        
        for i, opportunity in enumerate(opportunities, 1):
            print(f"\n[{i}/{len(opportunities)}] {opportunity.event_name}")
            print(f"   Following: {opportunity.original_bet.display}")
            
            # Place the bet
            result = await self.place_single_bet(opportunity, bet_size)
            results.append(result)
            
            if result.success:
                successful_count += 1
            else:
                failed_count += 1
            
            # Delay between bets (be nice to the API)
            if i < len(opportunities):
                time.sleep(delay_seconds)
        
        summary = BetPlacementSummary(
            total=len(opportunities),
            successful=successful_count,
            failed=failed_count,
            bet_size_used=bet_size or self.default_bet_size,
            results=results
        )
        
        print(f"\n📊 FOLLOW-THE-MONEY SUMMARY:")
        print(f"   Total follow opportunities: {summary.total}")
        print(f"   ✅ Successfully followed: {summary.successful}")
        print(f"   ❌ Failed to follow: {summary.failed}")
        print(f"   💰 Bet size used: ${summary.bet_size_used}")
        
        return summary
    
    def get_placement_stats(self) -> Dict:
        """
        Get statistics about bet placements
        
        Returns:
            dict: Placement statistics
        """
        total_placed = len(self.placed_bets)
        total_failed = len(self.failed_bets)
        total_stake = sum(
            bet.get('bet_data', {}).get('stake', 0) 
            for bet in self.placed_bets 
            if bet.get('bet_data')
        )
        
        return {
            'total_attempts': total_placed + total_failed,
            'successful_bets': total_placed,
            'failed_bets': total_failed,
            'success_rate': (total_placed / (total_placed + total_failed)) * 100 if (total_placed + total_failed) > 0 else 0,
            'total_stake_placed': total_stake,
            'average_stake': total_stake / total_placed if total_placed > 0 else 0
        }
    
    def get_bet_history(self) -> Dict:
        """
        Get complete bet history
        
        Returns:
            dict: Complete bet history with statistics
        """
        return {
            'statistics': self.get_placement_stats(),
            'successful_bets': self.placed_bets,
            'failed_bets': self.failed_bets,
            'generated_at': datetime.now().isoformat()
        }
    
    def clear_history(self) -> None:
        """Clear bet placement history"""
        self.placed_bets.clear()
        self.failed_bets.clear()
    
    async def get_bet_status(self, bet_id: str) -> Optional[Dict]:
        """
        Get status of a specific bet from ProphetX
        
        Args:
            bet_id: Bet ID to check status for
            
        Returns:
            dict: Bet status information or None if not found
        """
        if self.dry_run:
            # In dry run mode, simulate bet status
            return {
                "bet_id": bet_id,
                "status": "simulated",
                "message": "Dry run mode - bet was simulated",
                "is_dry_run": True
            }
        
        # This would require a ProphetX API endpoint to check bet status
        # For now, return None as this endpoint may not be available
        return None
    
    async def cancel_bet(self, bet_id: str) -> Dict:
        """
        Cancel a specific bet (if supported by ProphetX)
        
        Args:
            bet_id: Bet ID to cancel
            
        Returns:
            dict: Cancellation result
        """
        if self.dry_run:
            return {
                "success": True,
                "message": "Dry run mode - bet cancellation simulated",
                "bet_id": bet_id,
                "is_dry_run": True
            }
        
        # This would require a ProphetX API endpoint to cancel bets
        # For now, return not supported
        return {
            "success": False,
            "message": "Bet cancellation not currently supported",
            "bet_id": bet_id
        }

# Global bet placement service instance
bet_placement_service = BetPlacementService()