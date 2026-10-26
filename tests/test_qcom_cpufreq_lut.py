"""Compile the actual non-boost LUT selector and cpufreq definitions on the host.

Run: python3 tests/test_qcom_cpufreq_lut.py --verify-regression
This validates selection after DT filtering, not actual frequency/thermal hardware.
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


NAME = 'qcom_cpufreq_hw_max_non_boost'


def extract_function(source):
    match = re.search(r'^static unsigned int\s+' + NAME + r'\([^;{}]+\)\s*\{',
                      source, re.MULTILINE)
    if match is None:
        raise ValueError('non-boost selector definition missing')
    opening = source.index('{', match.start())
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if not depth:
            return source[match.start():index + 1]
    raise ValueError('unbalanced selector definition')


def definitions(header):
    parts = []
    for name in ('CPUFREQ_ENTRY_INVALID', 'CPUFREQ_TABLE_END', 'CPUFREQ_BOOST_FREQ',
                 'cpufreq_for_each_valid_entry'):
        match = re.search(r'^#define\s+' + name + r'\b[^\n]*', header, re.MULTILINE)
        if match is None:
            raise ValueError('cpufreq definition missing: ' + name)
        definition = match.group()
        cursor = match.end()
        while definition.rstrip().endswith('\\'):
            following = header.index('\n', cursor + 1)
            definition += header[cursor:following]
            cursor = following
        parts.append(definition)
    match = re.search(r'struct cpufreq_frequency_table\s*\{[^}]+\};', header)
    if match is None:
        raise ValueError('cpufreq table struct missing')
    return '\n'.join(parts) + '\n' + match.group() + '\n'


@contextmanager
def build_directory(parent):
    parent = parent.resolve()
    parent.mkdir(mode=0o777, parents=True, exist_ok=True)
    directory = parent / ('qcom-lut-check-' + uuid.uuid4().hex)
    directory.mkdir(mode=0o777)
    try:
        yield directory
    finally:
        if directory.resolve().parent != parent:
            raise RuntimeError('unexpected build directory')
        shutil.rmtree(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--cc', default=os.environ.get('HOSTCC'))
    parser.add_argument('--build-dir', type=Path, default=Path('work'))
    parser.add_argument('--verify-regression', action='store_true')
    args = parser.parse_args()
    compiler = args.cc or next((shutil.which(x) for x in ('cc', 'gcc', 'clang', 'tcc')
                               if shutil.which(x)), None)
    if compiler is None:
        parser.error('no host C compiler; use --cc')
    source = (args.source_root / 'drivers/cpufreq/qcom-cpufreq-hw.c').read_text(encoding='utf-8')
    header = (args.source_root / 'include/linux/cpufreq.h').read_text(encoding='utf-8')
    selector = extract_function(source)
    with build_directory(args.build_dir) as directory:
        (directory / 'qcom_cpufreq_definitions_under_test.h').write_text(definitions(header), encoding='utf-8')
        binary = directory / ('qcom-lut-check.exe' if os.name == 'nt' else 'qcom-lut-check')

        def run(code):
            (directory / 'qcom_cpufreq_selection_under_test.h').write_text(code, encoding='utf-8')
            subprocess.run([compiler, '-std=gnu11', '-Wall', '-Wextra', '-I', str(directory),
                            str(Path(__file__).with_name('qcom_cpufreq_lut_harness.c')),
                            '-o', str(binary)], check=True)
            return subprocess.run([str(binary)], capture_output=True, text=True)

        result = run(selector)
        print(result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        if result.returncode:
            return 1
        if args.verify_regression:
            # Exact previous selection loop, wrapped as the extracted helper.
            old = '''static unsigned int qcom_cpufreq_hw_max_non_boost(struct cpufreq_frequency_table *table)
{
    unsigned int j, last = 0;
    for (j = 0; j < 40 && table[j].frequency != CPUFREQ_TABLE_END; j++) {
        if (table[j].flags == CPUFREQ_BOOST_FREQ)
            break;
        last = table[j].frequency;
    }
    return last;
}
'''
            regressed = run(old)
            if not regressed.returncode or 'FAIL trailing_invalid:' not in regressed.stderr:
                raise RuntimeError('fixture failed to detect invalid non-boost frequency')
            print('PASS: original invalid-entry/non-boost selection regression detected')
    return 0


if __name__ == '__main__':
    sys.exit(main())
