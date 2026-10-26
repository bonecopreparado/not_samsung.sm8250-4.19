"""Check actual input boost frequency selection against changing policy ceilings."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from test_cpu_event_boost import extract_function


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('HOSTCC'))
    parser.add_argument('--verify-regressions', action='store_true')
    args = parser.parse_args()
    cc = args.cc or next((shutil.which(x) for x in ('cc', 'gcc', 'clang', 'tcc') if shutil.which(x)), None)
    if not cc:
        parser.error('no host C compiler; specify --cc')
    root = Path(__file__).resolve().parents[1]
    function = extract_function((root / 'drivers/cpufreq/cpu_event_boost.c').read_text(),
                                'get_input_boost_freq')
    parent = root / 'work'
    parent.mkdir(mode=0o777, exist_ok=True)
    build = parent / ('boost-profile-' + uuid.uuid4().hex)
    build.mkdir(mode=0o777)
    try:
        header = build / 'input_boost_profile_under_test.h'
        binary = build / ('profile.exe' if os.name == 'nt' else 'profile')

        def run(source, enabled):
            header.write_text(source, encoding='utf-8')
            subprocess.run([cc, '-std=c99', '-Wall', '-Wextra',
                            '-DCONFIG_INPUT_BOOST_TO_MAX=' + str(enabled), '-I', str(build),
                            str(Path(__file__).with_name('input_boost_profile_harness.c')),
                            '-o', str(binary)], check=True)
            return subprocess.run([str(binary)], text=True, capture_output=True)

        for enabled in (0, 1):
            result = run(function, enabled)
            print(result.stdout, end='')
            if result.returncode:
                print(result.stderr, file=sys.stderr)
                return 1
        if args.verify_regressions:
            for name, mutation in (
                ('ignores current ceiling', function.replace('return policy->max;', 'return 4000000;', 1)),
                ('ignores burst selection', function.replace('IS_ENABLED(CONFIG_INPUT_BOOST_TO_MAX)', '0', 1)),
            ):
                result = run(mutation, 1)
                if not result.returncode or 'FAIL ' not in result.stderr:
                    raise RuntimeError('fixture did not detect: ' + name)
                print('PASS regression detected:', name)
        return 0
    finally:
        shutil.rmtree(build)


if __name__ == '__main__':
    sys.exit(main())
