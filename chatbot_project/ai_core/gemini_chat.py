import google.generativeai as genai
import json
import re
import os
from dotenv import load_dotenv
from prompts import SYSTEM_PROMPT

load_dotenv()

class GeminiMusicChat:
    def __init__(self):
        """Gemini 초기화"""
        self.analysis_ready = False
        self.target_features = None
        self.target_genres = None
        
        # Gemini API 설정
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 .env 파일에 없습니다!")
        
        genai.configure(api_key=api_key)
        
        #모델 초기화 시 시스템 프롬프트 설정
        self.model = genai.GenerativeModel(
            'gemini-2.0-flash-exp',
            system_instruction=SYSTEM_PROMPT 
        )
        
        #빈 히스토리로 채팅 시작
        self.chat = self.model.start_chat(history=[])
        
        print("Gemini 연결 성공!")
    
    def send_message(self, user_message):
        """
        사용자 메시지를 Gemini에게 보내고 응답 받기
        """
        try:
            #user_message 전송
            response = self.chat.send_message(user_message)
            bot_message = response.text


        except Exception as e:
            return {
                "type": "error",
                "message": f"Gemini API 오류: {str(e)}"
            }
         
        
        # JSON 분석 결과가 있는지 확인 (간단한 트리거)
        if '"ready": true' in bot_message:
            analysis = self._extract_json(bot_message) 
            
            if analysis and analysis.get("ready"):
                self.analysis_ready = True
                self.target_features = analysis.get("target_features")
                self.target_genres = analysis.get("genres", [])
                
                # AI의 실제 답변만 추출 (JSON 블록 제거)
                message_without_json = re.sub(r'```json\s*(\{.*?\})\s*```', '', bot_message, flags=re.DOTALL).strip()
                
                # main.py가 스크린샷처럼 AI의 실제 분석 멘트를 출력하게 함
                if not message_without_json:
                    message_without_json = "분석 완료! 이제 음악을 추천해드릴 수 있어요 🎵"
                
                return {
                    "type": "analysis_complete",
                    "message": message_without_json, # 하드코딩된 메시지 대신 실제 AI 답변
                    "target_features": self.target_features,
                    "genres": self.target_genres
                }
        
        # 일반 대화
        return {
            "type": "conversation",
            "message": bot_message
        }
    
    def _extract_json(self, text):

        # ```json ... ``` 블록을 찾습니다. (re.DOTALL은 .이 줄바꿈도 포함하게 함)
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        
        if json_match:
            json_string = json_match.group(1) # 1번 캡처 그룹 (괄호 안의 내용)
            try:
                return json.loads(json_string)
            except json.JSONDecodeError as e:
                print(f"JSON 파싱 오류: {e} | 원본: {json_string}")
                return None
        return None
    
     #백엔드에게 전달할 타겟 특징 반환
    def get_target_features(self):
       
        if not self.analysis_ready:
            return None
        return {
            "target_features": self.target_features,
            "genres": self.target_genres
        }