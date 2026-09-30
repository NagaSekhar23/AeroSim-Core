#include "TimingStatistics.h"

#include <algorithm>
#include <limits>
#include <stdexcept>

SchedulingClassification classify_scheduling_offset(
    std::chrono::nanoseconds signed_offset,
    std::chrono::nanoseconds period) {
    if (period <= std::chrono::nanoseconds::zero()) {
        throw std::invalid_argument("timing period must be positive");
    }
    return {
        signed_offset > std::chrono::nanoseconds::zero(),
        signed_offset >= period
    };
}

TimingStatistics calculate_timing_statistics(const std::vector<TimingSample>& samples) {
    TimingStatistics statistics;
    if (samples.empty()) {
        return statistics;
    }

    auto minimum_execution = std::chrono::nanoseconds::max();
    auto maximum_execution = std::chrono::nanoseconds::zero();
    auto maximum_scheduling_error = std::chrono::nanoseconds::zero();
    long double total_execution_ns = 0.0L;
    long double total_scheduling_error_ns = 0.0L;

    for (const TimingSample& sample : samples) {
        minimum_execution = std::min(minimum_execution, sample.step_execution_time);
        maximum_execution = std::max(maximum_execution, sample.step_execution_time);
        maximum_scheduling_error =
            std::max(maximum_scheduling_error, sample.absolute_scheduling_error);
        total_execution_ns += sample.step_execution_time.count();
        total_scheduling_error_ns += sample.absolute_scheduling_error.count();
        if (sample.late_start) {
            ++statistics.late_starts;
        }
        if (sample.missed_deadline) {
            ++statistics.missed_deadlines;
        }
    }

    const long double sample_count = static_cast<long double>(samples.size());
    statistics.average_step_execution_time_ns =
        static_cast<double>(total_execution_ns / sample_count);
    statistics.minimum_step_execution_time = minimum_execution;
    statistics.maximum_step_execution_time = maximum_execution;
    statistics.average_absolute_scheduling_error_ns =
        static_cast<double>(total_scheduling_error_ns / sample_count);
    statistics.maximum_absolute_scheduling_error = maximum_scheduling_error;
    return statistics;
}
