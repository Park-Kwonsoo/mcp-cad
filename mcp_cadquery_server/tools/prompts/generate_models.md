# Generate Model Tool Prompt

## tool_description

Use only for new AI CAD generation from natural-language requirements or a
reference image when no CadQuery script or STL exists yet. The server
synthesizes CadQuery source, exports an STL, and stores the result under a
model_id for later modify_model iterations. If the user already has CadQuery
code, use execute_cadquery_script or build_and_export_stl; if the user has an
STL, use the STL tools.

## description_field

Natural-language requirements for a new AI-generated CadQuery model. Use when
no CadQuery script or STL exists yet and the server should synthesize source
code from the prompt.

## image_path_field

Optional local sketch, photo, screenshot, or reference image path for AI
source-code generation.

## model_id_field

Optional stable id for the new AI-generated model; future modify_model calls
can target this id.

## repair_instruction_template

Fix this CadQuery execution/export error while preserving the requested model
intent: {error}

