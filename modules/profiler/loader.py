import io
import pandas as pd
from pathlib import Path

class InvalidSpreadsheetError(ValueError):
    pass

READ_OPTS = dict(dtype = str, keep_default_na = False)

def load_table(file_bytes: bytes, filename: str):
    """Checks if the filetype is correct and within csv, tsv and excel"""

    extension = Path(filename).suffix.lower()
    buffer = io.BytesIO(file_bytes)

    try:
        if extension in {".csv", ".tsv"}:
            delimiter = "\t" if extension == ".tsv" else ","
            data = None
            for encoding in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    data = pd.read_csv(buffer, sep = delimiter, encoding = encoding, **READ_OPTS)
                    break
                except UnicodeDecodeError:
                    continue
            if data is None:
                raise InvalidSpreadsheetError("Could not decode the file's text encoding.")


        elif extension == ".xlsx":
            data = pd.read_excel(buffer, engine = "openpyxl", **READ_OPTS)

        elif extension == ".xls":
            data = pd.read_excel(buffer, engine = "xlrd", **READ_OPTS)

        else:
            raise InvalidSpreadsheetError(
                f"Unsupported file type '{extension or 'unknown'}'. Please upload a .csv, .tsv or excel file"
            )

    except InvalidSpreadsheetError:
        raise

    except pd.errors.EmptyDataError:
        raise InvalidSpreadsheetError("The file has no content")
    except Exception as e:
        raise InvalidSpreadsheetError(f"Could not parse {filename}: {e}")

    if data.empty:
        raise InvalidSpreadsheetError(
            "The uploaded spreadsheet has headers but no data rows"
        )

    return data
