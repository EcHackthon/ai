"""애플리케이션 환경 설정을 한곳에서 불러오면 됨."""

from __future__ import annotations

from dataclasses import dataclass
import re
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
    spotify_market: str = "KR"
    spotify_default_seed_genres: Tuple[str, ...] = tuple()
    gemini_model: str = "gemini-2.0-flash-exp"

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

        # Enforce Gemini >= 2.0 and flash family
        model_raw = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        model = _ensure_gemini_flash_v2_or_newer(model_raw)

        return cls(
            gemini_api_key=gemini_api_key,
            spotify_client_id=spotify_client_id,
            spotify_client_secret=spotify_client_secret,
            spotify_refresh_token=os.getenv("SPOTIFY_REFRESH_TOKEN"),
            spotify_redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
            spotify_market=os.getenv("SPOTIFY_MARKET", "KR"),
            gemini_model=model,
            spotify_default_seed_genres=default_seed_genres,
        )


def _ensure_gemini_flash_v2_or_newer(name: str) -> str:
    """Validate and coerce Gemini model to 2.0+ flash family.

    - Accepts variants like "gemini-2.0-flash-exp", "gemini-2.1-flash", "gemini-2.0-flash".
    - If lower than 2.0 or missing flash, coerces to "gemini-2.0-flash".
    """

    if not isinstance(name, str) or not name:
        return "gemini-2.0-flash"

    m = re.match(r"^gemini-(\d+)(?:\.(\d+))?-(.+)$", name.strip())
    if not m:
        return "gemini-2.0-flash"

    major = int(m.group(1))
    family = m.group(3)
    if major < 2:
        return "gemini-2.0-flash"
    if "flash" not in family:
        # force flash line if other family provided
        return f"gemini-{major}.0-flash"
    return name.strip()
