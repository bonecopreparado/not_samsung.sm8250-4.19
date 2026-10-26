"""Run the actual read-only APK gate with a host shell and mocked Android PM."""
import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SHELL = [shutil.which('busybox'), 'ash'] if shutil.which('busybox') else ['bash']


class InstalledManagerGuardTest(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'work'
        parent.mkdir(mode=0o777, exist_ok=True)
        self.folder = parent / ('manager-guard-' + uuid.uuid4().hex)
        self.folder.mkdir(mode=0o777)
        def cleanup():
            assert self.folder.resolve().parent == parent.resolve()
            shutil.rmtree(self.folder)
        self.addCleanup(cleanup)
        source = (ROOT / 'scripts/r8q-sukisu-repair.sh').read_text(encoding='utf-8')
        self.guard = re.search(r'^check_installed_manager\(\) \{\n.*?^\}', source, re.M | re.S).group()
        self.constants = '\n'.join(re.findall(r'^(?:APK_SHA|EXPECTED_MANAGER_VERSION)=.*$', source, re.M))
        self.hash_function = re.search(r'^hash_file\(\) \{.*$', source, re.M).group()
        self.good = self.folder / 'official.apk'
        self.bad = self.folder / 'other.apk'
        self.good.write_bytes(b'fixture representing the official APK bytes')
        self.bad.write_bytes(b'wrong APK')
        # The function uses a real SHA-256 implementation; replace the release
        # digest for this isolated fixture, without altering its decision logic.
        import hashlib
        self.constants = re.sub(r'^APK_SHA=.*$', 'APK_SHA=' + hashlib.sha256(self.good.read_bytes()).hexdigest(),
                                self.constants, flags=re.M)

    def run_guard(self, version, apk):
        wrapper = self.folder / 'guard.sh'
        text = self.constants + '\n' + self.hash_function + '\n'
        text += "fail() { printf '%s\\n' \"$*\" >&2; exit 23; }\n"
        text += 'dumpsys() { printf "%s\\n" ' + shlex.quote('  versionCode=' + version + ' minSdk=27') + '; }\n'
        text += 'pm() { printf "%s\\n" ' + shlex.quote('package:' + apk.as_posix()) + '; }\n'
        text += self.guard + '\ncheck_installed_manager\nprintf "guard-passed\\n"\n'
        wrapper.write_bytes(text.encode())
        return subprocess.run(SHELL + [str(wrapper.resolve())], text=True, capture_output=True,
                              env=os.environ | {'ASH_STANDALONE': '1'}, timeout=10)

    def test_wrong_installed_version_rejected(self):
        result = self.run_guard('41084', self.good)
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertIn('41084', result.stderr)
        self.assertNotIn('guard-passed', result.stdout)

    def test_missing_installed_version_rejected(self):
        result = self.run_guard('', self.good)
        self.assertEqual(result.returncode, 23)

    def test_same_version_wrong_apk_rejected(self):
        result = self.run_guard('40545', self.bad)
        self.assertEqual(result.returncode, 23)
        self.assertIn('APK instalado', result.stderr)

    def test_verified_pair_passes(self):
        result = self.run_guard('40545', self.good)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('guard-passed', result.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--shell')
    parser.add_argument('--busybox', action='store_true')
    args, rest = parser.parse_known_args()
    if args.shell:
        SHELL = [str(Path(args.shell).resolve())] + (['sh'] if args.busybox else [])
    unittest.main(argv=[sys.argv[0], *rest])
