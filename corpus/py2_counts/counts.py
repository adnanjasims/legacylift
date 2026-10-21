#py2.7 sample. Integer division is the behaviour 2to3 does not rewrite.

def half(n):
    return n / 2


def split_even(n):
    return n / 2, n - n / 2


def steps(n):
    total = 0
    for i in xrange(n):
        total = total + i / 2
    return total
