"""AI 서버 디버깅 및 테스트 스크립트"""

import sys
import traceback

print("=" * 60)
print("AI 서버 초기화 테스트")
print("=" * 60)

try:
    print("\n1. 모듈 임포트 테스트...")
    from ai_core.config import Settings
    print("✓ Settings 임포트 성공")
    
    from ai_core.strict_chat import StrictGeminiMusicChat as GeminiMusicChat
    print("✓ GeminiMusicChat 임포트 성공")
    
    from ai_core.spotify_client import SpotifyClient
    print("✓ SpotifyClient 임포트 성공")
    
    from ai_core.recommendation_service import RecommendationService
    print("✓ RecommendationService 임포트 성공")
    
    print("\n2. 설정 로드 테스트...")
    settings = Settings.from_env()
    print(f"✓ 설정 로드 성공")
    print(f"  - Gemini API Key: {'설정됨' if settings.gemini_api_key else '없음'}")
    print(f"  - Gemini Model: {settings.gemini_model}")
    print(f"  - Spotify Client ID: {'설정됨' if hasattr(settings, 'spotify_client_id') and settings.spotify_client_id else '없음'}")
    
    print("\n3. GeminiMusicChat 인스턴스 생성 테스트...")
    chat = GeminiMusicChat(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model
    )
    print(f"✓ GeminiMusicChat 생성 성공: {chat}")
    
    print("\n4. SpotifyClient 인스턴스 생성 테스트...")
    spotify_client = SpotifyClient(settings)
    print(f"✓ SpotifyClient 생성 성공: {spotify_client}")
    
    print("\n5. RecommendationService 인스턴스 생성 테스트...")
    recommendation_service = RecommendationService(
        spotify_client,
        default_limit=5,
        market=getattr(settings, 'spotify_market', 'KR')
    )
    print(f"✓ RecommendationService 생성 성공: {recommendation_service}")
    
    print("\n6. Gemini API 호출 테스트...")
    response = chat.send_message("안녕하세요")
    print(f"✓ Gemini 응답 성공:")
    print(f"  - Type: {response.type}")
    print(f"  - Message: {response.message[:100]}...")
    
    print("\n" + "=" * 60)
    print("✅ 모든 테스트 통과!")
    print("=" * 60)
    
except Exception as e:
    print("\n" + "=" * 60)
    print("❌ 오류 발생!")
    print("=" * 60)
    print(f"\n오류 메시지: {e}")
    print(f"\n상세 트레이스백:")
    traceback.print_exc()
    print("\n" + "=" * 60)
    sys.exit(1)
