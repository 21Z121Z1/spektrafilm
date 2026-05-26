# Spektrafilm - GPU & Color Management Research Instructions

## Research Goal
Research and implement cross-platform GPU acceleration and comprehensive color management for the Spektrafilm project.

## Available MCP Tools
- `web-search` — DuckDuckGo/Bing web search (no API key needed)
- `markfetch` — Fetch URLs and convert to clean markdown

## Research Areas

### 1. Cross-Platform GPU Acceleration System
Search for and document best practices in:
- **Vulkan Compute** — cross-platform GPU compute (Linux/Windows/Android)
- **WebGPU** — emerging standard, works everywhere via Dawn/wgpu
- **OpenCL** — mature cross-platform compute
- **Metal** — Apple ecosystem (already partially supported via MLX)
- **CUDA** — NVIDIA (already partially supported via CuPy)
- **SYCL/oneAPI** — Intel's cross-platform GPU programming model
- **Array API Standard** — NumPy-compatible GPU arrays (CuPy, JAX, PyTorch)

Key questions to research:
- What is the best Python GPU abstraction layer for scientific computing that works across Metal/CUDA/Vulkan?
- How do projects like OpenColorIO, Little CMS, and Colour Science handle GPU-accelerated color transforms?
- What are the performance characteristics of MLX vs CuPy vs PyTorch for image processing pipelines?
- How to implement GPU tiling for large images (100MP+) with limited VRAM?
- Best practices for GPU fallback chains (try Metal → CUDA → CPU)

### 2. Color Management System
Search for and document best practices in:
- **ICC Profile** handling — creation, embedding, validation
- **ACES** workflow — ACEScg, ACES2065-1, ACEScct, ODT/RRT
- **HDR standards** — HDR10, HDR10+, Dolby Vision, HLG, gain maps
- **OpenColorIO (OCIO)** — industry-standard color management
- **Display-referred vs scene-referred** workflows
- **Tone mapping** operators — Reinhard, filmic, ACES, display-referred
- **Gamut mapping** — perceptual, absolute colorimetric, relative colorimetric

Key questions to research:
- How does DaVinci Resolve / Nuke / Blender handle cross-gamut color management?
- What is the state of the art for HDR gain map encoding (Apple/Adobe specs)?
- How to properly implement ACES output transforms for different display capabilities?
- Best practices for ICC v4 vs v2 profile compatibility
- How do professional tools validate color pipeline integrity?

### 3. Python-Specific Implementation Patterns
Search for:
- **colour-science** library GPU capabilities and API
- **OpenColorIO** Python bindings for ACES workflows
- **OpenImageIO** Python bindings for metadata-aware I/O
- **Array API** interoperability between CuPy/MLX/NumPy
- How to structure a GPU-capable image processing pipeline in Python

## Research Process
1. For each area, search the web thoroughly using `web-search`
2. Fetch and read the most relevant articles/docs using `markfetch`
3. Document findings in `docs/dev/research-gpu-color-management.md`
4. Include code examples, API references, and architecture patterns
5. Rate each approach by: cross-platform support, performance, maintenance burden, Python ecosystem fit

## Output Format
Write findings to `docs/dev/research-gpu-color-management.md` with:
- Executive summary (1 paragraph)
- GPU acceleration comparison table
- Color management architecture recommendations
- Specific library/tool recommendations with version info
- Code snippets showing integration patterns
- References with URLs
