"""Gemini-powered mood-to-playlist planner for the CLI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import google.generativeai as genai

JSON_FALLBACK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


class GeminiPlannerError(RuntimeError):
    """Raised when Gemini cannot produce a usable plan."""


@dataclass(frozen=True)
class TrackRequest:
    """Desired track coming from Gemini."""

    title: str
    artist: Optional[str] = None
    rationale: Optional[str] = None
    search_hint: Optional[str] = None


@dataclass(frozen=True)
class SearchQuery:
    """Fallback search query for Spotify when explicit tracks are missing."""

    query: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class PlaylistPlan:
    """Structured response describing what the CLI should build."""

    ready: bool
    playlist_title: str
    mood_summary: str
    notes_for_backend: str
    followup_question: Optional[str]
    track_requests: List[TrackRequest]
    fallback_queries: List[SearchQuery]
    reasoning: Optional[str]
    raw_response: str

    @property
    def needs_more_input(self) -> bool:
        return not self.ready and bool(self.followup_question)


class GeminiPlaylistPlanner:
    """Keeps a running conversation with Gemini and returns playlist intents."""

    def __init__(self, *, api_key: str, model_name: str, limit: int = 5) -> None:
        if limit <= 0:
            raise ValueError("Playlist limit must be positive.")

        self.limit = limit
        self._model = self._build_model(api_key, model_name, limit)
        self._chat = self._model.start_chat(history=[])

    def plan(self, user_message: str) -> PlaylistPlan:
        """Send the user's input to Gemini and parse the response."""

        if not user_message:
            raise ValueError("User message must not be empty.")

        try:
            response = self._chat.send_message(user_message)
        except Exception as exc:  # pragma: no cover - surface helpful context
            raise GeminiPlannerError(f"Gemini call failed: {exc}") from exc

        text = (response.text or "").strip()
        if not text:
            raise GeminiPlannerError("Gemini returned an empty response.")

        payload = self._coerce_json(text)
        return self._parse_payload(payload, raw_response=text)

    @staticmethod
    def _build_model(api_key: str, model_name: str, limit: int):
        genai.configure(api_key=api_key)

        system_instruction = (
            "You are a collaborative Spotify DJ living inside a CLI. "
            "Always reply with a single JSON object (no markdown fences) using this schema:\n"
            "{\n"
            '  \"status\": \"ready\" | \"need_more_info\",\n'
            '  \"playlist_title\": string,\n'
            '  \"mood_summary\": string,\n'
            '  \"notes_for_backend\": string,\n'
            '  \"followup_question\": string | null,\n'
            '  \"reasoning\": string,\n'
            '  \"track_requests\": [\n'
            "    {\n"
            '      \"title\": string,\n'
            '      \"artist\": string | null,\n'
            '      \"rationale\": string,\n'
            '      \"search_hint\": string | null\n'
            "    }\n"
            "  ],\n"
            '  \"fallback_queries\": [\n'
            "    {\n"
            '      \"query\": string,\n'
            '      \"reason\": string | null\n'
            "    }\n"
            "  ]\n"
            "}\n"
            f"Return at most {limit} track_requests. If you have fewer solid matches, "
            "keep the list short and rely on fallback_queries to cover the gap. "
            "Every response must be valid JSON. "
            "All natural-language strings must be written in Korean."
        )

        return genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
        )

    @staticmethod
    def _coerce_json(raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = JSON_FALLBACK_PATTERN.search(raw)
            if not match:
                raise GeminiPlannerError("Gemini response was not valid JSON.")
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:  # pragma: no cover
                raise GeminiPlannerError("Gemini response did not contain parseable JSON.") from exc

    def _parse_payload(self, payload: Dict[str, Any], *, raw_response: str) -> PlaylistPlan:
        status = str(payload.get("status", "ready")).lower()
        ready = status == "ready"

        track_requests = self._parse_track_requests(payload.get("track_requests") or [])
        fallback_queries = self._parse_queries(payload.get("fallback_queries") or [])

        playlist_title = self._clean_str(payload.get("playlist_title"), default="Gemini Vibes")
        mood_summary = self._clean_str(payload.get("mood_summary"), default="")
        notes_for_backend = self._clean_str(payload.get("notes_for_backend"), default="")
        reasoning = self._clean_str(payload.get("reasoning"), default="")
        followup_question = self._clean_optional(payload.get("followup_question"))

        return PlaylistPlan(
            ready=ready,
            playlist_title=playlist_title,
            mood_summary=mood_summary,
            notes_for_backend=notes_for_backend,
            followup_question=followup_question,
            track_requests=track_requests,
            fallback_queries=fallback_queries,
            reasoning=reasoning,
            raw_response=raw_response,
        )

    def _parse_track_requests(self, items: Iterable[Any]) -> List[TrackRequest]:
        parsed: List[TrackRequest] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = self._clean_optional(item.get("title"))
            if not title:
                continue
            artist = self._clean_optional(item.get("artist"))
            rationale = self._clean_optional(item.get("rationale"))
            search_hint = self._clean_optional(item.get("search_hint"))
            parsed.append(
                TrackRequest(
                    title=title,
                    artist=artist,
                    rationale=rationale,
                    search_hint=search_hint,
                )
            )
            if len(parsed) >= self.limit:
                break
        return parsed

    def _parse_queries(self, items: Iterable[Any]) -> List[SearchQuery]:
        parsed: List[SearchQuery] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            query = self._clean_optional(item.get("query"))
            if not query:
                continue
            reason = self._clean_optional(item.get("reason"))
            parsed.append(SearchQuery(query=query, reason=reason))
        return parsed

    @staticmethod
    def _clean_str(value: Any, *, default: str) -> str:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else default
        return default

    @staticmethod
    def _clean_optional(value: Any) -> Optional[str]:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None
