# Third-Party Data

Country Compare includes and processes datasets obtained from third-party data providers.

The Apache License 2.0 that applies to the Country Compare source code does **not** relicense third-party datasets contained in or used by this repository. Third-party data remains subject to the applicable terms, licenses, and attribution requirements of its original provider.

## World Bank Open Data

The raw datasets currently stored under `data/raw/` were obtained from World Bank Open Data.

At the time the datasets were added to this repository, the reviewed source datasets indicated the Creative Commons Attribution 4.0 International license (CC BY 4.0), unless otherwise indicated by the specific dataset.

World Bank licensing can vary by dataset. Some datasets may contain third-party material or may be made available under different license terms. The license and attribution requirements shown on the source dataset page should therefore be treated as authoritative for each individual dataset.

### Attribution

Unless a specific source dataset specifies otherwise, attribution for the World Bank source data should identify:

- World Bank Open Data as the source.
- The applicable dataset or indicator where practical.
- The applicable data license.
- Any modifications or transformations made to the source data where required by the applicable license.

A suitable general attribution for datasets confirmed to be covered by CC BY 4.0 is:

> Source: World Bank Open Data. Licensed under Creative Commons Attribution 4.0 International unless otherwise indicated by the source dataset.

## Processed and Derived Data

Country Compare may transform raw source datasets into normalized, filtered, combined, or otherwise processed forms for use by the application.

Processing a third-party dataset does not remove or replace the license or attribution requirements applicable to the underlying source data. Users redistributing processed or derived datasets should review the terms of the corresponding original data sources.

## Adding or Updating Data

Before adding, updating, or replacing a third-party dataset:

1. Verify the dataset's current license on the provider's source or metadata page.
2. Confirm that redistribution in this repository is permitted.
3. Record any required attribution.
4. Record any restrictions, additional terms, or third-party rights.
5. Update this file or the relevant data-directory documentation if the license differs from the general terms described above.

For additional information about the raw World Bank files currently included in the repository, see [`data/raw/README.md`](data/raw/README.md).