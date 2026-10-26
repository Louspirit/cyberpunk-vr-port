"""Exercise the production CET optics script without a game process.

Requires lupa, either installed normally or in build/lua-test-deps.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "build/lua-test-deps"))
from lupa.luajit21 import LuaRuntime


def fixture(profile_name="w_att__scope_sniper_01_010173"):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().package.path = (
        str(ROOT / "mods/cet/CyberpunkVRPort_Optics/?.lua").replace("\\", "/")
        + ";" + lua.globals().package.path
    )
    lua.globals().profileName = profile_name
    lua.execute(r'''
        events, logs, components, order, missing = {}, {}, {}, {}, {}
        dotOn, componentReads, publishedPath = 0, 0, nil
        weaponType, weaponEvolution, magnification = 'sniper', 'power', 6
        function registerForEvent(name, fn) events[name] = fn end
        function print(line) logs[#logs + 1] = line end
        CName = {new=function(value) return value end}
        NameToString = tostring
        function vector(x,y,z,w) return {x=x,y=y,z=z,w=w or 0} end
        Vector4 = {new=vector}
        Vector2 = {new=function(value) return value end}
        Quaternion = {new=function(i,j,k,r) return {i=i,j=j,k=k,r=r} end}
        Transform = {new=function() return {position=vector(0,0,0,1)} end}
        function SetVRSightDot(on) if on then dotOn=dotOn+1 end end
        function add(name, enabled, mask)
            if components[name] then return end
            local value={name=name,enabled=enabled,chunkMask=mask,refreshes=0}
            function value:GetName() return self.name end
            function value:IsEnabled() return self.enabled end
            function value:Toggle(on) self.enabled=on end
            function value:IsA() return false end
            function value:RefreshAppearance() self.refreshes=self.refreshes+1 end
            function value:ChangeAppearance(name) self.meshAppearance=name;return true end
            function value:GetWidget() return nil end
            components[name]=value;order[#order+1]=value
        end
        profile=require('optics/profiles')[profileName]
        add(profileName,true,255)
        if not profile or not profile.cameraOnly then add('vr_optic_low',false) end
        add('vr_optic_surface',false);add('vr_optic_panel',false)
        if profile and profile.originalPanel then add(profile.originalPanel,true) end
        for _,layer in ipairs(profile and profile.reticles or {}) do
            add(layer.originalPanel,true);add(layer.originalMesh,true)
            add(layer.surface,false);add(layer.panel,false)
        end
        weapon={}
        function weapon:GetEntityID() return {hash=42} end
        function weapon:IsRanged() return true end
        function weapon:HasScope() return true end
        function weapon:GetComponents()
            componentReads=componentReads+1
            local values={}
            for _,c in ipairs(order) do if not missing[c.name] then values[#values+1]=c end end
            return values
        end
        function weapon:GetWorldOrientation() return Quaternion.new(0,0,0,1) end
        function weapon:GetWorldPosition() return vector(0,0,0,1) end
        function weapon:GetScopeOffset() return vector(0,0,0.1,1) end
        function weapon:GetWeaponRecord()
            return {ItemType=function() return {Type=function()return weaponType end} end,
                    Evolution=function() return {Type=function()return weaponEvolution end} end}
        end
        activeWeapon=weapon
        player={}
        function player:GetEntityID() return {hash=1} end
        function player:GetActiveWeapon() return activeWeapon end
        function player:FindComponentByName() return nil end
        local stereo={ready=true,VrcamSel={loadingActive=false,appliedWant=true,enabledCount=1,
            appliedName='test',selected='test',appliedId='1'}}
        function GetMod(name)
            if name=='CyberpunkVRPort_Optics' then return optics end
            return stereo
        end
        gamedataStatType={ZoomLevel=1}
        gamedataItemType={Wea_SniperRifle='sniper'}
        gamedataWeaponEvolution={Smart='smart'}
        local board={GetInt=function()return 0 end}
        function GetAllBlackboardDefs()return {PlayerStateMachine={Vision='Vision',UpperBody='UpperBody'}}end
        local camera={GetActiveCameraRight=function()return vector(1,0,0)end,
            GetActiveCameraWorldTransform=function(_,t)t.position=vector(2,-0.2,1,1)end}
        Game={GetPlayer=function()return player end,
            FindEntityByID=function()return weapon end,
            VRPhysicalOpticsEnabled=function()return true end,
            VRPhysicalOpticsCameraReady=function()return false end,
            GetCameraSystem=function()return camera end,
            GetStatsSystem=function()return {GetStatValue=function()return magnification end}end,
            GetBlackboardSystem=function()return {GetLocalInstanced=function()return board end}end,
            SetVRPhysicalOpticsPath=function(path)publishedPath=path end}
    ''')
    lua.globals().optics = lua.execute(
        (ROOT / "mods/cet/CyberpunkVRPort_Optics/init.lua").read_text(encoding="utf-8")
    )
    lua.execute("function tick(delta) events.onUpdate(delta or 0.21) end")
    return lua


def load_crosshair(lua):
    lua.execute('''
        observed={};weaponAim=true
        function Observe(class,method,fn)observed[class..'.'..method]=fn end
        function IsDefined(value)return value~=nil end
        function EnumInt(value)return value end
        function GetVRWeaponAim()return weaponAim end
        function widget(name,children)
            local value={name=name,children=children or {},visible=true,scale={X=1,Y=1}}
            function value:GetName()return self.name end
            function value:IsA(name)return name=='inkCompoundWidget'end
            function value:GetNumChildren()return #self.children end
            function value:GetWidgetByIndex(index)return self.children[index+1]end
            function value:SetScale(scale)self.scale=scale end
            function value:SetVisible(on)self.visible=on end
            return value
        end
        activeWidget=widget('active',{
            widget('smartGun',{widget('smartGunFrame'),widget('dotContainer'),widget('smartGunBG'),
                widget('smartGunFluff'),widget('wmrk')}),widget('smartFots'),widget('reticle_no_smart_link')})
        hudRoot=widget('hud')
        container={GetRootWidget=function()return hudRoot end,
            GetActiveCrosshairWidget=function()return activeWidget end}
    ''')
    lua.globals().crosshair = lua.execute(
        (ROOT / "mods/cet/CyberpunkVRPort_Crosshair/init.lua").read_text(encoding="utf-8")
    )
    lua.execute('''
        events.onInit()
        observed['gameuiCrosshairContainerController.OnInitialize'](container)
        function crosshairTick(method)
            observed['gameuiCrosshairBaseGameController.'..(method or 'UpdateCrosshairState')]({})
        end
    ''')


class OpticalLayoutFallbackTests(unittest.TestCase):
    def test_complete_scope_keeps_existing_reticle_path_without_extra_dot(self):
        fixture().execute('''
            tick();assert(optics.error==nil and optics.path=='camera')
            assert(components[profileName].chunkMask==profile.bodyMask)
            for _,layer in ipairs(profile.reticles)do
                assert(not components[layer.originalPanel].enabled)
                assert(not components[layer.originalMesh].enabled)
                assert(components[layer.surface].enabled and components[layer.panel].enabled)
            end
            assert(dotOn==0 and publishedPath==3)
            local count=#logs;local applies=optics.stats.applies
            tick();assert(#logs==count and optics.stats.applies==applies)
        ''')

    def test_missing_replacements_never_hide_native_artwork(self):
        for name in ("vr_optic_low", "vr_optic_surface", "vr_optic_panel",
                     "vr_optic_reticle_front", "vr_optic_reticle_front_panel",
                     "vr_optic_reticle_rear", "vr_optic_reticle_rear_panel"):
            with self.subTest(missing=name):
                lua = fixture()
                lua.globals().missingName = name
                lua.execute('''
                    missing[missingName]=true;tick()
                    assert(optics.path=='native' and optics.error:find(missingName,1,true))
                    assert(components[profileName].chunkMask==255)
                    for _,layer in ipairs(profile.reticles)do
                        assert(components[layer.originalPanel].enabled)
                        assert(components[layer.originalMesh].enabled)
                    end
                    assert(not components.vr_optic_surface.enabled and not components.vr_optic_panel.enabled)
                    assert(dotOn==0 and publishedPath==4)
                    assert(optics.diagnostics():find('profile=sniper_01',1,true))
                    assert(optics.diagnostics():find(missingName,1,true))
                ''')

    def test_complete_shader_scope_keeps_its_existing_lens_and_reticles(self):
        fixture("w_att__scope_long_05_01").execute('''
            weaponType,magnification='rifle',2.35;tick()
            assert(optics.path=='shader' and optics.error==nil and publishedPath==2)
            assert(components.vr_optic_low.enabled)
            assert(not components.vr_optic_surface.enabled and not components.vr_optic_panel.enabled)
            for _,layer in ipairs(profile.reticles)do
                assert(not components[layer.originalPanel].enabled)
                assert(components[layer.surface].enabled and components[layer.panel].enabled)
            end
            assert(dotOn==0)
        ''')

    def test_same_entity_layout_loss_restores_then_recovers(self):
        fixture().execute('''
            tick();missing.vr_optic_reticle_rear_panel=true;tick()
            assert(optics.path=='native' and components[profileName].chunkMask==255)
            assert(components[profile.reticles[2].originalPanel].enabled)
            assert(not components.vr_optic_reticle_front.enabled)
            local reads=componentReads;local count=#logs
            tick(0.01);assert(componentReads==reads and #logs==count)
            missing.vr_optic_reticle_rear_panel=nil;tick()
            assert(optics.path=='camera' and optics.error==nil and optics.missingComponents==nil)
            assert(not components[profile.reticles[2].originalPanel].enabled)
            assert(components.vr_optic_reticle_rear_panel.enabled)
            assert(dotOn==0)
        ''')

    def test_holstering_restores_the_previous_weapon(self):
        fixture().execute('''
            tick();activeWeapon=nil;tick()
            assert(optics.path=='none' and optics.profile==nil and optics.error==nil)
            assert(components[profileName].chunkMask==255)
            for _,layer in ipairs(profile.reticles)do
                assert(components[layer.originalPanel].enabled)
                assert(not components[layer.surface].enabled and not components[layer.panel].enabled)
            end
        ''')

    def test_switching_to_another_weapon_restores_the_previous_weapon(self):
        fixture().execute('''
            tick()
            other=setmetatable({GetEntityID=function()return {hash=43}end,
                GetComponents=function()return {}end},{__index=weapon})
            Game.FindEntityByID=function(id)if id.hash==42 then return weapon else return other end end
            activeWeapon=other;tick()
            assert(optics.path=='native' and optics.profile==nil)
            assert(optics.diagnostics():find('weapon=43 ',1,true))
            assert(components[profileName].chunkMask==255)
            for _,layer in ipairs(profile.reticles)do
                assert(components[layer.originalPanel].enabled)
                assert(not components[layer.surface].enabled and not components[layer.panel].enabled)
            end
        ''')

    def test_incomplete_layout_restores_native_ads_visibility_gates(self):
        fixture().execute('''
            add('native_ads_gate',false)
            local gate=components.native_ads_gate
            gate.visibilityAnimationParam='visibleWhenAiming'
            gate.IsA=function(_,name)return name=='entSkinnedMeshComponent'end
            missing.vr_optic_reticle_rear_panel=true;tick()
            assert(not gate.enabled and gate.visibilityAnimationParam=='visibleWhenAiming')
            missing.vr_optic_reticle_rear_panel=nil;tick()
            assert(gate.enabled and gate.visibilityAnimationParam=='None')
            missing.vr_optic_reticle_rear_panel=true;tick()
            assert(not gate.enabled and gate.visibilityAnimationParam=='visibleWhenAiming')
        ''')

    def test_same_weapon_unmatched_scope_restores_previous_profile(self):
        fixture().execute('''
            tick();missing[profileName]=true;tick()
            assert(optics.path=='native' and optics.profile==nil and optics.error==nil)
            assert(optics.fallbackReason=='No authored optical profile')
            for _,layer in ipairs(profile.reticles)do
                assert(components[layer.originalPanel].enabled)
                assert(not components[layer.surface].enabled and not components[layer.panel].enabled)
            end
            assert(dotOn==0)
        ''')

    def test_fallback_preserves_originally_disabled_native_panel(self):
        fixture().execute('''
            local original=components[profile.reticles[2].originalPanel]
            original.enabled=false;tick()
            missing.vr_optic_reticle_rear_panel=true;tick()
            assert(not original.enabled)
            events.onShutdown();assert(not original.enabled)
        ''')

    def test_camera_only_profile_does_not_require_low_magnification_mesh(self):
        fixture("w_rifle_sniper__nokota_osprey__base1_8610").execute('''
            assert(components.vr_optic_low==nil);tick()
            assert(optics.path=='camera' and optics.error==nil)
            missing.vr_optic_reticle_rear_panel=true;tick()
            assert(optics.path=='native' and optics.error:find('vr_optic_reticle_rear_panel',1,true))
            assert(components[profile.reticles[1].originalPanel].enabled)
        ''')

    def test_unmatched_sniper_reports_native_fallback_without_new_aim_mark(self):
        fixture("unmatched_sniper_layout").execute('''
            tick();assert(optics.path=='native' and optics.profile==nil and optics.error==nil)
            assert(optics.fallbackReason=='No authored optical profile')
            assert(optics.diagnostics():find('path=native profile=none',1,true))
            assert(dotOn==0)
        ''')


class NativeReticleFallbackTests(unittest.TestCase):
    def test_unmatched_sniper_keeps_the_native_hud_in_both_callbacks(self):
        lua = fixture("unmatched_sniper_layout")
        load_crosshair(lua)
        lua.execute('''
            tick();crosshairTick()
            assert(optics.ShouldKeepNativeReticle(weapon))
            assert(crosshair.native and not crosshair.hidden and not crosshair.smart)
            assert(hudRoot.visible and activeWidget.visible and dotOn==0)
            hudRoot.visible=false;activeWidget.visible=false
            crosshairTick('OnCrosshairStateChange')
            assert(hudRoot.visible and activeWidget.visible and crosshair.hudScale==1)
        ''')

    def test_missing_layout_keeps_native_then_hides_it_after_recovery(self):
        lua = fixture()
        load_crosshair(lua)
        lua.execute('''
            missing.vr_optic_reticle_rear_panel=true;tick();crosshairTick()
            assert(crosshair.native and not crosshair.hidden and hudRoot.visible)
            missing.vr_optic_reticle_rear_panel=nil;tick();crosshairTick()
            assert(not optics.ShouldKeepNativeReticle(weapon))
            assert(not crosshair.native and crosshair.hidden and not hudRoot.visible)
            assert(dotOn==0)
        ''')

    def test_camera_and_shader_scopes_keep_native_crosshair_hidden(self):
        for profile, kind, mag, expected in (
            ("w_att__scope_sniper_01_010173", "sniper", 6, "camera"),
            ("w_att__scope_long_05_01", "rifle", 2.35, "shader"),
        ):
            with self.subTest(path=expected):
                lua = fixture(profile)
                load_crosshair(lua)
                lua.globals().weaponType = kind
                lua.globals().magnification = mag
                lua.execute('''
                    tick();crosshairTick()
                    assert(not crosshair.native and crosshair.hidden)
                    assert(not hudRoot.visible and not activeWidget.visible and dotOn==0)
                ''')
                self.assertEqual(lua.globals().optics.path, expected)

    def test_smart_sniper_keeps_existing_hud_scale(self):
        lua = fixture("unmatched_smart_sniper")
        load_crosshair(lua)
        lua.execute('''
            weaponEvolution='smart';tick();crosshairTick()
            assert(crosshair.smart and not crosshair.hidden and crosshair.hudScale==0.4)
            assert(hudRoot.visible and activeWidget.visible and crosshair.scaled==7)
            assert(activeWidget.children[1].children[1].scale.X==0.4 and dotOn==0)
            weaponAim=false;crosshairTick()
            assert(not crosshair.hidden and crosshair.smart and crosshair.hudScale==0.4)
        ''')

    def test_previous_weapon_and_holster_cannot_reuse_a_native_decision(self):
        lua = fixture("unmatched_sniper_layout")
        load_crosshair(lua)
        lua.execute('''
            tick();crosshairTick();assert(crosshair.native)
            other=setmetatable({GetEntityID=function()return {hash=43}end,
                GetComponents=function()return {}end},{__index=weapon})
            Game.FindEntityByID=function(id)if id.hash==42 then return weapon else return other end end
            activeWeapon=other;crosshairTick()
            assert(not crosshair.native and crosshair.hidden)
            assert(not optics.ShouldKeepNativeReticle(other))
            tick();crosshairTick();assert(crosshair.native)
            assert(not optics.ShouldKeepNativeReticle(weapon))
            activeWeapon=nil;crosshairTick()
            assert(not crosshair.native and crosshair.hidden)
            tick();assert(not optics.ShouldKeepNativeReticle(other))
            activeWeapon=other;crosshairTick()
            assert(not crosshair.native and crosshair.hidden)
        ''')

    def test_disabled_optics_cannot_keep_a_stale_native_hud(self):
        lua = fixture("unmatched_sniper_layout")
        load_crosshair(lua)
        lua.execute('''
            tick();crosshairTick();assert(crosshair.native)
            optics.enabled=false;crosshairTick()
            assert(not crosshair.native and crosshair.hidden)
        ''')


if __name__ == "__main__":
    unittest.main()
