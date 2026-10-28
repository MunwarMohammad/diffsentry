"""Map GitHub file patches to new-side coordinates; never execute repository code."""

import re

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_lines(patch: str):
    line = None
    for text in patch.splitlines():
        match = HUNK.match(text)
        if match:
            line = int(match.group(1))
        elif line is not None:
            if text.startswith("+"):
                yield line, text[1:]
                line += 1
            elif text.startswith(" "):
                line += 1
            elif text.startswith("-") or text.startswith("\\"):
                continue
            else:
                line = None


def prepare_files(files: list[dict], limit: int):
    included, warnings = [], []
    size = 0
    for file in files:
        path, patch = file["filename"], file.get("patch")
        if file.get("status") == "removed":
            warnings.append(f"{path}: deleted file excluded from new-line review")
            continue
        if not patch:
            warnings.append(f"{path}: no textual patch available (binary, empty, or oversized)")
            continue
        added = list(added_lines(patch))
        if file.get("additions", len(added)) != len(added):
            warnings.append(f"{path}: GitHub supplied an incomplete patch; excluded")
            continue
        if size + len(patch) + len(path) > limit:
            warnings.append(f"{path}: excluded by review size limit")
            continue
        size += len(patch) + len(path)
        included.append({"filename": path, "patch": patch})
    return included, warnings


def validate_findings(items, files, limit=30):
    allowed = {f["filename"]: {n for n, _ in added_lines(f["patch"])} for f in files}
    unique = {}
    rejected = 0
    rank = {"error": 0, "warning": 1, "info": 2}
    for item in items:
        if item.line not in allowed.get(item.file, set()):
            rejected += 1
            continue
        key = (item.file, item.line, " ".join(item.message.lower().split()))
        previous = unique.get(key)
        if previous is None or rank[item.severity] < rank[previous.severity]:
            unique[key] = item
    result = sorted(unique.values(), key=lambda f: (rank[f.severity], f.file, f.line, f.message))
    warnings = [f"Discarded {rejected} findings with invalid diff locations"] if rejected else []
    if len(result) > limit:
        warnings.append(f"Showing {limit} of {len(result)} validated findings")
    return result[:limit], warnings
