from __future__ import annotations
from concurrent.futures import TimeoutError as FutureTimeout
import inspect
import os
from pathlib import Path
import sys
import threading
import time

import jobutils
from jobutils import MAX_WORKERS, PoolMethod, mpf, mpf_iter
import pytest


MP_METHODS = ["map", "map_async", "starmap", "starmap_async", "imap", "imap_unordered", "apply", "apply_async"]
ORDERED_METHODS = [m for m in MP_METHODS if m != "imap_unordered"]
EXECUTOR_METHODS = ["process_pool", "thread_pool"]
ALL_METHODS = MP_METHODS + EXECUTOR_METHODS + ["serial"]

_G: dict[str, object] = {}
_LOCK = threading.Lock()
_CONC = {"cur": 0, "max": 0}


def _square(x):
    return x * x


def _add(a, b):
    return a + b


def _affine(a, x, b=0):
    return a * x + b


def _inv(x):
    return 1 / x


def _sleep_ret(x):
    time.sleep(x)
    return x


def _pid(_):
    return os.getpid()


def _flaky(directory, x):
    marker = Path(directory) / str(x)
    if not marker.exists():
        marker.write_text("seen")
        raise RuntimeError(f"first attempt for {x}")
    return x * 2


def _init(value):
    _G["value"] = value


def _read_init(_):
    return _G.get("value")


def _track(x):
    with _LOCK:
        _CONC["cur"] += 1
        _CONC["max"] = max(_CONC["max"], _CONC["cur"])
    time.sleep(0.02)
    with _LOCK:
        _CONC["cur"] -= 1
    return x


class _Collector:
    def __init__(self):
        self.calls: list[tuple[int, object]] = []

    def __call__(self, idx, value):
        self.calls.append((idx, value))


def test_parse_accepts_strings_and_members():
    assert PoolMethod.parse("map") is PoolMethod.MAP
    assert PoolMethod.parse("IMAP_Unordered") is PoolMethod.IMAP_UNORDERED
    assert PoolMethod.parse("  thread-pool ") is PoolMethod.THREAD_POOL
    assert PoolMethod.parse(PoolMethod.SERIAL) is PoolMethod.SERIAL


def test_parse_rejects_unknown():
    with pytest.raises(ValueError, match="unknown method"):
        PoolMethod.parse("nope")


def test_is_mp_pool_flags():
    for m in MP_METHODS:
        assert PoolMethod(m).is_mp_pool
    for m in ["joblib", "process_pool", "thread_pool", "serial"]:
        assert not PoolMethod(m).is_mp_pool


def test_pool_method_is_str_enum():
    assert PoolMethod.MAP == "map"
    assert str(PoolMethod.MAP.value) == "map"


def test_resolve_workers():
    cpus = os.cpu_count() or 1
    assert jobutils._resolve_workers(64, 3) == 3
    assert jobutils._resolve_workers(4, None) == 4
    assert jobutils._resolve_workers(0, None) == cpus
    assert jobutils._resolve_workers(None, None) == cpus
    assert jobutils._resolve_workers(-3, 1000) == min(cpus, 1000)
    assert jobutils._resolve_workers(4, 0) == 1


def test_resolve_chunksize():
    assert jobutils._resolve_chunksize(None, 100, 4) is None
    assert jobutils._resolve_chunksize(5, 100, 4) == 5
    assert jobutils._resolve_chunksize(0, 160, 4) == 10
    assert jobutils._resolve_chunksize(0, None, 4) == 1
    assert jobutils._resolve_chunksize(0, 1, 8) == 1


@pytest.mark.parametrize("method", ALL_METHODS)
def test_basic_results(method):
    got = mpf(_square, range(20), method, workers=3)
    assert sorted(got) == [i * i for i in range(20)]


@pytest.mark.parametrize("method", ORDERED_METHODS + EXECUTOR_METHODS + ["serial"])
def test_order_preserved(method):
    assert mpf(_square, list(range(25)), method, workers=3) == [i * i for i in range(25)]


def test_default_method_is_imap_unordered():
    assert sorted(mpf(_square, range(10), workers=2)) == [i * i for i in range(10)]
    assert inspect.signature(mpf).parameters["method"].default is PoolMethod.IMAP_UNORDERED


def test_ordered_flag_for_imap_unordered():
    items = list(range(40))
    assert mpf(_square, items, "imap_unordered", workers=4, chunksize=1, ordered=True) == [i * i for i in items]


@pytest.mark.parametrize("method", ["starmap", "starmap_async"])
def test_starmap_tuples(method):
    assert mpf(_add, [(1, 2), (3, 4), (5, 6)], method, workers=2) == [3, 7, 11]


@pytest.mark.parametrize("method", ["starmap", "starmap_async"])
def test_starmap_wraps_scalars(method):
    assert mpf(_square, [2, 3, 4], method, workers=2) == [4, 9, 16]


@pytest.mark.parametrize("method", ["map", "imap", "apply", "process_pool", "thread_pool", "serial"])
def test_unpack_true(method):
    assert mpf(_add, [(1, 2), (3, 4)], method, workers=2, unpack=True) == [3, 7]


def test_unpack_with_mixed_scalars():
    assert mpf(_square, [2, 3], "thread_pool", unpack=True) == [4, 9]


@pytest.mark.parametrize("method", ["map", "imap", "process_pool", "thread_pool", "serial"])
def test_func_args_and_kwargs(method):
    got = mpf(_affine, [1, 2, 3], method, workers=2, func_args=(10,), func_kwargs={"b": 1})
    assert got == [11, 21, 31]


@pytest.mark.parametrize("method", ALL_METHODS)
def test_empty_input(method):
    assert mpf(_square, [], method) == []


@pytest.mark.parametrize("method", ["imap", "map", "process_pool", "thread_pool", "serial"])
def test_generator_input(method):
    gen = (i for i in range(12))
    assert mpf(_square, gen, method, workers=2) == [i * i for i in range(12)]


@pytest.mark.parametrize("method", ["imap", "process_pool", "thread_pool"])
def test_single_item_and_oversized_worker_count(method):
    assert mpf(_square, [7], method, workers=64) == [49]
    assert mpf(_square, [1, 2, 3], method, workers=64) == [1, 4, 9]


def test_bad_arguments():
    with pytest.raises(TypeError):
        mpf("not callable", [1])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown method"):
        mpf(_square, [1], "bogus")
    with pytest.raises(ValueError):
        mpf(_square, [1], "serial", retries=-1)
    with pytest.raises(ValueError):
        mpf(_square, [1], "thread_pool", timeout=0)
    with pytest.raises(ValueError):
        mpf(_square, [1], "thread_pool", timeout=-1)


@pytest.mark.parametrize("method", MP_METHODS)
def test_timeout_rejected_for_mp_pool(method):
    with pytest.raises(ValueError, match="timeout"):
        mpf(_square, [1], method, timeout=1.0)


def test_timeout_rejected_for_serial_and_joblib():
    with pytest.raises(ValueError):
        mpf(_square, [1], "serial", timeout=1.0)
    with pytest.raises(ValueError):
        mpf(_square, [1], "joblib", timeout=1.0)


def test_unsupported_option_combinations():
    with pytest.raises(ValueError, match="maxtasksperchild"):
        mpf(_square, [1], "thread_pool", maxtasksperchild=1)
    with pytest.raises(ValueError):
        mpf(_square, [1], "joblib", initializer=_init, initargs=(1,))
    with pytest.raises(ValueError):
        mpf(_square, [1], "joblib", maxtasksperchild=1)


@pytest.mark.parametrize("method", ALL_METHODS)
def test_exceptions_propagate(method):
    with pytest.raises(ZeroDivisionError):
        mpf(_inv, [1, 0, 2], method, workers=2)


@pytest.mark.parametrize("method", ORDERED_METHODS + EXECUTOR_METHODS + ["serial"])
def test_return_exceptions_keeps_positions(method):
    got = mpf(_inv, [1, 0, 2], method, workers=2, return_exceptions=True)
    assert got[0] == 1.0 and got[2] == 0.5
    assert isinstance(got[1], ZeroDivisionError)


def test_return_exceptions_with_ordered_unordered_pool():
    got = mpf(_inv, [1, 0, 2, 0], "imap_unordered", workers=2, chunksize=1, ordered=True, return_exceptions=True)
    assert [isinstance(g, ZeroDivisionError) for g in got] == [False, True, False, True]


def test_return_exceptions_unordered_counts():
    got = mpf(_inv, [1, 0, 2, 0], "imap_unordered", workers=2, return_exceptions=True)
    assert sum(isinstance(g, ZeroDivisionError) for g in got) == 2


@pytest.mark.parametrize("method", ["thread_pool", "process_pool"])
def test_return_exceptions_with_progress_path(method):
    cb = _Collector()
    got = mpf(_inv, [1, 0, 2], method, workers=2, return_exceptions=True, on_progress=cb)
    assert isinstance(got[1], ZeroDivisionError)
    assert sorted(i for i, _ in cb.calls) == [0, 1, 2]


@pytest.mark.parametrize("method", ["thread_pool", "process_pool", "serial", "imap", "map", "apply_async"])
def test_on_progress_reports_every_result(method):
    cb = _Collector()
    got = mpf(_square, list(range(9)), method, workers=3, on_progress=cb)
    assert got == [i * i for i in range(9)]
    assert sorted(cb.calls) == [(i, i * i) for i in range(9)]


def test_on_progress_indices_for_imap_unordered_are_input_indices():
    cb = _Collector()
    got = mpf(_square, list(range(15)), "imap_unordered", workers=3, chunksize=1, on_progress=cb)
    assert sorted(cb.calls) == [(i, i * i) for i in range(15)]
    assert sorted(got) == [i * i for i in range(15)]


def test_slow_path_preserves_input_order():
    items = [0.3, 0.0, 0.1]
    assert mpf(_sleep_ret, items, "thread_pool", workers=3, on_progress=lambda i, v: None) == items


def test_timeout_thread_pool_return_exceptions():
    got = mpf(_sleep_ret, [0.0, 1.0], "thread_pool", workers=2, timeout=0.3, return_exceptions=True)
    assert got[0] == 0.0
    assert isinstance(got[1], FutureTimeout)


def test_timeout_thread_pool_fail_fast_raises():
    t0 = time.monotonic()
    with pytest.raises(FutureTimeout):
        mpf(_sleep_ret, [0.0, 1.0], "thread_pool", workers=2, timeout=0.3)
    assert time.monotonic() - t0 < 0.9


def test_timeout_without_expiry_returns_normally():
    assert mpf(_square, list(range(8)), "thread_pool", workers=2, timeout=5.0) == [i * i for i in range(8)]


def test_timeout_kills_hung_process_workers():
    t0 = time.monotonic()
    got = mpf(_sleep_ret, [0.0, 30.0], "process_pool", workers=2, timeout=0.7, return_exceptions=True)
    assert got[0] == 0.0 and isinstance(got[1], FutureTimeout)
    assert time.monotonic() - t0 < 15


def test_timeout_does_not_count_queue_time():
    items = [0.2] * 6
    got = mpf(_sleep_ret, items, "thread_pool", workers=2, timeout=0.6)
    assert got == items


def test_fail_fast_false_runs_everything_then_raises_first_error():
    cb = _Collector()
    with pytest.raises(ZeroDivisionError):
        mpf(_inv, [1, 0, 2, 0], "thread_pool", workers=2, on_progress=cb, fail_fast=False)
    assert len(cb.calls) == 4


def test_fail_fast_true_stops_early():
    with pytest.raises(ZeroDivisionError):
        mpf(_inv, [0] + [1] * 50, "thread_pool", workers=1, on_progress=lambda i, v: None, max_pending=1)


def test_max_pending_limits_concurrency():
    _CONC.update(cur=0, max=0)
    got = mpf(_track, list(range(16)), "thread_pool", workers=6, max_pending=2)
    assert got == list(range(16))
    assert _CONC["max"] <= 2


def test_max_pending_validates_to_at_least_one():
    assert mpf(_square, [1, 2, 3], "thread_pool", workers=2, max_pending=0) == [1, 4, 9]


@pytest.mark.parametrize("method", ["serial", "thread_pool", "process_pool", "map", "imap"])
def test_retries_recover_from_transient_failures(method, tmp_path):
    got = mpf(_flaky, list(range(6)), method, workers=2, func_args=(str(tmp_path),), retries=1)
    assert got == [i * 2 for i in range(6)]


@pytest.mark.parametrize("method", ["serial", "thread_pool", "map"])
def test_without_retries_transient_failure_surfaces(method, tmp_path):
    with pytest.raises(RuntimeError, match="first attempt"):
        mpf(_flaky, [1, 2], method, workers=2, func_args=(str(tmp_path),))


def test_retries_exhausted_reraises():
    with pytest.raises(ZeroDivisionError):
        mpf(_inv, [0], "serial", retries=2)


def test_retry_delay_backs_off(tmp_path):
    t0 = time.monotonic()
    assert mpf(_flaky, [1], "serial", func_args=(str(tmp_path),), retries=1, retry_delay=0.2) == [2]
    assert time.monotonic() - t0 >= 0.18


def test_retry_wrapper_counts_attempts():
    calls = []

    def always_fail():
        calls.append(1)
        raise ValueError

    with pytest.raises(ValueError):
        jobutils._Retry(always_fail, 3, 0.0)()
    assert len(calls) == 4


@pytest.mark.parametrize("method", ["serial", "thread_pool", "process_pool", "imap", "map"])
def test_initializer_runs(method):
    got = mpf(_read_init, [0, 1, 2, 3], method, workers=2, initializer=_init, initargs=("ready",))
    assert got == ["ready"] * 4


def test_maxtasksperchild_pool_recycles_workers():
    pids = mpf(_pid, list(range(6)), "imap_unordered", workers=2, chunksize=1, maxtasksperchild=1)
    assert len(set(pids)) == 6


@pytest.mark.skipif(sys.version_info < (3, 11), reason="max_tasks_per_child needs 3.11+")
def test_maxtasksperchild_process_pool():
    pids = mpf(_pid, list(range(4)), "process_pool", workers=2, chunksize=1, maxtasksperchild=1)
    assert len(set(pids)) == 4


def test_spawn_context():
    assert mpf(_square, list(range(8)), "imap", workers=2, context="spawn") == [i * i for i in range(8)]


def test_process_pool_with_context():
    assert mpf(_square, list(range(6)), "process_pool", workers=2, context="spawn") == [i * i for i in range(6)]


@pytest.mark.parametrize("method", ["map", "map_async", "imap", "imap_unordered", "process_pool"])
def test_chunksize_variants(method):
    for chunksize in (None, 0, 1, 7, 1000):
        got = mpf(_square, list(range(30)), method, workers=3, chunksize=chunksize)
        assert sorted(got) == [i * i for i in range(30)]


def test_workers_zero_uses_cpu_count():
    assert mpf(_square, [1, 2, 3], "imap", workers=0) == [1, 4, 9]


def test_joblib_backend():
    pytest.importorskip("joblib")
    assert mpf(_square, list(range(10)), "joblib", workers=2) == [i * i for i in range(10)]
    assert mpf(_add, [(1, 2), (3, 4)], "joblib", workers=2, unpack=True) == [3, 7]
    got = mpf(_inv, [1, 0], "joblib", workers=2, return_exceptions=True)
    assert got[0] == 1.0 and isinstance(got[1], ZeroDivisionError)
    cb = _Collector()
    mpf(_square, [1, 2], "joblib", workers=1, on_progress=cb)
    assert cb.calls == [(0, 1), (1, 4)]


def test_serial_runs_in_process_and_lazily_consumes():
    pids = mpf(_pid, [0, 1], "serial")
    assert set(pids) == {os.getpid()}


def test_wrapper_classes():
    assert jobutils._Star(_add)((1, 2)) == 3
    assert jobutils._Star(_square)(3) == 9
    assert jobutils._Indexed(_square)((5, 4)) == (5, 16)
    caught = jobutils._Catch(_inv)(0)
    assert isinstance(caught, ZeroDivisionError)
    assert jobutils._Catch(_inv)(2) == 0.5


def test_wrappers_are_picklable():
    import pickle

    for obj in (
        jobutils._Star(_add),
        jobutils._Retry(_square, 2, 0.1),
        jobutils._Catch(_square),
        jobutils._Indexed(_square),
    ):
        clone = pickle.loads(pickle.dumps(obj))
        assert type(clone) is type(obj)


def test_mpf_iter_ordered():
    assert list(mpf_iter(_square, range(15), workers=3)) == [i * i for i in range(15)]


def test_mpf_iter_unordered():
    got = list(mpf_iter(_square, range(15), workers=3, ordered=False, chunksize=1))
    assert sorted(got) == [i * i for i in range(15)]


def test_mpf_iter_is_lazy_generator():
    gen = mpf_iter(_square, range(5), workers=2)
    assert inspect.isgenerator(gen)
    assert next(gen) == 0
    gen.close()


def test_mpf_iter_empty_and_options(tmp_path):
    assert list(mpf_iter(_square, [])) == []
    got = list(mpf_iter(_flaky, [1, 2], workers=2, func_args=(str(tmp_path),), retries=1))
    assert got == [2, 4]
    assert list(mpf_iter(_add, [(1, 2), (3, 4)], unpack=True, workers=2)) == [3, 7]
    caught = list(mpf_iter(_inv, [1, 0], workers=1, return_exceptions=True))
    assert caught[0] == 1.0 and isinstance(caught[1], ZeroDivisionError)


def test_mpf_iter_initializer():
    assert list(mpf_iter(_read_init, [0, 1], workers=2, initializer=_init, initargs=(5,))) == [5, 5]


def test_mpf_iter_validation():
    with pytest.raises(TypeError):
        list(mpf_iter(None, [1]))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        list(mpf_iter(_square, [1], retries=-1))


def test_public_api_surface():
    assert MAX_WORKERS == 8
    assert jobutils.DEFAULT_CHUNKSIZE == 4
    assert jobutils.DEFAULT_EXECUTOR_CHUNKSIZE == 1
    for name in jobutils.__all__:
        assert hasattr(jobutils, name)
    params = inspect.signature(mpf).parameters
    for name in (
        "workers",
        "chunksize",
        "unpack",
        "func_args",
        "func_kwargs",
        "initializer",
        "initargs",
        "maxtasksperchild",
        "context",
        "timeout",
        "return_exceptions",
        "max_pending",
        "on_progress",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
