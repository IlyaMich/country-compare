from __future__ import annotations

import pandas as pd

from country_compare.data.contract import ALL_COLUMNS, OPTIONAL_COLUMNS


def add_optional_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    for column in OPTIONAL_COLUMNS:
        if column not in result.columns:
            result[column] = None
    return result


def order_canonical_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    ordered_columns = [column for column in ALL_COLUMNS if column in dataframe.columns]
    remaining_columns = [column for column in dataframe.columns if column not in ordered_columns]
    return dataframe.loc[:, [*ordered_columns, *remaining_columns]].copy(deep=True)
