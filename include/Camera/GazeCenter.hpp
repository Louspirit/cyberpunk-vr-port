#pragma once
#include <atomic>
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdio>

namespace cvr::gaze {
// One calibrated binocular head-gaze ray, shared by targeting and scanner display.
// Horizontal eye asymmetry is retained: their separate centres are not a common ray.
struct Center {float tangentY{},ndcY{};};
// Default 0 retains the rendered-window centre used by earlier releases. A headset's
// physical forward axis is independent of its lens window's asymmetric bounds.
struct Calibration {
    int32_t mode{}; // 0 = rendered view centre (legacy), 1 = physical headset forward
    float pitchDegrees{}; // positive raises both the targeting ray and scanner reticle
    bool operator==(const Calibration&) const = default;
};
inline Calibration Sanitize(Calibration value) {
    value.mode=value.mode==1?1:0;
    value.pitchDegrees=std::isfinite(value.pitchDegrees)?std::clamp(value.pitchDegrees,-30.f,30.f):0.f;
    return value;
}
inline std::atomic<uint64_t> calibrationBits{};
inline void Configure(Calibration value){calibrationBits.store(std::bit_cast<uint64_t>(Sanitize(value)),std::memory_order_release);}
inline Calibration GetCalibration(){return std::bit_cast<Calibration>(calibrationBits.load(std::memory_order_acquire));}
inline bool ForceCameraForward(Calibration calibration,bool ownsHeadGaze,bool asymmetricProjection) {
    return asymmetricProjection && ownsHeadGaze && (calibration.mode==1 || calibration.pitchDegrees!=0.f);
}
inline bool ParseSetting(const char* line,Calibration& value) {
    int mode{};float pitch{};
    if(std::sscanf(line,"xr_gaze_center_mode = %d",&mode)==1) {value.mode=mode;value=Sanitize(value);return true;}
    if(std::sscanf(line,"xr_gaze_pitch_deg = %f",&pitch)==1) {value.pitchDegrees=pitch;value=Sanitize(value);return true;}
    return false;
}
inline void WriteSettings(FILE* file,Calibration value) {
    value=Sanitize(value);
    std::fprintf(file,"xr_gaze_center_mode=%d\nxr_gaze_pitch_deg=%.3f\n",value.mode,value.pitchDegrees);
}
inline std::atomic<uint64_t> centerBits{};
inline std::atomic<bool> headLook{true};
inline Center FromWindows(float up0,float down0,float up1,float down1,Calibration calibration={}) {
    const float middle=(up0+down0+up1+down1)*.25f;
    const float half=(up0-down0+up1-down1)*.25f;
    if(!std::isfinite(middle) || !std::isfinite(half) || half<.05f || std::abs(middle)>1.f)return {};
    calibration=Sanitize(calibration);
    float tangent=calibration.mode==1?0.f:middle;
    if(calibration.pitchDegrees!=0.f) {
        constexpr float radians=3.14159265358979323846f/180.f;
        // The native targeting guard accepts a ray within 45 degrees of the camera.
        // Clamp the combined angle too so its ray and the scanner cannot diverge.
        tangent=std::clamp(std::tan(std::clamp(std::atan(tangent)+calibration.pitchDegrees*radians,
                                             -45.f*radians,45.f*radians)),-1.f,1.f);
    }
    return {tangent,tangent/half};
}
inline void Publish(Center value){centerBits.store(std::bit_cast<uint64_t>(value),std::memory_order_release);}
inline Center Read(){return headLook.load(std::memory_order_relaxed) ? std::bit_cast<Center>(centerBits.load(std::memory_order_acquire)) : Center{};}
inline float CanvasOffset(Center center,float height,float designScale) {
    return height>0 && designScale>0 ? -center.ndcY*height*.5f/designScale : 0.f;
}
}
