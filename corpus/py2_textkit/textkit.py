#py2.7 sample. iteritems, has_key, except-comma, and print.

def invert(mapping):
    out = {}
    for key, value in mapping.iteritems():
        out[value] = key
    return out


def lookup(mapping, key):
    if mapping.has_key(key):
        return mapping[key]
    return None


def parse_pair(text):
    try:
        left, right = text.split(":")
        return left, right
    except ValueError, err:
        return "error", str(err)


def banner(name):
    print "textkit", name
    return "textkit:%s" % name
