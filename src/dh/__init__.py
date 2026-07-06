from .archiveutils import compress, decompress, is_valid_archive, xtar
from .const import (
    ARCHIVE_EXT,
    AUDIO_EXT,
    BIN_EXT,
    BOOK_EXT,
    CSS_COLORS,
    DOC_TH1,
    DOC_TH2,
    DOCTH,
    DOCUMENT_EXT,
    EXT2MIME,
    FONT_EXT,
    IMG_EXT,
    MAX_WORKERS,
    MIME2EXT,
    MOVIE_EXT,
    PKG_MAPPING,
    PY_KEYWORDS,
    SOURCE_CODE_EXT,
    STDLIB,
    TXT_EXT,
    black,
    blink,
    blue,
    bold,
    consealed,
    cyan,
    green,
    grey,
    greyblack,
    greywhite,
    lblue,
    lcyan,
    lgreen,
    lmagenta,
    lred,
    lyellow,
    magenta,
    red,
    reset,
    reverse,
    underline,
    white,
    yellow,
)
from .cprint import cprint
from .curl import cdownload
from .expand_arg import expand_arg
from .fautils import georgian_to_hijri, get_persian_date, gregorian_to_jalali
from .fileutils import (
    append_text,
    format_size,
    format_time,
    fsz,
    get_dirs,
    get_file_age,
    get_files,
    get_filez,
    get_installed_packages,
    get_installed_pkgs,
    get_ipackages,
    get_ipkgs,
    get_mime_type,
    get_nobinary,
    get_pyfiles,
    get_random_filename,
    get_removed_lines,
    get_size,
    gext,
    gsz,
    is_binary,
    is_empty,
    is_image,
    is_python_file,
    is_text_file,
    is_within,
    normalize_filename,
    normalize_path,
    read_lines,
    read_lines_mmap,
    restore_bak,
    reverse_dict,
    rrs,
    runcmd,
    safe_delete,
    should_skip,
    unique_path,
    write_txt_file,
)
from .hashutils import content_hash, get_sha256
from .jobutils import (
    mpf,
    mpf3,
    mpf_async,
    mpf_imap,
    mpf_imap2,
    mpf_imap3,
    mpf_joblib,
    mpf_map,
    mpf_starmap,
    mpf_starmap2,
    mpf_starmap3,
)
from .logutils import init_logger
from .memutils import track_memory
from .utils import sunique
from .textutils import (
    clean_text,
    cosine_similarity,
    count_words,
    get_sentences,
    get_words,
    has_doc,
    is_alpha,
    is_alphanum,
    is_digit,
    is_lower,
    is_none_english,
    is_upper,
    jaccard_similarity,
    jaro_winkler_similarity,
    levenshtein_distance,
    levenshtein_similarity,
    partial_ratio,
    remove_blank_lines,
    remove_stop_words,
    sentiment_label,
    sentiment_score,
    tokenize,
)
from .urlutils import is_valid_url
from .visitor import JsonEncoder, Visitor

# fileutils
__all__ = [
    "append_text",
    "format_size",
    "format_time",
    "fsz",
    "get_dirs",
    "get_file_age",
    "get_files",
    "get_filez",
    "get_installed_packages",
    "get_installed_pkgs",
    "get_ipackages",
    "get_ipkgs",
    "get_mime_type",
    "get_nobinary",
    "get_pyfiles",
    "get_random_filename",
    "get_removed_lines",
    "get_size",
    "gext",
    "gsz",
    "is_binary",
    "is_empty",
    "is_image",
    "is_python_file",
    "is_text_file",
    "is_within",
    "normalize_filename",
    "normalize_path",
    "read_lines",
    "read_lines_mmap",
    "restore_bak",
    "reverse_dict",
    "rrs",
    "runcmd",
    "safe_delete",
    "should_skip",
    "unique_path",
    "write_txt_file",
]

# archiveutils
__all__ += ["compress", "decompress", "is_valid_archive", "xtar"]

# const
__all__ += [
    "ARCHIVE_EXT",
    "AUDIO_EXT",
    "BIN_EXT",
    "BOOK_EXT",
    "CSS_COLORS",
    "DOC_TH1",
    "DOC_TH2",
    "DOCTH",
    "DOCUMENT_EXT",
    "EXT2MIME",
    "FONT_EXT",
    "IMG_EXT",
    "MAX_WORKERS",
    "MIME2EXT",
    "MOVIE_EXT",
    "PKG_MAPPING",
    "PY_KEYWORDS",
    "SOURCE_CODE_EXT",
    "STDLIB",
    "TXT_EXT",
    "black",
    "blink",
    "blue",
    "bold",
    "consealed",
    "cyan",
    "green",
    "grey",
    "greyblack",
    "greywhite",
    "lblue",
    "lcyan",
    "lgreen",
    "lmagenta",
    "lred",
    "lyellow",
    "magenta",
    "red",
    "reset",
    "reverse",
    "underline",
    "white",
    "yellow",
]

# cprint
__all__ += ["cprint"]

# curl.py
__all__ += ["cdownload"]

# expand_arg
__all__ += ["expand_arg"]

# fautild
__all__ += ["georgian_to_hijri", "get_persian_date", "gregorian_to_jalali"]

# hashutils
__all__ += ["content_hash", "get_sha256"]

# jobutils
__all__ += [
    "mpf",
    "mpf3",
    "mpf_async",
    "mpf_imap",
    "mpf_imap2",
    "mpf_imap3",
    "mpf_joblib",
    "mpf_map",
    "mpf_starmap",
    "mpf_starmap2",
    "mpf_starmap3",
]

# logutils
__all__ += ["init_logger"]

# memutils
__all__ += ["track_memory"]

# utils
__all__ += ["sunique"]

# textutils
__all__ += [
    "clean_text",
    "cosine_similarity",
    "count_words",
    "get_sentences",
    "get_words",
    "has_doc",
    "is_alpha",
    "is_alphanum",
    "is_digit",
    "is_lower",
    "is_none_english",
    "is_upper",
    "jaccard_similarity",
    "jaro_winkler_similarity",
    "levenshtein_distance",
    "levenshtein_similarity",
    "partial_ratio",
    "remove_blank_lines",
    "remove_stop_words",
    "sentiment_label",
    "sentiment_score",
    "tokenize",
]

# urlutils
__all__ += ["is_valid_url"]

# jsonutils
__all__ += ["JsonEncoder", "Visitor"]
