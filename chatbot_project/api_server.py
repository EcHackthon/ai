"""Flask API 서버: 프론트엔드와 Gemini AI를 연결합니다."""

from __future__ import annotations

import logging
import requests
from typing import Dict

from flask import Flask, request, jsonify
from flask_cors import CORS

from ai_core import (
    GeminiPlannerError,
    GeminiPlaylistPlanner,
    Settings,
    SpotifyAuthError,
    SpotifyService,
    SpotifyServiceError,
)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # 모든 origin 허용 (개발 환경)

# 전역 설정 및 인스턴스
settings = Settings.from_env()
planner = GeminiPlaylistPlanner(
    api_key=settings.gemini_api_key,
    model_name=settings.gemini_model,
    limit=5,
)
spotify_service = SpotifyService(settings, limit=5)

# 세션별 대화 히스토리를 관리하기 위한 딕셔너리
chat_sessions: Dict[str, list] = {}

# 백엔드 서버 URL
BACKEND_SERVER_URL = "https://back-ieck.onrender.com"


def filter_code_blocks(text: str) -> tuple[str, bool]:
    """
    코드 블록으로 시작하는 텍스트를 필터링합니다.
    Returns: (filtered_text, is_filtered)
    """
    if not text:
        return text, False
    
    stripped = text.strip()
    # ''' 또는 ``` 로 시작하는 경우 필터링
    if stripped.startswith("'''") or stripped.startswith("```"):
        logger.info(f"[Filter] 코드 블록 응답 필터링: {stripped[:50]}...")
        return "", True
    
    return text, False


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
        "session_id": "세션 ID (선택사항)"
    }
    
    Response:
    {
        "type": "conversation" | "recommendation" | "error",
        "message": "AI 응답 메시지",
        "recommendations": {...} (추천 완료 시에만 포함)
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
        
        # 세션별 히스토리 가져오기 (간단한 구현)
        if session_id not in chat_sessions:
            chat_sessions[session_id] = []
        
        logger.info(f"[Session: {session_id}] User message: {user_message}")
        
        # Gemini에 메시지 전송
        try:
            plan = planner.plan(user_message)
            
            # 더 많은 정보가 필요한 경우
            if plan.needs_more_input:
                response_message = plan.followup_question
                filtered_message, is_filtered = filter_code_blocks(response_message)
                
                if is_filtered:
                    return jsonify({
                        "type": "filtered",
                        "message": ""
                    }), 200
                
                return jsonify({
                    "type": "conversation",
                    "message": filtered_message
                }), 200
            
            # 추천 생성
            try:
                resolved_tracks = spotify_service.collect_tracks(plan)
                
                if not resolved_tracks:
                    return jsonify({
                        "type": "conversation",
                        "message": "재생 가능한 트랙을 찾지 못했습니다. 다른 기분이나 장르를 말씀해주세요."
                    }), 200
                
                # 백엔드 전송용 payload 생성
                payload = {
                    "provider": "spotify",
                    "playlist_title": plan.playlist_title,
                    "mood_summary": plan.mood_summary,
                    "notes": plan.notes_for_backend,
                    "reasoning": plan.reasoning,
                    "session_id": session_id,
                    "tracks": [
                        {
                            "id": track.id,
                            "name": track.name,
                            "artists": track.artists,
                            "url": track.url,
                            "album_image": track.album_image,
                            "popularity": track.popularity,
                            "duration_ms": track.duration_ms,
                            "rationale": track.rationale,
                            "source": track.source,
                            "audio_features": track.audio_features,
                        }
                        for track in resolved_tracks
                    ],
                }
                
                logger.info(f"[Session: {session_id}] Generated {len(payload['tracks'])} recommendations")
                
                # 백엔드 서버로 추천 결과 전송
                try:
                    backend_response = requests.post(
                        f"{BACKEND_SERVER_URL}/api/recommend",
                        json=payload,
                        timeout=5
                    )
                    
                    if backend_response.status_code == 200:
                        logger.info(f"[Session: {session_id}] ✅ 백엔드로 추천 결과 전송 성공")
                    else:
                        logger.warning(f"[Session: {session_id}] ⚠️ 백엔드 응답 상태: {backend_response.status_code}")
                        
                except Exception as backend_exc:
                    logger.warning(f"[Session: {session_id}] ⚠️ 백엔드 전송 실패 (계속 진행): {backend_exc}")
                
                # 응답 메시지 생성
                response_message = f"🎵 {plan.playlist_title}\n\n"
                if plan.mood_summary:
                    response_message += f"{plan.mood_summary}\n\n"
                response_message += f"{len(resolved_tracks)}곡의 추천 음악을 준비했습니다!"
                
                # 필터링 체크
                filtered_message, is_filtered = filter_code_blocks(response_message)
                
                if is_filtered:
                    return jsonify({
                        "type": "filtered",
                        "message": "",
                        "recommendations": payload
                    }), 200
                
                return jsonify({
                    "type": "recommendation",
                    "message": filtered_message,
                    "recommendations": payload
                }), 200
                
            except SpotifyAuthError as exc:
                logger.error(f"Spotify auth error: {exc}")
                return jsonify({
                    "type": "error",
                    "message": "Spotify 인증 오류가 발생했습니다."
                }), 500
            except SpotifyServiceError as exc:
                logger.error(f"Spotify service error: {exc}")
                return jsonify({
                    "type": "error",
                    "message": "Spotify 서비스 오류가 발생했습니다."
                }), 500
                
        except GeminiPlannerError as exc:
            logger.error(f"Gemini planner error: {exc}")
            error_message = f"요청을 이해하지 못했습니다: {exc}"
            filtered_message, is_filtered = filter_code_blocks(error_message)
            
            if is_filtered:
                return jsonify({
                    "type": "filtered",
                    "message": ""
                }), 200
            
            return jsonify({
                "type": "conversation",
                "message": filtered_message
            }), 200
        
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
            chat_sessions[session_id] = []
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
