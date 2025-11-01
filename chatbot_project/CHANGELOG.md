# AI-MAIN 수정 내역 (2025-11-02)

## 🔧 주요 변경사항

### 1. Flask API 서버 복원 (`api_server.py`)
**문제:** Flask 서버가 없어서 front-main → back-master → ai-main 채팅 연결 불가

**해결:**
- `backup/api_server.py.bak`를 기반으로 새로운 `api_server.py` 생성
- 세션별 채팅 인스턴스 관리 구현
- 아티스트 추론 기능 추가 (artist_inference 모듈 활용)
- 백엔드로 추천 결과 자동 전송 기능 추가

**주요 기능:**
- `POST /api/chat` - 사용자 메시지 처리 및 추천 생성
- `POST /api/chat/reset` - 세션 초기화
- `GET /api/health` - 서버 상태 확인
- `GET /api/chat/sessions` - 활성 세션 목록 (디버깅용)

---

### 2. start_server.bat 수정
**문제:** `python main.py --server` 명령이 존재하지 않음

**해결:**
```bat
# 변경 전
python main.py --server

# 변경 후
python api_server.py
```

---

### 3. start-all.bat 수정
**문제:** 전체 시스템 시작 시 잘못된 명령어 사용

**해결:**
```bat
# 변경 전
cd /d %~dp0ai-main\chatbot_project && python main.py --server

# 변경 후
cd /d %~dp0ai-main\chatbot_project && python api_server.py
```

---

### 4. requirements.txt 업데이트
**추가된 패키지:**
```
flask==3.0.0
flask-cors==4.0.0
```

---

### 5. 새로운 파일 추가

#### setup_and_start.bat
패키지 설치 및 서버 시작을 한 번에 수행

#### SERVER_GUIDE.md
AI 서버 사용 가이드 문서

---

## 📊 수정 전/후 비교

### 연결 구조 변화

**수정 전 (작동 불가):**
```
front-main → back-master → ❌ (Flask 서버 없음)
```

**수정 후 (정상 작동):**
```
front-main (Chat.jsx)
    ↓ POST /api/chat { message, session_id, google_id }
back-master (chat.js)
    ↓ POST http://localhost:5000/api/chat
ai-main (api_server.py) ✅
    ↓ Gemini API + Spotify API
    ↓ 응답 + recommendations
    ↓ POST http://localhost:4000/api/recommend
back-master (recommend.js)
    ↓ Supabase 저장
    ↓ 응답 전달
front-main (Chat.jsx)
    ↓ 메시지 표시 + 추천곡 처리
```

---

## ✅ 해결된 문제들

1. ✅ **Flask API 서버 부재** - api_server.py 생성으로 해결
2. ✅ **채팅 연결 불가** - 정상 작동
3. ✅ **추천 결과 전송 실패** - 백엔드로 자동 전송 구현
4. ✅ **세션 관리 미흡** - 세션별 독립적인 채팅 인스턴스 관리
5. ✅ **아티스트 추론 누락** - artist_inference 모듈 통합
6. ✅ **시작 스크립트 오류** - 모든 bat 파일 수정

---

## 🚀 사용 방법

### 처음 시작 (패키지 설치 필요)
```bash
cd ai-main/chatbot_project
setup_and_start.bat
```

### 일반 시작
```bash
cd ai-main/chatbot_project
start_server.bat
```

### 전체 시스템 시작
```bash
# 프로젝트 루트에서
start-all.bat
```

---

## 🔍 테스트 방법

1. AI 서버 시작:
```bash
cd ai-main/chatbot_project
python api_server.py
```

2. Health check 확인:
```bash
curl http://localhost:5000/api/health
```

3. 채팅 테스트:
```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"오늘 기분이 좋아\", \"session_id\": \"test\"}"
```

---

## 📝 참고사항

- main.py는 CLI 모드로 여전히 사용 가능
- api_server.py는 웹 API 전용
- 두 파일은 같은 ai_core 모듈을 공유
- 세션은 메모리에 저장되어 서버 재시작 시 초기화됨

---

## 🐛 알려진 이슈

없음 (현재 모든 주요 문제 해결됨)

---

## 📅 변경 이력

- 2025-11-02: 초기 수정 완료
  - Flask API 서버 복원
  - 세션 관리 개선
  - 백엔드 연동 강화
  - 문서화 추가
