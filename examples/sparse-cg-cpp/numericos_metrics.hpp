// One-header instrumentation for NumericOS. Copy it next to your solver.
//
//   numericos::metric("residual_rel", value, iteration);
//
// prints one numericos.metric.v1 record on standard output. JSON has no NaN and no infinity,
// so a non-finite value is written as a word. Each record is flushed at once: standard output
// is fully buffered when it is a pipe, and the supervisor should see a value when it is
// produced, not when the program ends.
#pragma once

#include <cmath>
#include <cstdio>

namespace numericos {

inline void metric(const char* name, double value, long step = -1) {
    std::printf("{\"schema\":\"numericos.metric.v1\",\"name\":\"%s\"", name);
    if (step >= 0) {
        std::printf(",\"step\":%ld", step);
    }
    if (std::isnan(value)) {
        std::printf(",\"value\":\"nan\"}\n");
    } else if (std::isinf(value)) {
        std::printf(",\"value\":\"%s\"}\n", value > 0 ? "inf" : "-inf");
    } else {
        std::printf(",\"value\":%.17g}\n", value);  // 17 significant digits round-trip a double
    }
    std::fflush(stdout);
}

}  // namespace numericos
