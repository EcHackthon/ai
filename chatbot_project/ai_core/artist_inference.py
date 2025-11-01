"""
Utilities to infer plausible seed artists from conversational signals.

The heuristics here are intentionally lightweight so that we can supply
Spotify recommendation seeds even when the LLM did not emit explicit
``seed_artists`` values.  They strike a balance between precision and
coverage by combining explicit mentions, genre keywords, and era hints.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence

# Canonical artist names keyed by lowercase alias (including Hangul forms).
# The lists are intentionally small but representative for K-Pop and global pop.
ARTIST_ALIASES: Dict[str, str] = {
    # Korean / K-Pop
    "iu": "IU",
    "아이유": "IU",
    "newjeans": "NewJeans",
    "뉴진스": "NewJeans",
    "bts": "BTS",
    "방탄소년단": "BTS",
    "방탄": "BTS",
    "blackpink": "BLACKPINK",
    "블랙핑크": "BLACKPINK",
    "le sserafim": "LE SSERAFIM",
    "르세라핌": "LE SSERAFIM",
    "ive": "IVE",
    "아이브": "IVE",
    "red velvet": "Red Velvet",
    "레드벨벳": "Red Velvet",
    "twice": "TWICE",
    "트와이스": "TWICE",
    "itzy": "ITZY",
    "있지": "ITZY",
    "aespa": "aespa",
    "에스파": "aespa",
    "stayc": "STAYC",
    "스테이씨": "STAYC",
    "bigbang": "BIGBANG",
    "빅뱅": "BIGBANG",
    "g-dragon": "G-DRAGON",
    "지드래곤": "G-DRAGON",
    "taemin": "TAEMIN",
    "태민": "TAEMIN",
    "shinee": "SHINee",
    "샤이니": "SHINee",
    "taeyeon": "TAEYEON",
    "태연": "TAEYEON",
    "seventeen": "SEVENTEEN",
    "세븐틴": "SEVENTEEN",
    "stray kids": "Stray Kids",
    "스트레이키즈": "Stray Kids",
    "enhypen": "ENHYPEN",
    "엔하이픈": "ENHYPEN",
    "nct": "NCT",
    "엔시티": "NCT",
    "monsta x": "MONSTA X",
    "몬스타엑스": "MONSTA X",
    "mamamoo": "MAMAMOO",
    "마마무": "MAMAMOO",
    "gfriend": "GFRIEND",
    "여자친구": "GFRIEND",
    "sunmi": "SUNMI",
    "선미": "SUNMI",
    "zico": "ZICO",
    "지코": "ZICO",
    "jay park": "Jay Park",
    "박재범": "Jay Park",
    "psy": "PSY",
    "박재상": "PSY",
    "epik high": "Epik High",
    "에픽하이": "Epik High",
    "akmu": "AKMU",
    "악동뮤지션": "AKMU",
    "bol4": "BOL4",
    "볼빨간사춘기": "BOL4",
    "10cm": "10CM",
    "박혜진": "박혜진",
    "jannabi": "JANNABI",
    "잔나비": "JANNABI",
    "lee mu jin": "Lee Mujin",
    "이무진": "Lee Mujin",
    "kim feel": "Kim Feel",
    "김필": "Kim Feel",
    # Global Pop / Hip-hop / R&B
    "taylor swift": "Taylor Swift",
    "테일러 스위프트": "Taylor Swift",
    "bruno mars": "Bruno Mars",
    "브루노 마스": "Bruno Mars",
    "ed sheeran": "Ed Sheeran",
    "에드 시런": "Ed Sheeran",
    "billie eilish": "Billie Eilish",
    "빌리 아일리시": "Billie Eilish",
    "dua lipa": "Dua Lipa",
    "두아 리파": "Dua Lipa",
    "olivia rodrigo": "Olivia Rodrigo",
    "harry styles": "Harry Styles",
    "shawn mendes": "Shawn Mendes",
    "justin bieber": "Justin Bieber",
    "아리아나 그란데": "Ariana Grande",
    "ariana grande": "Ariana Grande",
    "selena gomez": "Selena Gomez",
    "weeknd": "The Weeknd",
    "the weeknd": "The Weeknd",
    "위켄드": "The Weeknd",
    "post malone": "Post Malone",
    "도자 캣": "Doja Cat",
    "doja cat": "Doja Cat",
    "sza": "SZA",
    "sia": "Sia",
    "avicii": "Avicii",
    "davichi": "Davichi",
    "britney spears": "Britney Spears",
    "backstreet boys": "Backstreet Boys",
    "nsync": "*NSYNC",
    "nsync": "*NSYNC",
    "madonna": "Madonna",
    "michael jackson": "Michael Jackson",
    "queen": "Queen",
    "coldplay": "Coldplay",
    "maroon 5": "Maroon 5",
    "maroon5": "Maroon 5",
    "imagine dragons": "Imagine Dragons",
    "linkin park": "Linkin Park",
    "paramore": "Paramore",
    "phoebe bridgers": "Phoebe Bridgers",
    "tame impala": "Tame Impala",
    # Japanese / J-Pop
    "yoasobi": "YOASOBI",
    "요아소비": "YOASOBI",
    "official hige dandism": "Official HIGE DANDism",
    "official higedandism": "Official HIGE DANDism",
    "오피셜히게단디즘": "Official HIGE DANDism",
    "히게단": "Official HIGE DANDism",
    "mrs. green apple": "Mrs. GREEN APPLE",
    "mrs green apple": "Mrs. GREEN APPLE",
    "미세스그린애플": "Mrs. GREEN APPLE",
    "king gnu": "King Gnu",
    "킹누": "King Gnu",
    "kenshi yonezu": "Kenshi Yonezu",
    "켄시 요네즈": "Kenshi Yonezu",
    "ado": "Ado",
    "아도": "Ado",
    "아이묭": "Aimyon",
    "aimyon": "Aimyon",
    "yorushika": "Yorushika",
    "요루시카": "Yorushika",
    "radwimps": "RADWIMPS",
    "라드윔프스": "RADWIMPS",
    "sekai no owari": "SEKAI NO OWARI",
    "세카이노오와리": "SEKAI NO OWARI",
    "bump of chicken": "BUMP OF CHICKEN",
    "범프오브치킨": "BUMP OF CHICKEN",
    "asian kung fu generation": "Asian Kung-Fu Generation",
    "asian kung-fu generation": "Asian Kung-Fu Generation",
    "아시안쿵푸제너레이션": "Asian Kung-Fu Generation",
    "utada hikaru": "Utada Hikaru",
    "우타다 히카루": "Utada Hikaru",
    "perfume": "Perfume",
    "퍼퓸": "Perfume",
    "aimer": "Aimer",
    "에이머": "Aimer",
    "eve": "Eve",
    "yonezu kenshi": "Kenshi Yonezu",
    "back number": "back number",
    "백넘버": "back number",
    "eir aoi": "Eir Aoi",
    "에이루아오이": "Eir Aoi",
    "justice": "Justice",
    "daft punk": "Daft Punk",
    "cassius": "Cassius",
    "stardust": "Stardust",
    "chemical brothers": "The Chemical Brothers",
    "jamiroquai": "Jamiroquai",
}

# Genre keywords -> canonical fallback artists (ordered by relevance).
GENRE_TO_ARTISTS: Dict[str, List[str]] = {
    "k-pop": ["NewJeans", "LE SSERAFIM", "BTS", "IVE", "TWICE"],
    "kpop": ["NewJeans", "LE SSERAFIM", "BTS", "IVE", "TWICE"],
    "j-pop": [
        "YOASOBI",
        "Official HIGE DANDism",
        "Mrs. GREEN APPLE",
        "Kenshi Yonezu",
        "King Gnu",
        "Ado",
        "LiSA",
    ],
    "jpop": [
        "YOASOBI",
        "Official HIGE DANDism",
        "Mrs. GREEN APPLE",
        "Kenshi Yonezu",
        "King Gnu",
        "Ado",
        "LiSA",
    ],
    "j-rock": ["Mrs. GREEN APPLE", "King Gnu", "RADWIMPS", "BUMP OF CHICKEN", "Asian Kung-Fu Generation"],
    "jrock": ["Mrs. GREEN APPLE", "King Gnu", "RADWIMPS", "BUMP OF CHICKEN", "Asian Kung-Fu Generation"],
    "anisong": ["LiSA", "Aimer", "Eir Aoi", "YOASOBI", "RADWIMPS"],
    "anime": ["LiSA", "Aimer", "YOASOBI", "RADWIMPS", "Eve"],
    "ballad": ["IU", "Kim Feel", "Lee Mujin", "Baekhyun"],
    "indie": ["JANNABI", "AKMU", "Se So Neon"],
    "r&b": ["SZA", "The Weeknd", "Taeyeon", "Crush"],
    "rnb": ["SZA", "The Weeknd", "Crush", "Dean"],
    "hip hop": ["ZICO", "Epik High", "Jay Park", "Beenzino"],
    "hip-hop": ["ZICO", "Epik High", "Jay Park", "Beenzino"],
    "retro": ["Daft Punk", "Justice", "Stardust"],
    "french house": ["Daft Punk", "Cassius", "Stardust"],
    "dance": ["Dua Lipa", "Calvin Harris", "Daft Punk"],
    "pop": ["Taylor Swift", "Ariana Grande", "Bruno Mars", "Olivia Rodrigo"],
    "teen pop": ["Taylor Swift", "Olivia Rodrigo", "Selena Gomez"],
    "edm": ["Avicii", "Calvin Harris", "Martin Garrix"],
    "house": ["Daft Punk", "Disclosure", "Calvin Harris"],
    "electro": ["Justice", "Daft Punk", "Skrillex"],
    "lofi": ["Joakim Karud", "Jinsang", "Idealism"],
    "jazz": ["Jamie Cullum", "Norah Jones", "Michel Camilo"],
    "city pop": ["Yutaka", "Tatsuro Yamashita", "Mariya Takeuchi"],
    "classic": ["Queen", "The Beatles", "ABBA"],
    "rock": ["Imagine Dragons", "Linkin Park", "Paramore"],
}

GENERIC_GENRE_KEYS = {"pop", "teen pop"}

# Era hints -> fallback artists that represent that period.
ERA_HINTS: Dict[str, List[str]] = {
    "80": ["Michael Jackson", "Madonna", "Queen"],
    "90": ["Backstreet Boys", "Britney Spears", "Daft Punk"],
    "00": ["Bruno Mars", "Coldplay", "Daft Punk"],
    "2000": ["Bruno Mars", "Coldplay", "Daft Punk"],
    "2010": ["Taylor Swift", "Ariana Grande", "The Weeknd"],
}

DEFAULT_FALLBACK_ARTISTS: List[str] = []


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = lowered.replace("&", " and ")
    lowered = lowered.replace("’", "'")
    cleaned = re.sub(r"[^0-9a-z가-힣\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _dedupe_preserve(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def normalize_artist_name(name: str) -> str:
    """
    아티스트 이름을 정규화합니다 (별칭을 표준 이름으로 변환).
    예: "박재범" -> "Jay Park", "jay park" -> "Jay Park"
    """
    if not name:
        return name
    normalized = _normalize_text(name)
    # ARTIST_ALIASES에서 찾기
    for alias, canonical in ARTIST_ALIASES.items():
        if _contains_alias(normalized, alias):
            return canonical
    # 일치하는 별칭이 없으면 원본 반환 (첫 글자 대문자)
    return name.strip()


def normalize_artist_list(artists: Sequence[str]) -> List[str]:
    """
    아티스트 리스트를 정규화하고 중복을 제거합니다.
    예: ["Jay Park", "박재범"] -> ["Jay Park"]
    """
    normalized = [normalize_artist_name(name) for name in artists if name]
    seen: set[str] = set()
    result: List[str] = []
    for name in normalized:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result


def _mentions_from_texts(texts: Sequence[str]) -> List[str]:
    mentions: List[str] = []
    if not texts:
        return mentions
    for text in texts:
        normalized = _normalize_text(text or "")
        if not normalized:
            continue
        for alias, canonical in ARTIST_ALIASES.items():
            if _contains_alias(normalized, alias):
                mentions.append(canonical)
    return _dedupe_preserve(mentions)


def _contains_alias(normalized_text: str, alias: str) -> bool:
    alias_norm = alias.lower()
    if not alias_norm:
        return False
    if re.search(r"[가-힣]", alias_norm):
        return alias_norm in normalized_text
    pattern = rf"\b{re.escape(alias_norm)}\b"
    return re.search(pattern, normalized_text) is not None


def _genre_fallbacks(genres: Sequence[str], *, max_results: int = 5) -> List[str]:
    specific_matches: List[str] = []
    generic_matches: List[str] = []

    for genre in genres or []:
        if not isinstance(genre, str):
            continue
        normalized = genre.lower()
        for key, candidates in GENRE_TO_ARTISTS.items():
            if key in normalized:
                target = generic_matches if key in GENERIC_GENRE_KEYS else specific_matches
                for name in candidates:
                    if name not in target:
                        target.append(name)

    combined: List[str] = []
    for pool in (specific_matches, generic_matches):
        for name in pool:
            if name not in combined:
                combined.append(name)
            if len(combined) >= max_results:
                return combined[:max_results]
    return combined[:max_results]


def _era_fallbacks(texts: Sequence[str]) -> List[str]:
    fallbacks: List[str] = []
    aggregated = " ".join(_normalize_text(text or "") for text in texts or [])
    if not aggregated:
        return fallbacks
    for key, artists in ERA_HINTS.items():
        if key in aggregated:
            fallbacks.extend(artists)
    return fallbacks


def infer_seed_artists(
    *,
    conversation: Sequence[str] | None,
    genres: Sequence[str] | None,
    existing_artists: Sequence[str] | None = None,
    max_artists: int = 5,
    min_artists: int = 1,
) -> List[str]:
    """
    Infer seed artist list to feed into Spotify recommendations.

    Parameters
    ----------
    conversation:
        Iterable of recent conversation snippets (user-first order preferred).
    genres:
        Genre hints produced by the LLM.
    existing_artists:
        Artists already identified by upstream logic (LLM extractions).
    max_artists:
        Upper bound for returned artist count (Spotify accepts up to five).
    min_artists:
        Minimum number of artists to return whenever possible.
    """
    try:
        max_count = int(max_artists)
    except (TypeError, ValueError):
        max_count = 5
    max_count = max(1, max_count)

    try:
        min_count = int(min_artists)
    except (TypeError, ValueError):
        min_count = 1
    min_count = max(1, min(min_count, max_count))

    candidates: List[str] = []
    seen_lower: set[str] = set()

    def _extend(pool: Sequence[str]) -> None:
        for name in pool:
            cleaned = str(name).strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen_lower:
                continue
            seen_lower.add(lowered)
            candidates.append(cleaned)
            if len(candidates) >= max_count:
                return

    existing_clean: List[str] = []
    if existing_artists:
        existing_clean = [
            str(name).strip()
            for name in existing_artists
            if isinstance(name, str) and str(name).strip()
        ]
    _extend(existing_clean)

    if len(candidates) < max_count:
        _extend(_mentions_from_texts(conversation or []))

    # 사용자가 명시적으로 아티스트를 지정했는지 확인
    has_explicit_artist = len(candidates) > 0

    genre_candidates = _genre_fallbacks(genres or [], max_results=max_count)
    # 명시적 아티스트가 있을 때는 장르 fallback을 제한적으로 추가
    if len(candidates) < max_count:
        if has_explicit_artist:
            # 명시적 아티스트가 있으면 장르 fallback은 최대 2개만 추가
            _extend(genre_candidates[:max(0, max_count - len(candidates))])
        else:
            _extend(genre_candidates)

    if len(candidates) < max_count:
        _extend(_era_fallbacks(conversation or []))

    # 명시적 아티스트가 있을 때는 기본 fallback 아티스트를 추가하지 않음
    if len(candidates) < max_count and not has_explicit_artist:
        if DEFAULT_FALLBACK_ARTISTS:
            _extend(DEFAULT_FALLBACK_ARTISTS)

    # 명시적 아티스트가 있을 때는 min_count를 1로 낮춤 (fallback 최소화)
    effective_min_count = 1 if has_explicit_artist else min_count
    
    if len(candidates) < effective_min_count:
        for pool in (genre_candidates, DEFAULT_FALLBACK_ARTISTS or []):
            for name in pool:
                cleaned = str(name).strip()
                if not cleaned:
                    continue
                lowered = cleaned.lower()
                if lowered in seen_lower:
                    continue
                seen_lower.add(lowered)
                candidates.append(cleaned)
                if len(candidates) >= effective_min_count:
                    break
            if len(candidates) >= effective_min_count:
                break

    if len(candidates) > max_count:
        return candidates[:max_count]
    return candidates
