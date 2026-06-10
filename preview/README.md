# Static Product Preview

This directory is the public-facing concept preview for My Parallel Lives. It is
independent from the Gradio agent demo and uses plain HTML, CSS, and JavaScript.

## Run locally

Open `index.html` directly, or serve the directory:

```bash
python3 -m http.server 8080 --directory preview
```

Then open `http://127.0.0.1:8080`.

## Pilot form

The pilot request form currently stores submissions in `localStorage` only. It
does not transmit personal data. Before public launch, replace the submit handler
in `app.js` with a real endpoint such as Formspree, Airtable, or a small API.
