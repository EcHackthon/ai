"""Spotify Web API를 얇게 감싸서 인증과 추천 호출을 처리하면 됨."""

from __future__ import annotations

import base64
import time
from typing import Dict, List, Optional, Set

import requests

from .config import Settings


class SpotifyAuthError(RuntimeError):
    """Spotify 인증에 실패하면 이 예외를 던지면 됨."""


class SpotifyClient:
    """토큰 관리까지 포함한 Spotify Web API 클라이언트를 제공하면 됨."""

    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE_URL = "https://api.spotify.com/v1"

    def __init__(self, settings: Settings):
        self._client_id = settings.spotify_client_id
        self._client_secret = settings.spotify_client_secret
        self._refresh_token = settings.spotify_refresh_token
        self._redirect_uri = settings.spotify_redirect_uri
        self._default_seed_genres = settings.spotify_default_seed_genres

        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._cached_genre_seeds: Optional[Set[str]] = None

    # ------------------------------------------------------------------
    # 인증 보조 함수는 이렇게 묶으면 됨
    # ------------------------------------------------------------------
    def _authorisation_header(self) -> Dict[str, str]:
        if not self._access_token or time.time() >= self._token_expiry - 30:
            self._refresh_access_token()

        return {"Authorization": f"Bearer {self._access_token}"}

    def _refresh_access_token(self) -> None:
        """설정된 전략에 맞게 새 액세스 토큰을 받아오면 됨."""

        payload = {"grant_type": "client_credentials"}

        if self._refresh_token:
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            }

            if self._redirect_uri:
                payload["redirect_uri"] = self._redirect_uri

        auth_header = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode("utf-8")
        ).decode("utf-8")

        response = requests.post(
            self.TOKEN_URL,
            data=payload,
            headers={"Authorization": f"Basic {auth_header}"},
            timeout=15,
        )

        if response.status_code != 200:
            raise SpotifyAuthError(
                "Failed to refresh Spotify token: "
                f"{response.status_code} {response.text}"
            )

        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in

    # ------------------------------------------------------------------
    # 외부에서 사용하는 공개 API는 이렇게 두면 됨
    # ------------------------------------------------------------------
    def get_recommendations(
        self,
        *,
        target_features: Dict[str, float],
        seed_genres: Optional[List[str]] = None,
        limit: int = 5,
        market: Optional[str] = None,
    ) -> Dict:
        """Spotify 추천 엔드포인트를 호출하면 됨.

        Parameters
        ----------
        target_features:
            원하는 오디오 피처 값을 ``feature: value`` 형태로 넘기면 됨.
            메서드가 자동으로 ``target_`` 접두사를 붙이면 됨.
        seed_genres:
            Gemini가 골라준 장르 목록을 최대 5개까지 넣으면 됨.
        limit:
            요청할 트랙 수를 정하면 됨(기본 5개).
        market:
            필요하다면 ``US``나 ``KR``처럼 마켓 코드를 지정하면 됨.
        """

        params: Dict[str, str] = {"limit": str(limit)}

        if market:
            params["market"] = market

        filtered_seed_genres = self._select_seed_genres(seed_genres)
        if filtered_seed_genres:
            params["seed_genres"] = ",".join(filtered_seed_genres)

        for feature, value in target_features.items():
            # Spotify에서는 ``target_<feature>`` 형태로 보내면 됨
            params[f"target_{feature}"] = str(value)

        response = requests.get(
            f"{self.API_BASE_URL}/recommendations",
            headers=self._authorisation_header(),
            params=params,
            timeout=15,
        )

        if response.status_code == 401:
            # 토큰이 만료되었으니 새로 갱신하고 한 번만 재시도하면 됨
            self._refresh_access_token()
            response = requests.get(
                f"{self.API_BASE_URL}/recommendations",
                headers=self._authorisation_header(),
                params=params,
                timeout=15,
            )

        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # 장르 시드 관련 보조 함수를 정리하면 됨
    # ------------------------------------------------------------------
    def _select_seed_genres(self, seed_genres: Optional[List[str]]) -> List[str]:
        """Spotify에서 허용하는 장르만 골라 쓰면 됨."""

        available = self._get_available_genre_seeds()

        candidates = [
            genre.strip().lower()
            for genre in seed_genres or []
            if genre and genre.strip().lower() in available
        ]

        if not candidates:
            candidates = [
                genre
                for genre in self._default_seed_genres
                if genre in available
            ]

        if not candidates:
            # 혹시 기본 장르가 모두 사라졌다면 API가 준 목록에서 앞부분만 쓰면 됨
            candidates = list(available)[:5]

        return candidates[:5]

    def _get_available_genre_seeds(self) -> Set[str]:
        """Spotify가 지원하는 장르 시드를 캐시해서 쓰면 됨."""

        if self._cached_genre_seeds:
            return self._cached_genre_seeds

        response = requests.get(
            f"{self.API_BASE_URL}/recommendations/available-genre-seeds",
            headers=self._authorisation_header(),
            timeout=15,
        )

        if response.status_code == 401:
            self._refresh_access_token()
            response = requests.get(
                f"{self.API_BASE_URL}/recommendations/available-genre-seeds",
                headers=self._authorisation_header(),
                timeout=15,
            )

        response.raise_for_status()
        payload = response.json()
        genres = set(payload.get("genres", []))

        if not genres:
            raise SpotifyAuthError(
                "Spotify에서 제공하는 장르 시드를 가져오지 못했으니 설정을 확인하면 됨."
            )

        self._cached_genre_seeds = genres
        return genres

