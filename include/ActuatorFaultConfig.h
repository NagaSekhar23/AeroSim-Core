#ifndef AEROSIM_ACTUATOR_FAULT_CONFIG_H
#define AEROSIM_ACTUATOR_FAULT_CONFIG_H

// Deterministic fault setup, kept separate from the actuator update logic.
// The fault activates at the first simulation step whose time reaches this value.
struct ActuatorFaultConfig {
    bool stuck_enabled = false;
    double activation_time = 0.0; // Simulation seconds, not wall-clock seconds
};

#endif // AEROSIM_ACTUATOR_FAULT_CONFIG_H
