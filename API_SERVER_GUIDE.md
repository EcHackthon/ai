# AI 채팅 서버 시작 가이드

프론트엔드 채팅창과 Gemini AI를 연결하는 Flask API 서버입니다.

## 📋 필수 요구사항

1. Python 3.8 이상
2. Gemini API Key
3. Spotify API 자격증명

## 🚀 시작하기

### 1. 의존성 설치

먼저 ai-main 폴더의 가상환경을 활성화하고 필요한 패키지를 설치합니다:

```bash
cd ai-main\chatbot_project

# 가상환경이 없다면 생성
python -m venv venv

# 가상환경 활성화 (Windows)
venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일에 다음 내용이 설정되어 있는지 확인하세요:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash-exp
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_MARKET=KR
```

### 3. API 서버 실행

```bash
# chatbot_project 폴더에서 실행
python api_server.py
```

서버가 정상적으로 시작되면 다음 메시지가 표시됩니다:
```
============================================================
🚀 AI API 서버를 시작합니다...
📍 서버 주소: http://localhost:5000
📍 Health check: http://localhost:5000/api/health
📍 Chat endpoint: POST http://localhost:5000/api/chat
============================================================
```

### 4. 프론트엔드 실행

별도의 터미널에서 프론트엔드를 실행합니다:

```bash
cd front-main
npm install  # 처음 한 번만
npm run dev
```

## 📡 API 엔드포인트

### 1. Health Check
```
GET http://localhost:5000/api/health
```

### 2. 채팅 메시지 전송
```
POST http://localhost:5000/api/chat
Content-Type: application/json

{
  "message": "사용자 메시지",
  "session_id": "선택사항"
}
```

**응답 예시:**
```json
{
  "type": "conversation",
  "message": "AI 응답 메시지"
}
```

또는 분석 완료 시:
```json
{
  "type": "analysis_complete",
  "message": "분석이 완료되었습니다!",
  "recommendations": {
    "tracks": [...],
    "seed_artists": [...],
    "seed_genres": [...]
  }
}
```

### 3. 채팅 초기화
```
POST http://localhost:5000/api/chat/reset
Content-Type: application/json

{
  "session_id": "선택사항"
}
```

## 🔄 통신 흐름

1. **사용자 입력** → 프론트엔드 Chat.jsx에서 메시지 입력
2. **프론트엔드 → AI 서버** → `POST /api/chat`로 메시지 전송
3. **AI 서버 → Gemini** → Gemini API에 메시지 전달
4. **Gemini → AI 서버** → Gemini 응답 수신 및 분석
5. **AI 서버 → Spotify** (필요시) → 음악 추천 생성
6. **AI 서버 → 프론트엔드** → 응답 및 추천 결과 반환
7. **프론트엔드** → 채팅창에 메시지 표시

## 🧪 테스트 방법

### 수동 테스트 (curl)

```bash
# Health check
curl http://localhost:5000/api/health

# 채팅 메시지 전송
curl -X POST http://localhost:5000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\": \"안녕하세요\"}"
```

### 브라우저 테스트

1. AI 서버 실행 (`python api_server.py`)
2. 프론트엔드 실행 (`npm run dev`)
3. 브라우저에서 채팅 페이지 접속
4. 메시지 입력 후 응답 확인

## ⚠️ 문제 해결

### CORS 오류
- `flask-cors`가 설치되어 있는지 확인
- API 서버가 5000번 포트에서 실행 중인지 확인

### 연결 오류
- AI 서버가 실행 중인지 확인
- 프론트엔드의 `AI_SERVER_URL`이 올바른지 확인 (Chat.jsx 상단)

### Gemini API 오류
- `.env` 파일의 `GEMINI_API_KEY`가 올바른지 확인
- API 키의 할당량이 남아있는지 확인

### Spotify 인증 오류
- `.env` 파일의 Spotify 자격증명 확인
- Spotify 개발자 대시보드에서 앱 설정 확인

## 📝 개발 팁

### 로그 확인
API 서버는 콘솔에 상세한 로그를 출력합니다. 문제 발생 시 로그를 확인하세요.

### 세션 관리
현재는 기본 세션(`default`)을 사용합니다. 여러 사용자를 지원하려면 고유한 `session_id`를 사용하세요.

### 프로덕션 배포
프로덕션 환경에서는:
- `app.run(debug=False)` 설정
- CORS 설정을 특정 도메인으로 제한
- 세션 관리를 Redis 등으로 변경
- HTTPS 사용
