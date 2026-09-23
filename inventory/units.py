"""
inventory/units.py

Normalises item units and computes human-friendly display units within a unit
family (mass: g <-> kg, volume: mL <-> L). Items outside a known family
(pcs, box, pack, btl, ...) are treated atomically - the quantity is just a
number in the item's own unit.

Every quantity is stored in the DB in the item's own `unit` column. Conversion
to a nicer display unit happens only at the display layer, so data and maths
are unaffected.

Families  prefix -> factor relative to the family's base (smallest) unit.
"""

from decimal import Decimal, ROUND_HALF_UP

# ── Unit families ────────────────────────────────────────────────────────────
MASS = {
    'mg': Decimal('0.001'),
    'g':  Decimal('1'),
    'kg': Decimal('1000'),
}

VOLUME = {
    'mL': Decimal('1'),
    'L':  Decimal('1000'),
}

FAMILIES = {
    'mass':   MASS,
    'volume': VOLUME,
}

ALIASES_BY_FAMILY = {
    'mass': {
        'mg': {'mg', 'milligram', 'milligrams'},
        'g':  {'g', 'gram', 'grams', 'gm', 'gm.', 'gms'},
        'kg': {'kg', 'kilo', 'kilos', 'kilogram', 'kilograms',
               'kilogramme', 'kilogrammes', 'kgs'},
    },
    'volume': {
        'mL': {'ml', 'milliliter', 'milliliters', 'millilitre',
               'millilitres', 'cc', 'cubic cm', 'cubic centimeter'},
        'L':  {'l', 'liter', 'liters', 'litre', 'litres', 'ltr', 'ltrs'},
    },
}

# Flat lookup: lowercase unit string -> (canonical, family)
LOOKUP = {}
for _family, _factors in ALIASES_BY_FAMILY.items():
    for _canonical, _aliases in _factors.items():
        for _a in _aliases:
            LOOKUP[_a] = (_canonical, _family)


def normalize_unit(unit):
    """Return the canonical unit string (e.g. 'g', 'kg', 'mL') or None for
    unknown / blank units, or the raw normalised text if not in a family."""
    if not unit:
        return None
    key = str(unit).strip().lower().rstrip('.')
    if not key:
        return None
    hit = LOOKUP.get(key)
    return hit[0] if hit else key


def lookup(unit):
    """Return (canonical, family) or (None, None) for non-family units."""
    key = normalize_unit(unit)
    if not key:
        return (None, None)
    hit = LOOKUP.get(key.lower())
    return (hit if hit else (None, None))


def is_convertible(unit):
    """True when the unit belongs to a family with meaningful prefix swaps."""
    _, family = lookup(unit)
    return family is not None


def conversion_factor(display_unit, stored_unit):
    """Factor such that: amount_in_stored_unit = amount_in_display_unit * factor.

    Solved from the family base so any pair in the same family works
    (e.g. health kg -> g returns 1000). Unrelated units return 1.
    """
    d, dfam = lookup(display_unit)
    s, sfam = lookup(stored_unit)
    if d is None or s is None or dfam != sfam:
        return Decimal('1')
    return FAMILIES[dfam][d] / FAMILIES[sfam][s]


def auto_display(value, unit):
    """Given a value expressed in the item's stored `unit`, pick the most
    readable unit within the family and return (display_value, display_unit).

    Rule: among the family prefixes, choose the largest one for which the
    converted value is still >= 1. So 1500 g -> 1.5 kg, 500 g -> 500 g.
    Unknown / atomic units return the value unchanged.
    """
    canonical, family = lookup(unit)
    if canonical is None or family is None:
        return Decimal(value), (normalize_unit(unit) or unit or 'pcs')

    factors = FAMILIES[family]
    try:
        base_value = Decimal(str(value)) * factors[canonical]
    except Exception:
        return Decimal(value), canonical

    best = canonical
    for cand in sorted(factors, key=lambda c: factors[c]):
        if base_value / factors[cand] >= 1:
            best = cand

    try:
        display_value = base_value / factors[best]
        display_value = display_value.quantize(Decimal('0.001'),
                                               rounding=ROUND_HALF_UP)
    except Exception:
        display_value = base_value

    return display_value, best


def qty_step(unit):
    """Smallest useful increment for a borrow qty input, in display units."""
    _, family = lookup(unit)
    return Decimal('0.1') if family else Decimal('1')


def unit_options_for(unit):
    """Possible display units for an item, smallest prefix first.

    Returns [{unit, factor}] where `factor` converts a value in `unit` to the
    item's stored `unit`. Items outside a known family get a single option so
    the UI can still show the unit without a useless chooser.
    """
    canonical, family = lookup(unit)
    if canonical is None or family is None:
        stored = normalize_unit(unit) or unit or 'pcs'
        return [{'unit': stored, 'factor': 1.0}]
    return [
        {
            'unit': cand,
            'factor': float(FAMILIES[family][cand] / FAMILIES[family][canonical]),
        }
        for cand in sorted(FAMILIES[family], key=lambda c: FAMILIES[family][c])
    ]