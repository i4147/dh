# Commands and terminal text

```python
import sys
from dh import runcmd

code, stdout, stderr = runcmd(
    [sys.executable, "-c", "print('hello')"],
    show_output=False,
    timeout=5,
)
assert (code, stdout, stderr) == (0, "hello\n", "")
```

Commands use argument vectors without a shell. Standard input is disconnected;
stdout and stderr are captured separately. `show_output=True` emits the cleaned
streams after the process finishes, rather than streaming live output.

`dh.utils.clean_terminal_transcript` removes ANSI/OSC escapes, control characters,
backspace artifacts, and carriage-return progress updates. It trims trailing
whitespace, collapses long blank-line runs, and terminates nonempty output with a
newline. `runcmd` preserves truly empty streams as `""`.

## Failures

| Exit code | Meaning |
| --- | --- |
| process code | Normal subprocess completion, including nonzero failures |
| 127 | Executable not found |
| 126 | Permission denied |
| 124 | Timeout; available partial stdout/stderr are preserved |
| 1 | Other operating-system or unexpected execution error |

Failure diagnostics go through the same cleanup and emission path as normal
output. The internal failure handler does not recursively execute another command
just to report an error. Invalid empty commands raise `ValueError`; non-string
arguments raise `TypeError` before subprocess execution.
