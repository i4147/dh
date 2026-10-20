from __future__ import annotations

import argparse
import atexit
import contextlib
import datetime as dt
import functools
import glob
import inspect
import itertools
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import types
from argparse import HelpFormatter
from collections import defaultdict, namedtuple
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from functools import partial, wraps
from pathlib import Path
from typing import Any, ClassVar, Self, TypeVar

try:
    import syslog
except ImportError:
    syslog = None
try:
    import cgitb
except ImportError:
    cgitb = None
try:
    from eventlet import sleep as _sleep
    from eventlet.semaphore import Semaphore
except ImportError:
    from time import sleep as _sleep

    class Semaphore:
        def __init__(self, *args: Any, **kwds: Any) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: Any) -> bool:
            return False


T = TypeVar("T")
_OMITTED: Any = object()
_NeverRaised = type("_NeverRaised", (Exception,), {})


class Error(Exception):
    pass


class reraise:
    def __enter__(self) -> Self:
        self.type, self.value, self.tb = sys.exc_info()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, tb: Any) -> bool:
        try:
            if exc_type or exc_value or tb:
                return False
            if not (self.type or self.value or self.tb):
                return False
            _raise_with(self.type, self.value, self.tb)
        finally:
            del self.tb
        return False


def _raise_with(exc_type: type[BaseException], value: BaseException, traceback: types.TracebackType | None) -> None:
    _raise_from(value.with_traceback(traceback), cause=None)


def retry_func(func: Callable[..., T], *args: Any, **kwds: Any) -> T | None:
    exc = kwds.pop("exc", Exception)
    times = kwds.pop("times", 3)
    when = kwds.pop("when", lambda e: True)
    between = kwds.pop("between", lambda tries: None)
    for tries in itertools.count(1):
        try:
            return func(*args, **kwds)
        except exc as e:
            if not when(e):
                raise
            if tries >= times:
                raise
            between(tries)
    return None


class retry:
    def __init__(
        self,
        exc: type[BaseException] | tuple[type[BaseException], ...] = Exception,
        times: int = 3,
        when: Callable[[BaseException], bool] = lambda e: True,
        between: Callable[[int], None] = lambda tries: None,
    ) -> None:
        self.exc = exc
        self.times = times
        self.when = when
        self.between = between

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwds: Any) -> T | None:
            return retry_func(func, *args, exc=self.exc, times=self.times, when=self.when, between=self.between, **kwds)

        return wrapper


class Retry:
    def __init__(self, func: Callable[..., T], *args: Any, **kwds: Any) -> None:
        self.callable = wraps(func)(partial(func, *args, **kwds))
        self._result: Callable[[], T] = self.callable

    def fails(self, exc: type[BaseException] | tuple[type[BaseException], ...] = Exception) -> Iterator[BaseException]:
        while True:
            try:
                result = self.callable()
            except exc as x:
                self._result = partial(self._raise, x)
                yield x
            else:
                self._result = lambda: result
                break
        self.callable = partial(self._raise, Error("Retry callable succeeded, fails() is done"))

    @property
    def result(self) -> T:
        return self._result()

    @staticmethod
    def _raise(exc: BaseException) -> Any:
        raise exc


def describe(exc: BaseException) -> str:
    return "%s: %s" % ("->".join(x.__class__.__name__ for x in rexchain(exc)), exc)


def exchain(exc: BaseException | None) -> Iterator[BaseException]:
    try:
        while exc is not None:
            yield exc
            exc = exc.__context__
    except AttributeError:
        pass


def rexchain(exc: BaseException | None) -> Iterator[BaseException]:
    try:
        yield from rexchain(exc.__context__)
    except AttributeError:
        pass
    if exc is not None:
        yield exc


def caused_by(
    exc: BaseException,
    classes: type[BaseException] | tuple[type[BaseException], ...],
    func: Callable[[BaseException], Any] = lambda err: err,
) -> Any:
    try:
        return func(next(x for x in exchain(exc) if isinstance(x, classes)))
    except StopIteration:
        return None


def caused_by_errno(exc: BaseException, errnos: int | tuple[int, ...]) -> OSError | None:
    if not isinstance(errnos, tuple):
        errnos = (errnos,)
    try:
        return next(x for x in exchain(exc) if isinstance(x, OSError) and x.errno in errnos)
    except StopIteration:
        return None


@contextmanager
def translate_to(
    throw: type[BaseException] | Callable[..., BaseException] | BaseException,
    catch: type[BaseException] | tuple[type[BaseException], ...] = Exception,
) -> Iterator[None]:
    try:
        yield
    except catch as err:
        raise_from(throw, cause=err)


def raise_from(
    throw: type[BaseException] | Callable[..., BaseException] | BaseException,
    cause: BaseException | None | Any = _OMITTED,
) -> None:
    if cause is _OMITTED:
        cause = sys.exc_info()[1]
    if not isinstance(throw, Exception):
        if cause is None:
            throw = throw()
        else:
            throw = throw(describe(cause))
    _raise_from(throw, cause)


def _raise_from(throw: BaseException, cause: BaseException | None) -> None:
    raise throw from cause


@contextmanager
def suppress(*exceptions: type[BaseException]) -> Iterator[None]:
    with contextlib.suppress(*exceptions):
        yield


@contextmanager
def suppress_errno(*errnos: int) -> Iterator[None]:
    try:
        yield
    except OSError as err:
        if err.errno not in errnos:
            raise


def exception_default(
    exc: type[BaseException] | tuple[type[BaseException], ...],
    default: T,
    func: Callable[..., Any],
    *args: Any,
    **kwds: Any,
) -> T:
    try:
        return func(*args, **kwds)
    except exc:
        return default


def capture(func: Callable[..., T], *args: Any, **kwds: Any) -> T | Exception:
    exc = kwds.pop("_exc", Exception)
    try:
        return func(*args, **kwds)
    except exc as err:
        return err


def uncapture(value: T | Exception) -> T:
    if isinstance(value, Exception):
        raise value
    return value


class exceptlink:
    def __init__(self, system: bool = False) -> None:
        self.system = system
        self.prev = sys.excepthook
        sys.excepthook = self

    def cancel(self) -> None:
        obj, attr = sys, "excepthook"
        while True:
            try:
                instance = getattr(obj, attr)
            except AttributeError:
                return
            if instance is self:
                setattr(obj, attr, instance.prev)
                return
            obj, attr = instance, "prev"

    def __call__(self, exc_type: Any, value: Any, traceback: Any) -> None:
        for instance in self.chain():
            try:
                handler = instance.handle
            except AttributeError:
                handler = instance
            with contextlib.suppress(Exception):
                handler(exc_type, value, traceback)

    def chain(self) -> Iterator[Any]:
        instance: Any = self
        system = False
        while True:
            with contextlib.suppress(AttributeError):
                system = system or instance.system
            yield instance
            try:
                prev = instance.prev
            except AttributeError:
                return
            if not prev:
                return
            if (not system) and prev is sys.__excepthook__:
                return
            instance = prev

    def handle(self, exc_type: Any, value: Any, traceback: Any) -> None:
        pass


if cgitb is not None:

    class cgitb_Hook(exceptlink):
        def __init__(self, *args: Any, **kwds: Any) -> None:
            system = kwds.pop("system", False)
            self.handle = cgitb.Hook(*args, **kwds)
            super().__init__(system)


class generic_exceptlink(exceptlink):
    def __init__(self, function: Callable[..., Any], system: bool = False) -> None:
        self.handle = function
        super().__init__(system)


class suppress_but_log(contextlib.ContextDecorator):
    def __init__(self, log: logging.Logger, description: str, *exceptions: type[BaseException]) -> None:
        self.log = log
        self.description = description
        self.exceptions = exceptions or (Exception,)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, value: Any, tb: Any) -> bool | None:
        if value:
            self.log.warning("*** Error trying to %s: %s: %s", self.description, value.__class__.__name__, value)
            return isinstance(value, self.exceptions)
        return None


class LoggingExitStack(contextlib.ExitStack):
    def __init__(self, *args: Any, **kwds: Any) -> None:
        super().__init__()
        self.suppressor = suppress_but_log(*args, **kwds)

    def callback(self, callback: Callable[..., Any], /, *args: Any, **kwds: Any) -> None:
        super().callback(self.suppressor(callback), *args, **kwds)


class attribute_alias:
    def __init__(self, attr: str) -> None:
        self.attr = attr

    def __get__(self, obj: Any, cls: type | None = None) -> Any:
        return getattr((cls if obj is None else obj), self.attr)

    def __set__(self, obj: Any, value: Any) -> None:
        setattr(obj, self.attr, value)

    def __delete__(self, obj: Any) -> None:
        delattr(obj, self.attr)


class class_or_instance_dispatch:
    def __init__(self, classmethod: Callable[..., Any], instancemethod: Callable[..., Any]) -> None:
        self.classmethod = classmethod
        self.instancemethod = instancemethod

    def __get__(self, obj: Any, cls: type | None = None) -> types.MethodType:
        if obj is None:
            return types.MethodType(self.classmethod, cls)
        return types.MethodType(self.instancemethod, obj)


def ownermethod(func: Callable[..., Any]) -> class_or_instance_dispatch:
    return class_or_instance_dispatch(func, func)


class within:
    def __init__(self, ctxmgr: Any, *args: Any, **kwds: Any) -> None:
        if callable(ctxmgr):
            self.ctxmgr = ctxmgr
            self.args = args
            self.kwds = kwds
        else:
            if args or kwds:
                msg = "Can't pass function arguments with non-callable() within() argument"
                raise TypeError(msg)
            self.ctxmgr = lambda: ctxmgr
            self.args = ()
            self.kwds = {}

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        signature = inspect.signature(func)
        if ("_context" in signature.parameters) or any(p.kind == p.VAR_KEYWORD for p in signature.parameters.values()):

            @wraps(func)
            def decorated(*args: Any, **kwds: Any) -> T:
                with self.ctxmgr(*self.args, **self.kwds) as context:
                    return func(_context=context, *args, **kwds)

        else:

            @wraps(func)
            def decorated(*args: Any, **kwds: Any) -> T:
                with self.ctxmgr(*self.args, **self.kwds):
                    return func(*args, **kwds)

        return decorated


class DontCall:
    def __init__(self, target: Any) -> None:
        self.target = target

    def __enter__(self) -> Any:
        return self.target.__enter__()

    def __exit__(self, *args: Any, **kwds: Any) -> Any:
        return self.target.__exit__(*args, **kwds)


class addict(dict):
    def __init__(self, *args: Any, **kwds: Any) -> None:
        super().__init__(*args[:1])
        for add in args[1:]:
            self.update(add)
        self.update(kwds)

    def copy(self) -> Self:
        return self.__class__(self)

    def __add__(self, other: Mapping) -> Self:
        new = self.copy()
        new.update(other)
        return new

    def __radd__(self, other: Mapping) -> Self:
        new = self.__class__(other)
        new.update(self)
        return new

    def __sub__(self, other: Iterable) -> Self:
        return subdict(self, set(self).difference(other))

    def __rsub__(self, other: Mapping) -> Self:
        return subdict(other, set(other).difference(self))


def subdict(d: Mapping, keys: Iterable) -> addict:
    return addict([(key, d[key]) for key in keys])


def interdict(d: Mapping, keys: Iterable) -> addict:
    return subdict(d, set(d).intersection(keys))


class smartdefaultdict(defaultdict):
    def __missing__(self, key: Any) -> Any:
        value = self.default_factory(key)
        self[key] = value
        return value


def drill(d: Any, keypath: Sequence) -> Any:
    result = d
    goodkeys: list[Any] = []
    for k in keypath:
        try:
            result = result[k]
        except (KeyError, IndexError, TypeError):
            raise_from(KeyError(goodkeys + [k]))
        else:
            goodkeys.append(k)
    return result


def dictwalk(d: Any, middle: bool = False, _idxs: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    if isinstance(d, Mapping):
        if middle:
            yield _idxs, d
        for k, v in d.items():
            yield from dictwalk(v, middle=middle, _idxs=_idxs + (k,))
    elif isinstance(d, Sequence) and not isinstance(d, (str, bytes, bytearray)):
        if middle:
            yield _idxs, d
        for i, v in enumerate(d):
            yield from dictwalk(v, middle=middle, _idxs=_idxs + (i,))
    else:
        yield _idxs, d


def preddict(d: Any, pred: Callable[[Any], bool]) -> Iterator[tuple]:
    for keypath, v in dictwalk(d):
        try:
            found = pred(v)
        except (TypeError, AttributeError):
            pass
        else:
            if found:
                yield keypath


def all_eq_in_dict(d: Any, value: Any) -> Iterator[tuple]:
    return preddict(d, lambda v: v == value)


def first_eq_in_dict(d: Any, value: Any) -> tuple | None:
    try:
        return next(all_eq_in_dict(d, value))
    except StopIteration:
        return None


def all_keys_eq(d: Any, key: Any) -> Iterator[tuple]:
    for keypath, v in dictwalk(d, middle=True):
        if keypath and keypath[-1] == key:
            yield keypath


def iterable(obj: Any) -> bool:
    if isinstance(obj, (str, bytes, bytearray)):
        return False
    try:
        iter(obj)
    except TypeError:
        return False
    return True


def sequence(obj: Any) -> Iterable:
    return obj if iterable(obj) else (obj,)


def empty(iterable: Iterable) -> bool:
    try:
        next(iter(iterable))
        return False
    except StopIteration:
        return True


def interleave(*iterables: Iterable) -> Iterator:
    return itertools.chain(*map(lambda *args: args, *iterables))


def lastflag(iterable: Iterable[T]) -> Iterator[tuple[T, bool]]:
    rest = iter(iterable)
    try:
        old = next(rest)
    except StopIteration:
        return
    for new in rest:
        yield old, False
        old = new
    yield old, True


def lazylen(iterable: Iterable) -> int:
    return sum(1 for _ in iterable)


def with_kwds(func: Callable, *args: Any) -> Any:
    if not args:
        return func()
    return func(*args[:-1], **args[-1])


def blocks_from(iterable: Iterable[T], bufsize: int) -> Iterator[tuple[T, ...]]:
    step_iter = iter(iterable)
    block = tuple(itertools.islice(step_iter, bufsize))
    while len(block) == bufsize:
        yield block
        block = tuple(itertools.islice(step_iter, bufsize))
    if block:
        yield block


class compose:
    def __init__(self, *funcs: Callable) -> None:
        self.rfuncs = list(reversed(funcs))

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        if self.rfuncs:
            result = self.rfuncs[0](*args, **kwds)
            for func in self.rfuncs[1:]:
                result = func(result)
            return result
        if not kwds:
            return args[0] if len(args) == 1 else args
        if not args:
            return next(iter(kwds.values())) if len(kwds) == 1 else kwds
        return args, kwds


class pcall:
    def __init__(self, func: Callable) -> None:
        self.func = func

    def __call__(self, args: tuple) -> Any:
        return self.func(*args)


class kcall:
    def __init__(self, func: Callable) -> None:
        self.func = func

    def __call__(self, kwds: dict) -> Any:
        return self.func(**kwds)


class pkcall:
    def __init__(self, func: Callable) -> None:
        self.func = func

    def __call__(self, args_kwds: tuple) -> Any:
        return self.func(*args_kwds[0], **args_kwds[1])


def exactly_one(sequence: Iterable[T], error: Exception) -> T:
    results = tuple(sequence)
    return results[0] if len(results) == 1 else uncapture(error)


def at_most_one(sequence: Iterable[T], error: Exception, **kwds: Any) -> T | None:
    results = tuple(sequence)
    if not results:
        return kwds.get("default")
    if len(results) != 1:
        return uncapture(error)
    return results[0]


class Cycle(Exception):
    pass


def topological_sort(items: Mapping) -> list:
    result = list(topological_rsort(items))
    result.reverse()
    return result


def topological_rsort(items: Mapping) -> Iterator:
    visiting: set = set()
    remaining: list = list(items)
    while remaining:
        node = remaining[0]
        yield from _visit(items, visiting, remaining, node)


def _visit(items: Mapping, visiting: set, remaining: list, node: Any) -> Iterator:
    if node in visiting:
        raise Cycle("Cycle detected back to node %s" % node)
    if node not in remaining:
        return
    visiting.add(node)
    try:
        for child in items[node]:
            yield from _visit(items, visiting, remaining, child)
    finally:
        visiting.remove(node)
    remaining.remove(node)
    yield node


def find_leaves(items: Mapping) -> set:
    return {dep for deps in items.values() for dep in deps if dep not in items}


def fill_leaves(items: dict) -> dict:
    for item in find_leaves(items):
        items[item] = ()
    return items


class BadLink(Exception):
    pass


def downstream_sorted(deps: Mapping, start: Iterable, end: Any = None) -> Iterator:
    affected = set().union(*(downstream_set(deps, node, end) for node in start))
    trimdeps = interdict(deps, affected)
    return itertools.chain(topological_sort(trimdeps), find_leaves(trimdeps))


def downstream_set(deps: Mapping, start: Any, end: Any = None) -> set:
    result: set = set()
    if end is None:
        _downstream_set(result, ["(param)"], deps, start)
    else:
        _downstream_set_to(result, ["(param)"], deps, start, end)
    return result


def _downstream_set(result: set, path: list, deps: Mapping, start: Any) -> None:
    try:
        children = _validate(path, deps, start)
    except BadLink as err:
        print(err, file=sys.stderr)
        return
    result.add(start)
    for child in children:
        _downstream_set(result, path + [start], deps, child)


def _downstream_set_to(result: set, path: list, deps: Mapping, start: Any, end: Any) -> None:
    if start == end:
        result.update(path[1:] + [start])
        return
    try:
        children = _validate(path, deps, start)
    except BadLink as err:
        print(err, file=sys.stderr)
        return
    for child in children:
        _downstream_set_to(result, path + [start], deps, child, end)


def _validate(path: list, deps: Mapping, start: Any) -> Iterable:
    try:
        pos = path[1:].index(start)
    except ValueError:
        pass
    else:
        raise BadLink("Circularity: %s" % (" -> ".join(path[1 + pos :] + [start])))
    return deps.get(start, [])


TIME_UNITS = ((0, "weeks"), (7, "days"), (24, "hours"), (60, "minutes"), (60, "seconds"))


def duration(seconds: float, levels: int | None = None) -> str:
    out: list[tuple[Any, str]] = []
    rest = int(seconds)
    for dividend, name in reversed(TIME_UNITS[1:]):
        rest, remainder = divmod(rest, dividend)
        out.insert(0, (remainder, name))
    out.insert(0, (rest, TIME_UNITS[0][1]))
    out = [pair for pair in out if pair[0]]
    if not out:
        out.append(("%.3f" % seconds, TIME_UNITS[-1][1]))
    return ", ".join(["%s %s" % pair for pair in out[:levels]])


def pickUnits(value: float, div: int, *units: str) -> str:
    if not units:
        return "%.1f" % value
    quotient = 0.0
    unit = ""
    for power, unit in reversed(list(zip(_powers(div), reversed(units)))):
        quotient = float(value) / power
        if int(quotient):
            break
    return "%.1f %s" % (quotient, unit)


def _powers(base: int) -> Iterator[int]:
    power = 1
    while True:
        yield power
        power *= base


class Timer:
    start: float
    end: float | None

    def __enter__(self) -> Self:
        self.start = time.time()
        self.end = None
        return self

    def __exit__(self, exc_type: Any, value: Any, tb: Any) -> bool:
        self.end = time.time()
        return False

    def time(self) -> float:
        return (self.end or time.time()) - self.start

    def duration(self, *args: Any, **kwds: Any) -> str:
        return duration(self.time(), *args, **kwds)

    def units(self, *args: Any, **kwds: Any) -> str:
        if not (args or kwds):
            args = (60, "hours", "minutes", "seconds")
        return pickUnits(self.time(), *args, **kwds)

    def format(self, fmt: str) -> str:
        today = time.mktime(dt.date.today().timetuple())
        return format_time(fmt, today + self.time())


def format_time(fmt: str, t: float) -> str:
    return time.strftime(fmt, time.localtime(t))


class ProgressTimer:
    def __init__(self, total: float, count: float = 0, start: float | None = None) -> None:
        self._total = total
        self._count = count
        self.reset(total, count, start)

    def reset(self, total: float | None = None, count: float | None = None, start: float | None = None) -> None:
        if total is not None:
            self._total = total
        if count is not None:
            self._count = count
        self.start = start if start is not None else time.time()
        self.finish = self.start
        self.elapsed = 0
        self.totaltime = 0
        self.timeleft = 0
        self._update()

    @property
    def total(self) -> float:
        return self._total

    @total.setter
    def total(self, total: float) -> None:
        if self._total != total:
            self._total = total
            self.reset(total)

    @property
    def count(self) -> float:
        return self._count

    @count.setter
    def count(self, count: float) -> None:
        if self._count != count:
            self._count = count
            if count == 0:
                self.reset(count=count)
            else:
                self._update()

    def bump(self, by: int = 1) -> None:
        self.count += by

    def _update(self) -> None:
        self.elapsed = time.time() - self.start
        if self._count:
            self.totaltime = self.elapsed * (float(self._total) / self._count)
            self.finish = self.start + self.totaltime
            self.timeleft = self.totaltime - self.elapsed


class ProgressError(Exception):
    pass


class factory:
    def __init__(self, desc: str) -> None:
        self.desc = desc

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        ProgressBar._factory_funcs.append((self.desc, func))
        return func


def make_impl_pair(mixins: Iterable[type], vanilla: type, args: tuple, kwds: dict) -> tuple[type, Any]:
    if not mixins:
        derived = vanilla
    else:
        bases = tuple(reversed(tuple(mixins))) + (vanilla,)
        name = "_".join(cls.__name__ for cls in bases)
        derived = type(name, bases, {})
    return vanilla, derived(*args, **kwds)


class ProgressBar:
    _factory_funcs: ClassVar[list[tuple[str, Callable[..., Any]]]] = []
    _cached_class: ClassVar[type | None] = None
    _class_cache: ClassVar[dict[tuple, type]] = {}

    def __init__(self, *args: Any, **kwds: Any) -> None:
        mixins = kwds.pop("mixins", ())
        mixins = tuple(mixins)
        try:
            impl_class = ProgressBar._class_cache[mixins]
        except KeyError:
            if not ProgressBar._cached_class:
                self._impl = self._find_impl(mixins, *args, **kwds)
            else:
                self._impl = make_impl_pair(mixins, ProgressBar._cached_class, args, kwds)[1]
            ProgressBar._class_cache[mixins] = self._impl.__class__
        else:
            self._impl = impl_class(*args, **kwds)

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._impl, attr)

    def _find_impl(self, mixins: tuple, *args: Any, **kwds: Any) -> Any:
        for desc, func in ProgressBar._factory_funcs:
            try:
                vanilla, impl = func(mixins, *args, **kwds)
            except Exception:
                continue
            ProgressBar._cached_class = vanilla
            return impl
        ProgressBar._cached_class = ProgressBar.NoImpl
        ProgressBar.NoImpl()
        return None

    class NoImpl:
        def __init__(self, *args: Any, **kwds: Any) -> None:
            raise ProgressError(
                "No available ProgressBar implementation in this environment -- tried "
                + ", ".join(desc for desc, func in ProgressBar._factory_funcs)
            )


class ProgressBarImplBase:
    live = False

    def __init__(self, title: str, maxval: float, label: str) -> None:
        self.titletext = title
        self.labeltext = label
        self.curval = 0
        self.maxval = maxval
        self.set(0, maxval)
        self.live = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any, **kwds: Any) -> bool:
        self.cleanup()
        return False

    def title(self, newstr: str = "") -> None:
        self.titletext = newstr

    def setlabel(self, newstr: str) -> None:
        self.label(newstr)
        self.display()

    def label(self, newstr: str = "") -> None:
        self.labeltext = newstr

    def _get_display_label(self) -> str:
        return "".join(self.get_display_list())

    def get_display_list(self) -> list[str]:
        return [self.labeltext]

    def inc(self, amt: int = 1) -> None:
        self.set(self.curval + amt)

    def set(self, value: float, max: float | None = None) -> None:
        if max is not None:
            self.maxval = max
        value = max(0, min(value, self.maxval))
        self.curval = value
        self.display()

    def __del__(self) -> None:
        self.cleanup()

    def display(self) -> None:
        pass

    def cleanup(self) -> None:
        if self.live:
            self.live = False
            self._cleanup()

    def _cleanup(self) -> None:
        pass


class ProgressThrottle:
    __quiesce_time = 1.0 / 5
    __last_display = 0

    def display(self) -> None:
        now = time.time()
        if (now > self.__last_display) >= self.__quiesce_time:
            type(self).__last_display = now
            super().display()


class Percent:
    def get_display_list(self) -> list[str]:
        return super().get_display_list() + [" (%s%%)" % int(((100.0 * self.curval) / self.maxval) + 0.5)]


class NofTotal:
    def set(self, value: float, maxval: float | None = None) -> None:
        if maxval is not None:
            self.__fmt = self.get_format(maxval)
            self.__max = self.format(maxval)
        super().set(value, maxval)

    def get_display_list(self) -> list[str]:
        return super().get_display_list() + [": %s of %s" % (self.format(self.curval), self.__max)]

    def get_format(self, maxval: float) -> str:
        if maxval < 10:
            fmt = "%.2f"
        elif maxval < 100:
            fmt = "%.1f"
        else:
            fmt = "%d"
        width = len(fmt % maxval)
        return "%%%s%s" % (width, fmt[1:])

    def format(self, value: float) -> str:
        return self.__fmt % value


class Count(NofTotal):
    def get_format(self, maxval: float) -> str:
        width = len("%d" % maxval)
        return "%%%sd" % width


class Size(NofTotal):
    def format(self, value: float) -> str:
        return pickUnits(value, 1024, "gb", "mb", "kb", "b")


class TimeBase:
    def __init__(self, title: str, maxval: float, label: str) -> None:
        self.timer = ProgressTimer(total=maxval)
        super().__init__(title, maxval, label)

    def set(self, value: float, max: float | None = None) -> None:
        if max is not None:
            self.timer.total = max
        self.timer.count = value
        super().set(value, max)


class TimeLeft(TimeBase):
    def get_display_list(self) -> list[str]:
        return super().get_display_list() + [", ", duration(self.timer.timeleft, levels=2), " remaining"]


class Elapsed(TimeBase):
    def get_display_list(self) -> list[str]:
        return super().get_display_list() + [", ", duration(self.timer.elapsed, levels=2), " elapsed"]


class TotalTime(TimeBase):
    def get_display_list(self) -> list[str]:
        return super().get_display_list() + [", ", duration(self.timer.totaltime, levels=2), " overall"]


class Finish(TimeBase):
    def get_display_list(self) -> list[str]:
        return super().get_display_list() + self._finish_format(self.timer.finish)

    @staticmethod
    def _finish_format(finish: float) -> list[str]:
        today = dt.date.today()
        finishdate = dt.date.fromtimestamp(finish)
        if finishdate == today:
            dformat = ""
        elif finishdate == today + dt.timedelta(days=1):
            dformat = " tomorrow"
        else:
            dformat = " %Y-%m-%d"
        return [format_time(f", ETA{dformat} %I:%M %p", finish)]


def FinishAs(fmt: str) -> type:
    return _make_timer_mixin("finish", lambda finish: [format_time(fmt, finish)])


def ElapsedAs(formatter: Callable) -> type:
    return _make_timer_mixin("elapsed", formatter)


def TimeLeftAs(formatter: Callable) -> type:
    return _make_timer_mixin("timeleft", formatter)


def TotalTimeAs(formatter: Callable) -> type:
    return _make_timer_mixin("totaltime", formatter)


_unique = 0


def _make_timer_mixin(attr: str, formatter: Callable) -> type:
    global _unique
    subclassname = "TimerMixin_%s" % _unique
    _unique += 1
    subclass = type(subclassname, (TimeBase,), {})
    subclass.get_display_list = lambda self: (
        super(subclass, self).get_display_list() + formatter(getattr(self.timer, attr))
    )
    return subclass


@factory("wx")
def make_wx_progress_bar(mixins: tuple, *args: Any, **kwds: Any) -> tuple[type, Any]:
    import wx

    global _app
    with contextlib.suppress(Exception):
        _app = wx.App(redirect=False)

    class ProgressBarImpl(ProgressBarImplBase, wx.ProgressDialog):
        def __init__(self, title: str, maxval: float, label: str) -> None:
            wx.ProgressDialog.__init__(
                self,
                title,
                label,
                maxval,
                style=wx.PD_SMOOTH | wx.PD_AUTO_HIDE | wx.PD_ELAPSED_TIME | wx.PD_ESTIMATED_TIME | wx.PD_REMAINING_TIME,
            )
            ProgressBarImplBase.__init__(self, title, maxval, label)
            self.Show(True)

        def title(self, newstr: str = "") -> None:
            self.SetTitle(newstr)

        def display(self) -> None:
            self.Update(self.curval, self._get_display_label())

        def _cleanup(self) -> None:
            self.Destroy()

    return make_impl_pair(mixins, ProgressBarImpl, args, kwds)


@factory("zenity")
def make_zenity_progress_bar(mixins: tuple, *args: Any, **kwds: Any) -> tuple[type, Any]:
    import subprocess

    class ProgressBarImpl(ProgressBarImplBase):
        def __init__(self, title: str, maxval: float, label: str) -> None:
            self.bar = subprocess.Popen(
                [
                    "zenity",
                    "--progress",
                    "--title",
                    title,
                    "--text",
                    label,
                    "--percentage",
                    "0",
                    "--width",
                    "400",
                    "--no-cancel",
                    "--auto-close",
                ],
                stdin=subprocess.PIPE,
            )
            ProgressBarImplBase.__init__(self, title, maxval, label)

        def display(self) -> None:
            percent = int((100.0 * self.curval) / self.maxval + 0.5)
            if percent == 100:
                percent = 99
            assert self.bar.stdin is not None
            self.bar.stdin.write(("%s\n#%s\n" % (percent, self._get_display_label())).encode())

        def _cleanup(self) -> None:
            assert self.bar.stdin is not None
            self.bar.stdin.write(b"100\n")
            self.bar.wait()

    return make_impl_pair(mixins, ProgressBarImpl, args, kwds)


@factory("EasyDialogs")
def make_EasyDialogs_progress_bar(mixins: tuple, *args: Any, **kwds: Any) -> tuple[type, Any]:
    import EasyDialogs.ProgressBar

    class ProgressBarImpl(EasyDialogs.ProgressBar):
        def __init__(self, *args: Any, **kwds: Any) -> None:
            self.curval = 0
            EasyDialogs.ProgressBar.__init__(self, *args, **kwds)

        def cleanup(self) -> None:
            pass

    return make_impl_pair(mixins, ProgressBarImpl, args, kwds)


class _FakeProgressBarImpl(ProgressBarImplBase):
    def __init__(self, title: str, maxval: float, label: str, plain: bool = False) -> None:
        if not plain:
            try:
                pos = list(self.__class__.__mro__).index(_FakeProgressBarImpl)
                before = self.__class__.__mro__[: pos + 1]
                after = self.__class__.__mro__[pos + 1 :]
                self.__class__ = type("Percent_" + self.__class__.__name__, before + (Percent,) + after, {})
            except TypeError:
                pass
        if title:
            print(title + ":")
        super().__init__(title, maxval, label)

    def display(self) -> None:
        print("\r" + self._get_display_label(), end=" ")
        sys.stdout.flush()

    def _cleanup(self) -> None:
        print()


def FakeProgressBar(*args: Any, **kwds: Any) -> Any:
    mixins = kwds.pop("mixins", ())
    return make_impl_pair(tuple(mixins), _FakeProgressBarImpl, args, kwds)[1]


class _AnsiProgressBarImpl(_FakeProgressBarImpl):
    baron = "\033[7m"
    baroff = "\033[m"

    def __init__(self, *args: Any, **kwds: Any) -> None:
        self.width = int(os.environ.get("COLUMNS", 80)) - 2
        super().__init__(*args, **kwds)

    def display(self) -> None:
        invert = int((self.width * self.curval) / float(self.maxval) + 0.5)
        text = self._get_display_label().ljust(invert)
        sys.stdout.writelines(("\r ", self.baron, text[:invert], self.baroff, text[invert:]))
        sys.stdout.flush()


class _ScoreProgressBarImpl(_AnsiProgressBarImpl):
    baron = "\033[4m"


def AnsiProgressBar(*args: Any, **kwds: Any) -> Any:
    mixins = kwds.pop("mixins", ())
    return make_ansi_progress_bar(tuple(mixins), *args, **kwds)[1]


@factory("fake")
def make_ansi_progress_bar(mixins: tuple, *args: Any, **kwds: Any) -> tuple[type, Any]:
    try:
        INSIDE_EMACS = os.environ["INSIDE_EMACS"]
    except KeyError:
        vanilla = _FakeProgressBarImpl if os.environ.get("TERM", "dumb") == "dumb" else _AnsiProgressBarImpl
    else:
        try:
            version = [int(p) for p in INSIDE_EMACS.split(",")[0].split(".")]
        except ValueError:
            vanilla = _FakeProgressBarImpl
        else:
            vanilla = _FakeProgressBarImpl if version[:2] <= [23, 1] else _ScoreProgressBarImpl
    return make_impl_pair(mixins, vanilla, args, kwds)


class ProgressStream:
    def __init__(self, title: str, maxval: float, label: str, bar: type = ProgressBar) -> None:
        try:
            self.bar = bar(title, maxval, label)
        except Exception:
            self.bar = ProgressBarImplBase(title, maxval, label)

    def __call__(self, iterable: Iterable[T]) -> Iterator[T]:
        for item in iterable:
            yield item
            self.respond(item)
        self.bar.cleanup()

    def respond(self, item: Any) -> None:
        raise NotImplementedError


class CountProgressStream(ProgressStream):
    def __init__(self, title: str, maxval: float, bar: type = ProgressBar) -> None:
        ProgressStream.__init__(self, title, maxval, "0 of %s" % maxval, bar=bar)
        self.count = 0

    def respond(self, item: Any) -> None:
        self.count += 1
        self.bar.label("%s of %s" % (self.count, self.bar.maxval))
        self.bar.set(self.count)


class SizeProgressStream(ProgressStream):
    def __init__(self, title: str, maxval: float, bar: type = ProgressBar) -> None:
        self.maxdesc = self.pickUnits(maxval)
        ProgressStream.__init__(self, title, maxval, "0 b of %s" % self.maxdesc, bar=bar)
        self.bytes = 0

    def respond(self, item: bytes) -> None:
        self.bytes += len(item)
        self.bar.label("%s of %s" % (self.pickUnits(self.bytes), self.maxdesc))
        self.bar.set(self.bytes)

    @staticmethod
    def pickUnits(bytes_: float) -> str:
        return pickUnits(bytes_, 1024, "gb", "mb", "kb", "b")


class ParagraphHelpFormatter(HelpFormatter):
    paragraph_break = re.compile(r"(\n\n|\n\x1b)")

    def _fill_text(self, text: str, *args: Any, **kwds: Any) -> str:
        return "".join(
            (
                (p[2:] if p.startswith("\x1b") else p)
                if self.paragraph_break.match(p)
                else super()._fill_text(p, *args, **kwds)
            )
            for p in self.paragraph_break.split(text)
        )


class ParagraphArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwds: Any) -> None:
        help_formatter = kwds.pop("formatter_class", ParagraphHelpFormatter)
        super().__init__(formatter_class=help_formatter, *args, **kwds)


class CommandsError(Exception):
    pass


def print_non_None(value: Any) -> None:
    if value is not None:
        print(value)


class Commands:
    def __init__(self, help: str | None = None) -> None:
        self.help = help
        self.commands: list[tuple[Callable, Callable]] = []

    def __call__(self, func: Callable) -> Callable:
        self.commands.append((func, print_non_None))
        return func

    def format(self, formatter: Callable) -> Callable:
        return functools.partial(self._format, formatter)

    def _format(self, formatter: Callable, func: Callable) -> Callable:
        self.commands.append((func, formatter))
        return func

    def get_parser(self, decamel: str | None = None, score: str = "_") -> argparse.ArgumentParser:
        self.decamel_sep = decamel
        self.score = score
        parser_holder: LazyArgumentParser | ArgumentParserWithSubparsers
        if len(self.commands) == 1:
            parser_holder = LazyArgumentParser(self.help)
        else:
            parser_holder = ArgumentParserWithSubparsers(self.help)
        for func, formatter in self.commands:
            name = self.convert_name(func.__name__)
            doc = inspect.getdoc(func)
            if not doc:
                doc = []
                help_text = None
            else:
                doc = doc.splitlines()
                help_text = list(itertools.takewhile(bool, doc))
                del doc[: len(help_text)]
                help_text = "\n".join(help_text)
            subparser = parser_holder.get_subparser(name, help=help_text)
            subparser.set_defaults(func=func, formatter=formatter)
            args = inspect.signature(func).parameters
            required = {name: meta for name, meta in list(args.items()) if meta.default is inspect.Parameter.empty}
            optional = {name: meta for name, meta in list(args.items()) if meta.default is not inspect.Parameter.empty}
            short_switches = smartdefaultdict(self.get_short_switches)
            for arg, meta in list(required.items()):
                kwds: dict[str, Any] = dict(dest=arg)
                if meta.kind == inspect.Parameter.KEYWORD_ONLY:
                    try:
                        switches = ["-" + short_switches[arg[0].lower()].pop()]
                    except IndexError:
                        switches = []
                    switches.append("--" + self.convert_name(arg))
                    kwds["required"] = True
                else:
                    switches = [self.convert_name(arg)]
                    if switches[0] == arg:
                        del kwds["dest"]
                if meta.annotation is not inspect.Parameter.empty:
                    if issubclass(meta.annotation, (str, bytes)) or not issubclass(meta.annotation, Iterable):
                        kwds["type"] = meta.annotation
                    else:
                        kwds["nargs"] = "+"
                subparser.add_argument(help=self.get_arg_help(doc, arg), *switches, **kwds)
            for arg, meta in list(optional.items()):
                try:
                    switches = ["-" + short_switches[arg[0].lower()].pop()]
                except IndexError:
                    switches = []
                switches.append("--" + self.convert_name(arg))
                kwds = dict(dest=arg)
                default = "(default %(default)s)"
                if meta.default is False:
                    kwds["action"] = "store_true"
                elif meta.default is True:
                    switch = score.join(("--no", arg))
                    kwds["action"] = "store_false"
                    default = f"(default {arg}={meta.default})"
                elif meta.annotation is not inspect.Parameter.empty:
                    if issubclass(meta.annotation, (str, bytes)) or not issubclass(meta.annotation, Iterable):
                        kwds["type"] = meta.annotation
                    else:
                        kwds["nargs"] = "*"
                elif meta.default is None or type(meta.default) is object:
                    pass
                else:
                    kwds["type"] = type(meta.default)
                help_text = self.get_arg_help(doc, arg)
                help_text = f"{help_text} {default}" if help_text else default
                subparser.add_argument(default=meta.default, help=help_text, *switches, **kwds)
            try:
                varargs = next(
                    meta for meta in list(args.values()) if meta.kind == inspect.Parameter.VAR_POSITIONAL
                ).name
            except StopIteration:
                pass
            else:
                argname = self.convert_name(varargs)
                kwds = dict(dest=varargs) if argname != varargs else {}
                subparser.add_argument(argname, nargs="*", help=self.get_arg_help(doc, varargs), **kwds)
        return parser_holder.get_parser()

    def convert_name(self, name: str) -> str:
        return self.decamel(name.replace("_", self.score))

    first_cap_re = re.compile(r"(.)([A-Z][a-z]+)")
    sep_cap_re = re.compile(r"([a-z0-9])([A-Z])")

    def decamel(self, name: str) -> str:
        if not self.decamel_sep:
            return name
        replace = self.decamel_sep.join((r"\1", r"\2"))
        intermediate = self.first_cap_re.sub(replace, name)
        return self.sep_cap_re.sub(replace, intermediate).lower()

    def get_arg_help(self, doc: list[str], arg: str) -> str | None:
        argpfx = arg + ":"
        helpsearch = iter(doc)
        for line in helpsearch:
            if line.startswith(argpfx):
                helplines = [line[len(argpfx) :].lstrip()]
                try:
                    line = next(helpsearch)
                    while line.startswith(" "):
                        helplines.append(line)
                        line = next(helpsearch)
                except StopIteration:
                    pass
                return "\n".join(helplines)
        return None

    @staticmethod
    def get_short_switches(initial: str) -> list[str]:
        return [initial.upper(), initial.lower()]


class LazyArgumentParser:
    def __init__(self, help: str | None) -> None:
        self.help = help
        self.parser: ArgumentParser | None = None

    def get_subparser(self, name: str, help: str | None) -> ArgumentParser:
        if self.parser is not None:
            msg = "LazyArgumentParser.get_subparser() must be called exactly once"
            raise CommandsError(msg)
        self.parser = ArgumentParser(description=self.help or help)
        return self.parser

    def get_parser(self) -> ArgumentParser:
        if self.parser is None:
            msg = "LazyArgumentParser.get_subparser() must be called exactly once before get_parser()"
            raise CommandsError(msg)
        return self.parser


class ArgumentParserWithSubparsers:
    def __init__(self, help: str | None) -> None:
        self.parser = ArgumentParser(description=help)
        self.subparsers = self.parser.add_subparsers(title="subcommands")

    def get_subparser(self, name: str, help: str | None) -> argparse.ArgumentParser:
        return self.subparsers.add_parser(name, description=help)

    def get_parser(self) -> argparse.ArgumentParser:
        return self.parser


class ArgumentParser(argparse.ArgumentParser):
    def parse_args(self, *args: Any, **kwds: Any) -> argparse.Namespace:
        parsed = super().parse_args(*args, **kwds)
        parsed.run = functools.partial(run, parsed)
        return parsed


def run(self: argparse.Namespace, exceptions: type[BaseException] = _NeverRaised) -> Any:
    kwds = vars(self)
    kwds.pop("run")
    func = kwds.pop("func")
    formatter = kwds.pop("formatter")
    try:
        return formatter(func(**kwds))
    except exceptions as err:
        sys.exit(describe(err))


IGNORE_DIRS = ("CVS", ".svn", ".hg", ".git", "__pycache__")


def file_arg(*args: Any, **kwds: Any) -> argparse.ArgumentParser:
    return _arg(args, kwds, dest="files", metavar="FILE", help="consider each {metavar} specified")


def dir_arg(*args: Any, **kwds: Any) -> argparse.ArgumentParser:
    return _arg(args, kwds, dest="dirs", metavar="DIR", help="consider all the files at top level of each {metavar}")


def file_or_dir_arg(*args: Any, **kwds: Any) -> argparse.ArgumentParser:
    return _arg(
        args,
        kwds,
        dest="files_or_dirs",
        metavar="FILE or DIR",
        help="consider each FILE specified, plus all the files at top level of each DIR",
    )


def tree_arg(*args: Any, **kwds: Any) -> argparse.ArgumentParser:
    return _arg(
        args,
        kwds,
        dest="trees",
        metavar="BASEDIR",
        help="recursively walk all the files in each {metavar}",
    )


def file_or_tree_arg(*args: Any, **kwds: Any) -> argparse.ArgumentParser:
    return _arg(
        args,
        kwds,
        dest="files_or_trees",
        metavar="FILE or BASEDIR",
        help="consider each FILE specified, plus all the files at any depth under each BASEDIR tree",
    )


def _arg(
    args: tuple,
    kwds: dict,
    dest: str,
    metavar: str,
    help: str,
    default: Any = (),
) -> argparse.ArgumentParser:
    prefix_chars = kwds.pop("prefix_chars", "-")
    dest = kwds.pop("dest", dest)
    if any(arg[0] in prefix_chars for arg in args):
        nargs = "+"
        kwds["dest"] = dest
    else:
        nargs = "*"
    nargs = kwds.pop("nargs", nargs)
    default = kwds.pop("default", default)
    metavar = kwds.pop("metavar", metavar)
    help = kwds.pop("help", help.format(metavar=metavar))
    parser = argparse.ArgumentParser(add_help=False, prefix_chars=prefix_chars)
    parser.add_argument(nargs=nargs, default=default, metavar=metavar, help=help, *args, **kwds)
    return parser


def files_from(
    args: Any = None,
    *,
    ignore_dirs: Iterable[str] = IGNORE_DIRS,
    files: Iterable[str] | None = None,
    dirs: Iterable[str] | None = None,
    files_or_dirs: Iterable[str] | None = None,
    trees: Iterable[str] | None = None,
    files_or_trees: Iterable[str] | None = None,
) -> Iterator[Path]:
    kwds = {
        "files": files,
        "dirs": dirs,
        "files_or_dirs": files_or_dirs,
        "trees": trees,
        "files_or_trees": files_or_trees,
    }
    for key, value in tuple(kwds.items()):
        if value is None:
            kwds[key] = getattr(args, key, ()) or ()
    files_lists = [(Path(f) for f in glob.glob(wild) if Path(f).is_file()) for wild in kwds["files"]]
    dirs_lists = [
        (Path(d) for d in glob.glob(wild) if Path(d).is_dir() and d not in ignore_dirs) for wild in kwds["dirs"]
    ]
    trees_lists = [
        (Path(d) for d in glob.glob(wild) if Path(d).is_dir() and d not in ignore_dirs) for wild in kwds["trees"]
    ]
    fod = tuple(Path(f_d) for wild in kwds["files_or_dirs"] for f_d in glob.glob(wild))
    fot = tuple(Path(f_t) for wild in kwds["files_or_trees"] for f_t in glob.glob(wild))
    files_lists.extend(
        (
            (f for f in fod if f.is_file()),
            (f for f in fot if f.is_file()),
        )
    )
    dirs_lists.append((d for d in fod if d.is_dir() and d not in ignore_dirs))
    trees_lists.append((d for d in fot if d.is_dir() and d not in ignore_dirs))
    return itertools.chain(
        itertools.chain.from_iterable(files_lists),
        itertools.chain.from_iterable(files_in_dir(dir) for dir in itertools.chain.from_iterable(dirs_lists)),
        itertools.chain.from_iterable(
            files_in_tree(dir, ignore_dirs=ignore_dirs) for dir in itertools.chain.from_iterable(trees_lists)
        ),
    )


def files_in_dir(dir: Path) -> Iterator[Path]:
    return (f for f in Path(dir).iterdir() if f.is_file())


def files_in_tree(dir: Path, ignore_dirs: Iterable[str] = IGNORE_DIRS) -> Iterator[Path]:
    ignore = set(ignore_dirs)
    for basedir, subdirs, files in os.walk(dir):
        for file in files:
            yield Path(basedir) / file
        for d in ignore:
            with contextlib.suppress(ValueError):
                subdirs.remove(d)


def filesource(filename: str | Path, mode: str = "r") -> Iterator[str]:
    with Path(filename).open(mode) as f:
        yield from f


def readlines(file: Any) -> Iterator[str]:
    line = file.readline()
    while line:
        yield line
        line = file.readline()


def filebufsource(filename: str | Path, size: int = 16 * 1024, mode: str = "rb") -> Iterator[bytes]:
    with Path(filename).open(mode) as f:
        while True:
            buf = f.read(size)
            if not buf:
                break
            yield buf


def filesink(
    filename: str | Path,
    iterable: Iterable[str | bytes],
    mode: str = "w",
    eol: str | None = None,
    flush: bool = False,
) -> None:
    if eol is not None:
        return filesink(filename, interleave(iterable, itertools.repeat(eol)), mode=mode, eol=None, flush=flush)
    with Path(filename).open(mode) as f:
        if not flush:
            f.writelines(iterable)
        else:
            for item in iterable:
                f.write(item)
                f.flush()


class JanitorError(Exception):
    pass


class _Dummy:
    def write(self, data: str) -> None:
        pass

    def flush(self) -> None:
        pass


class Janitor:
    triple = namedtuple("triple", ("always", "desc", "func"))

    def __init__(self, report: Any = None, errors: Any = sys.stderr) -> None:
        self.report = report or _Dummy()
        self.errors = errors
        self.actions: list = []
        self.with_depth: list[int] = []

    def cleanup(self, func: Callable, *args: Any, **kwds: Any) -> None:
        self._add(True, func, *args, **kwds)

    def rollback(self, func: Callable, *args: Any, **kwds: Any) -> None:
        if not self.with_depth:
            msg = "Calling Janitor.rollback() outside a 'with' block is an error"
            raise JanitorError(msg)
        self._add(False, func, *args, **kwds)

    def context(self, manager: Any) -> Any:
        self.actions.append(
            self.triple(always=True, desc=self._name_for(manager) + ".__exit__()", func=manager.__exit__)
        )
        return manager.__enter__()

    def atexit(self) -> None:
        atexit.register(self.done)

    def _add(self, always: bool, func: Callable, *args: Any, **kwds: Any) -> None:
        try:
            desc = kwds.pop("_desc")
        except KeyError:
            name = self._name_for(func)
            desc = "{}({})".format(
                name,
                ", ".join(
                    itertools.chain(
                        (repr(a) for a in args),
                        ("{}={!r}".format(k, v) for (k, v) in kwds.items()),
                    )
                ),
            )
        self.actions.append(
            self.triple(
                always=always,
                desc=desc,
                func=lambda exc_type, value, tb: partial(func, *args, **kwds),
            )
        )

    def _name_for(self, obj: Any) -> str:
        try:
            return obj.__name__
        except AttributeError:
            try:
                return obj.__class__.__name__
            except AttributeError:
                return repr(obj)

    def __enter__(self) -> Self:
        self.with_depth.append(len(self.actions))
        return self

    def __exit__(self, exc_type: Any, value: Any, tb: Any) -> bool:
        backto = self.with_depth.pop(-1)
        self._call_some(exc_type, value, tb, backto=backto)
        return False

    def done(self) -> None:
        self._call_some(None, None, None, backto=0)

    def _call_some(self, exc_type: Any, value: Any, tb: Any, backto: int) -> None:
        exc = exc_type is not None
        actions = self.actions[backto:]
        del self.actions[backto:]
        while actions:
            triple = actions.pop(-1)
            if not (triple.always or exc):
                continue
            print(triple.desc, file=self.report)
            try:
                triple.func(exc_type, value, tb)
            except Exception as err:
                print("Calling {}\nraised  {}".format(triple.desc, describe(err)), file=self.errors)

    def tearDown(self) -> None:
        self.done()

    def teardown_method(self, method: Any) -> None:
        self.done()


EXCEPTION = object()


def log_calls(
    logger: logging.Logger | str | Callable | None = None,
    level: int = logging.DEBUG,
    exclevel: int | Any = logging.DEBUG,
) -> Any:
    if callable(logger):
        func = logger
        deco = _log_calls(logger=f"{func.__module__}.{func.__name__}", level=level, exclevel=exclevel)
        return deco(func)
    return _log_calls(logger=logger, level=level, exclevel=exclevel)


class _log_calls:
    def __init__(self, logger: logging.Logger | str | None, level: int, exclevel: int | Any) -> None:
        self.logger = logger if isinstance(logger, logging.Logger) else logging.getLogger(logger)
        self.level = level
        self.exclevel = exclevel

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        log = functools.partial(self.logger.log, self.level)
        exclog = (
            self.logger.exception if self.exclevel is EXCEPTION else functools.partial(self.logger.log, self.exclevel)
        )

        @wraps(func)
        def wrapper(*args: Any, **kwds: Any) -> T:
            name = func.__name__
            log(
                "{}({})".format(
                    name,
                    ", ".join(
                        itertools.chain(
                            (repr(arg) for arg in args),
                            ("{}={!r}".format(*item) for item in list(kwds.items())),
                        )
                    ),
                )
            )
            try:
                result = func(*args, **kwds)
            except Exception as err:
                exclog("{}() raised {}".format(name, describe(err)))
                raise
            else:
                log("%s() => %r", name, result)
                return result

        return wrapper


class OutError(Exception):
    pass


def push_generator(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwds: Any) -> Any:
        return pushiter(func(*args, **kwds))

    return wrapper


def pushiter(generator_call: Any) -> Any:
    handle = iter(generator_call)
    next(handle)
    return handle


class ofilter:
    def __init__(self, sink: Any = None, **kwds: Any) -> None:
        self.sink = self._maybe_adapt(sink, **kwds)

    @property
    def name(self) -> str:
        try:
            return self.sink.name
        except AttributeError:
            try:
                return self.sink.__name__
            except AttributeError:
                return repr(self.sink)

    def _maybe_adapt(self, sink: Any = None, **kwds: Any) -> Any:
        try:
            write = kwds.pop("write")
        except KeyError:
            try:
                sink.write
            except AttributeError:
                raise OutError("%s passed invalid sink %s" % (self.__class__.__name__, sink.__class__.__name__))
            try:
                sink.flush
            except AttributeError:
                return adapter(sink.write)
            else:
                return sink
        else:
            return adapter(write, kwds.pop("flush", None))

    def write(self, item: Any) -> None:
        self.sink.write(item)

    def writelines(self, iterable: Iterable) -> None:
        for item in iterable:
            self.write(item)

    def flush(self) -> None:
        self.sink.flush()

    def close(self) -> None:
        self.flush()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, value: Any, tb: Any) -> bool:
        self.close()
        return False


class adapter(ofilter):
    def __init__(self, write: Callable, flush: Callable | None = None) -> None:
        self.write = write
        if flush:
            self.flush = flush

    def flush(self) -> None:
        pass


class _Flush(Exception):
    pass


class buffer_lines(ofilter):
    def __init__(self, sink: Any = None, **kwds: Any) -> None:
        self.eol = kwds.pop("eol", "")
        self.loopgen = self.loop(self._maybe_adapt(sink, **kwds))

    def write(self, item: str) -> None:
        self.loopgen.send(item)

    def flush(self) -> None:
        self.write("\n")
        self.loopgen.throw(_Flush)

    def close(self) -> None:
        self.flush()
        self.loopgen.close()

    @push_generator
    def loop(self, sink: Any) -> Iterator[None]:
        buffer = [""]
        while True:
            while "\n" not in buffer[-1]:
                try:
                    buffer.append((yield))
                except _Flush:
                    sink.flush()
            pieces = [p.rstrip("\r") for p in buffer.pop(-1).split("\n")]
            sink.write("".join(buffer + [pieces.pop(0), self.eol]))
            buffer = [pieces.pop(-1)]
            for line in pieces:
                sink.write(line + self.eol)


class overtype(ofilter):
    def write(self, line: str) -> None:
        super().write(line.rsplit("\r", 1)[-1])


if syslog is not None:

    class _syslogger(ofilter):
        def __init__(self, *args: Any, **kwds: Any) -> None:
            self.level = kwds.pop("level", syslog.LOG_INFO)
            syslog.openlog(*args, **kwds)

        def write(self, text: str, **kwds: Any) -> None:
            syslog.syslog(kwds.pop("level", self.level), text)

        def flush(self) -> None:
            pass

    def syslogger(*args: Any, **kwds: Any) -> buffer_lines:
        return buffer_lines(_syslogger(*args, **kwds))


logwrappers = namedtuple("logwrappers", ("debug", "info", "warning", "error", "critical", "exception"))


def wraplogger(logger: logging.Logger) -> Any:
    return logwrappers(**{field: buffer_lines(adapter(getattr(logger, field))) for field in logwrappers._fields})


@contextmanager
def log_handler(
    name: str | logging.Logger,
    handler: logging.Handler | None,
    level: int | None = None,
    propagate: bool | None = None,
    optional: bool = False,
) -> Iterator[logging.Logger]:
    logger = name if isinstance(name, logging.Logger) else logging.getLogger(name)
    hasHandlers = getattr(logger, "hasHandlers", lambda: False)
    if (not handler) or (optional and hasHandlers()):
        handler = None
    else:
        logger.addHandler(handler)
    prevlevel = logger.level
    if level is not None:
        logger.setLevel(level)
    prevprop = logger.propagate
    if propagate is not None:
        logger.propagate = propagate
    try:
        yield logger
    finally:
        logger.propagate = prevprop
        logger.setLevel(prevlevel)
        if handler:
            logger.removeHandler(handler)


class tee(ofilter):
    def __init__(self, *sinks: Any) -> None:
        self.sinks = sinks

    def write(self, data: Any) -> None:
        for sink in self.sinks:
            sink.write(data)

    def flush(self) -> None:
        for sink in self.sinks:
            sink.flush()


class JsonLines(exceptlink):
    def __init__(self, filename: str | Path, system: bool = False) -> None:
        self.outf = Path(filename).open("a")
        super().__init__(system)
        self.write("started", None)
        atexit.register(self.write, "stopped", key=None)

    def handle(self, exc_type: Any, value: Any, traceback: Any) -> None:
        self.write("exception", key=describe(value))

    @contextmanager
    def task(self, key: str) -> Iterator[None]:
        self.starting(key)
        try:
            yield
        except Exception:
            self.aborted(key)
            raise
        else:
            self.finished(key)

    def starting(self, key: str) -> None:
        self.write("starting", key)

    def finished(self, key: str) -> None:
        self.write("finished", key)

    def aborted(self, key: str) -> None:
        self.write("aborted", key)

    def write(self, action: str, key: str | None) -> None:
        json.dump(dict(time=dt.datetime.today().isoformat(), action=action, key=key), self.outf)
        self.outf.write("\n")
        self.outf.flush()


class PickleableProxy:
    _target: Any = None

    def __init__(self, target: Any) -> None:
        self._target = target

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._target, attr)


class WrappingProxy(PickleableProxy):
    def __init__(
        self,
        target: Any,
        wrapper: Callable,
        wrap: Iterable[str] = (),
        nowrap: Iterable[str] = (),
        should_wrap: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(target)
        self.__wrapper = wrapper
        wparams = [w for w in (wrap, nowrap, should_wrap) if w]
        if len(wparams) > 1:
            msg = "Pass WrappingProxy.__init__() at most one of wrap, nowrap or should_wrap"
            raise TypeError(msg)
        if not wparams:
            self._test = lambda method: True
        elif wrap:
            wrap_set = set(wrap)
            self._test = lambda method: method in wrap_set
        elif nowrap:
            nowrap_set = set(nowrap)
            self._test = lambda method: method not in nowrap_set
        else:
            self._test = should_wrap

    def __getattr__(self, attr: str) -> Any:
        attribute = getattr(self._target, attr)
        if not callable(attribute):
            return attribute
        if not self._test(attr):
            setattr(self, attr, attribute)
            return attribute
        wrapped = wraps(attribute)(self.__wrapper(attribute))
        setattr(self, attr, wrapped)
        return wrapped


class WrappingProxyFamily(WrappingProxy):
    def __init__(
        self,
        target: Any,
        wrapper: Callable,
        *args: Any,
        alsowrap: tuple = (),
        **kwds: Any,
    ) -> None:
        self.__alsowrap = alsowrap

        def meta_wrapper(method: Callable) -> Callable:
            wrapped = wrapper(method)

            def propagate(*args: Any, **kwds: Any) -> Any:
                value = wrapped(*args, **kwds)
                if not isinstance(value, self.__alsowrap):
                    return value
                return WrappingProxyFamily(value, wrapper=wrapper, should_wrap=self._test, alsowrap=self.__alsowrap)

            return propagate

        super().__init__(target, wrapper=meta_wrapper, *args, **kwds)


def relwalk(base: str | Path, *args: Any, **kwds: Any) -> Iterator[tuple[str, list[str], list[str]]]:
    nopfilter = lambda path: False
    skipfiles = kwds.pop("skipfiles", nopfilter)
    skipdirs = kwds.pop("skipdirs", nopfilter)
    base_str = str(base)
    for dirpath, dirs, files in os.walk(base, *args, **kwds):
        if dirpath.startswith(base_str):
            trimdir = dirpath[len(base_str) :].lstrip(os.sep)
        else:
            trimdir = dirpath
        for d in dirs[:]:
            if skipdirs(os.path.join(trimdir, d)):
                dirs.remove(d)
        yield trimdir, dirs, [f for f in files if not skipfiles(os.path.join(trimdir, f))]


def relfiles(*args: Any, **kwds: Any) -> Iterator[str]:
    for dir, dirs, files in relwalk(*args, **kwds):
        for file in files:
            yield os.path.join(dir, file)


def reldirs(*args: Any, **kwds: Any) -> Iterator[str]:
    for dir, dirs, files in relwalk(*args, **kwds):
        for subdir in dirs:
            yield os.path.join(dir, subdir)


def relnames(*args: Any, **kwds: Any) -> Iterator[str]:
    for dir, dirs, files in relwalk(*args, **kwds):
        for name in itertools.chain(dirs, files):
            yield os.path.join(dir, name)


_bufparam = "buffering"


class ReplaceFile:
    def __init__(
        self,
        filename: str | Path,
        inmode: str = "r",
        outmode: str = "w",
        newext: str | None = None,
        oldext: str | None = None,
    ) -> None:
        self.filename = Path(filename)
        self.inmode = inmode
        self.outmode = outmode
        self.newext = newext
        self.oldext = oldext
        self.outname: Path | None = None
        self.inf: Any = None
        self.outf: Any = None

    def __enter__(self) -> tuple[Any, Any]:
        self.inf = self.filename.open(self.inmode)
        if self.newext:
            self.outname = Path(str(self.filename) + self.newext)
            self.outf = self.outname.open(self.outmode)
        else:
            self.outf = tempfile.NamedTemporaryFile(
                mode=self.outmode,
                dir=str(self.filename.parent),
                delete=False,
                **{_bufparam: 16 * 1024},
            )
            self.outname = Path(self.outf.name)
        return self.inf, self.outf

    def __exit__(self, exc_type: Any, value: Any, tb: Any) -> bool | None:
        self.inf.close()
        self.outf.close()
        if exc_type or value or tb:
            if not self.newext:
                assert self.outname is not None
                self.outname.unlink()
            return False
        assert self.outname is not None
        shutil.copymode(self.filename, self.outname)
        if self.oldext:
            oldname = Path(str(self.filename) + self.oldext)
            with contextlib.suppress(FileNotFoundError):
                oldname.unlink()
            self.filename.rename(oldname)
        else:
            self.filename.unlink()
        self.outname.rename(self.filename)
        return None


try:
    _monotonic: Callable[[], float] = time.monotonic
except AttributeError:
    _monotonic = time.time


class Throttle:
    def __init__(self, interval: float) -> None:
        self.interval = interval
        self.throttle = Semaphore(1)
        self.nexttime = 0.0

    def __enter__(self) -> None:
        self.throttle.__enter__()
        delay = self.nexttime - _monotonic()
        if delay > 0:
            _sleep(delay)
        self.nexttime = _monotonic() + self.interval

    def __exit__(self, *args: Any) -> bool:
        self.throttle.__exit__(*args)
        return False

    def wrap(self, func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwds: Any) -> T:
            with self:
                return func(*args, **kwds)

        return wrapper


class ThrottledProxy(WrappingProxy):
    def __init__(
        self,
        target: Any,
        throttle: Throttle,
        limit: Iterable[str] = (),
        nolimit: Iterable[str] = (),
        limiter: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(target, wrapper=throttle.wrap, wrap=limit, nowrap=nolimit, should_wrap=limiter)


class ThrottledProxyFamily(WrappingProxyFamily):
    def __init__(
        self,
        target: Any,
        throttle: Throttle,
        limit: Iterable[str] = (),
        nolimit: Iterable[str] = (),
        limiter: Callable[[str], bool] | None = None,
        alsowrap: tuple = (),
    ) -> None:
        super().__init__(
            target,
            wrapper=throttle.wrap,
            wrap=limit,
            nowrap=nolimit,
            should_wrap=limiter,
            alsowrap=alsowrap,
        )
