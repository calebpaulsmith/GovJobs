"""Export helpers for tables shown in the Streamlit app."""
from __future__ import annotations

from io import BytesIO

import pandas as pd


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def dataframe_to_xlsx_bytes(
    df: pd.DataFrame,
    *,
    sheet_name: str,
    title: str | None = None,
) -> bytes:
    output = BytesIO()
    safe_sheet = _safe_sheet_name(sheet_name)
    startrow = 2 if title else 0
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=safe_sheet, index=False, startrow=startrow)
        worksheet = writer.sheets[safe_sheet]
        if title:
            worksheet.cell(row=1, column=1, value=title)
            worksheet.cell(row=1, column=1).style = "Title"
        if not df.empty:
            worksheet.freeze_panes = worksheet.cell(row=startrow + 2, column=1)
            for idx, column in enumerate(df.columns, start=1):
                values = [str(column), *(str(value) for value in df[column].head(500).fillna(""))]
                width = min(max(len(value) for value in values) + 2, 60)
                worksheet.column_dimensions[worksheet.cell(row=1, column=idx).column_letter].width = width
    return output.getvalue()


def _safe_sheet_name(name: str) -> str:
    invalid = set("[]:*?/\\")
    cleaned = "".join("_" if char in invalid else char for char in name).strip()
    return (cleaned or "Export")[:31]
