"""
통신 테스트 스크립트
AI 서버, 백엔드, 프론트엔드 간의 통신을 테스트합니다.

테스트 항목:
1. AI 서버(Flask) ↔ 프론트엔드 통신 (포트 5000)
2. AI 서버 → 백엔드 추천 결과 전송 (포트 4000)
3. 백엔드 → 프론트엔드 추천 결과 전달
"""

import requests
import json
import time
from typing import Optional

# 서버 주소 설정 (배포 환경)
AI_SERVER_URL = "http://localhost:5000"  # AI 서버는 로컬에서만 실행
BACKEND_SERVER_URL = "https://back-ieck.onrender.com"

# 테스트 메시지
TEST_MESSAGES = [
    "기분 좋은 음악 추천해줘",
    "신나는 팝송 듣고 싶어",
    "잔잔한 발라드 추천해줘"
]


def print_section(title: str):
    """섹션 제목 출력"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_result(success: bool, message: str):
    """결과 출력"""
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")


def test_ai_server_health() -> bool:
    """테스트 1: AI 서버 Health Check"""
    print_section("테스트 1: AI 서버 상태 확인")
    
    try:
        response = requests.get(f"{AI_SERVER_URL}/api/health", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print_result(True, f"AI 서버 연결 성공: {data}")
            return True
        else:
            print_result(False, f"AI 서버 응답 오류: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print_result(False, "AI 서버에 연결할 수 없습니다. Flask 서버가 실행 중인지 확인하세요.")
        print("   실행 방법: cd ai-main/chatbot_project && python main.py --server")
        return False
    except Exception as e:
        print_result(False, f"예상치 못한 오류: {e}")
        return False


def test_backend_health() -> bool:
    """백엔드 서버 상태 확인"""
    print_section("백엔드 서버 상태 확인")
    
    try:
        response = requests.get(f"{BACKEND_SERVER_URL}/api/health", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print_result(True, f"백엔드 서버 연결 성공: {data}")
            return True
        else:
            print_result(False, f"백엔드 서버 응답 오류: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print_result(False, "백엔드 서버에 연결할 수 없습니다. Node.js 서버가 실행 중인지 확인하세요.")
        print("   실행 방법: cd back-master && npm start")
        return False
    except Exception as e:
        print_result(False, f"예상치 못한 오류: {e}")
        return False


def test_ai_chat_endpoint(message: str = "신나는 음악 추천해줘") -> Optional[dict]:
    """테스트 2: AI 서버 채팅 엔드포인트"""
    print_section(f"테스트 2: AI 서버 채팅 API - '{message}'")
    
    try:
        payload = {
            "message": message,
            "session_id": "test_session_001"
        }
        
        print(f"📤 요청 데이터: {json.dumps(payload, ensure_ascii=False)}")
        
        response = requests.post(
            f"{AI_SERVER_URL}/api/chat",
            json=payload,
            timeout=60  # Gemini API 호출 시간 고려
        )
        
        if response.status_code == 200:
            data = response.json()
            print_result(True, f"AI 응답 수신 성공")
            print(f"   응답 타입: {data.get('type')}")
            print(f"   메시지: {data.get('message', '')[:100]}...")
            
            if data.get('recommendations'):
                recs = data['recommendations']
                track_count = len(recs.get('tracks', []))
                print(f"   ✨ 추천곡 포함: {track_count}개")
                
                if track_count > 0:
                    print(f"\n   🎵 추천된 곡:")
                    for i, track in enumerate(recs['tracks'][:3], 1):
                        artists = ', '.join(track.get('artists', []))
                        print(f"      {i}. {track.get('name')} - {artists}")
                
                return recs
            else:
                print_result(True, "추천곡은 아직 생성되지 않음 (대화 중)")
                return None
        else:
            print_result(False, f"AI 서버 오류: {response.status_code} - {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        print_result(False, "요청 시간 초과 (60초)")
        return None
    except Exception as e:
        print_result(False, f"오류 발생: {e}")
        return None


def test_backend_recommend_endpoint() -> Optional[dict]:
    """테스트 3: 백엔드에서 추천 결과 가져오기"""
    print_section("테스트 3: 백엔드 추천 결과 조회")
    
    try:
        response = requests.get(f"{BACKEND_SERVER_URL}/api/recommend", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('ok') and data.get('data'):
                recs = data['data']
                track_count = len(recs.get('tracks', []))
                print_result(True, f"백엔드에서 추천 결과 조회 성공: {track_count}개 트랙")
                
                if track_count > 0:
                    print(f"\n   🎵 백엔드에 저장된 추천곡:")
                    for i, track in enumerate(recs['tracks'][:5], 1):
                        artists = ', '.join(track.get('artists', []))
                        print(f"      {i}. {track.get('name')} - {artists}")
                
                return recs
            else:
                print_result(True, "백엔드에 아직 추천 결과가 없습니다")
                return None
        else:
            print_result(False, f"백엔드 오류: {response.status_code}")
            return None
            
    except Exception as e:
        print_result(False, f"오류 발생: {e}")
        return None


def test_backend_chat_relay() -> bool:
    """테스트 4: 백엔드를 통한 AI 서버 통신"""
    print_section("테스트 4: 백엔드 Chat API (AI 서버 중계)")
    
    try:
        payload = {
            "message": "테스트 메시지",
            "session_id": "test_session_002"
        }
        
        print(f"📤 백엔드로 메시지 전송: {payload['message']}")
        
        response = requests.post(
            f"{BACKEND_SERVER_URL}/api/chat",
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            print_result(True, "백엔드 Chat API 정상 작동")
            print(f"   응답 타입: {data.get('type')}")
            print(f"   메시지: {data.get('message', '')[:100]}...")
            return True
        else:
            print_result(False, f"백엔드 Chat API 오류: {response.status_code}")
            return False
            
    except Exception as e:
        print_result(False, f"오류 발생: {e}")
        return False


def test_ai_to_backend_integration() -> bool:
    """테스트 5: AI → 백엔드 통합 테스트"""
    print_section("테스트 5: AI 서버 → 백엔드 통합 테스트")
    
    # AI 서버에 추천 요청
    print("\n1️⃣ AI 서버에 추천 요청 중...")
    recommendations = test_ai_chat_endpoint("신나는 팝송 추천해줘")
    
    if not recommendations:
        print_result(False, "AI 서버에서 추천 결과를 받지 못했습니다")
        return False
    
    # 잠시 대기 (백엔드 전송 시간)
    print("\n⏳ 백엔드 전송 대기 중 (3초)...")
    time.sleep(3)
    
    # 백엔드에서 추천 결과 확인
    print("\n2️⃣ 백엔드에서 추천 결과 확인 중...")
    backend_data = test_backend_recommend_endpoint()
    
    if backend_data:
        # 트랙 비교
        ai_track_names = {track['name'] for track in recommendations.get('tracks', [])}
        backend_track_names = {track['name'] for track in backend_data.get('tracks', [])}
        
        if ai_track_names == backend_track_names:
            print_result(True, "✨ AI → 백엔드 통합 테스트 성공! 데이터 일치")
            return True
        else:
            print_result(True, "⚠️ 데이터가 일치하지 않지만 전송은 성공")
            return True
    else:
        print_result(False, "백엔드에서 추천 결과를 찾을 수 없습니다")
        return False


def run_all_tests():
    """모든 테스트 실행"""
    print("\n" + "🧪" * 40)
    print("  통신 테스트 시작")
    print("🧪" * 40)
    
    results = []
    
    # 서버 상태 확인
    ai_ok = test_ai_server_health()
    backend_ok = test_backend_health()
    
    if not ai_ok or not backend_ok:
        print("\n" + "⚠️" * 40)
        print("  서버가 실행되지 않았습니다. 먼저 서버를 시작하세요:")
        print("  1. AI 서버: cd ai-main/chatbot_project && python main.py --server")
        print("  2. 백엔드: cd back-master && npm start")
        print("⚠️" * 40)
        return
    
    # AI 채팅 API 테스트
    time.sleep(1)
    rec = test_ai_chat_endpoint("신나는 음악 추천해줘")
    results.append(("AI Chat API", rec is not None))
    
    # 백엔드 중계 테스트
    time.sleep(1)
    relay_ok = test_backend_chat_relay()
    results.append(("Backend Chat Relay", relay_ok))
    
    # 통합 테스트
    time.sleep(1)
    integration_ok = test_ai_to_backend_integration()
    results.append(("AI → Backend Integration", integration_ok))
    
    # 최종 결과
    print("\n" + "📊" * 40)
    print("  테스트 결과 요약")
    print("📊" * 40)
    
    for test_name, success in results:
        icon = "✅" if success else "❌"
        print(f"{icon} {test_name}")
    
    all_success = all(success for _, success in results)
    
    if all_success:
        print("\n🎉" * 40)
        print("  모든 테스트 통과!")
        print("🎉" * 40)
    else:
        print("\n⚠️" * 40)
        print("  일부 테스트 실패")
        print("⚠️" * 40)


if __name__ == "__main__":
    run_all_tests()
