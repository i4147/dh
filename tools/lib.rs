use pyo3::exceptions::PyOSError;
use pyo3::prelude::*;
use std::ffi::OsStr;
use std::fs::FileType;
use std::path::{Path, PathBuf};

const SKIPPED_DIRS: &[&str] = &[
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache", 
    ".pytest_cache",
];

/// Apply the same exclusions before jwalk schedules any directory's children.
fn new_walker(path: &Path, follow_links: bool) -> Option<jwalk::WalkDir> {
    // jwalk follows a symlink supplied as the root even when follow_links is
    // false, and a dangling root link would otherwise produce an error before
    // the filter runs. Strip trailing separators for this check so `link/` is
    // treated the same as `link`.
    if !follow_links && path.components().collect::<PathBuf>().is_symlink() {
        return None;
    }

    Some(
        jwalk::WalkDir::new(path)
            .follow_links(follow_links)
            // Preserve jwalk's existing default of omitting hidden children.
            .skip_hidden(true)
            .process_read_dir(move |_, _, _, entries| {
                entries.retain(|result| match result {
                    Ok(entry) => {
                        let skipped_link = !follow_links && entry.path_is_symlink();
                        let skipped_dir = entry.file_type().is_dir()
                            && SKIPPED_DIRS
                                .iter()
                                .any(|name| entry.file_name() == OsStr::new(name));
                        !skipped_link && !skipped_dir
                    }
                    // Preserve traversal errors rather than silently hiding them.
                    Err(_) => true,
                });
            }),
    )
}

fn walk_error(error: jwalk::Error) -> PyErr {
    PyOSError::new_err(format!("Error walking directory: {error}"))
}

fn collect_paths(
    walker: Option<jwalk::WalkDir>,
    include: impl Fn(FileType) -> bool,
) -> PyResult<Vec<PathBuf>> {
    let mut paths = Vec::new();
    if let Some(walker) = walker {
        for result in walker {
            let entry = result.map_err(walk_error)?;
            if include(entry.file_type()) {
                paths.push(entry.path());
            }
        }
    }
    Ok(paths)
}

#[pyfunction]
#[pyo3(signature = (path, follow_links=None))]
fn walk(path: PathBuf, follow_links: Option<bool>) -> PyResult<Vec<PathBuf>> {
    collect_paths(new_walker(&path, follow_links.unwrap_or(false)), |_| true)
}

#[pyfunction]
#[pyo3(signature = (path, follow_links=None))]
fn walk_files(path: PathBuf, follow_links: Option<bool>) -> PyResult<Vec<PathBuf>> {
    collect_paths(new_walker(&path, follow_links.unwrap_or(false)), |kind| {
        kind.is_file()
    })
}

#[pyfunction]
#[pyo3(signature = (path, follow_links=None))]
fn walk_dirs(path: PathBuf, follow_links: Option<bool>) -> PyResult<Vec<PathBuf>> {
    collect_paths(new_walker(&path, follow_links.unwrap_or(false)), |kind| {
        kind.is_dir()
    })
}

#[pyclass(from_py_object)]
#[derive(Clone)]
struct Entry {
    #[pyo3(get)]
    path: PathBuf,
    #[pyo3(get)]
    is_file: bool,
    #[pyo3(get)]
    is_dir: bool,
    #[pyo3(get)]
    is_symlink: bool,
    #[pyo3(get)]
    depth: usize,
}

#[pyfunction]
#[pyo3(signature = (path, follow_links=None, max_depth=None, min_depth=None))]
fn walk_with_metadata(
    path: PathBuf,
    follow_links: Option<bool>,
    max_depth: Option<usize>,
    min_depth: Option<usize>,
) -> PyResult<Vec<Entry>> {
    let follow = follow_links.unwrap_or(false);
    let Some(mut walker) = new_walker(&path, follow) else {
        return Ok(Vec::new());
    };
    if let Some(max) = max_depth {
        walker = walker.max_depth(max);
    }
    if let Some(min) = min_depth {
        walker = walker.min_depth(min);
    }

    let mut results = Vec::new();
    for result in walker {
        let entry = result.map_err(walk_error)?;
        let file_type = entry.file_type();
        let entry_path = entry.path();
        // A trailing slash makes the OS dereference a root link before jwalk
        // can recognize it. The returned path no longer has that separator.
        let is_symlink =
            entry.path_is_symlink() || (follow && entry.depth() == 0 && entry_path.is_symlink());
        results.push(Entry {
            path: entry_path,
            is_file: file_type.is_file(),
            is_dir: file_type.is_dir(),
            is_symlink,
            depth: entry.depth(),
        });
    }
    Ok(results)
}

#[pyfunction]
#[pyo3(signature = (path, follow_links=None, num_threads=None))]
fn walk_parallel(
    path: PathBuf,
    follow_links: Option<bool>,
    num_threads: Option<usize>,
) -> PyResult<Vec<PathBuf>> {
    let walker = new_walker(&path, follow_links.unwrap_or(false)).map(|walker| {
        walker.parallelism(jwalk::Parallelism::RayonNewPool(num_threads.unwrap_or(0)))
    });
    collect_paths(walker, |_| true)
}

#[pymodule]
fn fastwalk(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(walk, m)?)?;
    m.add_function(wrap_pyfunction!(walk_files, m)?)?;
    m.add_function(wrap_pyfunction!(walk_dirs, m)?)?;
    m.add_function(wrap_pyfunction!(walk_with_metadata, m)?)?;
    m.add_function(wrap_pyfunction!(walk_parallel, m)?)?;
    m.add_class::<Entry>()?;
    Ok(())
}
