"""CLI 데모 애플리케이션 + Flask API 서버를 실행하려면 이 모듈을 사용하면 됨."""

from __future__ import annotations

import requests
import argparse
import json
import logging
from typing import Optional

from flask import Flask, request, jsonify
from flask_cors import CORS

from ai_core.config import Settings
from ai_core.strict_chat import StrictGeminiMusicChat as GeminiMusicChat
from ai_core.recommendation_service import RecommendationService
from ai_core.spotify_client import SpotifyClient, SpotifyAuthError

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
                seed_artists=getattr(gemini_response, 'seed_artists', None),
            )
        except SpotifyAuthError as exc:
            print(f"❌ Spotify 인증 오류: {exc}")
            continue

        payload = recommendation_service.build_backend_payload(recommendation_result)
        _print_recommendations(payload)

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


# 전역 변수로 선언
_app_chat = None
_app_recommendation_service = None
_app_backend_url = "http://localhost:4000"


def create_flask_app() -> Flask:
    """Flask API 서버를 생성하면 됨."""
    
    global _app_chat, _app_recommendation_service
    
    app = Flask(__name__)
    CORS(app)  # CORS 활성화
    
    # 전역 설정 및 인스턴스
    settings = Settings.from_env()
    _app_chat = GeminiMusicChat(api_key=settings.gemini_api_key, model_name=settings.gemini_model)
    spotify_client = SpotifyClient(settings)
    _app_recommendation_service = RecommendationService(
        spotify_client,
        default_limit=5,
        market=settings.spotify_market,
    )
    
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """서버 상태 확인"""
        return jsonify({"status": "ok", "message": "AI server is running"})
    
    @app.route('/api/chat', methods=['POST'])
    def chat_endpoint():
        """
        백엔드에서 사용자 메시지를 받아 Gemini에 전달하고 응답을 반환합니다.
        """
        try:
            logger.info("=== Chat endpoint called ===")
            data = request.get_json()
            logger.info(f"Received data: {data}")
            
            if not data or 'message' not in data:
                logger.error("No message in request")
                return jsonify({
                    "type": "error",
                    "message": "메시지가 필요합니다."
                }), 400
            
            user_message = data['message']
            session_id = data.get('session_id', 'default')
            
            logger.info(f"[Session: {session_id}] User message: {user_message}")
            logger.info(f"Chat instance: {_app_chat}")
            logger.info(f"Recommendation service: {_app_recommendation_service}")
            
            # Gemini에 메시지 전송
            logger.info("Calling Gemini API...")
            try:
                gemini_response = _app_chat.send_message(user_message)
                logger.info(f"Gemini response type: {gemini_response.type}")
            except Exception as gemini_error:
                error_msg = str(gemini_error)
                logger.error(f"Gemini API error: {error_msg}")
                
                # 할당량 초과 에러 처리
                if "429" in error_msg or "quota" in error_msg.lower() or "ResourceExhausted" in error_msg:
                    return jsonify({
                        "type": "error",
                        "message": "😅 Gemini API 할당량이 초과되었습니다.\n\n무료 티어는 하루 50개 요청으로 제한됩니다.\n잠시 후 다시 시도해주세요. (약 1분 후)\n\n또는 .env 파일에서 다른 API 키를 사용하거나,\nGemini API 대시보드에서 할당량을 확인해주세요.\n\n🔗 https://ai.dev/usage"
                    }), 429
                
                # 기타 Gemini 에러
                return jsonify({
                    "type": "error",
                    "message": f"Gemini API 오류가 발생했습니다: {error_msg[:200]}"
                }), 500
            
            response_data = {
                "type": gemini_response.type,
                "message": gemini_response.message,
            }
            
            # 분석이 완료된 경우 Spotify 추천 생성
            if gemini_response.type == "analysis_complete" and gemini_response.target_features:
                try:
                    recommendation_result = _app_recommendation_service.recommend(
                        target_features=gemini_response.target_features,
                        genres=gemini_response.genres,
                        seed_artists=None,
                    )
                    
                    payload = _app_recommendation_service.build_backend_payload(recommendation_result)
                    response_data["recommendations"] = payload
                    
                    logger.info(f"[Session: {session_id}] Generated {len(payload.get('tracks', []))} recommendations")
                    
                    # 백엔드 서버로도 전송 (기존 동작 유지)
                    try:
                        backend_response = requests.post(
                            f"{_app_backend_url}/api/recommend",
                            json=payload,
                            timeout=5
                        )
                        logger.info(f"✅ 백엔드로 전송 성공: {backend_response.status_code}")
                    except Exception as exc:
                        logger.warning(f"⚠️ 백엔드 전송 실패 (무시): {exc}")
                    
                except SpotifyAuthError as exc:
                    logger.error(f"Spotify auth error: {exc}")
                    response_data["message"] += "\n\n⚠️ Spotify 인증 오류가 발생했습니다."
                except Exception as exc:
                    logger.error(f"Recommendation error: {exc}")
                    response_data["message"] += "\n\n⚠️ 추천 생성 중 오류가 발생했습니다."
            
            logger.info(f"Returning response: {response_data}")
            return jsonify(response_data), 200
            
        except Exception as e:
            logger.exception(f"!!! ERROR in chat endpoint: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({
                "type": "error",
                "message": f"서버 오류가 발생했습니다: {str(e)}"
            }), 500
    
    @app.route('/api/chat/reset', methods=['POST'])
    def reset_chat():
        """채팅 세션을 초기화합니다."""
        try:
            data = request.get_json() or {}
            session_id = data.get('session_id', 'default')
            
            _app_chat.reset()
            logger.info(f"[Session: {session_id}] Chat reset")
            
            return jsonify({
                "status": "ok",
                "message": "대화가 초기화되었습니다."
            }), 200
            
        except Exception as e:
            logger.exception(f"Error in reset endpoint: {e}")
            return jsonify({
                "type": "error",
                "message": "초기화 중 오류가 발생했습니다."
            }), 500
    
    return app


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
        help="Flask API 서버 모드로 실행하면 됨.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="API 서버 포트 번호 (기본값: 5000)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    if args.server:
        # Flask 서버 모드
        app = create_flask_app()
        print("=" * 60)
        print("🚀 AI API 서버를 시작합니다...")
        print(f"📍 서버 주소: http://localhost:{args.port}")
        print(f"📍 Health check: http://localhost:{args.port}/api/health")
        print(f"📍 Chat endpoint: POST http://localhost:{args.port}/api/chat")
        print("=" * 60)
        app.run(host='0.0.0.0', port=args.port, debug=True)
    else:
        # CLI 모드
        run_cli(limit=args.limit)
