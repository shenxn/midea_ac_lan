# Exact-model local LAN adapters / 精确型号本地适配

This fork adds native Python codecs for three exact models while retaining
`midea-lan==2026.10.0` for discovery, authentication, encryption and LAN transport.
All other models continue through the upstream selector. The adapters do not
request cloud services, load vendor Lua files or require `lupa`.

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

## Native protocol / 原生 Python 协议

`local_protocol.py` implements the wire formats needed by these adapters:

- ED: FF/01 status records, 12-bit field identifiers, four-bit value lengths,
  little-endian numbers and flag fields; 15/01 single-setting control records.
- AC: JZ envelopes inside UART frames, Dallas/Maxim CRC-8 and additive checksums,
  general status, running status and dedicated C003 ventilation status/control.
- UART: device type, frame length, supported response types and checksum checks.

This is a deliberately bounded implementation of the currently exposed fields,
not a general port of every feature in the large vendor scripts. Unknown ED
records are skipped by their declared length. Malformed or truncated frames are
rejected as a whole, with no partial state update. AC status updates include only
fields carried by that response: a C003 acknowledgement cannot reset temperatures,
filter life or the dedicated-model confirmation from a running-status response.

The previous Lua adapter is replaced entirely. There is no fallback runtime, no
script download and no dependency on the original private files. Old private
files in `.storage/midea_ac_lan/model_lua` or the integration's `model_lua`
subdirectory are ignored; keep them with backups if you need to roll back to the
previous commit. The native implementation does not delete them.

## Installation / 安装与升级

This is a personal fork branch, not an upstream release. Back up the existing
integration directory and HA configuration first.

1. Check out `codex/local-model-adapters` from this fork, or download that branch's
   archive. Replace the complete `custom_components/midea_ac_lan` directory in
   your HA configuration. Install `local_protocol.py` together with the other
   files; do not install just `local_models.py`.
2. Restart HA. The manifest requires only `midea-lan==2026.10.0`; no additional
   Lua files, Lua runtime or native extension installation is needed.
3. Keep existing config entries, device IDs and credentials. Open each device's
   integration options to enable desired extra entities. Existing `f08_*`,
   `a1_*` and ventilation attribute keys are preserved. Historical disabled
   entities may remain in HA's entity registry; this code does not delete them.
4. Verify telemetry first. Do not use dispensing, heating or regeneration as an
   installation smoke test. Updating this fork does not disable Cloud entries;
   any duplicate-device migration remains a separate user configuration step.

For subsequent updates, replace the integration directory from the chosen fork
commit, then restart HA. Avoid an upstream HACS update replacing the fork. For
rollback, restore the previous complete integration directory and its required
private codecs if returning to the Lua version, then restart HA.

厨房空调的标准 LAN 配置修正、按设备停用 Cloud、实体启用选项属于现有 HA
实例配置，不写入公共仓库。冰箱和耗电统计不属于此次适配范围。此次 Python
改写与测试未操作正在运行的 HA，也没有发送出水、加热或再生命令。

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

## Offline verification / 离线验证

```bash
uv sync --locked
uv run pytest
```

All tests run without Lua, private files or device connections, including CI.
`tests/fixtures/local_protocol.json` contains synthetic golden vectors checked
against the previous private codecs. It contains no household captures or device
identifiers. The reference codec versions were:

- ED / 6360000F: 2024090502
- AC / 24297131: 2024112901
- ED / 6320088A: 2025032701

During development, 1,618 control operations were compared byte for byte against
Lua: every allowed integer hardness, regeneration interval, temperature and fan
speed, every volume/timeout/preset choice, both states of every supported switch,
and ventilation addressing variants. Query packets were compared before and
after control. The checked-in vectors retain representative values and boundaries.
121 synthetic response cases cover every exposed field, mixed records, zero,
high-bit and seeded random payloads. Tests also cover every truncated prefix and
single-byte corruption of each response, inner checksums, unknown fields,
unsupported commands, partial updates, exact model dispatch and shared exclusion
lists. See [wire format notes](local-protocol.md) for maintenance details.

The previous Lua deployment had on-device verification of all nine dispenser
settings and ventilation mode/sterilization/exhaust changes with readback and
restoration. That is historical evidence for the protocol, not a hardware test
of the new Python implementation. Offline equivalence does not establish physical
water-volume accuracy or prove behavior on other firmware/model combinations.
