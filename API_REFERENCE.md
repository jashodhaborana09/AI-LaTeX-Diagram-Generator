# API Reference

All API responses are JSON. Unexpected server errors are logged internally and return safe client-facing messages.

## Health

### `GET /health`

Returns service metadata and readiness state.

```bash
curl http://127.0.0.1:5000/health
```

```json
{
  "status": "healthy",
  "service": "AI LaTeX Diagram Generator",
  "model": "IBM Granite 4 H Small",
  "version": "1.0.0"
}
```

## Generate

### `POST /generate`

Generates TikZ, PDF, and PNG artifacts from a natural-language prompt.

```bash
curl -X POST http://127.0.0.1:5000/generate \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Draw a simple API to database architecture diagram.\"}"
```

Request body:

```json
{
  "prompt": "Draw a simple API to database architecture diagram."
}
```

Success response:

```json
{
  "success": true,
  "tikz": "\\begin{tikzpicture}\n\\node[draw] {API};\n\\end{tikzpicture}",
  "pdf": "/generated/pdf/diagram.pdf",
  "png": "/generated/images/diagram.png",
  "tex": "/generated/latex/diagram.tex",
  "job_id": "diagram",
  "message": "Generation successful"
}
```

Validation errors:

- `400`: Missing, empty, whitespace-only, or oversized prompt.
- `415`: Request body is not JSON.
- `429`: Rate limit exceeded.

## Upload

### `POST /upload`

Uploads a PNG, JPG, or JPEG reference image.

```bash
curl -X POST http://127.0.0.1:5000/upload \
  -F "file=@diagram.png"
```

Success response:

```json
{
  "success": true,
  "filename": "diagram-abc123.png",
  "message": "Upload successful"
}
```

Validation errors:

- `400`: Missing file field, filename, or empty file.
- `413`: File exceeds `MAX_UPLOAD_SIZE`.
- `415`: Unsupported image extension.
- `429`: Rate limit exceeded.

## Refine

### `POST /refine`

Refines existing TikZ with a natural-language instruction.

```bash
curl -X POST http://127.0.0.1:5000/refine \
  -H "Content-Type: application/json" \
  -d "{\"instruction\":\"Move the database node left\",\"tikz\":\"\\begin{tikzpicture}\\node[draw] {Database};\\end{tikzpicture}\"}"
```

Request body:

```json
{
  "instruction": "Move the database node left",
  "tikz": "\\begin{tikzpicture}\\node[draw] {Database};\\end{tikzpicture}"
}
```

Success response follows the same artifact contract as `/generate`.

Validation errors:

- `400`: Missing, empty, whitespace-only, or oversized instruction; missing TikZ.
- `415`: Request body is not JSON.

## Generated Artifacts

### `GET /generated/<asset_type>/<filename>`

Serves generated files. Supported `asset_type` values:

- `pdf`
- `images`
- `latex`

Examples:

```text
/generated/pdf/diagram.pdf
/generated/images/diagram.png
/generated/latex/diagram.tex
```

## Error Shape

```json
{
  "success": false,
  "error": "Invalid request."
}
```
