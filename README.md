# AI 감정 기반 음악 추천 챗봇

Gemini 대화 모델과 Spotify Web API를 연결하여 사용자의 감정과 상황을
기반으로 음악을 추천하는 CLI 프로토타입입니다. 
Jason Mayes의 `Web-AI-Spotify-DJ` 아이디어를 Python 환경에서 재구현하면서 
백엔드와의 연동을 염두에 둔 구조로 정리했습니다.

## 구성 요소

- **Gemini** – 감정 분석과 오디오 피처 추출을 담당합니다.
- **Spotify Web API** – Gemini가 산출한 오디오 피처를 이용해 실제 곡을
  추천합니다.
- **RecommendationService** – 분석 결과를 받아 Spotify 추천 API를 호출하고
  백엔드 전송용 페이로드를 생성합니다.

## 환경 변수 설정

루트(`/workspace/ai/chatbot_project`)에 `.env` 파일을 만들고 아래 값을
입력하세요.



```env
GEMINI_API_KEY=your_gemini_key
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# 다음 항목은 개인 계정 연동 시 사용,
# 하지만, admin 이 Spotify Token을 built-in 하게
# 작성해도 좋음.

SPOTIFY_REFRESH_TOKEN=optional_refresh_token

SPOTIFY_REDIRECT_URI=https://example.com/callback

SPOTIFY_MARKET=KR  # 기본값은 US

SPOTIFY_DEFAULT_SEED_GENRES=pop,dance-pop  
# Spotify에서 제공하는 장르 시드만 넣으면 됨
# 2024이후 Spotify 는 자체적으로 genre 를 넘겨주는 api를 파기함.

GEMINI_MODEL=gemini-2.0-flash-exp
```

> ⚠️ `.env` 파일은 `chatbot_project/.gitignore`에 포함되어 있으므로 저장소에
> 커밋되지 않습니다.

## 설치 및 실행

```bash
cd chatbot_project
python -m venv .venv
source .venv/bin/activate  # Windows는 .venv\Scripts\activate
pip install -r requirements.txt
python main.py
# 기본 5곡이 아닌 다른 개수로 추천받고 싶으면 --limit 옵션을 쓰면 됨.
python main.py --limit 7
# Local 에서 환경이 되있는 경우엔, virtual-simulation 단계는 건너 뛰어도 됨.
```

CLI는 자연어로 대화하며 사용자의 감정을 파악합니다. 
Gemini가 충분한 정보를 모으면 자동으로 Spotify 추천을 실행하고,
추천된 곡과 함께 백엔드로 전송 가능한 JSON 페이로드를 출력합니다.

## 백엔드 연동

`RecommendationService.build_backend_payload()`에서 반환하는 딕셔너리를 그대로
REST API나 메시지 큐에 전달하면 됩니다. 구조는 다음과 같습니다.

```json
{
  "provider": "spotify",
  "audio_features": {"energy": 0.8, "tempo": 120},
  "genres": ["pop"],
  "tracks": [
    {
      "id": "123",
      "name": "Song",
      "artists": ["Artist"],
      "url": "https://open.spotify.com/track/123",
      "preview_url": "https://p.scdn.co/mp3-preview/...",
      "album_image": "https://i.scdn.co/image/..."
    }
  ]
}
```

## 코드 구조

```
chatbot_project/
├── ai_core/
│   ├── config.py                 # 환경 변수 로더
│   ├── gemini_chat.py            # Gemini 대화 래퍼
│   ├── models.py                 # 데이터 모델 정의
│   ├── prompts.py                # 시스템 프롬프트
│   ├── recommendation_service.py # Spotify 추천 비즈니스 로직
│   └── spotify_client.py         # Spotify API 클라이언트
├── main.py                       # CLI 진입점
└── requirements.txt
```

각 모듈은 객체지향적으로 구성되어 있어 다른 인터페이스
(예: FastAPI, Flask,웹소켓) 로 확장하기 쉽습니다.
Spotify 권장 사양에 맞춰 오디오 피처 값은 자동으로
클램핑(clamping)되며,  실제로 사용된 장르 시드만 결과에 
남도록 정리됩니다.

## 최근 변경 사항

### 251029
- 모든 모듈의 주석과 Docstring을 한국어 문체로 통일해서 두 명의 작업자가
  같은 뉘앙스로 문서를 읽으면 됨.
- 보안상 실제 키를 분리할 수 있도록 `.env.example`을 추가했고, 필요한 값은
  `.env`에만 채우면 됨.
- Gemini 호출이 실패했을 때 사용자에게 바로 알려주고 재시도하면 되도록
  예외 처리를 넣었고, CLI에서 `--limit` 옵션으로 추천 곡 수를 조절하면 됨.
### 251030
- Spotify 추천은 허용된 장르 시드만 자동으로 선택하고, Spotify 문서에 나온 범위로
  오디오 피처를 정규화해서 호출하므로 404 오류나 잘못된 요청을 예방하면 됨.
  `.env`의 `SPOTIFY_DEFAULT_SEED_GENRES`에는 `available-genre-seeds` API에서 제공하는
  값만 넣으면 됨.

## 테스트 방법

아래 명령을 실행해서 파이썬 소스가 정상적으로 컴파일되는지 확인하면 됨.

```bash
python -m compileall chatbot_project
```

