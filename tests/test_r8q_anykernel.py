"""Exercise the real patched AK3 device gate with mocked Android inputs."""
import argparse
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_ak3', ROOT / 'scripts/prepare-r8q-anykernel.py')
prepare_ak3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_ak3)
SHELL = [shutil.which('busybox'), 'ash'] if shutil.which('busybox') else ['bash']


class R8qAnyKernelTest(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'work'
        parent.mkdir(mode=0o777, exist_ok=True)
        self.root = parent / ('ak3-test-' + uuid.uuid4().hex)
        self.root.mkdir(mode=0o777)
        self.addCleanup(shutil.rmtree, self.root)
        self.fixture = ROOT / 'tests/fixtures/ak3-r8q'
        shutil.copytree(self.fixture, self.root, dirs_exist_ok=True)

    def test_idempotent_patch_preserves_original_gate(self):
        original = (self.root / 'META-INF/com/google/android/update-binary').read_bytes()
        prepare_ak3.prepare(self.root)
        patched = (self.root / 'META-INF/com/google/android/update-binary').read_bytes()
        prepare_ak3.prepare(self.root)
        self.assertEqual((self.root / 'META-INF/com/google/android/update-binary').read_bytes(), patched)
        self.assertEqual(patched.decode().replace(prepare_ak3.FALLBACK, '', 1).encode(), original)
        self.assertIn('do.devicecheck=1', (self.root / 'anykernel.sh').read_text())
        self.assertLess(patched.index(b'do_devicecheck;'), patched.index(b'ash anykernel.sh;'))

    def test_unknown_template_and_conflicting_helper_fail(self):
        target = self.root / 'META-INF/com/google/android/update-binary'
        data = target.read_bytes()
        target.write_bytes(data + b'\n# changed upstream\n')
        with self.assertRaisesRegex(ValueError, 'Untested'):
            prepare_ak3.prepare(self.root)
        target.write_bytes(data)
        (self.root / 'tools').mkdir(exist_ok=True)
        (self.root / 'tools/r8q-devicecheck.sh').write_bytes(b'# different helper\n')
        with self.assertRaisesRegex(ValueError, 'differs'):
            prepare_ak3.prepare(self.root)

    def test_other_device_or_disabled_gate_rejected(self):
        target = self.root / 'anykernel.sh'
        original = target.read_bytes()
        for old, new in ((b'device.name1=r8q', b'device.name1=x1q'),
                         (b'do.devicecheck=1', b'do.devicecheck=0')):
            target.write_bytes(original.replace(old, new))
            with self.assertRaisesRegex(ValueError, 'Expected r8q'):
                prepare_ak3.prepare(self.root)

    def gate(self, props=None, dt='Samsung R8Q EUR PROJECT - R8 PV2',
             compatible='qcom,kona\nqcom,sm8250', block=True, helper=True):
        prepare_ak3.prepare(self.root)
        properties = {
            'ro.product.device': 'OP5D0DL1', 'ro.build.product': 'OP5D0DL1',
            'ro.product.vendor.device': 'OP5D0DL1', 'ro.vendor.product.device': 'OP5D0DL1',
            'ro.boot.em.model': 'SM-G780G', 'ro.boot.bootloader': 'G780GXXSGEYH1',
            'ro.board.platform': 'kona',
        }
        properties.update(props or {})
        mocks = '\ngetprop() {\n  case "$1" in\n'
        for key, value in properties.items():
            mocks += f'    {shlex.quote(key)}) printf "%s\\n" {shlex.quote(value)} ;;\n'
        mocks += '  esac\n}\n'
        helper_path = self.root / 'tools/r8q-devicecheck.sh'
        if helper:
            helper_path.write_bytes(helper_path.read_bytes() + (
                '\nr8q_read_dt() {\n  case "$1" in\n'
                f'    model) printf "%s\\n" {shlex.quote(dt)} ;;\n'
                f'    compatible) printf "%s\\n" {shlex.quote(compatible)} ;;\n'
                '  esac\n}\n'
                f'r8q_has_boot_partition() {{ return {0 if block else 1}; }}\n'
            ).encode())
        else:
            helper_path.unlink()
        source = (self.root / 'META-INF/com/google/android/update-binary').read_text()
        start = source.index('do_devicecheck() {')
        end = source.index('\n}', start) + 2
        script = '''ui_print() { printf '%s\n' "$@"; }
abort() { ui_print "$@"; exit 19; }
file_getprop() { grep "^$2=" "$1" | tail -n1 | cut -d= -f2-; }
''' + mocks + source[start:end] + '\ndo_devicecheck\nprintf "gate-returned\\n"\n'
        runner = self.root / 'gate.sh'
        runner.write_bytes(script.encode())
        result = subprocess.run(SHELL + [str(runner.resolve())], cwd=self.root,
                                env=os.environ | {'ASH_STANDALONE': '1'},
                                text=True, capture_output=True, timeout=15)
        return result

    def test_coloros_g780g_hardware_passes(self):
        result = self.gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Samsung r8q hardware verified', result.stdout)

    def test_eur_g781b_hardware_passes(self):
        result = self.gate({'ro.boot.em.model': 'SM-G781B',
                            'ro.boot.bootloader': 'G781BXXU9'}, dt='Samsung SM-G781B')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_r8q_match_still_works_without_helper(self):
        result = self.gate({'ro.product.device': 'r8q'}, helper=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unsupported_or_missing_evidence_aborts(self):
        cases = [
            {'props': {'ro.boot.em.model': 'CPH2653', 'ro.boot.bootloader': 'unknown'}},
            {'props': {'ro.boot.em.model': 'SM-G780F', 'ro.boot.bootloader': 'G780FXXU1'}},
            {'props': {'ro.boot.em.model': 'SM-G991B', 'ro.boot.bootloader': 'G991BXXU1'}},
            {'props': {'ro.boot.em.model': 'SM-G781U', 'ro.boot.bootloader': 'G781USQU1'}},
            {'props': {'ro.boot.bootloader': 'G781BXXU1'}},
            {'props': {'ro.boot.em.model': ''}},
            {'props': {'ro.board.platform': 'lahaina'}},
            {'dt': 'OnePlus 13'}, {'dt': ''},
            {'compatible': 'qcom,lahaina'}, {'compatible': ''},
            {'block': False}, {'helper': False},
        ]
        for index, values in enumerate(cases):
            with self.subTest(index=index):
                # Restore the helper after each mocked Android environment.
                helper = self.root / 'tools/r8q-devicecheck.sh'
                if helper.exists():
                    helper.unlink()
                result = self.gate(**values)
                self.assertEqual(result.returncode, 19, result.stdout + result.stderr)
                self.assertNotIn('gate-returned', result.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--shell')
    parser.add_argument('--busybox', action='store_true')
    args, remaining = parser.parse_known_args()
    if args.shell:
        SHELL = [str(Path(args.shell).resolve())] + (['sh'] if args.busybox else [])
    unittest.main(argv=[sys.argv[0], *remaining])
