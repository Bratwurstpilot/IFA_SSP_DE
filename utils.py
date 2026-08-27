import pandas as pd


def safe_int_conversion(value, default=0):
    if pd.isna(value):
        return default
    return int(value)
