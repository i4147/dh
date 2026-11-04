optimize this utility python pkg
merge fikeutils & pathutils
i sdd src of fastwalk in tools dir for refrence
remove extra file system walkers just keep the ones in pathutils.py
add type annotations and docstrings & comments to filrs
add pytest based tests and mdbook based docs, (build html docs too)
fix any type errors (make ty happy)
the get_files function in pathutils returns all files even if we pass ext=['.rst'], fix it
use fastwalk.walk and add an arguman named dirs_only to merge get_dirs (in get_files) too
