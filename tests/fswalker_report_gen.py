from dh import ReportGenerator, get_filez
def example_usage():
    print(f"{BOLD}Example 1: Walk filesystem{BOLD}")
    config = FileWalkerConfig(skip_dirs={".git", "__pycache__"}, file_pattern="*.py")
    files = list(get_filez(["/sdcard"], config))
    print(f"Found {len(files)} Python files\n")
    print(f"{BOLD}Example 2: Custom filter{RESET}")
    def large_file_filter(path: Path) -> bool:
        return path.stat().st_size > 1024
    files = list(get_filez(["/data/data/com.termux/files/home/repos"], config=None, file_filter=large_file_filter))
    print(f"Found {len(files)} files > 1KB\n")
    print(f"{BOLD}Example 3: Generate report{RESET}")
    report = ReportGenerator("File Analysis Report")
    report.add_item(ReportItem("src/main.py", "success", "Processed successfully"))
    report.add_item(ReportItem("src/old.py", "binary", "Skipped binary file"))
    report.add_item(ReportItem("data/config.json", "error", "Permission denied"))
    report.add_item(ReportItem("data/cache.tmp", "warning", "File is temporary"))
    report.add_stat("total_files", 100)
    report.add_stat("files_modified", 75)
    report.add_stat("lines_removed", 5000)
    report.print_report(show_all=True)
    report.export_to_file(Path("report.txt"), format="text")
    report.export_to_file(Path("report.csv"), format="csv")
    print(f"{GREEN}Reports exported to report.txt and report.csv{RESET}")
if __name__ == "__main__":
    example_usage()
