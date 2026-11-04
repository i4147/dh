# task 
# # optimize utility python module

- merge fileutils & pathutils
I added src of fastwalk in tools dir for reference

- add type annotations and docstrings & comments to files

- add pytest based tests and mdbook based docs, (build html docs too)

- fix any type errors (make ty happy)

- the get_files function in pathutils returns all files even if we pass ext=['.rst'], fix it
use fastwalk.walk and add an argument named dirs_only to merge get_dirs (in get_files) too

- in fileutils.py refactor runcmd to return cleaned output, using clean_terminal_transcript function in utils.py
  also rewrite fail function (around line 740) to use runcmd function

