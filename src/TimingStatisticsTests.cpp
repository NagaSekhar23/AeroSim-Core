#include "TimingStatistics.h"

#include <cmath>
#include <iostream>
#include <vector>

namespace {
bool check(const char* name, double actual, double expected) {
    if (std::abs(actual - expected) <= 1e-9) {
        return true;
    }
    std::cerr << name << " was " << actual << ", expected " << expected << '\n';
    return false;
}

bool test_statistics_from_fixed_samples() {
    const std::vector<TimingSample> samples{
        {std::chrono::nanoseconds{100}, std::chrono::nanoseconds{10}, true, false},
        {std::chrono::nanoseconds{200}, std::chrono::nanoseconds{40}, true, true},
        {std::chrono::nanoseconds{300}, std::chrono::nanoseconds{70}, true, false}
    };

    const TimingStatistics result = calculate_timing_statistics(samples);
    return check("average execution time", result.average_step_execution_time_ns, 200.0)
        && check("minimum execution time", result.minimum_step_execution_time.count(), 100.0)
        && check("maximum execution time", result.maximum_step_execution_time.count(), 300.0)
        && check("average scheduling error",
                 result.average_absolute_scheduling_error_ns, 40.0)
        && check("maximum scheduling error",
                 result.maximum_absolute_scheduling_error.count(), 70.0)
        && result.late_starts == 3
        && result.missed_deadlines == 1;
}

bool test_lateness_threshold_boundaries() {
    constexpr auto period = std::chrono::milliseconds{10};
    const SchedulingClassification on_time = classify_scheduling_offset(
        std::chrono::nanoseconds{0}, period);
    const SchedulingClassification slightly_late = classify_scheduling_offset(
        std::chrono::nanoseconds{1}, period);
    const SchedulingClassification exactly_one_period_late =
        classify_scheduling_offset(period, period);
    const SchedulingClassification more_than_one_period_late =
        classify_scheduling_offset(period + std::chrono::nanoseconds{1}, period);
    if (on_time.late_start || on_time.missed_deadline
        || !slightly_late.late_start || slightly_late.missed_deadline
        || !exactly_one_period_late.late_start
        || !exactly_one_period_late.missed_deadline
        || !more_than_one_period_late.late_start
        || !more_than_one_period_late.missed_deadline) {
        std::cerr << "Scheduling offset classification crossed an incorrect threshold\n";
        return false;
    }

    const std::vector<TimingSample> samples{
        {std::chrono::nanoseconds{1}, std::chrono::nanoseconds{0},
         on_time.late_start, on_time.missed_deadline},
        {std::chrono::nanoseconds{1}, std::chrono::nanoseconds{1},
         slightly_late.late_start, slightly_late.missed_deadline},
        {std::chrono::nanoseconds{1}, period,
         exactly_one_period_late.late_start, exactly_one_period_late.missed_deadline},
        {std::chrono::nanoseconds{1}, period + std::chrono::nanoseconds{1},
         more_than_one_period_late.late_start, more_than_one_period_late.missed_deadline}
    };

    const TimingStatistics result = calculate_timing_statistics(samples);
    return result.late_starts == 3
        && result.missed_deadlines == 2
        && check("average absolute scheduling error",
                 result.average_absolute_scheduling_error_ns,
                 (0.0 + 1.0 + 10'000'000.0 + 10'000'001.0) / 4.0)
        && check("maximum absolute scheduling error",
                 result.maximum_absolute_scheduling_error.count(), 10'000'001.0);
}

bool test_empty_samples() {
    const TimingStatistics result = calculate_timing_statistics({});
    return check("empty average execution time", result.average_step_execution_time_ns, 0.0)
        && check("empty average scheduling error",
                 result.average_absolute_scheduling_error_ns, 0.0)
        && result.minimum_step_execution_time.count() == 0
        && result.maximum_step_execution_time.count() == 0
        && result.maximum_absolute_scheduling_error.count() == 0
        && result.late_starts == 0
        && result.missed_deadlines == 0;
}
} // namespace

int main() {
    if (!test_statistics_from_fixed_samples()
        || !test_lateness_threshold_boundaries()
        || !test_empty_samples()) {
        return 1;
    }
    std::cout << "Passed: timing statistics\n";
    return 0;
}
