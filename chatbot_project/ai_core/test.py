from gemini_chat import GeminiMusicChat
import json

#해당 코드들은 테스트 용으로 ai 응답을 위한 프로그램입니다.
#아직 스포티파이가 연결이 안되어 있습니다.
def main():
    """Gemini 채팅 테스트"""
    print("=" * 50)
    print("🎵 음악 추천 챗봇 테스트 (Audio Features)")
    print("=" * 50)
    print("종료: 'quit' 입력\n")
    
    # Gemini 채팅 시스템 초기화
    chat = GeminiMusicChat()
    
    # 첫 인사
    print("🤖 AI: 안녕하세요! 오늘 어떤 음악을 들으시고 싶으세요?\n")
    
    message_count = 0
    
    while True:
        # 사용자 입력
        user_input = input("😊 You: ").strip()
        
        if user_input.lower() in ['quit', 'exit', '종료']:
            print("\n👋 대화를 종료합니다.")
            break
        
        if not user_input:
            continue
        
        message_count += 1
        print(f"\n[메시지 {message_count}번]")
        
        # Gemini에게 메시지 전송
        result = chat.send_message(user_input)
        
        # 응답 출력
        print(f"🤖 AI: {result['message']}\n")
        
        # 분석 완료되면 타겟 특징 출력
        if result['type'] == 'analysis_complete':
            print("=" * 50)
            print("✅ 분석 완료!")
            print("=" * 50)
            print("\n🎯 타겟 음악 특징 (Audio Features):")
            print(json.dumps(result['target_features'], indent=2, ensure_ascii=False))
            print("\n🎸 추천 장르:")
            print(json.dumps(result['genres'], indent=2, ensure_ascii=False))
            print("\n" + "=" * 50)
            print("이 특징을 가진 노래를 찾으면 됩니다!")
            print("백엔드가 Spotify의 노래들과 비교해서")
            print("가장 비슷한 노래를 추천합니다.")
            print("=" * 50)
            

if __name__ == "__main__":
    main()