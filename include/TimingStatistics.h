#ifndef AEROSIM_TIMING_STATISTICS_H
#define AEROSIM_TIMING_STATISTICS_H

#include <chrono>
#include <vector>

struct TimingSample {
    std::chrono::nanoseconds step_execution_time;
    // Absolute difference between the step start and its intended deadline.
    std::chrono::nanoseconds absolute_scheduling_error;
    // True when the step starts strictly after its intended deadline.
    bool late_start;
    // True when the step starts at least one full simulation period late.
    bool missed_deadline;
};

struct SchedulingClassification {
    bool late_start;
    bool missed_deadline;
};

struct TimingStatistics {
    double average_step_execution_time_ns = 0.0;
    std::chrono::nanoseconds minimum_step_execution_time{0};
    std::chrono::nanoseconds maximum_step_execution_time{0};
    double average_absolute_scheduling_error_ns = 0.0;
    std::chrono::nanoseconds maximum_absolute_scheduling_error{0};
    // Counts individual steps that start after their intended deadlines.
    std::size_t late_starts = 0;
    // Counts individual steps that start at least one full period late.
    std::size_t missed_deadlines = 0;
};

// Summarize captured measurements. Empty input produces zero-valued statistics.
TimingStatistics calculate_timing_statistics(const std::vector<TimingSample>& samples);

// Classify a signed step-start offset from its deadline, in nanoseconds.
// A positive offset is late; an offset at least one period is full-period late.
SchedulingClassification classify_scheduling_offset(
    std::chrono::nanoseconds signed_offset,
    std::chrono::nanoseconds period);

#endif // AEROSIM_TIMING_STATISTICS_H
