
# ai_core/spotify_client.py
from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Tuple, Set, Any

import requests


class SpotifyAuthError(Exception):
    pass


class SpotifyClient:
    """
    Safe Spotify client with:
    - Robust Settings/env loading (accepts a Settings object or explicit args)
    - Client Credentials token management
    - Avoids deprecated endpoints when blocked for new apps
    - Fallback: Search + Artist Top Tracks instead of /recommendations
    """

    API_BASE_URL = "https://api.spotify.com/v1"
    TOKEN_URL = "https://accounts.spotify.com/api/token"

    # Conservative default seeds for dance/house use-cases
    DEFAULT_SEED_GENRES: Set[str] = {
        "house", "deep-house", "dance", "edm", "electro", "disco", "club",
        "progressive-house", "techno", "trance",
        "pop", "k-pop", "hip-hop", "r-n-b", "funk", "latin"
    }

    # Allowed ranges for some target_* features to avoid 400s
    _FEATURE_LIMITS = {
        "acousticness": (0.0, 1.0),
        "danceability": (0.0, 1.0),
        "energy": (0.0, 1.0),
        "instrumentalness": (0.0, 1.0),
        "liveness": (0.0, 1.0),
        "speechiness": (0.0, 1.0),
        "valence": (0.0, 1.0),
        "popularity": (0, 100),
        "tempo": (30.0, 250.0),
        "loudness": (-60.0, 0.0),
        "key": (0, 11),
        "mode": (0, 1),
        "time_signature": (3, 7),
    }

    def __init__(
        self,
        settings: Optional[Any] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        market: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        """
        Initialize with Settings object, explicit args, or environment variables.
        Recognized Settings names: spotify_client_id/secret/market (case-insensitive variants also work).
        """
        def _pull(obj: Any, *names: str) -> Optional[str]:
            for name in names:
                if hasattr(obj, name):
                    v = getattr(obj, name)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                if isinstance(obj, dict) and name in obj:
                    v = obj.get(name)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
            return None

        # explicit
        cid = client_id.strip() if isinstance(client_id, str) and client_id.strip() else None
        csec = client_secret.strip() if isinstance(client_secret, str) and client_secret.strip() else None
        mkt = market.strip() if isinstance(market, str) and market.strip() else None

        # settings
        user_refresh_token: Optional[str] = None
        default_seed_genres: Optional[Tuple[str, ...]] = None
        redirect_uri: Optional[str] = None
        if settings is not None:
            cid = cid or _pull(settings, "spotify_client_id", "SPOTIFY_CLIENT_ID", "client_id")
            csec = csec or _pull(settings, "spotify_client_secret", "SPOTIFY_CLIENT_SECRET", "client_secret")
            mkt = mkt or _pull(settings, "spotify_market", "SPOTIFY_MARKET", "market")
            user_refresh_token = user_refresh_token or _pull(
                settings,
                "spotify_refresh_token",
                "SPOTIFY_REFRESH_TOKEN",
                "refresh_token",
            )
            redirect_uri = redirect_uri or _pull(
                settings,
                "spotify_redirect_uri",
                "SPOTIFY_REDIRECT_URI",
                "redirect_uri",
            )
            default_seed_genres = getattr(settings, "spotify_default_seed_genres", None)

        # env
        cid = cid or os.getenv("SPOTIFY_CLIENT_ID")
        csec = csec or os.getenv("SPOTIFY_CLIENT_SECRET")
        mkt = mkt or os.getenv("SPOTIFY_MARKET") or "KR"
        user_refresh_token = user_refresh_token or os.getenv("SPOTIFY_REFRESH_TOKEN")
        redirect_uri = redirect_uri or os.getenv("SPOTIFY_REDIRECT_URI")

        if not cid or not csec:
            raise SpotifyAuthError("SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET 누락")

        self.client_id: str = cid
        self.client_secret: str = csec
        self.market: str = mkt
        self._session = session or requests.Session()

        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

        self._token_source: str = "client"
        self._user_refresh_token: Optional[str] = user_refresh_token if user_refresh_token else None
        self._redirect_uri: Optional[str] = redirect_uri if redirect_uri else None
        if self._user_refresh_token:
            self._token_source = "user"

        self._cached_genre_seeds: Set[str] = set()
        provided_default_genres = [
            g.strip().lower()
            for g in (default_seed_genres or tuple())
            if isinstance(g, str) and g.strip()
        ]
        if provided_default_genres:
            self._default_seed_genres: Set[str] = set(provided_default_genres)
        else:
            self._default_seed_genres = set(self.DEFAULT_SEED_GENRES)

        self._obtain_access_token()

    # ---------- Auth ----------

    def _obtain_access_token(self) -> None:
        if self._token_source == "user" and self._user_refresh_token:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self._user_refresh_token,
            }
            if self._redirect_uri:
                data["redirect_uri"] = self._redirect_uri
        else:
            data = {"grant_type": "client_credentials"}
            self._token_source = "client"

        resp = self._session.post(
            self.TOKEN_URL,
            data=data,
            auth=(self.client_id, self.client_secret),
            timeout=15,
        )
        if not resp.ok:
            hint = ""
            try:
                j = resp.json()
                if j.get("error") == "invalid_client":
                    hint = " (invalid_client: Client ID/Secret 재확인/재발급 필요)"
                if j.get("error") == "invalid_grant" and self._token_source == "user":
                    hint = " (invalid_grant: refresh token 만료, 클라이언트 크레덴셜로 전환함)"
            except Exception:
                pass
            if self._token_source == "user":
                self._token_source = "client"
                self._user_refresh_token = None
                self._obtain_access_token()
                return
            raise SpotifyAuthError(f"토큰 발급 실패: {resp.status_code} {resp.text}{hint}")
        payload = resp.json()
        self._access_token = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 3600)) - 60
        if payload.get("refresh_token"):
            self._user_refresh_token = payload.get("refresh_token")
            self._token_source = "user"

    def _refresh_access_token(self) -> None:
        if self._access_token is None or time.time() >= self._token_expiry:
            self._obtain_access_token()

    def _auth_header(self) -> Dict[str, str]:
        self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    # ---------- User token helpers ----------

    def apply_user_token(
        self,
        *,
        access_token: str,
        expires_in: int,
        refresh_token: Optional[str] = None,
    ) -> None:
        """외부 OAuth 연동 결과를 적용하면 됨."""

        if not access_token:
            raise SpotifyAuthError("유효한 사용자 액세스 토큰이 필요함")

        self._access_token = access_token
        self._token_expiry = time.time() + max(int(expires_in or 0), 60) - 60
        if refresh_token:
            self._user_refresh_token = refresh_token
        if self._user_refresh_token:
            self._token_source = "user"
        else:
            self._token_source = "client"

    def clear_user_token(self) -> None:
        """사용자 토큰 없이 클라이언트 크레덴셜로 전환하면 됨."""

        self._token_source = "client"
        self._user_refresh_token = None
        self._access_token = None
        self._token_expiry = 0.0

    # ---------- Genres ----------

    def _get_available_genre_seeds(self) -> Set[str]:
        """
        Try deprecated endpoint; if blocked/404/403, fall back to default list.
        """
        if self._cached_genre_seeds:
            return self._cached_genre_seeds

        url = f"{self.API_BASE_URL}/recommendations/available-genre-seeds"
        try:
            r = self._session.get(url, headers=self._auth_header(), timeout=15)
            if r.status_code == 401:
                self._refresh_access_token()
                r = self._session.get(url, headers=self._auth_header(), timeout=15)

            if r.status_code in (403, 404):
                genres = set(self._default_seed_genres)
            else:
                r.raise_for_status()
                genres = set((r.json() or {}).get("genres") or []) or set(self._default_seed_genres)
        except requests.RequestException:
            genres = set(self._default_seed_genres)

        self._cached_genre_seeds = genres
        return genres

    def _select_seed_genres(self, seed_genres: Optional[List[str]]) -> List[str]:
        if not seed_genres:
            return []
        avail = self._get_available_genre_seeds()
        filtered = [g for g in seed_genres if isinstance(g, str) and g.lower() in avail]
        return filtered[:5]

    # ---------- Fallback helpers ----------

    def _seed_artists_from_genres(
        self,
        genres: Optional[List[str]],
        *,
        limit: int = 5,
        market: Optional[str] = None,
    ) -> List[str]:
        if not genres:
            genres = list(self._default_seed_genres)

        artist_ids: List[str] = []
        for g in genres:
            g = (g or "").strip()
            if not g:
                continue
            q = f'genre:"{g}"'
            params = {"q": q, "type": "artist", "limit": 50}
            params["market"] = market or self.market

            r = self._session.get(
                f"{self.API_BASE_URL}/search",
                headers=self._auth_header(),
                params=params,
                timeout=10,
            )
            if r.status_code == 401:
                self._refresh_access_token()
                r = self._session.get(
                    f"{self.API_BASE_URL}/search",
                    headers=self._auth_header(),
                    params=params,
                    timeout=10,
                )
            if r.ok:
                items = (r.json().get("artists") or {}).get("items") or []
                for a in items:
                    aid = a.get("id")
                    if aid and aid not in artist_ids:
                        artist_ids.append(aid)
                        if len(artist_ids) >= limit:
                            break
            if len(artist_ids) >= limit:
                break
        return artist_ids[:limit]

    def _artist_top_tracks(self, artist_id: str, *, market: Optional[str] = None) -> List[dict]:
        params = {"market": market or self.market}
        r = self._session.get(
            f"{self.API_BASE_URL}/artists/{artist_id}/top-tracks",
            headers=self._auth_header(),
            params=params,
            timeout=10,
        )
        if r.status_code == 401:
            self._refresh_access_token()
            r = self._session.get(
                f"{self.API_BASE_URL}/artists/{artist_id}/top-tracks",
                headers=self._auth_header(),
                params=params,
                timeout=10,
            )
        if not r.ok:
            return []
        data = r.json() or {}
        tracks = data.get("tracks") or []
        return tracks

    def _manual_recommendations(
        self,
        *,
        seed_genres: Optional[List[str]],
        seed_artists: Optional[List[str]],
        seed_tracks: Optional[List[str]],
        limit: int,
        market: Optional[str],
    ) -> Dict:
        """
        Fallback recommender:
        - Prefer explicit seed_artists -> top-tracks
        - Else, derive artists from genres and use their top-tracks
        - Else, search tracks with the first genre keyword
        """
        market = market or self.market
        out_tracks: List[dict] = []
        seen: Set[str] = set()

        artists = list(seed_artists or [])
        if not artists:
            artists = self._seed_artists_from_genres(seed_genres, limit=5, market=market)

        for aid in artists:
            for t in self._artist_top_tracks(aid, market=market):
                tid = t.get("id")
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                out_tracks.append(t)
                if len(out_tracks) >= limit:
                    break
            if len(out_tracks) >= limit:
                break

        # Last resort: search tracks by genre keyword
        if len(out_tracks) < limit and seed_genres:
            q = f'genre:"{seed_genres[0]}"'
            params = {"q": q, "type": "track", "limit": max(10, limit), "market": market}
            r = self._session.get(f"{self.API_BASE_URL}/search", headers=self._auth_header(), params=params, timeout=10)
            if r.ok:
                items = (r.json().get("tracks") or {}).get("items") or []
                for t in items:
                    tid = t.get("id")
                    if tid and tid not in seen:
                        seen.add(tid)
                        out_tracks.append(t)
                        if len(out_tracks) >= limit:
                            break

        return {"tracks": out_tracks[:limit]}

    # ---------- Features ----------

    def _prepare_target_features(self, target_features: Dict[str, float]) -> Tuple[Dict[str, str], Dict[str, float]]:
        applied: Dict[str, float] = {}
        params: Dict[str, str] = {}
        if not target_features:
            return params, applied

        def _clamp(name: str, val: float) -> float:
            lo, hi = self._FEATURE_LIMITS.get(name, (-1e9, 1e9))
            return max(lo, min(hi, val))

        for k, v in target_features.items():
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            fv = _clamp(k, fv)
            params[f"target_{k}"] = str(fv)
            applied[k] = fv
        return params, applied

    # ---------- Recommendations (with fallback) ----------

    def get_recommendations(
        self,
        *,
        target_features: Dict[str, float],
        seed_genres: Optional[List[str]] = None,
        seed_tracks: Optional[List[str]] = None,
        seed_artists: Optional[List[str]] = None,
        limit: int = 5,
        market: Optional[str] = None,
    ) -> Tuple[Dict, Dict[str, float], List[str]]:
        # First, try legacy /recommendations once (some old apps still have access)
        params: Dict[str, str] = {"limit": str(max(1, min(limit, 100)))}  # <=100
        params["market"] = market or self.market

        # seed handling
        seeds_g = self._select_seed_genres(seed_genres)
        seeds_t = (seed_tracks or [])[:5]
        seeds_a = (seed_artists or [])[:5]

        merged = []
        for bucket in (seeds_t, seeds_a, seeds_g):
            for s in bucket:
                if len(merged) < 5:
                    merged.append(("t" if bucket is seeds_t else "a" if bucket is seeds_a else "g", s))

        final_tracks = [s for tag, s in merged if tag == "t"]
        final_artists = [s for tag, s in merged if tag == "a"]
        final_genres = [s for tag, s in merged if tag == "g"]

        if final_genres:
            params["seed_genres"] = ",".join(final_genres)
        if final_tracks:
            params["seed_tracks"] = ",".join(final_tracks)
        if final_artists:
            params["seed_artists"] = ",".join(final_artists)

        feat_params, applied_features = self._prepare_target_features(target_features)
        params.update(feat_params)

        # Try deprecated endpoint (may work on old apps)
        url = f"{self.API_BASE_URL}/recommendations"
        try:
            r = self._session.get(url, headers=self._auth_header(), params=params, timeout=20)
            if r.status_code == 401:
                self._refresh_access_token()
                r = self._session.get(url, headers=self._auth_header(), params=params, timeout=20)

            if r.status_code in {400, 403, 404}:
                # Fallback to manual recommender
                manual = self._manual_recommendations(
                    seed_genres=final_genres or seed_genres,
                    seed_artists=final_artists or seed_artists,
                    seed_tracks=final_tracks or seed_tracks,
                    limit=limit,
                    market=market,
                )
                return manual, applied_features, final_genres
            r.raise_for_status()
            return r.json(), applied_features, final_genres
        except requests.RequestException:
            manual = self._manual_recommendations(
                seed_genres=final_genres or seed_genres,
                seed_artists=final_artists or seed_artists,
                seed_tracks=final_tracks or seed_tracks,
                limit=limit,
                market=market,
            )
            return manual, applied_features, final_genres

    # ---------- Audio features ----------

    def get_audio_features(self, track_ids: List[str]) -> Dict[str, Dict[str, float]]:
        if not track_ids:
            return {}

        features_map: Dict[str, Dict[str, float]] = {}
        chunk_size = 100
        for start in range(0, len(track_ids), chunk_size):
            chunk = track_ids[start : start + chunk_size]
            if not chunk:
                continue
            params = {"ids": ",".join(chunk)}
            try:
                response = self._session.get(
                    f"{self.API_BASE_URL}/audio-features",
                    headers=self._auth_header(),
                    params=params,
                    timeout=10,
                )
                if response.status_code == 401:
                    self._refresh_access_token()
                    response = self._session.get(
                        f"{self.API_BASE_URL}/audio-features",
                        headers=self._auth_header(),
                        params=params,
                        timeout=10,
                    )
                if not response.ok:
                    continue
                payload = response.json() or {}
                for feature_payload in payload.get("audio_features", []) or []:
                    track_id = feature_payload.get("id")
                    if not track_id:
                        continue
                    normalized = {
                        key: feature_payload.get(key)
                        for key in (
                            "acousticness",
                            "danceability",
                            "energy",
                            "instrumentalness",
                            "liveness",
                            "speechiness",
                            "valence",
                            "tempo",
                            "loudness",
                        )
                    }
                    features_map[track_id] = {
                        name: float(value)
                        for name, value in normalized.items()
                        if isinstance(value, (int, float))
                    }
            except requests.RequestException:
                continue

        return features_map
