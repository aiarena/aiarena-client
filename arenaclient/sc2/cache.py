from functools import wraps

def property_cache_forever(f):
    @wraps(f)
    def inner(self):
        property_cache = "_cache_" + f.__name__
        cache_updated = hasattr(self, property_cache)
        if not cache_updated:
            setattr(self, property_cache, f(self))
        cache = getattr(self, property_cache)
        return cache

    return property(inner)


def property_immutable_cache(f):
    """ This cache should only be used on properties that return an immutable object """

    @wraps(f)
    def inner(self):
        if f.__name__ not in self.cache:
            self.cache[f.__name__] = f(self)
        return self.cache[f.__name__]

    return property(inner)
