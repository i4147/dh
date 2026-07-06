import subprocess
import tempfile
from pathlib import Path

readme_markdown = ""
with tempfile.TemporaryDirectory() as tmpdir:
    tmp_path = Path(tmpdir)
    subprocess.run(
        [
            "sphinx-build",
            "-M",
            "markdown",
            "./docs",
            str(tmp_path),
        ],
        check=True,
    )
    index_file = tmp_path / "markdown" / "index.md"
    readme_markdown = index_file.read_text(encoding="utf-8")
Path("README.md").write_text(readme_markdown, encoding="utf-8")
