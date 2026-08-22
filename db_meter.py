import math

# --- SPL calibration: NiceHCK NK1 Max + Kiwi Ears Belle ---
AMP_MAX_OUTPUT_VRMS = 1.42          # NK1 Max: 63mW @ 32Ω → V = sqrt(P×R)
HEADPHONE_SENSITIVITY_DB_MW = 103.0    # Kiwi Ears Belle: 103dB @ 1kHz
HEADPHONE_IMPEDANCE_OHMS = 32.0        # Kiwi Ears Belle

METER_FLOOR_DBFS = -90.0
OK_LVL = 70.0
DANGER_LVL = 80.0

_meter_rms_dbfs = METER_FLOOR_DBFS

def on_af_metadata_change(name, value):
  global _meter_rms_dbfs
  if not value:
    return

def draw_level_meter(surface, x, y, font):
  spl=_spl_smoothed
  if spl>=DANGER_LVL:
    label, color = f"{spl:.0f} dB!", (230, 70, 60)
    
