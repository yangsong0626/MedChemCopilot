# Architecture

The application is organized around project iteration:

1. Import measured potency and ADMET data.
2. Normalize compounds and assay properties.
3. Train or refresh project/property models.
4. Generate or import candidate designs.
5. Predict properties for designs.
6. Rank candidates against project goals.
7. Present ranked designs to chemists.
8. Capture feedback and include it in the next iteration.

## Boundaries

- Measured data is stored in `AssayResult` and `ADMETResult`.
- Candidate molecules are stored in `Design`.
- Predicted values are stored in `Prediction`.
- Ranking outputs are stored in `DesignRank`.
- Model metadata and metrics are stored in `ModelRun`.
- Chemist decisions are stored in `DesignFeedback`.

This keeps auditability and model provenance visible from the first version.

