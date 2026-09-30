#ifndef AEROSIM_UAV_STATE_H
#define AEROSIM_UAV_STATE_H

// Position, altitude, speed, and elapsed simulation time for the UAV.
struct UAVState {
    double time;          // Simulation time in seconds
    double x;             // Forward position in metres
    double y;             // Sideways position in metres
    double altitude;      // Altitude coordinate in metres; datum is unspecified
    double forward_speed; // Forward speed in metres per second
};

#endif // AEROSIM_UAV_STATE_H
