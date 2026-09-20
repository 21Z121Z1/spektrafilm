// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "execution.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <vector>

static_assert(sizeof(sfm_operation)==72 && offsetof(sfm_operation,args)==24,"execution wire layout");

namespace {
struct Ledger { std::atomic<uint64_t> live{0}, peak{0}; uint64_t limit; explicit Ledger(uint64_t n):limit(n){} };
struct Allocation {
    id<MTLBuffer> memory;
    std::shared_ptr<Ledger> ledger;
    uint64_t bytes = 0;
    ~Allocation() { if (ledger) ledger->live.fetch_sub(bytes); }
};
using Buffer = std::shared_ptr<Allocation>;
struct Core {
    id<MTLDevice> device;
    id<MTLCommandQueue> queue;
    id<MTLComputePipelineState> fir, recursive, copy, transpose, pointwise, validate, pack, probe, rng;
    id<MTLComputePipelineState> fir_mix, recursive_mix, copy_mix;
    std::shared_ptr<Ledger> ledger;
    std::vector<Buffer> pool;
    std::mutex mutex;
    bool closed = false;
    void check() { if (closed) throw std::runtime_error("executor is closed"); }
    void trim() {
        pool.erase(std::remove_if(pool.begin(), pool.end(), [](const Buffer& p){return p.use_count()==1;}),pool.end());
    }
    Buffer allocate(size_t bytes, bool pooled = false) {
        if (!bytes || bytes > device.maxBufferLength) throw std::runtime_error("invalid Metal buffer length");
        if (pooled) for (const auto& p : pool) if (p.use_count()==1 && p->bytes==bytes) return p;
        uint64_t live=ledger->live.load();
        if (live > ledger->limit || bytes > ledger->limit-live) { trim(); live=ledger->live.load(); }
        if (live > ledger->limit || bytes > ledger->limit-live) throw std::runtime_error("native resident allocation budget exceeded");
        auto p=std::make_shared<Allocation>();
        p->memory=[device newBufferWithLength:bytes options:MTLResourceStorageModeShared | MTLResourceHazardTrackingModeTracked];
        if (!p->memory) throw std::runtime_error("Metal buffer allocation failed");
        p->bytes=bytes; p->ledger=ledger;
        uint64_t now=ledger->live.fetch_add(bytes)+bytes;
        ledger->peak.store(std::max(ledger->peak.load(),now));
        if (pooled) pool.push_back(p);
        return p;
    }
};
int failure(char* e, size_t n, const char* what) { if(e && n) std::snprintf(e,n,"%s",what?what:"Metal failure"); return 1; }
template<class F> int guard(F fn, char* e, size_t n) noexcept {
    if(e && n) e[0]=0;
    @autoreleasepool { @try { try { fn(); return 0; }
        catch(const std::exception& x){return failure(e,n,x.what());}
        catch(...){return failure(e,n,"unknown native exception");}
    } @catch(NSException* x){return failure(e,n,x.reason.UTF8String);} }
}
void require(bool ok,const char* message){if(!ok) throw std::runtime_error(message);}
id<MTLComputePipelineState> load(Core& c,id<MTLLibrary> library,NSString* name) {
    id<MTLFunction> f=[library newFunctionWithName:name];
    require(f!=nil,"missing prepared-execution kernel");
    NSError* error=nil;
    id<MTLComputePipelineState> result=[c.device newComputePipelineStateWithFunction:f error:&error];
    if(!result) throw std::runtime_error(error?error.localizedDescription.UTF8String:"pipeline creation failed");
    return result;
}
id<MTLComputeCommandEncoder> encoder(id<MTLCommandBuffer> cb,id<MTLComputePipelineState> state) {
    auto e=[cb computeCommandEncoder];require(e!=nil,"compute encoder creation failed");
    [e setComputePipelineState:state];return e;
}
void dispatch(id<MTLComputeCommandEncoder> e,id<MTLComputePipelineState> state,size_t threads) {
    NSUInteger width=std::min<NSUInteger>(256,state.maxTotalThreadsPerThreadgroup);
    require(width!=0,"invalid compute threadgroup limit");
    [e dispatchThreads:MTLSizeMake(threads,1,1) threadsPerThreadgroup:MTLSizeMake(width,1,1)];
    [e endEncoding];
}
void finish(id<MTLCommandBuffer> cb) {
    require(cb!=nil,"command buffer creation failed");[cb commit];[cb waitUntilCompleted];
    if(cb.status!=MTLCommandBufferStatusCompleted)
        throw std::runtime_error(cb.error?cb.error.localizedDescription.UTF8String:"Metal command failed");
}
void spatial(id<MTLCommandBuffer> cb,id<MTLComputePipelineState> state,const Buffer& a,const Buffer& out,
             const Buffer& constants,size_t offset,const uint32_t* m,size_t threads,const Buffer* accumulation=nullptr,size_t mix_offset=0) {
    auto e=encoder(cb,state);[e setBuffer:a->memory offset:0 atIndex:0];[e setBuffer:out->memory offset:0 atIndex:1];
    [e setBuffer:constants->memory offset:offset atIndex:2];[e setBytes:m length:24 atIndex:3];
    if(accumulation){[e setBuffer:(*accumulation)->memory offset:0 atIndex:4];[e setBuffer:constants->memory offset:mix_offset atIndex:5];}
    dispatch(e,state,threads);
}
void statistics(const Core& c,sfm_execution_stats& s) {
    s.allocated_bytes=c.ledger->live.load();s.high_water_bytes=c.ledger->peak.load();
}
size_t shape(uint32_t h,uint32_t w,uint32_t c) {
    require(h && w && h<=16384 && w<=16384 && c && c<=4,"invalid native image shape");
    require(uint64_t(h)*w*c<=UINT32_MAX,"native image index overflow");return size_t(h)*w*c;
}
double pair(const float* x,size_t i){return double(x[2*i])+double(x[2*i+1]);}
void check_axis(const float* x,uint32_t n,uint32_t c) {
    for(uint32_t ch=0;ch<c;++ch) for(uint32_t j=1;j<n;++j)
        require(pair(x,size_t(j)*c+ch)>=pair(x,size_t(j-1)*c+ch),"non-monotonic interpolation axis");
}
void check_operation(const sfm_operation& o,const float* constants,size_t count,uint32_t channels) {
    require(o.code>=1 && o.code<=12,"unknown execution operation");
    require(o.offset<=count && o.count<=count-o.offset,"execution constant bounds");
    const float* d=constants+o.offset;
    uint64_t needed=0,n=o.args[0];
    if(o.code==1 || o.code==11) {
        for(uint32_t ch=0;ch<channels;++ch) {
            uint32_t kind=o.args[3*ch],r=o.args[3*ch+1],off=o.args[3*ch+2];
            require(kind<=2 && r<=64 && (kind==1 || r==0),"invalid Gaussian descriptor");
            uint32_t length=kind==1?2*(2*r+1):(kind==2?8:0);
            require(o.code!=11 || o.count>=4*channels,"Gaussian mix constant bounds");
            uint32_t available=o.count-(o.code==11?4*channels:0);
            require(off<=available && length<=available-off,"Gaussian constant bounds");
        }
    } else if(o.code==2 || o.code==3) needed=4*channels;
    else if(o.code==4) {
        require(n>=2 && n<=4096,"invalid curve sample count");needed=4*n*channels;
    } else if(o.code==5) {
        require(channels==3 && n>0 && n<=256,"invalid spectral shape");needed=16*n;
    } else if(o.code==6) {
        require(channels==3 && n>=2 && n<=4096 && o.args[1]<=1 && o.args[7]<=3,"invalid grain shape");
        require(o.args[4]<=UINT32_MAX-8,"grain stream overflow");needed=24*n+72;
    } else if(o.code==7) needed=2;
    else if(o.code==12){require(channels==3,"matrix operation requires RGB");needed=18;}
    require(needed==0 || needed==o.count,"incorrect prepared constant count");
    if(o.code==4 || o.code==6) check_axis(d,uint32_t(n),channels);
    if(o.code==6) for(unsigned j=0;j<9;++j) {
        const float* p=d+24*n;
        require(pair(p,4*j+1)>0 && pair(p,4*j+2)>0 && pair(p,4*j+3)>=0 && pair(p,4*j+3)<=1,"invalid grain particle constants");
    }
    if(o.code==7){require(pair(d,0)>=0 && pair(d,0)<=4,"invalid lognormal sigma");require(o.args[4]<=UINT32_MAX-(channels-1),"lognormal stream overflow");}
}
} // namespace
struct sfm_executor { std::shared_ptr<Core> core; };
struct sfm_program {
    std::shared_ptr<Core> core;Buffer constants;std::vector<sfm_operation> operations;
    uint32_t channels=0,slots=0,output=0;bool gaussian=false;
};
struct sfm_image { std::shared_ptr<Core> core;Buffer buffer;uint32_t height,width,channels; };
struct sfm_texture { std::shared_ptr<Core> core;Buffer buffer;id<MTLTexture> texture; };

uint32_t sfm_execution_version(void) noexcept{return 1;}
int sfm_executor_create(const char* path,uint64_t budget,sfm_executor** out,char* e,size_t n) noexcept {
    if(out)*out=nullptr;
    return guard([&]{
        require(path && out && budget>=64,"invalid executor arguments");auto c=std::make_shared<Core>();
        c->device=MTLCreateSystemDefaultDevice();require(c->device && c->device.hasUnifiedMemory,"unified-memory Metal device required");
        c->ledger=std::make_shared<Ledger>(budget);c->queue=[c->device newCommandQueue];require(c->queue!=nil,"command queue creation failed");
        NSString* p=[NSString stringWithUTF8String:path];require(p!=nil,"invalid UTF-8 library path");NSError* error=nil;
        auto library=[c->device newLibraryWithURL:[NSURL fileURLWithPath:p] error:&error];
        require(library!=nil,"cannot load prepared-execution metallib");
        c->fir=load(*c,library,@"sfm_fir");c->recursive=load(*c,library,@"sfm_recursive");c->copy=load(*c,library,@"sfm_copy");
        c->fir_mix=load(*c,library,@"sfm_fir_mix");c->recursive_mix=load(*c,library,@"sfm_recursive_mix");c->copy_mix=load(*c,library,@"sfm_copy_mix");
        c->transpose=load(*c,library,@"sfm_transpose");c->pointwise=load(*c,library,@"sfm_pointwise");
        c->validate=load(*c,library,@"sfm_validate");c->pack=load(*c,library,@"sfm_pack_rgba");
        c->probe=load(*c,library,@"sfm_probe");c->rng=load(*c,library,@"sfm_philox_probe");
        auto a=c->allocate(8),b=c->allocate(8);float v[2]={16777216.0f,1};std::memcpy(a->memory.contents,v,8);
        auto cb=[c->queue commandBuffer];require(cb!=nil,"probe command buffer creation failed");
        auto en=encoder(cb,c->probe);[en setBuffer:a->memory offset:0 atIndex:0];[en setBuffer:b->memory offset:0 atIndex:1];dispatch(en,c->probe,1);finish(cb);
        auto r=static_cast<const float*>(b->memory.contents);require(r[0]==1 && r[1]==1,"prepared-execution safe-math probe failed");
        *out=new sfm_executor{c};
    },e,n);
}
void sfm_executor_destroy(sfm_executor* p) noexcept {
    if(!p)return;@autoreleasepool{auto c=p->core;{std::lock_guard<std::mutex> lock(c->mutex);c->closed=true;c->pool.clear();}delete p;}
}
int sfm_executor_trim(sfm_executor* p,char* e,size_t n) noexcept {
    return guard([&]{require(p,"null executor");auto& c=*p->core;std::lock_guard<std::mutex> lock(c.mutex);c.check();c.trim();},e,n);
}
int sfm_executor_stats(sfm_executor* p,sfm_execution_stats* s,char* e,size_t n) noexcept {
    if(s)*s={};return guard([&]{require(p && s,"null statistics argument");auto& c=*p->core;
        std::lock_guard<std::mutex> lock(c.mutex);c.check();statistics(c,*s);},e,n);
}
int sfm_program_create(sfm_executor* p,const sfm_operation* ops,size_t count,const float* values,size_t value_count,
                       uint32_t channels,uint32_t slots,uint32_t output,sfm_program** out,char* e,size_t n) noexcept {
    if(out)*out=nullptr;return guard([&]{
        require(p && out && (ops || !count) && values,"null program argument");
        require(count<=4096 && value_count<=16777216 && channels && channels<=4 && slots && slots<=128 && output<slots,"program limits exceeded");
        auto c=p->core;std::lock_guard<std::mutex> lock(c->mutex);c->check();
        std::vector<bool> initialized(slots,false);initialized[0]=true;
        for(size_t i=0;i<value_count;++i) require(std::isfinite(values[i]),"non-finite prepared constant");
        bool gaussian=false;
        for(size_t i=0;i<count;++i) {
            const auto& o=ops[i];bool binary=o.code==3 || o.code==8 || o.code==11;
            require(o.a<slots && o.b<slots && o.destination<slots && o.destination!=0,"invalid execution slot");
            require(initialized[o.a] && (!binary || initialized[o.b]),"uninitialized execution input");
            require(o.destination!=o.a && (!binary || o.destination!=o.b),"in-place execution is not supported");
            check_operation(o,values,value_count,channels);initialized[o.destination]=true;gaussian|=o.code==1 || o.code==11;
        }
        require(initialized[output],"uninitialized program output");
        auto result=std::make_unique<sfm_program>();result->core=c;result->channels=channels;result->slots=slots;result->output=output;result->gaussian=gaussian;
        if(count)result->operations.assign(ops,ops+count);
        result->constants=c->allocate(std::max<size_t>(16,value_count*sizeof(float)));
        if(value_count)std::memcpy(result->constants->memory.contents,values,value_count*sizeof(float));
        *out=result.release();
    },e,n);
}
void sfm_program_destroy(sfm_program* p) noexcept{@autoreleasepool{delete p;}}
int sfm_image_upload(sfm_executor* p,const float* values,size_t elements,uint32_t h,uint32_t w,uint32_t channels,sfm_image** out,char* e,size_t n) noexcept {
    if(out)*out=nullptr;return guard([&]{
        require(p && values && out,"null upload argument");require(shape(h,w,channels)==elements,"upload element count mismatch");
        for(size_t i=0;i<elements;++i)require(std::isfinite(values[i]),"non-finite input image");
        auto c=p->core;std::lock_guard<std::mutex> lock(c->mutex);c->check();auto result=std::make_unique<sfm_image>();
        result->core=c;result->buffer=c->allocate(elements*sizeof(float));result->height=h;result->width=w;result->channels=channels;
        std::memcpy(result->buffer->memory.contents,values,elements*sizeof(float));*out=result.release();
    },e,n);
}
int sfm_image_read(sfm_executor* p,const sfm_image* image,float* values,size_t elements,char* e,size_t n) noexcept {
    return guard([&]{require(p && image && values,"null read argument");auto c=p->core;std::lock_guard<std::mutex> lock(c->mutex);c->check();
        require(image->core==c,"image belongs to another executor");require(elements==shape(image->height,image->width,image->channels),"read element count mismatch");
        std::memcpy(values,image->buffer->memory.contents,elements*sizeof(float));},e,n);
}
void sfm_image_destroy(sfm_image* p) noexcept{@autoreleasepool{delete p;}}
int sfm_program_run(sfm_executor* p,const sfm_program* program,const sfm_image* image,sfm_image** out,sfm_execution_stats* stats,char* e,size_t n) noexcept {
    if(out)*out=nullptr;if(stats)*stats={};return guard([&]{
        require(p && program && image && out && stats,"null run argument");auto c=p->core;std::lock_guard<std::mutex> lock(c->mutex);c->check();
        require(program->core==c && image->core==c,"program or image belongs to another executor");
        require(program->channels==image->channels,"program/image channel mismatch");
        uint32_t h=image->height,w=image->width,channels=image->channels;size_t elements=shape(h,w,channels),pixels=size_t(h)*w,bytes=elements*sizeof(float);
        size_t transpose_threads=size_t((h+31)/32)*((w+31)/32)*std::min<NSUInteger>(256,c->transpose.maxTotalThreadsPerThreadgroup);
        for(const auto& o:program->operations) if(o.code==6 || o.code==7) {
            uint64_t origin=(uint64_t(o.args[6])<<32)|o.args[5];require(origin<=UINT64_MAX-(pixels-1),"random pixel counter overflow");
        }
        std::vector<Buffer> slots(program->slots);slots[0]=image->buffer;
        for(uint32_t i=1;i<program->slots;++i)slots[i]=c->allocate(bytes,true);
        Buffer tmp1,tmp2;
        if(program->gaussian){tmp1=c->allocate(bytes,true);tmp2=c->allocate(bytes,true);}
        auto flag=c->allocate(4,true);*static_cast<uint32_t*>(flag->memory.contents)=0;
        auto cb=[c->queue commandBuffer];require(cb!=nil,"run command buffer creation failed");uint64_t dispatches=0;
        for(const auto& o:program->operations) {
            if(o.code==1 || o.code==11) {
                const Buffer* accumulation=o.code==11?&slots[o.b]:nullptr;
                size_t mix_offset=o.code==11?size_t(o.offset+o.count-4*channels)*sizeof(float):0;
                for(uint32_t ch=0;ch<channels;++ch) {
                    uint32_t kind=o.args[3*ch],radius=o.args[3*ch+1];size_t offset=size_t(o.offset+o.args[3*ch+2])*sizeof(float);
                    uint32_t m[6]={h,w,channels,ch,0,radius};
                    if(kind==0){spatial(cb,accumulation?c->copy_mix:c->copy,slots[o.a],slots[o.destination],program->constants,0,m,pixels,accumulation,mix_offset);++dispatches;}
                    else if(kind==1){spatial(cb,c->fir,slots[o.a],tmp1,program->constants,offset,m,pixels);m[4]=1;
                        spatial(cb,accumulation?c->fir_mix:c->fir,tmp1,slots[o.destination],program->constants,offset,m,pixels,accumulation,mix_offset);dispatches+=2;}
                    else {
                        spatial(cb,c->transpose,slots[o.a],tmp1,program->constants,0,m,transpose_threads);
                        m[0]=w;m[1]=h;spatial(cb,c->recursive,tmp1,tmp2,program->constants,offset,m,h);
                        spatial(cb,c->transpose,tmp2,tmp1,program->constants,0,m,transpose_threads);
                        m[0]=h;m[1]=w;spatial(cb,accumulation?c->recursive_mix:c->recursive,tmp1,slots[o.destination],program->constants,offset,m,w,accumulation,mix_offset);dispatches+=4;
                    }
                }
            } else {
                uint32_t m[16]={h,w,channels,o.code};std::copy(o.args,o.args+12,m+4);
                auto en=encoder(cb,c->pointwise);[en setBuffer:slots[o.a]->memory offset:0 atIndex:0];
                [en setBuffer:slots[o.b]->memory offset:0 atIndex:1];[en setBuffer:slots[o.destination]->memory offset:0 atIndex:2];
                [en setBuffer:program->constants->memory offset:(o.count?size_t(o.offset)*sizeof(float):0) atIndex:3];
                [en setBuffer:flag->memory offset:0 atIndex:4];[en setBytes:m length:sizeof(m) atIndex:5];dispatch(en,c->pointwise,pixels);++dispatches;
            }
        }
        auto en=encoder(cb,c->validate);[en setBuffer:slots[program->output]->memory offset:0 atIndex:0];
        [en setBuffer:flag->memory offset:0 atIndex:1];uint32_t total=uint32_t(elements);[en setBytes:&total length:4 atIndex:2];
        dispatch(en,c->validate,elements);++dispatches;finish(cb);
        uint32_t bits=*static_cast<const uint32_t*>(flag->memory.contents);
        require(!bits,"native result rejected: non-finite value, sampler domain or rejection limit");
        auto result=std::make_unique<sfm_image>();result->core=c;result->buffer=slots[program->output];result->height=h;result->width=w;result->channels=channels;
        stats->dispatches=dispatches;stats->submissions=1;stats->readback_bytes=4;
        double elapsed=cb.GPUEndTime-cb.GPUStartTime;if(std::isfinite(elapsed) && elapsed>0)stats->gpu_nanoseconds=uint64_t(elapsed*1e9);
        statistics(*c,*stats);*out=result.release();
    },e,n);
}
int sfm_image_texture(sfm_executor* p,const sfm_image* image,sfm_texture** out,char* e,size_t n) noexcept {
    if(out)*out=nullptr;return guard([&]{
        require(p && image && out,"null texture argument");auto c=p->core;std::lock_guard<std::mutex> lock(c->mutex);c->check();
        require(image->core==c && image->channels==3,"texture export requires a same-executor RGB image");
        NSUInteger alignment=[c->device minimumLinearTextureAlignmentForPixelFormat:MTLPixelFormatRGBA32Float];
        require(alignment>0 && alignment%16==0,"unsupported linear texture alignment");
        size_t row=(size_t(image->width)*16+alignment-1)/alignment*alignment;
        auto result=std::make_unique<sfm_texture>();result->core=c;result->buffer=c->allocate(row*image->height);
        auto descriptor=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA32Float width:image->width height:image->height mipmapped:NO];
        descriptor.storageMode=MTLStorageModeShared;descriptor.usage=MTLTextureUsageShaderRead;
        result->texture=[result->buffer->memory newTextureWithDescriptor:descriptor offset:0 bytesPerRow:row];
        require(result->texture!=nil,"cannot create buffer-backed RGBA32Float texture");
        auto cb=[c->queue commandBuffer];require(cb!=nil,"texture command buffer creation failed");auto en=encoder(cb,c->pack);
        [en setBuffer:image->buffer->memory offset:0 atIndex:0];[en setBuffer:result->buffer->memory offset:0 atIndex:1];
        uint32_t m[4]={image->height,image->width,3,uint32_t(row/16)};[en setBytes:m length:sizeof(m) atIndex:2];
        dispatch(en,c->pack,size_t(image->height)*image->width);finish(cb);*out=result.release();
    },e,n);
}
void* sfm_texture_handle(const sfm_texture* p) noexcept{return p?(__bridge void*)p->texture:nullptr;}
void sfm_texture_destroy(sfm_texture* p) noexcept{@autoreleasepool{delete p;}}
int sfm_executor_philox(sfm_executor* p,const uint32_t counter[4],const uint32_t key[2],uint32_t result[4],char* e,size_t n) noexcept {
    return guard([&]{require(p && counter && key && result,"null Philox argument");auto c=p->core;std::lock_guard<std::mutex> lock(c->mutex);c->check();
        auto a=c->allocate(24),b=c->allocate(16);std::memcpy(a->memory.contents,counter,16);std::memcpy(static_cast<char*>(a->memory.contents)+16,key,8);
        auto cb=[c->queue commandBuffer];require(cb!=nil,"Philox command buffer creation failed");auto en=encoder(cb,c->rng);
        [en setBuffer:a->memory offset:0 atIndex:0];[en setBuffer:b->memory offset:0 atIndex:1];dispatch(en,c->rng,1);finish(cb);std::memcpy(result,b->memory.contents,16);},e,n);
}

int sfm_texture_read(const sfm_texture* p,float* values,size_t elements,char* e,size_t n) noexcept {
    return guard([&]{require(p && values,"null texture read argument");auto c=p->core;std::lock_guard<std::mutex> lock(c->mutex);
        size_t width=p->texture.width,height=p->texture.height;require(elements==width*height*4,"texture read element count mismatch");
        size_t stride=p->buffer->bytes/height;const char* source=static_cast<const char*>(p->buffer->memory.contents);
        for(size_t row=0;row<height;++row)std::memcpy(values+row*width*4,source+row*stride,width*16);
    },e,n);
}
