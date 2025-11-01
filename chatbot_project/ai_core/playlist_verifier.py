"""Gemini를 이용해 플레이리스트 후보를 검증하는 모듈."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence

import google.generativeai as genai

from .response_filter import parse_json_safely

logger = logging.getLogger(__name__)


_VERIFIER_SYSTEM_PROMPT = """
당신은 감정 기반 플레이리스트를 검증하는 한국인 음악 큐레이터입니다.
- mood_profile은 사용자가 원한 오디오 특징과 힌트를 담고 있습니다.
- candidates에는 Spotify 트랙 후보와 오디오 특징이 포함됩니다.
- selection_limit 개수만큼 곡을 골라야 하며, 분위기 일치도와 아티스트 다양성을 고려하세요.
- 출력은 항상 JSON 으로만 작성합니다. 설명이나 자연어 문장을 JSON 밖에 쓰지 않습니다.
- 반드시 아래 스키마를 지킵니다.
{
  "selected_tracks": [
    {"id": "spotify track id", "reason": "선택 사유 한 문장 (한국어)"}
  ],
  "notes": "최종 리스트 특징을 한두 문장으로 요약 (한국어)"
}
- selected_tracks 길이는 selection_limit 이하로 유지하세요.
""".strip()


@dataclass
class PlaylistVerifierResult:
    """재검증 결과."""

    track_ids: List[str]
    notes: Optional[str] = None
    raw_text: Optional[str] = None
    parsed: Optional[Dict[str, Any]] = None


class PlaylistVerifierProtocol(Protocol):
    """재검증기가 구현해야 하는 인터페이스."""

    def select_tracks(
        self,
        *,
        mood_profile: Dict[str, Any],
        candidates: Sequence[Dict[str, Any]],
        limit: int,
    ) -> PlaylistVerifierResult:
        """후보 중 최종 트랙을 골라 ``PlaylistVerifierResult`` 로 반환."""


class GeminiPlaylistVerifier:
    """Gemini LLM을 이용해 후보 곡을 평가하고 최종 선정을 돕는 클래스."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: Optional[str] = None,
        max_candidates: int = 25,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key must be provided for playlist verification.")

        genai.configure(api_key=api_key)
        resolved_model = (
            model_name
            or os.getenv("GEMINI_VERIFIER_MODEL")
            or os.getenv("GEMINI_MODEL")
            or "gemini-2.0-pro-exp"
        )
        self._model = genai.GenerativeModel(
            resolved_model,
            generation_config={
                "temperature": 0.45,
                "top_p": 0.9,
                "max_output_tokens": 1024,
            },
        )
        self._system_prompt = _VERIFIER_SYSTEM_PROMPT
        self._max_candidates = max(5, max_candidates)
        self._model_name = resolved_model

    def select_tracks(
        self,
        *,
        mood_profile: Dict[str, Any],
        candidates: Sequence[Dict[str, Any]],
        limit: int,
    ) -> PlaylistVerifierResult:
        if limit <= 0 or not candidates:
            return PlaylistVerifierResult(track_ids=[])

        trimmed = [
            self._simplify_candidate(candidate)
            for candidate in candidates[: self._max_candidates]
            if candidate.get("id")
        ]
        if not trimmed:
            return PlaylistVerifierResult(track_ids=[])

        selection_limit = max(1, min(limit, len(trimmed)))
        payload = {
            "mood_profile": mood_profile or {},
            "selection_limit": selection_limit,
            "candidates": trimmed,
        }

        user_prompt = (
            "아래 JSON 데이터는 추천 후보 목록입니다. mood_profile을 참고해 selection_limit 수만큼 엄선하고, "
            "항상 JSON 으로만 응답하세요.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

        try:
            prompt = f"{self._system_prompt}\n\n{user_prompt}"
            response = self._model.generate_content(prompt)
        except Exception as error:  # pragma: no cover - 네트워크 오류 대비
            logger.warning("Gemini playlist verifier call failed: %s", error)
            return PlaylistVerifierResult(track_ids=[])

        raw_text = self._extract_response_text(response)
        data = parse_json_safely(raw_text)
        track_ids: List[str] = []
        notes: Optional[str] = None

        if isinstance(data, dict):
            selected = data.get("selected_tracks")
            if isinstance(selected, list):
                for entry in selected:
                    if isinstance(entry, dict):
                        track_id = entry.get("id")
                        if isinstance(track_id, str) and track_id.strip():
                            track_ids.append(track_id.strip())
            if not track_ids:
                alt = data.get("selected_track_ids")
                if isinstance(alt, list):
                    for track_id in alt:
                        if isinstance(track_id, str) and track_id.strip():
                            track_ids.append(track_id.strip())
            note_field = data.get("notes") or data.get("summary")
            if isinstance(note_field, str) and note_field.strip():
                notes = note_field.strip()
        else:
            logger.debug("Gemini playlist verifier returned non JSON text: %s", raw_text[:200])

        if not track_ids:
            logger.warning("Gemini playlist verifier did not return track ids. Raw text: %s", raw_text[:200])

        return PlaylistVerifierResult(
            track_ids=track_ids[:selection_limit],
            notes=notes,
            raw_text=raw_text,
            parsed=data if isinstance(data, dict) else None,
        )

    def _simplify_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        artists: List[str] = []
        raw_artists = candidate.get("artists") or []
        for artist in raw_artists:
            if isinstance(artist, str):
                if artist.strip():
                    artists.append(artist.strip())
            elif isinstance(artist, dict):
                name = artist.get("name")
                if isinstance(name, str) and name.strip():
                    artists.append(name.strip())

        features = candidate.get("features") or candidate.get("audio_features") or {}
        simplified_features: Dict[str, float] = {}
        for key in ("acousticness", "danceability", "energy", "instrumentalness", "valence"):
            value = features.get(key)
            if isinstance(value, (int, float)):
                simplified_features[key] = round(float(value), 3)
        for key in ("tempo", "loudness"):
            value = features.get(key)
            if isinstance(value, (int, float)):
                simplified_features[key] = round(float(value), 1)

        payload: Dict[str, Any] = {
            "id": candidate.get("id"),
            "name": candidate.get("name"),
            "artists": artists,
            "popularity": candidate.get("popularity"),
            "distance_to_target": candidate.get("distance_to_target"),
            "features": simplified_features,
        }

        summary = candidate.get("summary") or candidate.get("summary_hint")
        if isinstance(summary, str) and summary.strip():
            payload["summary"] = summary.strip()

        return {key: value for key, value in payload.items() if value not in (None, [], {})}

    def _extract_response_text(self, response: Any) -> str:
        """Gemini SDK 응답에서 텍스트를 최대한 안전하게 추출."""

        if response is None:
            return ""

        # 최신 SDK에서는 ``response.text`` 가 단순 텍스트일 때만 동작하며,
        # 복합 파트 응답일 경우 ``ValueError`` 를 발생시킨다. 이런 경우를 방어하기 위해
        # 접근 자체를 ``try`` 블록으로 감싼다.
        text_value = None
        try:
            text_value = getattr(response, "text")
        except (AttributeError, ValueError, TypeError):
            text_value = None
        if isinstance(text_value, str) and text_value.strip():
            return text_value

        candidates = getattr(response, "candidates", None) or []
        collected_parts: List[str] = []

        for candidate in candidates:
            # ``candidate.content.parts`` 또는 ``candidate.parts`` 에 텍스트 파트가 존재할 수 있다.
            content = getattr(candidate, "content", None)
            parts = None
            if content is not None:
                parts = getattr(content, "parts", None)
            if not parts:
                parts = getattr(candidate, "parts", None)

            if not parts:
                continue

            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    collected_parts.append(part_text.strip())

        if collected_parts:
            return "\n".join(collected_parts)

        try:
            return str(response)
        except Exception:  # pragma: no cover - 예외적 객체 표현 방어
            return ""
