default_app_config = 'inventory.InventoryConfig'

# ── Python 3.14 compatibility fix ────────────────────────────────────────────
# Python 3.14 broke copy(super()) which Django 4.2's BaseContext.__copy__
# relies on. The original code does copy(super()) to shallow-clone the context
# object. In 3.14, copy() on a super() proxy no longer returns a usable clone.
# We fix BaseContext.__copy__ to shallow-copy via __dict__ instead.
import sys
if sys.version_info >= (3, 14):
    from copy import copy as _copy, deepcopy as _deepcopy
    from django.template.context import BaseContext

    def _BaseContext__copy__(self):
        duplicate = object.__new__(type(self))
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = _BaseContext__copy__

    # RenderContext.__copy__ calls copy(super()) too
    from django.template.context import RenderContext

    def _RenderContext__copy__(self):
        duplicate = object.__new__(type(self))
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    RenderContext.__copy__ = _RenderContext__copy__