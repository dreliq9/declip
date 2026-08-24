#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>

using namespace std::chrono_literals;

struct Handle { uint32_t slot; uint32_t generation; };
struct Resource { uint32_t generation{1}; uint32_t refs{0}; bool alive{false}; };
enum class TaskState : uint8_t { Empty, Queued, Running, PendingFence, Completed, Cancelled, Lost };
struct Task { uint32_t id{0}; Handle handle{}; TaskState state{TaskState::Empty}; bool cancel{false}; uint64_t due_tick{0}; };

struct Result {
    uint64_t submitted{0}, completed{0}, cancelled{0}, lost{0};
    uint64_t backpressure_waits{0}, stale_accepts{0}, violations{0};
    uint64_t retain_ops{0}, release_ops{0}, device_loss_events{0};
    uint32_t max_queue{0}, leaked_resources{0};
};

struct Kernel {
    static constexpr uint32_t RESOURCE_COUNT = 64;
    static constexpr uint32_t TASK_CAP = 8192;

    std::mutex m;
    std::condition_variable cv_work;
    std::condition_variable cv_space;
    std::condition_variable cv_state;
    std::vector<Resource> resources = std::vector<Resource>(RESOURCE_COUNT);
    std::vector<Task> tasks = std::vector<Task>(TASK_CAP);
    std::vector<uint32_t> queue;
    uint32_t queue_cap{16};
    uint32_t next_task{0};
    uint64_t tick{0};
    bool producers_done{false};
    bool shutdown{false};
    bool device_lost{false};
    uint64_t started{0};
    uint64_t terminal{0};
    Result result{};

    explicit Kernel(uint32_t cap) : queue_cap(cap) { queue.reserve(cap); }

    bool valid_locked(Handle h) const {
        return h.slot < resources.size() && resources[h.slot].alive && resources[h.slot].generation == h.generation;
    }

    bool retain_locked(Handle h) {
        if (!valid_locked(h)) return false;
        resources[h.slot].refs++;
        result.retain_ops++;
        return true;
    }

    bool release_locked(Handle h) {
        if (!valid_locked(h)) return false;
        auto &r = resources[h.slot];
        if (r.refs == 0) { result.violations++; return false; }
        r.refs--;
        result.release_ops++;
        if (r.refs == 0) {
            r.alive = false;
            r.generation++;
            if (r.generation == 0) r.generation = 1;
        }
        return true;
    }

    std::vector<Handle> allocate_base_resources() {
        std::lock_guard<std::mutex> lock(m);
        std::vector<Handle> out;
        out.reserve(resources.size());
        for (uint32_t i = 0; i < resources.size(); ++i) {
            auto &r = resources[i];
            r.refs = 1;
            r.alive = true;
            out.push_back({i, r.generation});
        }
        return out;
    }

    bool submit(Handle h, uint32_t producer_id, uint32_t op_index) {
        std::unique_lock<std::mutex> lock(m);
        while (queue.size() >= queue_cap && !device_lost && !shutdown) {
            result.backpressure_waits++;
            cv_space.wait(lock);
        }
        if (device_lost || shutdown) return false;
        if (!retain_locked(h)) { result.stale_accepts++; return false; }
        if (next_task >= tasks.size()) {
            release_locked(h);
            result.violations++;
            return false;
        }
        uint32_t id = next_task++;
        auto &t = tasks[id];
        t.id = id;
        t.handle = h;
        t.state = TaskState::Queued;
        t.cancel = ((id + producer_id + op_index) % 11u) == 0u;
        queue.push_back(id);
        result.submitted++;
        result.max_queue = std::max<uint32_t>(result.max_queue, static_cast<uint32_t>(queue.size()));
        cv_work.notify_one();
        cv_state.notify_all();
        return true;
    }

    void worker(uint32_t worker_id) {
        uint64_t local = worker_id + 1;
        for (;;) {
            uint32_t id = 0;
            {
                std::unique_lock<std::mutex> lock(m);
                cv_work.wait(lock, [&]{ return shutdown || !queue.empty() || (producers_done && terminal == result.submitted); });
                if (shutdown) return;
                if (queue.empty()) {
                    if (producers_done && terminal == result.submitted) return;
                    continue;
                }
                id = queue.front();
                queue.erase(queue.begin());
                cv_space.notify_all();
                auto &t = tasks[id];
                if (t.state != TaskState::Queued) { result.violations++; continue; }
                if (device_lost) {
                    t.state = TaskState::Lost;
                    release_locked(t.handle);
                    result.lost++; terminal++;
                    cv_state.notify_all();
                    continue;
                }
                if (t.cancel) {
                    t.state = TaskState::Cancelled;
                    release_locked(t.handle);
                    result.cancelled++; terminal++;
                    cv_state.notify_all();
                    continue;
                }
                t.state = TaskState::Running;
                started++;
            }

            for (uint32_t i = 0; i < 250 + ((id + worker_id) & 127u); ++i) {
                local ^= (local << 7) + i + id;
                local = (local >> 3) | (local << 61);
            }
            std::this_thread::yield();

            {
                std::lock_guard<std::mutex> lock(m);
                auto &t = tasks[id];
                if (t.state != TaskState::Running) { result.violations++; continue; }
                if (device_lost) {
                    t.state = TaskState::Lost;
                    release_locked(t.handle);
                    result.lost++; terminal++;
                } else if (t.cancel) {
                    t.state = TaskState::Cancelled;
                    release_locked(t.handle);
                    result.cancelled++; terminal++;
                } else {
                    t.state = TaskState::PendingFence;
                    t.due_tick = tick + 2 + (id % 5);
                }
                cv_state.notify_all();
            }
        }
    }

    void fence_thread() {
        for (;;) {
            std::this_thread::sleep_for(80us);
            std::lock_guard<std::mutex> lock(m);
            tick++;
            bool pending = false;
            for (uint32_t i = 0; i < next_task; ++i) {
                auto &t = tasks[i];
                if (t.state != TaskState::PendingFence) continue;
                pending = true;
                if (device_lost) {
                    t.state = TaskState::Lost;
                    release_locked(t.handle);
                    result.lost++; terminal++;
                } else if (t.due_tick <= tick) {
                    t.state = TaskState::Completed;
                    release_locked(t.handle);
                    result.completed++; terminal++;
                }
            }
            cv_state.notify_all();
            if (shutdown) return;
            if (producers_done && terminal == result.submitted && !pending && queue.empty()) return;
        }
    }

    void canceller() {
        uint32_t cursor = 0;
        for (;;) {
            std::this_thread::sleep_for(55us);
            std::lock_guard<std::mutex> lock(m);
            if (shutdown) return;
            uint32_t upper = next_task;
            for (; cursor < upper; ++cursor) {
                if ((cursor % 7u) == 0u) {
                    auto &t = tasks[cursor];
                    if (t.state == TaskState::Queued || t.state == TaskState::Running || t.state == TaskState::PendingFence) t.cancel = true;
                }
            }
            if (producers_done && terminal == result.submitted) return;
        }
    }

    void trigger_device_loss_after(uint64_t threshold) {
        if (threshold == 0) return;
        std::unique_lock<std::mutex> lock(m);
        cv_state.wait(lock, [&]{ return shutdown || started >= threshold || (producers_done && terminal == result.submitted); });
        if (shutdown || device_lost || terminal == result.submitted) return;
        device_lost = true;
        result.device_loss_events++;
        for (auto id : queue) {
            auto &t = tasks[id];
            if (t.state == TaskState::Queued) {
                t.state = TaskState::Lost;
                release_locked(t.handle);
                result.lost++; terminal++;
            }
        }
        queue.clear();
        for (uint32_t i = 0; i < next_task; ++i) {
            if (tasks[i].state == TaskState::Running || tasks[i].state == TaskState::PendingFence) tasks[i].cancel = true;
        }
        cv_work.notify_all();
        cv_space.notify_all();
        cv_state.notify_all();
    }

    Result run_case(uint64_t seed, uint32_t workers, uint32_t producers, uint32_t ops_per_producer, bool inject_loss) {
        auto handles = allocate_base_resources();
        std::vector<std::thread> worker_threads;
        for (uint32_t i = 0; i < workers; ++i) worker_threads.emplace_back([&, i]{ worker(i); });
        std::thread fence([&]{ fence_thread(); });
        std::thread cancel([&]{ canceller(); });
        std::thread loss;
        if (inject_loss) loss = std::thread([&]{ trigger_device_loss_after(std::max<uint64_t>(8, (uint64_t)workers * 4)); });

        std::vector<std::thread> producer_threads;
        for (uint32_t p = 0; p < producers; ++p) {
            producer_threads.emplace_back([&, p]{
                uint64_t x = seed ^ (0x9E3779B97F4A7C15ull * (p + 1));
                for (uint32_t op = 0; op < ops_per_producer; ++op) {
                    x ^= x << 13; x ^= x >> 7; x ^= x << 17;
                    auto h = handles[static_cast<size_t>(x % handles.size())];
                    {
                        std::lock_guard<std::mutex> lock(m);
                        if (!device_lost && valid_locked(h)) {
                            if (!retain_locked(h)) result.violations++;
                            if (!release_locked(h)) result.violations++;
                        }
                    }
                    if (!submit(h, p, op) && !inject_loss) {
                        std::lock_guard<std::mutex> lock(m);
                        result.violations++;
                    }
                    if ((op & 31u) == 0u) std::this_thread::yield();
                }
            });
        }
        for (auto &t : producer_threads) t.join();
        {
            std::lock_guard<std::mutex> lock(m);
            producers_done = true;
            cv_work.notify_all(); cv_space.notify_all(); cv_state.notify_all();
        }
        if (loss.joinable()) loss.join();
        for (auto &t : worker_threads) t.join();
        fence.join(); cancel.join();

        {
            std::lock_guard<std::mutex> lock(m);
            for (auto h : handles) {
                if (valid_locked(h) && !release_locked(h)) result.violations++;
            }
            if (terminal != result.submitted) result.violations++;
            if (result.completed + result.cancelled + result.lost != result.submitted) result.violations++;
            if (result.max_queue > queue_cap) result.violations++;
            for (auto &r : resources) if (r.alive || r.refs != 0) result.leaked_resources++;
            if (result.leaked_resources != 0) result.violations++;
            for (auto h : handles) if (valid_locked(h)) result.stale_accepts++;
            if (result.stale_accepts != 0) result.violations++;
            for (uint32_t i = 0; i < resources.size(); ++i) {
                auto &r = resources[i];
                r.alive = true; r.refs = 1;
                Handle fresh{i, r.generation};
                if (fresh.generation == handles[i].generation) result.violations++;
                release_locked(fresh);
            }
        }
        shutdown = true;
        return result;
    }
};

int main(int argc, char **argv) {
    uint64_t seed = argc > 1 ? std::strtoull(argv[1], nullptr, 10) : 1;
    uint32_t workers = argc > 2 ? static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 10)) : 4;
    uint32_t producers = argc > 3 ? static_cast<uint32_t>(std::strtoul(argv[3], nullptr, 10)) : 4;
    uint32_t ops = argc > 4 ? static_cast<uint32_t>(std::strtoul(argv[4], nullptr, 10)) : 400;
    uint32_t qcap = argc > 5 ? static_cast<uint32_t>(std::strtoul(argv[5], nullptr, 10)) : 16;
    bool loss = argc > 6 ? std::strtoul(argv[6], nullptr, 10) != 0 : false;
    Kernel k(qcap);
    auto start = std::chrono::steady_clock::now();
    Result r = k.run_case(seed, workers, producers, ops, loss);
    double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    std::cout << "RESULT language=cpp seed=" << seed << " workers=" << workers << " producers=" << producers
              << " ops=" << ops << " loss=" << (loss ? 1 : 0) << " seconds=" << seconds
              << " submitted=" << r.submitted << " completed=" << r.completed << " cancelled=" << r.cancelled
              << " lost=" << r.lost << " backpressure=" << r.backpressure_waits << " max_queue=" << r.max_queue
              << " retain=" << r.retain_ops << " release=" << r.release_ops << " stale_accepts=" << r.stale_accepts
              << " leaked=" << r.leaked_resources << " violations=" << r.violations << "\n";
    return r.violations == 0 ? 0 : 2;
}
