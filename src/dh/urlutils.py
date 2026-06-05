from re import IGNORECASE as re_IGNORECASE
from re import UNICODE as re_UNICODE
from re import compile as re_compile
from typing import Any, Callable, Pattern
from typing import Any, Callable, Dict
from inspect import getfullargspec
from functools import wraps
from itertools import chain


class ValidationFailure(Exception):
    def __init__(self, function: Callable[..., Any], arg_dict: Dict[str, Any]):
        self.func = function
        self.__dict__.update(arg_dict)

    def __repr__(self):
        return (
            f"ValidationFailure(func={self.func.__name__}, "
            + f"args={ {k: v for k, v in self.__dict__.items() if k != 'func'} })"
        )

    def __str__(self):
        return repr(self)

    def __bool__(self):
        return False


def _func_args_as_dict(func: Callable[..., Any], *args: Any, **kwargs: Any):
    return dict(list(zip(dict.fromkeys(chain(getfullargspec(func)[0], kwargs.keys())), args)) + list(kwargs.items()))


def validator(func: Callable[..., Any]):
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        return True if func(*args, **kwargs) else ValidationFailure(func, _func_args_as_dict(func, *args, **kwargs))

    return wrapper


ip_middle_octet = "(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5]))"
ip_last_octet = "(?:\\.(?:0|[1-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-5]))"
regex = re_compile(
    "^(?:(?:https?|ftp)://)(?:[-a-z\\u00a1-\\uffff0-9._~%!$&'()*+,;=:]+(?::[-a-z0-9._~%!$&'()*+,;=:]*)?@)?(?:(?P<private_ip>(?:(?:10|127)"
    + ip_middle_octet
    + "{2}"
    + ip_last_octet
    + ")|(?:(?:169\\.254|192\\.168)"
    + ip_middle_octet
    + ip_last_octet
    + ")|(?:172\\.(?:1[6-9]|2\\d|3[0-1])"
    + ip_middle_octet
    + ip_last_octet
    + "))|(?P<private_host>(?:localhost))|(?P<public_ip>(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])"
    + ip_middle_octet
    + "{2}"
    + ip_last_octet
    + ")|\\[(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\\]|(?:(?:(?:xn--[-]{0,2})|[a-z\\u00a1-\\uffff\\U00010000-\\U0010ffff0-9]-?)*[a-z\\u00a1-\\uffff\\U00010000-\\U0010ffff0-9]+)(?:\\.(?:(?:xn--[-]{0,2})|[a-z\\u00a1-\\uffff\\U00010000-\\U0010ffff0-9]-?)*[a-z\\u00a1-\\uffff\\U00010000-\\U0010ffff0-9]+)*(?:\\.(?:(?:xn--[-]{0,2}[a-z\\u00a1-\\uffff\\U00010000-\\U0010ffff0-9]{2,})|[a-z\\u00a1-\\uffff\\U00010000-\\U0010ffff]{2,})))(?::\\d{2,5})?(?:/[-a-z\\u00a1-\\uffff\\U00010000-\\U0010ffff0-9._~%!$&'()*+,;=:@/]*)?(?:\\?\\S*)?(?:#\\S*)?$",
    re_UNICODE | re_IGNORECASE,
)
pattern = re_compile(regex)


@validator
def is_valid_url(value, public=False):
    result = pattern.match(value)
    if not public:
        return result
    return result and (not any((result.groupdict().get(key) for key in ("private_ip", "private_host"))))
