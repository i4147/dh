# Other utilities

## Text and hashing

`get_sha256(path)` streams a file into a SHA-256 digest. `has_doc(code)` detects
Python comments or docstrings. `is_valid_url` accepts plausible HTTP/HTTPS URLs
and rejects missing input. `slugify` creates ASCII slugs; `tokenize_text` splits
identifiers into words and numeric tokens. `cube_rgb` expects an xterm color-cube
index in the inclusive range 16–231.

## Terminal formatting

`colored` returns styled text; `cprint` prints it. Both accept foreground,
background, and style attributes. Explicit overrides and terminal environment
settings determine whether ANSI color sequences are emitted.

## Parallel execution

```python
from dh import Method, mpf, values, failures

outcomes = mpf(abs, [-2, -1, 0], method=Method.THREAD, progress=None)
assert values(outcomes) == [2, 1, 0]
assert failures(outcomes) == []
```

Outcomes contain input indexes, items, results, and error information. Thread
execution supports non-picklable callables; process backends require picklable
functions and inputs. Put process-based calls behind an `if __name__ == "__main__"`
guard. Interpreter pools require Python 3.14+; unavailable methods raise
`MethodUnavailableError`. Python 3.11 uses equivalent `TypeVar`/`Generic` type
syntax, without requiring newer parser features.

For file-specific multiprocessing, `process_files` yields `(path, result)` pairs;
worker exceptions become `ERROR:` strings. `FileWalkerConfig` supports depth,
hidden-file, pattern, and symlink controls for the legacy configurable walker.
