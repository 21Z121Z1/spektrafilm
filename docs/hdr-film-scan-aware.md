# Film-Scan-Aware HDR Mapping

This file is kept as a compatibility entry point. The current canonical documentation is [`film-scan-aware-hdr.md`](film-scan-aware-hdr.md).

`film_scan_aware` now means positive film-scan HDR:

- negative film raw scans are physical diagnostics only;
- negative film defaults to `profile_kind="positive_negative_scan"`;
- positive/reversal film uses `profile_kind="positive_film_scan"` and is not inverted;
- print/paper stages remain bypassed with `io.scan_film=True`;
- the HDR profile curve must be positive, monotonic increasing, and safe for `h_profile / s_profile` gain construction.

See [`film-scan-aware-hdr.md`](film-scan-aware-hdr.md) for route definitions, negative-to-positive rendering details, sampling rules, limitations, and validation commands.
