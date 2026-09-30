#include "TimingStatistics.h"
#include "UAVSimulator.h"

#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using Nanoseconds = std::chrono::nanoseconds;

constexpr double default_run_duration_seconds = 0.25;

double parse_run_duration(int argc, char* argv[]) {
    if (argc == 1) {
        return default_run_duration_seconds;
    }
    if (argc != 2) {
        throw std::invalid_argument("usage: aerosim_timing [run_duration_seconds]");
    }

    std::size_t parsed_characters = 0;
    const double duration = std::stod(argv[1], &parsed_characters);
    if (parsed_characters != std::string(argv[1]).size()
        || !std::isfinite(duration) || duration <= 0.0) {
        throw std::invalid_argument("run duration must be a positive number of seconds");
    }
    return duration;
}

double to_milliseconds(double nanoseconds) {
    return nanoseconds / 1'000'000.0;
}

double to_milliseconds(Nanoseconds nanoseconds) {
    return std::chrono::duration<double, std::milli>(nanoseconds).count();
}
} // namespace

int main(int argc, char* argv[]) {
    try {
        const double run_duration_seconds = parse_run_duration(argc, argv);
        const auto period = std::chrono::duration_cast<Clock::duration>(
            std::chrono::duration<double>(UAVSimulator::time_step));
        const auto run_duration = std::chrono::duration_cast<Clock::duration>(
            std::chrono::duration<double>(run_duration_seconds));

        UAVSimulator simulator;
        std::vector<TimingSample> samples;
        const Clock::time_point start = Clock::now();
        const Clock::time_point finish = start + run_duration;
        Clock::time_point deadline = start + period;

        // Every deadline is based on the previous intended deadline, not on
        // when the preceding step finished, so ordinary delays do not accumulate.
        while (deadline <= finish) {
            std::this_thread::sleep_until(deadline);
            const Clock::time_point step_start = Clock::now();
            const auto signed_schedule_offset =
                std::chrono::duration_cast<Nanoseconds>(step_start - deadline);
            const auto schedule_error = signed_schedule_offset >= Nanoseconds::zero()
                ? signed_schedule_offset
                : -signed_schedule_offset;

            const Clock::time_point step_end_before = Clock::now();
            simulator.step();
            const Clock::time_point step_end = Clock::now();
            const auto execution_time = std::chrono::duration_cast<Nanoseconds>(
                step_end - step_end_before);

            const SchedulingClassification classification = classify_scheduling_offset(
                signed_schedule_offset,
                std::chrono::duration_cast<Nanoseconds>(period));
            samples.push_back({
                execution_time,
                schedule_error,
                classification.late_start,
                classification.missed_deadline
            });

            deadline += period;
        }

        const TimingStatistics statistics = calculate_timing_statistics(samples);
        // Six decimal places in milliseconds make very short step work visible.
        std::cout << std::fixed << std::setprecision(6);
        std::cout << "Target period: " << UAVSimulator::time_step * 1000.0 << " ms\n";
        std::cout << "Requested wall-clock duration: " << run_duration_seconds << " s\n";
        std::cout << "Simulation time: " << simulator.state().time << " s\n";
        std::cout << "Simulation steps: " << samples.size() << '\n';
        std::cout << "Step execution time (ms): average="
                  << to_milliseconds(statistics.average_step_execution_time_ns)
                  << ", minimum=" << to_milliseconds(statistics.minimum_step_execution_time)
                  << ", maximum=" << to_milliseconds(statistics.maximum_step_execution_time)
                  << '\n';
        std::cout << "Absolute scheduling error (ms): average="
                  << to_milliseconds(statistics.average_absolute_scheduling_error_ns)
                  << ", maximum="
                  << to_milliseconds(statistics.maximum_absolute_scheduling_error)
                  << '\n';
        std::cout << "Late step starts: " << statistics.late_starts
                  << " (step start was after its deadline)\n";
        std::cout << "Full-period-late steps: " << statistics.missed_deadlines
                  << " (step start was at least one full period after its deadline)\n";
        std::cout << "Scheduling uses the monotonic steady_clock; operating-system"
                     " scheduling is not hard real-time.\n";
    } catch (const std::exception& error) {
        std::cerr << "Timing harness error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
