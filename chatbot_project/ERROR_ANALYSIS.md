# 🔍 500 에러 원인 분석 및 해결

## 🎯 발견된 문제

### 원인: **Gemini API 할당량 초과**

```
429 You exceeded your current quota
Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests
Limit: 50 requests per day (Free Tier)
```

**Gemini API 무료 티어 제한:**
- 하루 50개 요청 제한
- `gemini-2.0-flash-exp` 모델 기준
- 제한 초과 시 약 1분 대기 필요

## ✅ 적용된 수정 사항

### 1. AI 서버 (main.py)
- ✅ Gemini API 에러 처리 강화
- ✅ 할당량 초과 시 친절한 메시지 반환 (429 상태 코드)
- ✅ 상세한 로깅 추가

### 2. 백엔드 (chat.js)
- ✅ AI 서버의 에러 응답을 프론트엔드로 전달
- ✅ 에러 타입 및 메시지 구조 개선

### 3. 프론트엔드 (Chat.jsx)
- ✅ 에러 메시지도 채팅창에 표시
- ✅ 사용자에게 친절한 피드백 제공

## 🔧 해결 방법

### 옵션 1: 잠시 대기 (권장)
할당량이 리셋될 때까지 약 **1분** 정도 기다린 후 다시 시도하세요.

### 옵션 2: 다른 Gemini 모델 사용
`.env` 파일에서 모델을 변경:

```env
# 현재 (할당량 소진)
GEMINI_MODEL=gemini-2.0-flash-exp

# 변경 옵션
GEMINI_MODEL=gemini-1.5-flash
# 또는
GEMINI_MODEL=gemini-1.5-pro
```

각 모델은 별도의 할당량을 가집니다.

### 옵션 3: 새 API 키 발급
1. https://ai.dev 접속
2. 새 프로젝트 생성
3. 새 API 키 발급
4. `.env` 파일의 `GEMINI_API_KEY` 업데이트

### 옵션 4: 유료 플랜 업그레이드
더 많은 요청이 필요하다면:
- https://ai.google.dev/pricing 참고
- Google Cloud Console에서 결제 설정

## 🧪 현재 할당량 확인

```bash
# 테스트 스크립트 실행
cd ai-main\chatbot_project
python test_server.py
```

성공 시:
```
✅ 모든 테스트 통과!
```

할당량 초과 시:
```
❌ 오류 발생!
429 You exceeded your current quota
```

## 📊 할당량 모니터링

https://ai.dev/usage?tab=rate-limit 에서 실시간 사용량 확인 가능

## 🚀 서버 재시작

수정 사항 적용을 위해 **AI 서버만 재시작**하면 됩니다:

```bash
# 1. 현재 실행 중인 AI 서버 중지 (Ctrl+C)

# 2. 재시작
cd ai-main\chatbot_project
python main.py --server
```

백엔드와 프론트엔드는 **재시작 불필요** (핫 리로드 지원)

## 💡 개선된 사용자 경험

이제 할당량 초과 시 채팅창에 다음과 같은 메시지가 표시됩니다:

```
😅 Gemini API 할당량이 초과되었습니다.

무료 티어는 하루 50개 요청으로 제한됩니다.
잠시 후 다시 시도해주세요. (약 1분 후)

또는 .env 파일에서 다른 API 키를 사용하거나,
Gemini API 대시보드에서 할당량을 확인해주세요.

🔗 https://ai.dev/usage
```

## 📝 향후 개선 사항

1. **캐싱**: 동일한 질문에 대해 캐시된 응답 사용
2. **Rate Limiting**: 클라이언트 측에서 요청 제한
3. **대체 AI**: 할당량 초과 시 다른 AI 모델로 폴백
4. **사용량 알림**: 일일 사용량 80% 도달 시 경고

## ✅ 체크리스트

- [x] 에러 원인 파악 (Gemini API 할당량 초과)
- [x] AI 서버 에러 핸들링 개선
- [x] 백엔드 에러 전달 개선
- [x] 프론트엔드 에러 표시 개선
- [x] 디버깅 스크립트 작성
- [x] 사용자 가이드 작성

## 🆘 추가 도움이 필요하면

1. AI 서버 로그 확인
2. `python test_server.py` 실행해서 구체적인 에러 확인
3. https://ai.dev/usage 에서 할당량 확인
