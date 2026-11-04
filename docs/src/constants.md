# Constants and file classification

Extension sets are immutable `frozenset[str]` values, normalized to lowercase
with leading dots. `TEXT_EXTENSIONS` and `BINARY_EXTENSIONS` are disjoint.
`is_text_file` matches suffixes case-insensitively and samples content when no
unambiguous extension or text basename hint exists. These hints are convenience
heuristics, not file-format validation or a security boundary.

## Corrections

- Compiled `.class`/`.pyc` files and Office `.doc`/`.docx` containers are binary.
- Textual `.ass`, `.tsv`, `.pem`, `.xbm`, `.xpm`, `.afm`, `.bdf`, `.dae`, and
  `.dxf` files no longer have binary-only hints.
- `.ts` (TypeScript/MPEG transport stream), `.plist` (XML/binary plist), `.obj`,
  `.stl`, `.fbx`, `.vtk`, `.pot`, `.mod`, `.pth`, certificate files, and portable
  bitmap formats have ambiguous representations. Neither set forces their type;
  they use the existing content sampler. UTF-16 and unusual encodings can still
  be misclassified by that heuristic.
- Unsupported wildcard-looking entries and questionable suffixes were removed
  from the binary allowlist; unknown extensions use content sampling instead.
- Exact text names such as `README`, `Makefile`, `.gitignore`, and `.env` belong
  in `TEXT_FILENAMES`, not extension tables. The classifier checks both.

## Other values

`STDLIB` uses the current interpreter's `sys.stdlib_module_names`, removing the
stale Python 2/platform-specific inventory. `PY_KEYWORDS` retains its historical
role as an identifier vocabulary (keywords, soft keywords, builtins, `self`, and
`cls`), but derives these names from the current interpreter instead of a stale
list. It is not a strict keyword-only set; use `keyword.iskeyword` for that.

CSS named colors include the CSS3 set plus `rebeccapurple`, with corrected
`aliceblue` and `midnightblue` RGB values. ANSI yellow and dim/grey escape strings
are corrected. Duplicate MIME keys are removed, and OpenType uses `font/otf`.
MIME reverse aliases remain intentionally many-to-one for compatibility.

Archive/audio/video categories include common omitted formats; font/image/document
categories no longer include unrelated generic binary, audio-only, or database
suffixes. Category membership describes the kind of file, not whether it is text.

Default `SKIP_DIRS` excludes generated output, environments, and tool metadata.
It no longer excludes ordinary source/package names (`numpy`, `pandas`, `pip`,
`scipy`, `mypy`, `cython`) or `.github`. Hidden directories are still omitted by
`get_files`; lower-level legacy walkers can include hidden files. Passing an
explicit skip set replaces the defaults rather than extending them.
