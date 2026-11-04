# dh utilities

dh provides typed filesystem helpers, terminal formatting, text processing, and
parallel task execution. Python 3.11 or newer is supported.

```sh
python -m pip install -e '.[dev,parallel]'
```

Rich and Loguru are installed as runtime dependencies. Joblib and tqdm are
optional: install the `parallel` extra when using those backends/progress bars.

```python
from dh import get_files, get_dirs

sources = get_files("src", ext=[".py"])
directories = list(get_dirs("src"))
```

Filesystem helpers are implemented in `dh.fileutils`. Existing imports from
`dh.pathutils` still work and refer to the same functions. The package root also
re-exports these helpers.

## Pure-Python traversal

All standard traversal helpers use a shared `os.scandir` engine in `fileutils`.
It uses cached `DirEntry` type metadata, prunes excluded subtrees before opening
them, and uses an explicit stack to avoid recursive Python calls. It needs no
native extensions and works on all supported Python versions.
