from dh import get_files, get_pyfiles, get_nobinary, get_dirs

for p in get_files("."):
    print(p)
for p in get_pyfiles("."):
    print(p)
for p in get_nobinary("."):
    print(p)
for p in get_dirs("."):
    print(p)
