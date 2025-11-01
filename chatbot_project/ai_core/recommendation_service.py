"""Helpers for turning chat analysis into Spotify recommendations."""

from __future__ import annotations

import random
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from .models import RecommendationResult, Track, track_to_payload
from .spotify_client import ArtistLite, SpotifyClient


class RecommendationService:
    # _fix61_helpers
    def _contains_hangul(self, text: str) -> bool:
        if not text:
            return False
        return bool(__import__("re").search(r"[\uac00-\ud7af]", text))

    def _korean_like(self, track: dict, genres: List[str], market: str) -> bool:
        genre_blob = ",".join([s.lower() for s in genres or []])
        if "k-" in genre_blob or "korean" in genre_blob or market.upper() == "KR":
            name = track.get("name") or ""
            artists = [(artist.get("name") or "") for artist in (track.get("artists") or [])]
            if any(self._contains_hangul(text) for text in [name] + artists):
                return True
            # If no Hangul characters, still allow; we just prefer Hangul if available.
        return True

    def _norm_pair(self, name: str, artist: str) -> str:
        import re

        track_name = re.sub(r"\s+", " ", (name or "").lower()).strip()
        artist_name = re.sub(r"\s+", " ", (artist or "").lower()).strip()
        return f"{track_name}::{artist_name}"

    def _feature_distance(self, feats: dict, target: dict) -> float:
        if not feats or not target:
            return 1e9
        keys = ["acousticness", "danceability", "energy", "instrumentalness", "valence"]
        total = 0.0
        count = 0
        for key in keys:
            if key in feats and key in target:
                delta = float(feats[key]) - float(target[key])
                total += delta * delta
                count += 1
        if "tempo" in feats and "tempo" in target:
            delta = (float(feats["tempo"]) - float(target["tempo"])) / 50.0
            total += delta * delta
            count += 1
        if "loudness" in feats and "loudness" in target:
            delta = (float(feats["loudness"]) - float(target["loudness"])) / 10.0
            total += delta * delta
            count += 1
        if count == 0:
            return 1e9
        return (total / count) ** 0.5

    def _normalize_target_features(
        self,
        raw_features: Optional[Dict[str, Any]],
        *,
        declared_ranges: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
        centers: Dict[str, float] = {}
        ranges: Dict[str, Dict[str, float]] = {}

        def _parse_num(value: Any) -> Optional[float]:
            if isinstance(value, (int, float)):
                return float(value)
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _coerce_range(payload: Any) -> Optional[Dict[str, float]]:
            lo = hi = target = None
            if isinstance(payload, dict):
                lo = _parse_num(payload.get("min"))
                hi = _parse_num(payload.get("max"))
                target = _parse_num(
                    payload.get("target")
                    or payload.get("value")
                    or payload.get("center")
                    or payload.get("mid")
                    or payload.get("mean")
                )
                spread = _parse_num(payload.get("spread") or payload.get("width") or payload.get("delta"))
                if spread is not None and target is not None:
                    if lo is None:
                        lo = target - spread
                    if hi is None:
                        hi = target + spread
                if target is None and lo is not None and hi is not None:
                    target = (lo + hi) / 2.0
                if target is None and lo is not None and hi is None:
                    hi = lo
                    target = lo
                if target is None and hi is not None and lo is None:
                    lo = hi
                    target = hi
            elif isinstance(payload, (list, tuple)) and len(payload) >= 2:
                lo = _parse_num(payload[0])
                hi = _parse_num(payload[1])
                target = _parse_num(payload[2]) if len(payload) >= 3 else None
                if target is None and lo is not None and hi is not None:
                    target = (lo + hi) / 2.0
            else:
                return None
            if lo is None and hi is None and target is not None:
                lo = hi = target
            if lo is None:
                lo = hi
            if hi is None:
                hi = lo
            if lo is None or hi is None:
                return None
            lo_f = float(lo)
            hi_f = float(hi)
            if hi_f < lo_f:
                lo_f, hi_f = hi_f, lo_f
            target_val = float(target) if target is not None else (lo_f + hi_f) / 2.0
            return {"min": lo_f, "max": hi_f, "target": target_val}

        if isinstance(declared_ranges, dict):
            for name, payload in declared_ranges.items():
                if not isinstance(name, str):
                    continue
                coerced = _coerce_range(payload)
                if coerced is None:
                    continue
                ranges[name] = coerced
                centers.setdefault(name, coerced["target"])

        if isinstance(raw_features, dict):
            for name, value in raw_features.items():
                if not isinstance(name, str):
                    continue
                coerced = None
                if isinstance(value, (dict, list, tuple)):
                    coerced = _coerce_range(value)
                if coerced is not None:
                    ranges[name] = coerced
                    centers[name] = coerced["target"]
                    continue
                num = _parse_num(value)
                if num is None:
                    continue
                centers[name] = num
                entry = ranges.get(name)
                if entry is None:
                    ranges[name] = {"min": num, "max": num, "target": num}
                else:
                    entry["target"] = num
                    entry["min"] = min(entry.get("min", num), num)
                    entry["max"] = max(entry.get("max", num), num)

        for name, value in list(centers.items()):
            entry = ranges.setdefault(name, {"min": value, "max": value, "target": value})
            entry["target"] = float(entry.get("target", value))
            entry["min"] = min(float(entry.get("min", value)), value)
            entry["max"] = max(float(entry.get("max", value)), value)

        for name, info in list(ranges.items()):
            if name not in centers:
                target = info.get("target")
                if isinstance(target, (int, float)):
                    centers[name] = float(target)

        return centers, ranges

    def _sample_target_features(
        self,
        centers: Dict[str, float],
        ranges: Dict[str, Dict[str, float]],
    ) -> Dict[str, float]:
        if not centers and not ranges:
            return {}
        sampled: Dict[str, float] = {}
        for name, center in centers.items():
            info = ranges.get(name) or {}
            lo = info.get("min", center)
            hi = info.get("max", center)
            if lo is None or hi is None:
                sampled[name] = center
                continue
            lo_f = float(lo)
            hi_f = float(hi)
            if hi_f < lo_f:
                lo_f, hi_f = hi_f, lo_f
            if hi_f - lo_f <= 1e-6:
                sampled[name] = center
            else:
                sampled[name] = self._random.uniform(lo_f, hi_f)
        for name, info in ranges.items():
            if name in sampled:
                continue
            lo = info.get("min")
            hi = info.get("max")
            if lo is None and hi is None:
                continue
            if lo is None:
                lo = hi
            if hi is None:
                hi = lo
            if lo is None or hi is None:
                continue
            lo_f = float(lo)
            hi_f = float(hi)
            if hi_f < lo_f:
                lo_f, hi_f = hi_f, lo_f
            if hi_f - lo_f <= 1e-6:
                sampled[name] = lo_f
            else:
                sampled[name] = self._random.uniform(lo_f, hi_f)
        return sampled

    # ---- fix6 era-aware helpers ----
    def _extract_release_year(self, item: dict) -> int:
        try:
            date = (item.get("album") or {}).get("release_date") or ""
            return int(str(date).split("-")[0]) if date else 0
        except Exception:
            return 0

    def _is_remaster_like(self, item: dict) -> bool:
        title = (item.get("name") or "").lower()
        album = ((item.get("album") or {}).get("name") or "").lower()
        keywords = [
            "remaster",
            "remastered",
            "re-recorded",
            "compilation",
            "greatest hits",
            "new stereo",
        ]
        return any(keyword in title for keyword in keywords) or any(keyword in album for keyword in keywords)

    def _era_from_context(self, genres: List[str], seed_artists: List[str]) -> tuple[int, int]:
        genre_blob = ",".join([s.lower() for s in genres or []])
        artist_blob = ",".join([s.lower() for s in seed_artists or []])
        # Heuristic: classic/vintage french house
        if (
            "classic french house" in genre_blob
            or "french touch" in genre_blob
            or any(name in artist_blob for name in ["daft punk", "modjo", "stardust", "cassius", "etienne de crecy"])
        ):
            return (1996, 2003)
        # default: no strict era
        return (0, 0)

    def _score_item(self, item: dict, *, era: tuple[int, int]) -> float:
        popularity = float(item.get("popularity") or 0) / 100.0
        start_year, end_year = era
        year = self._extract_release_year(item)
        era_bonus = 0.0
        if start_year and year:
            if start_year <= year <= end_year:
                # Gaussian-ish bonus centered in era
                center = (start_year + end_year) / 2.0
                width = max(1.0, (end_year - start_year) / 2.0)
                era_bonus = __import__("math").exp(-((year - center) ** 2) / (2.0 * width * width)) * 0.6
            else:
                # small penalty if far from era when era specified
                era_bonus = -0.2
        remaster_penalty = -0.25 if self._is_remaster_like(item) else 0.0
        return popularity + era_bonus + remaster_penalty

    """Convert Gemini analysis into Spotify recommendation results."""

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
        self._random = random.Random()
        self._user_track_history: Dict[str, List[str]] = {}
        self._history_max = 200

    def _sanitize_raw_response(self, raw: dict) -> dict:
        raw = dict(raw or {})
        if not isinstance(raw.get("per_track_jitter_hint"), dict):
            raw["per_track_jitter_hint"] = {}
        genres = raw.get("inferred_genres") or []
        if isinstance(genres, list):
            raw["inferred_genres"] = sorted({(g or "").strip().lower() for g in genres if g})
        else:
            raw["inferred_genres"] = []
        return raw

    def recommend(
        self,
        *,
        target_features: Optional[Dict[str, Any]] = None,
        target_feature_ranges: Optional[Dict[str, Any]] = None,
        profile: Optional[Dict[str, float]] = None,
        genres: Optional[List[str]] = None,
        seed_artists: Optional[List[str]] = None,
        limit: Optional[int] = None,
        user_token: Optional[str] = None,
    ) -> RecommendationResult:
        """Request Spotify recommendations based on the analysed profile."""

        if target_features is None and profile is not None:
            target_features = profile
        declared_ranges = target_feature_ranges if isinstance(target_feature_ranges, dict) else None
        if target_features is None and declared_ranges is not None:
            target_features = {}
        if not isinstance(target_features, dict):
            raise ValueError("target_features must be provided as a dict")

        centers, feature_ranges = self._normalize_target_features(target_features, declared_ranges=declared_ranges)
        if not centers and feature_ranges:
            centers = {name: info.get("target") for name, info in feature_ranges.items() if isinstance(info, dict)}
            centers = {name: value for name, value in centers.items() if isinstance(value, (int, float))}
        limit = limit or self._default_limit
        requested_target_features = dict(centers)
        sampled_target_features = self._sample_target_features(centers, feature_ranges)
        sanitized_range_payload = {
            name: {"min": info.get("min"), "max": info.get("max")}
            for name, info in feature_ranges.items()
            if isinstance(info, dict) and info.get("min") is not None and info.get("max") is not None
        }

        user_key = user_token or "__default__"

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

        ## fix61_anchor_start: build anchor seeds when user didn't name artists
        if not seed_artist_names and normalized_seed_genres:
            anchors: List[ArtistLite] = []
            for genre in normalized_seed_genres[:3]:
                try:
                    anchors += self._spotify_client.search_artists_by_genre(genre, limit=10, market=self._market)
                except Exception:
                    continue
            seen_ids: set[str] = set()
            unique_anchors: List[ArtistLite] = []
            for artist in anchors:
                artist_id = getattr(artist, "id", None)
                if artist_id and artist_id not in seen_ids:
                    seen_ids.add(artist_id)
                    unique_anchors.append(artist)
            unique_anchors = sorted(
                unique_anchors,
                key=lambda artist: (getattr(artist, "followers", 0), getattr(artist, "popularity", 0)),
                reverse=True,
            )[:5]
            if unique_anchors:
                seed_artist_names = [artist.name for artist in unique_anchors]
        ## fix61_anchor_end

        resolved_artist_ids = (
            self._spotify_client.resolve_artist_ids(seed_artist_names, market=self._market)
            if seed_artist_names
            else {}
        )
        seed_artist_ids = list(resolved_artist_ids.values())

        target_payload = sampled_target_features or requested_target_features
        if not target_payload:
            target_payload = requested_target_features
        raw_response, applied_features, used_genres = self._spotify_client.get_recommendations(
            target_features=target_payload,
            feature_ranges=feature_ranges,
            seed_genres=normalized_seed_genres,
            seed_artists=seed_artist_ids,
            limit=limit,
            market=self._market,
        )
        raw_response = self._sanitize_raw_response(raw_response)
        if sanitized_range_payload and not raw_response.get("target_feature_ranges"):
            raw_response["target_feature_ranges"] = sanitized_range_payload
        raw_response["requested_target_features"] = dict(requested_target_features)
        if sampled_target_features:
            raw_response.setdefault("sampled_target_features", dict(sampled_target_features))
        if feature_ranges and not raw_response.get("target_feature_ranges"):
            raw_response["target_feature_ranges"] = {
                name: {"min": info.get("min"), "max": info.get("max")}
                for name, info in feature_ranges.items()
                if isinstance(info, dict)
            }
        if not applied_features:
            applied_features = dict(target_payload)
        response_target_features = dict(
            raw_response.get("target_features")
            or applied_features
            or requested_target_features
        )
        if not raw_response.get("target_features"):
            raw_response["target_features"] = dict(response_target_features)
        jitter_hint = raw_response.get("per_track_jitter_hint")
        if not used_genres:
            used_genres = normalized_seed_genres.copy()

        original_tracks = raw_response.get("tracks", []) or []
        raw_tracks = [
            item for item in original_tracks
            if item.get("popularity", 0) >= 40
        ]
        search_terms = self._collect_search_terms(normalized_seed_genres, inferred_genres)
        if not raw_tracks:
            ## fix6_fallback_search_start: label & text search
            label_hints = list((raw_response.get("label_hints") or []))
            pool: List[dict] = []
            try:
                for label in label_hints[:4]:
                    pool += self._spotify_client.search_tracks_by_label(label, limit=25)
            except Exception:
                pass
            if not pool:
                for genre in normalized_seed_genres[:3]:
                    try:
                        pool += self._spotify_client.search_tracks_raw(genre, limit=20)
                    except Exception:
                        continue
            era_window = self._era_from_context(inferred_genres, seed_artist_names)
            pool = [item for item in pool if item.get("id")]
            if pool:
                scored_pool = [(self._score_item(item, era=era_window), item) for item in pool]
                scored_pool.sort(key=lambda pair: pair[0], reverse=True)
                raw_tracks = [item for _, item in scored_pool[:limit]]
            ## fix6_fallback_search_end
            if not raw_tracks:
                raw_tracks = self._augment_from_search_terms(
                    terms=search_terms,
                    existing=raw_tracks,
                    limit=limit,
                    market=self._market,
                ) or original_tracks

        seen_artists = set()
        diverse_tracks: List[dict] = []
        for item in raw_tracks:
            artist_names = tuple(
                artist.get("name")
                for artist in item.get("artists", [])
                if artist.get("name")
            )
            key = artist_names[0] if artist_names else None
            if key is None or key not in seen_artists:
                if key:
                    seen_artists.add(key)
                diverse_tracks.append(item)
        raw_tracks = diverse_tracks or raw_tracks

        ## fix6_rerank_start: era-aware re-ranking
        era_window = self._era_from_context(inferred_genres, seed_artist_names)
        if raw_tracks:
            scored_tracks = [(self._score_item(item, era=era_window), item) for item in raw_tracks]
            scored_tracks.sort(key=lambda pair: pair[0], reverse=True)
            raw_tracks = [item for _, item in scored_tracks]
        ## fix6_rerank_end

        ## fix61_vibe_postproc_start: market/language filter, popularity floor, dedup, distance rank
        market_val = self._market or getattr(self._spotify_client, "market", None) or "KR"

        def apply_filters(pool: List[dict], pop_floor: int, market_code: str) -> List[dict]:
            seen_ids: set[str] = set()
            seen_pairs: set[str] = set()
            filtered: List[dict] = []
            for track in pool:
                track_id = track.get("id")
                popularity = int(track.get("popularity") or 0)
                if popularity < pop_floor:
                    continue
                if not self._korean_like(track, inferred_genres, market_code):
                    continue
                if track_id and track_id in seen_ids:
                    continue
                artist_name = ((track.get("artists") or [{}])[0].get("name") or "")
                pair_key = self._norm_pair(track.get("name"), artist_name)
                if pair_key in seen_pairs:
                    continue
                seen_ids.add(track_id)
                seen_pairs.add(pair_key)
                filtered.append(track)
            return filtered

        stage: List[dict] = []
        feat_map: Dict[str, Dict[str, float]] = {}
        if raw_tracks:
            stage = apply_filters(raw_tracks, 55, market_val)
            if len(stage) < limit:
                stage = apply_filters(raw_tracks, 50, market_val)
            if len(stage) < limit:
                stage = apply_filters(raw_tracks, 45, market_val)
        if stage:
            feats_list = self._spotify_client.get_audio_features([track["id"] for track in stage])
            for features in feats_list or []:
                if features and features.get("id"):
                    feat_map[features["id"]] = features
            scored_stage = []
            for track in stage:
                features = feat_map.get(track.get("id")) or {}
                distance = self._feature_distance(features, response_target_features)
                popularity_bonus = float(track.get("popularity") or 0) / 200.0
                scored_stage.append((-distance + popularity_bonus, track))
            scored_stage.sort(key=lambda pair: pair[0], reverse=True)
            raw_tracks = [track for _, track in scored_stage[:limit]]
        ## fix61_vibe_postproc_end
        if len(raw_tracks) < limit:
            supplements = self._augment_from_search_terms(
                terms=search_terms,
                existing=raw_tracks,
                market=self._market,
                limit=limit - len(raw_tracks),
            )
            if supplements:
                raw_tracks.extend(supplements)
                raw_tracks = apply_filters(raw_tracks, 40, market_val)
                if len(raw_tracks) < limit:
                    refill = self._augment_from_search_terms(
                        terms=search_terms,
                        existing=raw_tracks,
                        market=self._market,
                        limit=limit - len(raw_tracks),
                    )
                    if refill:
                        raw_tracks.extend(refill)
                        raw_tracks = apply_filters(raw_tracks, 40, market_val)

        matched_seed_artists: List[str] = []
        if seed_artist_names:
            seed_lookup = {name.lower(): name for name in seed_artist_names}
            filtered_tracks: List[dict] = []
            for item in raw_tracks:
                artist_names = [artist.get("name", "") for artist in item.get("artists", [])]
                lower_names = [name.lower() for name in artist_names if name]
                overlap = [seed_lookup[name] for name in lower_names if name in seed_lookup]
                if overlap:
                    filtered_tracks.append(item)
                    for name in overlap:
                        if name not in matched_seed_artists:
                            matched_seed_artists.append(name)
            if filtered_tracks:
                raw_tracks = filtered_tracks
            if seed_artist_ids and len(raw_tracks) < limit:
                fallback_tracks = self._spotify_client.get_artist_top_tracks(
                    seed_artist_ids,
                    market=self._market,
                    limit=limit * 2,
                )
                extra: List[dict] = []
                seen_ids = {item.get("id") for item in raw_tracks if item.get("id")}
                for track in fallback_tracks:
                    track_id = track.get("id")
                    if not track_id or track_id in seen_ids:
                        continue
                    seen_ids.add(track_id)
                    extra.append(track)
                    if len(raw_tracks) + len(extra) >= limit:
                        break
                    artist_names = [artist.get("name", "") for artist in track.get("artists", [])]
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
            if len(raw_tracks) < limit:
                artist_supplements = self._augment_from_artist_search(
                    seed_artist_names,
                    existing=raw_tracks,
                    market=self._market,
                    take=limit - len(raw_tracks),
                )
                if artist_supplements:
                    raw_tracks.extend(artist_supplements)

        audio_features_map: Dict[str, Dict[str, float]] = {}
        track_ids = [item.get("id") for item in raw_tracks if item.get("id")]
        if track_ids:
            audio_features_map = self._spotify_client.get_audio_features(track_ids)
        extra_margin = 5 if len(raw_tracks) > limit else 0
        rank_limit = min(len(raw_tracks), limit + extra_margin) if raw_tracks else limit
        ranked_tracks = self._rank_tracks(
            raw_tracks,
            audio_features_map,
            response_target_features,
            jitter_hint=jitter_hint,
            limit=rank_limit,
        )
        filtered_ranked_tracks = self._apply_history_filter(
            ranked_tracks,
            base_pool=list(raw_tracks),
            search_terms=search_terms,
            user_key=user_key,
            limit=limit,
        )

        tracks: List[Track] = []
        for item in filtered_ranked_tracks:
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
                    artists=[
                        artist.get("name", "")
                        for artist in item.get("artists", [])
                        if artist.get("name")
                    ],
                    external_url=item.get("external_urls", {}).get("spotify", ""),
                    album_image=album_images[0]["url"] if album_images else None,
                    audio_features=features,
                    summary=summary,
                )
            )

        self._remember_tracks(user_key, [track.id for track in tracks])

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

    def _collect_search_terms(self, normalized: List[str], inferred: List[str]) -> List[str]:
        terms: List[str] = []
        seen: set[str] = set()
        for source in (normalized or []):
            lower = source.lower().strip()
            if lower and lower not in seen:
                terms.append(lower)
                seen.add(lower)
        if not terms:
            for genre in inferred or []:
                if not isinstance(genre, str):
                    continue
                lower = genre.lower().strip()
                if lower and lower not in seen:
                    terms.append(lower)
                    seen.add(lower)
        if not terms:
            return []
        return terms[:6]

    def _augment_from_search_terms(
        self,
        *,
        terms: List[str],
        existing: List[dict],
        market: Optional[str],
        limit: int,
    ) -> List[dict]:
        if limit <= 0 or not terms:
            return []
        existing_ids = {item.get("id") for item in existing if item.get("id")}
        seen_pairs = {
            self._norm_pair(item.get("name"), ((item.get("artists") or [{}])[0].get("name") or ""))
            for item in existing
        }
        collected: List[dict] = []
        for term in terms:
            try:
                candidates = self._spotify_client.search_tracks_raw(term, limit=25, market=market)
            except Exception:
                continue
            for track in candidates:
                track_id = track.get("id")
                if not track_id or track_id in existing_ids:
                    continue
                artist_name = ((track.get("artists") or [{}])[0].get("name") or "")
                pair = self._norm_pair(track.get("name"), artist_name)
                if pair in seen_pairs:
                    continue
                existing_ids.add(track_id)
                seen_pairs.add(pair)
                collected.append(track)
                if len(collected) >= limit:
                    return collected
        return collected

    def _augment_from_artist_search(
        self,
        artist_names: List[str],
        *,
        existing: List[dict],
        market: Optional[str],
        take: int,
    ) -> List[dict]:
        if take <= 0 or not artist_names:
            return []
        existing_ids = {item.get("id") for item in existing if item.get("id")}
        seen_pairs = {
            self._norm_pair(item.get("name"), ((item.get("artists") or [{}])[0].get("name") or ""))
            for item in existing
        }
        supplements: List[dict] = []
        for artist_name in artist_names:
            query = f'artist:"{artist_name}"'
            try:
                results = self._spotify_client.search_tracks_raw(query, limit=25, market=market)
            except Exception:
                continue
            lower_seed_names = {name.lower() for name in artist_names if isinstance(name, str)}
            for track in results:
                track_id = track.get("id")
                if not track_id or track_id in existing_ids:
                    continue
                artist_names_payload = [a.get("name", "") for a in track.get("artists", []) if a.get("name")]
                lower_payloads = {name.lower() for name in artist_names_payload if isinstance(name, str)}
                if lower_payloads and not (lower_payloads & lower_seed_names):
                    continue
                pair = self._norm_pair(track.get("name"), artist_names_payload[0] if artist_names_payload else "")
                if pair in seen_pairs:
                    continue
                existing_ids.add(track_id)
                seen_pairs.add(pair)
                supplements.append(track)
                if len(supplements) >= take:
                    return supplements
        return supplements

    def _apply_history_filter(
        self,
        ranked: List[dict],
        *,
        base_pool: List[dict],
        search_terms: List[str],
        user_key: str,
        limit: int,
    ) -> List[dict]:
        if not ranked:
            return []
        history = [track_id for track_id in self._user_track_history.get(user_key, []) if track_id]
        history_set = set(history)
        seen_ids: set[str] = set()
        filtered: List[dict] = []
        leftovers: List[dict] = []
        for track in ranked:
            track_id = track.get("id")
            if not track_id or track_id in seen_ids:
                continue
            seen_ids.add(track_id)
            if track_id in history_set:
                leftovers.append(track)
                continue
            filtered.append(track)
            if len(filtered) >= limit:
                break

        if len(filtered) < limit and search_terms:
            supplements = self._augment_from_search_terms(
                terms=search_terms,
                existing=base_pool + ranked,
                market=self._market,
                limit=max(limit * 2, 10),
            )
            for track in supplements:
                track_id = track.get("id")
                if not track_id or track_id in seen_ids or track_id in history_set:
                    continue
                seen_ids.add(track_id)
                filtered.append(track)
                if len(filtered) >= limit:
                    break

        if len(filtered) < limit:
            existing_ids = {item.get("id") for item in filtered}
            for track in leftovers:
                track_id = track.get("id")
                if not track_id or track_id in existing_ids:
                    continue
                filtered.append(track)
                existing_ids.add(track_id)
                if len(filtered) >= limit:
                    break

        return filtered[:limit]

    def _remember_tracks(self, user_key: str, track_ids: List[str]) -> None:
        if not track_ids:
            return
        history = self._user_track_history.setdefault(user_key, [])
        for track_id in track_ids:
            if track_id:
                history.append(track_id)
        if len(history) > self._history_max:
            del history[:-self._history_max]

    def _rank_tracks(
        self,
        tracks: List[dict],
        audio_features_map: Dict[str, Dict[str, float]],
        target_features: Dict[str, float],
        *,
        jitter_hint: Optional[Dict[str, float]],
        limit: int,
    ) -> List[dict]:
        if not tracks:
            return []
        scored: List[tuple[float, dict]] = []
        for index, track in enumerate(tracks):
            track_id = track.get("id")
            features = audio_features_map.get(track_id) or {}
            distance = self._feature_distance(features, target_features)
            if not target_features:
                distance = 1.0
            popularity_bonus = float(track.get("popularity") or 0) / 200.0
            jitter_score = self._jitter_score(track_id, target_features, jitter_hint)
            base = -distance + popularity_bonus + jitter_score
            # slight bias to original ordering to keep deterministic behaviour
            stability = -index * 1e-5
            scored.append((base + stability, track))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [track for _, track in scored[:limit]]

    def _jitter_score(
        self,
        track_id: Optional[str],
        target_features: Dict[str, float],
        jitter_hint: Optional[Dict[str, float]],
    ) -> float:
        if not track_id or not jitter_hint:
            return 0.0
        try:
            import hashlib
        except ImportError:
            return 0.0
        key_parts = [f"{name}:{value:.3f}" for name, value in sorted(target_features.items())]
        payload = f"{track_id}|{'|'.join(key_parts)}".encode("utf-8", "ignore")
        digest = hashlib.sha1(payload).digest()
        magnitude = sum(float(v) for v in jitter_hint.values() if isinstance(v, (int, float)))
        if magnitude == 0.0:
            return 0.0
        # Map digest to [-0.5, 0.5] and scale by jitter magnitude (keeping it tiny)
        span = int.from_bytes(digest[:8], "big") / (2**64 - 1) - 0.5
        return span * (magnitude / len(jitter_hint)) * 0.05

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
            genre.strip() for genre in genres or [] if isinstance(genre, str) and genre.strip()
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
