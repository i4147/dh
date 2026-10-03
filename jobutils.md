# refactored jobutils.py

**Key rewrite decisions:**

1. **Class-based organization**: Replaced functional decomposition with two main state-managing classes:
   - `_PoolDispatcher` encapsulates multiprocessing pool method dispatch logic
   - `_ExecutorFutureManager` handles concurrent.futures future orchestration with timeout, progress, and queue management

2. **Cleaner flow**: Each method handler (`_handle_mp_pool_method`, `_handle_joblib_method`) validates constraints early, reducing nested conditionals in `mpf()`

3. **Future management**: Extracted timeout calculation and timeout handling into discrete methods (`_calculate_wait_time`, `_handle_timeouts`) for readability

4. **Reduced complexity**: Consolidated the simple executor path detection into a boolean flag for clarity

5. **Type safety**: Preserved all type hints and maintained API compatibility
