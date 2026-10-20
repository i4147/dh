from dh import get_ipackages, get_ipkgs


errs = 0
for pkg, ver in get_ipackages().items():
    if pkg is not None and ver is not None:
        print(f"{pkg} : {ver}")
    else:
        errs += 1
        print("there is a none element in ipackages output")
for pkgname in get_ipkgs():
    if pkgname is not None:
        print(f"{pkgname}")
    else:
        errs += 1
        print("there is a none element in ipkgs output")
print(f"done with {errs} errors")
