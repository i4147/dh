import random

from dh import cprint

colors = ("red", "green", "yellow", "blue", "cyan", "magenta", "grey", "white")

for i in range(0, 255):
    cprint(f"{i} ", random.choice(colors), end=" ")
