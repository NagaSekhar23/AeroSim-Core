#include "UAVSimulator.h"

#include <charconv>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <system_error>

#ifndef AEROSIM_COMPILER_ID
#define AEROSIM_COMPILER_ID "unknown"
#endif

#ifndef AEROSIM_COMPILER_VERSION
#define AEROSIM_COMPILER_VERSION "unknown"
#endif

#ifndef AEROSIM_BUILD_CONFIGURATION
#define AEROSIM_BUILD_CONFIGURATION "unspecified"
#endif

namespace {
using Clock = std::chrono::steady_clock;
constexpr std::uint64_t warmup_step_count = 10'000;

std::uint64_t parse_step_count(const char* text) {
    std::uint64_t step_count = 0;
    const std::string value(text);
    const auto result = std::from_chars(value.data(), value.data() + value.size(), step_count);
    if (result.ec != std::errc{} || result.ptr != value.data() + value.size()
        || step_count == 0) {
        throw std::invalid_argument("step count must be a positive integer");
    }
    return step_count;
}
} // namespace

int main(int argc, char* argv[]) {
    if (argc != 2) {
        std::cerr << "usage: aerosim_compute_benchmark STEP_COUNT\n";
        return 2;
    }

    try {
        const std::uint64_t step_count = parse_step_count(argv[1]);

        // Exercise the same code path before measurement, using a separate
        // simulator so the measured run still starts from the default state.
        UAVSimulator warmup_simulator;
        warmup_simulator.set_actuator_command(0.8);
        for (std::uint64_t step = 0; step < warmup_step_count; ++step) {
            warmup_simulator.step();
        }
        const double warmup_final_x = warmup_simulator.state().x;

        // Identical measured setup is performed before timing in every run.
        UAVSimulator simulator;
        simulator.set_actuator_command(0.8);

        const Clock::time_point start = Clock::now();
        for (std::uint64_t step = 0; step < step_count; ++step) {
            simulator.step();
        }
        const Clock::time_point finish = Clock::now();
        const auto elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
            finish - start).count();
        const double elapsed_seconds = std::chrono::duration<double>(finish - start).count();
        const double nanoseconds_per_step =
            static_cast<double>(elapsed_ns) / static_cast<double>(step_count);
        const double steps_per_second = static_cast<double>(step_count) / elapsed_seconds;

        // Final state is emitted so each simulation result remains observable.
        std::cout << std::setprecision(17)
                  << "{\"step_count\":" << step_count
                  << ",\"warmup_step_count\":" << warmup_step_count
                  << ",\"warmup_final_position_x_m\":" << warmup_final_x
                  << ",\"elapsed_nanoseconds\":" << elapsed_ns
                  << ",\"nanoseconds_per_step\":" << nanoseconds_per_step
                  << ",\"steps_per_second\":" << steps_per_second
                  << ",\"final_simulation_time_s\":" << simulator.state().time
                  << ",\"final_position_x_m\":" << simulator.state().x
                  << ",\"final_actuator_position\":"
                  << simulator.actuator_state().actual_position
                  << ",\"compiler_id\":\"" << AEROSIM_COMPILER_ID << "\""
                  << ",\"compiler_version\":\"" << AEROSIM_COMPILER_VERSION << "\""
                  << ",\"build_configuration\":\""
                  << AEROSIM_BUILD_CONFIGURATION << "\"}\n";
    } catch (const std::exception& error) {
        std::cerr << "Compute benchmark error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
