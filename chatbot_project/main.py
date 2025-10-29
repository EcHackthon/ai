"""CLI 데모 애플리케이션을 실행하려면 이 모듈을 사용하면 됨."""

from __future__ import annotations

import argparse
import json
from typing import Optional

from ai_core.config import Settings
from ai_core.gemini_chat import GeminiMusicChat
from ai_core.recommendation_service import RecommendationService
from ai_core.spotify_client import SpotifyClient, SpotifyAuthError


def _print_recommendations(payload: dict) -> None:
    print("\n🎧 Spotify 추천 플레이리스트")
    print("-" * 40)
    for idx, track in enumerate(payload.get("tracks", []), start=1):
        artists = ", ".join(track["artists"])
        print(f"{idx}. {track['name']} - {artists}")
        if track.get("url"):
            print(f"   🔗 {track['url']}")
        if track.get("preview_url"):
            print(f"   🎵 Preview: {track['preview_url']}")
    print("-" * 40)


def run_cli(limit: Optional[int] = None) -> None:
    settings = Settings.from_env()

    chat = GeminiMusicChat(api_key=settings.gemini_api_key, model_name=settings.gemini_model)
    spotify_client = SpotifyClient(settings)
    recommendation_service = RecommendationService(
        spotify_client,
        default_limit=limit or 5,
        market=settings.spotify_market,
    )

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

        try:
            recommendation_result = recommendation_service.recommend(
                target_features=gemini_response.target_features,
                genres=gemini_response.genres,
            )
        except SpotifyAuthError as exc:
            print(f"❌ Spotify 인증 오류: {exc}")
            continue

        payload = recommendation_service.build_backend_payload(recommendation_result)
        _print_recommendations(payload)

        print("\n백엔드 전송용 JSON:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))


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

