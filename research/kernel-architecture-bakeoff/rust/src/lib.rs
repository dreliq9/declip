use std::ffi::CStr;
use std::os::raw::{c_char, c_int};

const MK_OK: c_int = 0;
const MK_INVALID: c_int = 1;
const MK_NOT_FOUND: c_int = 2;
const MK_CONFLICT: c_int = 3;
const MK_OVERFLOW: c_int = 5;
const MK_STALE: c_int = 6;
const MK_CYCLE: c_int = 7;

const MK_NODE_SOURCE: u32 = 1;
const MK_NODE_TRANSFORM: u32 = 2;
const MK_NODE_SINK: u32 = 3;
const MK_NO_RESOURCE_SLOT: u32 = u32::MAX;

const MAX_ASSETS: usize = 32;
const MAX_CLIPS: usize = 64;
const MAX_PROPOSALS: usize = 64;
const MAX_RESOURCES: usize = 128;
const MAX_NODES: usize = 64;
const MAX_DEPS: usize = 4;
const MAX_ID: usize = 128;
const FNV_OFFSET: u64 = 14_695_981_039_346_656_037;
const FNV_PRIME: u64 = 1_099_511_628_211;

#[repr(C)]
#[derive(Copy, Clone, Default, Eq, PartialEq)]
pub struct Time {
    pub num: i64,
    pub den: i64,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Eq, PartialEq)]
pub struct ResourceHandle {
    pub slot: u32,
    pub generation: u32,
}

impl ResourceHandle {
    const NONE: Self = Self {
        slot: MK_NO_RESOURCE_SLOT,
        generation: 0,
    };
}

#[derive(Copy, Clone)]
struct Asset {
    id: [u8; MAX_ID],
    id_len: usize,
    duration: Time,
}

impl Default for Asset {
    fn default() -> Self {
        Self {
            id: [0; MAX_ID],
            id_len: 0,
            duration: Time::default(),
        }
    }
}

#[derive(Copy, Clone, Default)]
struct Clip {
    asset_index: usize,
    source_in: Time,
    duration: Time,
    transition: Time,
}

#[derive(Copy, Clone, Default)]
struct Proposal {
    id: u64,
    base_revision: u64,
    clip_index: usize,
    new_duration: Time,
}

#[derive(Copy, Clone, Default)]
struct ResourceSlot {
    generation: u32,
    refcount: u32,
    size_bytes: u64,
    domain: u32,
    active: bool,
}

#[derive(Copy, Clone)]
struct PlanNode {
    id: u32,
    kind: u32,
    deps: [u32; MAX_DEPS],
    dep_count: usize,
    resource: ResourceHandle,
}

impl Default for PlanNode {
    fn default() -> Self {
        Self {
            id: 0,
            kind: 0,
            deps: [0; MAX_DEPS],
            dep_count: 0,
            resource: ResourceHandle::NONE,
        }
    }
}

pub struct Kernel {
    revision: u64,
    next_proposal: u64,
    assets: [Asset; MAX_ASSETS],
    asset_count: usize,
    clips: [Clip; MAX_CLIPS],
    clip_count: usize,
    proposals: [Proposal; MAX_PROPOSALS],
    proposal_count: usize,
    resources: [ResourceSlot; MAX_RESOURCES],
    nodes: [PlanNode; MAX_NODES],
    node_count: usize,
}

impl Default for Kernel {
    fn default() -> Self {
        Self {
            revision: 0,
            next_proposal: 1,
            assets: [Asset::default(); MAX_ASSETS],
            asset_count: 0,
            clips: [Clip::default(); MAX_CLIPS],
            clip_count: 0,
            proposals: [Proposal::default(); MAX_PROPOSALS],
            proposal_count: 0,
            resources: [ResourceSlot::default(); MAX_RESOURCES],
            nodes: [PlanNode::default(); MAX_NODES],
            node_count: 0,
        }
    }
}

fn normalize_time(input: Time) -> Option<Time> {
    if input.den == 0 {
        return None;
    }
    if input.num == 0 {
        return Some(Time { num: 0, den: 1 });
    }
    let mut n = input.num as i128;
    let mut d = input.den as i128;
    if d < 0 {
        n = -n;
        d = -d;
    }
    if n < i64::MIN as i128 || n > i64::MAX as i128 || d <= 0 || d > i64::MAX as i128 {
        return None;
    }
    let mut a = if n < 0 { (-n) as u128 } else { n as u128 };
    let mut b = d as u128;
    while b != 0 {
        let r = a % b;
        a = b;
        b = r;
    }
    Some(Time {
        num: (n / a as i128) as i64,
        den: (d / a as i128) as i64,
    })
}

fn add_time(a: Time, b: Time) -> Option<Time> {
    let na = normalize_time(a)?;
    let nb = normalize_time(b)?;
    let n = na.num as i128 * nb.den as i128 + nb.num as i128 * na.den as i128;
    let d = na.den as i128 * nb.den as i128;
    if n < i64::MIN as i128 || n > i64::MAX as i128 || d <= 0 || d > i64::MAX as i128 {
        return None;
    }
    normalize_time(Time {
        num: n as i64,
        den: d as i64,
    })
}

fn compare_time(a: Time, b: Time) -> i32 {
    let Some(na) = normalize_time(a) else {
        return 0;
    };
    let Some(nb) = normalize_time(b) else {
        return 0;
    };
    let left = na.num as i128 * nb.den as i128;
    let right = nb.num as i128 * na.den as i128;
    left.cmp(&right) as i32
}

fn positive_time(t: Time) -> bool {
    normalize_time(t).is_some_and(|n| n.num > 0)
}

fn hash_byte(h: u64, b: u8) -> u64 {
    (h ^ b as u64).wrapping_mul(FNV_PRIME)
}

fn hash_u32(mut h: u64, v: u32) -> u64 {
    for i in 0..4 {
        h = hash_byte(h, (v >> (i * 8)) as u8);
    }
    h
}

fn hash_u64(mut h: u64, v: u64) -> u64 {
    for i in 0..8 {
        h = hash_byte(h, (v >> (i * 8)) as u8);
    }
    h
}

fn hash_i64(h: u64, v: i64) -> u64 {
    hash_u64(h, v as u64)
}

impl Kernel {
    fn find_asset(&self, id: &[u8]) -> Option<usize> {
        (0..self.asset_count).find(|&i| {
            self.assets[i].id_len == id.len() && self.assets[i].id[..id.len()] == *id
        })
    }

    fn valid_clip(&self, clip: &Clip) -> bool {
        if clip.asset_index >= self.asset_count || !positive_time(clip.duration) {
            return false;
        }
        let Some(end) = add_time(clip.source_in, clip.duration) else {
            return false;
        };
        if compare_time(clip.source_in, Time { num: 0, den: 1 }) < 0
            || compare_time(end, self.assets[clip.asset_index].duration) > 0
        {
            return false;
        }
        clip.transition.num == 0
            || (positive_time(clip.transition) && compare_time(clip.transition, clip.duration) < 0)
    }

    fn valid_resource(&self, handle: ResourceHandle) -> bool {
        let Some(slot) = self.resources.get(handle.slot as usize) else {
            return false;
        };
        slot.active && slot.generation == handle.generation
    }

    fn find_node(&self, id: u32) -> Option<usize> {
        (0..self.node_count).find(|&i| self.nodes[i].id == id)
    }

    fn state_hash(&self) -> u64 {
        let mut h = hash_u64(FNV_OFFSET, self.revision);
        h = hash_u64(h, self.asset_count as u64);
        for asset in &self.assets[..self.asset_count] {
            h = hash_u64(h, asset.id_len as u64);
            for &b in &asset.id[..asset.id_len] {
                h = hash_byte(h, b);
            }
            h = hash_i64(h, asset.duration.num);
            h = hash_i64(h, asset.duration.den);
        }
        h = hash_u64(h, self.clip_count as u64);
        for clip in &self.clips[..self.clip_count] {
            h = hash_u64(h, clip.asset_index as u64);
            h = hash_i64(h, clip.source_in.num);
            h = hash_i64(h, clip.source_in.den);
            h = hash_i64(h, clip.duration.num);
            h = hash_i64(h, clip.duration.den);
            h = hash_i64(h, clip.transition.num);
            h = hash_i64(h, clip.transition.den);
        }
        h
    }

    fn resource_hash(&self) -> u64 {
        let mut h = FNV_OFFSET;
        for slot in &self.resources {
            h = hash_u32(h, slot.generation);
            h = hash_u32(h, slot.refcount);
            h = hash_u64(h, slot.size_bytes);
            h = hash_u32(h, slot.domain);
            h = hash_byte(h, u8::from(slot.active));
        }
        h
    }

    fn plan_hash(&self) -> u64 {
        let mut h = hash_u64(FNV_OFFSET, self.node_count as u64);
        for node in &self.nodes[..self.node_count] {
            h = hash_u32(h, node.id);
            h = hash_u32(h, node.kind);
            h = hash_u64(h, node.dep_count as u64);
            for &dep in &node.deps[..node.dep_count] {
                h = hash_u32(h, dep);
            }
            h = hash_u32(h, node.resource.slot);
            h = hash_u32(h, node.resource.generation);
        }
        h
    }

    fn validate_plan(&self) -> c_int {
        if self.node_count == 0 {
            return MK_INVALID;
        }
        let mut indegree = [0u32; MAX_NODES];
        let mut done = [false; MAX_NODES];
        for (i, node) in self.nodes[..self.node_count].iter().enumerate() {
            if node.kind == MK_NODE_SOURCE && node.dep_count != 0 {
                return MK_INVALID;
            }
            if (node.kind == MK_NODE_TRANSFORM || node.kind == MK_NODE_SINK) && node.dep_count == 0 {
                return MK_INVALID;
            }
            if node.resource.slot != MK_NO_RESOURCE_SLOT && !self.valid_resource(node.resource) {
                return MK_STALE;
            }
            indegree[i] = node.dep_count as u32;
            if node.deps[..node.dep_count]
                .iter()
                .any(|dep| self.find_node(*dep).is_none())
            {
                return MK_INVALID;
            }
        }
        let mut processed = 0usize;
        loop {
            let selected = (0..self.node_count).find(|&i| !done[i] && indegree[i] == 0);
            let Some(selected) = selected else {
                break;
            };
            done[selected] = true;
            processed += 1;
            let id = self.nodes[selected].id;
            for i in 0..self.node_count {
                if done[i] {
                    continue;
                }
                for dep in &self.nodes[i].deps[..self.nodes[i].dep_count] {
                    if *dep == id && indegree[i] > 0 {
                        indegree[i] -= 1;
                    }
                }
            }
        }
        if processed == self.node_count {
            MK_OK
        } else {
            MK_CYCLE
        }
    }
}

unsafe extern "C" {
    fn avformat_version() -> u32;
}

unsafe fn kernel_ref<'a>(ptr: *const Kernel) -> Option<&'a Kernel> {
    unsafe { ptr.as_ref() }
}

unsafe fn kernel_mut<'a>(ptr: *mut Kernel) -> Option<&'a mut Kernel> {
    unsafe { ptr.as_mut() }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_time_normalize(input: Time, out: *mut Time) -> c_int {
    let Some(out) = (unsafe { out.as_mut() }) else {
        return MK_INVALID;
    };
    let Some(n) = normalize_time(input) else {
        return MK_INVALID;
    };
    *out = n;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_time_add(a: Time, b: Time, out: *mut Time) -> c_int {
    let Some(out) = (unsafe { out.as_mut() }) else {
        return MK_INVALID;
    };
    let Some(sum) = add_time(a, b) else {
        return MK_OVERFLOW;
    };
    *out = sum;
    MK_OK
}

#[unsafe(no_mangle)]
pub extern "C" fn mk_time_compare(a: Time, b: Time) -> c_int {
    compare_time(a, b)
}

#[unsafe(no_mangle)]
pub extern "C" fn mk_kernel_create() -> *mut Kernel {
    Box::into_raw(Box::new(Kernel::default()))
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_kernel_destroy(kernel: *mut Kernel) {
    if !kernel.is_null() {
        unsafe { drop(Box::from_raw(kernel)) };
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_kernel_revision(kernel: *const Kernel) -> u64 {
    unsafe { kernel_ref(kernel) }.map_or(0, |k| k.revision)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_kernel_add_asset(
    kernel: *mut Kernel,
    id: *const c_char,
    duration: Time,
) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_INVALID;
    };
    if id.is_null() || !positive_time(duration) {
        return MK_INVALID;
    }
    let bytes = unsafe { CStr::from_ptr(id) }.to_bytes();
    if bytes.is_empty() || bytes.len() >= MAX_ID {
        return MK_INVALID;
    }
    if k.find_asset(bytes).is_some() {
        return MK_CONFLICT;
    }
    if k.asset_count >= MAX_ASSETS {
        return MK_OVERFLOW;
    }
    let Some(duration) = normalize_time(duration) else {
        return MK_INVALID;
    };
    let asset = &mut k.assets[k.asset_count];
    asset.id[..bytes.len()].copy_from_slice(bytes);
    asset.id_len = bytes.len();
    asset.duration = duration;
    k.asset_count += 1;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_kernel_append_clip(
    kernel: *mut Kernel,
    asset_id: *const c_char,
    source_in: Time,
    duration: Time,
    transition_in: Time,
) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_INVALID;
    };
    if asset_id.is_null() || k.clip_count >= MAX_CLIPS {
        return MK_INVALID;
    }
    let bytes = unsafe { CStr::from_ptr(asset_id) }.to_bytes();
    let Some(asset_index) = k.find_asset(bytes) else {
        return MK_NOT_FOUND;
    };
    let (Some(source), Some(duration), Some(transition)) = (
        normalize_time(source_in),
        normalize_time(duration),
        normalize_time(transition_in),
    ) else {
        return MK_INVALID;
    };
    let clip = Clip {
        asset_index,
        source_in: source,
        duration,
        transition,
    };
    if (k.clip_count == 0 && transition.num != 0) || !k.valid_clip(&clip) {
        return MK_INVALID;
    }
    k.clips[k.clip_count] = clip;
    k.clip_count += 1;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_kernel_propose_trim(
    kernel: *mut Kernel,
    base_revision: u64,
    clip_index: usize,
    new_duration: Time,
    proposal_id: *mut u64,
) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_INVALID;
    };
    let Some(out) = (unsafe { proposal_id.as_mut() }) else {
        return MK_INVALID;
    };
    if base_revision != k.revision {
        return MK_CONFLICT;
    }
    if clip_index >= k.clip_count || k.proposal_count >= MAX_PROPOSALS || !positive_time(new_duration) {
        return MK_INVALID;
    }
    let Some(duration) = normalize_time(new_duration) else {
        return MK_INVALID;
    };
    let mut candidate = k.clips[clip_index];
    candidate.duration = duration;
    if !k.valid_clip(&candidate) {
        return MK_INVALID;
    }
    let id = k.next_proposal;
    k.next_proposal += 1;
    k.proposals[k.proposal_count] = Proposal {
        id,
        base_revision,
        clip_index,
        new_duration: duration,
    };
    k.proposal_count += 1;
    *out = id;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_kernel_commit(
    kernel: *mut Kernel,
    proposal_id: u64,
    new_revision: *mut u64,
) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_INVALID;
    };
    let Some(out) = (unsafe { new_revision.as_mut() }) else {
        return MK_INVALID;
    };
    let Some(index) = (0..k.proposal_count).find(|&i| k.proposals[i].id == proposal_id) else {
        return MK_NOT_FOUND;
    };
    let proposal = k.proposals[index];
    if proposal.base_revision != k.revision {
        return MK_CONFLICT;
    }
    let mut candidate = k.clips[proposal.clip_index];
    candidate.duration = proposal.new_duration;
    if !k.valid_clip(&candidate) {
        return MK_INVALID;
    }
    k.clips[proposal.clip_index] = candidate;
    k.revision += 1;
    k.proposal_count = 0;
    *out = k.revision;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_kernel_state_hash(kernel: *const Kernel) -> u64 {
    unsafe { kernel_ref(kernel) }.map_or(0, Kernel::state_hash)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_resource_alloc(
    kernel: *mut Kernel,
    size_bytes: u64,
    domain: u32,
    out: *mut ResourceHandle,
) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_INVALID;
    };
    let Some(out) = (unsafe { out.as_mut() }) else {
        return MK_INVALID;
    };
    if size_bytes == 0 || domain == 0 {
        return MK_INVALID;
    }
    let Some(index) = (0..MAX_RESOURCES).find(|&i| !k.resources[i].active) else {
        return MK_OVERFLOW;
    };
    let slot = &mut k.resources[index];
    if slot.generation == 0 {
        slot.generation = 1;
    }
    slot.active = true;
    slot.refcount = 1;
    slot.size_bytes = size_bytes;
    slot.domain = domain;
    *out = ResourceHandle {
        slot: index as u32,
        generation: slot.generation,
    };
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_resource_retain(kernel: *mut Kernel, handle: ResourceHandle) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_STALE;
    };
    if !k.valid_resource(handle) {
        return MK_STALE;
    }
    let slot = &mut k.resources[handle.slot as usize];
    if slot.refcount == u32::MAX {
        return MK_OVERFLOW;
    }
    slot.refcount += 1;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_resource_release(kernel: *mut Kernel, handle: ResourceHandle) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_STALE;
    };
    if !k.valid_resource(handle) {
        return MK_STALE;
    }
    let slot = &mut k.resources[handle.slot as usize];
    if slot.refcount == 0 {
        return MK_STALE;
    }
    slot.refcount -= 1;
    if slot.refcount == 0 {
        slot.active = false;
        slot.size_bytes = 0;
        slot.domain = 0;
        slot.generation = slot.generation.wrapping_add(1);
        if slot.generation == 0 {
            slot.generation = 1;
        }
    }
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_resource_touch(kernel: *const Kernel, handle: ResourceHandle) -> c_int {
    let Some(k) = (unsafe { kernel_ref(kernel) }) else {
        return MK_STALE;
    };
    if k.valid_resource(handle) {
        MK_OK
    } else {
        MK_STALE
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_resource_refcount(
    kernel: *const Kernel,
    handle: ResourceHandle,
    out_refcount: *mut u32,
) -> c_int {
    let Some(k) = (unsafe { kernel_ref(kernel) }) else {
        return MK_STALE;
    };
    let Some(out) = (unsafe { out_refcount.as_mut() }) else {
        return MK_INVALID;
    };
    if !k.valid_resource(handle) {
        return MK_STALE;
    }
    *out = k.resources[handle.slot as usize].refcount;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_resource_hash(kernel: *const Kernel) -> u64 {
    unsafe { kernel_ref(kernel) }.map_or(0, Kernel::resource_hash)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_plan_reset(kernel: *mut Kernel) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_INVALID;
    };
    k.node_count = 0;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_plan_add_node(
    kernel: *mut Kernel,
    id: u32,
    kind: u32,
    deps: *const u32,
    dep_count: usize,
    resource: ResourceHandle,
) -> c_int {
    let Some(k) = (unsafe { kernel_mut(kernel) }) else {
        return MK_INVALID;
    };
    if id == 0 || dep_count > MAX_DEPS || k.node_count >= MAX_NODES {
        return MK_INVALID;
    }
    if !(MK_NODE_SOURCE..=MK_NODE_SINK).contains(&kind) {
        return MK_INVALID;
    }
    if dep_count > 0 && deps.is_null() {
        return MK_INVALID;
    }
    if k.find_node(id).is_some() {
        return MK_CONFLICT;
    }
    let mut node = PlanNode {
        id,
        kind,
        dep_count,
        resource,
        ..PlanNode::default()
    };
    if dep_count > 0 {
        let slice = unsafe { std::slice::from_raw_parts(deps, dep_count) };
        node.deps[..dep_count].copy_from_slice(slice);
    }
    k.nodes[k.node_count] = node;
    k.node_count += 1;
    MK_OK
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_plan_validate(kernel: *const Kernel) -> c_int {
    let Some(k) = (unsafe { kernel_ref(kernel) }) else {
        return MK_INVALID;
    };
    k.validate_plan()
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_plan_hash(kernel: *const Kernel) -> u64 {
    unsafe { kernel_ref(kernel) }.map_or(0, Kernel::plan_hash)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn mk_ffmpeg_version() -> u32 {
    unsafe { avformat_version() }
}

#[unsafe(no_mangle)]
pub extern "C" fn mk_benchmark(iterations: u64) -> u64 {
    let mut x = Time { num: 1001, den: 30000 };
    let y = Time { num: 1, den: 48000 };
    let mut sum = 0u64;
    for i in 0..iterations {
        let Some(z) = add_time(x, y) else {
            break;
        };
        sum ^= (z.num as u64).wrapping_add(z.den as u64).wrapping_add(i);
        x = if i & 1 == 1 {
            Time { num: 1001, den: 30000 }
        } else {
            Time { num: 1, den: 24 }
        };
    }
    sum
}
