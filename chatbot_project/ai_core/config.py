"""애플리케이션 환경 설정을 한곳에서 불러오면 됨."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import os

from dotenv import load_dotenv


# 모듈이 로드될 때 곧바로 환경 변수를 읽어두면 됨.
# 이렇게 하면 Gemini나 Spotify 객체를 만들지 않아도 설정 값을 바로 쓸 수 있음.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """실행 시 필요한 설정 값을 담아두면 됨."""

    gemini_api_key: str
    spotify_client_id: str
    spotify_client_secret: str
    spotify_refresh_token: Optional[str] = None
    spotify_redirect_uri: Optional[str] = None
    spotify_market: str = "US"
    spotify_default_seed_genres: Tuple[str, ...] = tuple()
    gemini_model: str = "gemini-2.0-flash-exp"
    gemini_verifier_model: str = "gemini-1.5-pro"

    @classmethod
    def from_env(cls) -> "Settings":
        """``os.environ``에서 값을 읽어와 ``Settings`` 인스턴스를 만들면 됨."""

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID")
        spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY 환경 변수를 넣어주면 됨.")

        if not spotify_client_id or not spotify_client_secret:
            raise ValueError(
                "Spotify 클라이언트 자격 증명을 입력하면 됨."
                " SPOTIFY_CLIENT_ID와 SPOTIFY_CLIENT_SECRET을 설정하면 됨."
            )

        default_seed_raw = os.getenv("SPOTIFY_DEFAULT_SEED_GENRES", "")
        default_seed_genres = tuple(
            genre.lower()
            for genre in (
                candidate.strip()
                for candidate in default_seed_raw.split(",")
                if candidate
            )
            if genre
        )

        return cls(
            gemini_api_key=gemini_api_key,
            spotify_client_id=spotify_client_id,
            spotify_client_secret=spotify_client_secret,
            spotify_refresh_token=os.getenv("SPOTIFY_REFRESH_TOKEN"),
            spotify_redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
            spotify_market=os.getenv("SPOTIFY_MARKET", "US"),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
            gemini_verifier_model=os.getenv("GEMINI_VERIFIER_MODEL")
            or os.getenv("GEMINI_MODEL", "gemini-1.5-pro"),
            spotify_default_seed_genres=default_seed_genres,
        )

