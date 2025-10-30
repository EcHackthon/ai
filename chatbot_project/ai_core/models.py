"""AI 코어 패키지에서 함께 쓰는 도메인 모델을 모아두면 됨."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Track:
    """Spotify 추천 API가 내려준 트랙 정보를 이 구조에 담으면 됨."""

    id: str
    name: str
    artists: List[str]
    external_url: str
    album_image: Optional[str]
    audio_features: Optional[Dict[str, float]] = None
    popularity: Optional[int] = None
    target_features: Dict[str, float] = field(default_factory=dict)
    seed_artists: List[str] = field(default_factory=list)
    seed_tracks: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecommendationResult:
    """Spotify 추천 결과와 관련 정보를 함께 보관하면 됨.

    ``features`` 필드에는 Spotify 문서에서 권장한 범위로 정리된 값이 들어있으면 됨.
    """

    features: Dict[str, float]
    seed_genres: List[str]
    inferred_genres: List[str]
    tracks: List[Track] = field(default_factory=list)
    feature_plan: List[Dict[str, float]] = field(default_factory=list)
    requested_artists: List[str] = field(default_factory=list)
    seed_artists: List[str] = field(default_factory=list)
    seed_tracks: List[str] = field(default_factory=list)
    raw_responses: List[Dict[str, Any]] = field(default_factory=list)


def track_to_payload(track: Track) -> Dict[str, Any]:
    """``Track`` 데이터를 직렬화 가능한 딕셔너리로 바꾸면 됨."""

    payload: Dict[str, Any] = {
        "id": track.id,
        "name": track.name,
        "artists": track.artists,
        "url": track.external_url,
        "album_image": track.album_image,
    }
    if track.popularity is not None:
        payload["popularity"] = track.popularity
    if track.audio_features is not None:
        payload["audio_features"] = track.audio_features
    if track.target_features:
        payload["target_features"] = track.target_features
    if track.seed_artists:
        payload["seed_artists"] = track.seed_artists
    if track.seed_tracks:
        payload["seed_tracks"] = track.seed_tracks

    return payload

