#include "TelemetryWriter.h"
#include "UAVSimulator.h"

#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <sstream>
#include <string>
#include <vector>

namespace {
namespace fs = std::filesystem;

class TemporaryDirectory {
public:
    TemporaryDirectory() {
        const auto unique_value = std::chrono::steady_clock::now().time_since_epoch().count();
        path_ = fs::temp_directory_path()
            / ("aerosim_telemetry_test_" + std::to_string(unique_value));
        fs::create_directories(path_);
    }

    ~TemporaryDirectory() {
        std::error_code error;
        fs::remove_all(path_, error);
    }

    const fs::path& path() const { return path_; }

private:
    fs::path path_;
};

std::vector<std::string> split_csv_row(const std::string& line) {
    std::vector<std::string> fields;
    std::stringstream row(line);
    std::string field;
    while (std::getline(row, field, ',')) {
        fields.push_back(field);
    }
    return fields;
}

std::vector<std::vector<std::string>> read_csv(const fs::path& path) {
    std::ifstream input(path);
    std::vector<std::vector<std::string>> rows;
    std::string line;
    while (std::getline(input, line)) {
        rows.push_back(split_csv_row(line));
    }
    return rows;
}

bool parse_finite_number(const std::string& text, double& value) {
    try {
        std::size_t parsed_characters = 0;
        const double parsed_value = std::stod(text, &parsed_characters);
        if (parsed_characters != text.size() || !std::isfinite(parsed_value)) {
            return false;
        }
        value = parsed_value;
        return true;
    } catch (const std::exception&) {
        return false;
    }
}

bool check_number(const char* name, const std::string& text, double expected) {
    double actual = 0.0;
    if (parse_finite_number(text, actual)
        && std::abs(actual - expected) <= 1e-12) {
        return true;
    }
    std::cerr << name << " was not the expected finite number: " << text
              << " (expected " << expected << ")\n";
    return false;
}

bool test_numeric_field_validation() {
    double parsed_value = 0.0;
    if (!parse_finite_number("0.5", parsed_value)
        || std::abs(parsed_value - 0.5) > 1e-12) {
        std::cerr << "Valid numeric field was rejected\n";
        return false;
    }

    for (const std::string& invalid_value : {
             "0.5junk", "nan", "inf", "-inf"}) {
        if (parse_finite_number(invalid_value, parsed_value)) {
            std::cerr << "Invalid numeric field was accepted: " << invalid_value << '\n';
            return false;
        }
    }
    return true;
}

bool test_schema_row_count_and_numeric_values() {
    TemporaryDirectory directory;
    const fs::path path = directory.path() / "numeric.csv";
    UAVSimulator simulator({-1.0, 1.0, 100.0});
    simulator.set_actuator_command(0.5);
    {
        TelemetryWriter writer(path.string());
        simulator.step();
        writer.write(simulator);
        simulator.step();
        writer.write(simulator);
        writer.close();
    }

    const auto rows = read_csv(path);
    const std::vector<std::string> expected_header{
        "simulation_time_s", "position_x_m", "position_y_m", "altitude_m",
        "forward_speed_mps", "actuator_command", "actuator_position",
        "actuator_fault_active"
    };
    if (rows.size() != 3 || rows.front() != expected_header) {
        std::cerr << "CSV header or row count was incorrect\n";
        return false;
    }

    return rows[1].size() == 8 && rows[2].size() == 8
        && check_number("first time", rows[1][0], 0.01)
        && check_number("first X", rows[1][1], 0.2)
        && check_number("first Y", rows[1][2], 0.0)
        && check_number("first altitude", rows[1][3], 100.0)
        && check_number("first speed", rows[1][4], 20.0)
        && check_number("first command", rows[1][5], 0.5)
        && check_number("first actuator position", rows[1][6], 0.5)
        && rows[1][7] == "false"
        && check_number("second time", rows[2][0], 0.02)
        && check_number("second X", rows[2][1], 0.4);
}

bool test_fault_activation_records() {
    TemporaryDirectory directory;
    const fs::path path = directory.path() / "fault.csv";
    UAVSimulator simulator({-1.0, 1.0, 10.0});
    simulator.set_actuator_command(1.0);
    simulator.configure_actuator_fault({true, 0.02});
    {
        TelemetryWriter writer(path.string());
        for (int step = 0; step < 3; ++step) {
            simulator.step();
            writer.write(simulator);
        }
        writer.close();
    }

    const auto rows = read_csv(path);
    return rows.size() == 4
        && rows[1][7] == "false"
        && rows[2][7] == "true"
        && rows[3][7] == "true"
        && check_number("actuator position at activation", rows[2][6], 0.2)
        && check_number("stuck actuator position", rows[3][6], 0.2);
}

bool test_output_file_handling() {
    TemporaryDirectory directory;
    const fs::path existing_path = directory.path() / "keep.csv";
    {
        std::ofstream existing(existing_path);
        existing << "existing content\n";
    }

    bool refused_existing_file = false;
    try {
        TelemetryWriter writer(existing_path.string());
    } catch (const std::runtime_error&) {
        refused_existing_file = true;
    }

    std::ifstream preserved(existing_path);
    std::string preserved_line;
    std::getline(preserved, preserved_line);
    if (!refused_existing_file || preserved_line != "existing content") {
        std::cerr << "Existing output file was not safely preserved\n";
        return false;
    }

    bool refused_missing_parent = false;
    try {
        TelemetryWriter writer((directory.path() / "missing" / "file.csv").string());
    } catch (const std::runtime_error&) {
        refused_missing_parent = true;
    }
    return refused_missing_parent;
}
} // namespace

int main(int argc, char* argv[]) {
    if (argc != 2) {
        std::cerr << "Provide one telemetry test name.\n";
        return 2;
    }

    const std::string test_name = argv[1];
    bool passed = false;
    if (test_name == "schema_and_values") {
        passed = test_schema_row_count_and_numeric_values();
    } else if (test_name == "numeric_validation") {
        passed = test_numeric_field_validation();
    } else if (test_name == "fault_records") {
        passed = test_fault_activation_records();
    } else if (test_name == "output_handling") {
        passed = test_output_file_handling();
    } else {
        std::cerr << "Unknown telemetry test: " << test_name << '\n';
        return 2;
    }

    if (passed) {
        std::cout << "Passed: telemetry " << test_name << '\n';
        return 0;
    }
    return 1;
}
