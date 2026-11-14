# Hidden in Plain Sight — fractal codec

Three secret words → a Mandelbrot-style picture → three words again. See **METHOD.md** for
the full explanation. Two separate apps, both fully offline:

| folder | where | run |
|---|---|---|
| `encoder_app/` | sender's computer | `python encode_app.py` → type 3 words, download the PNG |
| `decoder_app/` | receiver's computer | `python decode_app.py` → drop the PNG, read the words |

Each folder is self-contained (code + word list + `requirements.txt` + `RUN.md`).
Rebuild them from the source files here with `python pack.py`.

## Development (this folder)

    python -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python encoder.py durhack_word_list.csv out.png apple river garden [mandelbrot|space|ember|emerald]
    .venv/bin/python decoder.py durhack_word_list.csv out.png overlay.png
    .venv/bin/python test.py durhack_word_list.csv 200 space     # accuracy under 6 conditions

- `codec.py`   words ↔ 45 bits ↔ 9 data + 6 Reed-Solomon parity symbols; symbol ↔ (size, distance)
- `layout.py`  all geometry in units of the main disc radius
- `encoder.py` shapes + fractal glow → PNG (4 themes)
- `decoder.py` marker (scale, rotation) → bulbs (size, distance) → RS decode → overlay
- `test.py`    clean / rotated+scaled / JPEG / grayscale / 3 bulbs tampered / everything at once
- `gallery/`   examples + the two reference images

## Test results (test.py, 200 random phrases per theme, 6 conditions each)

| condition | mandelbrot | space | ember | emerald |
|---|---|---|---|---|
| clean | 200/200 | 200/200 | 200/200 | 200/200 |
| rotated (any angle) + scaled 0.7–1.0 | 200/200 | 200/200 | 200/200 | 200/200 |
| re-saved as JPEG (quality 60) | 200/200 | 200/200 | 200/200 | 200/200 |
| converted to grayscale | 85/200 | **200/200** | 65/200 | 41/200 |
| 3 of 15 bulbs tampered | 200/200 | 200/200 | 200/200 | 200/200 |
| rotated + scaled + JPEG + 3 bulbs tampered | 200/200 | 200/200 | 200/200 | 200/200 |

Grayscale only survives in the **space** theme: the dark themes' backgrounds (navy, deep red,
deep green) are near-black in luminance, so a grayscale copy loses the body/background contrast.
Outside the deliberately tampered bulbs, not a single bulb was misread in any run.
About 0.2 s per encode + decode.
