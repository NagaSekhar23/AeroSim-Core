#include "TelemetryWriter.h"

#include "UAVSimulator.h"

#include <cmath>
#include <iomanip>
#include <locale>
#include <sstream>
#include <stdexcept>

TelemetryWriter::TelemetryWriter(const std::string& output_path) : output_(output_path) {
    // A fixed locale and enough precision keep output stable and parseable.
    output_.write("simulation_time_s,position_x_m,position_y_m,altitude_m,"
                  "forward_speed_mps,actuator_command,actuator_position,"
                  "actuator_fault_active\n");
}

void TelemetryWriter::write(const UAVSimulator& simulator) {
    const UAVState& state = simulator.state();
    const ActuatorState& actuator = simulator.actuator_state();
    if (!std::isfinite(state.time) || !std::isfinite(state.x)
        || !std::isfinite(state.y) || !std::isfinite(state.altitude)
        || !std::isfinite(state.forward_speed)
        || !std::isfinite(actuator.commanded_position)
        || !std::isfinite(actuator.actual_position)) {
        throw std::invalid_argument("telemetry numeric values must be finite");
    }

    std::ostringstream row;
    row.imbue(std::locale::classic());
    row << std::setprecision(17)
        << state.time << ','
        << state.x << ','
        << state.y << ','
        << state.altitude << ','
        << state.forward_speed << ','
        << actuator.commanded_position << ','
        << actuator.actual_position << ','
        << (simulator.actuator_fault_active() ? "true" : "false")
        << '\n';
    output_.write(row.str());
}

void TelemetryWriter::close() {
    output_.close();
}
