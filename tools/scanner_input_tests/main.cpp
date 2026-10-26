#include "Hooks/ScannerGesture.hpp"
#include "Camera/GazeCenter.hpp"
#include "Camera/TakeoverTargeting.hpp"
#include "Runtimes/AsymmetricProjection.hpp"
#include "Runtimes/RuntimeFovCorrection.hpp"
#include "Utils/XrMath.hpp"
#include "Render/WorldMarkerProjection.hpp"
#include <array>
#include <cstring>
#include <stdexcept>
#include <limits>
#include <cstdio>
extern "C" {
int32_t CyberpunkVR_AsymProjection=1;
int32_t CyberpunkVR_AsymSquarePixels=1;
float CyberpunkVR_AsymInnerGuard=0.f;
}
int g_launcherWidth=2064,g_launcherHeight=2232;
void Check(bool value){if(!value)throw std::runtime_error("scanner input regression");}
void Near(float value,float expected,float tolerance=1.e-5f){Check(std::abs(value-expected)<tolerance);}
XrQuaternionf Axis(float x,float y,float z,float angle){const float s=std::sin(angle*.5f);return {x*s,y*s,z*s,std::cos(angle*.5f)};}
void CalibrationCases() {
    constexpr float radians=3.14159265358979323846f/180.f;
    const XrFovf lens[]{ {-54*radians,40*radians,44*radians,-55*radians},
                         {-40*radians,54*radians,44*radians,-55*radians} };
    const auto correction=ComputeRuntimeFovCorrection(lens[0],lens[1]);
    Near(correction.pitchDeltaRad,-5.5f*radians);
    Check(!correction.pitchEnabled); // Diagnostic frustum recentring does not rotate the HMD pose.
    const XrQuaternionf heads[]{ {0,0,0,1},
        MultiplyQuat(Axis(0,1,0,35*radians),MultiplyQuat(Axis(1,0,0,-18*radians),Axis(0,0,1,12*radians))) };
    cvr::projection::EyeWindow reference[2]{};
    for(size_t h=0;h<std::size(heads);++h) {
        const auto head=heads[h];
        // Real per-eye orientations include both common HMD orientation and opposite display cant.
        const XrQuaternionf eyes[]{MultiplyQuat(head,Axis(0,1,0,-7*radians)),MultiplyQuat(head,Axis(0,1,0,7*radians))};
        cvr::projection::EyeWindow windows[2]{};
        Check(cvr::projection::Windows(lens,eyes,windows));
        if(h==0) {reference[0]=windows[0];reference[1]=windows[1];}
        for(int e=0;e<2;++e) {
            Near(windows[e].u,reference[e].u);Near(windows[e].d,reference[e].d);
            Near(windows[e].l,reference[e].l);Near(windows[e].r,reference[e].r);
        }
        const float up=windows[0].u,down=windows[0].d;
        const auto legacy=cvr::gaze::FromWindows(up,down,windows[1].u,windows[1].d);
        Near(std::atan(legacy.tangentY)/radians,-13.02f,.02f);
        const cvr::gaze::Calibration configurations[]{ {0,0},{1,0},{1,5},{1,-5},{0,5},{0,-5} };
        for(auto calibration:configurations) {
            const auto gaze=cvr::gaze::FromWindows(up,down,windows[1].u,windows[1].d,calibration);
            const float wanted=(calibration.mode==1?0.f:std::atan(legacy.tangentY))+calibration.pitchDegrees*radians;
            Near(std::atan(gaze.tangentY),wanted);
            const auto panel=RotateVector(head,{0,gaze.tangentY,-1});
            const auto inHead=RotateVector(ConjugateQuat(head),panel);
            Near(inHead.x,0);Near(inHead.y/-inHead.z,std::tan(wanted));
            if(calibration.mode==1 && calibration.pitchDegrees==0) {
                const auto forward=RotateVector(head,{0,0,-1});
                Near(panel.x,forward.x);Near(panel.y,forward.y);Near(panel.z,forward.z);
            }
            // PersistentDot remains on the native in-eye canvas, not the extracted XR panel.
            // Exercise the production ink-camera rewrite that WorldMarkers applies to that canvas;
            // the RootGazeDot translation must then land on the actual selected ray in each eye.
            constexpr float width=2856.f,height=3088.f,designScale=2856.f/3840.f;
            for(const auto& window:windows) {
                std::array<float,212> camera{};
                const float matrix[]{2/width,0,0,-1,0,-2/height,0,1,0,0,1,0,0,0,0,1};
                std::memcpy(camera.data(),matrix,sizeof(matrix));camera[188]=width;camera[189]=height;
                auto shifted=camera;const auto projection=cvr::projection::ToEngine(window);
                cvr::markers::ShiftInkCamera(shifted.data(),camera.data(),sizeof(camera),1,projection.shiftX,projection.shiftY);
                const float rootY=height*.5f+cvr::gaze::CanvasOffset(gaze,height,designScale)*designScale;
                const float dotNdc=shifted[5]*rootY+shifted[7];
                const float rayNdc=(2*gaze.tangentY-window.u-window.d)/(window.u-window.d);
                Near(dotNdc,rayNdc);
            }

            std::array<uint8_t,0x31240> state{};std::array<uint8_t,0x400> source{};
            const uintptr_t player=0x123400,sourceAddress=reinterpret_cast<uintptr_t>(source.data());
            const uint64_t entity=42;const uint32_t active=1;
            std::memcpy(state.data(),&player,sizeof(player));std::memcpy(state.data()+8,&entity,sizeof(entity));
            std::memcpy(state.data()+24,&active,sizeof(active));std::memcpy(state.data()+0x30CC8,&sourceAddress,sizeof(sourceAddress));
            // Native targeting uses game axes (+Y forward,+Z up), independently of eye cant.
            const auto game=MultiplyQuat(Axis(0,0,1,35*radians),MultiplyQuat(Axis(1,0,0,-18*radians),Axis(0,1,0,12*radians)));
            const auto forward=RotateVector(game,{0,1,0});
            const float pose[]{1,2,3,1,game.x,game.y,game.z,game.w},ray[]{forward.x,forward.y,forward.z,1};
            using namespace cvr::camera;
            std::memcpy(state.data()+TargetingCameraTransformOffset,pose,sizeof(pose));
            std::memcpy(state.data()+TargetingDefaultForwardOffset,ray,sizeof(ray));
            const bool force=calibration.mode==1 || calibration.pitchDegrees!=0.f;
            const bool adjusted=CenterHeadGaze(state.data(),player,entity,gaze.tangentY,force);
            Check(adjusted==(gaze.tangentY!=0 || force));
            float result[4]{};std::memcpy(result,state.data()+TargetingDefaultForwardOffset,sizeof(result));
            const float length=std::sqrt(1+gaze.tangentY*gaze.tangentY);
            const auto expected=RotateVector(game,{0,1/length,gaze.tangentY/length});
            Near(result[0],expected.x);Near(result[1],expected.y);Near(result[2],expected.z);
            Check(!std::memcmp(state.data()+TargetingCameraTransformOffset,pose,sizeof(pose)));
            if(adjusted)Check(!std::memcmp(source.data()+0x370,result,sizeof(result)));
            if(calibration.mode==1 && calibration.pitchDegrees==0) {
                // An almost-camera ray is a normal FPP-cache variation. Zero must be an explicit
                // reset in physical mode; legacy zero and scripted off-axis rays remain untouched.
                const auto drift=RotateVector(game,{0,std::cos(3*radians),std::sin(3*radians)});
                const float driftRay[]{drift.x,drift.y,drift.z,1};
                std::memcpy(state.data()+TargetingDefaultForwardOffset,driftRay,sizeof(driftRay));
                Check(!CenterHeadGaze(state.data(),player,entity,0));
                Check(!std::memcmp(state.data()+TargetingDefaultForwardOffset,driftRay,sizeof(driftRay)));
                Check(CenterHeadGaze(state.data(),player,entity,0,true));
                std::memcpy(result,state.data()+TargetingDefaultForwardOffset,sizeof(result));
                Near(result[0],forward.x);Near(result[1],forward.y);Near(result[2],forward.z);
                const auto scripted=RotateVector(game,{0,std::cos(20*radians),std::sin(20*radians)});
                const float scriptRay[]{scripted.x,scripted.y,scripted.z,1};
                std::memcpy(state.data()+TargetingDefaultForwardOffset,scriptRay,sizeof(scriptRay));
                Check(!CenterHeadGaze(state.data(),player,entity,0,true));
                Check(!std::memcmp(state.data()+TargetingDefaultForwardOffset,scriptRay,sizeof(scriptRay)));
            }
        }
    }
    cvr::gaze::Calibration settings{};
    Check(cvr::gaze::ParseSetting("xr_gaze_center_mode=1",settings));
    Check(cvr::gaze::ParseSetting("xr_gaze_pitch_deg = 4.25",settings));
    FILE* file=std::tmpfile();Check(file!=nullptr);cvr::gaze::WriteSettings(file,settings);std::rewind(file);
    cvr::gaze::Calibration roundTrip{};char line[128]{};
    while(std::fgets(line,sizeof(line),file))Check(cvr::gaze::ParseSetting(line,roundTrip));
    std::fclose(file);Check(settings==roundTrip);
    Check(!cvr::gaze::ParseSetting("xr_gaze_pitch_deg_extra=10",settings));
    Check(cvr::gaze::ParseSetting("xr_gaze_center_mode=99",settings));Check(settings.mode==0);
    Check(cvr::gaze::ParseSetting("xr_gaze_pitch_deg=99",settings));Check(settings.pitchDegrees==30);
    settings=cvr::gaze::Sanitize({1,std::numeric_limits<float>::quiet_NaN()});Check(settings.pitchDegrees==0);
    cvr::gaze::Configure({1,-99});Check(cvr::gaze::GetCalibration()==cvr::gaze::Calibration{1,-30});
    const cvr::gaze::Calibration savedPhysical{1,0};
    Check(cvr::gaze::ForceCameraForward(savedPhysical,true,true));
    Check(!cvr::gaze::ForceCameraForward(savedPhysical,true,false)); // saved mode cannot own symmetric projection
    Check(!cvr::gaze::ForceCameraForward(savedPhysical,false,true)); // weapon/device optics keep ownership
    Check(!cvr::gaze::ForceCameraForward({},true,true)); // legacy zero remains the native no-op
    cvr::gaze::Configure({});
    const auto limit=cvr::gaze::FromWindows(1.6f,.4f,1.6f,.4f,{0,30});
    Check(std::isfinite(limit.tangentY) && limit.tangentY<=1.f);
}
int main(){
    CalibrationCases();
    constexpr float pi=3.14159265358979323846f;
    const float up=std::tan(44*pi/180),down=std::tan(-55*pi/180),half=(up-down)*.5f;
    const auto gaze=cvr::gaze::FromWindows(up,down,up,down);
    Check(std::abs((gaze.tangentY-(up+down)*.5f)/half)<1.e-6f);
    // Native-dot translation and the XR panel must land on the same pixel.
    const float nativeY=(1+gaze.ndcY)*3088*.5f;
    Check(std::abs(nativeY+cvr::gaze::CanvasOffset(gaze,3088,2856.f/3840)*(2856.f/3840)-1544)<.001f);
    std::array<uint8_t,0x31240> cache{};
    std::array<uint8_t,0x400> source{};
    const uintptr_t sourceAddress=reinterpret_cast<uintptr_t>(source.data());
    std::memcpy(cache.data()+0x30CC8,&sourceAddress,sizeof(sourceAddress));
    uintptr_t player=0x123400;uint64_t entity=42;uint32_t active=1;
    std::memcpy(cache.data(),&player,8);std::memcpy(cache.data()+8,&entity,8);std::memcpy(cache.data()+24,&active,4);
    const float camera[]{1,2,3,1,0,0,0,1},origin[]{4,5,6,1},forward[]{0,1,0,1};
    using namespace cvr::camera;
    std::memcpy(cache.data()+TargetingCameraTransformOffset,camera,sizeof(camera));
    std::memcpy(cache.data()+TargetingDefaultPositionOffset,origin,sizeof(origin));
    std::memcpy(cache.data()+TargetingDefaultForwardOffset,forward,sizeof(forward));
    std::memcpy(source.data()+0x350,origin,sizeof(origin));
    std::memcpy(source.data()+0x370,forward,sizeof(forward));
    Check(!CenterHeadGaze(cache.data(),player,entity+1,gaze.tangentY));
    Check(CenterHeadGaze(cache.data(),player,entity,gaze.tangentY));
    float ray[4];std::memcpy(ray,cache.data()+TargetingDefaultForwardOffset,sizeof(ray));
    Check(std::abs(ray[2]/ray[1]-gaze.tangentY)<1.e-6f);
    Check(!std::memcmp(cache.data()+TargetingCameraTransformOffset,camera,sizeof(camera)));
    Check(!std::memcmp(cache.data()+TargetingDefaultPositionOffset,origin,sizeof(origin)));
    Check(!std::memcmp(source.data()+0x350,origin,sizeof(origin)));
    Check(!std::memcmp(source.data()+0x370,ray,sizeof(ray)));
    Check(cvr::gaze::FromWindows(1,-1,1,-1).tangentY==0);
    cvr::gaze::Publish(gaze);cvr::gaze::headLook=false;Check(cvr::gaze::Read().tangentY==0);cvr::gaze::headLook=true;
    cvr::input::ScannerEarZone zone;
    Check(zone.Contains(-.25f,-.10f,.15f,false));
    Check(zone.Contains(-.20f,-.18f,.12f,false));
    Check(zone.Contains(-.20f,0,-.05f,false));
    Check(!zone.Contains(-.20f,-.30f,-.40f,false)); // ordinary hand rest / weapon position
    Check(!zone.Contains(.10f,-.03f,.06f,false)); // other side of the head
    Check(!zone.Contains(std::numeric_limits<float>::quiet_NaN(),0,0,false));
    cvr::input::ScannerRequest request;bool held=true;
    request.Update(held,0,1000);Check(held);
    request.Update(held,0,1749);Check(held);
    request.Update(held,0,1750);Check(!held); // rejected opening releases LB
    held=true;request.Update(held,0,2000);request.Update(held,1,2040);
    request.Update(held,1,10000);Check(held); // accepted hold can last indefinitely
    request.Update(held,0,10020);Check(!held); // game-driven exit releases our latch
    held=true;request.Update(held,-1,11000);request.Update(held,-1,11750);Check(!held);
    held=true;request.Update(held,1,12000);held=false;request.Update(held,1,12020);
    held=true;request.Update(held,0,12040);Check(held); // a new squeeze gets its own acceptance window
}
