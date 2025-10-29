"""추천 흐름을 높은 수준에서 묶어 처리하면 됨."""

from __future__ import annotations

from typing import Dict, List, Optional

from .models import RecommendationResult, Track, track_to_payload
from .spotify_client import SpotifyClient


class RecommendationService:
    """Gemini 분석 결과를 받아 Spotify 추천으로 변환하면 됨."""

    def __init__(
        self,
        spotify_client: SpotifyClient,
        *,
        default_limit: int = 5,
        market: Optional[str] = None,
    ) -> None:
        self._spotify_client = spotify_client
        self._default_limit = default_limit
        self._market = market

    def recommend(
        self,
        *,
        target_features: Dict[str, float],
        genres: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> RecommendationResult:
        """넘겨받은 피처로 Spotify 추천을 요청하면 됨."""

        limit = limit or self._default_limit

        raw_response = self._spotify_client.get_recommendations(
            target_features=target_features,
            seed_genres=genres,
            limit=limit,
            market=self._market,
        )

        tracks: List[Track] = []
        for item in raw_response.get("tracks", []):
            album_images = item.get("album", {}).get("images", [])
            tracks.append(
                Track(
                    id=item["id"],
                    name=item["name"],
                    artists=[artist["name"] for artist in item.get("artists", [])],
                    external_url=item.get("external_urls", {}).get("spotify", ""),
                    preview_url=item.get("preview_url"),
                    album_image=album_images[0]["url"] if album_images else None,
                )
            )

        return RecommendationResult(
            features=target_features,
            genres=genres or [],
            tracks=tracks,
            raw_response=raw_response,
        )

    @staticmethod
    def build_backend_payload(result: RecommendationResult) -> Dict:
        """백엔드에 전달하기 좋은 페이로드를 만들면 됨."""

        return {
            "provider": "spotify",
            "audio_features": result.features,
            "genres": result.genres,
            "tracks": [track_to_payload(track) for track in result.tracks],
        }

