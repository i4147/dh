from dh import STDLIB, STDLIB2


print(len(list(STDLIB)))
uniqstd = list(set(STDLIB))
print(f"uniq :{len(uniqstd)}")
print(len(list(STDLIB2)))
diff_std = [p for p in STDLIB if not p in STDLIB2]
with open("std_diff", "w") as f:
    f.writelines(f"{k}\n" for k in diff_std)
