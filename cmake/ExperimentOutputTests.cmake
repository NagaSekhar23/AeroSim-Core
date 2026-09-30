if(NOT DEFINED AEROSIM_EXPERIMENTS OR NOT DEFINED TEST_ROOT)
    message(FATAL_ERROR "AEROSIM_EXPERIMENTS and TEST_ROOT are required")
endif()

# This test owns and recreates only its dedicated build-tree directory.
file(REMOVE_RECURSE "${TEST_ROOT}")
file(MAKE_DIRECTORY "${TEST_ROOT}")

set(success_dir "${TEST_ROOT}/successful-run")
execute_process(
    COMMAND "${AEROSIM_EXPERIMENTS}" --output-dir "${success_dir}" --fault-time 0.75
    RESULT_VARIABLE success_result
    OUTPUT_VARIABLE success_stdout
    ERROR_VARIABLE success_stderr
)
if(NOT success_result EQUAL 0)
    message(FATAL_ERROR "Experiment success case failed: ${success_stderr}")
endif()

foreach(filename IN ITEMS nominal.csv fault_injected.csv experiment_complete.txt)
    if(NOT EXISTS "${success_dir}/${filename}")
        message(FATAL_ERROR "Successful experiment is missing ${filename}")
    endif()
endforeach()

file(STRINGS "${success_dir}/nominal.csv" nominal_rows)
file(STRINGS "${success_dir}/fault_injected.csv" fault_rows)
list(LENGTH nominal_rows nominal_line_count)
list(LENGTH fault_rows fault_line_count)
if(NOT nominal_line_count EQUAL 201 OR NOT fault_line_count EQUAL 201)
    message(FATAL_ERROR "Completed telemetry must contain one header and 200 rows")
endif()

file(READ "${success_dir}/experiment_complete.txt" completion_contents)
set(expected_completion
    "AeroSim-Core experiment complete\nnominal_rows=200\nfault_injected_rows=200\nfault_activation_time_s=0.75\n")
if(NOT completion_contents STREQUAL expected_completion)
    message(FATAL_ERROR "Completion marker contents do not match completed output")
endif()

# A visible pre-existing destination must fail before either run starts.
set(collision_dir "${TEST_ROOT}/collision-run")
file(MAKE_DIRECTORY "${collision_dir}")
file(WRITE "${collision_dir}/fault_injected.csv" "preserve existing result\n")
execute_process(
    COMMAND "${AEROSIM_EXPERIMENTS}" --output-dir "${collision_dir}" --fault-time 0.75
    RESULT_VARIABLE failure_result
    OUTPUT_VARIABLE failure_stdout
    ERROR_VARIABLE failure_stderr
)
if(failure_result EQUAL 0)
    message(FATAL_ERROR "Experiment unexpectedly accepted a pre-existing output")
endif()
if(EXISTS "${collision_dir}/nominal.csv"
    OR EXISTS "${collision_dir}/experiment_complete.txt")
    message(FATAL_ERROR "Failed experiment was incorrectly marked or partially started")
endif()
file(READ "${collision_dir}/fault_injected.csv" preserved_contents)
if(NOT preserved_contents STREQUAL "preserve existing result\n")
    message(FATAL_ERROR "Pre-existing experiment output was modified")
endif()

# A dangling symlink is not reported by filesystem::exists(), but exclusive
# creation must reject it. This failure occurs after nominal.csv is complete;
# the missing completion marker must identify that run as incomplete.
set(partial_dir "${TEST_ROOT}/partial-run")
file(MAKE_DIRECTORY "${partial_dir}")
file(CREATE_LINK "${partial_dir}/missing-target"
     "${partial_dir}/fault_injected.csv" SYMBOLIC RESULT link_result)
if(NOT link_result STREQUAL "0")
    message(FATAL_ERROR "Could not create deterministic dangling-link test fixture: ${link_result}")
endif()
execute_process(
    COMMAND "${AEROSIM_EXPERIMENTS}" --output-dir "${partial_dir}" --fault-time 0.75
    RESULT_VARIABLE partial_result
    OUTPUT_VARIABLE partial_stdout
    ERROR_VARIABLE partial_stderr
)
if(partial_result EQUAL 0)
    message(FATAL_ERROR "Experiment unexpectedly opened a dangling-link destination")
endif()
if(NOT EXISTS "${partial_dir}/nominal.csv"
    OR EXISTS "${partial_dir}/experiment_complete.txt")
    message(FATAL_ERROR "Interrupted experiment completion state was not represented correctly")
endif()
