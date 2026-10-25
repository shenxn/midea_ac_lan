# Local protocol maintenance notes

Offsets below are zero-based. This document describes the native subset used by
this fork, not a general Midea protocol specification. Do not add writable fields
solely because a vendor script or another model mentions them.

## Frames

UART packets consist of a ten-byte header, a body and one checksum byte. Byte 0
is AA, byte 1 is total length minus one, byte 2 is the appliance type, and byte 9
is the message type. The sum of bytes 1 through the checksum must be zero modulo 256. AC requests use header byte 8 = 02; ED uses 00.

The AC body is a JZ envelope: `AA length 00 address FF command payload CRC sum`.
Its length includes both checksums. CRC-8 uses the reflected polynomial 8C,
initial value zero, over the envelope before the CRC. The final byte makes the
sum of the whole envelope zero modulo 256. General/run queries use address FF;
C003 requests use the model's address (zero in the verified default).

## ED status and controls

Status body: `FF 01 category`, followed by records. A record has two header bytes:
`id_low`, then `(value_length << 4) | id_high`; value bytes follow. Numbers are
little endian. Unknown records can be skipped; known records must have enough
bytes for every exposed field. Extra record bytes are permitted.

Selected record groups:

| IDs                   | Meaning                                                         |
| --------------------- | --------------------------------------------------------------- |
| 000 / 001             | Dispenser flags / fault code                                    |
| 011 / 020             | Water usage / water kind                                        |
| 021 / 023             | Temperature presets / volume presets and current slot           |
| 036 / 048 / 207       | Display timeout / presence wake / signed inlet temperature      |
| 901–907               | Flow, available soft water, usage and salt                      |
| 909–90D               | Protection thresholds, hardness, schedule and remaining seconds |
| 90F / 910 / 911 / 914 | Alarms, counters, operating flags and softening                 |

Control body: `15 01 01`, a two-byte little-endian command ID and three value
bytes. Exactly one command is emitted. Representative command IDs are 0900
(hardness), 0901 (interval), 0906 (softening), 090C (chlorine sterilization),
0108 (timeout), 0118 (presence wake), 0202 (volume slot), 020D (current slot),
0401 (temperature slot). Status record IDs and command IDs are different namespaces.
Temperature slots use selectors 10/11/12; volume slots use 1/2/3 and 10 mL units.

Only ED outer message types 03 and 04 with FF/01 bodies provide status. Control
acknowledgements of other types do not optimistically update HA.

## Dedicated ventilation

Polling uses general command 11, running command 10 with selector 01, and C003
command C0 with `pack_id 01 C0 03`.

General status carries master power at payload byte 4 bit 3, mode at byte 15,
sterilization at byte 36 bit 7, intake/exhaust switches at byte 55 bits 5/6,
model type at byte 61 and seven-bit intake/exhaust speeds at bytes 62/63.
Running status carries signed hundredths of a degree at bytes 7–8 (indoor) and
61–62 (outdoor), dedicated-model identity at byte 58 bits 4–6 and used filter
percentage at byte 63. Missing extension fields do not reset earlier measurements.

C003 status contains its marker at payload bytes 1–3. Model type is byte 6;
power/sterilization/intake/exhaust flags are bits 0–3 of byte 9; mode is the low
five bits of byte 10; speeds are the low seven bits of bytes 11/12.

The control payload is 31 bytes. Bytes 11–14 are `01 C0 03 13`. Bytes 17/18
are enable/value masks for the four flags. Mode at byte 19 and intake/exhaust
speeds at bytes 20/21 use bit 7 as their enable flag. Unrelated fields remain
zero. Byte 30 balances the sum of bytes 12–30. The payload is then wrapped in
JZ and UART envelopes. Changing mode must not enable either fan or power bit.

The adapter rejects modes outside 1/4/7/8 and requires a prior running-status
confirmation of `special_machine_type=1` before a mode change. State updates
always come from received device frames.
