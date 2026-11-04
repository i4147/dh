# Filesystem traversal

```python
from pathlib import Path
from dh.fileutils import get_files, get_filez, get_dirs

rst_files = get_files(Path("docs"), ext=[".rst"], skip_dirs={"vendor"})
for script in get_filez("src", pyfiles=True, nobinary=True):
    print(script)

dirs = get_files("src", dirs_only=True)
assert dirs == sorted(get_dirs("src"))
```

## Filtering contract

- `get_files` returns a sorted `list[Path]`; `get_filez` returns an iterator.
- `ext=None` and `ext=[]` disable suffix filtering. Leading dots are optional,
  matching is case-insensitive, and compound suffixes such as `.tar.gz` work.
- Filters combine: `ext=[".py"], pyfiles=True` requires both conditions.
- `pyfiles=True` accepts `.py` files (including empty files) and extensionless
  files whose first line is a Python shebang. It does not parse arbitrary text.
- `nobinary=True` uses the package's extension/content-based binary classifier.
- `skip_dirs=None` uses `dh.const.SKIP_DIRS`; a custom set replaces this set.
  Entries below matching directory components are excluded as well.
- `dirs_only=True` ignores all file filters and includes the root directory,
  `get_dirs` delegates to this mode.
- Hidden children, symlinks, and bytecode caches are omitted by the walker.
  Use `skip_dirs=set()` to include non-hidden cache/build directories.
- A single file root can be filtered too. Missing roots and traversal errors
  raise `OSError` subclasses. Results remain relative if the input is relative.

The shared `os.scandir` engine is lazy: `get_filez` filters entries as they are
visited without collecting the entire tree. Directory exclusions prune work
before descent. Only one directory handle is open at a time; file-type checks use
cached `DirEntry` metadata rather than additional `Path.stat` calls. An explicit
stack avoids Python recursion limits. Directory mode can yield a directory before
its children are visited; `get_files` sorts its final results.

## Compatibility

`dh.pathutils` is a compatibility import layer, not a second implementation.
`get_pyfiles` and `get_nobinary` delegate to the same filtering engine.
Older helpers such as `getfiles`, `walkfiles`, `get_files_scandir`, and configurable
walkers share this engine while retaining their specialized filtering/error semantics;
use `get_files` for the new
unified filtering interface.
