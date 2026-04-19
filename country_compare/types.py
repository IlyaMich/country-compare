from typing import Literal

NormalizationMethod = Literal["minmax", "percentile", "rank", "log_minmax"]
MissingDataPolicy = Literal["drop", "renormalize"]
YearStrategy = Literal["latest_per_metric", "target_year", "common_year"]
