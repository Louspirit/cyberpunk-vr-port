# Quest 3 stereo effects and smoke audit — 2026-10-26

Scope: Quest 3, Virtual Desktop/VDXR, port 0.1.8. Investigate different cyberware
effects and smoke between MAIN and VRCAM. This audit changed no installed game
files, settings, render hooks or Vortex state. It does not establish visual success
in the headset. The existing brightness workaround must remain the baseline.

## Verified installed shader inventory

`tools/asym_tests/quest3_stereo_audit.py` compared installed shader files with the
repository using SHA-256. All 158 files in these fixed shader groups match; none
are missing, additional or different:

| Installed group | Source group | Files |
| --- | --- | ---: |
| `asym` | `src/Shaders/asym_fog` | 4 |
| `asym_ssr` | `src/Shaders/asym_ssr` | 8 |
| `asym_ao` | `src/Shaders/asym_ao` | 4 |
| `asym_particles` | `src/Shaders/asym_particles` | 114 |
| `asym_expo` | `src/Shaders/asym_expo` | 2 |
| `asym_shadow` | `src/Shaders/asym_shadow` | 1 |
| `view_dir` | `src/Shaders/view_dir` | 24 |
| `screen_fx` | `src/Shaders/screen_fx` | 1 |

The Sandevistan replacement `screen_fx/52f74d75736ab8b0.dxil` is present (7,242
bytes). File presence does not prove a replacement pipeline was built or bound.
`src/Render/HiddenAreaShaders.cpp` exposes Loaded/Built/Failed/Binds counters for
`CyberpunkVR_ParticleFacing` and `CyberpunkVR_ScreenFxPatch`; both switches default
to 1. The particle replacements load from `asym_particles/` (group 3), screen FX
from `screen_fx/` (group 7).

`tools/asym_tests/particle_facing_shaders.py` corrects camera-facing world
billboards (smoke, steam, sparks) to face the eye position. It explicitly excludes
screen particles and world-oriented factories without camera axes. A matching
114-file inventory therefore does not cover every particle material or effect.

## Archive collisions: a concrete compatibility issue

The tool reads RED4 archive version-12 indices and stored file segments. The
layout follows WolvenKit's [ArchiveReader.cs](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Archive/IO/ArchiveReader.cs).
No extraction or game DLL loading is involved.

| Installed archive | Entries | IDs shared with port | Different uncompressed segment sizes |
| --- | ---: | ---: | ---: |
| `cyberpunkvrport.archive` | 1,099 | — | — |
| `ZVisualEffectsFixes.archive` | 1,550 | 63 | 63 |
| `Velocity.archive` | 3 | 0 | 0 |
| `PreemOptics.archive` | 2 | 0 | 0 |
| `GeneralShadowsFix.archive` | 127 | 0 | 0 |

All 63 overlapping stored payloads differ too. Each overlapping file has at
least one different uncompressed segment length, so this is not merely a change
in compression settings. This proves different serialized resources; it does not
by itself prove which change causes a visible symptom. Lack of direct overlap in
the other archives does not prove semantic compatibility.

The overlaps are primarily firearm muzzle `.effect` resources: Nue, Liberty,
Unity, Lexington, Ajax, Umbra, Copperhead, Masamune, Kyubi, Saratoga, Pulsar,
Guillotine, Defender, MA70, Sor22, Silverhand and several EP1 firearms, including
FPP/TPP and silenced variants. Example:

`base\fx\weapons\firearms\pistols\tsunami_nue\w_pistol_nue_muzzle.effect`

The archive index SHA-1 fields must **not** be used to declare equality: every
entry checked in these mod archives contains `da39a3ee…`, the SHA-1 of an empty
input. The audit instead hashes the actual stored segments and reports their
uncompressed lengths. It does not decompress them or infer the specific semantic
field difference.

### Expected priority, and the limit of that conclusion

No `archive/pc/mod/modlist.txt` was present. The documented legacy-archive policy
is ASCII filename order, with the first archive providing a resource winning.
Uppercase `Z` (90) precedes lowercase `c` (99), so the installed names predict
that **`ZVisualEffectsFixes.archive` wins these 63 resources over
`cyberpunkvrport.archive`**. See the modding tool project's
[load-order documentation](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-users/users-modding-cyberpunk-2077/load-order).

This is an inference from the documented policy and observed installation,
not a live observation of the engine's resource resolver. The available
ArchiveXL 2026-10-25 log lists `.xl` extensions; it does not record the winner of
these native `.effect` lookups. Do not mistake the `.xl` listing for native
archive precedence. Do not rename archives as an unrecorded workaround.

## Nova Optics: relevant settings, no demonstrated per-eye hook

Installed components are
`bin/x64/plugins/cyber_engine_tweaks/mods/NovaOptics/init.lua` and
`r6/scripts/NovaOptics/NovaOptics.reds`. They can alter exposure, bloom,
volumetric fog, vignette, chromatic aberration, film grain and grading.

Static inspection found these routes:

- `OnArea` and `OnEnv` handle `Resource/PostLoad` of world environment resources;
  `OnSector` walks environment trigger settings. They mutate shared area-setting
  objects, with captured originals for restoration.
- Session-ready and vehicle state callbacks reapply those settings. A scanner
  `PlayerVisionModeController` wrapper changes the film-grain scanner state.
- No direct MAIN/VRCAM/view-key selection was found. This does not show a
  MAIN-only update: the source settings are shared. An interaction with how the
  port populates its second view remains possible, but unproved.

No Nova Optics `settings.json` existed in its CET folder at audit time. The Lua
source defaults are `enable=false` and `autoMode=false`; `OnInit` loads these when
the file is absent and pushes the settings into the service. Thus installation
alone is insufficient evidence that Nova's effects are active. The live service
was not queried; its current in-memory state remains unknown. Do not disable Nova
as the first speculative fix. If needed, read the public service fields without
changing them through CET before planning an A/B.

## Existing port mechanisms and safety boundaries

The baseline configuration supplied to this audit has render mask 2051 (bits 0,
1 and 11), grading mirror 3, environment mirror FFFF and vision-to-second-eye 1.
Bit 11 grants `GameplayPostProcess`, which the code identifies with scanner tint,
Sandevistan, Kerenzikov, focus and cyberspace. It is already requested here.
`tools/gen_vrcam_assets.py` already sets `renderParticles=1` on VRCAM components.

Two similarly named composition controls are **different variables**:

- `xr_comp_lend_set=1` controls the existing composition-state loan.
- `xr_vrcam_composition=0` controls the historical graph-injection group. Zero is
  the source default; `src/Stereo/FrameGraph.cpp` warns that missing RTT inputs
  caused downstream faults when this group was enabled.

They are parsed and assigned separately in `src/Core/LiveControlsPoll.cpp`.
Changing `xr_vrcam_composition` is not an alias fix and is not proposed here.

The existing screen-effect correction neutralizes picture displacement in
assets and the Sandevistan shader. It leaves colour, overlays and other visual
features. `docs/screen-fx-distortion-20261018.md` explicitly leaves Cyberspace
DataMoshing/Pixelsort distortion unresolved. A replacement for a missing named
technique should be based on that shader's actual inputs, not an unrelated
brightness or gamma adjustment.

`include/Stereo/FogHistory.hpp` and `src/Stereo/RenderParity.cpp` deliberately
refuse MAIN fog-history borrowing when the two froxel frusta differ. Prior
measurements in the source record worse haze agreement with that borrowing
under asymmetric projection. Keep the frustum and resource-alias guards.

The recorded particle investigation (`docs/single-pass-descriptors-20260930.md`)
found the same instances processed under two particle epochs. Native onscreen
particle preparation also produces per-view outputs. The record does not prove
twice-intended simulation speed or causality for this user's smoke. Skipping the
whole second-eye particle pass, zeroing its delta or copying engine pointers is
not a justified correction.

## Minimal diagnosis and reversible A/B

1. Keep the working brightness settings. Preserve the active Vortex profile,
   deployment state and current archive/shader hashes as baseline A.
2. For muzzle smoke, close the game, disable only the Vortex mod that owns
   `ZVisualEffectsFixes.archive`, deploy, and verify that the port archive remains
   present. Restart and reproduce the same named weapon/effect and location.
   Compare both eyes. This removes a verified resource override without changing
   exposure, LUT, projection or simulation settings. If ineffective, restore the
   same mod and deployment before the next experiment. If effective, identify
   the required muzzle-resource delta and package a compatibility correction as
   a separate Vortex version; do not permanently discard unrelated fixes blindly.
3. Treat cyberware separately: name the exact effect (scanner, Sandevistan,
   Berserk, overclock, cyberspace) and distinguish missing colour/outline from
   different displaced pixels. A correct Sandevistan file does not cover all
   cyberspace techniques. Keep a same-scene baseline with the effect off.
4. If normal logs cannot distinguish a missing particle pass from a geometry or
   timing difference, reuse the existing bounded probes before adding rendering
   behavior. `CapCensus`, `NodeCensus` and `[rmask]` are disabled by the launcher's
   DEBUG-off gate; silence is not evidence of equality. In one bounded DEBUG
   session, inspect `Particles=MV`, `GameplayPostProcess=MV`, refusals for
   `DecoupledParticleLighting` (`0x6212EC`), and the per-view dispatch set. Restore
   the previous DEBUG choice afterward. Dispatch alone does not prove GPU work.
5. Only if both passes run and the symptom persists should the existing opt-in
   particle trace be considered. `CVR_STEREO_BOUNDS_TRACE` enables compatibility-
   checked, register-preserving observers in `src/Stereo/NativeBoundsTrace.cpp`;
   the reader is `tools/single_pass_tests/read_cpu_collector.py`. It can compare
   node side, instance identity, epoch and accumulated time. This is a heavier
   investigation requiring a fresh bounded launch, not a default fix.

No A/B, DEBUG launch, Vortex change or live-memory modification was performed by
this audit. The verified next experiment is the single-mod muzzle-effects A/B;
the remaining branches need named effects and per-view evidence.

## Reproduce the read-only inventory

With Python 3.10 or newer, from the repository root:

```powershell
python -B tools/asym_tests/quest3_stereo_audit.py --game-root '<Cyberpunk 2077 game root>'
python -B tools/asym_tests/quest3_stereo_audit.py --game-root '<Cyberpunk 2077 game root>' --json
```

The tool emits to stdout, uses only the Python standard library, and never writes
to the game, Vortex, settings or archives. The JSON output includes every
collision hash, available depot-path mapping and per-segment uncompressed sizes.

## Scanner/quickhacks clarification (2026-10-26)

The user confirms scanner/quickhacks is the clearest reproducer. Prioritize this
path before the unrelated muzzle-smoke archive A/B.

Read-only findings:
- `xr_vision_to_second_eye=1` is already enabled in the installed configuration.
- The existing log has no `[vision]` / `[vismap]` evidence; DEBUG was off. This
  cannot establish that either view produces, captures or composites the layer.
- `VisionLayer.cpp` selects a snapshot by node `0x61FDE4` and ordinal 0.
  Another historical comment says an address moved, but the engine table labels
  `0x61EE78` DrawConeAO. Changing the node from comments alone is unjustified.
- `hk_Dispatch` additionally contains an outline shader override selected by a
  fixed 384x384 dispatch and ordinal 2, matching the installed INI. The selected
  view resolution is rectangular 2064x2232. This is a potential mismatch, not
  proof: the producer can run at a different resolution. The override does not
  visibly enforce the root-table signature claimed in its comment. Broadening
  its dispatch predicate would therefore risk replacing unrelated shaders.
- Shader-digest matching during PSO creation is a separate path; failure of the
  dispatch override alone does not establish failure of the whole correction.

Next evidence needed: a short launcher DEBUG session in the same location,
scanner closed then opened and aimed at a hackable object. Preserve all current
brightness/composition settings. Inspect `[vismap]` per-view node/ordinal/size,
shader override creation, capture/composite counters and per-view GameplayPostFX.
Do not switch the fixed node, disable ordinal selection, broaden shader matching,
or borrow MAIN fog history before this evidence is available.
