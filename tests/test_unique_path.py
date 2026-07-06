import re
from dh import unique_path


c = "f_1_2_3.py"

c1 = re.sub(r"(_\d+)+", "", c)
print(c1)

c2 = unique_path(c)
print(c2)
