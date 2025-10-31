"""Helpers for turning chat analysis into Spotify recommendations."""

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
        target_features: Optional[Dict[str, float]] = None,
        profile: Optional[Dict[str, float]] = None,
        genres: Optional[List[str]] = None,
        seed_artists: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> RecommendationResult:
        """Request Spotify recommendations based on the analysed profile."""

        # Allow legacy callers that still pass `profile` instead of `target_features`
        if target_features is None and profile is not None:
            target_features = profile
        if not isinstance(target_features, dict):
            raise ValueError("target_features must be provided as a dict")

        limit = limit or self._default_limit

        inferred_genres: List[str] = []
        seen_genres = set()
        for genre in genres or []:
            if not isinstance(genre, str):
                continue
            cleaned = genre.strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen_genres:
                continue
            inferred_genres.append(cleaned)
            seen_genres.add(lowered)

        normalized_seed_genres = self._spotify_client.normalize_genres(inferred_genres)

        seed_artist_names = [
            str(name).strip()
            for name in (seed_artists or [])
            if isinstance(name, str) and str(name).strip()
        ]
        resolved_artist_ids = (
            self._spotify_client.resolve_artist_ids(seed_artist_names, market=self._market)
            if seed_artist_names
            else {}
        )
        seed_artist_ids = list(resolved_artist_ids.values())

        raw_response, applied_features, used_genres = self._spotify_client.get_recommendations(
            target_features=target_features,
            seed_genres=normalized_seed_genres,
            seed_artists=seed_artist_ids,
            limit=limit,
            market=self._market,
        )
        if not used_genres:
            used_genres = normalized_seed_genres.copy()

        original_tracks = raw_response.get("tracks", [])
        raw_tracks = [
            item for item in original_tracks
            if item.get("popularity", 0) >= 40
        ]
        if not raw_tracks:
            raw_tracks = original_tracks

        # Prefer artist diversity (avoid many tracks from the same artist)
        seen_artists = set()
        diverse_tracks = []
        for it in raw_tracks:
            artist_names = tuple(artist.get("name") for artist in it.get("artists", []) if artist.get("name"))
            key = artist_names[0] if artist_names else None
            if key is None or key not in seen_artists:
                if key:
                    seen_artists.add(key)
                diverse_tracks.append(it)
        raw_tracks = diverse_tracks or raw_tracks

        matched_seed_artists: List[str] = []
        if seed_artist_names:
            seed_lookup = {name.lower(): name for name in seed_artist_names}
            filtered: List[dict] = []
            for it in raw_tracks:
                artist_names = [a.get("name", "") for a in it.get("artists", [])]
                lower_names = [name.lower() for name in artist_names if name]
                overlap = [seed_lookup[name] for name in lower_names if name in seed_lookup]
                if overlap:
                    filtered.append(it)
                    for name in overlap:
                        if name not in matched_seed_artists:
                            matched_seed_artists.append(name)
            if filtered:
                raw_tracks = filtered
            if seed_artist_ids and len(raw_tracks) < limit:
                fallback_tracks = self._spotify_client.get_artist_top_tracks(
                    seed_artist_ids,
                    market=self._market,
                    limit=limit * 2,
                )
                extra: List[dict] = []
                seen_ids = {item.get("id") for item in raw_tracks if item.get("id")}
                for track in fallback_tracks:
                    tid = track.get("id")
                    if not tid or tid in seen_ids:
                        continue
                    seen_ids.add(tid)
                    extra.append(track)
                    if len(raw_tracks) + len(extra) >= limit:
                        break
                    artist_names = [a.get("name", "") for a in track.get("artists", [])]
                    for name in artist_names:
                        canonical = seed_lookup.get(name.lower())
                        if canonical and canonical not in matched_seed_artists:
                            matched_seed_artists.append(canonical)
                if extra:
                    raw_tracks.extend(extra)
            if not raw_tracks and seed_artist_ids:
                fallback_tracks = self._spotify_client.get_artist_top_tracks(
                    seed_artist_ids,
                    market=self._market,
                    limit=limit,
                )
                if fallback_tracks:
                    raw_tracks = fallback_tracks
                    matched_seed_artists = seed_artist_names.copy()

        audio_features_map: Dict[str, Dict[str, float]] = {}
        track_ids = [item.get("id") for item in raw_tracks if item.get("id")]
        if track_ids:
            audio_features_map = self._spotify_client.get_audio_features(track_ids)

        tracks: List[Track] = []
        for item in raw_tracks:
            track_id = item.get("id")
            if not track_id:
                continue
            album_images = item.get("album", {}).get("images", [])
            features = audio_features_map.get(track_id)
            summary = self._summarize_track(features, inferred_genres)
            tracks.append(
                Track(
                    id=track_id,
                    name=item.get("name", ""),
                    artists=[artist.get("name", "") for artist in item.get("artists", []) if artist.get("name")],
                    external_url=item.get("external_urls", {}).get("spotify", ""),
                    album_image=album_images[0]["url"] if album_images else None,
                    audio_features=features,
                    summary=summary,
                )
            )

        if not matched_seed_artists and seed_artist_names:
            matched_seed_artists = seed_artist_names.copy()

        return RecommendationResult(
            features=applied_features,
            seed_genres=used_genres,
            seed_artists=matched_seed_artists,
            inferred_genres=inferred_genres,
            tracks=tracks,
            raw_response=raw_response,
        )

    @staticmethod
    def build_backend_payload(result: RecommendationResult) -> Dict:
        """Build a backend-friendly payload from a recommendation result."""

        payload = {
            "provider": "spotify",
            "audio_profile": result.features,
            "inferred_genres": result.inferred_genres,
            "seed_genres": result.seed_genres,
            "seed_artists": result.seed_artists,
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

    @staticmethod
    def _summarize_track(
        audio_features: Optional[Dict[str, float]],
        genres: List[str],
    ) -> Optional[str]:
        if not isinstance(audio_features, dict):
            return None

        def _feature(name: str) -> Optional[float]:
            value = audio_features.get(name)
            if isinstance(value, (int, float)):
                return float(value)
            return None

        descriptors: List[str] = []
        energy = _feature("energy")
        valence = _feature("valence")
        dance = _feature("danceability")
        acoustic = _feature("acousticness")
        instrumental = _feature("instrumentalness")
        tempo = _feature("tempo")

        if energy is not None:
            if energy >= 0.7:
                descriptors.append("high-energy feel")
            elif energy <= 0.35:
                descriptors.append("calm energy")
        if valence is not None:
            if valence >= 0.65:
                descriptors.append("uplifting mood")
            elif valence <= 0.3:
                descriptors.append("moody vibes")
        if dance is not None:
            if dance >= 0.65:
                descriptors.append("danceable beat")
            elif dance <= 0.35:
                descriptors.append("laid-back groove")
        if acoustic is not None and acoustic >= 0.6:
            descriptors.append("acoustic texture")
        elif instrumental is not None and instrumental >= 0.6:
            descriptors.append("instrumental focus")

        genre_candidates = [
            g.strip() for g in genres or [] if isinstance(g, str) and g.strip()
        ]
        genre_phrase = None
        if genre_candidates:
            genre_phrase = f"{', '.join(genre_candidates[:2])} vibe"

        tempo_phrase = None
        if tempo is not None and tempo > 0:
            tempo_phrase = f"around {int(round(tempo))} BPM"

        components: List[str] = []
        if genre_phrase:
            components.append(genre_phrase)
        if descriptors:
            components.append(", ".join(descriptors[:2]))
        if tempo_phrase:
            components.append(tempo_phrase)

        if not components:
            return None

        return " | ".join(components) + "."

