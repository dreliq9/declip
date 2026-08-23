use std::collections::HashMap;
use std::ffi::CStr;
use std::os::raw::{c_char, c_int};

const MK_OK: c_int = 0;
const MK_INVALID: c_int = 1;
const MK_NOT_FOUND: c_int = 2;
const MK_CONFLICT: c_int = 3;
const MK_BUFFER_TOO_SMALL: c_int = 4;
const MK_OVERFLOW: c_int = 5;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct MkTime {
    pub num: i64,
    pub den: i64,
}

#[derive(Clone)]
struct Clip {
    asset: String,
    source_in: MkTime,
    duration: MkTime,
    transition: MkTime,
}

#[derive(Clone, Copy)]
struct Proposal {
    base_revision: u64,
    clip_index: usize,
    new_duration: MkTime,
}

pub struct Project {
    revision: u64,
    next_proposal: u64,
    assets: HashMap<String, MkTime>,
    clips: Vec<Clip>,
    proposals: HashMap<u64, Proposal>,
}

impl Project {
    fn new() -> Self {
        Self {
            revision: 0,
            next_proposal: 1,
            assets: HashMap::new(),
            clips: Vec::new(),
            proposals: HashMap::new(),
        }
    }
}

fn gcd(mut a: u64, mut b: u64) -> u64 {
    while b != 0 {
        let r = a % b;
        a = b;
        b = r;
    }
    a
}

fn normalize(mut t: MkTime) -> Option<MkTime> {
    if t.den == 0 {
        return None;
    }
    if t.num == 0 {
        return Some(MkTime { num: 0, den: 1 });
    }
    if t.den < 0 {
        if t.den == i64::MIN || t.num == i64::MIN {
            return None;
        }
        t.den = -t.den;
        t.num = -t.num;
    }
    let g = gcd(t.num.unsigned_abs(), t.den as u64) as i64;
    Some(MkTime { num: t.num / g, den: t.den / g })
}

fn add(a: MkTime, b: MkTime) -> Option<MkTime> {
    let a = normalize(a)?;
    let b = normalize(b)?;
    let n = (a.num as i128) * (b.den as i128) + (b.num as i128) * (a.den as i128);
    let d = (a.den as i128) * (b.den as i128);
    if n > i64::MAX as i128 || n < i64::MIN as i128 || d > i64::MAX as i128 {
        return None;
    }
    normalize(MkTime { num: n as i64, den: d as i64 })
}

fn compare(a: MkTime, b: MkTime) -> Option<c_int> {
    let a = normalize(a)?;
    let b = normalize(b)?;
    let l = (a.num as i128) * (b.den as i128);
    let r = (b.num as i128) * (a.den as i128);
    Some(if l > r { 1 } else if l < r { -1 } else { 0 })
}

fn positive(t: MkTime) -> bool {
    normalize(t).is_some_and(|v| v.num > 0)
}

fn valid_clip(project: &Project, clip: &Clip) -> bool {
    let Some(asset_duration) = project.assets.get(&clip.asset).copied() else { return false; };
    if !positive(clip.duration) { return false; }
    let Some(end) = add(clip.source_in, clip.duration) else { return false; };
    if compare(clip.source_in, MkTime { num: 0, den: 1 }).unwrap_or(0) < 0 { return false; }
    if compare(end, asset_duration).unwrap_or(0) > 0 { return false; }
    if clip.transition.num != 0
        && (!positive(clip.transition) || compare(clip.transition, clip.duration).unwrap_or(0) >= 0)
    {
        return false;
    }
    true
}

unsafe fn string_from_c(ptr: *const c_char) -> Option<String> {
    if ptr.is_null() {
        return None;
    }
    let s = unsafe { CStr::from_ptr(ptr) }.to_str().ok()?;
    if s.is_empty() { None } else { Some(s.to_owned()) }
}

fn rat(t: MkTime) -> String {
    let n = normalize(t).unwrap_or(MkTime { num: 0, den: 1 });
    format!("{}/{}", n.num, n.den)
}

#[no_mangle]
pub extern "C" fn mk_time_normalize(input: MkTime, out: *mut MkTime) -> c_int {
    if out.is_null() { return MK_INVALID; }
    match normalize(input) {
        Some(v) => { unsafe { *out = v; } MK_OK }
        None => MK_INVALID,
    }
}

#[no_mangle]
pub extern "C" fn mk_time_add(a: MkTime, b: MkTime, out: *mut MkTime) -> c_int {
    if out.is_null() { return MK_INVALID; }
    match add(a, b) {
        Some(v) => { unsafe { *out = v; } MK_OK }
        None => MK_OVERFLOW,
    }
}

#[no_mangle]
pub extern "C" fn mk_time_compare(a: MkTime, b: MkTime) -> c_int {
    compare(a, b).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn mk_project_create() -> *mut Project {
    Box::into_raw(Box::new(Project::new()))
}

#[no_mangle]
pub extern "C" fn mk_project_destroy(project: *mut Project) {
    if !project.is_null() {
        unsafe { drop(Box::from_raw(project)); }
    }
}

#[no_mangle]
pub extern "C" fn mk_project_revision(project: *const Project) -> u64 {
    if project.is_null() { 0 } else { unsafe { (*project).revision } }
}

#[no_mangle]
pub extern "C" fn mk_project_add_asset(project: *mut Project, id: *const c_char, duration: MkTime) -> c_int {
    if project.is_null() || !positive(duration) { return MK_INVALID; }
    let Some(id) = (unsafe { string_from_c(id) }) else { return MK_INVALID; };
    let duration = normalize(duration).unwrap();
    let project = unsafe { &mut *project };
    if project.assets.contains_key(&id) { return MK_CONFLICT; }
    project.assets.insert(id, duration);
    MK_OK
}

#[no_mangle]
pub extern "C" fn mk_project_append_clip(project: *mut Project, asset: *const c_char, source_in: MkTime, duration: MkTime, transition: MkTime) -> c_int {
    if project.is_null() { return MK_INVALID; }
    let Some(asset) = (unsafe { string_from_c(asset) }) else { return MK_INVALID; };
    let (Some(source_in), Some(duration), Some(transition)) = (normalize(source_in), normalize(duration), normalize(transition)) else { return MK_INVALID; };
    let project = unsafe { &mut *project };
    let clip = Clip { asset, source_in, duration, transition };
    if !valid_clip(project, &clip) || (project.clips.is_empty() && clip.transition.num != 0) { return MK_INVALID; }
    project.clips.push(clip);
    MK_OK
}

#[no_mangle]
pub extern "C" fn mk_project_propose_trim(project: *mut Project, base_revision: u64, clip_index: usize, new_duration: MkTime, proposal_id: *mut u64) -> c_int {
    if project.is_null() || proposal_id.is_null() { return MK_INVALID; }
    let project = unsafe { &mut *project };
    if base_revision != project.revision { return MK_CONFLICT; }
    if clip_index >= project.clips.len() || !positive(new_duration) { return MK_INVALID; }
    let new_duration = normalize(new_duration).unwrap();
    let mut candidate = project.clips[clip_index].clone();
    candidate.duration = new_duration;
    if !valid_clip(project, &candidate) { return MK_INVALID; }
    let id = project.next_proposal;
    project.next_proposal += 1;
    project.proposals.insert(id, Proposal { base_revision, clip_index, new_duration });
    unsafe { *proposal_id = id; }
    MK_OK
}

#[no_mangle]
pub extern "C" fn mk_project_commit(project: *mut Project, proposal_id: u64, new_revision: *mut u64) -> c_int {
    if project.is_null() || new_revision.is_null() { return MK_INVALID; }
    let project = unsafe { &mut *project };
    let Some(proposal) = project.proposals.get(&proposal_id).copied() else { return MK_NOT_FOUND; };
    if proposal.base_revision != project.revision { return MK_CONFLICT; }
    let mut candidate = project.clips[proposal.clip_index].clone();
    candidate.duration = proposal.new_duration;
    if !valid_clip(project, &candidate) { return MK_INVALID; }
    project.clips[proposal.clip_index] = candidate;
    project.revision += 1;
    project.proposals.clear();
    unsafe { *new_revision = project.revision; }
    MK_OK
}

#[no_mangle]
pub extern "C" fn mk_project_lower_ffmpeg(project: *const Project, buffer: *mut c_char, capacity: usize, needed: *mut usize) -> c_int {
    if project.is_null() || needed.is_null() { return MK_INVALID; }
    let project = unsafe { &*project };
    let mut text = String::from("ffmpeg");
    for clip in &project.clips { text.push_str(" -i "); text.push_str(&clip.asset); }
    text.push_str(" -filter_complex \"");
    for (i, clip) in project.clips.iter().enumerate() {
        if i > 0 { text.push(';'); }
        text.push_str(&format!("[{}:v]trim=start={}:duration={}[v{}]", i, rat(clip.source_in), rat(clip.duration), i));
    }
    for i in 1..project.clips.len() {
        let clip = &project.clips[i];
        if clip.transition.num != 0 {
            text.push_str(&format!(";[v{}][v{}]xfade=duration={}[x{}]", i - 1, i, rat(clip.transition), i));
        }
    }
    text.push_str("\" out.mp4");
    let bytes = text.as_bytes();
    let total = bytes.len() + 1;
    unsafe { *needed = total; }
    if buffer.is_null() || capacity < total { return MK_BUFFER_TOO_SMALL; }
    unsafe {
        std::ptr::copy_nonoverlapping(bytes.as_ptr(), buffer.cast::<u8>(), bytes.len());
        *buffer.add(bytes.len()) = 0;
    }
    MK_OK
}

#[no_mangle]
pub extern "C" fn mk_benchmark(iterations: u64) -> u64 {
    let mut x = MkTime { num: 1001, den: 30000 };
    let y = MkTime { num: 1, den: 48000 };
    let mut sum = 0u64;
    for i in 0..iterations {
        let Some(z) = add(x, y) else { break; };
        sum ^= (z.num as u64).wrapping_add(z.den as u64).wrapping_add(i);
        x = if i & 1 == 1 { MkTime { num: 1001, den: 30000 } } else { MkTime { num: 1, den: 24 } };
    }
    sum
}
