"""Exercise the real cpufreq_limit sysfs handlers with small host shims.

Run: python3 tests/test_cpufreq_limit.py
CC selects a GCC, Clang or TCC-compatible host compiler (default: cc/gcc/clang/tcc).
HOST_TEST_OUTPUT_DIR may name an existing writable directory instead of temp.
CPUFREQ_LIMIT_SOURCE can override the driver source for reproducing old bugs.

The C harness extracts production handlers, but simulates kernel types and the
kstrtouint API. Passing it does not mean the kernel was compiled or boot-tested.
"""
from contextlib import nullcontext
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def compiler_command():
    configured = os.environ.get("CC")
    if configured:
        if Path(configured).is_file():
            return [configured]
        return [part.strip('"') for part in
                shlex.split(configured, posix=os.name != "nt")]
    for candidate in ("cc", "gcc", "clang", "tcc"):
        executable = shutil.which(candidate)
        if executable:
            return [executable]
    return None


def extract_handlers(source):
    """Keep the original macro, constants and functions unchanged."""
    def function(name):
        start = source.index("static ssize_t " + name + "(")
        brace = source.index("{", start)
        level, end = 1, brace + 1
        while level:
            level += (source[end] == "{") - (source[end] == "}")
            end += 1
        return source[start:end]

    constant = re.search(r"^#define MAX_ATTRIBUTE_NUM[ \t]+\d+[ \t]*$",
                         source, re.MULTILINE)
    if not constant:
        raise ValueError("MAX_ATTRIBUTE_NUM definition not found")
    macro = source[source.index("#define store_one("):
                   source.index("static ssize_t show_ltl_cpu_num(")]
    result = constant.group() + "\n" + macro + "\n"
    for name in ("big_min_freq", "big_max_freq", "ltl_min_freq",
                 "ltl_max_freq", "ltl_min_lock"):
        result += f"store_one({name}, {name});\n"
    result += function("store_ltl_divider") + "\n"
    result += function("store_hmp_boost_type") + "\n"
    return result


class CpufreqLimitTest(unittest.TestCase):
    def test_sysfs_handlers(self):
        compiler = compiler_command()
        if not compiler:
            self.skipTest("set CC to a GCC, Clang or TCC-compatible compiler")
        source_path = Path(os.environ.get(
            "CPUFREQ_LIMIT_SOURCE", ROOT / "drivers/cpufreq/cpufreq_limit.c"))
        source = source_path.read_text(encoding="utf-8")
        output_override = os.environ.get("HOST_TEST_OUTPUT_DIR")
        if output_override:
            output_dir = Path(output_override).resolve()
            if not output_dir.is_dir():
                self.fail("HOST_TEST_OUTPUT_DIR must name an existing directory")
            context = nullcontext(output_dir)
        else:
            context = tempfile.TemporaryDirectory(prefix="cpufreq-limit-check-")
        with context as directory:
            build_dir = Path(directory)
            (build_dir / "cpufreq_limit_under_test.h").write_text(
                extract_handlers(source), encoding="utf-8")
            binary = build_dir / ("cpufreq-limit-check.exe" if os.name == "nt"
                                  else "cpufreq-limit-check")
            subprocess.run(compiler + ["-std=c99", "-Wall", "-Wextra",
                           "-Wno-unused-parameter", "-I", str(build_dir),
                           str(Path(__file__).with_name("cpufreq_limit_harness.c")),
                           "-o", str(binary)], check=True)
            subprocess.run([str(binary.resolve())], check=True)


if __name__ == "__main__":
    unittest.main()
