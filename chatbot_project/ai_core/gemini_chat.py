"""Gemini API를 파이썬 SDK로 호출하면 됨."""

from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from .prompts import SYSTEM_PROMPT


logger = logging.getLogger(__name__)


@dataclass
class GeminiResponse:
    """``GeminiMusicChat.send_message`` 호출 결과를 이 구조에 담으면 됨."""

    type: str
    message: str
    target_features: Optional[Dict[str, float]] = None
    genres: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "target_features": self.target_features,
            "genres": self.genres or [],
        }


class GeminiMusicChat:
    """Gemini 모델과 대화를 이어가고 상태를 기억하면 됨."""

    def __init__(self, *, api_key: Optional[str] = None, model_name: str = "gemini-2.0-flash-exp"):
        if not api_key:
            raise ValueError("Gemini API key must be supplied.")

        self._model_name = model_name
        self._api_key = api_key

        self.analysis_ready = False
        self.target_features: Optional[Dict[str, float]] = None
        self.target_genres: List[str] = []

        genai.configure(api_key=self._api_key)

        self._model = genai.GenerativeModel(self._model_name)
        self._system_prompt = SYSTEM_PROMPT
        self._history: List[Dict[str, str]] = []

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """대화 상태를 초기화하면 됨."""

        self.analysis_ready = False
        self.target_features = None
        self.target_genres = []
        self._history.clear()

    # ------------------------------------------------------------------
    def send_message(self, user_message: str) -> GeminiResponse:
        """사용자 메시지를 Gemini에 전달하고 응답을 해석하면 됨."""

        try:
            response = self._model.generate_content(self._build_prompt(user_message))
        except Exception as error:
            logger.exception("Gemini 호출이 실패했음: %s", error)
            return GeminiResponse(
                type="error",
                message="Gemini 호출이 실패했음. 잠시 후 다시 시도하면 됨.",
            )

        bot_message = getattr(response, "text", "").strip()

        if not bot_message:
            return GeminiResponse(
                type="error",
                message="Gemini 응답이 비어 있음. 다시 입력하면 됨.",
            )

        analysis_payload = self._extract_json(bot_message)

        if isinstance(analysis_payload, dict) and analysis_payload.get("ready"):
            self.analysis_ready = True
            self.target_features = analysis_payload.get("target_features")
            self.target_genres = analysis_payload.get("genres", [])

            clean_message = self._strip_json_block(bot_message).strip() or (
                "분석이 완료되었습니다! 잠시 후 추천을 준비할게요."
            )

            self._history.append({"user": user_message, "assistant": bot_message})

            return GeminiResponse(
                type="analysis_complete",
                message=clean_message,
                target_features=self.target_features,
                genres=self.target_genres,
            )

        clean_message = self._strip_json_block(bot_message).strip() or bot_message

        self._history.append({"user": user_message, "assistant": bot_message})

        return GeminiResponse(type="conversation", message=clean_message, genres=[])

    def _build_prompt(self, user_message: str) -> str:
        segments = [f"<SYSTEM>\n{self._system_prompt}\n</SYSTEM>"]
        for turn in self._history[-6:]:
            segments.append(f"<USER>\n{turn.get('user', '')}\n</USER>")
            segments.append(f"<ASSISTANT>\n{turn.get('assistant', '')}\n</ASSISTANT>")
        segments.append(f"<USER>\n{user_message}\n</USER>")
        return "\n\n".join(segments)

    # ------------------------------------------------------------------
    @staticmethod
    def _strip_json_block(text: str) -> str:
        return re.sub(r"```json\s*\{.*?\}\s*```", "", text, flags=re.DOTALL)

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """응답 안에 포함된 JSON 블록을 파싱하면 됨."""

        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if not match:
            return None

        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    def get_target_features(self) -> Optional[Dict[str, Any]]:
        """최근 분석 결과가 있으면 그대로 반환하면 됨."""

        if not self.analysis_ready:
            return None

        return {
            "target_features": self.target_features,
            "genres": self.target_genres,
        }

