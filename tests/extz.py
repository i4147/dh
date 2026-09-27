#!/data/data/com.termux/files/usr/bin/python
import sys
from pathlib import Path
from dh import BIN_EXT, TXT_EXT
def main():
    extz = []
    for k in BIN_EXT:
        extz.append(k)
    for x in TXT_EXT:
        extz.append(x)
    with open("extz", "w") as f:
        for j in extz:
            f.write(j)
            f.write("\n")
if __name__ == "__main__":
    sys.exit(main())
