# Gemini CLI DJ

Gemini와 Spotify Web API를 결합해 사용자의 기분과 추가 조건에 맞는 곡을 찾아주는 CLI입니다.  
Gemini가 대화 맥락을 분석하고 JSON 형태의 플레이리스트 플랜을 생성하면, CLI가 Spotify 검색으로 실제 재생 가능한 트랙을 검증·보강한 뒤 백엔드에 전달합니다.

## 환경 변수
프로젝트 루트(`chatbot_project/`)에 `.env`를 만들고 필수 값을 채웁니다.

```env
GEMINI_API_KEY=your_gemini_key
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_MARKET=KR        # 기본값은 US
GEMINI_MODEL=gemini-2.0-flash-exp
```

다음 값은 선택 사항입니다(미지정 시 무시됩니다).

```env
SPOTIFY_REFRESH_TOKEN=optional_refresh_token
SPOTIFY_REDIRECT_URI=https://example.com/callback
```

`python-dotenv`가 `.env`를 자동으로 로드하므로 추가 작업은 필요 없습니다.

## 실행 방법

```bash
cd chatbot_project
python -m venv .venv
.venv\Scripts\activate  # PowerShell
pip install -r requirements.txt
python main.py
```

옵션:

- `--limit <n>` : 요청당 반환할 최대 곡 수(기본값 5)
- `--backend-url <url>` : 플레이리스트 JSON을 전송할 엔드포인트(기본값 `http://localhost:4000/api/recommend`)

CLI에서 `quit` 또는 `exit`를 입력하면 종료됩니다.

## 동작 흐름
1. 사용자가 분위기, 상황, 추가 요구사항을 자연어로 입력합니다.
2. `GeminiPlaylistPlanner`가 대화 내용을 분석하고 다음을 포함한 JSON을 반환합니다.
   - 곡 후보 리스트(`track_requests`)
   - 부족할 경우를 대비한 검색 키워드(`fallback_queries`)
   - 백엔드로 전달할 요약 정보
3. `SpotifyService`가 각 곡을 Spotify에서 검색해 실제 재생 가능한 트랙만 추립니다.
   - 검색 실패 시 보조 키워드로 채워 넣습니다.
   - `audio-features` API를 호출해 곡 특성(tempo, energy 등)을 가져옵니다.
4. CLI는 결과를 콘솔에 출력하고 동일한 데이터를 백엔드로 POST합니다.

## 백엔드 전송 예시

```json
{
  "provider": "spotify",
  "playlist_title": "Sunrise Ease",
  "mood_summary": "Calm, bright, gentle female vocals",
  "notes": "Early morning focus with light acoustic textures.",
  "reasoning": "User wanted mellow acoustic pop to ease into the day.",
  "tracks": [
    {
      "id": "3n3Ppam7vgaVa1iaRUc9Lp",
      "name": "Mr. Brightside",
      "artists": ["The Killers"],
      "url": "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp",
      "album_image": "https://i.scdn.co/image/...",
      "popularity": 78,
      "duration_ms": 222075,
      "rationale": "Upbeat indie rock energy to lift the morning mood.",
      "source": "gemini",
      "audio_features": {
        "danceability": 0.54,
        "energy": 0.95,
        "valence": 0.47,
        "tempo": 148.03
      }
    }
  ]
}
```

필드 구조는 `main.py`의 `_build_payload`를 참고하세요.

## 코드 구성

```
chatbot_project/
├── ai_core/
│   ├── config.py            # .env를 읽어 Settings 객체 생성
│   ├── gemini_playlist.py   # Gemini와 대화하며 플레이리스트 플랜 생성
│   ├── spotify_service.py   # Spotify 검색·오디오 특성 조회
│   └── __init__.py
├── main.py                  # CLI 엔트리포인트
└── requirements.txt
```

`google-generativeai`, `requests`, `python-dotenv`만 사용하도록 간소화했습니다.  
`recommendations` API 대신 명시적 트랙 검색을 사용하므로, 결과는 항상 Spotify에서 즉시 재생 가능한 곡으로만 구성됩니다.
