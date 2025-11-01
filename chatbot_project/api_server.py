"""Flask API 서버: 프론트엔드와 Gemini AI를 연결합니다."""

from __future__ import annotations

import logging
import requests
from typing import Dict

from flask import Flask, request, jsonify
from flask_cors import CORS

from ai_core.config import Settings
from ai_core.strict_chat import StrictGeminiMusicChat as GeminiMusicChat
from ai_core.recommendation_service import RecommendationService
from ai_core.spotify_client import SpotifyClient, SpotifyAuthError
from ai_core.artist_inference import infer_seed_artists


# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # 모든 origin 허용 (개발 환경)

# 전역 설정 및 인스턴스
settings = Settings.from_env()
spotify_client = SpotifyClient(settings)
recommendation_service = RecommendationService(
    spotify_client,
    default_limit=5,
    market=settings.spotify_market,
)

# 세션별 채팅 인스턴스를 관리하기 위한 딕셔너리
chat_sessions: Dict[str, GeminiMusicChat] = {}

# 백엔드 서버 URL
BACKEND_SERVER_URL = "https://back-ieck.onrender.com"


def get_or_create_chat_session(session_id: str) -> GeminiMusicChat:
    """세션 ID에 해당하는 채팅 인스턴스를 가져오거나 생성합니다."""
    if session_id not in chat_sessions:
        chat_sessions[session_id] = GeminiMusicChat(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model
        )
        logger.info(f"[Session: {session_id}] 새로운 채팅 세션 생성")
    return chat_sessions[session_id]


@app.route('/api/health', methods=['GET'])
def health_check():
    """서버 상태 확인"""
    return jsonify({"status": "ok", "message": "AI server is running"})


@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    """
    프론트엔드에서 사용자 메시지를 받아 Gemini에 전달하고 응답을 반환합니다.
    
    Request Body:
    {
        "message": "사용자 메시지",
        "session_id": "세션 ID (선택사항)",
        "google_id": "구글 사용자 ID (선택사항)"
    }
    
    Response:
    {
        "type": "conversation" | "analysis_complete" | "error",
        "message": "AI 응답 메시지",
        "recommendations": {...} (분석 완료 시에만 포함)
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({
                "type": "error",
                "message": "메시지가 필요합니다."
            }), 400
        
        user_message = data['message']
        session_id = data.get('session_id', 'default')
        google_id = data.get('google_id')
        
        # 세션별 채팅 인스턴스 가져오기
        current_chat = get_or_create_chat_session(session_id)
        
        logger.info(f"[Session: {session_id}] User message: {user_message}")
        
        # Gemini에 메시지 전송
        gemini_response = current_chat.send_message(user_message)
        
        response_data = {
            "type": gemini_response.type,
            "message": gemini_response.message,
        }
        
        # 분석이 완료된 경우 Spotify 추천 생성
        if gemini_response.type == "analysis_complete" and gemini_response.target_features:
            try:
                # 대화 기록에서 아티스트 추론
                conversation_snippets = []
                history = getattr(current_chat, "history", []) or []
                for turn in history[-8:]:
                    user_turn = turn.get("user")
                    if isinstance(user_turn, str) and user_turn.strip():
                        conversation_snippets.append(user_turn.strip())
                if user_message:
                    conversation_snippets.append(user_message)
                
                inferred_artists = infer_seed_artists(
                    conversation=conversation_snippets,
                    genres=gemini_response.genres,
                    existing_artists=getattr(gemini_response, "seed_artists", None),
                    max_artists=5,
                    min_artists=1,
                )
                
                # Spotify 추천 생성
                recommendation_result = recommendation_service.recommend(
                    target_features=gemini_response.target_features,
                    target_feature_ranges=getattr(gemini_response, 'target_feature_ranges', None),
                    genres=gemini_response.genres,
                    seed_artists=inferred_artists,
                )
                
                # 백엔드 전송용 payload 생성
                payload = recommendation_service.build_backend_payload(recommendation_result)
                response_data["recommendations"] = payload
                
                logger.info(f"[Session: {session_id}] Generated {len(payload.get('tracks', []))} recommendations")
                
                # 백엔드 서버로 추천 결과 전송 (비동기적으로 처리)
                try:
                    # session_id를 payload에 추가
                    payload_with_session = {
                        **payload,
                        "session_id": session_id
                    }
                    
                    backend_response = requests.post(
                        f"{BACKEND_SERVER_URL}/api/recommend",
                        json=payload_with_session,
                        timeout=5
                    )
                    
                    if backend_response.status_code == 200:
                        logger.info(f"[Session: {session_id}] ✅ 백엔드로 추천 결과 전송 성공")
                    else:
                        logger.warning(f"[Session: {session_id}] ⚠️ 백엔드 응답 상태: {backend_response.status_code}")
                        
                except Exception as backend_exc:
                    logger.warning(f"[Session: {session_id}] ⚠️ 백엔드 전송 실패 (계속 진행): {backend_exc}")
                    # 백엔드 전송 실패해도 프론트엔드에는 정상 응답
                
            except SpotifyAuthError as exc:
                logger.error(f"Spotify auth error: {exc}")
                response_data["message"] += "\n\n⚠️ Spotify 인증 오류가 발생했습니다."
            except Exception as exc:
                logger.error(f"Recommendation error: {exc}")
                logger.exception("Full traceback:")
                response_data["message"] += "\n\n⚠️ 추천 생성 중 오류가 발생했습니다."
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.exception(f"Error in chat endpoint: {e}")
        return jsonify({
            "type": "error",
            "message": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
        }), 500


@app.route('/api/chat/reset', methods=['POST'])
def reset_chat():
    """
    채팅 세션을 초기화합니다.
    
    Request Body:
    {
        "session_id": "세션 ID (선택사항)"
    }
    """
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id', 'default')
        
        if session_id in chat_sessions:
            chat_sessions[session_id].reset()
            logger.info(f"[Session: {session_id}] Chat session reset")
        else:
            logger.info(f"[Session: {session_id}] No existing session to reset")
        
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


@app.route('/api/chat/sessions', methods=['GET'])
def list_sessions():
    """활성 세션 목록 조회 (디버깅용)"""
    return jsonify({
        "status": "ok",
        "active_sessions": list(chat_sessions.keys()),
        "session_count": len(chat_sessions)
    })


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 AI API 서버를 시작합니다...")
    print("📍 서버 주소: http://localhost:5000")
    print("📍 Health check: http://localhost:5000/api/health")
    print("📍 Chat endpoint: POST http://localhost:5000/api/chat")
    print("📍 Reset endpoint: POST http://localhost:5000/api/chat/reset")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
