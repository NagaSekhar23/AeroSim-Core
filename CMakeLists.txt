cmake_minimum_required(VERSION 3.16)
project(AeroSimCore LANGUAGES CXX)

function(aerosim_enable_warnings target)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endfunction()

add_library(aerosim_core
    src/UAVSimulator.cpp
    src/Actuator.cpp
)
target_include_directories(aerosim_core PUBLIC include)
target_compile_features(aerosim_core PUBLIC cxx_std_17)
aerosim_enable_warnings(aerosim_core)

add_executable(aerosim src/main.cpp)
target_link_libraries(aerosim PRIVATE aerosim_core)
aerosim_enable_warnings(aerosim)

enable_testing()

add_executable(aerosim_tests src/UAVSimulatorTests.cpp)
target_link_libraries(aerosim_tests PRIVATE aerosim_core)
aerosim_enable_warnings(aerosim_tests)

add_test(NAME initial_state COMMAND aerosim_tests initial_state)
add_test(NAME forward_movement COMMAND aerosim_tests forward_movement)
add_test(NAME fixed_altitude_and_y COMMAND aerosim_tests fixed_altitude_and_y)
add_test(NAME simulation_time_step COMMAND aerosim_tests simulation_time_step)
add_test(NAME actuator_position_limits COMMAND aerosim_tests actuator_position_limits)
add_test(NAME actuator_rate_limit COMMAND aerosim_tests actuator_rate_limit)
add_test(NAME actuator_command_tracking COMMAND aerosim_tests actuator_command_tracking)
add_test(NAME invalid_actuator_config COMMAND aerosim_tests invalid_actuator_config)
add_test(NAME non_finite_actuator_commands COMMAND aerosim_tests non_finite_actuator_commands)
add_test(NAME invalid_actuator_time_steps COMMAND aerosim_tests invalid_actuator_time_steps)
add_test(NAME stuck_actuator_invalid_time_step
         COMMAND aerosim_tests stuck_actuator_invalid_time_step)
add_test(NAME commands_at_actuator_limits COMMAND aerosim_tests commands_at_actuator_limits)
add_test(NAME actuator_fault_activation_time COMMAND aerosim_tests actuator_fault_activation_time)
add_test(NAME stuck_actuator COMMAND aerosim_tests stuck_actuator)

add_executable(aerosim_timing
    src/TimingHarness.cpp
    src/TimingStatistics.cpp
)
target_link_libraries(aerosim_timing PRIVATE aerosim_core)
aerosim_enable_warnings(aerosim_timing)

add_executable(aerosim_compute_benchmark src/ComputeBenchmark.cpp)
target_link_libraries(aerosim_compute_benchmark PRIVATE aerosim_core)
target_compile_definitions(aerosim_compute_benchmark PRIVATE
    AEROSIM_COMPILER_ID=\"${CMAKE_CXX_COMPILER_ID}\"
    AEROSIM_COMPILER_VERSION=\"${CMAKE_CXX_COMPILER_VERSION}\"
    AEROSIM_BUILD_CONFIGURATION=\"$<CONFIG>\"
)
aerosim_enable_warnings(aerosim_compute_benchmark)

add_executable(aerosim_timing_tests
    src/TimingStatisticsTests.cpp
    src/TimingStatistics.cpp
)
target_include_directories(aerosim_timing_tests PRIVATE include)
target_compile_features(aerosim_timing_tests PRIVATE cxx_std_17)
aerosim_enable_warnings(aerosim_timing_tests)

add_test(NAME timing_statistics COMMAND aerosim_timing_tests)

add_executable(aerosim_experiments
    src/ExperimentRunner.cpp
    src/ExclusiveFile.cpp
    src/TelemetryWriter.cpp
)
target_link_libraries(aerosim_experiments PRIVATE aerosim_core)
aerosim_enable_warnings(aerosim_experiments)

add_executable(aerosim_telemetry_tests
    src/TelemetryTests.cpp
    src/ExclusiveFile.cpp
    src/TelemetryWriter.cpp
)
target_link_libraries(aerosim_telemetry_tests PRIVATE aerosim_core)
aerosim_enable_warnings(aerosim_telemetry_tests)

add_test(NAME telemetry_schema_and_values
         COMMAND aerosim_telemetry_tests schema_and_values)
add_test(NAME telemetry_numeric_validation
         COMMAND aerosim_telemetry_tests numeric_validation)
add_test(NAME telemetry_fault_records
         COMMAND aerosim_telemetry_tests fault_records)
add_test(NAME telemetry_output_handling
         COMMAND aerosim_telemetry_tests output_handling)

add_test(NAME experiment_output_completion
    COMMAND ${CMAKE_COMMAND}
        "-DAEROSIM_EXPERIMENTS=$<TARGET_FILE:aerosim_experiments>"
        "-DTEST_ROOT=${CMAKE_CURRENT_BINARY_DIR}/experiment-output-test"
        -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ExperimentOutputTests.cmake
)
