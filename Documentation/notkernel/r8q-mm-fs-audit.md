# Targeted MM/filesystem review at e6083422

## Included candidate: MGLRU kswapd failure accounting

`mm/vmscan.c` increments the zero-progress event at the end of
`balance_pgdat()`, but skips `kswapd_failures++` whenever MGLRU is enabled.
Consequently repeated unsuccessful passes cannot reach the retry limit that
`prepare_kswapd_sleep()` uses to stop futile background reclaim. A reclaim
pass that makes progress already resets the counter in the shared
`shrink_node()` path; that behavior is retained.

The candidate removes only the MGLRU exception. It does not change reclaim
targets, swappiness, file-cache protection or OOM policy. This aligns the
failure increment with the unconditional operation in
[Linux v6.1 balance_pgdat](https://github.com/torvalds/linux/blob/v6.1/mm/vmscan.c#L7158).
The exception was added by the older Motorola/QCOM adaptation
[2ed4ed418ca0](https://github.com/bonecopreparado/not_samsung.sm8250-4.19/commit/2ed4ed418ca025789f9b9c2096567d6fa53c794c).

The related upstream fix
[b130ba4a6259](https://github.com/torvalds/linux/commit/b130ba4a6259f6b64d8af15e9e7ab1e912bcb7ad)
explains how defeated failure tracking can keep kswapd at 100% CPU without
reclaim progress. Its exact patch concerns unconditional resets in a newer
MGLRU implementation; this tree uses the older shared shrink_node path, so
copying that patch verbatim would not apply. The candidate restores failure
counting in this tree rather than claiming an identical backport.

The host test extracts the actual accounting block, progress reset,
prepare_kswapd_sleep function and retry limit. It checks both legacy and
MGLRU modes, no-progress passes through the retry threshold, wakeups,
successful reclaim reset, and balanced-node sleep. With TinyCC on Windows,
148 checks passed and reintroducing the old MGLRU bypass was detected.
This does not prove the scenario occurred on the tester's phone or replace
a full ARM64 build and memory-pressure/device tests.

## Optimizations already in the tree

- F2FS has NAT lockless-counter annotations, XArray conversion, NAT-lock
  checkpoint improvements, and separate read/block-age extent cache work.
  Examples: commits `8fac3720c22e`, `1088b90a78ea`, `3b95f4c24918`,
  `815cc3957a3e`, `dfcfcc6d16b9` and `484b267ce472`.
- Ext4 includes overwrite optimization (`b4552ee2cae9`) and a substantial
  stable lineage. A wholesale new IOMAP API replacement would require
  matching direct-I/O, unwritten-extent and writeback dependencies and
  filesystem regression testing, not just a frequency/performance build.
- EROFS already has per-CPU decompression workers (`5b68ef13a8f7`), cached
  decompression and managed-cache strategy support. The actual e608 config
  enables the per-CPU worker and HIPRI options, but see the defect below.

The September 2026 EROFS cache-disabled optimization proposal targets
managed_pslots XArray, anonymous pclusters/dedupe and newer folio/48-bit
extent APIs. This tree instead uses its older managed-cache mapping and
page-based decompression structures. It is not a direct small backport.
[Upstream proposal](https://www.mail-archive.com/linux-erofs%40lists.ozlabs.org/msg17094.html).

No broad F2FS, ext4/IOMAP or EROFS cache rewrite was implemented here.
The supplied recovery dmesg shows ext4 mounts and F2FS magic-mismatch probing.
That does not establish which filesystems Android was using. Android mount
usage must be established before assigning a benefit to an EROFS/F2FS
optimization. Filesystem probe messages alone do not establish corruption.

## Real EROFS finding deferred from this patch

`fs/erofs/zdata.c:146-158` declares a zero-initialized sched_param, then
passes it with SCHED_FIFO under the HIPRI option and ignores the result.
SCHED_FIFO with RT priority zero is invalid. The change was introduced by
[e0f425bed6ca](https://github.com/bonecopreparado/not_samsung.sm8250-4.19/commit/e0f425bed6ca8488c52e12ab981d5a1305be7d13).
Thus enabling the config does not establish that high-priority scheduling
is effective.

The original per-CPU-worker backport used sched_set_fifo_low(), which is
available in this tree at kernel/sched/core.c:5809-5814 and requests FIFO
priority 1. Restoring it would newly activate RT scheduling in current
default builds. That should be a separate change with CPU-contention,
decompression, latency and filesystem-use measurements. It is deliberately
not included in this MM accounting candidate.
