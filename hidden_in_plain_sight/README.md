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
    .venv/bin/python encoder.py durhack_word_list.csv out.png apple river garden [auto|mandelbrot|space|ember|emerald]
    .venv/bin/python decoder.py durhack_word_list.csv out.png overlay.png
    .venv/bin/python test.py durhack_word_list.csv 200 space     # accuracy under 6 conditions

- `codec.py`   words ↔ 45 bits ↔ 9 data + 6 Reed-Solomon parity symbols; symbol ↔ (size, distance)
- `layout.py`  all geometry in units of the main disc radius
- `encoder.py` shapes + fractal glow → PNG; "auto" style is generated from the words (palette, fractal family, kaleidoscope, decoration), 4 fixed presets too
- `decoder.py` marker (scale, rotation) → bulbs (size, distance) → RS decode → overlay
- `test.py`    clean / rotated+scaled / JPEG / grayscale / 3 bulbs tampered / everything at once
- `gallery/`   examples + the two reference images

## Test results (test.py, 200 random phrases per theme, 6 conditions each)

| condition | **auto** (per-phrase style) | space preset |
|---|---|---|
| clean | 200/200 | 200/200 |
| rotated (any angle) + scaled 0.7–1.0 | 200/200 | 200/200 |
| re-saved as JPEG (quality 60) | 200/200 | 200/200 |
| converted to grayscale | 165/200 | **200/200** |
| photo-like (camera keystone + blur + JPEG) | 160/200 | 174/200 |
| 3 of 15 babies erased | 200/200 | 200/200 |
| 3 of 15 babies swapped for other valid babies (adversarial) | 200/200 | 200/200 |
| rotated + scaled + JPEG + 3 babies erased | 200/200 | 200/200 |

Final design, 200 random phrases per column. File-to-file (the challenge's channel) is perfect in
every condition. Grayscale survives whenever the background is not near-black in luminance:
always in the **space** preset, in most auto styles. Photographs are a bonus path: mild keystone
is undone by the homography refinement; when a photo cannot be read reliably the decoder says
so rather than returning a wrong phrase. About 0.2 s per encode + decode.


