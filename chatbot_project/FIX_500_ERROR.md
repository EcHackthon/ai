# 🔧 AI 서버 500 에러 수정

## 문제 원인

Flask 앱 내부의 중첩 함수(엔드포인트)에서 외부 함수의 로컬 변수(`chat`, `recommendation_service`)에 접근할 때 스코프 문제가 발생했습니다.

## 해결 방법

변수들을 전역 변수로 선언하여 모든 엔드포인트에서 접근 가능하도록 수정했습니다.

## 수정 사항

`ai-main/chatbot_project/main.py`:
- `chat` → `_app_chat` (전역 변수)
- `recommendation_service` → `_app_recommendation_service` (전역 변수)
- `backend_url` → `_app_backend_url` (전역 변수)

## 재시작 필요

**AI 서버를 재시작해주세요:**

1. Python 터미널에서 `Ctrl+C`로 서버 중지
2. 다시 실행:
   ```bash
   cd ai-main\chatbot_project
   python main.py --server
   ```

또는 `start_server.bat` 파일을 다시 실행하세요.

## 테스트

서버 재시작 후:
```bash
# 1. Health check
curl http://localhost:5000/api/health

# 2. 백엔드를 통한 채팅 테스트
curl -X POST http://localhost:4000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\": \"안녕하세요\"}"
```

프론트엔드 채팅창에서도 정상 작동할 것입니다.
