#ifndef AEROSIM_UAV_SIMULATOR_H
#define AEROSIM_UAV_SIMULATOR_H

#include "Actuator.h"
#include "ActuatorFaultConfig.h"
#include "UAVState.h"

class UAVSimulator {
public:
    static constexpr double time_step = 0.01; // Fixed 100 Hz simulation step

    explicit UAVSimulator(const ActuatorConfig& actuator_config = {});

    // Advance the state by one fixed simulation step.
    void step();

    // Read the current state without changing it.
    const UAVState& state() const;

    // Set the requested actuator position; the actuator clamps it to its limits.
    void set_actuator_command(double position);
    const ActuatorState& actuator_state() const;

    // Configure deterministic fault injection using simulation time.
    void configure_actuator_fault(const ActuatorFaultConfig& config);
    bool actuator_fault_active() const;

private:
    UAVState state_;
    Actuator actuator_;
    ActuatorFaultConfig actuator_fault_config_;
    bool actuator_fault_active_;
};

#endif // AEROSIM_UAV_SIMULATOR_H
