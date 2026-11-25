from .core import check as inspect_value
from . import core


def run(value):
    return inspect_value(value) + core.helper(value)
