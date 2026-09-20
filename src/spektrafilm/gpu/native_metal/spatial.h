// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
#define SFM_NOEXCEPT noexcept
extern "C" {
#else
#define SFM_NOEXCEPT
#endif

typedef struct sfm_context sfm_context;
// kind: 0 identity, 1 FIR, 2 YvV. offset counts float32 values, not pairs.
typedef struct { uint32_t kind, radius, offset; } sfm_channel;
typedef struct {
    uint64_t allocated_bytes, high_water_bytes, upload_bytes, readback_bytes;
    uint64_t dispatches, gpu_nanoseconds;
} sfm_stats;

uint32_t sfm_abi_version(void) SFM_NOEXCEPT;
// All pointers are caller-owned and must be valid for their stated lengths.
// Each context serializes calls. Destroy must not race another C ABI call.
// Errors are nonzero status and a bounded NUL-terminated error string.
int sfm_create(const char* metallib, uint64_t budget, sfm_context** result,
               char* error, size_t error_size) SFM_NOEXCEPT;
void sfm_destroy(sfm_context* context) SFM_NOEXCEPT;
int sfm_release_memory(sfm_context* context, char* error, size_t error_size) SFM_NOEXCEPT;
int sfm_gaussian(sfm_context* context, const float* source, float* destination,
                 size_t elements, uint32_t height, uint32_t width, uint32_t channels,
                 const sfm_channel* plan, size_t plan_count,
                 const float* constants, size_t constant_count, sfm_stats* stats,
                 char* error, size_t error_size) SFM_NOEXCEPT;
#ifdef __cplusplus
}
#endif
#undef SFM_NOEXCEPT
