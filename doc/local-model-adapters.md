# Exact-model local LAN adapters / 精确型号本地适配

This fork adds model-specific adapters while retaining `midea-lan==2026.10.0`
for discovery, authentication, encryption and LAN transport. All other models
continue through the upstream selector. No cloud request is made by these adapters.

| Appliance              | Type / model / subtype | Added capabilities                                                                                                                                              |
| ---------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CWS-F08 softener       | ED / 6360000F / 845    | Salt, available soft water, usage, flow, regeneration status and alarms; softening, chlorine sterilization, hardness 1–999 ppm, regeneration interval 0–15 days |
| CAX250GC1M ventilation | AC / 24297131 / 1      | Independent intake/exhaust, sterilization, temperature, filter used/remaining; heat exchange 1, strong 7, holiday 8, auto 4                                     |
| CWGR-A1 dispenser      | ED / 6320088A / 1046   | Three temperature and volume presets, display timeout, presence wake, current quantity preset; existing power/child lock and telemetry                          |

The ventilation mode setter additionally requires the appliance to report
`special_machine_type=1`. Dedicated C003 controls do not send AC thermostat commands.
Unsupported softener regeneration and dispenser dispensing/heating/draining/
sterilizing/cooling commands are rejected. Settings are reported only after device
acknowledgement; there is no optimistic state update.

## Private vendor codecs are required

The three model codecs were obtained from an existing appliance integration cache.
No redistribution grant was found in those files. They are **not included in this
repository or covered by its MIT license**. Obtain the exact versions below from
your own authorized local cache. Do not open an issue or PR containing the codecs,
serial numbers, tokens, keys or household audit dumps.

Place your private files under the Home Assistant configuration directory:

```text
/config/.storage/midea_ac_lan/model_lua/
  T_0000_ED_6360000F_2024090502.lua
  T_0000_AC_24297131_2024112901.lua
  T_0000_ED_6320088A_2025032701.lua
```

`/config` is an example; use your actual HA configuration directory. Only the
codec for a configured exact model is needed. This location survives replacement
of `custom_components/midea_ac_lan`. The original local-patch location
`custom_components/midea_ac_lan/model_lua/` remains a fallback for migration,
but should be moved to `.storage` before upgrading. The adapter never downloads
codecs or sends appliance information to obtain them. A missing codec causes
that device's setup to fail with the required filename and location in the log;
unrelated models do not load Lua.

Only load trusted files. Lua executes local code: disabling Python access and
removing filesystem/process globals after initialization is defense in depth,
not a security sandbox for untrusted scripts. `bit.lua` (David Manura) and
`cjson.lua` (rxi JSON compatibility module) are shipped with their original MIT
notices intact. Their licenses do not grant rights to the three vendor codecs.

## Installation / 安装与升级

This is a personal fork branch, not an upstream release. Back up the existing
integration directory, HA configuration and private codec directory first.

1. Check out `codex/local-model-adapters` from this fork, or download that branch's
   archive. Copy its complete `custom_components/midea_ac_lan` directory into your
   HA `custom_components` directory. Do not install just `local_models.py`.
2. Supply the matching private Lua files in the directory above. On an existing
   patched installation, copy those files to `.storage` **before** replacing the
   old integration directory.
3. Restart HA. Its manifest installs `midea-lan==2026.10.0` and `lupa>=2.0`.
   Lupa must provide `lupa.lua51` on the HA host architecture. Dependency or codec
   load failures are visible in the HA log; do not silently fall back to generic
   controls for these exact models.
4. Keep existing device config entries, IDs and credentials. Open each device's
   integration options to enable desired extra entities. Existing `f08_*`,
   `a1_*` and ventilation attribute keys are preserved. Disabled historical
   entities may remain in HA's entity registry; this code does not delete them.
5. Verify telemetry first. Do not use dispensing, heating or regeneration as an
   installation smoke test. Updating this fork does not disable Cloud entries;
   any duplicate-device migration remains a separate user configuration step.

For subsequent updates, replace the integration directory from the chosen fork
commit, retain `.storage/midea_ac_lan/model_lua`, then restart HA. Avoid an upstream
HACS update replacing the fork. For rollback, restore the previous complete
integration directory and restart; keep private codecs and configuration backups.

厨房空调的标准 LAN 配置修正、按设备停用 Cloud、实体启用选项属于现有 HA
实例配置，不写入公共仓库。冰箱和耗电统计不属于此次适配范围。此次仓库迁移
未操作正在运行的 HA，也没有重新发送出水、加热或再生命令。

## Exact dispenser ranges / 管线机设置范围

- Temperatures: slot 1 = 35–45 °C; slots 2/3 = 35–99 °C; step 1 °C.
- Volume slot 1: 50/100/150 mL.
- Volume slot 2: 150/200/250/300/400/500 mL.
- Volume slot 3: 300/400/500/600/700 mL.
- Display timeout: 10/30/60/120/180/300 seconds.
- Current quantity: 0 disables the preset; 1/2/3 select slots. Legacy codes 21–25
  are rejected. Selecting a preset does not dispense water.
- Preset volumes use 10 mL protocol units. Existing `water_consumption / 1000`
  conversion is retained for history continuity; it is not a physical calibration.

## Offline verification

```bash
uv sync --locked
uv run pytest
# Optional, on a machine holding your private codecs; still no appliance I/O:
MIDEA_TEST_CODEC_DIR=/absolute/private/model_lua uv run pytest
```

Public tests cover exact dispatch, control allowlists/ranges, no optimistic state,
first-status gating, state mapping, external codec loading, frame validation and
shared exclusion-list isolation. Seven optional tests replay synthetic packets
through the actual vendor codecs, check TLV tags/C003 masks and require no network.
The committed fixtures contain synthetic status dictionaries, not household dumps.
CI skips only the optional vendor tests when the files are unavailable.

The previous local deployment had on-device verification of all nine dispenser
settings and ventilation mode/sterilization/exhaust changes with readback and
restoration. This records prior validation scope, not a new hardware test of this
refactor. Offline tests cannot establish physical water-volume accuracy or prove
behavior on other firmware/model combinations.
