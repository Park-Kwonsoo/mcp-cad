# Modify Model Tool Prompt

## tool_description

Use only for follow-up AI CAD revisions of an existing generated model by
model_id. Reads the latest stored CadQuery source, regenerates a new version,
exports a new STL, and preserves version history. Do not use this for arbitrary
existing STL resize/reposition operations; use transform_stl_mesh for raw STL
transforms.

## model_id_field

Existing AI-generated model id returned by generate_model or list_models;
required for source-level revisions.

## instruction_field

Source-level revision instruction for the latest stored AI model version. Use
for follow-up design changes by model_id, not for raw STL transforms or
supplied CadQuery scripts.

## repair_instruction_template

Fix this CadQuery execution/export error while preserving the requested model
intent: {error}

