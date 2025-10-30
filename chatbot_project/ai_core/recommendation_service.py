"""추천 흐름을 높은 수준에서 묶어 처리하면 됨."""

from __future__ import annotations

from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .models import RecommendationResult, Track, track_to_payload
from .spotify_client import SpotifyClient


class RecommendationService:
    """Gemini 분석 결과를 받아 Spotify 추천으로 변환하면 됨."""

    _BASE_DEFAULTS: Dict[str, float] = {
        "acousticness": 0.35,
        "danceability": 0.6,
        "energy": 0.65,
        "instrumentalness": 0.2,
        "valence": 0.5,
        "tempo": 118.0,
        "loudness": -6.0,
    }

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
        artists: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> RecommendationResult:
        """넘겨받은 피처로 Spotify 추천을 요청하면 됨."""

        desired_count = limit or self._default_limit
        inferred_genres = [genre for genre in (genres or []) if isinstance(genre, str) and genre]

        normalized = self._normalize_features(target_features)
        base_profile = self._merge_with_defaults(normalized)

        requested_artists = [artist for artist in (artists or []) if isinstance(artist, str) and artist.strip()]
        resolved_artists = self._spotify_client.resolve_artist_ids(requested_artists, market=self._market)
        artist_id_lookup = {item["id"]: item.get("name", "") for item in resolved_artists}
        seed_artist_ids = [item["id"] for item in resolved_artists]
        preferred_artist_names = [item.get("name", "").lower() for item in resolved_artists if item.get("name")]
        if not preferred_artist_names:
            preferred_artist_names = [artist.lower() for artist in requested_artists]

        feature_candidates = self._plan_feature_variants(base_profile, desired_count * 2)

        tracks: List[Track] = []
        used_feature_plan: List[Dict[str, float]] = []
        raw_responses: List[Dict[str, Any]] = []
        seen_track_ids: Set[str] = set()
        audio_features_cache: Dict[str, Dict[str, float]] = {}
        used_seed_genres: Set[str] = set()
        used_seed_artists: Set[str] = set()
        used_seed_tracks: Set[str] = set()

        idx = 0
        while len(tracks) < desired_count and idx < len(feature_candidates):
            planned_features = feature_candidates[idx]
            idx += 1

            seed_genres = self._derive_seed_genres(planned_features, inferred_genres, bool(seed_artist_ids))

            response, applied_features, resp_genres, resp_artists, resp_tracks = self._spotify_client.get_recommendations(
                target_features=planned_features,
                seed_genres=seed_genres,
                seed_tracks=None,
                seed_artists=seed_artist_ids or None,
                limit=20,
                market=self._market,
            )

            raw_responses.append(response)
            used_seed_genres.update(resp_genres or seed_genres)
            used_seed_artists.update(resp_artists or seed_artist_ids)
            used_seed_tracks.update(resp_tracks or [])

            selection = self._pick_track(
                response.get("tracks", []) or [],
                planned_features,
                preferred_artist_names,
                seen_track_ids,
                audio_features_cache,
            )
            if selection is None:
                continue

            track_item, track_audio_features = selection
            seen_track_ids.add(track_item["id"])
            used_feature_plan.append(applied_features or planned_features)

            tracks.append(
                self._build_track(
                    track_item,
                    track_audio_features,
                    applied_features or planned_features,
                    seed_artists=self._translate_seed_artists(resp_artists or seed_artist_ids, artist_id_lookup),
                    seed_tracks=list(resp_tracks or []),
                )
            )

        if len(tracks) < desired_count and seed_artist_ids:
            for artist_id in seed_artist_ids:
                if len(tracks) >= desired_count:
                    break
                top_tracks = self._spotify_client.get_artist_top_tracks(artist_id, market=self._market)
                selection = self._pick_track(
                    top_tracks,
                    base_profile,
                    preferred_artist_names,
                    seen_track_ids,
                    audio_features_cache,
                )
                if selection is None:
                    continue
                track_item, track_audio_features = selection
                seen_track_ids.add(track_item["id"])
                inferred_features = track_audio_features or base_profile
                used_feature_plan.append(inferred_features)
                tracks.append(
                    self._build_track(
                        track_item,
                        track_audio_features,
                        inferred_features,
                        seed_artists=self._translate_seed_artists([artist_id], artist_id_lookup),
                        seed_tracks=[],
                    )
                )

        if len(tracks) < desired_count:
            extra_candidates: List[Dict[str, Any]] = []
            for response in raw_responses:
                extra_candidates.extend(response.get("tracks", []) or [])
            for candidate in extra_candidates:
                if len(tracks) >= desired_count:
                    break
                if candidate.get("id") in seen_track_ids:
                    continue
                selection = self._pick_track(
                    [candidate],
                    base_profile,
                    preferred_artist_names,
                    seen_track_ids,
                    audio_features_cache,
                )
                if selection is None:
                    continue
                track_item, track_audio_features = selection
                seen_track_ids.add(track_item["id"])
                inferred_features = track_audio_features or base_profile
                used_feature_plan.append(inferred_features)
                tracks.append(
                    self._build_track(
                        track_item,
                        track_audio_features,
                        inferred_features,
                        seed_artists=self._translate_seed_artists(seed_artist_ids, artist_id_lookup),
                        seed_tracks=[],
                    )
                )

        requested_artist_names = [item.get("name", "") for item in resolved_artists if item.get("name")]
        if not requested_artist_names:
            requested_artist_names = requested_artists

        result = RecommendationResult(
            features=base_profile,
            seed_genres=sorted(used_seed_genres),
            inferred_genres=inferred_genres,
            tracks=tracks,
            feature_plan=used_feature_plan,
            requested_artists=requested_artist_names,
            seed_artists=self._translate_seed_artists(list(used_seed_artists) or seed_artist_ids, artist_id_lookup),
            seed_tracks=sorted(used_seed_tracks),
            raw_responses=raw_responses,
        )

        return result

    @staticmethod
    def build_backend_payload(result: RecommendationResult) -> Dict[str, Any]:
        """백엔드에 전달하기 좋은 페이로드를 만들면 됨."""

        payload: Dict[str, Any] = {
            "provider": "spotify",
            "audio_profile": result.features,
            "feature_plan": result.feature_plan,
            "inferred_genres": result.inferred_genres,
            "seed_genres": result.seed_genres,
            "seed_artists": result.seed_artists,
            "seed_tracks": result.seed_tracks,
            "requested_artists": result.requested_artists,
            "tracks": [track_to_payload(track) for track in result.tracks],
        }

        track_features = [track.audio_features for track in result.tracks if track.audio_features]
        if track_features:
            aggregated: Dict[str, float] = {}
            feature_names = {name for features in track_features for name in features.keys()}
            for feature_name in feature_names:
                numeric_values = [
                    float(value)
                    for features in track_features
                    for value in [features.get(feature_name)]
                    if isinstance(value, (int, float))
                ]
                if numeric_values:
                    aggregated[feature_name] = float(mean(numeric_values))
            if aggregated:
                payload["audio_features_summary"] = aggregated

        return payload

    # ------------------------------------------------------------------
    def _normalize_features(self, features: Dict[str, float]) -> Dict[str, float]:
        normalized: Dict[str, float] = {}
        for name, value in (features or {}).items():
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            normalized[name] = self._clamp(name, numeric)
        return normalized

    def _merge_with_defaults(self, features: Dict[str, float]) -> Dict[str, float]:
        merged = dict(self._BASE_DEFAULTS)
        merged.update(features)
        return {key: self._clamp(key, value) for key, value in merged.items()}

    def _plan_feature_variants(self, base_features: Dict[str, float], count: int) -> List[Dict[str, float]]:
        patterns: List[Dict[str, float]] = [
            {"energy": 0.08, "danceability": 0.05, "tempo": 6},
            {"energy": -0.05, "valence": 0.07, "danceability": 0.02},
            {"instrumentalness": 0.12, "acousticness": 0.1, "energy": -0.04},
            {"danceability": 0.08, "valence": -0.05, "tempo": -4},
            {"energy": 0.04, "tempo": 10, "valence": 0.05},
            {"instrumentalness": -0.1, "danceability": 0.06, "energy": 0.05},
        ]

        variants: List[Dict[str, float]] = []
        for idx in range(max(1, count)):
            variant = dict(base_features)
            pattern = patterns[idx % len(patterns)]
            for feature_name, delta in pattern.items():
                base_value = variant.get(feature_name, base_features.get(feature_name))
                if base_value is None:
                    continue
                variant[feature_name] = self._clamp(feature_name, base_value + delta)
            variants.append(variant)

        return variants

    def _derive_seed_genres(
        self,
        features: Dict[str, float],
        inferred_genres: List[str],
        has_artist_seeds: bool,
    ) -> List[str]:
        allowed = {genre.lower() for genre in self._spotify_client.DEFAULT_SEED_GENRES}
        seeds: List[str] = []

        for genre in inferred_genres:
            normalized = genre.lower()
            if normalized in allowed and normalized not in seeds:
                seeds.append(normalized)

        if not seeds:
            energy = features.get("energy", 0.5)
            dance = features.get("danceability", 0.5)
            valence = features.get("valence", 0.5)
            acoustic = features.get("acousticness", 0.5)

            candidates = []
            if energy >= 0.7:
                candidates.extend(["edm", "dance", "electro"])
            if dance >= 0.65:
                candidates.append("dance")
            if valence >= 0.6:
                candidates.append("pop")
            if acoustic >= 0.6:
                candidates.append("latin")
            if energy < 0.45:
                candidates.append("r-n-b")
            if valence < 0.4:
                candidates.append("hip-hop")

            for candidate in candidates:
                normalized = candidate.lower()
                if normalized in allowed and normalized not in seeds:
                    seeds.append(normalized)

        if not seeds and not has_artist_seeds:
            seeds.append("pop")

        return seeds[:3]

    def _pick_track(
        self,
        candidates: Iterable[Dict[str, Any]],
        target_features: Dict[str, float],
        preferred_artists: List[str],
        seen_track_ids: Set[str],
        cache: Dict[str, Dict[str, float]],
        *,
        popularity_floor: int = 50,
    ) -> Optional[Tuple[Dict[str, Any], Optional[Dict[str, float]]]]:
        candidate_list = [item for item in candidates if item and item.get("id") and item.get("id") not in seen_track_ids]
        if not candidate_list:
            return None

        missing_ids = [item["id"] for item in candidate_list if item["id"] not in cache]
        if missing_ids:
            cache.update(self._spotify_client.get_audio_features(missing_ids))

        preferred = [artist.lower() for artist in preferred_artists]

        def score(item: Dict[str, Any]) -> Tuple[int, float, int]:
            audio = cache.get(item["id"])
            popularity = int(item.get("popularity", 0) or 0)
            artist_names = [artist.get("name", "").lower() for artist in item.get("artists", []) if artist.get("name")]
            artist_hit = 1 if preferred and any(name in artist_names for name in preferred) else 0

            if audio:
                differences = [
                    abs(audio.get(feature, target_features.get(feature, 0.0)) - target_features.get(feature, 0.0))
                    for feature in target_features.keys()
                    if feature in audio
                ]
                feature_score = sum(differences) / len(differences) if differences else 1.0
            else:
                feature_score = 1.0

            return (-artist_hit, feature_score, -popularity)

        ordered = sorted(candidate_list, key=score)

        for item in ordered:
            if int(item.get("popularity", 0) or 0) >= popularity_floor:
                return item, cache.get(item["id"])

        fallback = ordered[0]
        return fallback, cache.get(fallback["id"])

    def _build_track(
        self,
        track_item: Dict[str, Any],
        audio_features: Optional[Dict[str, float]],
        target_features: Dict[str, float],
        *,
        seed_artists: List[str],
        seed_tracks: List[str],
    ) -> Track:
        album = track_item.get("album") or {}
        album_images = album.get("images") or []
        image_url = album_images[0]["url"] if album_images else None

        return Track(
            id=track_item["id"],
            name=track_item.get("name", ""),
            artists=[artist.get("name", "") for artist in track_item.get("artists", []) if artist.get("name")],
            external_url=(track_item.get("external_urls") or {}).get("spotify", ""),
            album_image=image_url,
            audio_features=audio_features,
            popularity=track_item.get("popularity"),
            target_features=target_features,
            seed_artists=seed_artists,
            seed_tracks=seed_tracks,
        )

    @staticmethod
    def _translate_seed_artists(seed_ids: List[str], lookup: Dict[str, str]) -> List[str]:
        translated: List[str] = []
        for seed in seed_ids:
            if seed in lookup and lookup[seed]:
                translated.append(lookup[seed])
            elif isinstance(seed, str) and seed:
                translated.append(seed)
        return translated

    @staticmethod
    def _clamp(name: str, value: float) -> float:
        bounds = SpotifyClient._FEATURE_LIMITS.get(name, (-1e9, 1e9))
        return max(bounds[0], min(bounds[1], value))

