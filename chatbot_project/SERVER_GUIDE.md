# AI 서버 사용 가이드

## 🚀 빠른 시작

### 1. 패키지 설치 및 서버 시작
```bash
setup_and_start.bat
```
또는
```bash
start_server.bat
```

### 2. 서버만 시작 (패키지가 이미 설치된 경우)
```bash
python api_server.py
```

### 3. CLI 모드 실행 (터미널에서 대화)
```bash
python main.py
```

---

## 📁 파일 구조

- `api_server.py` - Flask API 서버 (프론트엔드와 통신)
- `main.py` - CLI 모드 (터미널에서 직접 대화)
- `start_server.bat` - 서버 시작 스크립트
- `setup_and_start.bat` - 패키지 설치 + 서버 시작
- `ai_core/` - 핵심 AI 로직 모듈

---

## 🔧 API 엔드포인트

### POST /api/chat
사용자 메시지를 받아 AI 응답 및 음악 추천 생성

**Request:**
```json
{
  "message": "오늘 기분이 좋아",
  "session_id": "user_session_123",
  "google_id": "optional_google_id"
}
```

**Response:**
```json
{
  "type": "conversation" | "analysis_complete",
  "message": "AI 응답 메시지",
  "recommendations": {
    "provider": "spotify",
    "tracks": [
      {
        "name": "노래 제목",
        "artists": ["아티스트"],
        "url": "spotify:track:...",
        "album_image": "이미지 URL",
        "audio_features": {...}
      }
    ]
  }
}
```

### POST /api/chat/reset
채팅 세션 초기화

**Request:**
```json
{
  "session_id": "user_session_123"
}
```

### GET /api/health
서버 상태 확인

**Response:**
```json
{
  "status": "ok",
  "message": "AI server is running"
}
```

---

## 🔄 연결 구조

```
front-main (Chat.jsx)
    ↓ POST /api/chat
back-master (chat.js)
    ↓ POST http://localhost:5000/api/chat
ai-main (api_server.py)
    ↓ Gemini API + Spotify API
    ↓ 응답: { message, recommendations }
    ↓ POST http://localhost:4000/api/recommend (백엔드로 추천 결과 전송)
back-master (recommend.js)
    ↓ Supabase에 저장
```

---

## ⚙️ 환경 변수 (.env)

필수 환경 변수:
```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-flash

SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_MARKET=KR
```

---

## 🐛 문제 해결

### 1. 패키지 설치 오류
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. 포트 이미 사용 중
다른 프로그램이 5000번 포트를 사용 중일 수 있습니다.
```bash
# Windows에서 5000번 포트 확인
netstat -ano | findstr :5000

# 프로세스 종료 (PID 확인 후)
taskkill /PID <PID> /F
```

### 3. Spotify 인증 오류
.env 파일의 SPOTIFY_CLIENT_ID와 SPOTIFY_CLIENT_SECRET을 확인하세요.

### 4. 백엔드 연결 오류
back-master 서버가 4000번 포트에서 실행 중인지 확인하세요.

---

## 📝 세션 관리

- 각 `session_id`마다 독립적인 채팅 컨텍스트 유지
- 세션은 서버가 재시작될 때까지 메모리에 유지
- 프로덕션 환경에서는 Redis 등을 사용한 영구 저장 권장

---

## 🔍 로그 확인

서버 실행 시 콘솔에 다음 로그가 표시됩니다:
- `[Session: xxx] User message: ...` - 사용자 메시지 수신
- `[Session: xxx] Generated N recommendations` - 추천 생성 완료
- `✅ 백엔드로 추천 결과 전송 성공` - 백엔드 전송 성공
- `⚠️ 백엔드 전송 실패` - 백엔드 전송 실패 (계속 진행)
