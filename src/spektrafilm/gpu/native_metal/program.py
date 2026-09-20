"""Immutable execution data, not a second optical model. No GPU imports."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import operator
import struct
import warnings

import numpy as np

EXECUTION_VERSION = 1
GRAIN_VERSION = "philox4x32-10-thinned-poisson-v1"
GAUSSIAN, AFFINE, MIX, CURVE, SPECTRAL, GRAIN, LOGNORMAL, MULTIPLY, LOG10, EXP10, GAUSSIAN_MIX, MATRIX = range(1, 13)


class CanonicalModelWarning(RuntimeWarning):
    """Reference behavior is preserved outside its intended monotonic domain."""


def integer(value, *, maximum=0xFFFFFFFF):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("boolean is not an execution integer")
    try:
        value = operator.index(value)
    except TypeError as error:
        raise ValueError("an exact integer is required") from error
    if not 0 <= value <= maximum:
        raise ValueError("execution integer out of range")
    return value


def pairs(values) -> tuple[float, ...]:
    data = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(data).all() or np.any(np.abs(data) > np.finfo(np.float32).max):
        raise ValueError("constants must be finite and representable")
    high = data.astype(np.float32)
    low = (data - high.astype(np.float64)).astype(np.float32)
    return tuple(float(x) for x in np.column_stack((high, low)).ravel())


def vector(value, channels):
    a = np.asarray(value, dtype=np.float64)
    if a.ndim == 0:
        a = np.full(channels, a.item())
    if a.shape != (channels,) or not np.isfinite(a).all():
        raise ValueError("expected finite scalar or per-channel vector")
    return a


@dataclass(frozen=True)
class Node:
    code: int
    inputs: tuple[int, ...]
    constants: tuple[float, ...] = ()
    args: tuple[int, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "code", integer(self.code, maximum=12))
        object.__setattr__(self, "inputs", tuple(integer(x) for x in self.inputs))
        object.__setattr__(self, "args", tuple(integer(x) for x in self.args))
        if not self.code or len(self.args) > 12 or len(self.inputs) != (2 if self.code in (MIX, MULTIPLY, GAUSSIAN_MIX) else 1):
            raise ValueError("invalid operation arity or arguments")
        data = tuple(float(x) for x in self.constants)
        if not all(math.isfinite(x) and abs(x) <= np.finfo(np.float32).max for x in data):
            raise ValueError("non-finite or overflowing prepared constant")
        object.__setattr__(self, "constants", data)


@dataclass(frozen=True)
class Program:
    channels: int
    nodes: tuple[Node, ...]
    output: int

    def __post_init__(self):
        object.__setattr__(self, "channels", integer(self.channels, maximum=4))
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "output", integer(self.output))
        if not self.channels or len(self.nodes) > 4096 or self.output > len(self.nodes):
            raise ValueError("program bounds")
        for i, node in enumerate(self.nodes, 1):
            if not isinstance(node, Node) or any(x >= i for x in node.inputs):
                raise ValueError("execution graph must be acyclic and topologically ordered")

    def compile(self):
        # Prune unreachable nodes. Last-use reuse is AFTER the consuming op,
        # never in-place. Slot 0 stays immutable even after its last reader.
        needed = {self.output}
        for i in range(len(self.nodes), 0, -1):
            if i in needed:
                needed.update(self.nodes[i - 1].inputs)
        last = {0: 0}
        for i, node in enumerate(self.nodes, 1):
            if i in needed:
                for x in node.inputs:
                    last[x] = i
        last[self.output] = len(self.nodes) + 1
        mapping, free, next_slot = {0: 0}, [], 1
        operations, constants, interned = [], [], {}
        for i, node in enumerate(self.nodes, 1):
            if i not in needed:
                continue
            destination = min(free) if free else next_slot
            if free:
                free.remove(destination)
            else:
                next_slot += 1
            inputs = [mapping[x] for x in node.inputs]
            a, b = inputs[0], inputs[1] if len(inputs) == 2 else 0
            key = np.asarray(node.constants, dtype="<f4").tobytes()
            if key not in interned:
                interned[key] = len(constants)
                constants.extend(node.constants)
            operations.append((node.code, a, b, destination, interned[key], len(node.constants),
                               *node.args, *(0 for _ in range(12 - len(node.args)))))
            mapping[i] = destination
            for x in set(node.inputs):
                if x and last[x] == i:
                    free.append(mapping.pop(x))
        if next_slot > 128 or len(constants) > 16777216:
            raise ValueError("prepared execution capacity exceeded")
        # At least one float gives the C ABI a non-null table even for identity.
        wire = np.asarray(operations, dtype=np.uint32).reshape(-1, 18)
        data = np.asarray(constants or (0.0,), dtype=np.float32)
        digest = hashlib.sha256(struct.pack("<IIII", EXECUTION_VERSION, self.channels,
                                            next_slot, mapping[self.output]))
        digest.update(GRAIN_VERSION.encode())
        digest.update(wire.astype("<u4", copy=False).tobytes())
        digest.update(data.astype("<f4", copy=False).tobytes())
        wire.flags.writeable = data.flags.writeable = False
        return Compiled(wire, data, next_slot, mapping[self.output], digest.hexdigest())


@dataclass(frozen=True)
class Compiled:
    operations: np.ndarray
    constants: np.ndarray
    slots: int
    output: int
    fingerprint: str


class Builder:
    """Only prepares constants; images enter later through the executor."""
    def __init__(self, channels=3):
        self.channels = integer(channels, maximum=4)
        if not self.channels:
            raise ValueError("empty channel set")
        self.nodes: list[Node] = []

    def add(self, code, inputs, constants=(), args=()):
        node = Node(code, inputs, constants, args)
        if any(x > len(self.nodes) for x in node.inputs):
            raise ValueError("node reads an unknown value")
        self.nodes.append(node)
        return len(self.nodes)

    def finish(self, output=None):
        return Program(self.channels, tuple(self.nodes), len(self.nodes) if output is None else output)

    def gaussian(self, source, sigma, truncate=3.0):
        from . import prepare_gaussian
        plan = prepare_gaussian(sigma, self.channels, truncate=truncate)
        return self.add(GAUSSIAN, (source,), plan.constants, tuple(x for entry in plan.entries for x in entry))

    def extend(self, program, source):
        if program.channels != self.channels:
            raise ValueError("program channel mismatch")
        mapping = {0: source}
        for i, node in enumerate(program.nodes, 1):
            mapping[i] = self.add(node.code, tuple(mapping[x] for x in node.inputs), node.constants, node.args)
        return mapping[program.output]

    def gaussian_mix(self, source, accumulator, sigma, accumulator_scale=1.0, weight=1.0):
        from . import prepare_gaussian
        plan = prepare_gaussian(sigma, self.channels)
        constants = plan.constants + pairs(np.r_[vector(accumulator_scale, self.channels), vector(weight, self.channels)])
        return self.add(GAUSSIAN_MIX, (source, accumulator), constants, tuple(x for entry in plan.entries for x in entry))

    def matrix(self, source, matrix):
        matrix = np.asarray(matrix, dtype=np.float64)
        if self.channels != 3 or matrix.shape != (3, 3):
            raise ValueError("expected a 3x3 output-row/input-column matrix")
        return self.add(MATRIX, (source,), pairs(matrix))

    def exponential(self, source, decay):
        from spektrafilm.utils.fast_gaussian_filter import _EXPONENTIAL_GAUSSIAN_FITS
        decay = vector(decay, self.channels)
        result = None
        for amplitude, ratio in _EXPONENTIAL_GAUSSIAN_FITS[3]:
            result = (self.affine(self.gaussian(source, decay * ratio), amplitude) if result is None
                      else self.gaussian_mix(source, result, decay * ratio, weight=amplitude))
        return result

    def affine(self, source, scale=1.0, offset=0.0):
        return self.add(AFFINE, (source,), pairs(np.r_[vector(scale, self.channels), vector(offset, self.channels)]))

    def mix(self, left, right, left_scale=1.0, right_scale=1.0):
        return self.add(MIX, (left, right), pairs(np.r_[vector(left_scale, self.channels), vector(right_scale, self.channels)]))

    def curve(self, source, axis, values):
        axis = np.asarray(axis, dtype=np.float64)
        values = np.asarray(values, dtype=np.float64)
        if axis.ndim == 1:
            axis = np.repeat(axis[:, None], self.channels, axis=1)
        if axis.ndim != 2 or axis.shape != values.shape or axis.shape[1] != self.channels or not 2 <= len(axis) <= 4096:
            raise ValueError("invalid curve shape")
        if np.any(np.diff(axis, axis=0) < 0):
            raise ValueError("non-monotonic interpolation axis")
        return self.add(CURVE, (source,), pairs(np.r_[axis.ravel(), values.ravel()]), (len(axis),))

    def spectral(self, source, channel_density, base_density, illuminant, sensitivity):
        dyes = np.asarray(channel_density, dtype=np.float64)
        base = np.asarray(base_density, dtype=np.float64)
        light = np.asarray(illuminant, dtype=np.float64)
        response = np.asarray(sensitivity, dtype=np.float64)
        if self.channels != 3 or dyes.ndim != 2 or dyes.shape[1] != 3 or response.shape != dyes.shape or base.shape != (len(dyes),) or light.shape != base.shape or not 1 <= len(base) <= 256:
            raise ValueError("invalid spectral table")
        rows = np.column_stack((dyes, base, light, response))
        if np.isinf(rows).any():
            raise ValueError("infinite spectral constant")
        # NaN density or illumination makes transmitted light zero in the CPU
        # oracle. Do not sanitize individual dye coefficients into a new band.
        invalid = np.isnan(rows[:, :5]).any(axis=1)
        if np.isnan(response).any():
            raise ValueError("sanitize sensitivities in the canonical preparation")
        rows[invalid] = 0.0
        return self.add(SPECTRAL, (source,), pairs(rows), (len(rows),))


def prepare_spatial(halation, pixel_size_um, *, lens_blur_um=0.0):
    """CPU serial lens/scatter/bounce semantics, NOT the MLX FFT contract.

    The separate camera diffusion-filter PSF is deliberately not approximated.
    Pass its canonical output as input when that filter is active.
    """
    pitch = float(pixel_size_um)
    if not math.isfinite(pitch) or pitch <= 0 or not math.isfinite(lens_blur_um) or lens_blur_um < 0:
        raise ValueError("invalid physical scale")
    b = Builder(3)
    current = b.gaussian(0, lens_blur_um / pitch) if lens_blur_um else 0
    if not halation.active:
        return b.finish(current)
    amount, scale = float(halation.scatter_amount), float(halation.scatter_spatial_scale)
    weight = vector(halation.scatter_tail_weight, 3)
    core = vector(halation.scatter_core_um, 3) * scale / pitch
    tail = vector(halation.scatter_tail_um, 3) * scale / pitch
    if not math.isfinite(amount) or amount < 0 or not math.isfinite(scale) or scale < 0:
        raise ValueError("invalid scatter scale")
    if amount > 0 and (np.any(core > 0) or np.any(tail > 0)):
        core_node = b.gaussian(current, np.maximum(core, 1e-6))
        # Keep the CPU fit sum of 0.9999; do not normalize as the FFT path does.
        tail_node = b.exponential(current, np.maximum(tail, 1e-6))
        scatter = b.mix(core_node, tail_node, 1 - weight, weight)
        current = b.mix(current, scatter, 1 - amount, amount)
    strength = vector(halation.halation_strength, 3) * float(halation.halation_amount)
    sigma = vector(halation.halation_first_sigma_um, 3) * float(halation.halation_spatial_scale) / pitch
    count = integer(halation.halation_n_bounces, maximum=64)
    decay = float(halation.halation_bounce_decay)
    if not math.isfinite(decay) or not 0 <= decay <= 1:
        raise ValueError("invalid bounce decay")
    if halation.halation_amount > 0 and count and np.any(strength > 0) and np.any(sigma > 0):
        weights = np.asarray([decay ** k for k in range(count)], dtype=np.float64)
        weights /= weights.sum()
        reflected = None
        for k, weight_k in enumerate(weights, 1):
            widths = np.maximum(sigma * np.sqrt(k), 1e-6)
            reflected = (b.affine(b.gaussian(current, widths), weight_k) if reflected is None
                         else b.gaussian_mix(current, reflected, widths, weight=weight_k))
        current = b.mix(current, reflected, 1, strength)
        if halation.halation_renormalize:
            current = b.affine(current, 1 / (1 + strength))
    return b.finish(current)


def prepare_grain(density_curves, density_curves_layers, grain, pixel_size_um,
                  *, positive=False, seed=0, pixel_origin=0):
    """Fused sub-layer interpolation and Poisson thinning, explicitly versioned.

    Distributional CPU parity, not legacy MLX/scipy random-stream identity.
    Particle blur, per-channel microstructure and final grain blur remain in order.
    """
    from . import prepare_gaussian
    b = Builder(3)
    if not grain.active:
        return b.finish(0)
    if not grain.sublayers_active:
        return _prepare_simple_grain(density_curves, grain, pixel_size_um, seed, pixel_origin)
    seed = integer(seed, maximum=2**64 - 1)
    origin = integer(pixel_origin, maximum=2**64 - 1)
    axis = np.asarray(density_curves, dtype=np.float64)
    layers = np.asarray(density_curves_layers, dtype=np.float64)
    if axis.ndim != 2 or axis.shape[1] != 3 or layers.shape != (len(axis), 3, 3) or not 2 <= len(axis) <= 4096:
        raise ValueError("invalid grain curves")
    if not np.isfinite(axis).all() or not np.isfinite(layers).all() or not math.isfinite(pixel_size_um) or pixel_size_um <= 0:
        raise ValueError("non-finite grain data or invalid pixel pitch")
    maximum = np.max(layers, axis=0)
    if np.any(maximum <= 0):
        raise ValueError("each grain layer must have positive maximum density")
    fractions = maximum / maximum.sum(axis=0)
    minimum = fractions * vector(grain.density_min, 3)
    area = float(grain.agx_particle_area_um2) * vector(grain.agx_particle_scale_layers, 3)[:, None] * vector(grain.agx_particle_scale, 3)
    if not np.isfinite(area).all() or np.any(area <= 0):
        raise ValueError("invalid particle area")
    particles = pixel_size_um**2 * fractions / area
    maximum = maximum + minimum
    uniformity = np.broadcast_to(vector(grain.uniformity, 3), (3, 3))
    if np.any(maximum <= 0) or np.any(uniformity < 0) or np.any(uniformity > 1):
        raise ValueError("invalid grain maximum or uniformity")
    axis = -axis if positive else axis.copy()
    if np.any(np.diff(axis, axis=0) < 0):
        warnings.warn(
            "fitted grain density axis is non-monotonic; preserving the CPU "
            "fast_interp binary search without sorting or changing profile values",
            CanonicalModelWarning, stacklevel=2,
        )
    constants = pairs(np.r_[axis.ravel(), layers.ravel(), np.stack((minimum, maximum, particles, uniformity), axis=-1).ravel()])
    args = [len(axis), int(positive), seed & 0xFFFFFFFF, seed >> 32, 0,
            origin & 0xFFFFFFFF, origin >> 32, 0]
    sigma = float(grain.blur_dye_clouds_um) * np.sqrt(maximum / particles)
    if not np.isfinite(sigma).all() or np.any(sigma < 0):
        raise ValueError("invalid dye-cloud blur")
    plans = [prepare_gaussian(s, 3) for s in sigma]
    delta = all(all(e[0] == 0 or (e[0] == 1 and e[1] == 0) for e in p.entries) for p in plans)
    if delta:
        current = b.add(GRAIN, (0,), constants, tuple(args))
    else:
        current = None
        for sl in range(3):
            args[7] = sl + 1
            one = b.add(GRAIN, (0,), constants, tuple(args))
            one = b.gaussian(one, sigma[sl])
            current = one if current is None else b.mix(current, one)
    micro_blur, micro_spread = grain.micro_structure
    spread = float(micro_spread) * 0.001 / pixel_size_um
    if spread > 0.05:
        sigma_log = np.sqrt(np.log1p(spread * spread))
        random_args = (0, 0, seed & 0xFFFFFFFF, seed >> 32, 9, origin & 0xFFFFFFFF, origin >> 32)
        field = b.add(LOGNORMAL, (0,), pairs([sigma_log]), random_args)
        if micro_blur / pixel_size_um > 0.4:
            field = b.gaussian(field, micro_blur / pixel_size_um)
        current = b.add(MULTIPLY, (current, field))
    current = b.affine(current, 1, -vector(grain.density_min, 3))
    if grain.blur > 0:
        current = b.gaussian(current, grain.blur)
    return b.finish(current)


def _prepare_simple_grain(curves, grain, pitch, seed, origin):
    # Reuse the layer sampler, not another RNG implementation. An identity
    # density interpolation spans exactly the unclipped probability interval.
    seed = integer(seed, maximum=2**64 - 1)
    origin = integer(origin, maximum=2**64 - 1)
    count = integer(grain.n_sub_layers, maximum=64)
    if not count or not math.isfinite(pitch) or pitch <= 0:
        raise ValueError("invalid simple-grain geometry")
    curves = np.asarray(curves, dtype=np.float64)
    if curves.ndim != 2 or curves.shape[1] != 3 or not np.isfinite(curves).all():
        raise ValueError("invalid simple-grain curves")
    minimum = vector(grain.density_min, 3)
    maximum = np.max(curves, axis=0) + minimum
    area = float(grain.agx_particle_area_um2) * vector(grain.agx_particle_scale, 3)
    if np.any(area <= 0) or np.any(maximum <= 0):
        raise ValueError("invalid simple-grain particles")
    particles = pitch**2 / area / count
    uniformity = vector(grain.uniformity, 3)
    if np.any(uniformity < 0) or np.any(uniformity > 1):
        raise ValueError("invalid simple-grain uniformity")
    axis = np.stack((-minimum, maximum-minimum))
    layers = np.repeat(axis[:, None, :], 3, axis=1)
    parameters = np.repeat(np.stack((minimum, maximum, particles, uniformity), -1)[None, ...], 3, axis=0)
    constants = pairs(np.r_[axis.ravel(), layers.ravel(), parameters.ravel()])
    b = Builder()
    current = None
    for layer in range(count):
        args = (2, 0, seed & 0xFFFFFFFF, seed >> 32, 3*layer, origin & 0xFFFFFFFF, origin >> 32, 1)
        one = b.add(GRAIN, (0,), constants, args)
        current = one if current is None else b.mix(current, one)
    current = b.affine(current, 1/count, -minimum)
    if grain.blur > 0.4:
        current = b.gaussian(current, grain.blur)
    return b.finish(current)


def prepare_development(log_exposure, density_curves, density_curves_layers,
                        dir_couplers, grain, pixel_size_um, *, positive=False,
                        gamma=1.0, seed=0, pixel_origin=0):
    """Real film log exposure -> negative CMY, using canonical setup functions.

    This is a callable optical stage, not a replacement RGB-in/RGB-out API.
    CPU setup owns the DIR inverse and donor/receiver matrix, including its
    legacy handling of non-monotonic inverse axes. Report that source-model
    condition; do not replace or repair its prepared curves in this backend.
    """
    from spektrafilm.model.couplers import (
        compute_dir_couplers_matrix, compute_density_curves_before_dir_couplers,
    )
    axis = np.asarray(log_exposure, dtype=np.float64)
    curves = np.asarray(density_curves, dtype=np.float64)
    if axis.ndim != 1 or curves.shape != (len(axis), 3) or not np.isfinite(curves).all():
        raise ValueError("invalid film density curves")
    curves = curves - np.min(curves, axis=0)
    gamma = vector(gamma, 3)
    if np.any(gamma <= 0):
        raise ValueError("density-curve gamma must be positive")
    b = Builder()
    density = b.curve(0, axis[:, None]/gamma, curves)
    if dir_couplers.active:
        matrix = compute_dir_couplers_matrix(dir_couplers) * dir_couplers.amount
        maximum = np.max(curves, axis=0)
        silver_curves = maximum-curves if positive else curves
        inverse_axis = axis[:, None] - silver_curves @ matrix
        if np.any(np.diff(inverse_axis, axis=0) <= 0):
            warnings.warn(
                "canonical DIR inverse exposure axis is non-monotonic; using "
                "the CPU-prepared curve, not claiming a valid physical inverse",
                CanonicalModelWarning, stacklevel=2,
            )
        before = compute_density_curves_before_dir_couplers(curves, axis, matrix, positive=positive)
        silver = b.affine(density, -1, maximum) if positive else density
        correction = b.matrix(silver, matrix.T)
        if dir_couplers.diffusion_size_um > 0:
            if not math.isfinite(pixel_size_um) or pixel_size_um <= 0:
                raise ValueError("invalid DIR pixel pitch")
            core = b.gaussian(correction, dir_couplers.diffusion_size_um / pixel_size_um)
            tail = b.exponential(correction, dir_couplers.diffusion_tail_um / pixel_size_um)
            weight = float(dir_couplers.diffusion_tail_weight)
            correction = b.mix(core, tail, 1-weight, weight)
        corrected = b.mix(0, correction, 1, -1)
        density = b.curve(corrected, axis[:, None]/gamma, before)
    density = b.extend(prepare_grain(curves, density_curves_layers, grain, pixel_size_um,
                                    positive=positive, seed=seed, pixel_origin=pixel_origin), density)
    return b.finish(density)
