# AI-Main Flask 서버 실행 가이드

## 🚀 실행 방법

### 1. 의존성 설치
```bash
cd ai-main/chatbot_project
pip install -r requirements.txt
```

### 2. 환경변수 설정 (.env 파일)
```env
GEMINI_API_KEY=your_gemini_api_key
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

### 3. Flask 서버 실행
```bash
python main.py --server
```

또는 포트 지정:
```bash
python main.py --server --port 5000
```

### 4. CLI 모드 실행 (선택사항)
```bash
python main.py
```

## 📡 API 엔드포인트

### Health Check
```
GET http://localhost:5000/api/health
```

### 채팅
```
POST http://localhost:5000/api/chat
Content-Type: application/json

{
  "message": "기분 좋은 팝송 추천해줘",
  "session_id": "default"
}
```

### 세션 초기화
```
POST http://localhost:5000/api/chat/reset
Content-Type: application/json

{
  "session_id": "default"
}
```

## 🔧 주요 변경사항

1. ✅ Flask API 서버 추가 (api_server.py)
2. ✅ `python main.py --server` 실행 방식 구현
3. ✅ `'''` 및 ``` 시작 응답 필터링
4. ✅ 배포 주소로 변경 (localhost:4000 → https://back-ieck.onrender.com)
5. ✅ requirements.txt에 Flask, flask-cors 추가

## 🌐 배포 설정

백엔드 서버에서 AI_SERVER_URL 환경변수 설정:
```env
AI_SERVER_URL=https://your-ai-server-url
```

기본값: http://localhost:5000
