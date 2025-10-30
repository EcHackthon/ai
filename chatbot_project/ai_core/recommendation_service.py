"""추천 흐름을 높은 수준에서 묶어 처리하면 됨."""

from __future__ import annotations

from statistics import mean
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

        inferred_genres = [genre for genre in (genres or []) if genre]

        raw_response, applied_features, used_genres = self._spotify_client.get_recommendations(
            target_features=target_features,
            seed_genres=inferred_genres,
            limit=limit,
            market=self._market,
        )

        tracks: List[Track] = []
        original_tracks = raw_response.get("tracks", [])
        raw_tracks = [
            item
            for item in original_tracks
            if item.get("popularity", 0) >= 35
        ]
        if not raw_tracks:
            raw_tracks = original_tracks

        audio_features_map = {}
        track_ids = [item.get("id") for item in raw_tracks if item.get("id")]
        if track_ids:
            audio_features_map = self._spotify_client.get_audio_features(track_ids)

        for item in raw_tracks:
            album_images = item.get("album", {}).get("images", [])
            tracks.append(
                Track(
                    id=item["id"],
                    name=item["name"],
                    artists=[artist["name"] for artist in item.get("artists", [])],
                    external_url=item.get("external_urls", {}).get("spotify", ""),
                    album_image=album_images[0]["url"] if album_images else None,
                    audio_features=audio_features_map.get(item["id"]),
                )
            )

        return RecommendationResult(
            features=applied_features,
            seed_genres=used_genres,
            inferred_genres=inferred_genres,
            tracks=tracks,
            raw_response=raw_response,
        )

    @staticmethod
    def build_backend_payload(result: RecommendationResult) -> Dict:
        """백엔드에 전달하기 좋은 페이로드를 만들면 됨."""

        payload = {
            "provider": "spotify",
            "audio_profile": result.features,
            "inferred_genres": result.inferred_genres,
            "seed_genres": result.seed_genres,
            "tracks": [track_to_payload(track) for track in result.tracks],
        }

        track_features = [track.audio_features for track in result.tracks if track.audio_features]
        if track_features:
            aggregated: Dict[str, float] = {}
            for feature_name in track_features[0].keys():
                values = [features.get(feature_name) for features in track_features if feature_name in features]
                numeric_values = [value for value in values if isinstance(value, (int, float))]
                if numeric_values:
                    aggregated[feature_name] = float(mean(numeric_values))
            if aggregated:
                payload["audio_features_summary"] = aggregated

        return payload

