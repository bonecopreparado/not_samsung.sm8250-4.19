"""Compile the real queue allocator/sync functions against a host workqueue shim."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


def function(source, name):
    match = re.search(r'^[^\n;{}]*\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{', source, re.MULTILINE)
    if not match:
        raise ValueError('function missing: ' + name)
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()),
                    source, flags=re.DOTALL)
    opening = masked.index('{', match.start())
    depth = 0
    for index in range(opening, len(masked)):
        depth += (masked[index] == '{') - (masked[index] == '}')
        if not depth:
            return source[match.start():index + 1]
    raise ValueError('unbalanced function: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--cc', default=os.environ.get('HOSTCC'))
    parser.add_argument('--verify-regression', action='store_true')
    args = parser.parse_args()
    cc = args.cc or next((shutil.which(c) for c in ('cc', 'gcc', 'clang', 'tcc') if shutil.which(c)), None)
    if not cc:
        parser.error('no host C compiler; pass --cc')
    core = (args.source_root / 'block/blk-core.c').read_text(encoding='utf-8')
    mq = (args.source_root / 'block/blk-mq.c').read_text(encoding='utf-8')
    functions = '\n\n'.join(function(core, name) for name in
                            ('blk_timeout_work_dummy', 'blk_rq_timed_out_timer',
                             'blk_alloc_queue_node', 'blk_sync_queue'))
    mq_allocator = function(mq, 'blk_mq_init_allocated_queue')
    mq_init = re.findall(r'INIT_WORK\(&q->timeout_work,\s*[^;]+;', mq_allocator)
    if len(mq_init) != 1:
        raise ValueError('MQ timeout initialization must be unique')
    functions += '\nstatic void init_mq_timeout_under_test(struct request_queue *q)\n{\n' + mq_init[0] + '\n}\n'
    parent = args.source_root / 'work'
    parent.mkdir(mode=0o777, exist_ok=True)
    build = parent / ('blk-timeout-' + uuid.uuid4().hex)
    build.mkdir(mode=0o777)
    try:
        header = build / 'blk_timeout_under_test.h'
        binary = build / ('timeout.exe' if os.name == 'nt' else 'timeout')

        def run(text):
            header.write_text(text, encoding='utf-8')
            subprocess.run([cc, '-std=gnu11', '-Wall', '-Wextra', '-Wno-unused-parameter',
                            '-Wno-unused-function', '-I', str(build),
                            str(Path(__file__).with_name('blk_timeout_harness.c')),
                            '-o', str(binary)], check=True)
            return subprocess.run([str(binary.resolve())], text=True, capture_output=True)

        current = run(functions)
        print(current.stdout, end='')
        print(current.stderr, file=sys.stderr, end='')
        if current.returncode:
            return 1
        if args.verify_regression:
            init = 'INIT_WORK(&q->timeout_work, blk_timeout_work_dummy);'
            if functions.count(init) != 1:
                raise ValueError('safe allocator timeout initialization not found')
            old = run(functions.replace(init, 'INIT_WORK(&q->timeout_work, NULL);', 1))
            if not old.returncode or 'FAIL ' not in old.stderr:
                raise RuntimeError('fixture did not detect the original NULL work callback')
            print('PASS: original NULL timeout-work callback regression detected')
        return 0
    finally:
        assert build.resolve().parent == parent.resolve()
        shutil.rmtree(build)


if __name__ == '__main__':
    sys.exit(main())
