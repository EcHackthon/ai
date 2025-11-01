
"""StrictGeminiMusicChat: 시스템 프롬프트 준수+JSON 강제화 래퍼."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from .prompts import SYSTEM_PROMPT
from .response_filter import parse_json_safely, sanitize_to_json_only

class GeminiResponse:
    def __init__(
        self,
        text: str,
        *,
        response_type: str = "conversation",
        target_features: Optional[Dict[str, Any]] = None,
        genres: Optional[List[str]] = None,
        seed_artists: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.text = text
        self.message = text  # backward compatibility with legacy callers
        self.type = response_type
        self.meta = meta or {}
        self.target_features = target_features
        self.genres = genres or []
        self.seed_artists = seed_artists or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "meta": self.meta,
            "target_features": self.target_features,
            "genres": self.genres,
            "seed_artists": self.seed_artists,
        }

class StrictGeminiMusicChat:
    """기존 GeminiMusicChat과 동일 인터페이스 최소 구현.
    - send_message(text) -> GeminiResponse
    - get_target_features() -> Optional[Dict[str, Any]]
    - reset()
    """
    def __init__(
        self,
        settings: Optional[Any] = None,
        *,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """Allow initialization via Settings object or direct credentials."""

        if settings is not None:
            api_key = api_key or getattr(settings, "gemini_api_key", None)
            model_name = model_name or getattr(settings, "gemini_model", None)

        api_key = api_key or os.getenv("GEMINI_API_KEY")
        model_name = model_name or os.getenv("GEMINI_MODEL") or "gemini-1.5-pro"
        if not api_key:
            raise RuntimeError("Gemini API key missing. Set settings.gemini_api_key or GEMINI_API_KEY.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name,
            system_instruction=SYSTEM_PROMPT,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.9,
                "max_output_tokens": 2048,
            },
        )
        self.history: List[Dict[str, str]] = []
        self.analysis_ready: bool = False
        self._target_features: Optional[Dict[str, float]] = None
        self._inferred_genres: Optional[List[str]] = None
        self._seed_artists: Optional[List[str]] = None
        self._diversity_hint: Optional[Dict[str, Any]] = None
        self._per_track_jitter_hint: Optional[Dict[str, Any]] = None

    def reset(self) -> None:
        self.history.clear()
        self.analysis_ready = False
        self._target_features = None
        self._inferred_genres = None
        self._seed_artists = None
        self._diversity_hint = None
        self._per_track_jitter_hint = None

    def _gen(self, text: str) -> str:
        parts = []
        if self.history:
            for turn in self.history[-8:]:
                parts.append({"role": "user", "parts": [turn["user"]]})
                parts.append({"role": "model", "parts": [turn["assistant"]]})
        parts.append({"role": "user", "parts": [text]})
        resp = self.model.generate_content(parts)
        return getattr(resp, "text", "") or ""

    def send_message(self, text: str) -> GeminiResponse:
        raw = self._gen(text) or ""
        raw_stripped = raw.strip()
        if not raw_stripped:
            assistant_show = "Gemini response was empty. Please try again."
            self.history.append({"user": text, "assistant": assistant_show})
            return GeminiResponse(
                assistant_show,
                response_type="error",
                target_features=self._target_features,
                genres=self._inferred_genres,
                seed_artists=self._seed_artists,
            )

        # 모델 출력 텍스트에서 JSON을 우선 추출
        json_only = sanitize_to_json_only(raw)
        if json_only:
            data = parse_json_safely(json_only)
        else:
            data = parse_json_safely(raw)

        assistant_show = raw_stripped
        response_type = "conversation"

        if data and isinstance(data, dict):
            ready = data.get("ready")
            if ready is True:
                self.analysis_ready = True

                # alias 지원: audio_profile/profile -> target_features
                tf = data.get("target_features") or data.get("audio_profile") or data.get("profile")
                if not isinstance(tf, dict):
                    tf = None
                self._target_features = tf

                ig = data.get("inferred_genres")
                if isinstance(ig, list):
                    self._inferred_genres = [str(x) for x in ig]
                sa = data.get("seed_artists")
                if isinstance(sa, list):
                    self._seed_artists = [str(x) for x in sa]
                dh = data.get("diversity_hint")
                if isinstance(dh, dict):
                    self._diversity_hint = dh
                pj = data.get("per_track_jitter_hint")
                if isinstance(pj, dict):
                    self._per_track_jitter_hint = pj

                # 사용자에게 JSON을 그대로 보여주도록 처리
                assistant_show = json_only or ("```json\n" + raw_stripped + "\n```")
                response_type = "analysis_complete"
            elif ready is False:
                # 중간 응답 - 모델이 다른 텍스트여도 JSON을 보여주도록 처리
                assistant_show = "```json\n{\"ready\": false}\n```"
                response_type = "conversation"
            # 그 외: 모델 텍스트 그대로 출력(초기 질문 등)
        else:
            # JSON 추출 실패 -> 일반 문장으로 간주 (포맷트 준수 유도)
            # 첫 문장 위주로 clipping
            lines = raw_stripped.splitlines()
            line = lines[0][:120] if lines else raw_stripped
            assistant_show = line

        # 히스토리 반영
        self.history.append({"user": text, "assistant": assistant_show})

        return GeminiResponse(
            assistant_show,
            response_type=response_type,
            target_features=self._target_features,
            genres=self._inferred_genres,
            seed_artists=self._seed_artists,
        )

    def get_target_features(self) -> Optional[Dict[str, Any]]:
        if not self.analysis_ready:
            return None
        return {
            "target_features": self._target_features,
            "genres": self._inferred_genres,
            "seed_artists": self._seed_artists,
            "diversity_hint": self._diversity_hint,
            "per_track_jitter_hint": self._per_track_jitter_hint,
        }
