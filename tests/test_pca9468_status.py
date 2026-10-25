"""Compile the real PCA9468 status function with deterministic I2C/log shims.

Run from the kernel root: python3 tests/test_pca9468_status.py --verify-regression
The fixture checks error propagation and log levels, not hardware charging.
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
    match = re.search(r"^static int " + name + r"\([^;{]+\)\s*\{", source, re.MULTILINE)
    if match is None:
        raise ValueError("missing function: " + name)
    opening = source.index("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():index + 1]
    raise ValueError("unbalanced function")


def register_definitions(header, function):
    names = set(re.findall(r"\bPCA9468_[A-Z0-9_]+\b", function))
    definitions = []
    for name in sorted(names):
        match = re.search(r"^#define\s+" + re.escape(name) + r"\s+[^\n]+", header, re.MULTILINE)
        if match is None:
            raise ValueError("missing register definition: " + name)
        # The first DC_VBAT_MIN definition is the CONFIG_BATTERY_SAMSUNG branch.
        definitions.append(match.group())
    adc = re.search(r"enum\s*\{\s*ADCCH_VOUT[^}]+\};", header)
    if adc is None:
        raise ValueError("missing ADC enum")
    return "\n".join(definitions) + "\n" + adc.group() + "\n"


@contextmanager
def build_directory(parent):
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / ("pca9468-test-" + uuid.uuid4().hex)
    target.mkdir(mode=0o777)
    try:
        yield target
    finally:
        if target.resolve().parent != parent:
            raise RuntimeError("unexpected build directory")
        shutil.rmtree(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cc", default=os.environ.get("HOSTCC"))
    parser.add_argument("--build-dir", type=Path, default=Path("work"))
    parser.add_argument("--verify-regression", action="store_true")
    args = parser.parse_args()
    compiler = args.cc or next((shutil.which(x) for x in ("cc", "gcc", "clang", "tcc")
                               if shutil.which(x)), None)
    if compiler is None:
        parser.error("no host C compiler; specify --cc")
    source = (args.source_root / "drivers/battery_v2/pca9468_charger.c").read_text(encoding="utf-8")
    header = (args.source_root / "drivers/battery_v2/include/charger/pca9468_charger.h").read_text(encoding="utf-8")
    function = extract_function(source, "pca9468_check_error")
    with build_directory(args.build_dir) as directory:
        (directory / "pca9468_registers_under_test.h").write_text(
            register_definitions(header, function), encoding="utf-8")
        function_header = directory / "pca9468_function_under_test.h"
        binary = directory / ("pca9468-check.exe" if os.name == "nt" else "pca9468-check")

        def run(code):
            function_header.write_text(code, encoding="utf-8")
            subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra", "-I", str(directory),
                            str(Path(__file__).with_name("pca9468_status_harness.c")),
                            "-o", str(binary)], check=True)
            return subprocess.run([str(binary)], capture_output=True, text=True)

        result = run(function)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        if result.returncode:
            return 1
        if args.verify_regression:
            guard = ("\t\t\tret = pca9468_read_reg(pca9468, PCA9468_REG_INT1_STS, &reg_val);\n"
                     "\t\t\tif (ret < 0)\n\t\t\t\tgoto error;\n")
            if guard not in function:
                raise ValueError("cannot reintroduce old bug: guard not found")
            old = function.replace(guard, guard.split("\n", 1)[0] + "\n", 1)
            regressed = run(old)
            if not regressed.returncode or "FAIL " not in regressed.stdout:
                raise RuntimeError("fixture did not detect the original I2C-read failure")
            print("PASS: reintroduced ignored-I2C-error regression detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
