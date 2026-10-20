`atomicio.py` is ready. I haven't run it, so test it on a scratch file before pointing it at your scripts.

**What it handles**
- **Payloads:** `bytes`, `str`, and anything else (dict, list, dataclass, set, Path, datetime) is serialized to JSON automatically. Use `as_json=True` to force JSON on a string.
- **Safety:** it writes a unique temp file in the same directory, fsyncs it, then does `os.replace`. It cleans up the temp file on failure, writes through symlinks, and creates parent directories.
- **Options:**
  - `encoding`, `errors`, `newline`
  - `mode=0o755`, `mode_from=other_file`, or the existing file's mode is preserved
  - `backup=True` (gives `.bak`) or `backup="path"`
  - `indent`, `sort_keys`, `ensure_ascii`
  - `skip_unchanged`, `lock`, `suppress_errors` (returns `False` instead of raising)
- **Legacy compatibility:** the optional third positional argument is dispatched by type:

| Old call | Third argument | Treated as |
|---|---|---|
| `write_atomic(path, data, backup)` | `bool` | backup |
| `atomic_write(path, data, mode)` | `int` | mode |
| `atomic_write(path, text, encoding)` | codec name | encoding |
| `write_atomic(target, data, mode_from)` | `Path` | copy mode |
| `atomic_save(path, data, lock)` | lock | held during write |
| `_atomic_write(path, data, original)` | `bytes` | ignored |

**Updating your scripts**

1. Put `atomicio.py` somewhere on your import path, e.g. `~/bin/lib/`, and add it to `PYTHONPATH` (for example `export PYTHONPATH="$HOME/bin/lib:$PYTHONPATH"` in your shell rc). Alternatively, put it next to the scripts.
2. In each script, delete the local `def` and add one import that matches the old name:
   ```python
   from atomicio import atomic_write            # or write_atomic / atomic_save / _atomic_write ...
   ```
   Aliases exist for `write_atomic`, `atomic_save`, `atomic_replace`, `atomic_write_text`, `atomic_write_json`, `atomic_write_file`, `_atomic_write` and `_atomic_save`. Existing calls keep working unchanged, so you can migrate one script at a time.
3. Where you serialize by hand, drop the manual step:
   ```python
   atomic_write(path, text)                       # str -> utf-8
   atomic_write(path, data_bytes, backup=True)    # bytes + .bak
   atomic_write(path, {"k": "v"})                 # dict -> pretty JSON (add indent=None for compact)
   atomic_write(path, translations, sort_keys=True, ensure_ascii=False)
   ```
4. Check these before swapping:
   - `fontpreview._atomic_write(text, dest)` has its arguments reversed (text first). Swap its call sites to `(dest, text)`.
   - If `tmc.py` and `rmc_termux.py` use `original` for something beyond ignoring it (for example comparing before writing), use `skip_unchanged=True` instead.
   - If `pyfmt.py` and `fontpreview.py` return a bool, `atomic_write` returns `True` on success. Pass `suppress_errors=True` if they relied on `False` 


   "''



------------------------------

I've updated `atomicio.py` with a fallback, and I simulated a failing `os.replace` to check it. I haven't run it on a real `/sdcard`, so that part is untested.

**What changed**
- **`fallback=True` (the default):** if the atomic write raises any `OSError` (`PermissionError` included), it retries as a plain write with `target.write_bytes(payload)`. That payload is already serialized, so bytes, text, JSON, `encoding`, `newline` and `indent` behave exactly as in the atomic path. On a simulated failure, a dict still came out as JSON and `\r\n` conversion still worked, and no stray temp files were left behind. Pass `fallback=False` if you want the error to be raised instead.
- **Permission tweaks are now best-effort:** `chmod`, `copymode` and fsync failures are ignored. On Termux `/sdcard` these are the likely culprits, so the write may now stay atomic there instead of falling back. If `os.replace` or the temp file is what's refused, the plain write takes over.
- **Backups:** if `copy2` can't copy the file metadata, it falls back to `copyfile`.
- **Fallback chmod:** an explicit `mode=` is applied after the plain write, but any failure is ignored.

**Caveat:** the fallback is not atomic. If Termux is killed mid-write, the file can end up truncated. If that matters, use `backup=True` for files you can't afford to lose.
