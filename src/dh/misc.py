def sunique(seq):
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


def version_to_tuple(version: str):
    from re import match as re_match

    pattern = r"(?P<major>\\d+).(?P<minor>\\d+).(?P<patch>\\d+)(?P<rest>.*)"
    matchz = re_match(pattern, version)
    parts: list[int] = [int(matchz[part]) for part in ["major", "minor", "patch"]]
    if matchz["rest"]:
        parts.append(matchz["rest"])
    return tuple(parts)
