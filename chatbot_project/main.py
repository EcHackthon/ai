"""Gemini powered CLI that curates Spotify tracks and pushes them to the backend."""

from __future__ import annotations

import argparse
import json
from typing import Iterable, Optional

import requests

from ai_core import (
    GeminiPlannerError,
    GeminiPlaylistPlanner,
    Settings,
    SpotifyAuthError,
    SpotifyService,
    SpotifyServiceError,
)
from ai_core.spotify_service import ResolvedTrack

DEFAULT_BACKEND_URL = "https://back-ieck.onrender.com/api/recommend"


def run_cli(*, limit: Optional[int] = None, backend_url: str = DEFAULT_BACKEND_URL) -> None:
    settings = Settings.from_env()
    effective_limit = limit or 5

    planner = GeminiPlaylistPlanner(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
        limit=effective_limit,
    )
    spotify = SpotifyService(settings, limit=effective_limit)

    _print_banner(effective_limit)

    while True:
        user_input = input("사용자> ").strip()
        if not user_input:
            continue

        lowered = user_input.lower()
        if lowered in {"quit", "exit"}:
            print("안녕히 가세요!")
            break

        try:
            plan = planner.plan(user_input)
        except GeminiPlannerError as exc:
            print(f"[Gemini] 요청을 이해하지 못했습니다: {exc}")
            continue

        if plan.needs_more_input:
            print(f"[Gemini] {plan.followup_question}")
            continue

        try:
            resolved_tracks = spotify.collect_tracks(plan)
        except SpotifyAuthError as exc:
            print(f"[Spotify] 인증에 실패했습니다: {exc}")
            continue
        except SpotifyServiceError as exc:
            print(f"[Spotify] API 오류가 발생했습니다: {exc}")
            continue

        if not resolved_tracks:
            print("[Spotify] 재생 가능한 트랙을 찾지 못했습니다. 더 구체적으로 말씀해 주세요.")
            continue

        payload = _build_payload(plan, resolved_tracks)
        _print_playlist(payload["playlist_title"], payload["mood_summary"], resolved_tracks)

        print("\n[Payload] 백엔드로 전송한 JSON:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        _push_to_backend(backend_url, payload)

        if plan.followup_question:
            print(f"\n[Gemini] {plan.followup_question}")


def _print_banner(limit: int) -> None:
    print("=" * 60)
    print("Gemini CLI DJ - 기분을 말하면 맞춤 곡을 찾아드려요.")
    print(f"요청당 최대 {limit}곡까지 추천합니다.")
    print("종료하려면 'quit' 또는 'exit'를 입력하세요.\n")


def _print_playlist(title: str, mood_summary: str, tracks: Iterable[ResolvedTrack]) -> None:
    print(f"\n재생목록: {title}")
    if mood_summary:
        print(f"   분위기 요약: {mood_summary}")
    print("-" * 60)
    for idx, track in enumerate(tracks, start=1):
        artists = ", ".join(track.artists)
        print(f"{idx:02d}. {track.name} - {artists}")
        if track.rationale:
            print(f"     추천 이유: {track.rationale}")
        if track.url:
            print(f"     링크: {track.url}")
        feature_summary = _summarise_audio_features(track.audio_features)
        if feature_summary:
            print(f"     오디오 특성: {feature_summary}")
    print("-" * 60)


def _summarise_audio_features(features: dict) -> str:
    if not features:
        return ""
    keys = ["danceability", "energy", "valence", "tempo"]
    parts = []
    for key in keys:
        if key in features:
            value = features[key]
            if isinstance(value, (int, float)):
                if key == "tempo":
                    parts.append(f"{key}={round(value)}")
                else:
                    parts.append(f"{key}={value:.2f}")
    return ", ".join(parts)


def _build_payload(plan, tracks: Iterable[ResolvedTrack]) -> dict:
    return {
        "provider": "spotify",
        "playlist_title": plan.playlist_title,
        "mood_summary": plan.mood_summary,
        "notes": plan.notes_for_backend,
        "reasoning": plan.reasoning,
        "tracks": [
            {
                "id": track.id,
                "name": track.name,
                "artists": track.artists,
                "url": track.url,
                "album_image": track.album_image,
                "popularity": track.popularity,
                "duration_ms": track.duration_ms,
                "rationale": track.rationale,
                "source": track.source,
                "audio_features": track.audio_features,
            }
            for track in tracks
        ],
    }


def _push_to_backend(backend_url: str, payload: dict) -> None:
    try:
        response = requests.post(backend_url, json=payload, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[Backend] 전송에 실패했습니다: {exc}")
        return

    try:
        body = response.json()
    except ValueError:
        body = response.text
    print(f"[Backend] 전송 성공 {response.status_code}: {body}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gemini CLI DJ - 기분을 음악으로 바꿔드립니다.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="요청당 가져올 최대 곡 수(기본 5).",
    )
    parser.add_argument(
        "--backend-url",
        type=str,
        default=DEFAULT_BACKEND_URL,
        help=f"플레이리스트 JSON을 전송할 백엔드 URL(기본: {DEFAULT_BACKEND_URL}).",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Flask API 서버 모드로 실행합니다.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="API 서버 포트 번호(기본: 5000)",
    )
    return parser.parse_args()


def run_server(port: int = 5000) -> None:
    """Flask API 서버를 실행합니다."""
    try:
        from api_server import app
    except ImportError as exc:
        print(f"❌ api_server 모듈을 불러올 수 없습니다: {exc}")
        print("api_server.py 파일이 존재하는지 확인해주세요.")
        return
    
    print("=" * 60)
    print("🚀 AI API 서버를 시작합니다...")
    print(f"📍 서버 주소: http://localhost:{port}")
    print(f"📍 Health check: http://localhost:{port}/api/health")
    print(f"📍 Chat endpoint: POST http://localhost:{port}/api/chat")
    print(f"📍 Reset endpoint: POST http://localhost:{port}/api/chat/reset")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=True)


if __name__ == "__main__":
    args = parse_args()
    
    if args.server:
        # Flask 서버 모드
        run_server(port=args.port)
    else:
        # CLI 모드
        run_cli(limit=args.limit, backend_url=args.backend_url)
