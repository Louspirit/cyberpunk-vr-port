#pragma once
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>

namespace cvr::scanner_zoom {
inline bool Valid(float zoom) { return std::isfinite(zoom) && zoom >= .1f && zoom <= 64.f; }

// MAIN and VRCAM can be prepared on different recording threads. Publish the
// scalar with its timestamp as one sample; never lend an old camera's zoom.
class MainSample {
    std::atomic<uint64_t> sample{};
public:
    void Publish(float zoom, uint32_t now, bool scanner) {
        sample.store(scanner && Valid(zoom)
            ? (uint64_t(now) << 32) | std::bit_cast<uint32_t>(zoom) : 0,
            std::memory_order_release);
    }
    bool Read(uint32_t now, float& zoom) const {
        const auto value=sample.load(std::memory_order_acquire);
        if (!value || uint32_t(now-uint32_t(value>>32)) > 250u) return false;
        zoom=std::bit_cast<float>(uint32_t(value));
        return Valid(zoom);
    }
};

// Return ownership when the scanner closes, its state expires, the source goes
// stale or asymmetric projection is disabled. A native refresh always wins.
struct Override {
    uintptr_t view{};
    bool owned{};
    float original{},written{};
    bool Update(uintptr_t identity, float& nativeZoom, bool enabled, float mainZoom) {
        if (view != identity) {view=identity;owned=false;}
        if (!enabled || !Valid(mainZoom) || !Valid(nativeZoom)) {
            if (owned && nativeZoom==written) nativeZoom=original;
            owned=false;
            return false;
        }
        if (!owned || nativeZoom!=written) original=nativeZoom;
        nativeZoom=written=mainZoom;
        owned=true;
        return true;
    }
};
}
