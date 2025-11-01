"""Thin Spotify API client tailored for the CLI playlist workflow."""

from __future__ import annotations

import time
from dataclasses import dataclass
import os
from typing import Any, Dict, Iterable, List, Optional

import requests

from .config import Settings
from .gemini_playlist import PlaylistPlan, SearchQuery, TrackRequest

AUTH_URL = "https://accounts.spotify.com/api/token"
BASE_URL = "https://api.spotify.com/v1"


class SpotifyAuthError(RuntimeError):
    """Raised when obtaining or refreshing the Spotify token fails."""


class SpotifyServiceError(RuntimeError):
    """Raised when Spotify returns an unexpected response."""


@dataclass
class ResolvedTrack:
    """Spotify track enriched with any Gemini context."""

    id: str
    name: str
    artists: List[str]
    url: Optional[str]
    album_image: Optional[str]
    popularity: Optional[int]
    duration_ms: Optional[int]
    rationale: Optional[str]
    source: str
    audio_features: Dict[str, Any]


class SpotifyService:
    """Handles Spotify search + enrichment with lightweight caching."""

    def __init__(self, settings: Settings, *, limit: int) -> None:
        self.client_id = settings.spotify_client_id
        self.client_secret = settings.spotify_client_secret
        self.market = settings.spotify_market
        self.limit = limit
        self._refresh_token = settings.spotify_refresh_token
        self._redirect_uri = settings.spotify_redirect_uri

        self._session = requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._token_source: str = "user" if self._refresh_token else "client"
        self._debug: bool = os.getenv("SPOTIFY_DEBUG", "0") not in {"", "0", "false", "False"}

    # ------------------------
    # Public workflow methods
    # ------------------------

    def collect_tracks(self, plan: PlaylistPlan) -> List[ResolvedTrack]:
        """Resolve Gemini's plan into fully enriched Spotify tracks."""

        resolved: List[ResolvedTrack] = []
        seen_ids: set[str] = set()

        # Step 1: obey explicit track picks from Gemini.
        for request in plan.track_requests:
            track = self._resolve_track_request(request)
            if not track or track["id"] in seen_ids:
                continue
            enriched = self._enrich_track(track, request=request, source="gemini")
            resolved.append(enriched)
            seen_ids.add(track["id"])
            if len(resolved) >= self.limit:
                return resolved

        # Step 2: fall back to broader queries to fill the quota.
        for query in plan.fallback_queries:
            for track in self._search_by_query(query):
                if track["id"] in seen_ids:
                    continue
                enriched = self._enrich_track(track, query=query, source="fallback")
                resolved.append(enriched)
                seen_ids.add(track["id"])
                if len(resolved) >= self.limit:
                    return resolved

        return resolved

    # ------------------------
    # Authentication helpers
    # ------------------------

    def _ensure_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token

        if self._token_source == "user":
            return self._refresh_user_token()

        return self._refresh_client_token()

    def _refresh_client_token(self) -> str:
        response = self._post_token_request(
            data={"grant_type": "client_credentials"},
            error_context="client credentials",
        )

        return self._store_token_from_response(response, source="client")

    def _refresh_user_token(self) -> str:
        if not self._refresh_token:
            raise SpotifyAuthError(
                "Spotify user token requested but SPOTIFY_REFRESH_TOKEN is not configured."
            )

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        response = self._post_token_request(
            data=data,
            error_context="refresh token",
        )

        return self._store_token_from_response(response, source="user")

    def _post_token_request(self, *, data: Dict[str, Any], error_context: str) -> requests.Response:
        try:
            response = self._session.post(
                AUTH_URL,
                data=data,
                auth=(self.client_id, self.client_secret),
                timeout=10,
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure path
            raise SpotifyAuthError(
                f"Failed to contact Spotify auth endpoint ({error_context}): {exc}"
            ) from exc

        if response.status_code != 200:
            raise SpotifyAuthError(
                f"Spotify token request failed for {error_context} ({response.status_code}): {response.text}"
            )
        return response

    def _store_token_from_response(self, response: requests.Response, *, source: str) -> str:
        now = time.time()
        token_data = response.json()
        access_token = token_data.get("access_token")
        expires_in = int(token_data.get("expires_in", 0))

        if not access_token:
            raise SpotifyAuthError(
                f"Spotify token response ({source}) did not include access_token."
            )

        self._token = access_token
        self._token_expiry = now + max(expires_in - 30, 30)
        self._token_source = source
        return access_token

    # ------------------------
    # Spotify search & enrichment
    # ------------------------

    def _resolve_track_request(self, request: TrackRequest) -> Optional[Dict[str, Any]]:
        search_templates = self._build_search_templates(request)
        for query in search_templates:
            track = self._search_one(query)
            if track:
                return track
        return None

    def _build_search_templates(self, request: TrackRequest) -> Iterable[str]:
        title = request.title
        artist = request.artist
        hint = request.search_hint

        queries = []
        if artist:
            queries.append(f'track:"{title}" artist:"{artist}"')
        queries.append(f'track:"{title}"')
        if artist and hint:
            queries.append(f'track:"{title}" artist:"{artist}" {hint}')
        if hint:
            queries.append(f"{title} {hint}")
        if artist:
            queries.append(f"{title} {artist}")
        queries.append(title)
        return queries

    def _search_one(self, query: str) -> Optional[Dict[str, Any]]:
        params = {
            "q": query,
            "type": "track",
            "limit": 5,
        }
        # Prefer from_token so Spotify derives market from the user.
        if self._token_source == "user":
            params["market"] = "from_token"
        payload = self._get(f"{BASE_URL}/search", params=params)

        tracks = (payload.get("tracks") or {}).get("items") or []
        for track in tracks:
            if self._is_track_playable(track):
                return track
        return None

    def _search_by_query(self, query: SearchQuery) -> Iterable[Dict[str, Any]]:
        params = {
            "q": query.query,
            "type": "track",
            "limit": max(self.limit, 5),
        }
        if self._token_source == "user":
            params["market"] = "from_token"
        payload = self._get(f"{BASE_URL}/search", params=params)
        tracks = (payload.get("tracks") or {}).get("items") or []
        for track in tracks:
            if self._is_track_playable(track):
                yield track

    def _enrich_track(
        self,
        track: Dict[str, Any],
        *,
        request: Optional[TrackRequest] = None,
        query: Optional[SearchQuery] = None,
        source: str,
    ) -> ResolvedTrack:
        features = self._get_audio_features(track["id"])
        return ResolvedTrack(
            id=track["id"],
            name=track.get("name"),
            artists=[artist.get("name") for artist in track.get("artists", []) if artist.get("name")],
            url=(track.get("external_urls") or {}).get("spotify"),
            album_image=self._extract_album_image(track),
            popularity=track.get("popularity"),
            duration_ms=track.get("duration_ms"),
            rationale=(request.rationale if request else query.reason if query else None),
            source=source,
            audio_features=features or {},
        )

    def _extract_album_image(self, track_payload: Dict[str, Any]) -> Optional[str]:
        album = track_payload.get("album") or {}
        images = album.get("images") or []
        if not images:
            return None
        # Images are ordered largest -> smallest; pick middle for a good balance.
        if len(images) >= 2:
            return images[1].get("url") or images[0].get("url")
        return images[0].get("url")

    def _is_track_playable(self, track_payload: Dict[str, Any]) -> bool:
        markets = track_payload.get("available_markets")
        if isinstance(markets, list) and markets:
            return self.market in markets
        # Some search payloads omit markets; assume playable if not explicitly blocked.
        return True

    # ------------------------
    # Raw Spotify HTTP helpers
    # ------------------------

    def _get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        allow_elevation: bool = True,
    ) -> Dict[str, Any]:
        params = dict(params or {})
        if self._debug:
            print(f"[Spotify] GET {url} params={params} token={self._token_source}")

        response = self._request_with_refresh(url, params=params, allow_elevation=allow_elevation)

        if response.status_code == 403 and "market" in params:
            # 2025 Spotify search docs note some catalog methods reject the market
            # filter when using client-credentials tokens. Re-run without it so we
            # still get globally available tracks instead of failing outright.
            stripped_params = {key: value for key, value in params.items() if key != "market"}
            response = self._request_with_refresh(
                url,
                params=stripped_params,
                allow_elevation=allow_elevation,
            )

        if response.status_code >= 400:
            raise SpotifyServiceError(
                f"Spotify API error {response.status_code}: {response.text}"
            )

        return response.json()

    def _request_with_refresh(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        allow_elevation: bool = True,
    ) -> requests.Response:
        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = self._session.get(url, headers=headers, params=params, timeout=10)
        except requests.RequestException as exc:  # pragma: no cover
            raise SpotifyServiceError(f"Spotify request failed: {exc}") from exc

        if response.status_code == 401:
            self._token = None
            token = self._ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            try:
                response = self._session.get(url, headers=headers, params=params, timeout=10)
            except requests.RequestException as exc:  # pragma: no cover
                raise SpotifyServiceError(f"Spotify request failed: {exc}") from exc

        if (
            response.status_code == 403
            and allow_elevation
            and self._refresh_token
            and self._token_source != "user"
        ):
            # Some catalog endpoints now require a user-scoped token.
            self._token = None
            self._token_source = "user"
            token = self._ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            if self._debug:
                print("[Spotify] Elevating to user token and retrying")
            try:
                response = self._session.get(url, headers=headers, params=params, timeout=10)
            except requests.RequestException as exc:  # pragma: no cover
                raise SpotifyServiceError(f"Spotify request failed: {exc}") from exc

        return response

    def _get_audio_features(self, track_id: str) -> Optional[Dict[str, Any]]:
        try:
            payload = self._get(
                f"{BASE_URL}/audio-features/{track_id}",
                allow_elevation=False,
            )
        except SpotifyServiceError as exc:
            message = str(exc)
            if "Spotify API error 403" in message:
                if self._debug:
                    print(f"[Spotify] audio-features forbidden for {track_id}, skipping")
                return {}
            raise
        if not payload or payload.get("id") != track_id:
            return None
        return {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "type",
                "uri",
                "track_href",
                "analysis_url",
                "id",
            }
        }
