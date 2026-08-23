use std::cmp::max;
use std::collections::VecDeque;
use std::env;
use std::sync::{Arc, Condvar, Mutex};
use std::thread;
use std::time::{Duration, Instant};

#[derive(Clone, Copy)]
struct Handle {
    slot: u32,
    generation: u32,
}

#[derive(Clone, Copy)]
struct Resource {
    generation: u32,
    refs: u32,
    alive: bool,
}

impl Default for Resource {
    fn default() -> Self {
        Self { generation: 1, refs: 0, alive: false }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum TaskState {
    Empty,
    Queued,
    Running,
    PendingFence,
    Completed,
    Cancelled,
    Lost,
}

#[derive(Clone, Copy)]
struct Task {
    id: u32,
    handle: Handle,
    state: TaskState,
    cancel: bool,
    due_tick: u64,
}

impl Default for Task {
    fn default() -> Self {
        Self {
            id: 0,
            handle: Handle { slot: 0, generation: 0 },
            state: TaskState::Empty,
            cancel: false,
            due_tick: 0,
        }
    }
}

#[derive(Default, Clone, Copy)]
struct ResultData {
    submitted: u64,
    completed: u64,
    cancelled: u64,
    lost: u64,
    backpressure_waits: u64,
    stale_accepts: u64,
    violations: u64,
    retain_ops: u64,
    release_ops: u64,
    device_loss_events: u64,
    max_queue: u32,
    leaked_resources: u32,
}

struct State {
    resources: Vec<Resource>,
    tasks: Vec<Task>,
    queue: VecDeque<u32>,
    queue_cap: usize,
    next_task: u32,
    tick: u64,
    producers_done: bool,
    shutdown: bool,
    device_lost: bool,
    started: u64,
    terminal: u64,
    result: ResultData,
}

impl State {
    fn new(queue_cap: usize) -> Self {
        Self {
            resources: vec![Resource::default(); 64],
            tasks: vec![Task::default(); 8192],
            queue: VecDeque::with_capacity(queue_cap),
            queue_cap,
            next_task: 0,
            tick: 0,
            producers_done: false,
            shutdown: false,
            device_lost: false,
            started: 0,
            terminal: 0,
            result: ResultData::default(),
        }
    }

    fn valid(&self, h: Handle) -> bool {
        let Some(r) = self.resources.get(h.slot as usize) else { return false; };
        r.alive && r.generation == h.generation
    }

    fn retain(&mut self, h: Handle) -> bool {
        if !self.valid(h) { return false; }
        let r = &mut self.resources[h.slot as usize];
        r.refs += 1;
        self.result.retain_ops += 1;
        true
    }

    fn release(&mut self, h: Handle) -> bool {
        if !self.valid(h) { return false; }
        let r = &mut self.resources[h.slot as usize];
        if r.refs == 0 {
            self.result.violations += 1;
            return false;
        }
        r.refs -= 1;
        self.result.release_ops += 1;
        if r.refs == 0 {
            r.alive = false;
            r.generation = r.generation.wrapping_add(1);
            if r.generation == 0 { r.generation = 1; }
        }
        true
    }
}

struct Kernel {
    state: Mutex<State>,
    cv_work: Condvar,
    cv_space: Condvar,
    cv_state: Condvar,
}

impl Kernel {
    fn new(queue_cap: usize) -> Arc<Self> {
        Arc::new(Self {
            state: Mutex::new(State::new(queue_cap)),
            cv_work: Condvar::new(),
            cv_space: Condvar::new(),
            cv_state: Condvar::new(),
        })
    }

    fn allocate_base_resources(&self) -> Vec<Handle> {
        let mut s = self.state.lock().unwrap();
        let mut out = Vec::with_capacity(s.resources.len());
        for (i, r) in s.resources.iter_mut().enumerate() {
            r.refs = 1;
            r.alive = true;
            out.push(Handle { slot: i as u32, generation: r.generation });
        }
        out
    }

    fn submit(&self, h: Handle, producer_id: u32, op_index: u32) -> bool {
        let mut s = self.state.lock().unwrap();
        while s.queue.len() >= s.queue_cap && !s.device_lost && !s.shutdown {
            s.result.backpressure_waits += 1;
            s = self.cv_space.wait(s).unwrap();
        }
        if s.device_lost || s.shutdown { return false; }
        if !s.retain(h) {
            s.result.stale_accepts += 1;
            return false;
        }
        if s.next_task as usize >= s.tasks.len() {
            s.release(h);
            s.result.violations += 1;
            return false;
        }
        let id = s.next_task;
        s.next_task += 1;
        s.tasks[id as usize] = Task {
            id,
            handle: h,
            state: TaskState::Queued,
            cancel: ((id + producer_id + op_index) % 11) == 0,
            due_tick: 0,
        };
        s.queue.push_back(id);
        s.result.submitted += 1;
        s.result.max_queue = max(s.result.max_queue, s.queue.len() as u32);
        self.cv_work.notify_one();
        self.cv_state.notify_all();
        true
    }

    fn worker(self: &Arc<Self>, worker_id: u32) {
        let mut local = worker_id as u64 + 1;
        loop {
            let id = {
                let mut s = self.state.lock().unwrap();
                while !s.shutdown && s.queue.is_empty() && !(s.producers_done && s.terminal == s.result.submitted) {
                    s = self.cv_work.wait(s).unwrap();
                }
                if s.shutdown { return; }
                let Some(id) = s.queue.pop_front() else {
                    if s.producers_done && s.terminal == s.result.submitted { return; }
                    continue;
                };
                self.cv_space.notify_all();
                let state = s.tasks[id as usize].state;
                if state != TaskState::Queued {
                    s.result.violations += 1;
                    continue;
                }
                if s.device_lost {
                    let h = s.tasks[id as usize].handle;
                    s.tasks[id as usize].state = TaskState::Lost;
                    s.release(h);
                    s.result.lost += 1;
                    s.terminal += 1;
                    self.cv_state.notify_all();
                    continue;
                }
                if s.tasks[id as usize].cancel {
                    let h = s.tasks[id as usize].handle;
                    s.tasks[id as usize].state = TaskState::Cancelled;
                    s.release(h);
                    s.result.cancelled += 1;
                    s.terminal += 1;
                    self.cv_state.notify_all();
                    continue;
                }
                s.tasks[id as usize].state = TaskState::Running;
                s.started += 1;
                id
            };

            for i in 0..(250 + ((id + worker_id) & 127)) {
                local ^= local.wrapping_shl(7).wrapping_add(i as u64).wrapping_add(id as u64);
                local = local.rotate_right(3);
            }
            thread::yield_now();

            let mut s = self.state.lock().unwrap();
            if s.tasks[id as usize].state != TaskState::Running {
                s.result.violations += 1;
                continue;
            }
            if s.device_lost {
                let h = s.tasks[id as usize].handle;
                s.tasks[id as usize].state = TaskState::Lost;
                s.release(h);
                s.result.lost += 1;
                s.terminal += 1;
            } else if s.tasks[id as usize].cancel {
                let h = s.tasks[id as usize].handle;
                s.tasks[id as usize].state = TaskState::Cancelled;
                s.release(h);
                s.result.cancelled += 1;
                s.terminal += 1;
            } else {
                s.tasks[id as usize].state = TaskState::PendingFence;
                s.tasks[id as usize].due_tick = s.tick + 2 + (id as u64 % 5);
            }
            self.cv_state.notify_all();
        }
    }

    fn fence_thread(self: &Arc<Self>) {
        loop {
            thread::sleep(Duration::from_micros(80));
            let mut s = self.state.lock().unwrap();
            s.tick += 1;
            let tick = s.tick;
            let device_lost = s.device_lost;
            let mut pending = false;
            for i in 0..s.next_task as usize {
                if s.tasks[i].state != TaskState::PendingFence { continue; }
                pending = true;
                if device_lost {
                    let h = s.tasks[i].handle;
                    s.tasks[i].state = TaskState::Lost;
                    s.release(h);
                    s.result.lost += 1;
                    s.terminal += 1;
                } else if s.tasks[i].due_tick <= tick {
                    let h = s.tasks[i].handle;
                    s.tasks[i].state = TaskState::Completed;
                    s.release(h);
                    s.result.completed += 1;
                    s.terminal += 1;
                }
            }
            self.cv_state.notify_all();
            if s.shutdown { return; }
            if s.producers_done && s.terminal == s.result.submitted && !pending && s.queue.is_empty() { return; }
        }
    }

    fn canceller(self: &Arc<Self>) {
        let mut cursor = 0usize;
        loop {
            thread::sleep(Duration::from_micros(55));
            let mut s = self.state.lock().unwrap();
            if s.shutdown { return; }
            let upper = s.next_task as usize;
            while cursor < upper {
                if cursor % 7 == 0 {
                    let t = &mut s.tasks[cursor];
                    if matches!(t.state, TaskState::Queued | TaskState::Running | TaskState::PendingFence) {
                        t.cancel = true;
                    }
                }
                cursor += 1;
            }
            if s.producers_done && s.terminal == s.result.submitted { return; }
        }
    }

    fn trigger_device_loss_after(self: &Arc<Self>, threshold: u64) {
        if threshold == 0 { return; }
        let mut s = self.state.lock().unwrap();
        while !s.shutdown && s.started < threshold && !(s.producers_done && s.terminal == s.result.submitted) {
            s = self.cv_state.wait(s).unwrap();
        }
        if s.shutdown || s.device_lost || s.terminal == s.result.submitted { return; }
        s.device_lost = true;
        s.result.device_loss_events += 1;
        while let Some(id) = s.queue.pop_front() {
            if s.tasks[id as usize].state == TaskState::Queued {
                let h = s.tasks[id as usize].handle;
                s.tasks[id as usize].state = TaskState::Lost;
                s.release(h);
                s.result.lost += 1;
                s.terminal += 1;
            }
        }
        for i in 0..s.next_task as usize {
            if matches!(s.tasks[i].state, TaskState::Running | TaskState::PendingFence) {
                s.tasks[i].cancel = true;
            }
        }
        self.cv_work.notify_all();
        self.cv_space.notify_all();
        self.cv_state.notify_all();
    }

    fn run_case(self: &Arc<Self>, seed: u64, workers: u32, producers: u32, ops_per_producer: u32, inject_loss: bool) -> ResultData {
        let handles = Arc::new(self.allocate_base_resources());
        let mut worker_threads = Vec::new();
        for i in 0..workers {
            let k = Arc::clone(self);
            worker_threads.push(thread::spawn(move || k.worker(i)));
        }
        let fence_k = Arc::clone(self);
        let fence = thread::spawn(move || fence_k.fence_thread());
        let cancel_k = Arc::clone(self);
        let cancel = thread::spawn(move || cancel_k.canceller());
        let loss = if inject_loss {
            let loss_k = Arc::clone(self);
            Some(thread::spawn(move || loss_k.trigger_device_loss_after(max(8, workers as u64 * 4))))
        } else { None };

        let mut producer_threads = Vec::new();
        for p in 0..producers {
            let k = Arc::clone(self);
            let hs = Arc::clone(&handles);
            producer_threads.push(thread::spawn(move || {
                let mut x = seed ^ 0x9E37_79B9_7F4A_7C15u64.wrapping_mul(p as u64 + 1);
                for op in 0..ops_per_producer {
                    x ^= x << 13; x ^= x >> 7; x ^= x << 17;
                    let h = hs[(x as usize) % hs.len()];
                    {
                        let mut s = k.state.lock().unwrap();
                        if !s.device_lost && s.valid(h) {
                            if !s.retain(h) { s.result.violations += 1; }
                            if !s.release(h) { s.result.violations += 1; }
                        }
                    }
                    if !k.submit(h, p, op) && !inject_loss {
                        k.state.lock().unwrap().result.violations += 1;
                    }
                    if op & 31 == 0 { thread::yield_now(); }
                }
            }));
        }
        for t in producer_threads { t.join().unwrap(); }
        {
            let mut s = self.state.lock().unwrap();
            s.producers_done = true;
            self.cv_work.notify_all();
            self.cv_space.notify_all();
            self.cv_state.notify_all();
        }
        if let Some(t) = loss { t.join().unwrap(); }
        for t in worker_threads { t.join().unwrap(); }
        fence.join().unwrap();
        cancel.join().unwrap();

        let mut s = self.state.lock().unwrap();
        for h in handles.iter().copied() {
            if s.valid(h) && !s.release(h) { s.result.violations += 1; }
        }
        if s.terminal != s.result.submitted { s.result.violations += 1; }
        if s.result.completed + s.result.cancelled + s.result.lost != s.result.submitted { s.result.violations += 1; }
        if s.result.max_queue as usize > s.queue_cap { s.result.violations += 1; }
        s.result.leaked_resources = s.resources.iter().filter(|r| r.alive || r.refs != 0).count() as u32;
        if s.result.leaked_resources != 0 { s.result.violations += 1; }
        for h in handles.iter().copied() {
            if s.valid(h) { s.result.stale_accepts += 1; }
        }
        if s.result.stale_accepts != 0 { s.result.violations += 1; }
        for (i, old) in handles.iter().copied().enumerate() {
            let generation = {
                let r = &mut s.resources[i];
                r.alive = true;
                r.refs = 1;
                r.generation
            };
            let fresh = Handle { slot: i as u32, generation };
            if fresh.generation == old.generation { s.result.violations += 1; }
            s.release(fresh);
        }
        s.shutdown = true;
        s.result
    }
}

fn parse<T: std::str::FromStr>(args: &[String], index: usize, default: T) -> T {
    args.get(index).and_then(|s| s.parse().ok()).unwrap_or(default)
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let seed: u64 = parse(&args, 1, 1);
    let workers: u32 = parse(&args, 2, 4);
    let producers: u32 = parse(&args, 3, 4);
    let ops: u32 = parse(&args, 4, 400);
    let qcap: usize = parse(&args, 5, 16);
    let loss: u32 = parse(&args, 6, 0);
    let k = Kernel::new(qcap);
    let started = Instant::now();
    let r = k.run_case(seed, workers, producers, ops, loss != 0);
    let seconds = started.elapsed().as_secs_f64();
    println!(
        "RESULT language=rust seed={} workers={} producers={} ops={} loss={} seconds={} submitted={} completed={} cancelled={} lost={} backpressure={} max_queue={} retain={} release={} stale_accepts={} leaked={} violations={}",
        seed, workers, producers, ops, loss, seconds, r.submitted, r.completed, r.cancelled, r.lost,
        r.backpressure_waits, r.max_queue, r.retain_ops, r.release_ops, r.stale_accepts, r.leaked_resources, r.violations
    );
    if r.violations != 0 { std::process::exit(2); }
}
