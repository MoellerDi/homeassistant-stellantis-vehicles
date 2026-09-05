"""VIN-based brand and model lookup for Stellantis vehicles.

The Stellantis connected-car API returns a vehicle's VIN, motorization and
brand, but no human-readable model name (e.g. "3008", "Corsa-e"). Stellantis
does not publish the VDS (VIN positions 4-8) decode table for its brands, so
there is no way to derive the model automatically. VIN_MODELS below is a
manually curated lookup that grows as users confirm their own vehicle's
model against its VIN (e.g. from the registration document) and add an
entry here.

VIN layout (17 characters), for reference
==========================================

Position  1-3   WMI (World Manufacturer Identifier) - manufacturer/brand + country.
Position  4-8   VDS (Vehicle Descriptor Section)     - model, body, engine/drivetrain.
                Manufacturer-specific and not publicly standardized - Stellantis
                does not publish an open table for it.
Position  9     Check digit
Position  10    Model year code (letter/number)
Position  11    Assembly plant
Position 12-17  Serial number

WMI examples for Stellantis brands
-----------------------------------

  VF3          Peugeot          (France)
  VF7          Citroën          (France)
  VR1          DS Automobiles
  W0L / W0V    Opel             (Germany)
  ZFA          Fiat             (Italy)
  ZAR          Alfa Romeo
  ZLA          Lancia
  1C3/1C4/1C6  Chrysler/Jeep/Ram (USA)
  2C4 / 3C4    Chrysler         (Canada/Mexico)
"""

# World Manufacturer Identifier (VIN positions 1-3) -> brand. Used only as a
# fallback for the "manufacturer" device info field when the API's own
# "brand" field is unavailable for a vehicle.
WMI_BRANDS = {
    "VF3": "Peugeot",
    "VF7": "Citroën",
    "VR7": "Citroën",
    "VR1": "DS Automobiles",
    "W0L": "Opel",
    "W0V": "Opel",
    "ZFA": "Fiat",
    "ZAR": "Alfa Romeo",
    "ZLA": "Lancia",
    "VXK": "Opel",
    "1C3": "Chrysler",
    "1C4": "Jeep",
    "1C6": "Ram",
    "2C3": "Chrysler",
    "2C4": "Chrysler",
    "3C4": "Chrysler",
    "3C6": "Ram",
}

# VIN prefix (WMI + VDS, i.e. positions 1-8) -> model name. Since Stellantis
# does not publish this mapping, entries are only added once confirmed
# (owner-stated model matching a real VIN prefix). Add further confirmed
# entries as:
#   "VR7BC5NZ": "ë-C4",
VIN_MODELS: dict[str, str] = {
    "VR3UHZKX": "Peugeot e-208",
    "VR3F4DGZ": "Peugeot 508 SW",
    "VR3KCZKZ": "Peugeot E-3008",
    "VR7BCZKX": "Citroën ë-C4",
    "VR7CBZYA": "Citroën ë-C3",
    "VXKF3DGY": "Opel Astra GSe",
    "VR7BCZKW": "Citroën ë-C4",
}


def get_brand_from_vin(vin: str) -> str | None:
    """Return the brand for a VIN's WMI, if known."""
    return WMI_BRANDS.get(vin[:3])


def get_model_from_vin(vin: str) -> str | None:
    """Return the model for a VIN, if a matching entry exists in VIN_MODELS."""
    return VIN_MODELS.get(vin[:8])
