# Quest 3 / VDXR left-eye RT artifact audit — 2026-10-27

## Evidence

The user reports left/VRCAM artifacts with ray tracing enabled and no such
artifacts with RT disabled. MAIN/right is described as correct. This establishes
a useful user A/B correlation, not the faulty RT pass or buffer.

Current saved settings have master RayTracing=false, subsettings reflections,
sun/local shadows=true and lighting=Ultra, path tracing=false. Retained subsettings
while the master is off are normal preferences; they do not prove RT executes.
DLSS is Auto with Transformer backend. Existing DEBUG-off logs do not contain a
per-eye RT dispatch/resource/history capture. No graphics setting was changed.

## Source findings

1. `src/Stereo/Dlss.cpp` mirrors MAIN AA mode to VRCAM in Detour_SlConstants.
   The existing SyncStereo.cpp explanation associates this with history-matrix
   updates used by SSR/GI/REBLUR/TAA. The fix already exists; adding it again or
   disabling it is not an evidence-based correction.
2. VRCAM's separate Streamline viewport/cache path supports independent DLSS
   state. That alone does not establish independent or correct RT-denoiser state.
3. NodeNames.inc identifies separate RT reflections, local/global shadows, AO,
   RTXDI and ReSTIRGI nodes. The current native-node observations are not an
   RT-on per-eye comparison. Reflection artifacts and shadow artifacts must not
   be merged into one unverified history diagnosis.
4. `xr_gi_reuse=1` drives the world GI-node build/apply reuse in ViewReuse.cpp.
   This is not itself proof of screen-space RT-history sharing. Local shadow-map
   reuse and reflection-probe reuse are both disabled in the installed INI.
5. Prior documented fixes (framegen-raytracing-20260928.md,
   rt-disabled-stale-flags-20260928.md) already handle RGBA16F motion-vector input
   and fresh MAIN feature flags. Their reported successes are historical,
   scene-specific results, not validation of this user's present RT artifacts.

## Next discriminating test

Keep the successful optics/scanner package unchanged. In one fixed scene, record
RT-off baseline, then enable RT with only one family at a time: reflections,
shadows, and lighting. Keep path tracing and Ray Reconstruction off for the
initial comparison. Restart after each configuration so stale history is not
mistaken for a steady-state defect. Retain the same DLSS preset and resolution.

Once the affected family is known, use a short DEBUG capture to compare that
node's MAIN/VRCAM feature admission, dimensions, camera current/previous matrices,
motion vectors, history identity and validity. Distinguish absent passes from
wrong reprojection before altering shader constants or sharing MAIN buffers.

No runtime/graphics/config modification, RT fix or extra test ZIP was produced
by this read-only audit. Avoid removing asymmetric fog-history guards or
forcing MAIN screen-space history into VRCAM; those can create new eye mismatch.
