#include "Actuator.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace {
ActuatorConfig validate_config(const ActuatorConfig& config) {
    if (!std::isfinite(config.minimum_position)
        || !std::isfinite(config.maximum_position)
        || config.minimum_position > config.maximum_position) {
        throw std::invalid_argument("actuator position bounds must be finite and ordered");
    }
    if (!std::isfinite(config.rate_limit) || config.rate_limit < 0.0) {
        throw std::invalid_argument("actuator rate limit must be finite and non-negative");
    }
    return config;
}
} // namespace

Actuator::Actuator(const ActuatorConfig& config)
    : config_(validate_config(config)),
      state_{std::clamp(0.0, config.minimum_position, config.maximum_position),
             std::clamp(0.0, config.minimum_position, config.maximum_position)},
      stuck_(false) {
}

void Actuator::set_command(double position) {
    if (!std::isfinite(position)) {
        throw std::invalid_argument("actuator command must be finite");
    }
    state_.commanded_position =
        std::clamp(position, config_.minimum_position, config_.maximum_position);
}

void Actuator::update(double time_step) {
    if (!std::isfinite(time_step) || time_step < 0.0) {
        throw std::invalid_argument("actuator time step must be finite and non-negative");
    }
    if (stuck_) {
        return;
    }

    const double maximum_change = config_.rate_limit * time_step;
    const double position_error = state_.commanded_position - state_.actual_position;
    const double limited_change = std::clamp(position_error, -maximum_change, maximum_change);
    state_.actual_position = std::clamp(state_.actual_position + limited_change,
                                        config_.minimum_position,
                                        config_.maximum_position);
}

void Actuator::set_stuck(bool stuck) {
    stuck_ = stuck;
}

const ActuatorState& Actuator::state() const {
    return state_;
}
