"""CLI 데모 애플리케이션을 실행하려면 이 모듈을 사용하면 됨."""

from __future__ import annotations

import requests
import argparse
import json
from typing import Optional

from ai_core.config import Settings
from ai_core.strict_chat import StrictGeminiMusicChat as GeminiMusicChat


def run_cli(limit: Optional[int] = None) -> None:
    settings = Settings.from_env()

    chat = GeminiMusicChat(api_key=settings.gemini_api_key, model_name=settings.gemini_model)

    print("=" * 60)
    print("🤖 Gemini 기반 감정형 음악 추천 챗봇")
    if limit:
        print(f"한 번에 {limit}곡씩 추천받으면 됨.")
    print("종료하려면 'quit' 또는 'exit'를 입력하면 됨.")
    print("=" * 60)

    while True:
        user_input = input("🧑 You: ").strip()
        if user_input.lower() in {"quit", "exit"}:
            print("👋 챗봇을 종료합니다.")
            break

        if not user_input:
            continue

        gemini_response = chat.send_message(user_input)
        print(f"🤖 Gemini: {gemini_response.message}\n")

        if gemini_response.type != "analysis_complete":
            continue

        if not gemini_response.target_features:
            print("⚠️ 타겟 오디오 특징이 누락되었습니다. 다시 시도해주세요.")
            continue

        # 분석 결과를 백엔드로 전송
        payload = {
            "target_features": gemini_response.target_features,
            "target_feature_ranges": getattr(gemini_response, 'target_feature_ranges', None),
            "genres": gemini_response.genres,
            "seed_artists": getattr(gemini_response, 'seed_artists', None),
            "limit": limit or 5,
        }

        print("\n백엔드 전송용 JSON:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        
        try:
            response = requests.post(
                "http://localhost:4000/api/recommend",
                json=payload,
                timeout=5
            )
            print("✅ 백엔드로 전송 성공:", response.status_code)
            print("백엔드 응답:", response.json())
        except Exception as exc:
            print("❌ 백엔드 전송 실패:", exc)


def parse_args() -> argparse.Namespace:
    """CLI 실행 시 사용할 인자를 파싱하면 됨."""

    parser = argparse.ArgumentParser(
        description="Gemini 감정 분석으로 Spotify 추천을 출력하면 됨.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="한 번에 추천받을 곡 수를 바꾸고 싶으면 이 옵션을 쓰면 됨.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_cli(limit=args.limit)