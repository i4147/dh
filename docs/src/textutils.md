# Text utilities

`dh.textutils` offers dependency-free text helpers, also exported from `dh`.

```python
from dh import (
    levenshtein, text_distance, count_words,
    to_camel, to_snake, word_frequencies,
)

assert levenshtein("kitten", "sitting") == 3
assert text_distance("kitten", "sitting") == 3 / 7
assert count_words("Don't stop, keep going!") == 4
assert to_snake("HTTPServer") == "http_server"
assert to_camel("hello_world") == "helloWorld"
assert to_camel("hello_world", upper_first=True) == "HelloWorld"
assert word_frequencies("Hello hello world").most_common(1) == [("hello", 2)]
```

## Distance

`levenshtein(left, right)` returns the minimum number of unit-cost insertions,
deletions, and substitutions. It is case-sensitive, with no implicit Unicode
normalization. It operates on Unicode code points, not grapheme clusters, and
transpositions cost two edits. Time is O(m × n); auxiliary memory is O(min(m, n)).

`text_distance` divides that distance by the longer input length, producing a
number between zero (identical) and one (maximally different). Two empty strings
have distance zero. It is not a similarity score; use `1 - text_distance(a, b)`
if a normalized similarity is desired. This length-normalized score does not
necessarily obey the triangle inequality; raw Levenshtein distance does.

## Words and frequencies

`count_words` counts Unicode letter/number runs, preserving internal straight or
curly apostrophes in contractions. Numbers count as words; underscores, hyphens,
and other punctuation separate words. Input is NFC-normalized before splitting.
This is a lexical heuristic: it does not perform language-specific segmentation,
so an unspaced Chinese sentence counts as one token.

`word_frequencies` returns `collections.Counter[str]` using the same tokens. By
default Unicode `casefold()` merges variants such as `Straße` and `STRASSE`.
Use `case_sensitive=True` to preserve case. Curly apostrophes normalize to straight
ones in either mode. Missing words have count zero; `most_common()` provides ranked
counts. Empty input returns an empty Counter.

## Case conversion

`to_snake` and `to_camel` split punctuation, whitespace, underscores, lower-to-upper
case transitions, acronym endings, and digit runs. Acronyms normalize to ordinary
word casing: `XMLHttpRequest` becomes `xml_http_request` or `xmlHttpRequest`.
`version2HTTPServer` becomes `version_2_http_server` or `version2HttpServer`.
Unicode letter casing is supported. `to_camel(..., upper_first=True)` produces
PascalCase instead of lowerCamelCase. Empty or punctuation-only input returns `""`.
These converters do not validate Python identifiers; leading numbers remain.
