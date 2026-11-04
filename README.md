# dh

Typed Python utilities for filesystem traversal, command execution, terminal text,
and parallel processing. Requires Python 3.11+.

```sh
python -m pip install -e '.[dev,parallel]'
```

```python
from dh import get_files, get_dirs, runcmd

rst_files = get_files("docs", ext=[".rst"])
directories = list(get_dirs("src"))
code, stdout, stderr = runcmd(["git", "status", "--short"], show_output=False)
```

`dh.fileutils` contains the shared filesystem implementation. Existing
`dh.pathutils` imports remain supported. `get_files(..., dirs_only=True)` unifies
directory traversal; suffix, Python-source, binary, and directory exclusion filters
work together. Traversal uses one shared pure-Python `os.scandir` engine, with
excluded directory trees pruned before descent. No native extension is required.

## Text helpers

```python
from dh import levenshtein, text_distance, count_words, to_camel, to_snake, word_frequencies

assert levenshtein("kitten", "sitting") == 3
assert to_snake("HTTPServer") == "http_server"
assert to_camel("hello_world") == "helloWorld"
assert count_words("Hello, world!") == 2
assert word_frequencies("Hi hi")["hi"] == 2
```

See [text utilities](docs/src/textutils.md) for distance and tokenization contracts.

## Tests and types

```sh
pytest -q
ty check
```

## Documentation

Read [the book sources](docs/src/index.md) or open
[`docs/html/index.html`](docs/html/index.html) for built HTML.

```sh
python tools/build_api_docs.py
mdbook build docs
```

See [development instructions](docs/src/development.md) for mdBook installation
and [traversal contracts](docs/src/traversal.md) for filtering details.
