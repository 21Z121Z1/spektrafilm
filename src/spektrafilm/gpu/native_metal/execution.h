// SPDX-License-Identifier: GPL-3.0-or-later
// Prepared, synchronous execution. All model coefficients belong to Python.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
#define SFM_NOEXCEPT noexcept
extern "C" {
#else
#define SFM_NOEXCEPT
#endif
typedef struct sfm_executor sfm_executor;
typedef struct sfm_program sfm_program;
typedef struct sfm_image sfm_image;
typedef struct sfm_texture sfm_texture;
// Version 1: 18 little/native-endian uint32 words, no embedded pointers.
// Sources and destination are physical slots. Slot 0 is immutable input.
// 1 Gaussian, 2 affine, 3 linear combination, 4 curve, 5 spectral integral,
// 6 layered grain, 7 lognormal field, 8 multiply, 9 log10, 10 exp10,
// 11 Gaussian + weighted accumulator, 12 RGB matrix.
typedef struct {
    uint32_t code, a, b, destination, offset, count;
    uint32_t args[12];
} sfm_operation;
typedef struct {
    uint64_t allocated_bytes, high_water_bytes, dispatches, submissions;
    uint64_t upload_bytes, readback_bytes, gpu_nanoseconds;
} sfm_execution_stats;
uint32_t sfm_execution_version(void) SFM_NOEXCEPT;
int sfm_executor_create(const char* metallib, uint64_t budget, sfm_executor** out,
                        char* error, size_t capacity) SFM_NOEXCEPT;
// Calls sharing an executor serialize. Destroy must not race with a call.
void sfm_executor_destroy(sfm_executor*) SFM_NOEXCEPT;
int sfm_executor_trim(sfm_executor*, char*, size_t) SFM_NOEXCEPT;
int sfm_executor_stats(sfm_executor*, sfm_execution_stats*, char*, size_t) SFM_NOEXCEPT;
int sfm_program_create(sfm_executor*, const sfm_operation*, size_t count,
                       const float* constants, size_t constant_count,
                       uint32_t channels, uint32_t slots, uint32_t output_slot,
                       sfm_program** out, char*, size_t) SFM_NOEXCEPT;
void sfm_program_destroy(sfm_program*) SFM_NOEXCEPT;
int sfm_image_upload(sfm_executor*, const float*, size_t elements,
                     uint32_t height, uint32_t width, uint32_t channels,
                     sfm_image** out, char*, size_t) SFM_NOEXCEPT;
int sfm_image_read(sfm_executor*, const sfm_image*, float*, size_t elements,
                   char*, size_t) SFM_NOEXCEPT;
void sfm_image_destroy(sfm_image*) SFM_NOEXCEPT;
int sfm_program_run(sfm_executor*, const sfm_program*, const sfm_image*,
                     sfm_image** out, sfm_execution_stats*, char*, size_t) SFM_NOEXCEPT;
// Packs on the GPU into RGBA32Float, with no host pixel readback. The borrowed
// id<MTLTexture> is valid only while this lease lives. The caller must finish
// its GPU reads before releasing the lease. The texture backing is never pooled.
int sfm_image_texture(sfm_executor*, const sfm_image*, sfm_texture** out,
                       char*, size_t) SFM_NOEXCEPT;
void* sfm_texture_handle(const sfm_texture*) SFM_NOEXCEPT;
void sfm_texture_destroy(sfm_texture*) SFM_NOEXCEPT;
// Explicit diagnostic readback; never used by the texture handoff.
int sfm_texture_read(const sfm_texture*, float*, size_t elements, char*, size_t) SFM_NOEXCEPT;
// Integer known-answer probe; the shipping Metal Philox implementation runs.
int sfm_executor_philox(sfm_executor*, const uint32_t counter[4],
                        const uint32_t key[2], uint32_t result[4], char*, size_t) SFM_NOEXCEPT;
#ifdef __cplusplus
}
#endif
#undef SFM_NOEXCEPT
