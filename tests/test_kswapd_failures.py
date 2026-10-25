"""Compile actual kswapd accounting, progress reset and sleep logic on the host."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


def function(source, name):
    match = re.search(r'^static bool ' + name + r'\([^;{]+\)\s*\{', source, re.M)
    if not match:
        raise ValueError('missing function: ' + name)
    opening = source.index('{', match.start())
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if not depth:
            return source[match.start():index + 1]
    raise ValueError('unbalanced function: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--cc', default=os.environ.get('HOSTCC'))
    parser.add_argument('--verify-regression', action='store_true')
    args = parser.parse_args()
    cc = args.cc or next((shutil.which(x) for x in ('cc', 'gcc', 'clang', 'tcc') if shutil.which(x)), None)
    if not cc:
        parser.error('no host C compiler; specify --cc')
    source = (args.source_root / 'mm/vmscan.c').read_text(encoding='utf-8')
    accounting = re.findall(r'\tif \(!sc\.nr_reclaimed\) \{.*?\n\t\}', source, re.S)
    reset = re.findall(r'\tif \(reclaimable\)\n\t\tpgdat->kswapd_failures = 0;', source)
    if len(accounting) != 1 or len(reset) != 1:
        raise ValueError('expected unique accounting/progress-reset statements')
    retries = re.search(r'^#define MAX_RECLAIM_RETRIES\s+\d+',
                        (args.source_root / 'mm/internal.h').read_text(), re.M)
    if not retries:
        raise ValueError('missing actual retry limit')
    template = (retries.group() + '\n' + function(source, 'prepare_kswapd_sleep') + '\n'
                + 'static void reset_on_progress(pg_data_t *pgdat, bool reclaimable)\n{\n'
                + reset[0] + '\n}\n')
    parent = args.source_root.resolve() / 'work'
    parent.mkdir(mode=0o777, exist_ok=True)
    build = parent / ('kswapd-check-' + uuid.uuid4().hex)
    build.mkdir(mode=0o777)
    try:
        header = build / 'kswapd_failure_under_test.h'
        binary = build / ('kswapd.exe' if os.name == 'nt' else 'kswapd')

        def run(block):
            code = (template + 'static void account_failure(pg_data_t *pgdat, unsigned long nr_reclaimed)\n{\n'
                    + '  struct scan_control sc = { nr_reclaimed };\n' + block + '\n}\n')
            header.write_text(code, encoding='utf-8')
            subprocess.run([cc, '-std=c99', '-Wall', '-Wextra', '-Wno-unused-function',
                            '-I', str(build), str(Path(__file__).with_name('kswapd_failure_harness.c')),
                            '-o', str(binary)], check=True)
            return subprocess.run([str(binary)], text=True, capture_output=True)

        result = run(accounting[0])
        print(result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        if result.returncode:
            return 1
        if args.verify_regression:
            block = accounting[0]
            if 'if (!lru_gen_enabled())' in block:
                raise ValueError('source already contains the old failure bypass')
            old = block.replace('pgdat->kswapd_failures++;',
                                'if (!lru_gen_enabled())\n\t\t\tpgdat->kswapd_failures++;', 1)
            regressed = run(old)
            if not regressed.returncode or 'FAIL ' not in regressed.stderr:
                raise RuntimeError('fixture did not detect bypassed MGLRU failure tracking')
            print('PASS: original MGLRU failure-accounting bypass detected')
        return 0
    finally:
        shutil.rmtree(build)


if __name__ == '__main__':
    sys.exit(main())
