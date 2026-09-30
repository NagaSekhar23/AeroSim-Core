#include "TelemetryWriter.h"
#include "UAVSimulator.h"
#include "ExclusiveFile.h"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <iomanip>
#include <locale>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {
constexpr double experiment_duration_seconds = 2.0;
constexpr double command_change_time_seconds = 0.5;
constexpr double initial_actuator_command = 0.8;
constexpr double later_actuator_command = -0.4;
constexpr int experiment_steps = static_cast<int>(
    experiment_duration_seconds / UAVSimulator::time_step);
constexpr const char* completion_filename = "experiment_complete.txt";

struct Options {
    std::filesystem::path output_directory = "telemetry/experiment";
    double fault_time_seconds = 0.75;
};

Options parse_options(int argc, char* argv[]) {
    Options options;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--output-dir" && index + 1 < argc) {
            options.output_directory = argv[++index];
        } else if (argument == "--fault-time" && index + 1 < argc) {
            const std::string value = argv[++index];
            std::size_t parsed_characters = 0;
            options.fault_time_seconds = std::stod(value, &parsed_characters);
            if (parsed_characters != value.size()) {
                throw std::invalid_argument("fault time must be a number of seconds");
            }
        } else {
            throw std::invalid_argument(
                "usage: aerosim_experiments [--output-dir PATH] [--fault-time SECONDS]");
        }
    }

    if (!std::isfinite(options.fault_time_seconds)
        || options.fault_time_seconds < 0.0
        || options.fault_time_seconds > experiment_duration_seconds) {
        throw std::invalid_argument("fault time must be between 0 and 2 seconds");
    }
    return options;
}

void run_scenario(const std::filesystem::path& output_path, bool inject_fault,
                  double fault_time_seconds) {
    // These settings are identical for both scenarios. The only intentional
    // difference is whether this fault configuration is enabled.
    UAVSimulator simulator;
    simulator.set_actuator_command(initial_actuator_command);
    simulator.configure_actuator_fault({inject_fault, fault_time_seconds});

    TelemetryWriter telemetry(output_path.string());
    for (int step = 0; step < experiment_steps; ++step) {
        if (simulator.state().time >= command_change_time_seconds) {
            simulator.set_actuator_command(later_actuator_command);
        }
        simulator.step();
        telemetry.write(simulator);
    }
    telemetry.close();
}
} // namespace

int main(int argc, char* argv[]) {
    try {
        const Options options = parse_options(argc, argv);
        std::filesystem::create_directories(options.output_directory);
        const std::filesystem::path nominal_path = options.output_directory / "nominal.csv";
        const std::filesystem::path fault_path = options.output_directory / "fault_injected.csv";
        const std::filesystem::path completion_path =
            options.output_directory / completion_filename;

        // Check both destinations up front so an existing result is not
        // silently replaced and a partial pair is less likely to be produced.
        if (std::filesystem::exists(nominal_path) || std::filesystem::exists(fault_path)
            || std::filesystem::exists(completion_path)) {
            throw std::runtime_error(
                "experiment output already exists; choose a fresh output directory");
        }

        run_scenario(nominal_path, false, options.fault_time_seconds);
        run_scenario(fault_path, true, options.fault_time_seconds);

        // This record is created only after both CSV writers have closed
        // successfully. Consumers must verify its complete contents; an
        // absent or truncated marker means the experiment is incomplete.
        std::ostringstream completion;
        completion.imbue(std::locale::classic());
        completion << "AeroSim-Core experiment complete\n"
                   << "nominal_rows=" << experiment_steps << '\n'
                   << "fault_injected_rows=" << experiment_steps << '\n'
                   << "fault_activation_time_s=" << std::setprecision(17)
                   << options.fault_time_seconds << '\n';
        ExclusiveFile marker(completion_path.string());
        marker.write(completion.str());
        marker.close();

        std::cout << "Wrote nominal telemetry: " << nominal_path.string() << '\n';
        std::cout << "Wrote fault-injected telemetry: " << fault_path.string() << '\n';
        std::cout << "Wrote completion marker: " << completion_path.string() << '\n';
        std::cout << "Fault activation time: " << options.fault_time_seconds
                  << " simulation seconds\n";
    } catch (const std::exception& error) {
        std::cerr << "Experiment runner error: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
