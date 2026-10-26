"""Compile actual UFS init + simple_ondemand functions with a framework fixture."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


def extract_function(source, name):
    match = re.search(r'^[^\n;{}]*\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{', source, re.M)
    if match is None:
        raise ValueError('missing function: ' + name)
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()),
                    source, flags=re.S)
    opening = masked.index('{', match.start())
    depth = 0
    for index in range(opening, len(masked)):
        depth += (masked[index] == '{') - (masked[index] == '}')
        if depth == 0:
            return source[match.start():index + 1] + '\n'
    raise ValueError('unbalanced function: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('HOSTCC'))
    parser.add_argument('--verify-regressions', action='store_true')
    args = parser.parse_args()
    compiler = args.cc or next((shutil.which(x) for x in ('cc', 'gcc', 'clang', 'tcc') if shutil.which(x)), None)
    if compiler is None:
        parser.error('no host C compiler; specify --cc')
    root = Path(__file__).resolve().parents[1]
    ufs = extract_function((root / 'drivers/scsi/ufs/ufshcd.c').read_text(encoding='utf-8'), 'ufshcd_devfreq_init')
    governor = extract_function((root / 'drivers/devfreq/governor_simpleondemand.c').read_text(encoding='utf-8'),
                                'devfreq_simple_ondemand_func')
    parent = root / 'work'
    parent.mkdir(mode=0o777, exist_ok=True)
    build = parent / ('ufs-initial-' + uuid.uuid4().hex)
    build.mkdir(mode=0o777)
    try:
        (build / 'simpleondemand_under_test.h').write_text(governor, encoding='utf-8')
        header = build / 'ufs_initial_freq_under_test.h'
        binary = build / ('ufs-initial.exe' if os.name == 'nt' else 'ufs-initial')

        def run(source):
            header.write_text(source, encoding='utf-8')
            subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-I', str(build),
                            str(Path(__file__).with_name('ufs_initial_freq_harness.c')), '-o', str(binary)],
                           check=True)
            return subprocess.run([str(binary)], text=True, capture_output=True)

        result = run(ufs)
        print(result.stdout, end='')
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            return 1
        if args.verify_regressions:
            assignment = '\tscaling->profile.initial_freq = clki->curr_freq;\n'
            if assignment not in ufs:
                raise ValueError('expected initial-frequency assignment missing')
            for name, mutation in (
                ('original zero initial frequency', ufs.replace(assignment, '', 1)),
                ('hardcoded300MHz', ufs.replace(assignment, '\tscaling->profile.initial_freq = 300000000;\n', 1)),
            ):
                result = run(mutation)
                if not result.returncode or 'FAIL ' not in result.stderr:
                    raise RuntimeError('fixture did not detect: ' + name)
                print('PASS regression detected:', name)
        return 0
    finally:
        assert build.resolve().parent == parent.resolve()
        shutil.rmtree(build)


if __name__ == '__main__':
    sys.exit(main())
