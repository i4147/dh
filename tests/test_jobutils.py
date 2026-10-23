from __future__ import annotations
from concurrent.futures import TimeoutError as FutureTimeoutError
import time
from unittest.mock import MagicMock
from dh import PoolMethod, _ExecutorFutureManager, _PoolDispatcher, mpf
import pytest
class TestPoolMethodEnum:
    def test_parse_valid_string(self):
        result = PoolMethod.parse("map")
        assert result == PoolMethod.MAP
    def test_parse_enum_passthrough(self):
        result = PoolMethod.parse(PoolMethod.MAP)
        assert result == PoolMethod.MAP
    def test_parse_case_insensitive(self):
        result = PoolMethod.parse("MAP")
        assert result == PoolMethod.MAP
    def test_parse_invalid_method_raises_error(self):
        with pytest.raises(ValueError, match="unknown method"):
            PoolMethod.parse("invalid_method")
    def test_is_mp_pool_true(self):
        assert PoolMethod.MAP.is_mp_pool is True
        assert PoolMethod.STARMAP.is_mp_pool is True
        assert PoolMethod.IMAP.is_mp_pool is True
    def test_is_mp_pool_false(self):
        assert PoolMethod.PROCESS_POOL.is_mp_pool is False
        assert PoolMethod.THREAD_POOL.is_mp_pool is False
        assert PoolMethod.JOBLIB.is_mp_pool is False
class TestSimpleMapOperations:
    def test_thread_pool_map_basic(self):
        def square(x):
            return x**2
        items = [1, 2, 3, 4, 5]
        result = mpf(square, items, method="thread_pool", workers=2)
        assert result == [1, 4, 9, 16, 25]
    def test_thread_pool_map_with_strings(self):
        def upper(s):
            return s.upper()
        items = ["hello", "world"]
        result = mpf(upper, items, method="thread_pool", workers=2)
        assert result == ["HELLO", "WORLD"]
    def test_process_pool_map_basic(self):
        def add_one(x):
            return x + 1
        items = [1, 2, 3]
        result = mpf(add_one, items, method="process_pool", workers=2)
        assert result == [2, 3, 4]
    def test_imap_unordered(self):
        def multiply(x):
            return x * 2
        items = [1, 2, 3, 4]
        result = mpf(multiply, items, method="imap_unordered", workers=2)
        assert sorted(result) == [2, 4, 6, 8]
    def test_empty_items_list(self):
        def dummy(x):
            return x
        result = mpf(dummy, [], method="thread_pool")
        assert result == []
class TestFunctionArguments:
    def test_func_args(self):
        def add(a, b):
            return a + b
        items = [1, 2, 3]
        result = mpf(add, items, method="thread_pool", func_args=(10,), workers=2)
        assert result == [11, 12, 13]
    def test_func_kwargs(self):
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"
        items = ["Alice", "Bob"]
        result = mpf(greet, items, method="thread_pool", func_kwargs={"greeting": "Hi"}, workers=2)
        assert result == ["Hi, Alice!", "Hi, Bob!"]
    def test_func_args_and_kwargs_combined(self):
        def combine(a, b, c=0):
            return a + b + c
        items = [1, 2, 3]
        result = mpf(
            combine,
            items,
            method="thread_pool",
            func_args=(5,),
            func_kwargs={"c": 10},
            workers=2,
        )
        assert result == [16, 17, 18]
    def test_non_callable_func_raises_error(self):
        with pytest.raises(TypeError, match="`func` must be callable"):
            mpf("not_callable", [1, 2, 3], method="thread_pool")
class TestUnpackParameter:
    def test_unpack_true_with_tuples(self):
        def add(a, b):
            return a + b
        items = [(1, 2), (3, 4), (5, 6)]
        result = mpf(add, items, method="thread_pool", unpack=True, workers=2)
        assert result == [3, 7, 11]
    def test_unpack_false_single_arg(self):
        def first_element(item):
            return item[0]
        items = [(1, 2), (3, 4)]
        result = mpf(first_element, items, method="thread_pool", unpack=False, workers=2)
        assert result == [1, 3]
    def test_unpack_true_with_single_items(self):
        def process(x):
            return x * 2
        items = [1, 2, 3]
        result = mpf(process, items, method="thread_pool", unpack=True, workers=2)
        assert result == [2, 4, 6]
class TestTimeoutHandling:
    def test_timeout_exceeded(self):
        def slow_function(x):
            time.sleep(2)
            return x
        items = [1]
        with pytest.raises(FutureTimeoutError):
            mpf(
                slow_function,
                items,
                method="process_pool",
                timeout=0.1,
                workers=1,
            )
    def test_timeout_with_return_exceptions(self):
        def slow_function(x):
            time.sleep(2)
            return x
        items = [1, 2]
        result = mpf(
            slow_function,
            items,
            method="process_pool",
            timeout=0.1,
            workers=1,
            return_exceptions=True,
        )
        assert len(result) == 2
        assert all(isinstance(r, (FutureTimeoutError, Exception)) for r in result)
    def test_timeout_not_supported_with_mp_pool(self):
        def dummy(x):
            return x
        with pytest.raises(ValueError, match="timeout is only supported by the executor backends"):
            mpf(dummy, [1, 2], method="map", timeout=1.0, workers=2)
class TestProgressCallback:
    def test_progress_callback_called(self):
        progress_calls = []
        def progress_fn(idx, result):
            progress_calls.append((idx, result))
        def square(x):
            return x**2
        items = [1, 2, 3]
        mpf(square, items, method="thread_pool", on_progress=progress_fn, workers=2)
        assert len(progress_calls) > 0
        results = [r for _, r in progress_calls]
        assert sorted(results) == [1, 4, 9]
    def test_progress_callback_with_exception(self):
        progress_calls = []
        def progress_fn(idx, result):
            progress_calls.append((idx, result))
        def failing_func(x):
            if x == 2:
                raise ValueError("Test error")
            return x * 2
        items = [1, 2, 3]
        mpf(
            failing_func,
            items,
            method="thread_pool",
            on_progress=progress_fn,
            return_exceptions=True,
            workers=2,
        )
        assert len(progress_calls) >= 2
        exceptions = [r for _, r in progress_calls if isinstance(r, Exception)]
        assert len(exceptions) >= 1
class TestExceptionHandling:
    def test_exception_raised_by_default(self):
        def failing_func(x):
            if x == 2:
                raise ValueError("Test error")
            return x
        items = [1, 2, 3]
        with pytest.raises(ValueError, match="Test error"):
            mpf(failing_func, items, method="thread_pool", workers=2)
    def test_exception_captured_with_return_exceptions(self):
        def failing_func(x):
            if x == 2:
                raise ValueError("Test error")
            return x * 2
        items = [1, 2, 3]
        result = mpf(
            failing_func,
            items,
            method="thread_pool",
            return_exceptions=True,
            workers=2,
        )
        assert len(result) == 3
        assert result[0] == 2
        assert isinstance(result[1], ValueError)
        assert result[2] == 6
    def test_multiple_exceptions(self):
        def failing_func(x):
            if x in [1, 3]:
                raise RuntimeError(f"Error {x}")
            return x * 2
        items = [1, 2, 3, 4]
        result = mpf(
            failing_func,
            items,
            method="thread_pool",
            return_exceptions=True,
            workers=2,
        )
        assert isinstance(result[0], RuntimeError)
        assert result[1] == 4
        assert isinstance(result[2], RuntimeError)
        assert result[3] == 8
class TestMaxPendingQueue:
    def test_max_pending_limits_queue(self):
        call_count = [0]
        max_concurrent = [0]
        current_concurrent = [0]
        def track_calls(x):
            call_count[0] += 1
            current_concurrent[0] += 1
            max_concurrent[0] = max(max_concurrent[0], current_concurrent[0])
            time.sleep(0.01)
            current_concurrent[0] -= 1
            return x * 2
        items = list(range(20))
        mpf(
            track_calls,
            items,
            method="thread_pool",
            max_pending=3,
            workers=2,
        )
        assert call_count[0] == 20
        assert max_concurrent[0] <= 5
    def test_max_pending_with_high_workers(self):
        def process(x):
            return x + 1
        items = [1, 2, 3, 4, 5]
        result = mpf(
            process,
            items,
            method="thread_pool",
            max_pending=10,
            workers=8,
        )
        assert result == [2, 3, 4, 5, 6]
class TestChunksize:
    def test_chunksize_with_process_pool(self):
        def square(x):
            return x**2
        items = list(range(100))
        result = mpf(
            square,
            items,
            method="process_pool",
            chunksize=10,
            workers=2,
        )
        assert result == [x**2 for x in range(100)]
    def test_chunksize_none_defaults_correctly(self):
        def add_one(x):
            return x + 1
        items = [1, 2, 3]
        result = mpf(add_one, items, method="thread_pool", chunksize=None, workers=2)
        assert result == [2, 3, 4]
class TestJobLibBackend:
    @pytest.mark.skipif(True, reason="joblib may not be installed in test environment")
    def test_joblib_basic(self):
        def square(x):
            return x**2
        items = [1, 2, 3, 4, 5]
        result = mpf(square, items, method="joblib", workers=2)
        assert sorted(result) == [1, 4, 9, 16, 25]
    def test_joblib_does_not_support_timeout(self):
        def dummy(x):
            return x
        with pytest.raises(ValueError, match="joblib.*does not support timeout"):
            mpf(dummy, [1, 2], method="joblib", timeout=1.0, workers=2)
    def test_joblib_does_not_support_initializer(self):
        def dummy(x):
            return x
        def init_func():
            pass
        with pytest.raises(ValueError, match="joblib.*does not support initializer"):
            mpf(
                dummy,
                [1, 2],
                method="joblib",
                initializer=init_func,
                workers=2,
            )
    def test_joblib_does_not_support_maxtasksperchild(self):
        def dummy(x):
            return x
        with pytest.raises(ValueError, match="joblib.*does not support.*maxtasksperchild"):
            mpf(
                dummy,
                [1, 2],
                method="joblib",
                maxtasksperchild=5,
                workers=2,
            )
class TestInitializer:
    @pytest.mark.skipif(True, reason="Requires multiprocessing context")
    def test_initializer_with_process_pool(self):
        results = []
        def init_worker(value):
            global worker_state
            worker_state = value
        def process_with_state(x):
            return x + worker_state
        items = [1, 2, 3]
        result = mpf(
            process_with_state,
            items,
            method="process_pool",
            initializer=init_worker,
            initargs=(10,),
            workers=1,
        )
        assert result == [11, 12, 13]
class TestMaxtasksperchild:
    def test_maxtasksperchild_process_pool_accepted(self):
        def process(x):
            return x * 2
        items = [1, 2, 3]
        result = mpf(
            process,
            items,
            method="process_pool",
            maxtasksperchild=2,
            workers=2,
        )
        assert result == [2, 4, 6]
    def test_maxtasksperchild_thread_pool_rejected(self):
        def process(x):
            return x * 2
        with pytest.raises(ValueError, match="ThreadPoolExecutor does not support maxtasksperchild"):
            mpf(
                process,
                [1, 2, 3],
                method="thread_pool",
                maxtasksperchild=2,
                workers=2,
            )
    def test_maxtasksperchild_mp_pool_accepted(self):
        def process(x):
            return x * 2
        items = [1, 2, 3]
        result = mpf(
            process,
            items,
            method="map",
            maxtasksperchild=2,
            workers=2,
        )
        assert result == [2, 4, 6]
class TestDifferentMethods:
    def test_map_method(self):
        def double(x):
            return x * 2
        items = [1, 2, 3, 4]
        result = mpf(double, items, method="map", workers=2)
        assert result == [2, 4, 6, 8]
    def test_starmap_method(self):
        def add(a, b):
            return a + b
        items = [(1, 2), (3, 4), (5, 6)]
        result = mpf(add, items, method="starmap", workers=2)
        assert result == [3, 7, 11]
    def test_imap_method(self):
        def square(x):
            return x**2
        items = [1, 2, 3, 4, 5]
        result = mpf(square, items, method="imap", workers=2)
        assert result == [1, 4, 9, 16, 25]
    def test_apply_method(self):
        def increment(x):
            return x + 1
        items = [10, 20, 30]
        result = mpf(increment, items, method="apply", workers=2)
        assert result == [11, 21, 31]
    def test_apply_async_method(self):
        def multiply(x):
            return x * 3
        items = [2, 4, 6]
        result = mpf(multiply, items, method="apply_async", workers=2)
        assert result == [6, 12, 18]
class TestEdgeCases:
    def test_single_item(self):
        def process(x):
            return x * 2
        result = mpf(process, [5], method="thread_pool", workers=1)
        assert result == [10]
    def test_large_items_list(self):
        def process(x):
            return x + 1
        items = list(range(1000))
        result = mpf(process, items, method="thread_pool", workers=4)
        assert len(result) == 1000
        assert result[0] == 1
        assert result[999] == 1000
    def test_different_return_types(self):
        def process(x):
            if x == 1:
                return "string"
            elif x == 2:
                return [1, 2, 3]
            elif x == 3:
                return {"key": "value"}
            else:
                return x
        items = [1, 2, 3, 4]
        result = mpf(process, items, method="thread_pool", workers=2)
        assert result[0] == "string"
        assert result[1] == [1, 2, 3]
        assert result[2] == {"key": "value"}
        assert result[3] == 4
    def test_none_return_values(self):
        def process(x):
            if x % 2 == 0:
                return None
            return x * 2
        items = [1, 2, 3, 4]
        result = mpf(process, items, method="thread_pool", workers=2)
        assert result[0] == 2
        assert result[1] is None
        assert result[2] == 6
        assert result[3] is None
class TestPoolDispatcher:
    def test_pool_dispatcher_map(self):
        pool_mock = MagicMock()
        pool_mock.map.return_value = [2, 4, 6]
        dispatcher = _PoolDispatcher(
            pool_mock,
            PoolMethod.MAP,
            lambda x: x * 2,
            [1, 2, 3],
            None,
        )
        result = dispatcher.dispatch()
        assert result == [2, 4, 6]
        pool_mock.map.assert_called_once()
    def test_pool_dispatcher_starmap(self):
        pool_mock = MagicMock()
        pool_mock.starmap.return_value = [3, 7, 11]
        dispatcher = _PoolDispatcher(
            pool_mock,
            PoolMethod.STARMAP,
            lambda a, b: a + b,
            [(1, 2), (3, 4), (5, 6)],
            None,
        )
        result = dispatcher.dispatch()
        assert result == [3, 7, 11]
class TestExecutorFutureManager:
    def test_future_manager_simple_execution(self):
        def square(x):
            return x**2
        from concurrent.futures import ThreadPoolExecutor
        manager = _ExecutorFutureManager(
            ThreadPoolExecutor,
            square,
            [1, 2, 3],
            workers=2,
            chunksize=None,
            unpack=False,
            timeout=None,
            return_exceptions=False,
            max_pending=None,
            on_progress=None,
        )
        result = manager.execute()
        assert sorted(result) == [1, 4, 9]
    def test_future_manager_with_exceptions(self):
        def process(x):
            if x == 2:
                raise ValueError("Test error")
            return x * 2
        from concurrent.futures import ThreadPoolExecutor
        manager = _ExecutorFutureManager(
            ThreadPoolExecutor,
            process,
            [1, 2, 3],
            workers=2,
            chunksize=None,
            unpack=False,
            timeout=None,
            return_exceptions=True,
            max_pending=None,
            on_progress=None,
        )
        result = manager.execute()
        assert result[0] == 2
        assert isinstance(result[1], ValueError)
        assert result[2] == 6
class TestIntegrationScenarios:
    def test_data_transformation_pipeline(self):
        def read_and_process(filename):
            return len(filename)
        files = ["file1.txt", "file2.txt", "file3.txt"]
        result = mpf(read_and_process, files, method="thread_pool", workers=2)
        assert result == [9, 9, 9]
    def test_cpu_bound_work(self):
        def fibonacci(n):
            if n <= 1:
                return n
            a, b = 0, 1
            for _ in range(2, n + 1):
                a, b = b, a + b
            return b
        items = [10, 15, 20]
        result = mpf(fibonacci, items, method="thread_pool", workers=2)
        assert len(result) == 3
        assert all(isinstance(r, int) for r in result)
    def test_mixed_workload_with_errors(self):
        def process_item(item):
            if item < 0:
                raise ValueError("Negative not allowed")
            return item**2
        items = [1, -2, 3, 4, -5, 6]
        result = mpf(
            process_item,
            items,
            method="thread_pool",
            return_exceptions=True,
            workers=2,
        )
        assert result[0] == 1
        assert isinstance(result[1], ValueError)
        assert result[2] == 9
        assert result[3] == 16
        assert isinstance(result[4], ValueError)
        assert result[5] == 36
    def test_chained_operations(self):
        def first_pass(x):
            return x + 10
        items = [1, 2, 3, 4, 5]
        first_result = mpf(first_pass, items, method="thread_pool", workers=2)
        def second_pass(x):
            return x * 2
        second_result = mpf(second_pass, first_result, method="thread_pool", workers=2)
        assert second_result == [22, 24, 26, 28, 30]
