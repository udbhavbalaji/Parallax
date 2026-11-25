def helper(value):
    return value + 1


def check(value):
    return helper(value)


def recurse(value):
    return recurse(value - 1) if value else 0


class Worker:
    def run(self, value):
        return self.finish(value)

    def finish(self, value):
        return check(value)


def unknown(value):
    return missing(value)


def shadow(check):
    return check(1)
