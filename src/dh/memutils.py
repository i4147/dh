"""
shoe memory usage of a function
usage:

@track_memory
def my_function():
    # your code
    pass

"""

import tracemalloc
from functools import wraps


def track_memory(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tracemalloc.start()
        result = func(*args, **kwargs)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"{func.__name__}: Peak {peak / 1024 / 1024:.2f} MB")
        return result

    return wrapper
