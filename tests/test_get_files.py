from dh import get_files, get_pyfiles


for path in get_files(".", ext=[".py"]):
    print(path, end=", ")
print()
for path in get_pyfiles("."):
    print(path, end=", ")
print()
