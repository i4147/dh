from __future__ import annotations
import string
from collections import Counter
from functools import lru_cache
from math import sqrt as math_sqrt
from re import IGNORECASE as re_IGNORECASE
from re import UNICODE as re_UNICODE
from re import compile as re_compile
from typing import Sequence, Union
from dh import is_binary
from pathlib import Path

_WORD_RE = re_compile(r"\b[\w']+\b", re_UNICODE)
_SENTENCE_RE = re_compile(r"(?<=[.!?])\s+")
_MULTISPACE_RE = re_compile(r"\s+")
_URL_RE = re_compile(r"https?://\S+|www\.\S+", re_IGNORECASE)
_HTML_RE = re_compile(r"<[^>]+>")
_EMOJI_RE = re_compile(
    r"[\U0001f300-\U0001f5ff\U0001f600-\U0001f64f\U0001f680-\U0001f6ff\U0001f700-\U0001f77f\U0001f780-\U0001f7ff\U0001f800-\U0001f8ff\U0001f900-\U0001f9ff\U0001fa00-\U0001fa6f\U0001fa70-\U0001faff\U00002702-\U000027b0\U000024c2-\U0001f251]+",
    flags=re_UNICODE,
)
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "he",
    "her",
    "his",
    "i",
    "in",
    "is",
    "it",
    "its",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "she",
    "that",
    "the",
    "their",
    "them",
    "there",
    "they",
    "this",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
    "you",
    "your",
    "yours",
    "am",
    "not",
    "no",
    "do",
    "does",
    "did",
    "done",
    "if",
    "then",
    "than",
    "too",
    "very",
}
POSITIVE_WORDS = {
    "good",
    "great",
    "awesome",
    "excellent",
    "amazing",
    "love",
    "like",
    "happy",
    "nice",
    "best",
    "fantastic",
    "wonderful",
    "perfect",
    "cool",
    "pleased",
    "enjoy",
    "satisfied",
    "brilliant",
    "super",
}
NEGATIVE_WORDS = {
    "bad",
    "terrible",
    "awful",
    "poor",
    "hate",
    "dislike",
    "sad",
    "worst",
    "horrible",
    "broken",
    "annoying",
    "disappointed",
    "angry",
    "upset",
    "buggy",
    "useless",
    "problem",
    "issue",
}
EMOJI_POSITIVE = {
    "😀",
    "😁",
    "😂",
    "🤣",
    "😊",
    "😍",
    "😘",
    "😄",
    "🙂",
    "😉",
    "😎",
    "👍",
    "🙌",
    "🥳",
    "❤️",
    "💙",
    "💚",
    "🔥",
}
EMOJI_NEGATIVE = {"😢", "😭", "😞", "😔", "😡", "🤬", "👎", "💔", "😣", "😫", "☹️", "🙁"}


def clean_text(text: str, keep_emoji: bool = True) -> str:
    if not text:
        return ""
    text = _HTML_RE.sub(SPACE, text)
    text = _URL_RE.sub(SPACE, text)
    if not keep_emoji:
        text = _EMOJI_RE.sub(SPACE, text)
    text = text.lower()
    text = _MULTISPACE_RE.sub(SPACE, text).strip()
    return text


def remove_stop_words(tokens: Sequence[str], stop_words: set[str] = STOP_WORDS) -> list[str]:
    return [t for t in tokens if t not in stop_words]


def get_sentences(text: str) -> list[str]:
    """
    Simple sentence splitter.
    """
    if not text:
        return []
    text = text.strip()
    parts = _SENTENCE_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def tokenize(text: str) -> list[str]:
    """
    Alias for get_words(text).
    """
    return get_words(text)


def sentiment_score(text: str) -> float:
    """
    Returns a score in [-1, 1] approximately:
    positive > 0, negative < 0.
    """
    if not text:
        return 0.0
    tokens = get_words(text)
    if not tokens:
        return 0.0
    score = 0.0
    for t in tokens:
        if t in POSITIVE_WORDS:
            score += 1.0
        elif t in NEGATIVE_WORDS:
            score -= 1.0
        elif t in EMOJI_POSITIVE:
            score += 1.0
        elif t in EMOJI_NEGATIVE:
            score -= 1.0
    return max(-1.0, min(1.0, score / max(1.0, math_sqrt(len(tokens)))))


def sentiment_label(text: str, positive_threshold: float = 0.15, negative_threshold: float = -0.15) -> str:
    s = sentiment_score(text)
    if s >= positive_threshold:
        return "positive"
    if s <= negative_threshold:
        return "negative"
    return "neutral"


def jaccard_similarity(a: Union[str, Sequence[str]], b: Union[str, Sequence[str]]) -> float:
    ta = set(get_words(a) if isinstance(a, str) else a)
    tb = set(get_words(b) if isinstance(b, str) else b)
    if not ta and (not tb):
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def cosine_similarity(a: Union[str, Sequence[str]], b: Union[str, Sequence[str]]) -> float:
    ta = get_words(a) if isinstance(a, str) else list(a)
    tb = get_words(b) if isinstance(b, str) else list(b)
    ca = Counter(ta)
    cb = Counter(tb)
    if not ca or not cb:
        return 0.0
    common = set(ca) & set(cb)
    dot = sum((ca[t] * cb[t] for t in common))
    norm_a = math_sqrt(sum((v * v for v in ca.values())))
    norm_b = math_sqrt(sum((v * v for v in cb.values())))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@lru_cache(maxsize=4096)
def levenshtein_distance(a: str, b: str) -> int:
    """
    Memory-efficient Levenshtein distance.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = (b, a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            ins = current[j - 1] + 1
            dele = previous[j] + 1
            sub = previous[j - 1] + (ca != cb)
            current.append(min(ins, dele, sub))
        previous = current
    return previous[-1]


def levenshtein_similarity(a: str, b: str) -> float:
    if not a and (not b):
        return 1.0
    dist = levenshtein_distance(a, b)
    return 1.0 - dist / max(len(a), len(b), 1)


def jaro_winkler_similarity(s1: str, s2: str, prefix_scale: float = 0.1) -> float:
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    len1, len2 = (len(s1), len(s2))
    match_distance = max(len1, len2) // 2 - 1
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2
    m = matches
    jaro = (m / len1 + m / len2 + (m - transpositions) / m) / 3.0
    prefix = 0
    for c1, c2 in zip(s1, s2):
        if c1 == c2:
            prefix += 1
        else:
            break
        if prefix == 4:
            break
    return jaro + prefix * prefix_scale * (1.0 - jaro)


def partial_ratio(a: str, b: str) -> float:
    """
    Fuzzy similarity between 0 and 1 based on best matching substring.
    """
    if not a and (not b):
        return 1.0
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = (b, a)
    best = 0.0
    la = len(a)
    for i in range(0, len(b) - la + 1):
        sub = b[i : i + la]
        sim = levenshtein_similarity(a, sub)
        if sim > best:
            best = sim
            if best == 1.0:
                break
    return best * 100


LOWER = set(string.ascii_lowercase)
UPPER = set(string.ascii_uppercase)
DIGIT = set(string.digits)
ALPHA = set(list(LOWER) + list(UPPER))
SPACE = set([" "])


def is_digit(txt, ps: bool = False):
    if ps:
        dps = set(list(DIGIT) + list(SPACE))
    else:
        dps = DIGIT
    for k in range(len(txt) - 1):
        if not txt[k] in dps:
            return False
    del dps
    return True


def is_alphanum(txt, ps: bool = False):
    if ps:
        dps = set(list(ALPHA) + list(DIGIT) + list(SPACE))
    else:
        dps = set(list(ALPHA) + list(DIGIT))
    for k in range(len(txt) - 1):
        if not txt[k] in dps:
            return False
    del dps
    return True


def is_alpha(txt, ps: bool = False):
    if ps:
        dps = set(list(ALPHA) + list(SPACE))
    else:
        dps = ALPHA
    for k in range(len(txt) - 1):
        if not txt[k] in dps:
            return False
    del dps
    return True


def is_lower(txt, ps: bool = False):
    if ps:
        dps = set(list(LOWER) + list(SPACE))
    else:
        dps = LOWER
    for k in range(len(txt) - 1):
        if not txt[k] in dps:
            return False
    del dps
    return True


def is_upper(txt, ps: bool = False):
    if ps:
        dps = set(list(UPPER) + list(SPACE))
    else:
        dps = UPPER
    for k in range(len(txt) - 1):
        if not txt[k] in dps:
            return False
    del dps
    return True


def is_none_english(path: str | Path) -> bool:
    from string import printable

    path = Path(path)
    try:
        if not path.is_file():
            return False
        if is_binary(path):
            return False
        content = path.read_text(encoding="utf-8")
        english_chars = set(printable + "!@#$%^&*()-'::;,?+×÷=/_€£¥₩")
        return any((char not in english_chars and (not char.isspace()) for char in content))
    except Exception:
        return False


def count_words(path: str | Path) -> dict:
    from collections import Counter
    from string import punctuation

    path = Path(path)
    if is_binary(path):
        return {}
    text = path.read_text(encoding="utf-8")
    if text:
        text = str(" ".join(list(text)))
        text = text.lower()
        for p in punctuation:
            text = text.replace(p, "")
        words = text.split()
        return Counter(words)
    return {}


def get_words(text: str) -> list[str]:
    from re import finditer as re_finditer

    if not text:
        return []
    text = clean_text(text, keep_emoji=True)
    words = _WORD_RE.findall(text)
    emojis = _EMOJI_RE.findall(text)
    if not emojis:
        return words
    tokens = []
    i = 0
    for m in re_finditer(r"\b[\w']+\b|[\U000024C2-\U0001FAFF\u2702-\u27B0]+", text, re_UNICODE):
        tokens.append(m.group(0))
        i += 1
    return tokens if tokens else words
