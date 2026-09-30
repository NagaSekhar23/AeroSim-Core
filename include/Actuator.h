#ifndef AEROSIM_ACTUATOR_H
#define AEROSIM_ACTUATOR_H

struct ActuatorConfig {
    double minimum_position = -1.0;
    double maximum_position = 1.0;
    double rate_limit = 2.0; // Maximum position change per simulation second
};

struct ActuatorState {
    double commanded_position;
    double actual_position;
};

// A software actuator with clamped commands and a per-second rate limit.
// This simple model has no backlash, inertia, or electrical/motor dynamics.
class Actuator {
public:
    explicit Actuator(const ActuatorConfig& config = {});

    void set_command(double position);
    void update(double time_step);
    void set_stuck(bool stuck);

    const ActuatorState& state() const;

private:
    ActuatorConfig config_;
    ActuatorState state_;
    bool stuck_;
};

#endif // AEROSIM_ACTUATOR_H
