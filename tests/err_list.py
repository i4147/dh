from dh import STDLIB, STDLIB2
from isort.stdlibs import py2, py3

df2 = [p for p in py2.stdlib if not p in py3.stdlib]
with open("onlypy2", "w") as f2:
    for k2 in df2:
        f2.write(f"{k2}\n")
df3 = [p for p in py3.stdlib if not p in py2.stdlib]
with open("onlypy3", "w") as f3:
    for k3 in df3:
        f3.write(f"{k3}\n")
df23 = [p for p in (py3.stdlib or py2.stdlib)]
with open("2or3", "w") as f23:
    for k23 in df23:
        f23.write(f"{k23}\n")
df2and3 = [p for p in (py3.stdlib and py2.stdlib)]
with open("2and3", "w") as f2and3:
    for k2and3 in df2and3:
        f2and3.write(f"{k2and3}\n")
df2a3 = [p for p in py3.stdlib if p in py2.stdlib]
with open("2a3", "w") as f2a3:
    for k2a3 in df2a3:
        f2a3.write(f"{k2a3}\n")
dfo = [p for p in STDLIB2 if p not in STDLIB]
with open("onlypy2o", "w") as f2o:
    for k2o in dfo:
        f2o.write(f"{k2o}\n")
err = {
    "_bootlocale",
    "_bootsubprocess",
    "_msi",
    "_overlapped",
    "_scproxy",
    "_sha256",
    "_sha512",
    "_uuid",
    "_winapi",
    "_wmi",
    "aix_support",
    "blake2",
    "codecs_cn",
    "codecs_hk",
    "codecs_iso2022",
    "codecs_jp",
    "codecs_kr",
    "codecs_tw",
    "collections_abc",
    "compat_pickle",
    "curses_panel",
    "distutils.bcppcompiler",
    "distutils.command.bdist_msi",
    "distutils.command.bdist_packager",
    "distutils.command.bdist_wininst",
    "distutils.command.register",
    "distutils.command.upload",
    "distutils.config",
    "distutils.msvc9compiler",
    "distutils.msvccompiler",
    "distutils_hack",
    "elementtree",
    "encodings.mac_centeuro",
    "encodings.mbcs",
    "encodings.oem",
    "frozen_importlib",
    "frozen_importlib_external",
    "importlib._common",
    "lib.libpython3",
    "lib2to3.__main__",
    "lib2to3.pgen2.conv",
    "lsprof",
    "markupbase",
    "msi",
    "multibytecodec",
    "multiprocessing.popen_spawn_win32",
    "osx_support",
    "overlapped",
    "posixshmem",
    "posixsubprocess",
    "py_abc",
    "pydatetime",
    "pydecimal",
    "pyio",
    "pylong",
    "scproxy",
    "sha1",
    "sha2",
    "sha3",
    "sitebuiltins",
    "strptime",
    "threading_local",
    "unittest.__main__",
    "venv.__main__",
    "weakrefset",
    "winapi",
    "wmi",
}
lastdf = [p for p in STDLIB if p in err]
with open("not_found", "w") as fo:
    for x in lastdf:
        fo.write(f"{x}\n")
