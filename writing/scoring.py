import math


def count_words(text):
    """Return the number of whitespace-separated tokens in the text."""
    return len((text or "").split())


def round_band(x):
    """Round to the nearest 0.5, using .25 -> .5 and .75 -> next whole."""
    return math.floor(float(x) * 2 + 0.5) / 2


def task_band(c1, c2, c3, c4):
    return round_band((float(c1) + float(c2) + float(c3) + float(c4)) / 4)


def writing_band(task1_band, task2_band):
    return round_band((float(task1_band) + 2 * float(task2_band)) / 3)
