from __future__ import annotations
import bz2
import codecs
import contextlib
import csv
import dataclasses
from dataclasses import dataclass, field
import gzip
import io
import json
import lzma
import os
from pathlib import Path
import pickle
import secrets
import shutil
import time
from typing import TYPE_CHECKING, Any, Callable, ContextManager, Literal, Self


if TYPE_CHECKING:
    import logging
    pass
__all__ = [
    "DEFAULT_OPTIONS",
    "Options",
    "WriteResult",
    "atomic_read",
    "atomic_write",
    "atomic_write_bytes",
    "atomic_write_csv",
    "atomic_write_json",
    "atomic_write_pickle",
    "atomic_write_text",
    "atomic_write_toml",
    "atomic_write_yaml",
]
_RAW_TYPES: tuple[type, ...] = (bytes, bytearray, memoryview)
_FORMATS = ("json", "yaml", "toml", "pickle", "csv", "text", "bytes", "msgpack")
_COMPRESSIONS = ("gzip", "bz2", "lzma", "zstd")


class _Unset:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<UNSET>"


_UNSET: Any = _Unset()


@dataclass(frozen=True)
class Options:
    encoding: str = "utf-8"
    errors: str = "strict"
    newline: str | None = None
    as_json: bool | None = None
    indent: int | None = 2
    sort_keys: bool = False
    ensure_ascii: bool = False
    trailing_newline: bool = True
    format: Literal["json", "yaml", "toml", "pickle", "csv", "text", "bytes", "msgpack"] | None = None
    serializer: Callable[[Any], bytes] | None = None
    json_default: Callable[[Any], Any] | None = None
    json_kwargs: dict[str, Any] = field(default_factory=dict)
    bom: bool = False
    compression: Literal["gzip", "bz2", "lzma", "zstd"] | None = None
    compresslevel: int | None = None
    mode: int | None = None
    mode_from: str | os.PathLike[str] | None = None
    preserve_times: bool = False
    dir_mode: int | None = None
    backup: bool | str | os.PathLike[str] = False
    backup_suffix: str = ".bak"
    reflink: bool = False
    mkdir: bool = True
    fsync: bool = True
    fsync_dir: bool = True
    sync: Literal["fsync", "fdatasync", "none"] = "fsync"
    tmp_dir: str | os.PathLike[str] | None = None
    fallback: bool = True
    rollback_on_fallback_error: bool = True
    exclusive: bool = False
    keep_tmp_on_error: bool = False
    retry: int = 0
    retry_delay: float = 0.1
    update: Callable[[bytes | None], Any] | None = None
    skip_unchanged: bool = False
    follow_symlinks: bool = True
    lock: ContextManager[Any] | None = None
    lock_path: str | os.PathLike[str] | None = None
    lock_timeout: float | None = None
    validate: Callable[[Any], bool] | None = None
    pre_write_hook: Callable[[Any], Any] | None = None
    post_write_hook: Callable[[Path], None] | None = None
    verify: bool = False
    dry_run: bool = False
    logger: logging.Logger | None = None
    on_error: Callable[[BaseException], None] | None = None
    on_success: Callable[["WriteResult"], None] | None = None
    suppress_errors: bool = False


DEFAULT_OPTIONS = Options()
_OPT_KEYS: frozenset[str] = frozenset(f.name for f in dataclasses.fields(Options))


@dataclass
class WriteResult:
    path: Path
    bytes_written: int = 0
    written: bool = True
    skipped: bool = False
    dry_run: bool = False
    backup_path: Path | None = None
    tmp_path: Path | None = None
    elapsed: float = 0.0
    format: str | None = None
    failed: bool = False
    error: BaseException | None = None

    def __bool__(self) -> bool:
        return not self.failed


class _PathLock:
    def __init__(self, path: str | os.PathLike[str], timeout: float | None = None) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self._fh: Any = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+b")
        start = time.monotonic()
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if self.timeout is not None and (time.monotonic() - start) >= self.timeout:
                    self._fh.close()
                    self._fh = None
                    msg = f"Could not acquire lock on {self.path!r} within {self.timeout}s"
                    raise TimeoutError(msg) from None
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None


def _resolve_lock(opts: Options) -> ContextManager[Any]:
    if opts.lock is not None:
        return opts.lock
    if opts.lock_path is not None:
        return _PathLock(opts.lock_path, timeout=opts.lock_timeout)
    return contextlib.nullcontext()


def _json_default(o: Any) -> Any:
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    if isinstance(o, (set, frozenset)):
        return list(o)
    if isinstance(o, os.PathLike):
        return os.fspath(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    msg = f"Cannot serialize {type(o).__name__}"
    raise TypeError(msg)


def _make_json_default(user_default: Callable[[Any], Any] | None) -> Callable[[Any], Any]:
    if user_default is None:
        return _json_default

    def _composed(o: Any) -> Any:
        try:
            return user_default(o)
        except TypeError:
            return _json_default(o)

    return _composed


def _is_encoding(name: str) -> bool:
    try:
        codecs.lookup(name)
        return True
    except LookupError:
        return False


def _is_sig_encoding(name: str) -> bool:
    return name.lower().replace("_", "-").endswith("-sig")


def _encode(text: str, opts: Options) -> bytes:
    enc = opts.encoding
    if opts.bom and not _is_sig_encoding(enc):
        try:
            codecs.lookup(enc + "-sig")
        except LookupError:
            pass
        else:
            enc = enc + "-sig"
    return text.encode(enc, opts.errors)


def _apply_newline(text: str, newline: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline != "\n":
        text = text.replace("\n", newline)
    return text


def _serialize_via_format(data: Any, fmt: str, opts: Options) -> bytes:
    if fmt == "json":
        text = json.dumps(
            data,
            indent=opts.indent,
            sort_keys=opts.sort_keys,
            ensure_ascii=opts.ensure_ascii,
            default=_make_json_default(opts.json_default),
            **opts.json_kwargs,
        )
        if opts.trailing_newline:
            text += "\n"
        return _encode(text, opts)
    if fmt == "yaml":
        try:
            import yaml
        except ImportError as e:
            msg = "format='yaml' requires the `PyYAML` package"
            raise ImportError(msg) from e
        text = yaml.safe_dump(data, sort_keys=opts.sort_keys, allow_unicode=not opts.ensure_ascii)
        return _encode(text, opts)
    if fmt == "toml":
        try:
            import tomli_w
        except ImportError as e:
            msg = "format='toml' requires the `tomli_w` package"
            raise ImportError(msg) from e
        text = tomli_w.dumps(data)
        return _encode(text, opts)
    if fmt == "pickle":
        return pickle.dumps(data)
    if fmt == "csv":
        buf = io.StringIO()
        csv.writer(buf).writerows(data)
        text = buf.getvalue()
        if opts.newline is not None:
            text = _apply_newline(text, opts.newline)
        return _encode(text, opts)
    if fmt == "msgpack":
        try:
            import msgpack
        except ImportError as e:
            msg = "format='msgpack' requires the `msgpack` package"
            raise ImportError(msg) from e
        return msgpack.packb(data, use_bin_type=True)
    if fmt == "text":
        if not isinstance(data, str):
            msg = f"format='text' requires str, got {type(data).__name__}"
            raise TypeError(msg)
        text = data
        if opts.trailing_newline and not text.endswith(("\n", "\r")):
            text += "\n"
        if opts.newline is not None:
            text = _apply_newline(text, opts.newline)
        return _encode(text, opts)
    if fmt == "bytes":
        if not isinstance(data, _RAW_TYPES):
            msg = f"format='bytes' requires bytes-like, got {type(data).__name__}"
            raise TypeError(msg)
        return bytes(data)
    msg = f"Unknown format: {fmt!r}"
    raise ValueError(msg)


def _serialize_inner(data: Any, opts: Options) -> bytes:
    if opts.serializer is not None:
        payload = opts.serializer(data)
        if not isinstance(payload, _RAW_TYPES):
            msg = f"serializer must return bytes, got {type(payload).__name__}"
            raise TypeError(msg)
        return bytes(payload)
    fmt = opts.format
    if fmt is not None:
        return _serialize_via_format(data, fmt, opts)
    as_json = opts.as_json
    if as_json is None:
        as_json = not isinstance(data, _RAW_TYPES + (str,))
    if as_json:
        return _serialize_via_format(data, "json", opts)
    if isinstance(data, _RAW_TYPES):
        return bytes(data)
    if isinstance(data, str):
        text = data
        if opts.newline is not None:
            text = _apply_newline(text, opts.newline)
        return _encode(text, opts)
    msg = f"Cannot write {type(data).__name__} as text; use as_json=True or format="
    raise TypeError(msg)


def _compress(data: bytes, compression: str, level: int | None) -> bytes:
    if compression == "gzip":
        return gzip.compress(data, compresslevel=level if level is not None else 9)
    if compression == "bz2":
        return bz2.compress(data, compresslevel=level if level is not None else 9)
    if compression == "lzma":
        return lzma.compress(data, preset=level)
    if compression == "zstd":
        try:
            import zstandard
        except ImportError as e:
            msg = "compression='zstd' requires the `zstandard` package"
            raise ImportError(msg) from e
        return zstandard.ZstdCompressor(level=level if level is not None else 3).compress(data)
    msg = f"Unknown compression: {compression!r}"
    raise ValueError(msg)


def _decompress(data: bytes, compression: str) -> bytes:
    if compression == "gzip":
        return gzip.decompress(data)
    if compression == "bz2":
        return bz2.decompress(data)
    if compression == "lzma":
        return lzma.decompress(data)
    if compression == "zstd":
        try:
            import zstandard
        except ImportError as e:
            msg = "compression='zstd' requires the `zstandard` package"
            raise ImportError(msg) from e
        return zstandard.ZstdDecompressor().decompress(data)
    msg = f"Unknown compression: {compression!r}"
    raise ValueError(msg)


def _serialize(data: Any, opts: Options) -> bytes:
    result = _serialize_inner(data, opts)
    if opts.compression is not None:
        result = _compress(result, opts.compression, opts.compresslevel)
    return result


def _do_sync(fd: int, sync: str) -> None:
    if sync == "none":
        return
    with contextlib.suppress(OSError):
        if sync == "fdatasync" and hasattr(os, "fdatasync"):
            os.fdatasync(fd)
        else:
            os.fsync(fd)


def _fsync_dir(directory: Path) -> None:
    if os.name != "posix":
        return
    with contextlib.suppress(OSError):
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _reflink(src: Path, dst: Path) -> None:
    if os.name != "posix":
        msg = "reflink not supported on this platform"
        raise OSError(msg)
    import fcntl

    FICLONE = 0x40049409
    with open(src, "rb") as sf, open(dst, "wb") as df:
        fcntl.ioctl(df.fileno(), FICLONE, sf.fileno())


def _backup(src: Path, dst: Path, reflink: bool) -> None:
    if reflink:
        try:
            _reflink(src, dst)
            return
        except OSError:
            pass
    try:
        shutil.copy2(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def _retry_replace(tmp: Path, target: Path, opts: Options) -> None:
    attempts = max(1, opts.retry + 1)
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            if opts.exclusive:
                try:
                    os.link(tmp, target)
                except FileExistsError:
                    raise
                except OSError:
                    if target.exists():
                        raise FileExistsError(str(target)) from None
                    os.replace(tmp, target)
                    return
                else:
                    os.unlink(tmp)
                    return
            os.replace(tmp, target)
            return
        except OSError as e:
            last_exc = e
            if i + 1 < attempts:
                time.sleep(opts.retry_delay * (i + 1))
    if last_exc is not None:
        raise last_exc


def _replace_atomically(target: Path, payload: bytes, opts: Options, *, exists: bool) -> Path:
    parent = target.parent
    tmp_dir = Path(opts.tmp_dir) if opts.tmp_dir is not None else parent
    tmp = tmp_dir / f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(tmp, flags, 0o666)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            if opts.fsync:
                _do_sync(f.fileno(), opts.sync)
        with contextlib.suppress(OSError, NotImplementedError):
            if opts.mode is not None:
                os.chmod(tmp, opts.mode)
            elif opts.mode_from is not None and Path(opts.mode_from).exists():
                shutil.copymode(opts.mode_from, tmp)
            elif exists:
                shutil.copymode(target, tmp)
        if opts.preserve_times and exists:
            with contextlib.suppress(OSError):
                st = target.stat()
                os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
        _retry_replace(tmp, target, opts)
    except BaseException:
        if not opts.keep_tmp_on_error:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        raise
    if opts.fsync and opts.fsync_dir:
        _fsync_dir(parent)
    return tmp


def _resolve_options(opt: Any, kwargs: dict[str, Any]) -> Options:
    base = DEFAULT_OPTIONS
    overrides: dict[str, Any] = {}
    if opt is not None:
        if isinstance(opt, Options):
            base = opt
        elif isinstance(opt, bool):
            overrides["backup"] = opt
        elif isinstance(opt, int):
            overrides["mode"] = opt
        elif isinstance(opt, str):
            if _is_encoding(opt):
                overrides["encoding"] = opt
            else:
                overrides["mode_from"] = opt
        elif isinstance(opt, os.PathLike):
            overrides["mode_from"] = opt
        elif hasattr(opt, "__enter__") and hasattr(opt, "__exit__"):
            overrides["lock"] = opt
        else:
            msg = f"Unsupported opt value: {type(opt).__name__}"
            raise TypeError(msg)
    for k, v in kwargs.items():
        if k not in _OPT_KEYS:
            msg = f"Unknown option: {k!r}"
            raise TypeError(msg)
        overrides[k] = v
    if not overrides:
        return base
    return dataclasses.replace(base, **overrides)


def atomic_write(
    path: str | os.PathLike[str],
    data: Any = _UNSET,
    opt: Any = None,
    *,
    update: Callable[[bytes | None], Any] | None = None,
    **kwargs: Any,
) -> WriteResult:
    opts = _resolve_options(opt, kwargs)
    if update is not None:
        if opts.update is not None:
            msg = "Specify `update=` either as kwarg or inside Options, not both"
            raise TypeError(msg)
        opts = dataclasses.replace(opts, update=update)
    if opts.update is not None:
        if data is not _UNSET:
            msg = "Provide either `data` or `update=`, not both"
            raise TypeError(msg)
    elif data is _UNSET:
        msg_0 = "atomic_write() requires `data` or `update=`"
        raise TypeError(msg_0)
    target = Path(os.path.realpath(path)) if opts.follow_symlinks else Path(path)
    start = time.monotonic()
    result = WriteResult(path=target, dry_run=opts.dry_run, format=opts.format)
    try:
        lock_cm = _resolve_lock(opts)
        with lock_cm:
            exists = target.is_file()
            if opts.update is not None:
                old = target.read_bytes() if exists else None
                payload_data = opts.update(old)
            else:
                payload_data = data
            if opts.pre_write_hook is not None:
                payload_data = opts.pre_write_hook(payload_data)
            if opts.validate is not None and not opts.validate(payload_data):
                msg = "validate() returned False; refusing to write"
                raise ValueError(msg)
            payload = _serialize(payload_data, opts)
            result.bytes_written = len(payload)
            if opts.skip_unchanged and exists and not opts.dry_run:
                with contextlib.suppress(OSError):
                    if target.read_bytes() == payload:
                        result.written = False
                        result.skipped = True
                        result.elapsed = time.monotonic() - start
                        if opts.on_success is not None:
                            with contextlib.suppress(Exception):
                                opts.on_success(result)
                        return result
            if opts.exclusive and exists and not opts.dry_run:
                raise FileExistsError(str(target))
            if opts.dry_run:
                result.written = False
                result.elapsed = time.monotonic() - start
                if opts.on_success is not None:
                    with contextlib.suppress(Exception):
                        opts.on_success(result)
                return result
            if opts.mkdir:
                target.parent.mkdir(parents=True, exist_ok=True, mode=opts.dir_mode or 0o777)
            if opts.backup and exists:
                bak = target.with_name(target.name + opts.backup_suffix) if opts.backup is True else Path(opts.backup)
                _backup(target, bak, opts.reflink)
                result.backup_path = bak
            try:
                result.tmp_path = _replace_atomically(target, payload, opts, exists=exists)
            except OSError:
                if not opts.fallback:
                    raise
                try:
                    target.write_bytes(payload)
                    if opts.mode is not None:
                        with contextlib.suppress(OSError, NotImplementedError):
                            os.chmod(target, opts.mode)
                except OSError:
                    if opts.rollback_on_fallback_error and result.backup_path is not None:
                        with contextlib.suppress(OSError):
                            shutil.copy2(result.backup_path, target)
                    raise
            if opts.verify:
                written = target.read_bytes()
                if written != payload:
                    if result.backup_path is not None:
                        with contextlib.suppress(OSError):
                            shutil.copy2(result.backup_path, target)
                    msg = f"Verification failed for {target}: written bytes differ"
                    raise OSError(msg)
            if opts.post_write_hook is not None:
                with contextlib.suppress(Exception):
                    opts.post_write_hook(target)
            result.written = True
            result.elapsed = time.monotonic() - start
            if opts.on_success is not None:
                with contextlib.suppress(Exception):
                    opts.on_success(result)
            if opts.logger is not None:
                opts.logger.debug("atomic_write: wrote %d bytes to %s", len(payload), target)
            return result
    except OSError as e:
        result.failed = True
        result.error = e
        result.elapsed = time.monotonic() - start
        if opts.on_error is not None:
            with contextlib.suppress(Exception):
                opts.on_error(e)
        if opts.logger is not None:
            opts.logger.debug("atomic_write: OSError for %s: %s", target, e)
        if opts.suppress_errors:
            return result
        raise
    except BaseException as e:
        if opts.on_error is not None:
            with contextlib.suppress(Exception):
                opts.on_error(e)
        raise


def atomic_read(
    path: str | os.PathLike[str],
    *,
    format: Literal["json", "yaml", "toml", "pickle", "csv", "text", "bytes", "msgpack"] | None = None,
    compression: Literal["gzip", "bz2", "lzma", "zstd"] | None = None,
    encoding: str = "utf-8",
    errors: str = "strict",
    deserializer: Callable[[bytes], Any] | None = None,
) -> Any:
    raw = Path(path).read_bytes()
    if compression is not None:
        raw = _decompress(raw, compression)
    if deserializer is not None:
        return deserializer(raw)
    if format is None or format == "bytes":
        return raw
    if format == "text":
        return raw.decode(encoding, errors)
    if format == "json":
        return json.loads(raw.decode(encoding, errors))
    if format == "yaml":
        try:
            import yaml
        except ImportError as e:
            msg = "format='yaml' requires the `PyYAML` package"
            raise ImportError(msg) from e
        return yaml.safe_load(raw.decode(encoding, errors))
    if format == "toml":
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        return tomllib.loads(raw.decode(encoding, errors))
    if format == "pickle":
        return pickle.loads(raw)
    if format == "msgpack":
        try:
            import msgpack
        except ImportError as e:
            msg = "format='msgpack' requires the `msgpack` package"
            raise ImportError(msg) from e
        return msgpack.unpackb(raw, raw=False)
    if format == "csv":
        text = raw.decode(encoding, errors)
        return list(csv.reader(io.StringIO(text)))
    msg = f"Unknown format: {format!r}"
    raise ValueError(msg)


def atomic_write_text(path: str | os.PathLike[str], text: str, **kwargs: Any) -> WriteResult:
    kwargs.setdefault("format", "text")
    return atomic_write(path, text, **kwargs)


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes, **kwargs: Any) -> WriteResult:
    kwargs.setdefault("format", "bytes")
    return atomic_write(path, data, **kwargs)


def atomic_write_json(path: str | os.PathLike[str], obj: Any, **kwargs: Any) -> WriteResult:
    kwargs.setdefault("format", "json")
    return atomic_write(path, obj, **kwargs)


def atomic_write_yaml(path: str | os.PathLike[str], obj: Any, **kwargs: Any) -> WriteResult:
    kwargs.setdefault("format", "yaml")
    return atomic_write(path, obj, **kwargs)


def atomic_write_toml(path: str | os.PathLike[str], obj: Any, **kwargs: Any) -> WriteResult:
    kwargs.setdefault("format", "toml")
    return atomic_write(path, obj, **kwargs)


def atomic_write_pickle(path: str | os.PathLike[str], obj: Any, **kwargs: Any) -> WriteResult:
    kwargs.setdefault("format", "pickle")
    return atomic_write(path, obj, **kwargs)


def atomic_write_csv(path: str | os.PathLike[str], rows: Any, **kwargs: Any) -> WriteResult:
    kwargs.setdefault("format", "csv")
    return atomic_write(path, rows, **kwargs)
