#include "UAVSimulator.h"

#include <iomanip>
#include <iostream>

int main() {
    constexpr double run_time = 2.0;
    constexpr int steps_per_sample = 50; // Print every 0.5 seconds
    constexpr int total_steps = static_cast<int>(run_time / UAVSimulator::time_step);

    UAVSimulator simulator;

    std::cout << "Simple fixed-wing UAV kinematic simulation\n";
    std::cout << "(constant speed; not a realistic aerodynamics model)\n\n";
    std::cout << " time (s)   X (m)   Y (m)   altitude (m)   speed (m/s)\n";

    for (int step = 0; step <= total_steps; ++step) {
        if (step % steps_per_sample == 0) {
            const UAVState& state = simulator.state();
            std::cout << std::fixed << std::setprecision(2)
                      << std::setw(8) << state.time << "  "
                      << std::setw(6) << state.x << "  "
                      << std::setw(6) << state.y << "  "
                      << std::setw(12) << state.altitude << "  "
                      << std::setw(11) << state.forward_speed << '\n';
        }

        if (step < total_steps) {
            simulator.step();
        }
    }

    return 0;
}
