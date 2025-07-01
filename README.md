# ProphetX Betting Tool API

A FastAPI-based application for following smart money on the ProphetX betting exchange.

## Strategy Overview

This tool implements a "follow the smart money" strategy:

1. **Scan Markets** - Find large bets (>$5k) that indicate sharp/informed money
2. **Follow Bets** - Place bets on the same side with slightly worse odds
3. **Get Priority** - Worse odds give us priority in the betting queue
4. **Profit** - When action flows our way, we get matched first

## Quick Start

### 1. Installation

```bash
# Clone/download the project files
cd prophetx-api

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Create environment configuration
python -m app.core.config  # This will create a sample .env file

# Edit .env with your ProphetX credentials
# PROPHETX_ACCESS_KEY=your_access_key_here
# PROPHETX_SECRET_KEY=your_secret_key_here
```

### 3. Run the API

```bash
# Start the FastAPI server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. Access the API

- **API Documentation**: http://127.0.0.1:8000/docs
- **Alternative Docs**: http://127.0.0.1:8000/redoc
- **Health Check**: http://127.0.0.1:8000/health

## API Endpoints

### Authentication
- `POST /auth/login` - Login to ProphetX
- `GET /auth/status` - Check authentication status
- `POST /auth/test` - Test API connection

### Market Scanning
- `GET /markets/tournaments` - List available tournaments
- `POST /markets/scan/tournament/{id}` - Scan specific tournament
- `POST /markets/scan/event/{id}` - Scan specific event
- `POST /markets/scan/comprehensive` - Scan all markets (large!)

### Bet Analysis
- `POST /analysis/odds/validate` - Validate if odds are accepted by ProphetX
- `POST /analysis/odds/undercut` - Calculate undercut odds
- `GET /analysis/strategy/explain` - Explain the follow-money strategy

### Bet Placement
- `POST /bets/place` - Place a single bet manually
- `POST /bets/place-multiple` - Place multiple follow bets
- `GET /bets/history` - View bet placement history
- `GET /bets/stats` - Get placement statistics

### Configuration
- `GET /config/settings` - View current settings
- `PUT /config/settings` - Update settings
- `POST /config/validate` - Validate configuration

## Example Workflow

### 1. First, authenticate:

```bash
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 2. Test connection:

```bash
curl -X POST "http://127.0.0.1:8000/auth/test"
```

### 3. Scan for opportunities:

```bash
# Get available tournaments
curl "http://127.0.0.1:8000/markets/tournaments"

# Scan NFL (tournament ID 31)
curl -X POST "http://127.0.0.1:8000/markets/scan/tournament/31?limit_events=5"
```

### 4. Place follow bets:

```bash
curl -X POST "http://127.0.0.1:8000/bets/place-multiple" \
  -H "Content-Type: application/json" \
  -d '{
    "opportunities": [...], 
    "bet_size": 5.0,
    "dry_run": true
  }'
```

## Safety Features

### Dry Run Mode
- **Default**: All bets are simulated (dry_run=true)
- **Testing**: Always test with dry_run=true first
- **Live Mode**: Set dry_run=false only when ready for real bets

### Configuration Validation
- Use `/config/validate` to check your setup
- Validates credentials, limits, and settings
- Provides recommendations for safe operation

### Betting Limits
- `min_stake_threshold`: Only follow bets above this amount (default: $5,000)
- `max_bet_size`: Maximum amount we'll bet (default: $1,000)
- `default_bet_size`: Default bet size for testing (default: $5)

## Configuration Options

Environment variables (set in `.env` file):

```bash
# ProphetX Credentials (Required)
PROPHETX_ACCESS_KEY=your_access_key
PROPHETX_SECRET_KEY=your_secret_key

# Environment
PROPHETX_SANDBOX=true  # Use sandbox for testing

# Strategy Settings
PROPHETX_MIN_STAKE=5000      # Only follow bets >= $5k
PROPHETX_MAX_BET_SIZE=1000   # Max bet size
PROPHETX_UNDERCUT_AMOUNT=1   # How aggressively to undercut
PROPHETX_TARGET_SPORTS=Baseball,American Football,Basketball

# Safety
DRY_RUN_MODE=true           # Simulate bets
DEFAULT_BET_SIZE=5.0        # Test bet size
```

## Understanding Betting Exchange Logic

### Key Concepts:

1. **When someone bets -138**: They offer +138 to the market
2. **To undercut them**: We offer better than +138 (like +140)
3. **To offer +140**: We must take -140 ourselves
4. **Result**: Our bet gets priority when action flows

### Example:
- Large bet: $10,000 on Pirates at +120 (offers -120 to market)
- Our follow: Pirates at +118 (offers -118 to market, better for bettors)
- Priority: When more people want Pirates, we get matched first

## Development

### Project Structure:
```
app/
├── main.py              # FastAPI application
├── core/
│   └── config.py        # Configuration management
├── models/
│   ├── requests.py      # Request models
│   └── responses.py     # Response models
├── services/
│   ├── auth_service.py      # ProphetX authentication
│   ├── scanner_service.py   # Market scanning
│   ├── odds_validator_service.py  # Odds validation
│   └── bet_placement_service.py   # Bet placement
└── routers/
    ├── auth.py          # Authentication endpoints
    ├── markets.py       # Market scanning endpoints
    ├── bets.py          # Bet placement endpoints
    ├── analysis.py      # Analysis endpoints
    └── config.py        # Configuration endpoints
```

### Running Tests:
```bash
pytest
```

### Development Mode:
```bash
uvicorn app.main:app --reload --log-level debug
```

## Important Notes

### Risk Management
- This strategy involves real money and real risk
- Large bets don't guarantee wins - they indicate edge, not certainty
- Always start with small bet sizes and dry run mode
- Understand the betting exchange mechanics before going live

### Legal Considerations
- Ensure sports betting is legal in your jurisdiction
- Comply with all relevant laws and regulations
- ProphetX may have terms of service regarding automated betting

### Technical Considerations
- API rate limits: Be respectful of ProphetX's API
- Error handling: Markets can change rapidly
- Network issues: Handle connection failures gracefully

## Support

For issues or questions:
1. Check the API documentation at `/docs`
2. Validate your configuration with `/config/validate`
3. Test with dry run mode first
4. Review the logs for error details

## Disclaimer

This tool is for educational and research purposes. Sports betting involves risk, and you should only bet what you can afford to lose. The authors are not responsible for any losses incurred using this software.