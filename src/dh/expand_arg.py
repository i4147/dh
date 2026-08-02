"""
File and Path Input Processor with Argument Expansion
Handles glob patterns, directories, and individual files using only pathlib
"""

import sys
from pathlib import Path


class Expander:
    def __init__(self, recursive: bool = False, follow_symlinks: bool = True) -> None:
        self.recursive = recursive
        self.follow_symlinks = follow_symlinks

    def expand_glob_patterns(self, patterns: list[str]) -> set[Path]:
        expanded = set()
        for pattern in patterns:
            path_pattern = Path(pattern)
            if path_pattern.is_absolute():
                parts = path_pattern.parts
                root = Path(parts[0]) if sys.platform == "win32" else Path("/")
                remaining = str(Path(*parts[1:])) if len(parts) > 1 else ""
                if self.recursive:
                    matched = root.glob(f"**/{remaining}" if remaining else "**/*")
                else:
                    matched = root.glob(remaining)
            elif self.recursive:
                matched = Path.cwd().glob(f"**/{pattern}")
            else:
                matched = Path.cwd().glob(pattern)
            for path in matched:
                if self.follow_symlinks and path.is_symlink():
                    try:
                        resolved = path.resolve()
                        if resolved.exists():
                            expanded.add(resolved)
                    except (RuntimeError, OSError):
                        continue
                else:
                    expanded.add(path.absolute())
        return expanded

    def expand_directory(self, directory: Path) -> list[Path]:
        if not directory.exists():
            msg = f"Directory not found: {directory}"
            raise FileNotFoundError(msg)
        if not directory.is_dir():
            msg = f"Not a directory: {directory}"
            raise NotADirectoryError(msg)
        files = []
        if self.recursive:
            for item in directory.rglob("*"):
                if self._is_valid_file(item):
                    path = item.resolve() if self.follow_symlinks else item.absolute()
                    if path.is_file():
                        files.append(path)
        else:
            for item in directory.glob("*"):
                if self._is_valid_file(item):
                    path = item.resolve() if self.follow_symlinks else item.absolute()
                    if path.is_file():
                        files.append(path)
        return files

    def _is_valid_file(self, path: Path) -> bool:
        if self.follow_symlinks and path.is_symlink():
            try:
                resolved = path.resolve()
                return resolved.is_file()
            except (RuntimeError, OSError):
                return False
        return path.is_file()

    def is_pattern(self, input_str: str) -> bool:
        pattern_chars = "*?[]{}!"
        return any(char in input_str for char in pattern_chars)

    def process_inputs(self, inputs: list[str]) -> list[Path]:
        if not inputs:
            return []
        if isinstance(inputs, str):
            inputz = [inputs]
        elif isinstance(inputs, list):
            inputz = inputs
        else:
            msg = "input type error"
            raise TypeError(msg)
        expanded_paths = set()
        glob_patterns = []
        direct_paths = []
        for input_item in inputz:
            if self.is_pattern(input_item):
                glob_patterns.append(input_item)
            else:
                direct_paths.append(input_item)
        if glob_patterns:
            pattern_expanded = self.expand_glob_patterns(glob_patterns)
            expanded_paths.update(pattern_expanded)
        for path_str in direct_paths:
            path = Path(path_str)
            if self.follow_symlinks:
                try:
                    path = path.resolve()
                except (RuntimeError, OSError):
                    path = path.absolute()
            else:
                path = path.absolute()
            if not path.exists():
                print(f"Warning: Path does not exist: {path}", file=sys.stderr)
                continue
            if path.is_dir():
                try:
                    dir_files = self.expand_directory(path)
                    expanded_paths.update(dir_files)
                except (NotADirectoryError, FileNotFoundError) as e:
                    print(f"Warning: {e}", file=sys.stderr)
            elif path.is_file():
                expanded_paths.add(path)
            elif path.is_symlink() and self.follow_symlinks:
                try:
                    resolved = path.resolve()
                    if resolved.is_file():
                        expanded_paths.add(resolved)
                    elif resolved.is_dir() and self.recursive:
                        dir_files = self.expand_directory(resolved)
                        expanded_paths.update(dir_files)
                except (RuntimeError, OSError):
                    print(f"Warning: Broken symlink: {path}", file=sys.stderr)
        return sorted(expanded_paths)

    def get_files_only(self, inputs: list[str], extensions: list[str] | None = None) -> list[Path]:
        all_paths = self.process_inputs(inputs)
        if extensions:
            extensions = [(ext.lower() if not ext.startswith(".") else ext.lower()) for ext in extensions]
            return [p for p in all_paths if p.suffix.lower() in extensions or (p.suffix == "" and "" in extensions)]
        return all_paths

    def get_directories_only(self, inputs: list[str]) -> list[Path]:
        all_paths = self.process_inputs(inputs)
        return [p for p in all_paths if p.is_dir()]

    def get_files_by_pattern(self, inputs: list[str], name_pattern: str | None = None) -> list[Path]:
        all_paths = self.process_inputs(inputs)
        if name_pattern:
            return [p for p in all_paths if p.match(name_pattern)]
        return all_paths


def expand_arg(inputs: list[str]) -> list[Path]:
    ex = Expander(recursive=True, follow_symlinks=False)
    return ex.process_inputs(inputs)
