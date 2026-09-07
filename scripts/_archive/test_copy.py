import copy

class BaseContext:
    def __init__(self, dict_=None):
        self.dicts = [{"True": True, "False": False, "None": None}]
        if dict_ is not None:
            self.dicts.append(dict_)

    def __copy__(self):
        # Emulating the old Django code
        try:
            duplicate = copy.copy(super())
            duplicate.dicts = self.dicts[:]
        except AttributeError as e:
            print("Old way failed:", e)

        # New way
        duplicate = object.__new__(type(self))
        duplicate.__dict__ = self.__dict__.copy()
        duplicate.dicts = self.dicts[:]
        return duplicate

class Context(BaseContext):
    def __init__(self, dict_=None):
        super().__init__(dict_)
        self.render_context = {'foo': 'bar'}
    
    def __copy__(self):
        duplicate = super().__copy__()
        duplicate.render_context = copy.copy(self.render_context)
        return duplicate

c = Context({'a': 1})
c2 = copy.copy(c)
print(type(c2))
print(c2.dicts)
print(c2.render_context)
