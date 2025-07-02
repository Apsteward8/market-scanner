#!/usr/bin/env python3
"""
ProphetX WebSocket Service
Real-time event handling for instant opportunity detection
"""

import asyncio
import json
import base64
import websockets
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import requests
from threading import Thread
import queue

from app.core.config import get_settings
from app.services.auth_service import auth_service
from app.services.odds_validator_service import odds_validator_service

@dataclass
class WebSocketEvent:
    """WebSocket event structure"""
    timestamp: int
    change_type: str
    payload: str  # base64 encoded
    op: str  # 'c'=create, 'u'=update, 'd'=delete
    decoded_payload: Optional[Dict] = None

@dataclass
class LargeBetAlert:
    """Alert for large bet detected"""
    sport_event_id: int
    market_id: int
    selection_name: str
    odds: float
    stake: float
    line_id: str
    competitor_id: Optional[int]
    timestamp: int
    alert_score: float  # Based on stake size

class ProphetXWebSocketService:
    """Service for handling ProphetX WebSocket connections and events"""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.prophetx_base_url
        
        # WebSocket connection info
        self.websocket_config: Optional[Dict] = None
        self.websocket = None
        self.is_connected = False
        
        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {
            'selections': [],
            'wager': [],
            'matched_bet': [],
            'market_selections': []
        }
        
        # Opportunity detection
        self.large_bet_alerts: List[LargeBetAlert] = []
        self.opportunity_queue = queue.Queue()
        
        # Auto-betting configuration
        self.auto_betting_enabled = False
        self.min_stake_for_alert = self.settings.min_stake_threshold
        
        # Statistics
        self.events_received = 0
        self.large_bets_detected = 0
        self.connection_start_time = None
    
    async def get_websocket_config(self) -> Dict:
        """Get WebSocket connection configuration"""
        url = f"{self.base_url}/partner/websocket/connection-config"
        headers = await auth_service.get_auth_headers()
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                self.websocket_config = response.json()
                return self.websocket_config
            else:
                raise Exception(f"Failed to get WebSocket config: {response.status_code}")
        except Exception as e:
            raise Exception(f"Error getting WebSocket config: {e}")
    
    async def register_pusher_subscriptions(self, socket_id: str) -> Dict:
        """Register pusher subscriptions using ProphetX's method"""
        url = f"{self.base_url}/partner/mm/pusher"
        headers = await auth_service.get_auth_headers()
        
        # ProphetX's approach: Just pass the socket_id to get available channels
        # NOT subscribing to event types directly
        payload = {
            "socket_id": socket_id
        }
        
        print(f"📝 Getting available channels with socket_id: {socket_id}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            print(f"📡 Channel discovery response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Channel discovery successful!")
                
                # Log what channels and events are available
                auth_data = result.get('data', {})
                authorized_channels = auth_data.get('authorized_channel', [])
                
                print(f"📡 Available channels: {len(authorized_channels)}")
                
                for channel in authorized_channels:
                    channel_name = channel.get('channel_name', 'unknown')
                    binding_events = channel.get('binding_events', [])
                    
                    print(f"📺 Channel: {channel_name}")
                    print(f"   Available events: {len(binding_events)}")
                    
                    # Look for selections-related events
                    selection_events = [e for e in binding_events if 'selection' in e.get('name', '').lower()]
                    tournament_events = [e for e in binding_events if 'tournament' in e.get('name', '').lower()]
                    
                    if selection_events:
                        print(f"   🎯 Selection events found: {len(selection_events)}")
                        for event in selection_events[:3]:  # Show first 3
                            print(f"      - {event.get('name', 'unknown')}")
                    
                    if tournament_events:
                        print(f"   🏟️  Tournament events found: {len(tournament_events)}")
                        # Show some tournament IDs that might be NFL/popular
                        nfl_events = [e for e in tournament_events if e.get('name', '').endswith('_31')]
                        if nfl_events:
                            print(f"      - NFL tournament events: {len(nfl_events)}")
                
                return result
            else:
                raise Exception(f"Failed to get channels: {response.status_code} - {response.text}")
        except Exception as e:
            raise Exception(f"Error getting channels: {e}")
    
    async def register_pusher_subscriptions_prophetx_style(self, socket_id: str) -> Dict:
        """Alternative: Try ProphetX's exact subscription method with header-subscriptions"""
        url = f"{self.base_url}/partner/mm/pusher"
        
        # Get auth headers and add the header-subscriptions like ProphetX does
        headers = await auth_service.get_auth_headers()
        headers['header-subscriptions'] = '''[{"type":"tournament","ids":[]},{"type":"selections","ids":[]},{"type":"market_selections","ids":[]}]'''
        
        payload = {
            "socket_id": socket_id
        }
        
        print(f"📝 Trying ProphetX-style subscription with header-subscriptions")
        print(f"📄 Headers: {headers}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            print(f"📡 ProphetX-style response: {response.status_code}")
            print(f"📄 Response: {response.text[:500]}...")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ ProphetX-style subscription successful!")
                return result
            else:
                print(f"❌ ProphetX-style subscription failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ ProphetX-style subscription error: {e}")
            return None
    
    def decode_payload(self, encoded_payload: str) -> Optional[Dict]:
        """Decode base64 encoded payload"""
        try:
            decoded_bytes = base64.b64decode(encoded_payload)
            decoded_str = decoded_bytes.decode('utf-8')
            return json.loads(decoded_str)
        except Exception as e:
            print(f"Error decoding payload: {e}")
            return None
    
    def parse_websocket_message(self, message: str) -> Optional[WebSocketEvent]:
        """Parse incoming Pusher WebSocket message"""
        try:
            data = json.loads(message)
            
            # Handle Pusher system events
            event_name = data.get("event", "")
            channel = data.get("channel", "")
            
            if event_name == "pusher:connection_established":
                print("✅ Pusher connection established")
                return None
            elif event_name == "pusher:error":
                error_data = data.get('data', {})
                print(f"❌ Pusher error: {error_data}")
                return None
            elif event_name in ["pusher:ping", "pusher:pong"]:
                return None  # Ignore heartbeat messages
            elif event_name == "pusher_internal:subscription_succeeded":
                channel_name = data.get("channel", "unknown")
                print(f"✅ Subscription succeeded for channel: {channel_name}")
                return None
            elif event_name == "pusher_internal:subscription_error":
                print(f"❌ Subscription error: {data}")
                return None
            
            # Handle ProphetX events
            event_data_str = data.get("data", "{}")
            event_data = json.loads(event_data_str) if isinstance(event_data_str, str) else event_data_str
            
            # Selections events - THESE CONTAIN THE BET DETAILS WE NEED!
            if "selections" in event_name or event_name == "selections":
                print(f"🎯 SELECTIONS EVENT: {event_name}")
                print(f"📊 Event data: {json.dumps(event_data, indent=2)[:500]}...")
                
                # Create event for processing
                event = WebSocketEvent(
                    timestamp=int(time.time() * 1000000),
                    change_type="selections",
                    payload="",  # Data is already decoded
                    op="u"
                )
                event.decoded_payload = event_data
                return event
            
            # Market selections events
            elif "market_selections" in event_name or event_name == "market_selections":
                print(f"📈 MARKET SELECTIONS EVENT: {event_name}")
                print(f"📊 Event data: {json.dumps(event_data, indent=2)[:300]}...")
                
                event = WebSocketEvent(
                    timestamp=int(time.time() * 1000000),
                    change_type="market_selections",
                    payload="",
                    op="u"
                )
                event.decoded_payload = event_data
                return event
            
            # Matched bet events
            elif "matched_bet" in event_name or event_name == "matched_bet":
                print(f"🎲 MATCHED BET EVENT: {event_name}")
                print(f"📊 Event data: {json.dumps(event_data, indent=2)[:300]}...")
                
                event = WebSocketEvent(
                    timestamp=int(time.time() * 1000000),
                    change_type="matched_bet",
                    payload="",
                    op="u"
                )
                event.decoded_payload = event_data
                return event
            
            # Tournament events (status updates)
            elif "tournament" in event_name:
                # Only log tournament events occasionally to reduce noise
                if event_name.endswith(('_31', '_109', '_23')):  # NFL, popular tournaments
                    print(f"🏟️  Tournament event: {event_name}")
                return None
            
            # Wager events (our own bets)
            elif event_name == "wagers":
                print(f"💰 Wager event received")
                event = WebSocketEvent(
                    timestamp=int(time.time() * 1000000),
                    change_type="wager", 
                    payload="",
                    op="u"
                )
                event.decoded_payload = event_data
                return event
            
            # Health check events
            elif event_name == "health_check":
                return None
            
            # Log unknown events for debugging (but limit noise)
            else:
                # Only log unknown events occasionally to avoid spam
                if len(event_name) < 50:  # Avoid logging very long event names
                    print(f"🔍 Unknown event: {event_name} on channel: {channel}")
                return None
            
        except Exception as e:
            print(f"Error parsing Pusher message: {e}")
            print(f"Raw message: {message[:200]}...")
            return None
    
    async def handle_selections_event(self, event: WebSocketEvent):
        """Handle selections event - THIS IS THE GOLDMINE for large bet detection"""
        if not event.decoded_payload:
            return
        
        payload = event.decoded_payload
        
        # Based on ProphetX docs, selections events have this structure:
        # {
        #   "sport_event_id": int,
        #   "market_id": int, 
        #   "info": {
        #     "stake": float,
        #     "odds": float,
        #     "name": string,
        #     "line_id": string,
        #     ...
        #   }
        # }
        
        info = payload.get("info", {})
        sport_event_id = payload.get("sport_event_id", 0)
        market_id = payload.get("market_id", 0)
        
        # Extract key information
        stake = info.get("stake", 0)
        odds = info.get("odds", 0) 
        selection_name = info.get("name", info.get("display_name", "Unknown"))
        line_id = info.get("line_id", "")
        
        print(f"📊 Selection details: {selection_name}, odds: {odds}, stake: ${stake}")
        
        # Check if this is a large bet worth following
        if stake >= self.min_stake_for_alert and odds != 0:
            
            alert = LargeBetAlert(
                sport_event_id=sport_event_id,
                market_id=market_id,
                selection_name=selection_name,
                odds=odds,
                stake=stake,
                line_id=line_id,
                competitor_id=info.get("competitor_id"),
                timestamp=event.timestamp,
                alert_score=stake / 1000  # Simple scoring based on stake size
            )
            
            self.large_bet_alerts.append(alert)
            self.large_bets_detected += 1
            
            print(f"🚨 LARGE BET ALERT: {selection_name} {odds:+.0f} for ${stake:,.0f}")
            print(f"   Event: {sport_event_id}, Market: {market_id}, Line: {line_id}")
            
            # Add to opportunity queue for processing
            self.opportunity_queue.put(alert)
            
            # Trigger opportunity analysis if auto-betting is enabled
            if self.auto_betting_enabled:
                await self.process_large_bet_opportunity(alert)
        else:
            # Log smaller bets occasionally for debugging
            if stake > 0:
                print(f"📝 Small bet: {selection_name} ${stake:.0f} (below ${self.min_stake_for_alert} threshold)")
    
    async def handle_market_selections_event(self, event: WebSocketEvent):
        """Handle market_selections event - market-level liquidity changes"""
        if not event.decoded_payload:
            return
        
        payload = event.decoded_payload
        sport_event_id = payload.get("sport_event_id", 0)
        market_id = payload.get("market_id", 0)
        
        info = payload.get("info", {})
        selections = info.get("selections", [])
        
        print(f"📈 Market selections update: Event {sport_event_id}, Market {market_id}")
        print(f"   Found {len(selections)} selection groups")
        
        # Process each selection group
        for selection_group in selections:
            if isinstance(selection_group, list):
                for selection in selection_group:
                    if isinstance(selection, dict):
                        stake = selection.get("stake", 0)
                        if stake >= self.min_stake_for_alert:
                            # Process as a large bet alert
                            selection_name = selection.get("name", selection.get("display_name", "Unknown"))
                            odds = selection.get("odds", 0)
                            line_id = selection.get("line_id", "")
                            
                            alert = LargeBetAlert(
                                sport_event_id=sport_event_id,
                                market_id=market_id,
                                selection_name=selection_name,
                                odds=odds,
                                stake=stake,
                                line_id=line_id,
                                competitor_id=selection.get("competitor_id"),
                                timestamp=event.timestamp,
                                alert_score=stake / 1000
                            )
                            
                            self.large_bet_alerts.append(alert)
                            self.large_bets_detected += 1
                            
                            print(f"🚨 LARGE BET ALERT (from market): {selection_name} {odds:+.0f} for ${stake:,.0f}")
                            
                            if self.auto_betting_enabled:
                                await self.process_large_bet_opportunity(alert)
    
    async def handle_wager_event(self, event: WebSocketEvent):
        """Handle wager event - track our own bet status"""
        if not event.decoded_payload:
            return
        
        payload = event.decoded_payload
        info = payload.get("info", {})
        
        external_id = info.get("external_id", "")
        matching_status = info.get("matching_status", "")
        matched_stake = info.get("matched_stake", 0)
        unmatched_stake = info.get("unmatched_stake", 0)
        
        print(f"💰 BET UPDATE: {external_id}")
        print(f"   Status: {matching_status}")
        print(f"   Matched: ${matched_stake:.2f}, Unmatched: ${unmatched_stake:.2f}")
    
    async def handle_matched_bet_event(self, event: WebSocketEvent):
        """Handle matched bet event - see market activity"""
        if not event.decoded_payload:
            return
        
        payload = event.decoded_payload
        info = payload.get("info", {})
        
        matched_odds = info.get("matched_odds", 0)
        matched_stake = info.get("matched_stake", 0)
        
        if matched_stake >= 1000:  # Only log significant matches
            print(f"🎯 MARKET MATCH: ${matched_stake:.0f} at {matched_odds:+.0f}")
    
    async def process_large_bet_opportunity(self, alert: LargeBetAlert):
        """Process a large bet alert and potentially place a follow bet"""
        try:
            # Import here to avoid circular imports
            from app.services.scanner_service import scanner_service
            from app.services.bet_placement_service import bet_placement_service
            
            print(f"🔍 Analyzing large bet opportunity: ${alert.stake:,.0f}")
            
            # Calculate undercut odds
            undercut_odds = odds_validator_service.calculate_undercut_odds(
                int(alert.odds), 
                self.settings.undercut_amount
            )
            
            if undercut_odds is None:
                print(f"❌ Could not calculate valid undercut for {alert.odds:+.0f}")
                return
            
            # Determine bet size (smaller for real-time bets)
            bet_size = min(alert.stake * 0.1, self.settings.max_bet_size, 50)  # Cap at $50 for safety
            
            print(f"💡 Follow opportunity: {alert.selection_name} {undercut_odds:+d} for ${bet_size:.0f}")
            
            # Here you could automatically place the bet if desired
            # For safety, we'll just log the opportunity for now
            
        except Exception as e:
            print(f"💥 Error processing opportunity: {e}")
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """Register a custom event handler"""
        if event_type in self.event_handlers:
            self.event_handlers[event_type].append(handler)
    
    async def start_websocket_connection(self):
        """Start the WebSocket connection and event loop"""
        try:
            print("🔌 Starting ProphetX WebSocket connection...")
            
            # Get WebSocket configuration
            config = await self.get_websocket_config()
            print(f"✅ Got WebSocket config: {config.get('service', 'Unknown')}")
            
            # Extract Pusher configuration
            app_id = config.get('app_id')
            key = config.get('key') 
            cluster = config.get('cluster', 'us2')
            
            if not app_id or not key:
                raise Exception("Missing app_id or key in WebSocket config")
            
            # Build Pusher WebSocket URL
            websocket_url = f"wss://ws-{cluster}.pusher.com/app/{key}?protocol=7&client=python&version=1.0"
            
            print(f"🔗 Connecting to: {websocket_url}")
            
            # Connect to Pusher WebSocket
            self.websocket = await websockets.connect(websocket_url)
            self.is_connected = True
            self.connection_start_time = time.time()
            
            print("🚀 WebSocket connected! Waiting for Pusher connection established...")
            
            # Wait for Pusher connection established message
            socket_id = None
            auth_channels = []
            
            try:
                connection_message = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
                conn_data = json.loads(connection_message)
                
                if conn_data.get("event") == "pusher:connection_established":
                    pusher_data = json.loads(conn_data.get("data", "{}"))
                    socket_id = pusher_data.get("socket_id")
                    print(f"✅ Pusher connection established! Socket ID: {socket_id}")
                else:
                    print(f"⚠️  Unexpected first message: {conn_data.get('event')}")
                    
            except Exception as e:
                print(f"⚠️  Error getting socket ID: {e}")
            
            # Register subscriptions with the correct socket_id
            if socket_id:
                try:
                    print("📝 Registering subscriptions...")
                    subscription_result = await self.register_pusher_subscriptions(socket_id)
                    
                    # Extract authorized channels for confirmation
                    auth_data = subscription_result.get('data', {})
                    auth_channels = auth_data.get('authorized_channel', [])
                    
                    print(f"✅ Subscriptions registered successfully!")
                    print(f"📡 Authorized channels: {len(auth_channels)}")
                    
                    # Send subscription confirmations for each authorized channel
                    for channel_info in auth_channels:
                        channel_name = channel_info.get('channel_name')
                        auth_token = channel_info.get('auth')
                        
                        if channel_name and auth_token:
                            subscribe_message = {
                                "event": "pusher:subscribe",
                                "data": {
                                    "auth": auth_token,
                                    "channel": channel_name
                                }
                            }
                            
                            print(f"📧 Subscribing to channel: {channel_name}")
                            await self.websocket.send(json.dumps(subscribe_message))
                            
                except Exception as e:
                    print(f"⚠️  Subscription registration failed: {e}")
                    print("Continuing with WebSocket connection anyway...")
            else:
                print("⚠️  No socket_id received, skipping subscription registration")
            
            print("📡 Starting event processing loop...")
            
            # Event processing loop with better error handling
            try:
                async for message in self.websocket:
                    await self.handle_websocket_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                print(f"🔌 WebSocket connection closed: {e}")
            except Exception as e:
                print(f"💥 Error in event processing loop: {e}")
                
        except websockets.exceptions.ConnectionClosed:
            print("🔌 WebSocket connection closed")
            self.is_connected = False
        except Exception as e:
            print(f"💥 WebSocket connection error: {e}")
            self.is_connected = False
    
    async def handle_websocket_message(self, message: str):
        """Handle incoming WebSocket message"""
        try:
            self.events_received += 1
            
            # Parse the message
            event = self.parse_websocket_message(message)
            if not event:
                return
            
            # Route to appropriate handler based on change_type
            if event.change_type == "selections":
                await self.handle_selections_event(event)
            elif event.change_type == "market_selections":
                await self.handle_market_selections_event(event)
            elif event.change_type == "wager":
                await self.handle_wager_event(event)
            elif event.change_type == "matched_bet":
                await self.handle_matched_bet_event(event)
            
            # Call custom handlers
            handlers = self.event_handlers.get(event.change_type, [])
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    print(f"Error in custom handler: {e}")
                    
        except Exception as e:
            print(f"Error handling WebSocket message: {e}")
            print(f"Message: {message[:300]}...")
    
    def get_connection_stats(self) -> Dict:
        """Get WebSocket connection statistics"""
        uptime = time.time() - self.connection_start_time if self.connection_start_time else 0
        
        return {
            "is_connected": self.is_connected,
            "uptime_seconds": uptime,
            "events_received": self.events_received,
            "large_bets_detected": self.large_bets_detected,
            "auto_betting_enabled": self.auto_betting_enabled,
            "min_stake_threshold": self.min_stake_for_alert,
            "recent_alerts": len([a for a in self.large_bet_alerts if time.time() - a.timestamp/1000000 < 3600])  # Last hour
        }
    
    def get_recent_large_bets(self, limit: int = 10) -> List[Dict]:
        """Get recent large bet alerts"""
        recent_alerts = sorted(self.large_bet_alerts, key=lambda x: x.timestamp, reverse=True)[:limit]
        
        return [
            {
                "selection_name": alert.selection_name,
                "odds": alert.odds,
                "stake": alert.stake,
                "alert_score": alert.alert_score,
                "timestamp": datetime.fromtimestamp(alert.timestamp / 1000000).isoformat(),
                "sport_event_id": alert.sport_event_id,
                "market_id": alert.market_id
            }
            for alert in recent_alerts
        ]
    
    def set_auto_betting(self, enabled: bool):
        """Enable or disable auto-betting on large bet alerts"""
        self.auto_betting_enabled = enabled
        print(f"🤖 Auto-betting {'ENABLED' if enabled else 'DISABLED'}")
    
    def set_min_stake_threshold(self, threshold: int):
        """Set minimum stake threshold for alerts"""
        self.min_stake_for_alert = threshold
        print(f"📊 Alert threshold set to ${threshold:,}")
    
    async def stop_connection(self):
        """Stop the WebSocket connection"""
        if self.websocket:
            await self.websocket.close()
        self.is_connected = False
        print("🛑 WebSocket connection stopped")

# Global WebSocket service instance
websocket_service = ProphetXWebSocketService()