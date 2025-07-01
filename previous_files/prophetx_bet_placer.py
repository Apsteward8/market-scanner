#!/usr/bin/env python3
"""
ProphetX Bet Placement Module
Handles placing bets through the ProphetX API
"""

import requests
import json
import time
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from prophetx_auth import ProphetXAuth

class ProphetXBetPlacer:
    """Handles bet placement for ProphetX"""
    
    def __init__(self, auth: ProphetXAuth, sandbox: bool = True):
        """
        Initialize the bet placer
        
        Args:
            auth: ProphetXAuth instance for authentication
            sandbox: Use sandbox environment
        """
        self.auth = auth
        
        if sandbox:
            self.base_url = "https://api-ss-sandbox.betprophet.co"
        else:
            self.base_url = "https://api-ss.betprophet.co"
        
        # Configuration
        self.default_bet_size = 5.0  # $5 test bets
        self.dry_run = False  # Set to True to simulate bets without placing them
        
        # Tracking
        self.placed_bets = []
        self.failed_bets = []
        
    def generate_external_id(self, opportunity: Dict) -> str:
        """
        Generate a unique external ID for a bet
        
        Args:
            opportunity: Opportunity dictionary containing bet details (new structure)
            
        Returns:
            str: Unique external ID (numbers, letters, -, . only)
        """
        # Create a unique ID using timestamp and some opportunity details
        timestamp = int(time.time() * 1000)  # Milliseconds for uniqueness
        event_id = opportunity.get('event_id', 0)
        market_id = opportunity.get('market_id', 0)
        
        # Format: event_market_timestamp
        external_id = f"{event_id}-{market_id}-{timestamp}"
        
        return external_id
    
    def place_bet(self, opportunity: Dict, bet_size: Optional[float] = None) -> Dict:
        """
        Place a single bet based on an opportunity
        
        Args:
            opportunity: Opportunity dictionary from scanner (new structure)
            bet_size: Bet size in dollars (uses default if None)
            
        Returns:
            dict: Result of bet placement
        """
        if bet_size is None:
            bet_size = self.default_bet_size
        
        # Extract required fields from NEW opportunity structure
        bet_placement = opportunity.get('bet_placement', {})
        line_id = bet_placement.get('line_id')
        odds = bet_placement.get('odds')
        original_bet = opportunity.get('original_bet', {})
        our_bet = opportunity.get('our_bet', {})
        
        if not line_id or odds is None:
            return {
                'success': False,
                'error_message': 'Missing required bet placement data',
                'opportunity': opportunity
            }
        
        external_id = self.generate_external_id(opportunity)
        
        # Prepare bet data
        bet_data = {
            "external_id": external_id,
            "line_id": line_id,
            "odds": odds,
            "stake": bet_size
        }
        
        # Enhanced logging for follow-the-money strategy
        print(f"🎯 FOLLOWING THE MONEY:")
        print(f"   📊 Original bet: {original_bet.get('display', 'Unknown')}")
        print(f"   💰 Our follow bet: {our_bet.get('display', 'Unknown')}")
        print(f"   🎲 Bet details:")
        print(f"      External ID: {external_id}")
        print(f"      Line ID: {line_id}")
        print(f"      Odds: {odds:+d}")
        print(f"      Stake: ${bet_size}")
        
        if self.dry_run:
            print("   🧪 DRY RUN - Bet simulation only")
            result = {
                'success': True,
                'bet_id': f"dry_run_{external_id}",
                'external_id': external_id,
                'message': 'Dry run - bet simulated',
                'bet_data': bet_data,
                'opportunity': opportunity
            }
            self.placed_bets.append(result)
            return result
        
        # Place the actual bet
        url = f"{self.base_url}/partner/mm/place_wager"
        headers = self.auth.get_auth_headers()
        
        try:
            response = requests.post(url, headers=headers, json=bet_data)
            
            if response.status_code == 200 or response.status_code == 201:
                # Successful bet placement
                response_data = response.json()
                
                result = {
                    'success': True,
                    'bet_id': response_data.get('id', external_id),
                    'external_id': external_id,
                    'response': response_data,
                    'bet_data': bet_data,
                    'opportunity': opportunity,
                    'placed_at': datetime.now().isoformat()
                }
                
                self.placed_bets.append(result)
                print(f"   ✅ Follow bet placed successfully!")
                
                return result
                
            else:
                # Failed bet placement
                error_msg = response.text
                print(f"   ❌ Bet placement failed: {response.status_code}")
                print(f"   Error: {error_msg}")
                
                result = {
                    'success': False,
                    'error_code': response.status_code,
                    'error_message': error_msg,
                    'external_id': external_id,
                    'bet_data': bet_data,
                    'opportunity': opportunity,
                    'failed_at': datetime.now().isoformat()
                }
                
                self.failed_bets.append(result)
                return result
                
        except Exception as e:
            print(f"   💥 Exception placing bet: {e}")
            
            result = {
                'success': False,
                'error_message': str(e),
                'external_id': external_id,
                'bet_data': bet_data,
                'opportunity': opportunity,
                'failed_at': datetime.now().isoformat()
            }
            
            self.failed_bets.append(result)
            return result
    
    def place_multiple_bets(self, opportunities: List[Dict], bet_size: Optional[float] = None, 
                           delay_seconds: float = 1.0) -> Dict:
        """
        Place bets for multiple opportunities
        
        Args:
            opportunities: List of opportunity dictionaries
            bet_size: Bet size for all bets (uses default if None)
            delay_seconds: Delay between bet placements
            
        Returns:
            dict: Summary of bet placement results
        """
        if not opportunities:
            return {'total': 0, 'successful': 0, 'failed': 0, 'results': []}
        
        print(f"\n🚀 FOLLOWING {len(opportunities)} LARGE BETS...")
        print("=" * 60)
        
        results = []
        successful_count = 0
        failed_count = 0
        
        for i, opportunity in enumerate(opportunities, 1):
            event_name = opportunity.get('event_name', 'Unknown Event')
            original_bet = opportunity.get('original_bet', {})
            
            print(f"\n[{i}/{len(opportunities)}] {event_name}")
            print(f"   Following: {original_bet.get('display', 'Unknown bet')}")
            
            # Place the bet
            result = self.place_bet(opportunity, bet_size)
            results.append(result)
            
            if result['success']:
                successful_count += 1
            else:
                failed_count += 1
            
            # Delay between bets (be nice to the API)
            if i < len(opportunities):
                time.sleep(delay_seconds)
        
        summary = {
            'total': len(opportunities),
            'successful': successful_count,
            'failed': failed_count,
            'results': results,
            'bet_size_used': bet_size or self.default_bet_size
        }
        
        print(f"\n📊 FOLLOW-THE-MONEY SUMMARY:")
        print(f"   Total follow opportunities: {summary['total']}")
        print(f"   ✅ Successfully followed: {summary['successful']}")
        print(f"   ❌ Failed to follow: {summary['failed']}")
        print(f"   💰 Bet size used: ${summary['bet_size_used']}")
        
        return summary
    
    def get_placement_stats(self) -> Dict:
        """
        Get statistics about bet placements
        
        Returns:
            dict: Placement statistics
        """
        total_placed = len(self.placed_bets)
        total_failed = len(self.failed_bets)
        total_stake = sum(bet['bet_data']['stake'] for bet in self.placed_bets)
        
        return {
            'total_attempts': total_placed + total_failed,
            'successful_bets': total_placed,
            'failed_bets': total_failed,
            'success_rate': (total_placed / (total_placed + total_failed)) * 100 if (total_placed + total_failed) > 0 else 0,
            'total_stake_placed': total_stake,
            'average_stake': total_stake / total_placed if total_placed > 0 else 0
        }
    
    def save_bet_log(self, filename: Optional[str] = None) -> str:
        """
        Save bet placement log to file
        
        Args:
            filename: Optional filename (auto-generated if None)
            
        Returns:
            str: Filename where log was saved
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"prophetx_bet_log_{timestamp}.json"
        
        log_data = {
            'statistics': self.get_placement_stats(),
            'successful_bets': self.placed_bets,
            'failed_bets': self.failed_bets,
            'generated_at': datetime.now().isoformat()
        }
        
        with open(filename, 'w') as f:
            json.dump(log_data, f, indent=2, default=str)
        
        return filename
    
    def set_dry_run(self, enabled: bool):
        """Enable or disable dry run mode"""
        self.dry_run = enabled
        print(f"🧪 Dry run mode: {'ENABLED' if enabled else 'DISABLED'}")
    
    def set_default_bet_size(self, size: float):
        """Set the default bet size"""
        self.default_bet_size = size
        print(f"💰 Default bet size set to: ${size}")

def test_bet_placer():
    """Test the bet placer with a mock opportunity"""
    print("ProphetX Bet Placer Test")
    print("=" * 40)
    
    # This is just for testing the module structure
    # In real usage, this would come from the scanner
    mock_opportunity = {
        'event_id': 12345,
        'event_name': 'Test Game',
        'market_name': 'Moneyline',
        'market_id': 251,
        'selection_info': {
            'line_id': 'test_line_id_12345',
            'competitor_id': 100,
            'outcome_id': 4
        },
        'display_name': 'Test Team +120',
        'our_odds': 120,
        'their_odds': 122,
        'their_stake': 5000,
        'our_bet_size': 5.0
    }
    
    # Mock auth (would use real auth in practice)
    class MockAuth:
        def get_auth_headers(self):
            return {'Authorization': 'Bearer mock_token', 'Content-Type': 'application/json'}
    
    # Create bet placer in dry run mode
    auth = MockAuth()
    placer = ProphetXBetPlacer(auth)
    placer.set_dry_run(True)  # Safe testing
    
    # Test single bet placement
    print("Testing single bet placement...")
    result = placer.place_bet(mock_opportunity)
    
    print(f"\nResult: {'✅ Success' if result['success'] else '❌ Failed'}")
    print(f"External ID: {result['external_id']}")
    
    # Test multiple bet placement
    print("\nTesting multiple bet placement...")
    opportunities = [mock_opportunity] * 3  # Three identical opportunities
    summary = placer.place_multiple_bets(opportunities)
    
    # Show stats
    stats = placer.get_placement_stats()
    print(f"\nStatistics:")
    print(f"  Success rate: {stats['success_rate']:.1f}%")
    print(f"  Total stake: ${stats['total_stake_placed']:.2f}")

if __name__ == "__main__":
    test_bet_placer()