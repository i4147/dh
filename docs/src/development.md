# Development

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,parallel]'
pytest -q
ty check
mdbook build docs
```

The book is compatible with mdBook 0.4.x. If Rust's `cargo` is available, install
it with `cargo install mdbook --version 0.4.40 --locked`. The sandbox build used
mdBook 0.4.4, distributed in the `cargo-mdbook@0.4.4` npm package. The unrelated
npm package named `mdbook` is not the Rust documentation generator.

Built HTML is included in `docs/html/index.html`; open that file locally or serve
`docs/html` with any static HTTP server. Rebuild it after changing book sources.

The API reference lists public function signatures and docstrings. Regenerate it
with `python tools/build_api_docs.py` before building the book.

Tests cover traversal filters, compatibility exports, custom skip directories,
root handling, hidden files/symlinks, scandir pruning and errors, subprocess
cleanup, timeouts, failure codes, validation, URL handling, hashing, and thread
execution, extension-classification invariants, and corrected constants.
