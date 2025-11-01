"""CLI 데모 애플리케이션을 실행하려면 이 모듈을 사용하면 됨."""

from __future__ import annotations

import requests
import argparse
import json
from typing import Optional

from ai_core.config import Settings
from ai_core.strict_chat import StrictGeminiMusicChat as GeminiMusicChat
from ai_core.recommendation_service import RecommendationService
from ai_core.spotify_client import SpotifyClient, SpotifyAuthError
from ai_core.artist_inference import infer_seed_artists, normalize_artist_list


def _print_recommendations(payload: dict) -> None:
    print("\n🎧 Spotify 추천 플레이리스트")
    print("-" * 40)
    seed_artists = payload.get("seed_artists") or []
    seed_genres = payload.get("seed_genres") or []
    if seed_artists:
        print(f"선호 아티스트 기준: {', '.join(seed_artists)}")
    elif seed_genres:
        print(f"참고 장르: {', '.join(seed_genres)}")
    for idx, track in enumerate(payload.get("tracks", []), start=1):
        artists = ", ".join(track["artists"])
        print(f"{idx}. {track['name']} - {artists}")
        summary = track.get("summary")
        if summary:
            print(f"   🎧 {summary}")
        if track.get("url"):
            print(f"   🔗 {track['url']}")
        features = track.get("audio_features")
        if isinstance(features, dict) and features:
            readable = ", ".join(
                f"{key}: {round(value, 2)}"
                for key, value in features.items()
                if isinstance(value, (int, float))
            )
            if readable:
                print(f"   🎚️ {readable}")
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

    # 이전 추천 결과 저장 (같은 아티스트의 다른 노래를 요청할 때 사용)
    previous_seed_artists: Optional[list[str]] = None
    previous_track_ids: set[str] = set()

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

        conversation_snippets = []
        history = getattr(chat, "history", []) or []
        for turn in history[-8:]:
            user_turn = turn.get("user")
            if isinstance(user_turn, str) and user_turn.strip():
                conversation_snippets.append(user_turn.strip())
        if user_input:
            conversation_snippets.append(user_input)
        
        # "다른 X 노래", "X 노래 더" 같은 패턴 감지
        user_input_lower = user_input.lower()
        is_continuation_request = any(
            keyword in user_input_lower
            for keyword in ["다른", "더", "추가", "another", "more", "other"]
        )

        # Gemini의 seed_artists는 완전히 무시하고, 사용자 입력에서만 아티스트 추출
        # 이전에 1명의 아티스트만 추천했고, 계속 같은 아티스트 요청이면 유지
        if previous_seed_artists and len(previous_seed_artists) == 1 and (
            is_continuation_request or
            any(artist.lower() in user_input_lower for artist in previous_seed_artists)
        ):
            # 이전 아티스트를 강제로 유지
            inferred_artists = normalize_artist_list(previous_seed_artists)
            print(f"🔒 이전 아티스트 유지: {', '.join(inferred_artists)}")
        else:
            # 사용자 입력에서 직접 아티스트 추출 (Gemini 무시)
            inferred_artists = infer_seed_artists(
                conversation=[user_input],  # 현재 입력만 사용
                genres=None,  # 장르는 무시
                existing_artists=None,
                max_artists=1,  # 최대 1명만
                min_artists=0,  # 지정 안되어 있어도 OK
            )
            # 추출된 아티스트가 없으면 fallback 사용
            if not inferred_artists:
                # 아티스트가 명시되지 않은 경우 빈 리스트 (장르만으로 추천)
                inferred_artists = []
            else:
                inferred_artists = normalize_artist_list(inferred_artists)

        # Gemini의 seed_artists를 강제로 덮어쓰기
        gemini_response.seed_artists = inferred_artists

        if not gemini_response.target_features:
            print("⚠️ 타겟 오디오 특징이 누락되었습니다. 다시 시도해주세요.")
            continue

        try:
            # 이전에 추천한 곡들을 제외하고 새로운 곡들만 추천 받음
            exclude_track_ids = (
                list(previous_track_ids)
                if previous_seed_artists and len(previous_seed_artists) == 1 and previous_track_ids
                else []
            )
            
            recommendation_result = recommendation_service.recommend(
                target_features=gemini_response.target_features,
                target_feature_ranges=getattr(gemini_response, 'target_feature_ranges', None),
                genres=gemini_response.genres,
                seed_artists=gemini_response.seed_artists,
                exclude_track_ids=exclude_track_ids or None,
            )
        except SpotifyAuthError as exc:
            print(f"❌ Spotify 인증 오류: {exc}")
            continue

        payload = recommendation_service.build_backend_payload(recommendation_result)
        _print_recommendations(payload)

        # 이전 추천 결과 저장 (다음 요청에서 같은 아티스트 유지하기 위해)
        if payload.get("seed_artists"):
            # 정규화하여 저장 (중복 제거)
            previous_seed_artists = normalize_artist_list(payload["seed_artists"])
            # 이번에 추천된 트랙 IDs 저장 (중복 방지)
            previous_track_ids = {
                track.get("id") 
                for track in payload.get("tracks", []) 
                if track.get("id")
            }
        else:
            previous_seed_artists = None
            previous_track_ids = set()

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


def run_server() -> None:
    """Flask API 서버를 실행합니다."""
    from ai_core.config import Settings
    
    settings = Settings.from_env()
    
    print("=" * 60)
    print("🚀 AI API 서버를 시작합니다...")
    print("📍 서버 주소: http://localhost:5000")
    print("📍 Health check: http://localhost:5000/api/health")
    print("📍 Chat endpoint: POST http://localhost:5000/api/chat")
    print("📍 Reset endpoint: POST http://localhost:5000/api/chat/reset")
    print("=" * 60)
    
    # api_server 모듈을 임포트하여 실행
    import api_server
    api_server.app.run(host='0.0.0.0', port=5000, debug=True)


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
    parser.add_argument(
        "--server",
        action="store_true",
        help="Flask API 서버 모드로 실행하면 됨 (포트 5000).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    if args.server:
        # Flask API 서버 모드
        run_server()
    else:
        # CLI 챗봇 모드
        run_cli(limit=args.limit)
