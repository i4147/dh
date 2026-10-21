# refactored fileutils.py

**Key rewrite improvements:**

1. **Class-based design patterns**: Extracted complex logic into dedicated classes:
   - `_FileReader`: Handles file reading with mmap fallback
   - `_ExtensionAnalyzer`: Encapsulates extension parsing logic
   - `_FileAgeCalculator`: Time calculation with string formatting
   - `_CommandRunner`: Command execution with error handling
   - `_DirectoryCopier`/`_DirectoryMover`: Parallel directory operations
   - `_ConfigurableFileWalker`: Pattern-based file traversal

2. **Cleaner separation of concerns**: Each class has single responsibility

3. **Helper methods**: Broke down complex methods into discrete steps (_organize_by_category, _export_text, etc.)

4. **Consistent patterns**: Uniform error handling, validation, and initialization across classes

5. **Maintained API compatibility**: All public functions preserve original signatures
# refactored jobutils.py

**Key rewrite decisions:**

1. **Class-based organization**: Replaced functional decomposition with two main state-managing classes:
   - `_PoolDispatcher` encapsulates multiprocessing pool method dispatch logic
   - `_ExecutorFutureManager` handles concurrent.futures future orchestration with timeout, progress, and queue management

2. **Cleaner flow**: Each method handler (`_handle_mp_pool_method`, `_handle_joblib_method`) validates constraints early, reducing nested conditionals in `mpf()`

3. **Future management**: Extracted timeout calculation and timeout handling into discrete methods (`_calculate_wait_time`, `_handle_timeouts`) for readability

4. **Reduced complexity**: Consolidated the simple executor path detection into a boolean flag for clarity

5. **Type safety**: Preserved all type hints and maintained API compatibility
