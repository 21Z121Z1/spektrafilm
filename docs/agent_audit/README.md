# Agent Audit Index

These documents come from the 2026-05-28 agent-driven quality audit. Use them as an audit snapshot, then re-check current source and tests before acting on any finding.

## Start Here

| Path | Notes |
| --- | --- |
| [`final_validation_report.md`](final_validation_report.md) | Summary of audit outcomes and validation state. |
| [`triaged_findings.md`](triaged_findings.md) | Consolidated findings sorted into priority buckets. |
| [`accepted_p0_p1.md`](accepted_p0_p1.md) | Accepted P0/P1 implementation guide. |
| [`next_goals.md`](next_goals.md) | Remaining follow-up goals after the audit pass. |

## Review Dimensions

| Path | Notes |
| --- | --- |
| [`review_hdr_color.md`](review_hdr_color.md) | HDR and color correctness findings. |
| [`review_format_metadata.md`](review_format_metadata.md) | Format, metadata, and I/O safety findings. |
| [`review_performance.md`](review_performance.md) | Performance and memory risk review. |
| [`review_test_gaps.md`](review_test_gaps.md) | Test coverage and test-quality findings. |
| [`review_ui_runtime.md`](review_ui_runtime.md) | UI, runtime, and threading risks. |
| [`review_docs_ci.md`](review_docs_ci.md) | Documentation, API, and CI consistency findings. |

## Architecture And Validation Support

| Path | Notes |
| --- | --- |
| [`architecture_index.md`](architecture_index.md) | Package structure and dependency map. |
| [`critical_paths.md`](critical_paths.md) | Critical runtime execution paths. |
| [`module_contracts.md`](module_contracts.md) | Module contracts and invariants. |
| [`validation_matrix.md`](validation_matrix.md) | Mapping from contracts to tests. |
| [`test_inventory.md`](test_inventory.md) | Test inventory snapshot. |
| [`deferred_p2.md`](deferred_p2.md) | Real but deferred P2 findings. |
| [`rejected_findings.md`](rejected_findings.md) | Rejected findings and reasons. |
| [`upstream_baseline/public_api_contracts.md`](upstream_baseline/public_api_contracts.md) | Public API contract snapshot from upstream baseline. |
