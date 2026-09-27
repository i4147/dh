from time import perf_counter
from termcolor import cprint
from dh import format_size, fsize, fsz
for i in range(0, 10000000, 10000):
    s1 = perf_counter()
    print(f"format_size ->{format_size(i)}", end=" | ")
    format_size_time = perf_counter() - s1
    cprint(f"{format_size_time:.6f}", "cyan")
    s2 = perf_counter()
    print(f"fsize ->{fsize(i)}", end=" | ")
    fsize_time = perf_counter() - s2
    cprint(f"{fsize_time:.6f}", "green")
    s3 = perf_counter()
    print(f"fsz ->{fsz(i)}", end=" | ")
    fsz_time = perf_counter() - s3
    cprint(f"{fsz_time:.6f}", "yellow")
    min_time = min(format_size_time, fsize_time, fsz_time)
    print(f"\n\033[05;96m{min_time}\033[0m\n")
    if min_time == format_size:
        cprint("format_size", "blue")
    if min_time == fsize:
        cprint("fsize", "magenta")
    if min_time == fsz:
        cprint("fsz", "red")
