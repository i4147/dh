"""Text utility contracts and edge cases."""

from collections import Counter
from itertools import product

import pytest
import dh
from dh import textutils
from dh.textutils import (
    count_words,
    levenshtein,
    text_distance,
    to_camel,
    to_snake,
    word_frequencies,
)


@pytest.mark.parametrize(
    "left,right,expected",
    [
        ("", "", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("kitten", "sitting", 3),
        ("same", "same", 0),
        ("a", "A", 1),
        ("ab", "ba", 2),
        ("café", "cafe", 1),
        ("🐈", "🐕", 1),
        ("a" * 100, "a", 99),
    ],
)
def test_levenshtein(left: str, right: str, expected: int) -> None:
    assert levenshtein(left, right) == expected
    assert levenshtein(right, left) == expected


def test_distance_contract() -> None:
    assert text_distance("", "") == 0.0
    assert text_distance("", "abc") == 1.0
    assert text_distance("kitten", "sitting") == pytest.approx(3 / 7)
    strings = ["", "a", "b", "aa", "ab", "ba", "bb"]
    for left, right in product(strings, repeat=2):
        distance = levenshtein(left, right)
        assert abs(len(left) - len(right)) <= distance <= max(len(left), len(right))
        assert 0 <= text_distance(left, right) <= 1
        for middle in strings:
            assert distance <= levenshtein(left, middle) + levenshtein(middle, right)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", 0),
        (" \n\t---🙂", 0),
        ("hello, world!", 2),
        ("Don't stop; don’t worry.", 4),
        ("one_two-three 123", 4),
        ("café cafe\u0301", 2),
        ("سلام دنیا", 2),
        ("你好世界", 1),
    ],
)
def test_count_words(text: str, expected: int) -> None:
    assert count_words(text) == expected
    assert sum(word_frequencies(text).values()) == expected


def test_word_frequencies() -> None:
    assert word_frequencies("") == Counter()
    counts = word_frequencies("Straße STRASSE café cafe\u0301 don't don’t")
    assert counts == Counter({"strasse": 2, "café": 2, "don't": 2})
    assert counts["missing"] == 0
    assert word_frequencies("Hi hi HI", case_sensitive=True) == Counter({"Hi": 1, "hi": 1, "HI": 1})


@pytest.mark.parametrize(
    "text,snake,camel,pascal",
    [
        ("", "", "", ""),
        ("--- ___", "", "", ""),
        ("hello world", "hello_world", "helloWorld", "HelloWorld"),
        ("helloWorld", "hello_world", "helloWorld", "HelloWorld"),
        ("HTTPServer", "http_server", "httpServer", "HttpServer"),
        ("XMLHttpRequest", "xml_http_request", "xmlHttpRequest", "XmlHttpRequest"),
        ("already_snake", "already_snake", "alreadySnake", "AlreadySnake"),
        ("version2HTTPServer", "version_2_http_server", "version2HttpServer", "Version2HttpServer"),
        ("café déjà_vu", "café_déjà_vu", "caféDéjàVu", "CaféDéjàVu"),
        ("ÉcoleÜber", "école_über", "écoleÜber", "ÉcoleÜber"),
        ("HELLO-WORLD", "hello_world", "helloWorld", "HelloWorld"),
    ],
)
def test_case_conversion(text: str, snake: str, camel: str, pascal: str) -> None:
    assert to_snake(text) == snake
    assert to_snake(snake) == snake
    assert to_camel(text) == camel
    assert to_camel(text, upper_first=True) == pascal


def test_package_exports() -> None:
    for name in textutils.__all__:
        assert getattr(dh, name) is getattr(textutils, name)
        assert name in dh.__all__
