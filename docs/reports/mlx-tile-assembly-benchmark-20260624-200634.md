# MLX Tile Assembly Benchmark

Generated: 2026-06-24T20:06:34

## Environment

- `platform`: `macOS-26.5.1-arm64-arm-64bit-Mach-O`
- `machine`: `arm64`
- `processor`: `arm`
- `python`: `3.13.1`
- `numpy`: `2.4.4`
- `mlx_available`: `True`
- `mlx_unavailable_reason`: `None`
- `backend`: `mlx`
- `backend_precision`: `float32`
- `mlx`: `0.31.2`
- `metal_available`: `True`
- `peak_memory_api`: `True`

## Strategy Feasibility

- `at_add`: current production behavior, `output.at[y0:y1].add(tile_out)`.
- `concat`: benchmark prototype that stores tile outputs and concatenates once.
- `metal_scatter`: infeasible: MLX fast.metal_kernel allocates declared outputs and does not expose a supported in-place write into an existing full-frame array. A scatter prototype would need one full-frame output per tile before combining, which defeats the residency/memory goal.

## Summary

| Size | Strategy | Status | Median Of Medians (s) | Peak Memory Max (MiB) | Parity Max Abs Diff | Records |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 12mp | at_add | ok | 0.0623 | 564.0 | 0 | 17 |
| 12mp | concat | ok | 0.0570 | 564.0 | 0 | 17 |
| 12mp | metal_scatter | infeasible | n/a | n/a | n/a | 17 |
| 24mp | at_add | ok | 0.1021 | 1087.7 | 0 | 17 |
| 24mp | concat | ok | 0.0939 | 1087.7 | 0 | 17 |
| 24mp | metal_scatter | infeasible | n/a | n/a | n/a | 17 |

## OOM And Memory Pressure

- OOM records: `0`
- Error records: `0`
- Maximum recorded peak memory: `1087.7 MiB`

## Recommendation

- Default strategy recommendation: `keep_at_add`
- Should change `_write_tile()` default: `False`
- 12MP/24MP winners: `{'12mp': 'concat', '24mp': 'concat'}`
- Reason: Keep .at.add default unless concat satisfies all 12MP/24MP wall-clock, memory, and parity gates.
- Conclusion: keep `.at.add` default.

### Gate Checks

- `12mp`: `{'size': '12mp', 'wall_clock_improvement': 0.08386665251962308, 'peak_memory_ratio': 0.9999999932363524, 'parity_ok': True, 'qualifies': False}`
- `24mp`: `{'size': '24mp', 'wall_clock_improvement': 0.07971479544737992, 'peak_memory_ratio': 0.9999999964928371, 'parity_ok': True, 'qualifies': False}`

## Detailed Records

| Scenario | Size | Overlap | Tile Rows | Strategy | Status | Median (s) | Min (s) | Max (s) | Peak Max (MiB) | Parity | Mean | Max Value |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| spectral | 12mp |  | 256 | at_add | ok | 0.0401 | 0.0387 | 0.0484 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 256 | concat | ok | 0.0362 | 0.0362 | 0.0408 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 256 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 12mp |  | 384 | at_add | ok | 0.0388 | 0.0379 | 0.0414 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 384 | concat | ok | 0.0390 | 0.0389 | 0.0397 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 384 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 12mp |  | 512 | at_add | ok | 0.0400 | 0.0364 | 0.0413 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 512 | concat | ok | 0.0362 | 0.0355 | 0.0364 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 512 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 12mp |  | 1024 | at_add | ok | 0.0370 | 0.0337 | 0.0528 | 480.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 1024 | concat | ok | 0.0343 | 0.0338 | 0.0366 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 1024 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 12mp |  | 2048 | at_add | ok | 0.0432 | 0.0423 | 0.0440 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 2048 | concat | ok | 0.0425 | 0.0420 | 0.0463 | 432.0 | 0 | 0.5002 | 0.7502 |
| spectral | 12mp |  | 2048 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 16 | 256 | at_add | ok | 0.0656 | 0.0642 | 0.0689 | 448.5 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 16 | 256 | concat | ok | 0.0628 | 0.0618 | 0.0710 | 448.5 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 16 | 256 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 16 | 512 | at_add | ok | 0.0623 | 0.0617 | 0.0712 | 439.5 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 16 | 512 | concat | ok | 0.0542 | 0.0529 | 0.0547 | 439.5 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 16 | 512 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 16 | 1024 | at_add | ok | 0.0586 | 0.0563 | 0.0617 | 437.3 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 16 | 1024 | concat | ok | 0.0576 | 0.0547 | 0.0592 | 437.3 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 16 | 1024 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 16 | 2048 | at_add | ok | 0.0655 | 0.0649 | 0.0664 | 531.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 16 | 2048 | concat | ok | 0.0570 | 0.0548 | 0.0592 | 531.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 16 | 2048 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 64 | 256 | at_add | ok | 0.0695 | 0.0684 | 0.0761 | 498.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 64 | 256 | concat | ok | 0.0646 | 0.0627 | 0.0658 | 498.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 64 | 256 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 64 | 512 | at_add | ok | 0.0683 | 0.0639 | 0.0731 | 462.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 64 | 512 | concat | ok | 0.0558 | 0.0529 | 0.0589 | 462.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 64 | 512 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 64 | 1024 | at_add | ok | 0.0589 | 0.0580 | 0.0631 | 453.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 64 | 1024 | concat | ok | 0.0559 | 0.0548 | 0.0922 | 453.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 64 | 1024 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 64 | 2048 | at_add | ok | 0.0643 | 0.0619 | 0.0660 | 540.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 64 | 2048 | concat | ok | 0.0674 | 0.0596 | 0.0772 | 540.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 64 | 2048 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 128 | 256 | at_add | ok | 0.1156 | 0.1155 | 0.1176 | 564.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 128 | 256 | concat | ok | 0.1098 | 0.1017 | 0.1103 | 564.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 128 | 256 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 128 | 512 | at_add | ok | 0.0688 | 0.0685 | 0.0767 | 492.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 128 | 512 | concat | ok | 0.0676 | 0.0668 | 0.0727 | 492.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 128 | 512 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 128 | 1024 | at_add | ok | 0.0613 | 0.0611 | 0.0636 | 474.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 128 | 1024 | concat | ok | 0.0704 | 0.0696 | 0.0762 | 474.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 128 | 1024 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 12mp | 128 | 2048 | at_add | ok | 0.0780 | 0.0743 | 0.0807 | 552.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 128 | 2048 | concat | ok | 0.0609 | 0.0595 | 0.0642 | 552.0 | 0 | 0.5000 | 0.7500 |
| spatial | 12mp | 128 | 2048 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 24mp |  | 256 | at_add | ok | 0.0894 | 0.0864 | 0.0931 | 824.0 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 256 | concat | ok | 0.0835 | 0.0783 | 0.1448 | 824.0 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 256 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 24mp |  | 500 | at_add | ok | 0.0861 | 0.0841 | 0.0898 | 824.1 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 500 | concat | ok | 0.0784 | 0.0605 | 0.0876 | 824.1 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 500 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 24mp |  | 512 | at_add | ok | 0.0886 | 0.0874 | 0.0935 | 824.0 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 512 | concat | ok | 0.0602 | 0.0597 | 0.0859 | 824.0 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 512 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 24mp |  | 1024 | at_add | ok | 0.0772 | 0.0767 | 0.0846 | 824.0 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 1024 | concat | ok | 0.0599 | 0.0561 | 0.0703 | 824.0 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 1024 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spectral | 24mp |  | 2048 | at_add | ok | 0.0739 | 0.0696 | 0.0748 | 824.0 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 2048 | concat | ok | 0.0682 | 0.0682 | 0.0704 | 824.0 | 0 | 0.5002 | 0.7502 |
| spectral | 24mp |  | 2048 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 16 | 256 | at_add | ok | 0.1199 | 0.1159 | 0.1451 | 857.1 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 16 | 256 | concat | ok | 0.1229 | 0.1110 | 0.1325 | 857.1 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 16 | 256 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 16 | 512 | at_add | ok | 0.1068 | 0.1012 | 0.1102 | 839.4 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 16 | 512 | concat | ok | 0.0965 | 0.0946 | 0.1096 | 839.4 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 16 | 512 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 16 | 1024 | at_add | ok | 0.1166 | 0.1111 | 0.1171 | 830.6 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 16 | 1024 | concat | ok | 0.0971 | 0.0927 | 0.1057 | 830.6 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 16 | 1024 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 16 | 2048 | at_add | ok | 0.1054 | 0.1043 | 0.1164 | 957.0 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 16 | 2048 | concat | ok | 0.1069 | 0.1056 | 0.1105 | 957.0 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 16 | 2048 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 64 | 256 | at_add | ok | 0.1057 | 0.1056 | 0.1123 | 956.0 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 64 | 256 | concat | ok | 0.1009 | 0.0998 | 0.1021 | 956.0 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 64 | 256 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 64 | 512 | at_add | ok | 0.1049 | 0.1010 | 0.1051 | 885.6 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 64 | 512 | concat | ok | 0.0880 | 0.0865 | 0.0903 | 885.6 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 64 | 512 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 64 | 1024 | at_add | ok | 0.0977 | 0.0972 | 0.0987 | 850.4 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 64 | 1024 | concat | ok | 0.0939 | 0.0920 | 0.0960 | 850.4 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 64 | 1024 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 64 | 2048 | at_add | ok | 0.1021 | 0.0992 | 0.1045 | 973.5 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 64 | 2048 | concat | ok | 0.0964 | 0.0938 | 0.1043 | 973.5 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 64 | 2048 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 128 | 256 | at_add | ok | 0.1343 | 0.1314 | 0.1356 | 1087.7 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 128 | 256 | concat | ok | 0.1235 | 0.1218 | 0.1336 | 1087.7 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 128 | 256 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 128 | 512 | at_add | ok | 0.1136 | 0.1039 | 0.1176 | 947.1 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 128 | 512 | concat | ok | 0.1028 | 0.1012 | 0.1036 | 947.1 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 128 | 512 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 128 | 1024 | at_add | ok | 0.0996 | 0.0995 | 0.1016 | 876.8 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 128 | 1024 | concat | ok | 0.0939 | 0.0939 | 0.0940 | 876.8 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 128 | 1024 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| spatial | 24mp | 128 | 2048 | at_add | ok | 0.0941 | 0.0916 | 0.0964 | 995.4 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 128 | 2048 | concat | ok | 0.0925 | 0.0918 | 0.0932 | 995.4 | 0 | 0.5000 | 0.7500 |
| spatial | 24mp | 128 | 2048 | metal_scatter | infeasible | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
