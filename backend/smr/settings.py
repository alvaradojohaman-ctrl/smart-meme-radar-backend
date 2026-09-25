import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', '')
    api_key: str = os.getenv('API_KEY', '')
    origins: tuple = tuple(x.strip() for x in os.getenv('ALLOWED_ORIGINS', 'http://localhost:8080').split(',') if x.strip())
    discovery_seconds: int = int(os.getenv('DISCOVERY_SECONDS', '60'))

    def validate(self):
        if not self.database_url:
            raise RuntimeError('DATABASE_URL is required (PostgreSQL)')
        if len(self.api_key) < 32:
            raise RuntimeError('API_KEY must contain at least 32 characters')
        if '*' in self.origins:
            raise RuntimeError('ALLOWED_ORIGINS must name explicit frontend origins')
        if self.discovery_seconds < 60:
            raise RuntimeError('DISCOVERY_SECONDS must be >= 60')

settings = Settings()
# Fixed prospectively; any change requires a new experiment/protocol version.
PROTOCOL = 'v04e-observation-1'
MODEL = 'v04d-frozen'
HORIZONS = {'5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '6h': 21600, '24h': 86400}
TOLERANCE_SECONDS = 60
