# r8q: CPU boost and charger follow-up

These changes build on `97f30708`, which compiled on the maintainer's Colab
and reached Android on the tester's r8q. The screenshot and current bugreport
confirm that boot result; they do not establish root/module compatibility.
See [the companion userspace diagnosis](r8q-root-compat.md) for that issue.

## CPU event boost

`mod_delayed_work()` does not cancel a callback that has already started.
The old unboost callbacks cleared the state unconditionally. If a new input
or maximum boost arrived while an older callback was running, that callback
could clear the new boost. The return value of `mod_delayed_work()` also does
not describe the logical boost state on its own.

Publish the expiry and the state under a spinlock, and have both callbacks
check that expiry before clearing a boost. A stale callback requeues itself
for the remaining interval. Workqueue operations stay outside the lock,
because modifying pending work can wait for another CPU's workqueue state.
Wake the policy thread when the boost state changes. Always wake it for a
display state change, including builds with wake boost disabled.

A zero duration now disables the corresponding request, avoiding an
immediate callback racing with state publication. Only an active maximum
boost participates in the longer-expiry comparison; an initial zero expiry
must not suppress the first request before jiffies wraps through zero.
The frequency tables, duration settings, policy maximum and thermal controls
are unchanged. This addresses lost boosts; it is not an FPS benchmark.

## PCA9468 direct charging

In the active state, `pca9468_check_error()` read `INT1_STS` without checking
the I2C result, then tested the stale previous register value and overwrote
the error with success. Propagate the negative read result through the
existing fault path before checking the temperature-protection bit.

Routine timer, successful active/CC status, and successful CC entry/exit
messages use `pr_debug()` instead of `pr_info()`. Fault status messages,
temperature errors and register dumps remain visible. The CC-inactive event
retains its existing level. This reduces routine logging overhead during
charging without changing polling intervals, voltages or current limits.

## Validation and limits

The host fixtures extract the changed functions from the actual source.
The CPU fixture models deterministic callback/kick interleavings, pending
extensions, display changes, disabled durations, expiry and jiffies wrap.
It does not emulate the kernel scheduler or prove every possible ordering.
The PCA9468 fixture models I2C failures and status registers; it does not
exercise a physical charger or all logging call sites.

On Windows with TinyCC, 205 CPU checks, 11 disabled-duration checks and
23 PCA9468 checks passed. Four CPU mutations and the original ignored-I2C
error were detected by deliberately reintroducing them. These runs did not
use sanitizers. The local helper script was also parsed as POSIX shell.
Full ARM64 build and device validation of this follow-up are pending.

```sh
python3 tests/test_cpu_event_boost.py --verify-regressions
python3 tests/test_pca9468_status.py --verify-regression
```

Run these alongside the existing build, cpufreq, MM/RCU and NoMount tests.
After compilation, check boot, touch/display responsiveness and normal/fast
charging on the r8q, and compare temperatures and frame times under the same
workload before attributing a performance change to this patch.
