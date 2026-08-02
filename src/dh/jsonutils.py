import json
import re
from collections.abc import Iterable
from copy import deepcopy as copy_deepcopy
from math import isnan
from sys import stdin as sys_stdin
from sys import stdout as sys_stdout


def check_if_numbers_are_consecutive(list_) -> bool:
    return all(second - first == 1 for first, second in zip(list_[:-1], list_[1:], strict=False))


def _construct_key(previous_key, separator: str, new_key: int, replace_separators=None) -> int | str:
    if replace_separators is not None:
        new_key = str(new_key).replace(separator, replace_separators)
    if previous_key:
        return f"{previous_key}{separator}{new_key}"
    return new_key


def flatten(nested_dict, separator="_", root_keys_to_ignore=None, replace_separators=None):
    if not isinstance(nested_dict, dict):
        msg = "type error"
        raise Exception(msg)
    if not isinstance(separator, str):
        msg = "type error"
        raise Exception(msg)
    if root_keys_to_ignore is None:
        root_keys_to_ignore = set()
    if len(nested_dict) == 0:
        return {}
    flattened_dict = {}

    def _flatten(object_, key: int | str | None) -> None:
        if not object_:
            flattened_dict[key] = object_
        elif isinstance(object_, dict):
            for object_key in object_:
                if not (not key and object_key in root_keys_to_ignore):
                    _flatten(
                        object_[object_key],
                        _construct_key(
                            key,
                            separator,
                            object_key,
                            replace_separators=replace_separators,
                        ),
                    )
        elif isinstance(object_, (list, set, tuple)):
            for index, item in enumerate(object_):
                _flatten(
                    item,
                    _construct_key(key, separator, index, replace_separators=replace_separators),
                )
        else:
            flattened_dict[key] = object_

    _flatten(nested_dict, None)
    return flattened_dict


flatten_json = flatten


def flatten_preserve_lists(
    nested_dict,
    separator: str = "_",
    root_keys_to_ignore=None,
    max_list_index: int = 3,
    max_depth: int = 3,
    replace_separators=None,
):
    assert isinstance(nested_dict, dict), "flatten requires a dictionary input"
    assert isinstance(separator, str), "separator must be a string"
    if root_keys_to_ignore is None:
        root_keys_to_ignore = set()
    flattened_dict = {}

    def _flatten(object_, key: int | str | None) -> None:
        if not object_:
            flattened_dict[key] = object_
        elif isinstance(object_, dict):
            first_key = next(iter(object_.keys()))
            is_iter = isinstance(object_[first_key], Iterable)
            if len(object_) == 1 and not is_iter:
                flattened_dict[key] = object_[first_key]
            else:
                for object_key in object_:
                    if not (not key and object_key in root_keys_to_ignore):
                        _flatten(
                            object_[object_key],
                            _construct_key(
                                key,
                                separator,
                                object_key,
                                replace_separators=replace_separators,
                            ),
                        )
        elif isinstance(object_, (list, set, tuple)):
            for index, item in enumerate(object_):
                key = _construct_key(key, separator, index, replace_separators=replace_separators)
                _flatten(item, key)
        else:
            flattened_dict[key] = object_

    def _flatten_low_entropy(object_, key: int | str | None, cur_depth, max_depth_inner) -> None:
        cur_depth += 1
        debug = 0
        if cur_depth > max_depth_inner or not object_:
            global_max_record = int(max(list(list_prebuilt_flattened_dict.keys())))
            for d in list_prebuilt_flattened_dict[str(global_max_record)]:
                d[key] = object_
        elif isinstance(object_, dict):
            first_key = next(iter(object_.keys()))
            if len(object_) == 1 and not (isinstance(object_[first_key], dict) or isinstance(object_[first_key], list)):
                global_max_record = int(max(list(list_prebuilt_flattened_dict.keys())))
                for d in list_prebuilt_flattened_dict[str(global_max_record)]:
                    d[key] = object_[first_key]
            else:
                for object_key, val in sorted(
                    object_.items(),
                    key=lambda x: (str(type(x[1])), len(str(x[1]))),
                    reverse=False,
                ):
                    if not (not key and object_key in root_keys_to_ignore):
                        _flatten_low_entropy(
                            object_[object_key],
                            _construct_key(
                                key,
                                separator,
                                object_key,
                                replace_separators=replace_separators,
                            ),
                            cur_depth,
                            max_depth_inner,
                        )
        elif isinstance(object_, (list, set)):
            if debug:
                print("\nparent key of list:", key, "| length: ", str(len(object_)))
            global_max_record_start = int(max(list(list_prebuilt_flattened_dict.keys())))
            entry = copy_deepcopy(list_prebuilt_flattened_dict[str(global_max_record_start)])
            for index, item in enumerate(object_):
                if debug:
                    print("  list key:", key, " index: " + str(index), "vals: ", item)
                sub = -1
                if isinstance(item, dict):
                    first_value = next(iter(item.values()))
                    if isinstance(first_value, float):
                        sub = first_value
                if not isnan(sub) and index < max_list_index:
                    if index > 0:
                        global_max_record = int(max(list(list_prebuilt_flattened_dict.keys())))
                        list_prebuilt_flattened_dict[str(global_max_record + 1)] = copy_deepcopy(entry)
                    _flatten_low_entropy(item, key, cur_depth, max_depth_inner)
            list_prebuilt_flattened_dict["0"] = [
                subel for k, v in sorted(list_prebuilt_flattened_dict.items()) for idx, subel in enumerate(v)
            ]
            for key in sorted(list_prebuilt_flattened_dict.keys()):
                if key != "0":
                    del list_prebuilt_flattened_dict[key]
            if debug:
                print("collapsed global list")
        else:
            global_max_record = int(max(list(list_prebuilt_flattened_dict.keys())))
            for d in list_prebuilt_flattened_dict[str(global_max_record)]:
                d[key] = object_
        cur_depth -= 1

    _flatten(nested_dict, None)
    reskeys = list(flattened_dict.keys())
    unique_integers = list({(separator + char) for key in reskeys for char in key if char.isdigit()})
    regex = "|".join(unique_integers)
    regex += "|" + regex.replace(".", "")
    unique_columns = list({re.sub("(" + regex + ")", "", key) for key in reskeys})
    prebuilt_flattened_dict = dict.fromkeys(unique_columns)
    list_prebuilt_flattened_dict = {"0": [prebuilt_flattened_dict]}
    _flatten_low_entropy(nested_dict, None, cur_depth=0, max_depth_inner=max_depth)
    return list_prebuilt_flattened_dict["0"]


def _unflatten_asserts(flat_dict, separator) -> None:
    assert isinstance(flat_dict, dict), "un_flatten requires dictionary input"
    assert isinstance(separator, str), "separator must be string"
    assert all(
        not value or not isinstance(value, Iterable) or isinstance(value, str) for value in flat_dict.values()
    ), "provided dict is not flat"


def unflatten(flat_dict, separator: str = "_"):
    _unflatten_asserts(flat_dict, separator)
    unflattened_dict = {}

    def _unflatten(dic, keys, value) -> None:
        for key in keys[:-1]:
            dic = dic.setdefault(key, {})
        dic[keys[-1]] = value

    list_keys = sorted(flat_dict.keys())
    for i, item in enumerate(list_keys):
        if i != len(list_keys) - 1:
            split_key = item.split(separator)
            next_split_key = list_keys[i + 1].split(separator)
            if split_key != next_split_key[:-1]:
                _unflatten(unflattened_dict, item.split(separator), flat_dict[item])
        else:
            _unflatten(unflattened_dict, item.split(separator), flat_dict[item])
    return unflattened_dict


def unflatten_list(flat_dict, separator: str = "_"):
    _unflatten_asserts(flat_dict, separator)
    unflattened_dict = unflatten(flat_dict, separator)

    def _convert_dict_to_list(object_, parent_object, parent_object_key: int | None) -> None:
        if isinstance(object_, dict):
            for key in object_:
                if isinstance(object_[key], dict):
                    _convert_dict_to_list(object_[key], object_, key)
            try:
                keys = [int(key) for key in object_]
                keys.sort()
            except (ValueError, TypeError):
                keys = []
            keys_len = len(keys)
            if (
                keys_len > 0
                and sum(keys) == int((keys_len - 1) * keys_len / 2)
                and keys[0] == 0
                and keys[-1] == keys_len - 1
                and check_if_numbers_are_consecutive(keys)
            ):
                parent_object[parent_object_key] = []
                for key_index, key in enumerate(keys):
                    parent_object[parent_object_key].append(object_[str(key)])
                    _convert_dict_to_list(
                        parent_object[parent_object_key][-1],
                        parent_object[parent_object_key],
                        key_index,
                    )

    _convert_dict_to_list(unflattened_dict, None, None)
    return unflattened_dict


def flatten_wrapper(content) -> str:
    input_json = json.loads(content)
    return json.dumps(flatten(input_json))


def stdin_to_stdout(func, input_stream=sys_stdin, output_stream=sys_stdout) -> None:
    raw = input_stream.read()
    output = func(raw)
    output_stream.write(f"{output}\n")
    output_stream.flush()
