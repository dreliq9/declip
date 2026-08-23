package main

import "core:fmt"
import "core:os"
import "core:strconv"
import "core:sync"
import "core:thread"
import "core:time"

RESOURCE_COUNT :: 64
TASK_CAP       :: 8192
QUEUE_MAX      :: 128
MAX_THREADS    :: 32

Handle :: struct {
    slot:       u32,
    generation: u32,
}

Resource :: struct {
    generation: u32,
    refs:       u32,
    alive:      bool,
}

Task_State :: enum u8 {
    Empty,
    Queued,
    Running,
    Pending_Fence,
    Completed,
    Cancelled,
    Lost,
}

Task :: struct {
    id:        u32,
    handle:    Handle,
    state:     Task_State,
    cancel:    bool,
    due_tick:  u64,
}

Result :: struct {
    submitted:           u64,
    completed:           u64,
    cancelled:           u64,
    lost:                u64,
    backpressure_waits:  u64,
    stale_accepts:       u64,
    violations:          u64,
    retain_ops:          u64,
    release_ops:         u64,
    device_loss_events:  u64,
    max_queue:           u32,
    leaked_resources:    u32,
}

Kernel :: struct {
    mutex:          sync.Mutex,
    cv_work:        sync.Cond,
    cv_space:       sync.Cond,
    cv_state:       sync.Cond,
    resources:      [RESOURCE_COUNT]Resource,
    tasks:          [TASK_CAP]Task,
    queue:          [QUEUE_MAX]u32,
    queue_head:     int,
    queue_count:    int,
    queue_cap:      int,
    next_task:      u32,
    tick:           u64,
    producers_done: bool,
    shutdown:       bool,
    device_lost:    bool,
    started:        u64,
    terminal:       u64,
    result:         Result,
}

Producer_Args :: struct {
    k:           ^Kernel,
    handles:     ^[RESOURCE_COUNT]Handle,
    producer_id: u32,
    seed:        u64,
    ops:         u32,
    inject_loss: bool,
}

valid_locked :: proc "contextless" (k: ^Kernel, h: Handle) -> bool {
    if int(h.slot) < 0 || int(h.slot) >= RESOURCE_COUNT {
        return false
    }
    r := &k.resources[h.slot]
    return r.alive && r.generation == h.generation
}

retain_locked :: proc "contextless" (k: ^Kernel, h: Handle) -> bool {
    if !valid_locked(k, h) {
        return false
    }
    r := &k.resources[h.slot]
    r.refs += 1
    k.result.retain_ops += 1
    return true
}

release_locked :: proc "contextless" (k: ^Kernel, h: Handle) -> bool {
    if !valid_locked(k, h) {
        return false
    }
    r := &k.resources[h.slot]
    if r.refs == 0 {
        k.result.violations += 1
        return false
    }
    r.refs -= 1
    k.result.release_ops += 1
    if r.refs == 0 {
        r.alive = false
        r.generation += 1
        if r.generation == 0 {
            r.generation = 1
        }
    }
    return true
}

queue_push_locked :: proc "contextless" (k: ^Kernel, id: u32) -> bool {
    if k.queue_count >= k.queue_cap || k.queue_count >= QUEUE_MAX {
        return false
    }
    index := (k.queue_head + k.queue_count) % QUEUE_MAX
    k.queue[index] = id
    k.queue_count += 1
    if u32(k.queue_count) > k.result.max_queue {
        k.result.max_queue = u32(k.queue_count)
    }
    return true
}

queue_pop_locked :: proc "contextless" (k: ^Kernel) -> (u32, bool) {
    if k.queue_count == 0 {
        return 0, false
    }
    id := k.queue[k.queue_head]
    k.queue_head = (k.queue_head + 1) % QUEUE_MAX
    k.queue_count -= 1
    return id, true
}

allocate_base_resources :: proc(k: ^Kernel, handles: ^[RESOURCE_COUNT]Handle) {
    sync.mutex_lock(&k.mutex)
    defer sync.mutex_unlock(&k.mutex)
    for i in 0..<RESOURCE_COUNT {
        r := &k.resources[i]
        if r.generation == 0 {
            r.generation = 1
        }
        r.refs = 1
        r.alive = true
        handles[i] = Handle{u32(i), r.generation}
    }
}

submit :: proc(k: ^Kernel, h: Handle, producer_id, op_index: u32) -> bool {
    sync.mutex_lock(&k.mutex)
    defer sync.mutex_unlock(&k.mutex)

    for k.queue_count >= k.queue_cap && !k.device_lost && !k.shutdown {
        k.result.backpressure_waits += 1
        sync.cond_wait(&k.cv_space, &k.mutex)
    }
    if k.device_lost || k.shutdown {
        return false
    }
    if !retain_locked(k, h) {
        k.result.stale_accepts += 1
        return false
    }
    if int(k.next_task) >= TASK_CAP {
        _ = release_locked(k, h)
        k.result.violations += 1
        return false
    }
    id := k.next_task
    k.next_task += 1
    k.tasks[id] = Task{
        id        = id,
        handle    = h,
        state     = .Queued,
        cancel    = ((id + producer_id + op_index) % 11) == 0,
        due_tick  = 0,
    }
    if !queue_push_locked(k, id) {
        _ = release_locked(k, h)
        k.result.violations += 1
        return false
    }
    k.result.submitted += 1
    sync.cond_signal(&k.cv_work)
    sync.cond_broadcast(&k.cv_state)
    return true
}

worker_proc :: proc(k: ^Kernel, worker_id: int) {
    local := u64(worker_id + 1)
    for {
        id: u32
        sync.mutex_lock(&k.mutex)
        for !k.shutdown && k.queue_count == 0 && !(k.producers_done && k.terminal == k.result.submitted) {
            sync.cond_wait(&k.cv_work, &k.mutex)
        }
        if k.shutdown {
            sync.mutex_unlock(&k.mutex)
            return
        }
        popped, ok := queue_pop_locked(k)
        if !ok {
            done := k.producers_done && k.terminal == k.result.submitted
            sync.mutex_unlock(&k.mutex)
            if done { return }
            continue
        }
        id = popped
        sync.cond_broadcast(&k.cv_space)
        t := &k.tasks[id]
        if t.state != .Queued {
            k.result.violations += 1
            sync.mutex_unlock(&k.mutex)
            continue
        }
        if k.device_lost {
            t.state = .Lost
            _ = release_locked(k, t.handle)
            k.result.lost += 1
            k.terminal += 1
            sync.cond_broadcast(&k.cv_state)
            sync.mutex_unlock(&k.mutex)
            continue
        }
        if t.cancel {
            t.state = .Cancelled
            _ = release_locked(k, t.handle)
            k.result.cancelled += 1
            k.terminal += 1
            sync.cond_broadcast(&k.cv_state)
            sync.mutex_unlock(&k.mutex)
            continue
        }
        t.state = .Running
        k.started += 1
        sync.cond_broadcast(&k.cv_state)
        sync.mutex_unlock(&k.mutex)

        work_count := 250 + int((id + u32(worker_id)) & 127)
        for i in 0..<work_count {
            local ~= (local << 7) + u64(i) + u64(id)
            local = (local >> 3) | (local << 61)
        }
        thread.yield()

        sync.mutex_lock(&k.mutex)
        t = &k.tasks[id]
        if t.state != .Running {
            k.result.violations += 1
            sync.mutex_unlock(&k.mutex)
            continue
        }
        if k.device_lost {
            t.state = .Lost
            _ = release_locked(k, t.handle)
            k.result.lost += 1
            k.terminal += 1
        } else if t.cancel {
            t.state = .Cancelled
            _ = release_locked(k, t.handle)
            k.result.cancelled += 1
            k.terminal += 1
        } else {
            t.state = .Pending_Fence
            t.due_tick = k.tick + 2 + u64(id % 5)
        }
        sync.cond_broadcast(&k.cv_state)
        sync.mutex_unlock(&k.mutex)
    }
}

fence_proc :: proc(k: ^Kernel) {
    for {
        time.sleep(80 * time.Microsecond)
        sync.mutex_lock(&k.mutex)
        k.tick += 1
        pending := false
        for i in 0..<int(k.next_task) {
            t := &k.tasks[i]
            if t.state != .Pending_Fence {
                continue
            }
            pending = true
            if k.device_lost {
                t.state = .Lost
                _ = release_locked(k, t.handle)
                k.result.lost += 1
                k.terminal += 1
            } else if t.due_tick <= k.tick {
                t.state = .Completed
                _ = release_locked(k, t.handle)
                k.result.completed += 1
                k.terminal += 1
            }
        }
        sync.cond_broadcast(&k.cv_state)
        should_exit := k.shutdown || (k.producers_done && k.terminal == k.result.submitted && !pending && k.queue_count == 0)
        sync.mutex_unlock(&k.mutex)
        if should_exit { return }
    }
}

canceller_proc :: proc(k: ^Kernel) {
    cursor := 0
    for {
        time.sleep(55 * time.Microsecond)
        sync.mutex_lock(&k.mutex)
        if k.shutdown {
            sync.mutex_unlock(&k.mutex)
            return
        }
        upper := int(k.next_task)
        for cursor < upper {
            if cursor % 7 == 0 {
                t := &k.tasks[cursor]
                if t.state == .Queued || t.state == .Running || t.state == .Pending_Fence {
                    t.cancel = true
                }
            }
            cursor += 1
        }
        done := k.producers_done && k.terminal == k.result.submitted
        sync.mutex_unlock(&k.mutex)
        if done { return }
    }
}

loss_proc :: proc(k: ^Kernel, threshold: u64) {
    if threshold == 0 { return }
    sync.mutex_lock(&k.mutex)
    for !k.shutdown && k.started < threshold && !(k.producers_done && k.terminal == k.result.submitted) {
        sync.cond_wait(&k.cv_state, &k.mutex)
    }
    if k.shutdown || k.device_lost || k.terminal == k.result.submitted {
        sync.mutex_unlock(&k.mutex)
        return
    }
    k.device_lost = true
    k.result.device_loss_events += 1
    for k.queue_count > 0 {
        id, ok := queue_pop_locked(k)
        if !ok { break }
        t := &k.tasks[id]
        if t.state == .Queued {
            t.state = .Lost
            _ = release_locked(k, t.handle)
            k.result.lost += 1
            k.terminal += 1
        }
    }
    for i in 0..<int(k.next_task) {
        t := &k.tasks[i]
        if t.state == .Running || t.state == .Pending_Fence {
            t.cancel = true
        }
    }
    sync.cond_broadcast(&k.cv_work)
    sync.cond_broadcast(&k.cv_space)
    sync.cond_broadcast(&k.cv_state)
    sync.mutex_unlock(&k.mutex)
}

producer_entry :: proc(data: rawptr) {
    a := cast(^Producer_Args)data
    x := a.seed ~ (u64(0x9E3779B97F4A7C15) * (u64(a.producer_id) + 1))
    for op in 0..<a.ops {
        x ~= x << 13
        x ~= x >> 7
        x ~= x << 17
        h := a.handles[x % RESOURCE_COUNT]
        sync.mutex_lock(&a.k.mutex)
        if !a.k.device_lost && valid_locked(a.k, h) {
            if !retain_locked(a.k, h) { a.k.result.violations += 1 }
            if !release_locked(a.k, h) { a.k.result.violations += 1 }
        }
        sync.mutex_unlock(&a.k.mutex)
        accepted := submit(a.k, h, a.producer_id, op)
        if !accepted && !a.inject_loss {
            sync.mutex_lock(&a.k.mutex)
            a.k.result.violations += 1
            sync.mutex_unlock(&a.k.mutex)
        }
        if (op & 31) == 0 { thread.yield() }
    }
}

run_case :: proc(seed: u64, workers, producers: int, ops: u32, queue_cap: int, inject_loss: bool) -> Result {
    k := new(Kernel)
    defer free(k)
    k.queue_cap = clamp(queue_cap, 1, QUEUE_MAX)

    handles: [RESOURCE_COUNT]Handle
    allocate_base_resources(k, &handles)

    worker_threads: [MAX_THREADS]^thread.Thread
    for i in 0..<workers {
        worker_threads[i] = thread.create_and_start_with_poly_data2(k, i, worker_proc)
    }
    fence_thread := thread.create_and_start_with_poly_data(k, fence_proc)
    cancel_thread := thread.create_and_start_with_poly_data(k, canceller_proc)
    loss_thread: ^thread.Thread
    if inject_loss {
        threshold := max(u64(8), u64(workers * 4))
        loss_thread = thread.create_and_start_with_poly_data2(k, threshold, loss_proc)
    }

    producer_args: [MAX_THREADS]Producer_Args
    producer_threads: [MAX_THREADS]^thread.Thread
    for p in 0..<producers {
        producer_args[p] = Producer_Args{k, &handles, u32(p), seed, ops, inject_loss}
        producer_threads[p] = thread.create_and_start_with_data(rawptr(&producer_args[p]), producer_entry)
    }
    for p in 0..<producers {
        thread.destroy(producer_threads[p])
    }

    sync.mutex_lock(&k.mutex)
    k.producers_done = true
    sync.cond_broadcast(&k.cv_work)
    sync.cond_broadcast(&k.cv_space)
    sync.cond_broadcast(&k.cv_state)
    sync.mutex_unlock(&k.mutex)

    if loss_thread != nil { thread.destroy(loss_thread) }
    for i in 0..<workers { thread.destroy(worker_threads[i]) }
    thread.destroy(fence_thread)
    thread.destroy(cancel_thread)

    sync.mutex_lock(&k.mutex)
    for h in handles {
        if valid_locked(k, h) && !release_locked(k, h) { k.result.violations += 1 }
    }
    if k.terminal != k.result.submitted { k.result.violations += 1 }
    if k.result.completed + k.result.cancelled + k.result.lost != k.result.submitted { k.result.violations += 1 }
    if int(k.result.max_queue) > k.queue_cap { k.result.violations += 1 }
    for i in 0..<RESOURCE_COUNT {
        r := &k.resources[i]
        if r.alive || r.refs != 0 { k.result.leaked_resources += 1 }
    }
    if k.result.leaked_resources != 0 { k.result.violations += 1 }
    for h in handles {
        if valid_locked(k, h) { k.result.stale_accepts += 1 }
    }
    if k.result.stale_accepts != 0 { k.result.violations += 1 }
    for i in 0..<RESOURCE_COUNT {
        r := &k.resources[i]
        r.alive = true
        r.refs = 1
        fresh := Handle{u32(i), r.generation}
        if fresh.generation == handles[i].generation { k.result.violations += 1 }
        _ = release_locked(k, fresh)
    }
    k.shutdown = true
    result := k.result
    sync.mutex_unlock(&k.mutex)
    return result
}

arg_u64 :: proc(index: int, fallback: u64) -> u64 {
    if index >= len(os.args) { return fallback }
    v, ok := strconv.parse_u64_maybe_prefixed(os.args[index])
    return v if ok else fallback
}

arg_int :: proc(index: int, fallback: int) -> int {
    if index >= len(os.args) { return fallback }
    v, ok := strconv.parse_int(os.args[index])
    return v if ok else fallback
}

main :: proc() {
    seed := arg_u64(1, 1)
    workers := arg_int(2, 4)
    producers := arg_int(3, 4)
    ops := u32(arg_int(4, 400))
    qcap := arg_int(5, 16)
    loss := arg_int(6, 0) != 0

    start := time.tick_now()
    r := run_case(seed, workers, producers, ops, qcap, loss)
    seconds := time.duration_seconds(time.tick_since(start))
    fmt.printfln("RESULT language=odin seed=%d workers=%d producers=%d ops=%d loss=%d seconds=%.6f submitted=%d completed=%d cancelled=%d lost=%d backpressure=%d max_queue=%d retain=%d release=%d stale_accepts=%d leaked=%d violations=%d",
        seed, workers, producers, ops, int(loss), seconds, r.submitted, r.completed, r.cancelled, r.lost,
        r.backpressure_waits, r.max_queue, r.retain_ops, r.release_ops, r.stale_accepts, r.leaked_resources, r.violations)
    if r.violations != 0 { os.exit(2) }
}
