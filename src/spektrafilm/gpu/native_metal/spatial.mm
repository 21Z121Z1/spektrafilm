// SPDX-License-Identifier: GPL-3.0-or-later
// Narrow Apple adapter. Python owns model constants; this file only executes.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "spatial.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <exception>
#include <memory>
#include <mutex>

struct sfm_context {
    id<MTLDevice> device;
    id<MTLCommandQueue> queue;
    id<MTLComputePipelineState> fir, recursive, copy;
    id<MTLBuffer> input, scratch, output, constants;
    std::mutex mutex;
    uint64_t budget = 0, high_water = 0;
};

namespace {
int fail(char* error, size_t size, const char* message) noexcept {
    if (error && size) std::snprintf(error, size, "%s", message ? message : "Metal failure");
    return 1;
}
const char* description(NSError* error) {
    return error ? error.localizedDescription.UTF8String : "Metal returned nil";
}
template<class Function>
int protect(Function body, char* error, size_t size) noexcept {
    if (error && size) error[0] = '\0';
    @autoreleasepool {
        @try {
            try { return body(); }
            catch (const std::exception& e) { return fail(error, size, e.what()); }
            catch (...) { return fail(error, size, "unknown C++ exception"); }
        } @catch (NSException* e) {
            return fail(error, size, e.reason.UTF8String);
        }
    }
}
bool complete(id<MTLCommandBuffer> command, char* error, size_t size) {
    if (!command) { fail(error, size, "cannot create command buffer"); return false; }
    [command commit];
    [command waitUntilCompleted];
    if (command.status != MTLCommandBufferStatusCompleted) {
        fail(error, size, description(command.error));
        return false;
    }
    return true;
}
id<MTLComputePipelineState> pipeline(id<MTLDevice> device, id<MTLLibrary> library,
                                     NSString* name, NSError** error) {
    id<MTLFunction> function = [library newFunctionWithName:name];
    return function ? [device newComputePipelineStateWithFunction:function error:error] : nil;
}
bool encode(id<MTLCommandBuffer> command, id<MTLComputePipelineState> state,
             id<MTLBuffer> input, id<MTLBuffer> output, id<MTLBuffer> constants,
             size_t offset, const uint32_t* meta, size_t threads) {
    id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
    if (!encoder) return false;
    [encoder setComputePipelineState:state];
    [encoder setBuffer:input offset:0 atIndex:0];
    [encoder setBuffer:output offset:0 atIndex:1];
    if (constants) [encoder setBuffer:constants offset:offset atIndex:2];
    if (meta) [encoder setBytes:meta length:6 * sizeof(uint32_t) atIndex:3];
    NSUInteger width = std::min<NSUInteger>(256, state.maxTotalThreadsPerThreadgroup);
    [encoder dispatchThreads:MTLSizeMake(threads, 1, 1)
        threadsPerThreadgroup:MTLSizeMake(width, 1, 1)];
    [encoder endEncoding];
    return true;
}
uint64_t resident(const sfm_context& c) {
    return c.input.length + c.scratch.length + c.output.length + c.constants.length;
}
void clear(sfm_context& c) {
    c.input = nil; c.scratch = nil; c.output = nil; c.constants = nil;
}
} // namespace

uint32_t sfm_abi_version(void) noexcept { return 1; }
int sfm_create(const char* path, uint64_t budget, sfm_context** output,
               char* error, size_t size) noexcept {
    if (output) *output = nullptr;
    return protect([&]() -> int {
        if (!output || !path || budget < 64) return fail(error, size, "invalid create arguments");
        auto c = std::make_unique<sfm_context>();
        c->budget = budget;
        c->device = MTLCreateSystemDefaultDevice();
        if (!c->device || !c->device.hasUnifiedMemory)
            return fail(error, size, "a unified-memory Metal device is required");
        NSString* name = [NSString stringWithUTF8String:path];
        if (!name) return fail(error, size, "metallib path is not UTF-8");
        NSError* detail = nil;
        id<MTLLibrary> library = [c->device newLibraryWithURL:[NSURL fileURLWithPath:name] error:&detail];
        if (!library) return fail(error, size, description(detail));
        c->queue = [c->device newCommandQueue];
        c->fir = pipeline(c->device, library, @"sfm_fir", &detail);
        c->recursive = pipeline(c->device, library, @"sfm_recursive", &detail);
        c->copy = pipeline(c->device, library, @"sfm_copy", &detail);
        id<MTLComputePipelineState> probe = pipeline(c->device, library, @"sfm_probe", &detail);
        if (!c->queue || !c->fir || !c->recursive || !c->copy || !probe)
            return fail(error, size, "missing queue or required spatial kernel");
        const float values[2] = {16777216.0f, 1.0f};
        id<MTLBuffer> source = [c->device newBufferWithBytes:values length:sizeof(values)
                                                          options:MTLResourceStorageModeShared];
        id<MTLBuffer> result = [c->device newBufferWithLength:sizeof(values)
                                                           options:MTLResourceStorageModeShared];
        if (!source || !result) return fail(error, size, "cannot allocate arithmetic probe");
        std::memset(result.contents, 0, sizeof(values));
        id<MTLCommandBuffer> command = [c->queue commandBuffer];
        if (!command || !encode(command, probe, source, result, nil, 0, nullptr, 1))
            return fail(error, size, "cannot encode arithmetic probe");
        if (!complete(command, error, size)) return 1;
        const float* checked = static_cast<const float*>(result.contents);
        if (checked[0] != 1.0f || checked[1] != 1.0f)
            return fail(error, size, "spatial arithmetic/ABI probe failed; rebuild with safe math and contraction off");
        *output = c.release();
        return 0;
    }, error, size);
}
void sfm_destroy(sfm_context* context) noexcept {
    @autoreleasepool { delete context; }
}
int sfm_release_memory(sfm_context* context, char* error, size_t size) noexcept {
    return protect([&]() -> int {
        if (!context) return fail(error, size, "null context");
        std::lock_guard<std::mutex> lock(context->mutex);
        clear(*context);
        return 0;
    }, error, size);
}

int sfm_gaussian(sfm_context* context, const float* source, float* destination,
                 size_t elements, uint32_t height, uint32_t width, uint32_t channels,
                 const sfm_channel* plan, size_t plan_count,
                 const float* values, size_t value_count, sfm_stats* stats,
                 char* error, size_t size) noexcept {
    if (stats) *stats = {};
    return protect([&]() -> int {
        if (!context || !source || !destination || !plan || !stats)
            return fail(error, size, "null argument");
        uint64_t pixels = uint64_t(height) * width;
        if (!height || !width || height > 16384 || width > 16384 || !channels || channels > 4 ||
            plan_count != channels || pixels > UINT32_MAX / channels || elements != pixels * channels)
            return fail(error, size, "invalid image shape or element count");
        if (value_count > 4096 || (value_count && !values))
            return fail(error, size, "invalid constant table");
        for (size_t i = 0; i < value_count; ++i)
            if (!std::isfinite(values[i])) return fail(error, size, "non-finite constant");
        for (uint32_t c = 0; c < channels; ++c) {
            const auto& p = plan[c];
            if (p.kind > 2 || p.radius > 64 || (p.kind != 1 && p.radius != 0))
                return fail(error, size, "invalid filter kind or radius");
            size_t count = p.kind == 1 ? 2 * (2 * size_t(p.radius) + 1) : (p.kind == 2 ? 8 : 0);
            if (p.offset > value_count || count > value_count - p.offset)
                return fail(error, size, "constant table bounds");
        }
        size_t image_bytes = elements * sizeof(float);
        size_t constant_bytes = std::max<size_t>(16, value_count * sizeof(float));
        uint64_t needed = uint64_t(image_bytes) * 3 + constant_bytes;
        std::lock_guard<std::mutex> lock(context->mutex);
        auto& c = *context;
        if (needed > c.budget || image_bytes > c.device.maxBufferLength)
            return fail(error, size, "spatial working-set budget exceeded");
        for (size_t i = 0; i < elements; ++i)
            if (!std::isfinite(source[i])) return fail(error, size, "non-finite input");
        // There is never work in flight between calls. Free old sizes FIRST,
        // so resizing does not momentarily hold two full working sets.
        if (c.input.length != image_bytes || c.constants.length != constant_bytes) {
            clear(c);
            c.input = [c.device newBufferWithLength:image_bytes options:MTLResourceStorageModeShared];
            c.scratch = [c.device newBufferWithLength:image_bytes options:MTLResourceStorageModeShared];
            c.output = [c.device newBufferWithLength:image_bytes options:MTLResourceStorageModeShared];
            c.constants = [c.device newBufferWithLength:constant_bytes options:MTLResourceStorageModeShared];
        }
        c.high_water = std::max(c.high_water, resident(c));
        if (!c.input || !c.scratch || !c.output || !c.constants) {
            clear(c);
            return fail(error, size, "Metal buffer allocation failed");
        }
        std::memcpy(c.input.contents, source, image_bytes);
        if (value_count) std::memcpy(c.constants.contents, values, value_count * sizeof(float));
        id<MTLCommandBuffer> command = [c.queue commandBuffer];
        if (!command) return fail(error, size, "cannot create spatial command buffer");
        uint64_t dispatches = 0;
        // Separate encoders and tracked buffers order dependencies without
        // waiting on the CPU between passes. Identity channels write output.
        for (unsigned pass = 0; pass != 2; ++pass) {
            for (uint32_t ch = 0; ch < channels; ++ch) {
                const auto& p = plan[ch];
                if (p.kind == 0 && pass != 0) continue;
                unsigned axis = p.kind == 2 ? 1 - pass : pass;
                uint32_t meta[6] = {height, width, channels, ch, axis, p.radius};
                id<MTLComputePipelineState> state = p.kind == 0 ? c.copy : (p.kind == 1 ? c.fir : c.recursive);
                size_t threads = p.kind == 2 ? (axis == 0 ? width : height) : pixels;
                id<MTLBuffer> in = pass == 0 ? c.input : c.scratch;
                id<MTLBuffer> out = pass == 1 || p.kind == 0 ? c.output : c.scratch;
                if (!encode(command, state, in, out, p.kind ? c.constants : nil,
                            p.offset * sizeof(float), meta, threads))
                    return fail(error, size, "cannot encode spatial pass");
                ++dispatches;
            }
        }
        if (!complete(command, error, size)) return 1;
        const float* result = static_cast<const float*>(c.output.contents);
        for (size_t i = 0; i < elements; ++i)
            if (!std::isfinite(result[i])) return fail(error, size, "non-finite spatial result");
        // Publish only after successful completion and numerical-domain checks.
        std::memcpy(destination, result, image_bytes);
        double seconds = command.GPUEndTime - command.GPUStartTime;
        *stats = {resident(c), c.high_water, image_bytes, image_bytes, dispatches,
                  std::isfinite(seconds) && seconds > 0 ? uint64_t(seconds * 1e9) : 0};
        return 0;
    }, error, size);
}
