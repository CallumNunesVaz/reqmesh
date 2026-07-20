"""A small SI unit / dimension system for parametric dimensional checking.

SysML v2 types attributes with ISQ/SI value types; reqmesh parameters carry a
free-text ``unit``. This module maps common unit symbols to an SI **dimension**
(a 7-tuple of base-quantity exponents) so the evaluator can flag dimensionally
inconsistent expressions (e.g. ``mass + length``) as *warnings* — never as hard
failures, and never for unknown units.

Design choices that keep checking additive and quiet:
- Unregistered / empty units resolve to ``None`` (wildcard) → no checking.
- Numeric literals are dimension-agnostic (``None``) so the ubiquitous
  ``mass <= 1157`` pattern (quantity vs bare number) never warns.
- Only two *known, different* dimensions clashing raises a mismatch.
"""

from __future__ import annotations

from typing import Optional

# Base quantities, SI order: length, mass, time, current, temperature, amount, luminous.
Dimension = tuple[int, int, int, int, int, int, int]

_DIMLESS: Dimension = (0, 0, 0, 0, 0, 0, 0)
_L: Dimension = (1, 0, 0, 0, 0, 0, 0)
_M: Dimension = (0, 1, 0, 0, 0, 0, 0)
_T: Dimension = (0, 0, 1, 0, 0, 0, 0)
_I: Dimension = (0, 0, 0, 1, 0, 0, 0)
_TH: Dimension = (0, 0, 0, 0, 1, 0, 0)


def _mul(d: Dimension, n: int) -> Dimension:
    return tuple(x * n for x in d)  # type: ignore[return-value]


def _add(a: Dimension, b: Dimension) -> Dimension:
    return tuple(x + y for x, y in zip(a, b))  # type: ignore[return-value]


# symbol -> (factor to SI base, dimension). Factor is unused by dimensional
# checking today but kept for future unit conversion.
UNITS: dict[str, tuple[float, Dimension]] = {
    # dimensionless
    "": (1.0, _DIMLESS), "%": (0.01, _DIMLESS), "each": (1.0, _DIMLESS),
    "count": (1.0, _DIMLESS), "ea": (1.0, _DIMLESS), "rad": (1.0, _DIMLESS),
    "deg": (0.0174533, _DIMLESS),
    # length
    "m": (1.0, _L), "km": (1000.0, _L), "cm": (0.01, _L), "mm": (0.001, _L),
    "um": (1e-6, _L), "in": (0.0254, _L), "ft": (0.3048, _L), "yd": (0.9144, _L),
    "mi": (1609.344, _L), "nmi": (1852.0, _L),
    # mass
    "kg": (1.0, _M), "g": (0.001, _M), "mg": (1e-6, _M), "t": (1000.0, _M),
    "tonne": (1000.0, _M), "lb": (0.453592, _M), "oz": (0.0283495, _M),
    # time
    "s": (1.0, _T), "ms": (0.001, _T), "min": (60.0, _T), "h": (3600.0, _T),
    "hr": (3600.0, _T), "day": (86400.0, _T),
    # current, temperature
    "A": (1.0, _I), "mA": (0.001, _I), "kA": (1000.0, _I),
    "K": (1.0, _TH),
    # area / volume
    "m2": (1.0, _mul(_L, 2)), "m3": (1.0, _mul(_L, 3)), "L": (0.001, _mul(_L, 3)),
    # speed / acceleration
    "m/s": (1.0, _add(_L, _mul(_T, -1))), "km/h": (0.277778, _add(_L, _mul(_T, -1))),
    "kt": (0.514444, _add(_L, _mul(_T, -1))),
    "m/s2": (1.0, _add(_L, _mul(_T, -2))), "g0": (9.80665, _add(_L, _mul(_T, -2))),
    # force, pressure, energy, power, frequency, voltage
    "N": (1.0, _add(_M, _add(_L, _mul(_T, -2)))),
    "kN": (1000.0, _add(_M, _add(_L, _mul(_T, -2)))),
    "Pa": (1.0, _add(_M, _add(_mul(_L, -1), _mul(_T, -2)))),
    "kPa": (1000.0, _add(_M, _add(_mul(_L, -1), _mul(_T, -2)))),
    "MPa": (1e6, _add(_M, _add(_mul(_L, -1), _mul(_T, -2)))),
    "bar": (1e5, _add(_M, _add(_mul(_L, -1), _mul(_T, -2)))),
    "psi": (6894.76, _add(_M, _add(_mul(_L, -1), _mul(_T, -2)))),
    "J": (1.0, _add(_M, _add(_mul(_L, 2), _mul(_T, -2)))),
    "kJ": (1000.0, _add(_M, _add(_mul(_L, 2), _mul(_T, -2)))),
    "W": (1.0, _add(_M, _add(_mul(_L, 2), _mul(_T, -3)))),
    "kW": (1000.0, _add(_M, _add(_mul(_L, 2), _mul(_T, -3)))),
    "hp": (745.7, _add(_M, _add(_mul(_L, 2), _mul(_T, -3)))),
    "Hz": (1.0, _mul(_T, -1)),
    "V": (1.0, _add(_M, _add(_mul(_L, 2), _add(_mul(_T, -3), _mul(_I, -1))))),
}


class DimensionError(Exception):
    """Two known, incompatible dimensions were combined."""


def known_units() -> list[str]:
    """Registered unit symbols (for UI autocomplete)."""
    return [u for u in UNITS if u]


def dimension_of(unit: Optional[str]) -> Optional[Dimension]:
    """Dimension of a unit symbol, or ``None`` (wildcard) if unknown/empty."""
    if not unit:
        return None
    return UNITS.get(unit.strip(), (1.0, None))[1]


def combine(a: Optional[Dimension], op: str, b: Optional[Dimension]) -> Optional[Dimension]:
    """Resulting dimension of ``a op b``. ``None`` propagates as a wildcard.

    Raises DimensionError only when both operands are known and inconsistent
    for + / - (addition of unlike quantities).
    """
    if op in ("+", "-"):
        if a is not None and b is not None and a != b:
            raise DimensionError(f"cannot add/subtract unlike quantities: {a} vs {b}")
        return a if a is not None else b
    if op == "*":
        return _add(a, b) if (a is not None and b is not None) else None
    if op == "/":
        return _add(a, _mul(b, -1)) if (a is not None and b is not None) else None
    return None  # pow / other: don't attempt


def compare_dims(a: Optional[Dimension], b: Optional[Dimension]) -> None:
    """For a comparison; raise if both sides are known and different."""
    if a is not None and b is not None and a != b:
        raise DimensionError(f"comparing unlike quantities: {a} vs {b}")
