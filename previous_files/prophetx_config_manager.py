#!/usr/bin/env python3
"""
ProphetX Configuration Manager
Handles loading credentials from environment variables or config files
"""

import os
import json
from typing import Optional, Dict
from dataclasses import dataclass

@dataclass
class ProphetXConfig:
    """Configuration container for ProphetX credentials and settings"""
    access_key: str
    secret_key: str
    sandbox: bool = True
    min_stake_threshold: int = 5000
    undercut_amount: int = 1
    max_bet_size: int = 1000
    target_sports: list = None
    
    def __post_init__(self):
        if self.target_sports is None:
            self.target_sports = ["Baseball", "American Football", "Basketball"]

class ConfigManager:
    """Manages loading configuration from various sources"""
    
    @staticmethod
    def load_from_env() -> Optional[ProphetXConfig]:
        """
        Load configuration from environment variables
        
        Expected environment variables:
        - PROPHETX_ACCESS_KEY
        - PROPHETX_SECRET_KEY
        - PROPHETX_SANDBOX (optional, default: true)
        - PROPHETX_MIN_STAKE (optional, default: 5000)
        """
        access_key = os.getenv('PROPHETX_ACCESS_KEY')
        secret_key = os.getenv('PROPHETX_SECRET_KEY')
        
        if not access_key or not secret_key:
            return None
        
        # Optional settings with defaults
        sandbox = os.getenv('PROPHETX_SANDBOX', 'true').lower() == 'true'
        min_stake = int(os.getenv('PROPHETX_MIN_STAKE', '5000'))
        undercut_amount = int(os.getenv('PROPHETX_UNDERCUT_AMOUNT', '1'))
        max_bet_size = int(os.getenv('PROPHETX_MAX_BET_SIZE', '1000'))
        
        return ProphetXConfig(
            access_key=access_key,
            secret_key=secret_key,
            sandbox=sandbox,
            min_stake_threshold=min_stake,
            undercut_amount=undercut_amount,
            max_bet_size=max_bet_size
        )
    
    @staticmethod
    def load_from_file(file_path: str = "prophetx_config.json") -> Optional[ProphetXConfig]:
        """
        Load configuration from JSON file
        
        Args:
            file_path: Path to config file
            
        Returns:
            ProphetXConfig object or None if file doesn't exist/invalid
        """
        try:
            if not os.path.exists(file_path):
                return None
                
            with open(file_path, 'r') as f:
                config_data = json.load(f)
            
            # Validate required fields
            if 'access_key' not in config_data or 'secret_key' not in config_data:
                print(f"❌ Config file {file_path} missing required fields: access_key, secret_key")
                return None
            
            return ProphetXConfig(**config_data)
            
        except Exception as e:
            print(f"❌ Error loading config file {file_path}: {e}")
            return None
    
    @staticmethod
    def create_sample_config_file(file_path: str = "prophetx_config.json"):
        """
        Create a sample configuration file
        
        Args:
            file_path: Path where to create the sample config
        """
        sample_config = {
            "access_key": "YOUR_ACCESS_KEY_HERE",
            "secret_key": "YOUR_SECRET_KEY_HERE",
            "sandbox": True,
            "min_stake_threshold": 5000,
            "undercut_amount": 1,
            "max_bet_size": 1000,
            "target_sports": ["Baseball", "American Football", "Basketball"]
        }
        
        try:
            with open(file_path, 'w') as f:
                json.dump(sample_config, f, indent=4)
            print(f"✅ Sample config file created: {file_path}")
            print(f"   Please edit the file and add your actual credentials")
        except Exception as e:
            print(f"❌ Error creating config file: {e}")
    
    @staticmethod
    def create_sample_env_file(file_path: str = ".env"):
        """
        Create a sample .env file
        
        Args:
            file_path: Path where to create the sample .env file
        """
        sample_env = """# ProphetX API Credentials
PROPHETX_ACCESS_KEY=YOUR_ACCESS_KEY_HERE
PROPHETX_SECRET_KEY=YOUR_SECRET_KEY_HERE

# Optional Settings
PROPHETX_SANDBOX=true
PROPHETX_MIN_STAKE=5000
PROPHETX_UNDERCUT_AMOUNT=1
PROPHETX_MAX_BET_SIZE=1000
"""
        
        try:
            with open(file_path, 'w') as f:
                f.write(sample_env)
            print(f"✅ Sample .env file created: {file_path}")
            print(f"   Please edit the file and add your actual credentials")
            print(f"   Don't forget to add .env to your .gitignore file!")
        except Exception as e:
            print(f"❌ Error creating .env file: {e}")
    
    @staticmethod
    def load_dotenv(file_path: str = ".env"):
        """
        Load environment variables from .env file
        
        Args:
            file_path: Path to .env file
        """
        try:
            if not os.path.exists(file_path):
                return False
                
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading .env file: {e}")
            return False
    
    @staticmethod
    def get_config() -> ProphetXConfig:
        """
        Get configuration from the best available source
        
        Priority:
        1. Environment variables
        2. .env file 
        3. prophetx_config.json file
        4. Interactive input
        
        Returns:
            ProphetXConfig object
        """
        print("🔧 Loading ProphetX configuration...")
        
        # Try environment variables first
        config = ConfigManager.load_from_env()
        if config:
            print("✅ Loaded configuration from environment variables")
            return config
        
        # Try loading .env file
        if ConfigManager.load_dotenv():
            config = ConfigManager.load_from_env()
            if config:
                print("✅ Loaded configuration from .env file")
                return config
        
        # Try config file
        config = ConfigManager.load_from_file()
        if config:
            print("✅ Loaded configuration from prophetx_config.json")
            return config
        
        # Interactive fallback
        print("❌ No configuration found in environment or files")
        print("Options:")
        print("1. Enter credentials manually (this session only)")
        print("2. Create .env file")
        print("3. Create config.json file")
        
        choice = input("Choose option (1/2/3): ").strip()
        
        if choice == "2":
            ConfigManager.create_sample_env_file()
            print("\n Please edit the .env file with your credentials and run again")
            exit(0)
        elif choice == "3":
            ConfigManager.create_sample_config_file()
            print("\n Please edit the prophetx_config.json file with your credentials and run again")
            exit(0)
        else:
            # Interactive input
            print("\nEntering credentials manually:")
            access_key = input("Access Key: ").strip()
            secret_key = input("Secret Key: ").strip()
            
            if not access_key or not secret_key:
                print("❌ Both access key and secret key are required!")
                exit(1)
            
            return ProphetXConfig(access_key=access_key, secret_key=secret_key)

def main():
    """Test the configuration manager"""
    print("ProphetX Configuration Manager Test")
    print("=" * 40)
    
    try:
        config = ConfigManager.get_config()
        
        print(f"\n✅ Configuration loaded successfully:")
        print(f"   Access Key: {config.access_key[:10]}...")
        print(f"   Secret Key: {config.secret_key[:10]}...")
        print(f"   Sandbox Mode: {config.sandbox}")
        print(f"   Min Stake Threshold: ${config.min_stake_threshold:,}")
        print(f"   Undercut Amount: {config.undercut_amount}")
        print(f"   Max Bet Size: ${config.max_bet_size:,}")
        print(f"   Target Sports: {', '.join(config.target_sports)}")
        
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"💥 Error: {e}")

if __name__ == "__main__":
    main()