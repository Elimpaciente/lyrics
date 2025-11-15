# pls don't forgot to star this repo
# https://github.com/Soumyadeep765/Song/

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import spotipy
import hashlib
import hmac
import math
import re
from urllib.parse import urlparse
from typing import Optional
from datetime import datetime, timedelta

# Initialize FastAPI server
app = FastAPI(
    title="Spotify Lyrics API",
    description="API to fetch Spotify track details and lyrics",
    version="2.0.0"
)

# Allow CORS for localhost request issues
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
TOKEN_URL = 'https://open.spotify.com/api/token'
LYRICS_URL = 'https://spclient.wg.spotify.com/color-lyrics/v2/track/'
SERVER_TIME_URL = 'https://open.spotify.com/api/server-time'
SECRET_KEY_URL = 'https://github.com/xyloflake/spot-secrets-go/blob/main/secrets/secretDict.json?raw=true'

DEFAULT_SP_DC = "AQAO1j7bPbFcbVh5TbQmwmTd_XFckJhbOipaA0t2BZpViASzI6Qrk1Ty0WviN1K1mmJv_hV7xGVbMPHm4-HAZbs3OXOHSu38Xq7hZ9wqWwvdZwjiWTQmKWLoKxJP1j3kI7-8eWgVZ8TcPxRnXrjP3uDJ9SnzOla_EpxePC74dHa5D4nBWWfFLdiV9bMQuzUex6izb12gCh0tvTt3Xlg"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# In-memory token cache
token_cache = {
    "token": None,
    "expires_at": datetime.min
}


class TOTP:
    def __init__(self) -> None:
        self.secret, self.version = self.get_secret_version()
        self.period = 30
        self.digits = 6

    def generate(self, timestamp_seconds: int) -> str:
        counter = math.floor(timestamp_seconds / self.period)
        counter_bytes = counter.to_bytes(8, byteorder="big")

        h = hmac.new(self.secret.encode('utf-8'), counter_bytes, hashlib.sha1)
        hmac_result = h.digest()

        offset = hmac_result[-1] & 0x0F
        binary = (
            (hmac_result[offset] & 0x7F) << 24
            | (hmac_result[offset + 1] & 0xFF) << 16
            | (hmac_result[offset + 2] & 0xFF) << 8
            | (hmac_result[offset + 3] & 0xFF)
        )

        return str(binary % (10**self.digits)).zfill(self.digits)
    
    def get_secret_version(self) -> tuple[str, str]:
        try:
            req = requests.get(SECRET_KEY_URL)
            if req.status_code != 200:
                raise ValueError("Failed to fetch TOTP secret and version.")
            
            secrets_data = req.json()
            
            # Get the latest version (last key in the dict)
            versions = list(secrets_data.keys())
            latest_version = versions[-1]
            original_secret = secrets_data[latest_version]
            
            if not isinstance(original_secret, list):
                raise ValueError('The original secret must be an array of integers.')
            
            # Transform the secret
            transformed = [char ^ ((i % 33) + 9) for i, char in enumerate(original_secret)]
            secret = ''.join(str(num) for num in transformed)
            
            return secret, latest_version
        except Exception as e:
            raise ValueError(f"Failed to get secret key: {str(e)}")


class SpotifyLyricsAPI:
    def __init__(self, sp_dc: str = DEFAULT_SP_DC) -> None:
        self.sp_dc = sp_dc
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.totp = TOTP()
        self.sp = None

    def get_server_time_params(self) -> dict:
        """Get server time and generate TOTP parameters"""
        try:
            response = self.session.get(SERVER_TIME_URL)
            server_time_data = response.json()
            
            if not server_time_data or 'serverTime' not in server_time_data:
                raise ValueError('Invalid server time response')
            
            server_time_seconds = server_time_data['serverTime']
            totp = self.totp.generate(server_time_seconds)
            
            timestamp = int(datetime.now().timestamp())
            
            params = {
                'reason': 'transport',
                'productType': 'web-player',
                'totp': totp,
                'totpVer': self.totp.version,
                'ts': str(timestamp)
            }
            
            return params
        except Exception as e:
            raise ValueError(f"Failed to get server time params: {str(e)}")

    def get_token(self) -> str:
        """Get a new access token from Spotify"""
        if not self.sp_dc:
            raise ValueError('Please set SP_DC.')
        
        try:
            params = self.get_server_time_params()
            
            headers = HEADERS.copy()
            headers['Cookie'] = f'sp_dc={self.sp_dc}'
            
            response = self.session.get(TOKEN_URL, params=params, headers=headers)
            token_data = response.json()
            
            if token_data.get('isAnonymous'):
                raise ValueError('The SP_DC set seems to be invalid, please correct it!')
            
            return token_data['accessToken']
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Token request failed: {str(e)}")

    def is_token_valid(self) -> bool:
        """Check if cached token is still valid"""
        return token_cache["token"] is not None and datetime.now() < token_cache["expires_at"]

    def ensure_valid_token(self) -> str:
        """Ensure we have a valid token, getting a new one if necessary"""
        if self.is_token_valid():
            return token_cache["token"]
        
        token = self.get_token()
        
        # Cache the token (valid for 30 minutes)
        token_cache["token"] = token
        token_cache["expires_at"] = datetime.now() + timedelta(minutes=30)
        
        # Initialize Spotipy with the new token
        self.sp = spotipy.Spotify(auth=token)
        
        return token

    def extract_track_id(self, input_str: str) -> str:
        """Extract track ID from URL or return as-is if already an ID"""
        if not input_str:
            raise ValueError("No track ID or URL provided")
        
        # If it's already a valid Spotify ID
        if re.match(r'^[a-zA-Z0-9]{22}$', input_str):
            return input_str
            
        # Try to extract from URL
        url_pattern = r'https?://open\.spotify\.com/track/([a-zA-Z0-9]{22})'
        match = re.search(url_pattern, input_str)
        if match:
            return match.group(1)
        
        raise ValueError("Invalid Spotify track URL or ID")

    def get_track_details(self, track_id: str) -> dict:
        """Get track metadata from Spotify"""
        try:
            self.ensure_valid_token()
            if not self.sp:
                raise ValueError("Spotify client not initialized")
            
            track = self.sp.track(track_id)
            return track
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Track not found: {str(e)}")

    def get_lyrics(self, track_id: str) -> dict:
        """Get lyrics for a track"""
        try:
            token = self.ensure_valid_token()
            formatted_url = f'{LYRICS_URL}{track_id}'
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.0.0 Safari/537.36',
                'App-platform': 'WebPlayer',
                'Authorization': f'Bearer {token}'
            }
            
            params = {'format': 'json', 'market': 'from_token'}
            
            response = self.session.get(formatted_url, headers=headers, params=params)
            
            if response.status_code != 200:
                return None
            
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lyrics fetch failed: {str(e)}")

    def format_duration(self, ms: int) -> str:
        """Format duration in human readable time"""
        seconds = int(ms / 1000)
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes}:{seconds:02d}"

    def format_ms(self, milliseconds: int) -> str:
        """Format milliseconds to MM:SS.CS format for LRC"""
        total_seconds = milliseconds // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        centiseconds = (milliseconds % 1000) // 10
        
        return f"{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    def format_track_details(self, track_details: dict) -> dict:
        """Format track metadata for response"""
        return {
            'id': track_details['id'],
            'name': track_details['name'],
            'title': track_details['name'],
            'artists': [{
                'name': artist['name'],
                'id': artist['id'],
                'url': artist['external_urls']['spotify']
            } for artist in track_details['artists']],
            'primary_artist': track_details['artists'][0]['name'],
            'album': {
                'name': track_details['album']['name'],
                'id': track_details['album']['id'],
                'url': track_details['album']['external_urls']['spotify'],
                'release_date': track_details['album']['release_date'],
                'total_tracks': track_details['album']['total_tracks'],
                'type': track_details['album']['album_type'],
                'images': track_details['album']['images']
            },
            'release_date': track_details['album']['release_date'],
            'duration': self.format_duration(track_details['duration_ms']),
            'duration_ms': track_details['duration_ms'],
            'image_url': track_details['album']['images'][0]['url'] if track_details['album']['images'] else None,
            'track_url': track_details['external_urls']['spotify'],
            'popularity': track_details['popularity'],
            'preview_url': track_details.get('preview_url'),
            'explicit': track_details.get('explicit', False),
            'type': track_details['type'],
            'uri': track_details['uri']
        }

    def get_combined_lyrics(self, lines: list, response_type: str = 'plain') -> str:
        """Combine lyrics lines based on response type"""
        if not lines:
            return "No lyrics available"
            
        if response_type == 'plain':
            return '\n'.join([line['words'] for line in lines])
        elif response_type == 'synchronized':
            return '\n'.join([f"[{self.format_ms(int(line['startTimeMs']))}] {line['words']}" for line in lines])
        elif response_type == 'lrc':
            return '\n'.join([f"[{self.format_ms(int(line['startTimeMs']))}] {line['words']}" for line in lines])
        else:
            return '\n'.join([line['words'] for line in lines])


class LyricsResponse(BaseModel):
    status: str
    details: Optional[dict] = None
    lyrics: str
    raw_lyrics: Optional[dict] = None
    response_type: str
    track_id: str


@app.get("/", summary="API Info")
async def root():
    """Get API information and usage"""
    return {
        "message": "Spotify Lyrics API",
        "version": "2.0.0",
        "description": "API to fetch Spotify lyrics with updated authentication",
        "endpoints": {
            "/spotify/lyrics": "Get lyrics for a Spotify track",
            "usage": {
                "by_id": "/spotify/lyrics?id=TRACK_ID",
                "by_url": "/spotify/lyrics?url=SPOTIFY_URL",
                "with_format": "/spotify/lyrics?id=TRACK_ID&format=synchronized"
            },
            "formats": ["plain", "synchronized", "lrc"]
        }
    }


@app.get("/spotify/lyrics", response_model=LyricsResponse, summary="Get track lyrics")
async def get_lyrics(
    id: Optional[str] = Query(None, description="Spotify track ID"),
    url: Optional[str] = Query(None, description="Spotify track URL"),
    format: str = Query('plain', description="Lyrics format (plain, synchronized, or lrc)"),
    sp_dc: Optional[str] = Query(DEFAULT_SP_DC, description="Spotify sp_dc cookie"),
    include_details: bool = Query(True, description="Include track details in response")
):
    """
    Get lyrics and track details for a Spotify track by either ID or URL.
    
    Parameters:
    - id: Spotify track ID (e.g. 3n3Ppam7vgaVa1iaRUc9Lp)
    - url: Spotify track URL (e.g. https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp)
    - format: Output format for lyrics (plain, synchronized, or lrc)
    - sp_dc: Optional Spotify sp_dc cookie for authentication
    - include_details: Whether to include full track details
    """
    if not id and not url:
        raise HTTPException(
            status_code=400,
            detail="Either 'id' or 'url' parameter is required"
        )
    
    try:
        spotify = SpotifyLyricsAPI(sp_dc)
        
        # Extract track ID from either URL or ID
        track_input = id if id else url
        track_id = spotify.extract_track_id(track_input)
        
        # Get lyrics
        lyrics_data = spotify.get_lyrics(track_id)
        
        lyrics_lines = []
        if lyrics_data and 'lyrics' in lyrics_data and 'lines' in lyrics_data['lyrics']:
            lyrics_lines = lyrics_data['lyrics']['lines']
        
        combined_lyrics = spotify.get_combined_lyrics(lyrics_lines, format)
        
        # Get track details if requested
        track_details = None
        if include_details:
            track_details = spotify.get_track_details(track_id)
            track_details = spotify.format_track_details(track_details)

        return {
            "status": "success",
            "details": track_details,
            "lyrics": combined_lyrics,
            "raw_lyrics": lyrics_data,
            "response_type": format,
            "track_id": track_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", summary="Health check")
async def health():
    """Health check endpoint"""
    return {
        "status": "OK",
        "timestamp": datetime.now().isoformat(),
        "token_cached": token_cache["token"] is not None,
        "token_valid": token_cache["token"] is not None and datetime.now() < token_cache["expires_at"]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
