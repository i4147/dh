from __future__ import annotations


def on_progress(done, total):
    pct = 100 * done / total if total else 0
    print(f"\r{pct:5.1f}%  ({done:,}/{total:,} bytes)", end="")


compressor = ParallelBrotliCompressor(
    quality=1,
    chunk_size=8 * 1024 * 1024,
    workers=8,
    progress_callback=on_progress,
)
compressor.compress_file("bigfile.bin", "bigfile.pbrt")
print()
ParallelBrotliCompressor.decompress_file("bigfile.pbrt", "bigfile.out")
compressor = ParallelBrotliCompressor(
    quality=3,
    chunk_size=4 * 1024 * 1024,
    mode=brotli.MODE_TEXT,
)
compressor.compress_file("huge.json", "huge.json.pbrt")
