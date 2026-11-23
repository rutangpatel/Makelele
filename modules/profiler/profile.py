import re
import pandas as pd
from modules.profiler.loader import load_table
from pathlib import Path

NULL_TOKENS = {"", "NA", "N/A", "NULL", "NONE", "NAN", "-", "--", "—", "?", "MISSING", "#N/A"}

def shape(val: str):
    val = re.sub(r"\d+", "9", val)
    val = re.sub(r"[A-Z]+", "A", val)
    return re.sub(r"[a-z]+", "a", val)

def create_profile(data: pd.DataFrame, max_rows: int = 50_000):
    sample = data.sample(max_rows, random_state = 0) if len(data) > max_rows else data
    columns = {}
    for column in data.columns:
        s = sample[column].fillna("").astype(str).str.strip()
        isnull = s.str.upper().isin(NULL_TOKENS)
        vals = s[~isnull]
        shapes = vals.map(shape)
        columns[str(column)] = {
            "null_percentage": float(round(100 * isnull.mean(), 1)),
            "null_tokens": sorted(set(s[isnull])),
            "unique": int(vals.nunique()),
            "top_shape": {
                s: {"count": int(c), "examples": vals[shapes == s].head(3).tolist()}
                for s, c in shapes.value_counts().head(5).items()
            },
            "samples": vals.drop_duplicates().head(5).tolist(),
            "top_values": {k: int(v) for k, v in vals.value_counts().head(5).items()}
        }

    return {
        "rows": len(data),
        "duplicate_rows": int(data.duplicated().sum()),
        "first_rows": data.head(3).astype(str).values.tolist(),
        "last_rows": data.tail(3).astype(str).values.tolist(),
        "columns": columns
    }
