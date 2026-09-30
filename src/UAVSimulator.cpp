#include "UAVSimulator.h"

#include <cmath>
#include <stdexcept>

UAVSimulator::UAVSimulator(const ActuatorConfig& actuator_config)
    // Keep the existing initial altitude coordinate at 100 m. Its datum is
    // unspecified; this simple model holds the coordinate constant each step.
    : state_{0.0, 0.0, 0.0, 100.0, 20.0},
      actuator_(actuator_config),
      actuator_fault_config_{},
      actuator_fault_active_(false) {
}

void UAVSimulator::step() {
    // Simple kinematic model: move straight at constant forward speed.
    // Y and altitude stay fixed. This does not model aerodynamic forces,
    // turning, wind, or aircraft control. The separate software actuator
    // tracks its command unless the configured simulation-time fault is active.
    state_.x += state_.forward_speed * time_step;
    if (!actuator_fault_active_) {
        actuator_.update(time_step);
    }
    state_.time += time_step;

    // Time is advanced in fixed simulation increments. If a configured time
    // falls between increments, activate at the first step at or beyond it.
    if (actuator_fault_config_.stuck_enabled
        && !actuator_fault_active_
        && state_.time >= actuator_fault_config_.activation_time) {
        actuator_fault_active_ = true;
        actuator_.set_stuck(true);
    }
}

const UAVState& UAVSimulator::state() const {
    return state_;
}

void UAVSimulator::set_actuator_command(double position) {
    actuator_.set_command(position);
}

const ActuatorState& UAVSimulator::actuator_state() const {
    return actuator_.state();
}

void UAVSimulator::configure_actuator_fault(const ActuatorFaultConfig& config) {
    if (!std::isfinite(config.activation_time) || config.activation_time < 0.0) {
        throw std::invalid_argument("actuator fault time must be finite and non-negative");
    }

    actuator_fault_config_ = config;
    actuator_fault_active_ = false;
    actuator_.set_stuck(false);

    // A fault configured at or before the current time activates immediately.
    if (config.stuck_enabled && state_.time >= config.activation_time) {
        actuator_fault_active_ = true;
        actuator_.set_stuck(true);
    }
}

bool UAVSimulator::actuator_fault_active() const {
    return actuator_fault_active_;
}
