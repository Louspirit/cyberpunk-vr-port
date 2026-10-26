# Optics layout and native-reticle checks

Run the production CET scripts in a LuaJIT 2.1 fixture without a game process:

```text
python -m pip install --target build/lua-test-deps lupa
python tools/optics_tests/test_layout_fallback.py -v
```

The fixture covers complete shader/camera scopes, incomplete appearances,
component enumeration versus direct entity lookup, restoration after equipment
changes, native HUD fallback, smart-sniper scale, and stale weapon identities.

In CET, hold the affected weapon and inspect:

```lua
print(GetMod('CyberpunkVRPort_Optics').diagnostics())
```

`directRecovered` counts required authored components absent from `GetComponents()`
but returned by `FindComponentByName`. `lookupErrors` counts failed lookup calls;
an absent component returned normally does not count as an error. Both counts
describe the last scan. The script logs changes to this diagnostic automatically.

## Packaged-asset audit for the black Overwatch lens

The 0.1.8 `cyberpunkvrport.archive` (25,845,760 bytes) contains 1,099 resource
entries and the custom `base\vrport\optics` meshes, including the sniper_01 low,
surface, front-reticle and rear-reticle meshes. Its resource
`base\weapons\firearms\attachments\scope\w_att__scope_sniper_01\w_att__scope_sniper_01.app`
has FNV-1a hash `a0cc2afdb4f0e5b5`. All eleven compiled appearance buffers include
the seven `vr_optic_*` component names, including the `panam` appearance used by
Overwatch. The installed mod-archive indexes inspected during diagnosis did not
duplicate this resource or the sixteen other resources containing optical
components/cameras.

This establishes packaged resource/name presence. It does not establish that the
engine instantiated or registered every serialized component. The live lookup
counts distinguish an enumeration omission from a component that cannot be found
on the weapon. A zero recovery count requires further appearance-buffer analysis.

The binary index, segment and custom-path layouts were checked against
[WolvenKit ArchiveReader](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Archive/IO/ArchiveReader.cs)
and [LxrsFooter](https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Archive/Base/LxrsFooter.cs).
The installed game's existing Oodle decoder was used for read-only decompression.
