from pathlib import Path

# ===== 설정 =====
ROOT = Path(__file__).resolve().parent
OUTDIR = ROOT / "_project_sources"
EXCLUDE_INIT = True

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "_project_sources",
    ".idea",
    ".pytest_cache",
}

TARGET_EXTENSIONS = {
    ".py",
    ".js",
    ".css",
    ".html",
    ".json",
    ".md",     # 문서
    ".yml",    # CI/CD, 설정
    ".yaml",
    ".txt"
}
# ================


def is_excluded_dir(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)

CURRENT_FILE = Path(__file__).resolve()

def get_target_files_in_folder(folder: Path):
    files = []
    for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        if p.resolve() == CURRENT_FILE:   # ← 추가
            continue
        if p.suffix.lower() not in TARGET_EXTENSIONS:
            continue
        if EXCLUDE_INIT and p.name == "__init__.py":
            continue
        files.append(p)
    return files


def folder_to_output_name(folder: Path, root: Path) -> str:
    rel = folder.relative_to(root)
    if not rel.parts:
        return "root.txt"
    return "_".join(rel.parts) + ".txt"


def build_folder_header(folder: Path, root: Path, target_files: list[Path]) -> str:
    rel = folder.relative_to(root)
    rel_str = "." if str(rel) == "." else rel.as_posix()

    lines = [
        "=" * 80,
        f"FOLDER: {rel_str}",
        f"FILE COUNT: {len(target_files)}",
        "=" * 80,
        "",
        "FILES:",
    ]

    for f in target_files:
        lines.append(f"- {f.name}")

    lines.extend(["", ""])
    return "\n".join(lines) + "\n"


def build_file_block(file_path: Path, root: Path) -> str:
    rel_path = file_path.relative_to(root).as_posix()

    try:
        code = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        code = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        code = f"[읽기 실패] {e}"

    lines = [
        "#" * 80,
        f"FILE: {file_path.name}",
        f"PATH: {rel_path}",
        f"EXT: {file_path.suffix.lower()}",
        "#" * 80,
        "",
        code.rstrip(),
        "",
        "",
    ]
    return "\n".join(lines)


def export_sources():
    OUTDIR.mkdir(exist_ok=True)

    exported_count = 0

    # ROOT 자신도 포함
    folders = [ROOT] + sorted([p for p in ROOT.rglob("*") if p.is_dir()])

    for folder in folders:
        if folder == OUTDIR:
            continue
        if is_excluded_dir(folder):
            continue

        target_files = get_target_files_in_folder(folder)
        if not target_files:
            continue

        out_name = folder_to_output_name(folder, ROOT)
        out_path = OUTDIR / out_name

        content_parts = [
            build_folder_header(folder, ROOT, target_files)
        ]

        for file_path in target_files:
            content_parts.append(build_file_block(file_path, ROOT))

        out_text = "".join(content_parts)

        out_path.write_text(out_text, encoding="utf-8", newline="\n")
        exported_count += 1
        print(f"[OK] {out_path.relative_to(ROOT)}")

    print()
    print(f"완료: {exported_count}개 txt 생성")
    print(f"출력 폴더: {OUTDIR}")


if __name__ == "__main__":
    export_sources()