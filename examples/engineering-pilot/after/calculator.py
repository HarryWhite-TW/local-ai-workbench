def average(values):
    """Return arithmetic mean, or 0 for empty input."""
    if len(values) == 0:
        return 0
    return sum(values) / len(values)
