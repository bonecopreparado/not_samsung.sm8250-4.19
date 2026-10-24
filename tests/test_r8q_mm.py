#!/usr/bin/env python3
"""Compile and run selected kernel MM functions against a small host fixture.

This is a focused logic/ordering regression test, not a kernel build or a
substitute for on-device memory-pressure and lockdep testing. It extracts the
function bodies from the source tree supplied with --source-root; the C fixture
models the 4.19 aggregate WORKINGSET_* counters and the relevant locking API.

Example:
  python3 tests/test_r8q_mm.py --source-root . --cc cc --verify-regressions
"""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


def extract_function(source, name):
    """Extract a complete definition, allowing comments/strings with braces."""
    pattern = r"^[^\n;{}]*\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{"
    match = re.search(pattern, source, re.MULTILINE)
    if match is None:
        raise ValueError("function definition not found: " + name)
    masked = re.sub(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        lambda m: "".join("\n" if ch == "\n" else " " for ch in m.group()),
        source,
        flags=re.DOTALL,
    )
    opening = masked.index("{", match.start())
    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():index + 1]
    raise ValueError("unbalanced function definition: " + name)


def generate(source_root, mutation=None):
    workingset = (source_root / "mm/workingset.c").read_text(encoding="utf-8")
    vmscan = (source_root / "mm/vmscan.c").read_text(encoding="utf-8")
    functions = {
        name: extract_function(workingset, name)
        for name in (
            "pack_shadow", "unpack_shadow", "page_lru_refs",
            "lru_gen_eviction", "lru_gen_refault",
        )
    }
    walker = extract_function(vmscan, "walk_mm")
    if mutation == "refault":
        increment = "\tmod_lruvec_state(lruvec, WORKINGSET_REFAULT, delta);\n"
        if increment not in functions["lru_gen_refault"]:
            raise ValueError("cannot inject the old refault bug: fixed increment missing")
        functions["lru_gen_refault"] = functions["lru_gen_refault"].replace(increment, "", 1)
        anchor = "\tmin_seq = READ_ONCE(lrugen->min_seq[type]);"
        functions["lru_gen_eviction"] = functions["lru_gen_eviction"].replace(
            anchor,
            "\tmod_lruvec_state(lruvec, WORKINGSET_REFAULT + type, delta);\n\n" + anchor,
            1,
        )
    elif mutation == "rcu":
        fixed = "\t\tmem_cgroup_unlock_pages();\n\t\tcond_resched();"
        if fixed not in walker:
            raise ValueError("cannot inject the old RCU bug: fixed ordering missing")
        walker = walker.replace(
            fixed, "\t\tcond_resched();\n\t\tmem_cgroup_unlock_pages();", 1,
        )
    fixture = Path(__file__).with_name("r8q_mm_fixture.c").read_text(encoding="utf-8")
    return fixture.replace("/* EXTRACT_WORKINGSET_FUNCTIONS */", "\n\n".join(functions.values())).replace(
        "/* EXTRACT_WALK_MM */", walker,
    )


def compile_and_run(cc, code, directory, name):
    source = directory / (name + ".c")
    binary = directory / (name + (".exe" if os.name == "nt" else ""))
    source.write_text(code, encoding="utf-8")
    built = subprocess.run(
        [cc, "-std=c99", "-Wall", "-Wextra", str(source), "-o", str(binary)],
        text=True, capture_output=True,
    )
    if built.returncode:
        raise RuntimeError("host fixture compilation failed:\n" + built.stdout + built.stderr)
    result = subprocess.run([str(binary)], text=True, capture_output=True)
    return result


@contextmanager
def build_directory(parent):
    # Ordinary inherited permissions also work with restricted Windows tokens;
    # TemporaryDirectory's owner-only ACL can make its contents inaccessible.
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    directory = parent / ("r8q-mm-tests-" + uuid.uuid4().hex)
    directory.mkdir(mode=0o777)
    try:
        yield directory
    finally:
        if directory.resolve().parent != parent:
            raise RuntimeError("refusing to clean a build outside its parent directory")
        shutil.rmtree(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("."))
    parser.add_argument("--cc", default=os.environ.get("HOSTCC"))
    parser.add_argument("--build-dir", type=Path, default=Path("work"),
                        help="parent directory for temporary host build files")
    parser.add_argument("--verify-regressions", action="store_true",
                        help="also reintroduce each old bug and require its fixture to fail")
    args = parser.parse_args()
    cc = args.cc or next((shutil.which(x) for x in ("cc", "gcc", "clang", "tcc") if shutil.which(x)), None)
    if cc is None:
        parser.error("no host C compiler found; pass --cc /path/to/compiler")
    try:
        with build_directory(args.build_dir) as directory:
            result = compile_and_run(cc, generate(args.source_root), directory, "current")
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            if result.returncode:
                return 1
            if args.verify_regressions:
                for mutation in ("refault", "rcu"):
                    result = compile_and_run(cc, generate(args.source_root, mutation), directory, mutation)
                    if not result.returncode or "FAIL " not in result.stdout:
                        raise RuntimeError("fixture did not detect reintroduced " + mutation + " regression")
                    print("PASS reintroduced " + mutation + " regression detected")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
