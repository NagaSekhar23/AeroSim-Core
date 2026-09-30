#include "UAVSimulator.h"

#include <cmath>
#include <initializer_list>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {
constexpr double tolerance = 1e-9;

bool nearly_equal(double actual, double expected) {
    return std::abs(actual - expected) <= tolerance;
}

bool check_value(const char* name, double actual, double expected) {
    if (nearly_equal(actual, expected)) {
        return true;
    }

    std::cerr << name << " was " << actual << ", expected " << expected << '\n';
    return false;
}

bool test_initial_state() {
    const UAVSimulator simulator;
    const UAVState& state = simulator.state();

    return check_value("X", state.x, 0.0)
        && check_value("Y", state.y, 0.0)
        && check_value("initial altitude coordinate", state.altitude, 100.0)
        && check_value("forward speed", state.forward_speed, 20.0);
}

bool test_forward_movement() {
    UAVSimulator simulator;
    constexpr int steps_for_two_seconds = 200;
    for (int step = 0; step < steps_for_two_seconds; ++step) {
        simulator.step();
    }

    return check_value("X after 2 seconds", simulator.state().x, 40.0);
}

bool test_fixed_altitude_and_y() {
    UAVSimulator simulator;
    constexpr int steps_for_two_seconds = 200;
    for (int step = 0; step < steps_for_two_seconds; ++step) {
        simulator.step();
    }

    const UAVState& state = simulator.state();
    return check_value("Y after 2 seconds", state.y, 0.0)
        && check_value("altitude coordinate after 2 seconds", state.altitude, 100.0);
}

bool test_simulation_time_step() {
    UAVSimulator simulator;
    simulator.step();

    return check_value("time after one step", simulator.state().time,
                       UAVSimulator::time_step);
}

bool test_actuator_position_limits() {
    const ActuatorConfig config{-0.5, 0.5, 100.0};
    UAVSimulator simulator(config);
    simulator.set_actuator_command(2.0);
    simulator.step();

    bool passed = check_value("clamped actuator command",
                              simulator.actuator_state().commanded_position, 0.5)
        && check_value("actuator at upper limit",
                       simulator.actuator_state().actual_position, 0.5);
    simulator.set_actuator_command(-2.0);
    return passed && check_value("actuator command at lower limit",
                                 simulator.actuator_state().commanded_position, -0.5);
}

bool test_actuator_rate_limit() {
    const ActuatorConfig config{-10.0, 10.0, 2.0};
    UAVSimulator simulator(config);
    simulator.set_actuator_command(1.0);
    simulator.step();

    return check_value("rate-limited actuator position",
                       simulator.actuator_state().actual_position, 0.02);
}

bool test_actuator_normal_command_tracking() {
    const ActuatorConfig config{-1.0, 1.0, 100.0};
    UAVSimulator simulator(config);
    simulator.set_actuator_command(0.5);
    simulator.step();

    return check_value("tracked actuator command",
                       simulator.actuator_state().actual_position, 0.5);
}

bool rejects_invalid_config(const ActuatorConfig& config) {
    try {
        Actuator actuator(config);
    } catch (const std::invalid_argument&) {
        return true;
    }
    return false;
}

bool test_invalid_actuator_config() {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double infinity = std::numeric_limits<double>::infinity();
    return rejects_invalid_config({nan, 1.0, 2.0})
        && rejects_invalid_config({-1.0, infinity, 2.0})
        && rejects_invalid_config({-infinity, 1.0, 2.0})
        && rejects_invalid_config({-1.0, nan, 2.0})
        && rejects_invalid_config({-1.0, 1.0, nan})
        && rejects_invalid_config({-1.0, 1.0, infinity})
        && rejects_invalid_config({-1.0, 1.0, -infinity})
        && rejects_invalid_config({1.0, -1.0, 2.0})
        && rejects_invalid_config({-1.0, 1.0, -0.1});
}

bool test_non_finite_actuator_commands() {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double infinity = std::numeric_limits<double>::infinity();
    UAVSimulator simulator;
    for (const double command : {nan, infinity, -infinity}) {
        bool rejected = false;
        try {
            simulator.set_actuator_command(command);
        } catch (const std::invalid_argument&) {
            rejected = true;
        }
        if (!rejected) {
            std::cerr << "Non-finite actuator command was accepted\n";
            return false;
        }
    }
    return check_value("command remains unchanged after rejected inputs",
                       simulator.actuator_state().commanded_position, 0.0);
}

bool test_invalid_actuator_time_steps() {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double infinity = std::numeric_limits<double>::infinity();
    Actuator actuator;
    for (const double time_step : {-0.01, nan, infinity, -infinity}) {
        bool rejected = false;
        try {
            actuator.update(time_step);
        } catch (const std::invalid_argument&) {
            rejected = true;
        }
        if (!rejected) {
            std::cerr << "Invalid actuator time step was accepted\n";
            return false;
        }
    }
    actuator.update(0.0); // Zero is valid: it advances no actuator position.
    return check_value("position after a zero time step",
                       actuator.state().actual_position, 0.0);
}

bool test_stuck_actuator_rejects_invalid_time_step() {
    Actuator actuator;
    actuator.set_stuck(true);
    bool rejected = false;
    try {
        actuator.update(std::numeric_limits<double>::quiet_NaN());
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    if (!rejected) {
        std::cerr << "Stuck actuator accepted an invalid time step\n";
        return false;
    }

    actuator.set_command(0.5);
    actuator.update(0.01);
    return check_value("stuck actuator remains frozen after valid update",
                       actuator.state().actual_position, 0.0);
}

bool test_commands_at_actuator_limits() {
    const ActuatorConfig config{-0.5, 0.5, 100.0};
    Actuator actuator(config);
    actuator.set_command(config.maximum_position);
    actuator.update(0.01);
    const bool reached_maximum = check_value("command at maximum limit",
        actuator.state().actual_position, config.maximum_position);
    actuator.set_command(config.minimum_position);
    actuator.update(0.01);
    return reached_maximum
        && check_value("command at minimum limit",
                       actuator.state().actual_position, config.minimum_position);
}

bool test_actuator_fault_activation_time() {
    const ActuatorConfig actuator_config{-1.0, 1.0, 10.0};
    UAVSimulator simulator(actuator_config);
    simulator.set_actuator_command(1.0);
    simulator.configure_actuator_fault({true, 0.02});

    simulator.step();
    if (simulator.actuator_fault_active()
        || !check_value("time before actuator fault", simulator.state().time, 0.01)) {
        std::cerr << "Actuator fault activated before its configured simulation time\n";
        return false;
    }

    simulator.step();
    return simulator.actuator_fault_active()
        && check_value("time at actuator fault", simulator.state().time, 0.02);
}

bool test_stuck_actuator_ignores_later_commands() {
    const ActuatorConfig actuator_config{-1.0, 1.0, 10.0};
    UAVSimulator simulator(actuator_config);
    simulator.set_actuator_command(1.0);
    simulator.step();
    simulator.configure_actuator_fault({true, simulator.state().time});
    const double frozen_position = simulator.actuator_state().actual_position;

    simulator.set_actuator_command(-1.0);
    for (int step = 0; step < 5; ++step) {
        simulator.step();
    }

    return simulator.actuator_fault_active()
        && check_value("stuck actuator position", simulator.actuator_state().actual_position,
                       frozen_position)
        && check_value("command still changes while stuck",
                       simulator.actuator_state().commanded_position, -1.0);
}
} // namespace

int main(int argc, char* argv[]) {
    if (argc != 2) {
        std::cerr << "Provide one test name.\n";
        return 2;
    }

    const std::string test_name = argv[1];
    bool passed = false;
    if (test_name == "initial_state") {
        passed = test_initial_state();
    } else if (test_name == "forward_movement") {
        passed = test_forward_movement();
    } else if (test_name == "fixed_altitude_and_y") {
        passed = test_fixed_altitude_and_y();
    } else if (test_name == "simulation_time_step") {
        passed = test_simulation_time_step();
    } else if (test_name == "actuator_position_limits") {
        passed = test_actuator_position_limits();
    } else if (test_name == "actuator_rate_limit") {
        passed = test_actuator_rate_limit();
    } else if (test_name == "actuator_command_tracking") {
        passed = test_actuator_normal_command_tracking();
    } else if (test_name == "invalid_actuator_config") {
        passed = test_invalid_actuator_config();
    } else if (test_name == "non_finite_actuator_commands") {
        passed = test_non_finite_actuator_commands();
    } else if (test_name == "invalid_actuator_time_steps") {
        passed = test_invalid_actuator_time_steps();
    } else if (test_name == "stuck_actuator_invalid_time_step") {
        passed = test_stuck_actuator_rejects_invalid_time_step();
    } else if (test_name == "commands_at_actuator_limits") {
        passed = test_commands_at_actuator_limits();
    } else if (test_name == "actuator_fault_activation_time") {
        passed = test_actuator_fault_activation_time();
    } else if (test_name == "stuck_actuator") {
        passed = test_stuck_actuator_ignores_later_commands();
    } else {
        std::cerr << "Unknown test: " << test_name << '\n';
        return 2;
    }

    if (passed) {
        std::cout << "Passed: " << test_name << '\n';
        return 0;
    }
    return 1;
}
