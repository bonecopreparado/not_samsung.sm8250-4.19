"""Compile actual boost functions with a deterministic host workqueue fixture.

Run: python3 tests/test_cpu_event_boost.py --verify-regressions
The fixture models ordering, not actual kernel scheduling or performance.
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
    pattern = r"^[^\n;{}]*\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{"
    match = re.search(pattern, source, re.MULTILINE)
    if match is None:
        raise ValueError("definition missing: " + name)
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


def extracted_functions(source, mutation=None):
    names = ['__cpu_input_boost_kick', '__cpu_event_boost_kick_max',
             'cpu_boost_unboost', 'input_unboost_worker', 'max_unboost_worker',
             'msm_drm_notifier_cb']
    functions = {name: extract_function(source, name) for name in names
                 if name != 'cpu_boost_unboost' or 'static void cpu_boost_unboost(' in source}
    if mutation == 'stale_worker':
        functions['input_unboost_worker'] = '''static void input_unboost_worker(struct work_struct *work)
{
    struct boost_drv *b = container_of(to_delayed_work(work), typeof(*b), input_unboost);
    clear_bit(INPUT_BOOST, &b->state);
    wake_up(&b->boost_waitq);
}'''
    elif mutation == 'late_reassert':
        functions['__cpu_event_boost_kick_max'] = functions['__cpu_event_boost_kick_max'].replace(
            '\tif (changed)\n\t\twake_up',
            '\tset_bit(MAX_BOOST, &b->state);\n\tif (changed)\n\t\twake_up', 1)
    elif mutation == 'inactive_deadline':
        functions['__cpu_event_boost_kick_max'] = functions['__cpu_event_boost_kick_max'].replace(
            'test_bit(MAX_BOOST, &b->state) &&\n\t    ', '', 1)
    elif mutation == 'no_unblank_wakeup':
        functions['msm_drm_notifier_cb'] = functions['msm_drm_notifier_cb'].replace(
            '\t}\n\twake_up(&b->boost_waitq);', '\t\twake_up(&b->boost_waitq);\n\t}', 1)
    return '\n\n'.join(functions.values()) + '\n'


@contextmanager
def build_directory(parent):
    parent = parent.resolve()
    parent.mkdir(mode=0o777, parents=True, exist_ok=True)
    directory = parent / ('cpu-boost-check-' + uuid.uuid4().hex)
    directory.mkdir(mode=0o777)
    try:
        yield directory
    finally:
        if directory.resolve().parent != parent:
            raise RuntimeError('refusing cleanup outside build parent')
        shutil.rmtree(directory)


def compile_and_run(cc, source, directory, name, mutation=None, zero_input=False):
    header = directory / 'cpu_event_boost_under_test.h'
    header.write_text(extracted_functions(source, mutation), encoding='utf-8')
    binary = directory / (name + ('.exe' if os.name == 'nt' else ''))
    command = [cc, '-std=gnu11', '-Wall', '-Wextra', '-Wno-unused-function',
               '-I', str(directory), str(Path(__file__).with_name('cpu_event_boost_harness.c')),
               '-o', str(binary)]
    if zero_input:
        command.insert(1, '-DCONFIG_INPUT_BOOST_DURATION_MS=0')
        command.insert(1, '-DCONFIG_WAKE_BOOST_DURATION_MS=0')
    built = subprocess.run(command, capture_output=True, text=True)
    if built.returncode:
        raise RuntimeError('fixture compile failed:\n' + built.stdout + built.stderr)
    return subprocess.run([str(binary.resolve())], capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--cc', default=os.environ.get('HOSTCC'))
    parser.add_argument('--build-dir', type=Path, default=Path('work'))
    parser.add_argument('--verify-regressions', action='store_true')
    args = parser.parse_args()
    cc = args.cc or next((shutil.which(x) for x in ('cc', 'gcc', 'clang', 'tcc') if shutil.which(x)), None)
    if not cc:
        parser.error('no host C compiler; pass --cc /path/to/compiler')
    source_path = args.source or args.source_root / 'drivers/cpufreq/cpu_event_boost.c'
    try:
        source = source_path.read_text(encoding='utf-8')
        with build_directory(args.build_dir) as directory:
            result = compile_and_run(cc, source, directory, 'current')
            print(result.stdout, end='')
            print(result.stderr, end='', file=sys.stderr)
            if result.returncode:
                return 1
            result = compile_and_run(cc, source, directory, 'zero_input', zero_input=True)
            print(result.stdout, end='')
            print(result.stderr, end='', file=sys.stderr)
            if result.returncode:
                return 1
            if args.verify_regressions:
                for mutation in ('stale_worker', 'late_reassert', 'inactive_deadline',
                                 'no_unblank_wakeup'):
                    result = compile_and_run(cc, source, directory, mutation, mutation,
                                             zero_input=(mutation == 'no_unblank_wakeup'))
                    if not result.returncode or 'FAIL ' not in result.stderr:
                        raise RuntimeError('fixture failed to detect ' + mutation)
                    print('PASS regression detected:', mutation)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
