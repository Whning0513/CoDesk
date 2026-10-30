"""Scorer-only values. Never stage this module in an Actor Guest."""

SCENE_NAME = "Lamp_Lite_Review"
OBJECT_NAMES = frozenset({"Lamp_Base", "Lamp_Bulb", "Lamp_Shade", "Camera_Main"})
INITIAL_SHADE_WIDTH_M = 1.20
TARGET_SHADE_WIDTH_M = 1.46
SHADE_HEIGHT_M = 0.60
BULB_WIDTH_M = 0.50
MIN_RADIAL_CLEARANCE_M = 0.40
TARGET_RADIAL_CLEARANCE_M = (TARGET_SHADE_WIDTH_M - BULB_WIDTH_M) / 2
PROTECTED_OBJECTS = ("Lamp_Base", "Lamp_Bulb", "Camera_Main")
