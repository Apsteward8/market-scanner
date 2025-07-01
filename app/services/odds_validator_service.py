#!/usr/bin/env python3
"""
Odds Validator Service
Handles odds validation and undercut calculations for ProphetX
"""

from typing import Optional, Dict

class OddsValidatorService:
    """Service for validating odds and calculating undercuts"""
    
    VALID_ODDS = [
        -10000, -7500, -5000, -4500, -4000, -3500, -3000, -2750, -2500, -2250,
        -2000, -1900, -1800, -1700, -1600, -1500, -1400, -1300, -1200, -1100,
        -1000, -980, -960, -940, -920, -900, -880, -860, -840, -820, -800,
        -780, -760, -740, -720, -700, -680, -660, -640, -620, -600, -580,
        -560, -540, -520, -500, -490, -480, -470, -460, -450, -440, -430,
        -420, -410, -400, -390, -380, -370, -360, -350, -340, -330, -320,
        -310, -300, -295, -290, -285, -280, -275, -270, -265, -260, -255,
        -250, -245, -240, -235, -230, -225, -220, -215, -210, -205, -200,
        -198, -196, -194, -192, -190, -188, -186, -184, -182, -180, -178,
        -176, -174, -172, -170, -168, -166, -164, -162, -160, -158, -156,
        -154, -152, -150, -148, -146, -144, -142, -140, -138, -136, -134,
        -132, -130, -128, -126, -124, -122, -120, -119, -118, -117, -116,
        -115, -114, -113, -112, -111, -110, -109, -108, -107, -106, -105,
        -104, -103, -102, -101,
        100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112,
        113, 114, 115, 116, 117, 118, 119, 120, 122, 124, 126, 128, 130,
        132, 134, 136, 138, 140, 142, 144, 146, 148, 150, 152, 154, 156,
        158, 160, 162, 164, 166, 168, 170, 172, 174, 176, 178, 180, 182,
        184, 186, 188, 190, 192, 194, 196, 198, 200, 205, 210, 215, 220,
        225, 230, 235, 240, 245, 250, 255, 260, 265, 270, 275, 280, 285,
        290, 295, 300, 310, 320, 330, 340, 350, 360, 370, 380, 390, 400,
        410, 420, 430, 440, 450, 460, 470, 480, 490, 500, 520, 540, 560,
        580, 600, 620, 640, 660, 680, 700, 720, 740, 760, 780, 800, 820,
        840, 860, 880, 900, 920, 940, 960, 980, 1000, 1100, 1200, 1300,
        1400, 1500, 1600, 1700, 1800, 1900, 2000, 2250, 2500, 2750, 3000,
        3500, 4000, 4500, 5000, 7500, 10000
    ]
    
    def __init__(self):
        # Create sorted sets for faster lookups
        self.valid_odds_set = set(self.VALID_ODDS)
        self.positive_odds = sorted([odd for odd in self.VALID_ODDS if odd > 0])
        self.negative_odds = sorted([odd for odd in self.VALID_ODDS if odd < 0], reverse=True)
    
    def is_valid_odd(self, odds: int) -> bool:
        """
        Check if an odd is valid for ProphetX
        
        Args:
            odds: Odds value to check
            
        Returns:
            bool: True if valid, False otherwise
        """
        return odds in self.valid_odds_set
    
    def calculate_undercut_odds(self, original_odds: int, undercut_amount: int = 1) -> Optional[int]:
        """
        Calculate undercut odds to offer better market odds
        
        BETTING EXCHANGE LOGIC:
        - When someone bets -138, they're offering +138 to the market
        - To undercut them, we offer better than +138 (like +140) 
        - To offer +140, we must take -140
        - So undercutting -138 means we take -140 (worse for us, better for market)
        
        Args:
            original_odds: The original odds being offered
            undercut_amount: How aggressively to undercut (1 = minimal)
            
        Returns:
            int: Our odds that will offer better to the market, or None if no valid undercut found
        """
        if not self.is_valid_odd(original_odds):
            return None
        
        if original_odds > 0:
            # They bet +120, offering -120 to market
            # We want to offer better than -120 (like -118)
            # To offer -118, we take +118
            return self._find_undercut_for_positive_bet(original_odds, undercut_amount)
        else:
            # They bet -138, offering +138 to market  
            # We want to offer better than +138 (like +140)
            # To offer +140, we take -140
            return self._find_undercut_for_negative_bet(original_odds, undercut_amount)
    
    def _find_undercut_for_positive_bet(self, original_odds: int, undercut_amount: int) -> Optional[int]:
        """
        Undercut a positive odds bet
        
        They bet +120 (offering -120 to market)
        We want to offer better than -120 (like -118) 
        To offer -118, we take +118
        """
        # Special case: +100 must cross to negative side
        if original_odds == 100:
            return -101
        
        # For other positive odds, try to go one step lower first
        if original_odds in self.positive_odds:
            original_index = self.positive_odds.index(original_odds)
            
            # Try to go one step lower (better market offering)
            if original_index > 0:
                candidate = self.positive_odds[original_index - 1]
                
                # If we hit +100, that's as low as we can go on positive side
                if candidate == 100:
                    return candidate
                
                return candidate
        
        # If we can't find a better positive odd, cross to negative side
        return -101
    
    def _find_undercut_for_negative_bet(self, original_odds: int, undercut_amount: int) -> Optional[int]:
        """
        Undercut a negative odds bet
        
        They bet -138 (offering +138 to market)
        We want to offer better than +138 (like +140)
        To offer +140, we take -140  
        """
        if original_odds not in self.negative_odds:
            return None
            
        original_index = self.negative_odds.index(original_odds)
        
        # Look for more negative odds (further from 0)
        # This offers better positive odds to the market
        if original_index < len(self.negative_odds) - 1:
            # Go one step more negative
            return self.negative_odds[original_index + 1]
        
        return None
    
    def explain_undercut(self, original_odds: int, undercut_odds: int) -> str:
        """
        Explain why the undercut makes sense in betting exchange terms
        
        Args:
            original_odds: Original odds (what they bet)
            undercut_odds: Our undercut odds (what we bet)
            
        Returns:
            str: Explanation of the undercut in market terms
        """
        if original_odds == 100 and undercut_odds == -101:
            return "They bet +100 (offering -100), we cross to -101 (offering +101) - better for bettors since +99 invalid"
        elif original_odds > 0 and undercut_odds > 0:
            # They bet +101 (offering -101), we bet +100 (offering -100) 
            their_offering = -original_odds
            our_offering = -undercut_odds
            return f"They offer {their_offering} to market, we offer {our_offering} (better for bettors)"
        elif original_odds > 0 and undercut_odds < 0:
            # Cross from positive to negative
            their_offering = -original_odds  
            our_offering = abs(undercut_odds)
            return f"They offer {their_offering} to market, we offer +{our_offering} (crossed sides, better for bettors)"
        elif original_odds < 0 and undercut_odds < 0:
            # They bet -138 (offering +138), we bet -140 (offering +140)
            their_offering = abs(original_odds)
            our_offering = abs(undercut_odds)
            return f"They offer +{their_offering} to market, we offer +{our_offering} (better for bettors)"
        elif original_odds < 0 and undercut_odds > 0:
            # They bet -101 (offering +101), we bet +100 (offering -100)  
            their_offering = abs(original_odds)
            our_offering = -undercut_odds
            return f"They offer +{their_offering} to market, we offer {our_offering} (crossed sides, better for bettors)"
        else:
            return f"Undercut from {original_odds} to {undercut_odds}"
    
    def calculate_profit_metrics(self, original_odds: int, undercut_odds: int, bet_size: float) -> Dict[str, float]:
        """
        Calculate profit metrics for an undercut bet
        
        Args:
            original_odds: Original odds being undercut
            undercut_odds: Our undercut odds
            bet_size: How much we're betting
            
        Returns:
            dict: Profit calculations
        """
        if undercut_odds > 0:
            # Positive odds: bet_size * (odds / 100) = potential_win
            potential_win = bet_size * (undercut_odds / 100)
        else:
            # Negative odds: bet_size * (100 / abs(odds)) = potential_win
            potential_win = bet_size * (100 / abs(undercut_odds))
        
        potential_profit = potential_win - bet_size
        roi_percent = (potential_profit / bet_size) * 100 if bet_size > 0 else 0
        
        return {
            'bet_size': bet_size,
            'potential_win': potential_win,
            'potential_profit': potential_profit,
            'roi_percent': roi_percent,
            'is_profitable': potential_profit > 0
        }
    
    def get_valid_odds_around(self, target_odds: int, count: int = 10) -> Dict[str, list]:
        """
        Get valid odds around a target value
        
        Args:
            target_odds: Target odds value
            count: Number of odds to return on each side
            
        Returns:
            dict: Lists of odds before and after target
        """
        if target_odds > 0:
            odds_list = self.positive_odds
        else:
            odds_list = self.negative_odds
        
        # Find closest valid odd
        if target_odds not in self.valid_odds_set:
            target_odds = min(odds_list, key=lambda x: abs(x - target_odds))
        
        try:
            target_index = odds_list.index(target_odds)
            
            before = odds_list[max(0, target_index - count):target_index]
            after = odds_list[target_index + 1:target_index + count + 1]
            
            return {
                'target': target_odds,
                'before': before,
                'after': after,
                'is_valid': target_odds in self.valid_odds_set
            }
        except ValueError:
            return {
                'target': target_odds,
                'before': [],
                'after': [],
                'is_valid': False
            }

# Global odds validator service instance
odds_validator_service = OddsValidatorService()