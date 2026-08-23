const std = @import("std");
const c = @cImport({
    @cInclude("pthread.h");
    @cInclude("unistd.h");
    @cInclude("sched.h");
});

const RESOURCE_COUNT = 64;
const TASK_CAP = 8192;
const QUEUE_MAX = 128;
const MAX_THREADS = 32;

const Handle = struct { slot: u32 = 0, generation: u32 = 0 };
const Resource = struct { generation: u32 = 1, refs: u32 = 0, alive: bool = false };
const TaskState = enum(u8) { empty, queued, running, pending_fence, completed, cancelled, lost };
const Task = struct {
    id: u32 = 0,
    handle: Handle = .{},
    state: TaskState = .empty,
    cancel: bool = false,
    due_tick: u64 = 0,
};
const Result = struct {
    submitted: u64 = 0,
    completed: u64 = 0,
    cancelled: u64 = 0,
    lost: u64 = 0,
    backpressure_waits: u64 = 0,
    stale_accepts: u64 = 0,
    violations: u64 = 0,
    retain_ops: u64 = 0,
    release_ops: u64 = 0,
    device_loss_events: u64 = 0,
    max_queue: u32 = 0,
    leaked_resources: u32 = 0,
};
const Kernel = struct {
    mutex: c.pthread_mutex_t = undefined,
    cv_work: c.pthread_cond_t = undefined,
    cv_space: c.pthread_cond_t = undefined,
    cv_state: c.pthread_cond_t = undefined,
    resources: [RESOURCE_COUNT]Resource = [_]Resource{.{}} ** RESOURCE_COUNT,
    tasks: [TASK_CAP]Task = [_]Task{.{}} ** TASK_CAP,
    queue: [QUEUE_MAX]u32 = [_]u32{0} ** QUEUE_MAX,
    queue_head: usize = 0,
    queue_count: usize = 0,
    queue_cap: usize = 16,
    next_task: u32 = 0,
    tick: u64 = 0,
    producers_done: bool = false,
    shutdown: bool = false,
    device_lost: bool = false,
    started: u64 = 0,
    terminal: u64 = 0,
    result: Result = .{},
};
const ProducerArgs = struct {
    k: *Kernel,
    handles: *[RESOURCE_COUNT]Handle,
    producer_id: u32,
    seed: u64,
    ops: u32,
    inject_loss: bool,
};

fn lock(k: *Kernel) void { _ = c.pthread_mutex_lock(&k.mutex); }
fn unlock(k: *Kernel) void { _ = c.pthread_mutex_unlock(&k.mutex); }
fn broadcast(cond: *c.pthread_cond_t) void { _ = c.pthread_cond_broadcast(cond); }
fn signal(cond: *c.pthread_cond_t) void { _ = c.pthread_cond_signal(cond); }

fn validLocked(k: *const Kernel, h: Handle) bool {
    if (h.slot >= RESOURCE_COUNT) return false;
    const r = k.resources[h.slot];
    return r.alive and r.generation == h.generation;
}
fn retainLocked(k: *Kernel, h: Handle) bool {
    if (!validLocked(k, h)) return false;
    k.resources[h.slot].refs += 1;
    k.result.retain_ops += 1;
    return true;
}
fn releaseLocked(k: *Kernel, h: Handle) bool {
    if (!validLocked(k, h)) return false;
    var r = &k.resources[h.slot];
    if (r.refs == 0) { k.result.violations += 1; return false; }
    r.refs -= 1;
    k.result.release_ops += 1;
    if (r.refs == 0) {
        r.alive = false;
        r.generation +%= 1;
        if (r.generation == 0) r.generation = 1;
    }
    return true;
}
fn queuePushLocked(k: *Kernel, id: u32) bool {
    if (k.queue_count >= k.queue_cap or k.queue_count >= QUEUE_MAX) return false;
    const index = (k.queue_head + k.queue_count) % QUEUE_MAX;
    k.queue[index] = id;
    k.queue_count += 1;
    if (k.queue_count > k.result.max_queue) k.result.max_queue = @intCast(k.queue_count);
    return true;
}
fn queuePopLocked(k: *Kernel) ?u32 {
    if (k.queue_count == 0) return null;
    const id = k.queue[k.queue_head];
    k.queue_head = (k.queue_head + 1) % QUEUE_MAX;
    k.queue_count -= 1;
    return id;
}
fn allocateBaseResources(k: *Kernel, handles: *[RESOURCE_COUNT]Handle) void {
    lock(k); defer unlock(k);
    for (0..RESOURCE_COUNT) |i| {
        var r = &k.resources[i];
        if (r.generation == 0) r.generation = 1;
        r.refs = 1; r.alive = true;
        handles[i] = .{ .slot = @intCast(i), .generation = r.generation };
    }
}
fn submit(k: *Kernel, h: Handle, producer_id: u32, op_index: u32) bool {
    lock(k); defer unlock(k);
    while (k.queue_count >= k.queue_cap and !k.device_lost and !k.shutdown) {
        k.result.backpressure_waits += 1;
        _ = c.pthread_cond_wait(&k.cv_space, &k.mutex);
    }
    if (k.device_lost or k.shutdown) return false;
    if (!retainLocked(k, h)) { k.result.stale_accepts += 1; return false; }
    if (k.next_task >= TASK_CAP) {
        _ = releaseLocked(k, h); k.result.violations += 1; return false;
    }
    const id = k.next_task; k.next_task += 1;
    k.tasks[id] = .{
        .id = id,
        .handle = h,
        .state = .queued,
        .cancel = ((id + producer_id + op_index) % 11) == 0,
        .due_tick = 0,
    };
    if (!queuePushLocked(k, id)) {
        _ = releaseLocked(k, h); k.result.violations += 1; return false;
    }
    k.result.submitted += 1;
    signal(&k.cv_work); broadcast(&k.cv_state);
    return true;
}

fn workerProc(k: *Kernel, worker_id: u32) void {
    var local: u64 = worker_id + 1;
    while (true) {
        var id: u32 = undefined;
        lock(k);
        while (!k.shutdown and k.queue_count == 0 and !(k.producers_done and k.terminal == k.result.submitted)) {
            _ = c.pthread_cond_wait(&k.cv_work, &k.mutex);
        }
        if (k.shutdown) { unlock(k); return; }
        const maybe_id = queuePopLocked(k);
        if (maybe_id == null) {
            const done = k.producers_done and k.terminal == k.result.submitted;
            unlock(k);
            if (done) return;
            continue;
        }
        id = maybe_id.?;
        broadcast(&k.cv_space);
        var t = &k.tasks[id];
        if (t.state != .queued) { k.result.violations += 1; unlock(k); continue; }
        if (k.device_lost) {
            t.state = .lost; _ = releaseLocked(k, t.handle); k.result.lost += 1; k.terminal += 1;
            broadcast(&k.cv_state); unlock(k); continue;
        }
        if (t.cancel) {
            t.state = .cancelled; _ = releaseLocked(k, t.handle); k.result.cancelled += 1; k.terminal += 1;
            broadcast(&k.cv_state); unlock(k); continue;
        }
        t.state = .running; k.started += 1; broadcast(&k.cv_state); unlock(k);

        const work_count: u32 = 250 + ((id + worker_id) & 127);
        var i: u32 = 0;
        while (i < work_count) : (i += 1) {
            local ^= (local << 7) +% i +% id;
            local = (local >> 3) | (local << 61);
        }
        _ = c.sched_yield();

        lock(k);
        t = &k.tasks[id];
        if (t.state != .running) { k.result.violations += 1; unlock(k); continue; }
        if (k.device_lost) {
            t.state = .lost; _ = releaseLocked(k, t.handle); k.result.lost += 1; k.terminal += 1;
        } else if (t.cancel) {
            t.state = .cancelled; _ = releaseLocked(k, t.handle); k.result.cancelled += 1; k.terminal += 1;
        } else {
            t.state = .pending_fence; t.due_tick = k.tick + 2 + (id % 5);
        }
        broadcast(&k.cv_state); unlock(k);
    }
}
fn fenceProc(k: *Kernel) void {
    while (true) {
        _ = c.usleep(80);
        lock(k); k.tick += 1;
        var pending = false;
        var i: usize = 0;
        while (i < k.next_task) : (i += 1) {
            var t = &k.tasks[i];
            if (t.state != .pending_fence) continue;
            pending = true;
            if (k.device_lost) {
                t.state = .lost; _ = releaseLocked(k, t.handle); k.result.lost += 1; k.terminal += 1;
            } else if (t.due_tick <= k.tick) {
                t.state = .completed; _ = releaseLocked(k, t.handle); k.result.completed += 1; k.terminal += 1;
            }
        }
        broadcast(&k.cv_state);
        const should_exit = k.shutdown or (k.producers_done and k.terminal == k.result.submitted and !pending and k.queue_count == 0);
        unlock(k); if (should_exit) return;
    }
}
fn cancellerProc(k: *Kernel) void {
    var cursor: usize = 0;
    while (true) {
        _ = c.usleep(55); lock(k);
        if (k.shutdown) { unlock(k); return; }
        const upper: usize = @intCast(k.next_task);
        while (cursor < upper) : (cursor += 1) {
            if (cursor % 7 == 0) {
                var t = &k.tasks[cursor];
                if (t.state == .queued or t.state == .running or t.state == .pending_fence) t.cancel = true;
            }
        }
        const done = k.producers_done and k.terminal == k.result.submitted;
        unlock(k); if (done) return;
    }
}
fn lossProc(k: *Kernel, threshold: u64) void {
    if (threshold == 0) return;
    lock(k);
    while (!k.shutdown and k.started < threshold and !(k.producers_done and k.terminal == k.result.submitted)) {
        _ = c.pthread_cond_wait(&k.cv_state, &k.mutex);
    }
    if (k.shutdown or k.device_lost or k.terminal == k.result.submitted) { unlock(k); return; }
    k.device_lost = true; k.result.device_loss_events += 1;
    while (k.queue_count > 0) {
        const id = queuePopLocked(k) orelse break;
        var t = &k.tasks[id];
        if (t.state == .queued) {
            t.state = .lost; _ = releaseLocked(k, t.handle); k.result.lost += 1; k.terminal += 1;
        }
    }
    var i: usize = 0;
    while (i < k.next_task) : (i += 1) {
        var t = &k.tasks[i];
        if (t.state == .running or t.state == .pending_fence) t.cancel = true;
    }
    broadcast(&k.cv_work); broadcast(&k.cv_space); broadcast(&k.cv_state); unlock(k);
}
fn producerProc(a: *ProducerArgs) void {
    var x = a.seed ^ (0x9E3779B97F4A7C15 *% (@as(u64, a.producer_id) + 1));
    var op: u32 = 0;
    while (op < a.ops) : (op += 1) {
        x ^= x << 13; x ^= x >> 7; x ^= x << 17;
        const h = a.handles[x % RESOURCE_COUNT];
        lock(a.k);
        if (!a.k.device_lost and validLocked(a.k, h)) {
            if (!retainLocked(a.k, h)) a.k.result.violations += 1;
            if (!releaseLocked(a.k, h)) a.k.result.violations += 1;
        }
        unlock(a.k);
        const accepted = submit(a.k, h, a.producer_id, op);
        if (!accepted and !a.inject_loss) { lock(a.k); a.k.result.violations += 1; unlock(a.k); }
        if ((op & 31) == 0) _ = c.sched_yield();
    }
}

fn runCase(seed: u64, workers: u32, producers: u32, ops: u32, queue_cap: usize, inject_loss: bool) !Result {
    var k: Kernel = .{};
    k.queue_cap = @min(@max(queue_cap, 1), QUEUE_MAX);
    _ = c.pthread_mutex_init(&k.mutex, null);
    _ = c.pthread_cond_init(&k.cv_work, null);
    _ = c.pthread_cond_init(&k.cv_space, null);
    _ = c.pthread_cond_init(&k.cv_state, null);
    defer {
        _ = c.pthread_cond_destroy(&k.cv_state);
        _ = c.pthread_cond_destroy(&k.cv_space);
        _ = c.pthread_cond_destroy(&k.cv_work);
        _ = c.pthread_mutex_destroy(&k.mutex);
    }
    var handles: [RESOURCE_COUNT]Handle = [_]Handle{.{}} ** RESOURCE_COUNT;
    allocateBaseResources(&k, &handles);

    var worker_threads: [MAX_THREADS]std.Thread = undefined;
    var wi: usize = 0;
    while (wi < workers) : (wi += 1) worker_threads[wi] = try std.Thread.spawn(.{}, workerProc, .{ &k, @as(u32, @intCast(wi)) });
    const fence_thread = try std.Thread.spawn(.{}, fenceProc, .{&k});
    const cancel_thread = try std.Thread.spawn(.{}, cancellerProc, .{&k});
    var loss_thread: ?std.Thread = null;
    if (inject_loss) loss_thread = try std.Thread.spawn(.{}, lossProc, .{ &k, @max(@as(u64, 8), @as(u64, workers) * 4) });

    var producer_args: [MAX_THREADS]ProducerArgs = undefined;
    var producer_threads: [MAX_THREADS]std.Thread = undefined;
    var pi: usize = 0;
    while (pi < producers) : (pi += 1) {
        producer_args[pi] = .{ .k = &k, .handles = &handles, .producer_id = @intCast(pi), .seed = seed, .ops = ops, .inject_loss = inject_loss };
        producer_threads[pi] = try std.Thread.spawn(.{}, producerProc, .{&producer_args[pi]});
    }
    pi = 0; while (pi < producers) : (pi += 1) producer_threads[pi].join();
    lock(&k); k.producers_done = true; broadcast(&k.cv_work); broadcast(&k.cv_space); broadcast(&k.cv_state); unlock(&k);
    if (loss_thread) |lt| lt.join();
    wi = 0; while (wi < workers) : (wi += 1) worker_threads[wi].join();
    fence_thread.join(); cancel_thread.join();

    lock(&k);
    for (handles) |h| if (validLocked(&k, h) and !releaseLocked(&k, h)) k.result.violations += 1;
    if (k.terminal != k.result.submitted) k.result.violations += 1;
    if (k.result.completed + k.result.cancelled + k.result.lost != k.result.submitted) k.result.violations += 1;
    if (k.result.max_queue > k.queue_cap) k.result.violations += 1;
    for (&k.resources) |*r| if (r.alive or r.refs != 0) { k.result.leaked_resources += 1; };
    if (k.result.leaked_resources != 0) k.result.violations += 1;
    for (handles) |h| if (validLocked(&k, h)) { k.result.stale_accepts += 1; };
    if (k.result.stale_accepts != 0) k.result.violations += 1;
    for (&k.resources, 0..) |*r, i| {
        r.alive = true; r.refs = 1;
        const fresh = Handle{ .slot = @intCast(i), .generation = r.generation };
        if (fresh.generation == handles[i].generation) k.result.violations += 1;
        _ = releaseLocked(&k, fresh);
    }
    k.shutdown = true;
    const result = k.result; unlock(&k); return result;
}

fn parseArg(argv: [*]const [*:0]const u8, argc: c_int, index: usize, fallback: u64) u64 {
    if (index >= @as(usize, @intCast(argc))) return fallback;
    return std.fmt.parseInt(u64, std.mem.span(argv[index]), 10) catch fallback;
}

export fn main(argc: c_int, argv: [*]const [*:0]const u8) c_int {
    const seed = parseArg(argv, argc, 1, 1);
    const workers: u32 = @intCast(parseArg(argv, argc, 2, 4));
    const producers: u32 = @intCast(parseArg(argv, argc, 3, 4));
    const ops: u32 = @intCast(parseArg(argv, argc, 4, 400));
    const qcap: usize = @intCast(parseArg(argv, argc, 5, 16));
    const loss = parseArg(argv, argc, 6, 0) != 0;
    const start = std.time.nanoTimestamp();
    const r = runCase(seed, workers, producers, ops, qcap, loss) catch return 3;
    const elapsed_ns = std.time.nanoTimestamp() - start;
    const seconds = @as(f64, @floatFromInt(elapsed_ns)) / 1_000_000_000.0;
    std.debug.print("RESULT language=zig seed={} workers={} producers={} ops={} loss={} seconds={d:.6} submitted={} completed={} cancelled={} lost={} backpressure={} max_queue={} retain={} release={} stale_accepts={} leaked={} violations={}\n", .{
        seed, workers, producers, ops, @intFromBool(loss), seconds, r.submitted, r.completed, r.cancelled, r.lost,
        r.backpressure_waits, r.max_queue, r.retain_ops, r.release_ops, r.stale_accepts, r.leaked_resources, r.violations,
    });
    return if (r.violations == 0) 0 else 2;
}
