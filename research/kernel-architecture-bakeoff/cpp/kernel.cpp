#include "../common/kernel_arch.h"

extern "C" {
#include <libavformat/avformat.h>
}

#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
#include <new>
#include <numeric>

namespace {
constexpr size_t MAX_ASSETS = 32;
constexpr size_t MAX_CLIPS = 64;
constexpr size_t MAX_PROPOSALS = 64;
constexpr size_t MAX_RESOURCES = 128;
constexpr size_t MAX_NODES = 64;
constexpr size_t MAX_DEPS = 4;
constexpr size_t MAX_ID = 128;
constexpr uint64_t FNV_OFFSET = 14695981039346656037ull;
constexpr uint64_t FNV_PRIME = 1099511628211ull;

struct Asset {
    std::array<char, MAX_ID> id{};
    size_t id_len{};
    mk_time_t duration{};
};

struct Clip {
    size_t asset_index{};
    mk_time_t source_in{};
    mk_time_t duration{};
    mk_time_t transition{};
};

struct Proposal {
    uint64_t id{};
    uint64_t base_revision{};
    size_t clip_index{};
    mk_time_t new_duration{};
};

struct ResourceSlot {
    uint32_t generation{};
    uint32_t refcount{};
    uint64_t size_bytes{};
    uint32_t domain{};
    bool active{};
};

struct PlanNode {
    uint32_t id{};
    uint32_t kind{};
    std::array<uint32_t, MAX_DEPS> deps{};
    size_t dep_count{};
    mk_resource_handle_t resource{MK_NO_RESOURCE_SLOT, 0};
};

bool normalize_time(mk_time_t in, mk_time_t &out) {
    if (in.den == 0) return false;
    if (in.num == 0) {
        out = {0, 1};
        return true;
    }
    __int128 n = in.num;
    __int128 d = in.den;
    if (d < 0) {
        n = -n;
        d = -d;
    }
    if (n < std::numeric_limits<int64_t>::min() || n > std::numeric_limits<int64_t>::max() ||
        d <= 0 || d > std::numeric_limits<int64_t>::max()) {
        return false;
    }
    const uint64_t mag = n < 0 ? static_cast<uint64_t>(-n) : static_cast<uint64_t>(n);
    const uint64_t den = static_cast<uint64_t>(d);
    const uint64_t g = std::gcd(mag, den);
    out = {static_cast<int64_t>(n / g), static_cast<int64_t>(d / g)};
    return true;
}

bool add_time(mk_time_t a, mk_time_t b, mk_time_t &out) {
    mk_time_t na{}, nb{};
    if (!normalize_time(a, na) || !normalize_time(b, nb)) return false;
    const __int128 n = static_cast<__int128>(na.num) * nb.den + static_cast<__int128>(nb.num) * na.den;
    const __int128 d = static_cast<__int128>(na.den) * nb.den;
    if (n < std::numeric_limits<int64_t>::min() || n > std::numeric_limits<int64_t>::max() ||
        d <= 0 || d > std::numeric_limits<int64_t>::max()) {
        return false;
    }
    return normalize_time({static_cast<int64_t>(n), static_cast<int64_t>(d)}, out);
}

int compare_time(mk_time_t a, mk_time_t b) {
    mk_time_t na{}, nb{};
    if (!normalize_time(a, na) || !normalize_time(b, nb)) return 0;
    const __int128 left = static_cast<__int128>(na.num) * nb.den;
    const __int128 right = static_cast<__int128>(nb.num) * na.den;
    return (left > right) - (left < right);
}

bool positive_time(mk_time_t t) {
    mk_time_t n{};
    return normalize_time(t, n) && n.num > 0;
}

uint64_t hash_byte(uint64_t h, uint8_t b) {
    return (h ^ b) * FNV_PRIME;
}

uint64_t hash_u32(uint64_t h, uint32_t v) {
    for (int i = 0; i < 4; ++i) h = hash_byte(h, static_cast<uint8_t>(v >> (i * 8)));
    return h;
}

uint64_t hash_u64(uint64_t h, uint64_t v) {
    for (int i = 0; i < 8; ++i) h = hash_byte(h, static_cast<uint8_t>(v >> (i * 8)));
    return h;
}

uint64_t hash_i64(uint64_t h, int64_t v) {
    return hash_u64(h, static_cast<uint64_t>(v));
}
}  // namespace

struct mk_kernel {
    uint64_t revision{};
    uint64_t next_proposal{1};
    std::array<Asset, MAX_ASSETS> assets{};
    size_t asset_count{};
    std::array<Clip, MAX_CLIPS> clips{};
    size_t clip_count{};
    std::array<Proposal, MAX_PROPOSALS> proposals{};
    size_t proposal_count{};
    std::array<ResourceSlot, MAX_RESOURCES> resources{};
    std::array<PlanNode, MAX_NODES> nodes{};
    size_t node_count{};
};

namespace {
int find_asset(const mk_kernel *k, const char *id) {
    if (!k || !id) return -1;
    const size_t len = std::strlen(id);
    for (size_t i = 0; i < k->asset_count; ++i) {
        if (k->assets[i].id_len == len && std::memcmp(k->assets[i].id.data(), id, len) == 0) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

bool valid_clip(const mk_kernel *k, const Clip &clip) {
    if (!k || clip.asset_index >= k->asset_count || !positive_time(clip.duration)) return false;
    mk_time_t end{};
    if (!add_time(clip.source_in, clip.duration, end)) return false;
    if (compare_time(clip.source_in, {0, 1}) < 0 || compare_time(end, k->assets[clip.asset_index].duration) > 0) {
        return false;
    }
    if (clip.transition.num != 0 &&
        (!positive_time(clip.transition) || compare_time(clip.transition, clip.duration) >= 0)) {
        return false;
    }
    return true;
}

bool valid_resource(const mk_kernel *k, mk_resource_handle_t handle) {
    if (!k || handle.slot >= MAX_RESOURCES) return false;
    const auto &slot = k->resources[handle.slot];
    return slot.active && slot.generation == handle.generation;
}

int find_node(const mk_kernel *k, uint32_t id) {
    for (size_t i = 0; i < k->node_count; ++i) {
        if (k->nodes[i].id == id) return static_cast<int>(i);
    }
    return -1;
}
}  // namespace

extern "C" {

mk_status_t mk_time_normalize(mk_time_t in, mk_time_t *out) {
    if (!out) return MK_INVALID;
    return normalize_time(in, *out) ? MK_OK : MK_INVALID;
}

mk_status_t mk_time_add(mk_time_t a, mk_time_t b, mk_time_t *out) {
    if (!out) return MK_INVALID;
    return add_time(a, b, *out) ? MK_OK : MK_OVERFLOW;
}

int mk_time_compare(mk_time_t a, mk_time_t b) {
    return compare_time(a, b);
}

mk_kernel_t *mk_kernel_create(void) {
    try {
        return new mk_kernel();
    } catch (...) {
        return nullptr;
    }
}

void mk_kernel_destroy(mk_kernel_t *kernel) {
    delete kernel;
}

uint64_t mk_kernel_revision(const mk_kernel_t *kernel) {
    return kernel ? kernel->revision : 0;
}

mk_status_t mk_kernel_add_asset(mk_kernel_t *kernel, const char *id, mk_time_t duration) {
    if (!kernel || !id || !*id || !positive_time(duration)) return MK_INVALID;
    if (find_asset(kernel, id) >= 0) return MK_CONFLICT;
    if (kernel->asset_count >= MAX_ASSETS) return MK_OVERFLOW;
    const size_t len = std::strlen(id);
    if (len >= MAX_ID) return MK_INVALID;
    mk_time_t normalized{};
    if (!normalize_time(duration, normalized)) return MK_INVALID;
    auto &asset = kernel->assets[kernel->asset_count++];
    std::memcpy(asset.id.data(), id, len);
    asset.id_len = len;
    asset.duration = normalized;
    return MK_OK;
}

mk_status_t mk_kernel_append_clip(
    mk_kernel_t *kernel,
    const char *asset_id,
    mk_time_t source_in,
    mk_time_t duration,
    mk_time_t transition_in) {
    if (!kernel || !asset_id || kernel->clip_count >= MAX_CLIPS) return MK_INVALID;
    const int asset_index = find_asset(kernel, asset_id);
    if (asset_index < 0) return MK_NOT_FOUND;
    mk_time_t source{}, dur{}, transition{};
    if (!normalize_time(source_in, source) || !normalize_time(duration, dur) ||
        !normalize_time(transition_in, transition)) {
        return MK_INVALID;
    }
    Clip clip{static_cast<size_t>(asset_index), source, dur, transition};
    if ((kernel->clip_count == 0 && transition.num != 0) || !valid_clip(kernel, clip)) return MK_INVALID;
    kernel->clips[kernel->clip_count++] = clip;
    return MK_OK;
}

mk_status_t mk_kernel_propose_trim(
    mk_kernel_t *kernel,
    uint64_t base_revision,
    size_t clip_index,
    mk_time_t new_duration,
    uint64_t *proposal_id) {
    if (!kernel || !proposal_id) return MK_INVALID;
    if (base_revision != kernel->revision) return MK_CONFLICT;
    if (clip_index >= kernel->clip_count || kernel->proposal_count >= MAX_PROPOSALS || !positive_time(new_duration)) {
        return MK_INVALID;
    }
    mk_time_t duration{};
    if (!normalize_time(new_duration, duration)) return MK_INVALID;
    Clip candidate = kernel->clips[clip_index];
    candidate.duration = duration;
    if (!valid_clip(kernel, candidate)) return MK_INVALID;
    const uint64_t id = kernel->next_proposal++;
    kernel->proposals[kernel->proposal_count++] = Proposal{id, base_revision, clip_index, duration};
    *proposal_id = id;
    return MK_OK;
}

mk_status_t mk_kernel_commit(mk_kernel_t *kernel, uint64_t proposal_id, uint64_t *new_revision) {
    if (!kernel || !new_revision) return MK_INVALID;
    size_t index = MAX_PROPOSALS;
    for (size_t i = 0; i < kernel->proposal_count; ++i) {
        if (kernel->proposals[i].id == proposal_id) {
            index = i;
            break;
        }
    }
    if (index == MAX_PROPOSALS) return MK_NOT_FOUND;
    const Proposal proposal = kernel->proposals[index];
    if (proposal.base_revision != kernel->revision) return MK_CONFLICT;
    Clip candidate = kernel->clips[proposal.clip_index];
    candidate.duration = proposal.new_duration;
    if (!valid_clip(kernel, candidate)) return MK_INVALID;
    kernel->clips[proposal.clip_index] = candidate;
    ++kernel->revision;
    kernel->proposal_count = 0;
    *new_revision = kernel->revision;
    return MK_OK;
}

uint64_t mk_kernel_state_hash(const mk_kernel_t *kernel) {
    if (!kernel) return 0;
    uint64_t h = FNV_OFFSET;
    h = hash_u64(h, kernel->revision);
    h = hash_u64(h, kernel->asset_count);
    for (size_t i = 0; i < kernel->asset_count; ++i) {
        const auto &asset = kernel->assets[i];
        h = hash_u64(h, asset.id_len);
        for (size_t j = 0; j < asset.id_len; ++j) h = hash_byte(h, static_cast<uint8_t>(asset.id[j]));
        h = hash_i64(h, asset.duration.num);
        h = hash_i64(h, asset.duration.den);
    }
    h = hash_u64(h, kernel->clip_count);
    for (size_t i = 0; i < kernel->clip_count; ++i) {
        const auto &clip = kernel->clips[i];
        h = hash_u64(h, clip.asset_index);
        h = hash_i64(h, clip.source_in.num);
        h = hash_i64(h, clip.source_in.den);
        h = hash_i64(h, clip.duration.num);
        h = hash_i64(h, clip.duration.den);
        h = hash_i64(h, clip.transition.num);
        h = hash_i64(h, clip.transition.den);
    }
    return h;
}

mk_status_t mk_resource_alloc(
    mk_kernel_t *kernel,
    uint64_t size_bytes,
    uint32_t domain,
    mk_resource_handle_t *out) {
    if (!kernel || !out || size_bytes == 0 || domain == 0) return MK_INVALID;
    for (uint32_t i = 0; i < MAX_RESOURCES; ++i) {
        auto &slot = kernel->resources[i];
        if (!slot.active) {
            if (slot.generation == 0) slot.generation = 1;
            slot.active = true;
            slot.refcount = 1;
            slot.size_bytes = size_bytes;
            slot.domain = domain;
            *out = {i, slot.generation};
            return MK_OK;
        }
    }
    return MK_OVERFLOW;
}

mk_status_t mk_resource_retain(mk_kernel_t *kernel, mk_resource_handle_t handle) {
    if (!valid_resource(kernel, handle)) return MK_STALE;
    auto &slot = kernel->resources[handle.slot];
    if (slot.refcount == UINT32_MAX) return MK_OVERFLOW;
    ++slot.refcount;
    return MK_OK;
}

mk_status_t mk_resource_release(mk_kernel_t *kernel, mk_resource_handle_t handle) {
    if (!valid_resource(kernel, handle)) return MK_STALE;
    auto &slot = kernel->resources[handle.slot];
    if (slot.refcount == 0) return MK_STALE;
    if (--slot.refcount == 0) {
        slot.active = false;
        slot.size_bytes = 0;
        slot.domain = 0;
        ++slot.generation;
        if (slot.generation == 0) slot.generation = 1;
    }
    return MK_OK;
}

mk_status_t mk_resource_touch(const mk_kernel_t *kernel, mk_resource_handle_t handle) {
    return valid_resource(kernel, handle) ? MK_OK : MK_STALE;
}

mk_status_t mk_resource_refcount(
    const mk_kernel_t *kernel,
    mk_resource_handle_t handle,
    uint32_t *out_refcount) {
    if (!out_refcount) return MK_INVALID;
    if (!valid_resource(kernel, handle)) return MK_STALE;
    *out_refcount = kernel->resources[handle.slot].refcount;
    return MK_OK;
}

uint64_t mk_resource_hash(const mk_kernel_t *kernel) {
    if (!kernel) return 0;
    uint64_t h = FNV_OFFSET;
    for (const auto &slot : kernel->resources) {
        h = hash_u32(h, slot.generation);
        h = hash_u32(h, slot.refcount);
        h = hash_u64(h, slot.size_bytes);
        h = hash_u32(h, slot.domain);
        h = hash_byte(h, slot.active ? 1 : 0);
    }
    return h;
}

mk_status_t mk_plan_reset(mk_kernel_t *kernel) {
    if (!kernel) return MK_INVALID;
    kernel->node_count = 0;
    return MK_OK;
}

mk_status_t mk_plan_add_node(
    mk_kernel_t *kernel,
    uint32_t id,
    uint32_t kind,
    const uint32_t *deps,
    size_t dep_count,
    mk_resource_handle_t resource) {
    if (!kernel || id == 0 || dep_count > MAX_DEPS || kernel->node_count >= MAX_NODES) return MK_INVALID;
    if (kind < MK_NODE_SOURCE || kind > MK_NODE_SINK) return MK_INVALID;
    if (dep_count > 0 && !deps) return MK_INVALID;
    if (find_node(kernel, id) >= 0) return MK_CONFLICT;
    auto &node = kernel->nodes[kernel->node_count++];
    node.id = id;
    node.kind = kind;
    node.dep_count = dep_count;
    node.resource = resource;
    for (size_t i = 0; i < dep_count; ++i) node.deps[i] = deps[i];
    return MK_OK;
}

mk_status_t mk_plan_validate(const mk_kernel_t *kernel) {
    if (!kernel || kernel->node_count == 0) return MK_INVALID;
    std::array<uint32_t, MAX_NODES> indegree{};
    std::array<bool, MAX_NODES> done{};
    for (size_t i = 0; i < kernel->node_count; ++i) {
        const auto &node = kernel->nodes[i];
        if (node.kind == MK_NODE_SOURCE && node.dep_count != 0) return MK_INVALID;
        if ((node.kind == MK_NODE_TRANSFORM || node.kind == MK_NODE_SINK) && node.dep_count == 0) return MK_INVALID;
        if (node.resource.slot != MK_NO_RESOURCE_SLOT && !valid_resource(kernel, node.resource)) return MK_STALE;
        indegree[i] = static_cast<uint32_t>(node.dep_count);
        for (size_t d = 0; d < node.dep_count; ++d) {
            if (find_node(kernel, node.deps[d]) < 0) return MK_INVALID;
        }
    }
    size_t processed = 0;
    for (;;) {
        int selected = -1;
        for (size_t i = 0; i < kernel->node_count; ++i) {
            if (!done[i] && indegree[i] == 0) {
                selected = static_cast<int>(i);
                break;
            }
        }
        if (selected < 0) break;
        done[selected] = true;
        ++processed;
        const uint32_t id = kernel->nodes[selected].id;
        for (size_t i = 0; i < kernel->node_count; ++i) {
            if (done[i]) continue;
            for (size_t d = 0; d < kernel->nodes[i].dep_count; ++d) {
                if (kernel->nodes[i].deps[d] == id && indegree[i] > 0) --indegree[i];
            }
        }
    }
    return processed == kernel->node_count ? MK_OK : MK_CYCLE;
}

uint64_t mk_plan_hash(const mk_kernel_t *kernel) {
    if (!kernel) return 0;
    uint64_t h = FNV_OFFSET;
    h = hash_u64(h, kernel->node_count);
    for (size_t i = 0; i < kernel->node_count; ++i) {
        const auto &node = kernel->nodes[i];
        h = hash_u32(h, node.id);
        h = hash_u32(h, node.kind);
        h = hash_u64(h, node.dep_count);
        for (size_t d = 0; d < node.dep_count; ++d) h = hash_u32(h, node.deps[d]);
        h = hash_u32(h, node.resource.slot);
        h = hash_u32(h, node.resource.generation);
    }
    return h;
}

uint32_t mk_ffmpeg_version(void) {
    return avformat_version();
}

uint64_t mk_benchmark(uint64_t iterations) {
    mk_time_t x{1001, 30000}, y{1, 48000}, z{};
    uint64_t sum = 0;
    for (uint64_t i = 0; i < iterations; ++i) {
        if (!add_time(x, y, z)) break;
        sum ^= static_cast<uint64_t>(z.num) + static_cast<uint64_t>(z.den) + i;
        x = (i & 1) ? mk_time_t{1001, 30000} : mk_time_t{1, 24};
    }
    return sum;
}

}  // extern "C"
