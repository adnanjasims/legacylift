#py2.7 sample. xrange and print. Division uses floats so 2to3 keeps behaviour.

def add_tax(cents, rate_percent):
    return cents + cents * rate_percent / 100.0


def bulk_prices(unit_cents, qty):
    prices = []
    for i in xrange(1, qty + 1):
        prices.append(add_tax(unit_cents * i, 8.0))
    return prices


def label(sku):
    print "sku", sku
    return "sku-%s" % sku
