"""Dependency-free word counting, identifier conversion, and edit distance."""

from collections import Counter
from collections.abc import Iterator
import re
import unicodedata

__all__ = [
    "count_words",
    "levenshtein",
    "text_distance",
    "to_camel",
    "to_snake",
    "word_frequencies",
]

# Unicode letters and numbers, excluding underscores. Internal apostrophes keep
# contractions together; other punctuation and whitespace separate words.
_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


def _words(text: str) -> Iterator[str]:
    """Yield NFC-normalized words without allocating a complete token list."""
    for match in _WORD_RE.finditer(unicodedata.normalize("NFC", text)):
        yield match.group()


def levenshtein(left: str, right: str) -> int:
    """Return unit-cost insertion/deletion/substitution distance between strings.

    Comparisons are case-sensitive and operate on Unicode code points, not
    grapheme clusters. No normalization is implicit. Uses O(min(m, n)) memory
    and O(m*n) time; transpositions count as two edits.
    """
    if left == right:
        return 0
    # Keep the dynamic-programming row on the shorter input.
    if len(left) < len(right):
        left, right = right, left
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, 1):
        current = [i]
        for j, char_right in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (char_left != char_right)))
        previous = current
    return previous[-1]


def text_distance(left: str, right: str) -> float:
    """Return Levenshtein distance divided by the longer string length.

    The result lies in [0, 1]: zero means identical and one means maximally
    different. Two empty strings have distance zero. Case and Unicode behavior
    are the same as levenshtein; this is a distance, not a similarity score.
    """
    length = max(len(left), len(right))
    return levenshtein(left, right) / length if length else 0.0


def count_words(text: str) -> int:
    """Count Unicode letter/number words, keeping internal apostrophes together.

    Underscores, hyphens, and punctuation separate words. Numbers count as
    words. This is a lexical heuristic, not language-specific segmentation
    (e.g. an unspaced Chinese sentence is a single token).
    """
    return sum(1 for _ in _words(text))


def word_frequencies(text: str, *, case_sensitive: bool = False) -> Counter[str]:
    """Count words using count_words tokenization and optional case sensitivity.

    By default Unicode casefold merges case variants. Tokens use NFC Unicode
    normalization and curly apostrophes are canonicalized to straight ones.
    Return a Counter, supporting most_common() and zero for missing words.
    """
    return Counter(
        word.replace("’", "'") if case_sensitive else word.replace("’", "'").casefold() for word in _words(text)
    )


def _identifier_words(text: str) -> Iterator[str]:
    """Split separators, case boundaries, acronym endings, and digit runs."""
    for match in re.finditer(r"[^\W_]+", unicodedata.normalize("NFC", text)):
        token = match.group()
        start = 0
        for index in range(1, len(token)):
            previous, current = token[index - 1], token[index]
            following = token[index + 1] if index + 1 < len(token) else ""
            boundary = (
                current.isdecimal() != previous.isdecimal()
                or (current.isupper() and previous.islower())
                or (previous.isupper() and current.isupper() and following.islower())
            )
            if boundary:
                yield token[start:index]
                start = index
        yield token[start:]


def to_snake(text: str) -> str:
    """Convert words or identifiers to lowercase snake_case.

    Handles acronyms (HTTPServer -> http_server), Unicode case boundaries,
    punctuation separators, and digit runs (version2 -> version_2). Empty or
    punctuation-only input returns an empty string. No identifier validity is
    guaranteed (e.g. a leading number is retained).
    """
    return "_".join(word.lower() for word in _identifier_words(text))


def to_camel(text: str, *, upper_first: bool = False) -> str:
    """Convert words or identifiers to lowerCamelCase, or PascalCase if requested.

    Uses to_snake boundary rules and normalizes acronyms (HTTPServer becomes
    httpServer). Empty or punctuation-only input returns an empty string.
    """
    words = iter(_identifier_words(text))
    first = next(words, "")
    first = first.capitalize() if upper_first else first.lower()
    return first + "".join(word.capitalize() for word in words)
