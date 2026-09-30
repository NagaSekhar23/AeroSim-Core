#ifndef AEROSIM_TELEMETRY_WRITER_H
#define AEROSIM_TELEMETRY_WRITER_H

#include "ExclusiveFile.h"

#include <string>

class UAVSimulator;

// Writes deterministic per-step simulator records. Existing files are refused
// so an experiment cannot silently replace earlier telemetry.
class TelemetryWriter {
public:
    explicit TelemetryWriter(const std::string& output_path);

    TelemetryWriter(const TelemetryWriter&) = delete;
    TelemetryWriter& operator=(const TelemetryWriter&) = delete;

    void write(const UAVSimulator& simulator);
    void close();

private:
    ExclusiveFile output_;
};

#endif // AEROSIM_TELEMETRY_WRITER_H
