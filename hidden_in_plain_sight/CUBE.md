# Rubik's Cipher (cube prototype)

> A scrambled cube looks like noise. This one is a sentence. Solve it and the words come out.

Branch `cube-prototype`. The fractal version (encoder.py / decoder.py / encode_app.py / decode_app.py) is untouched and
remains the fallback.

## Run

Two separate sites, like the fractal version: the sender runs the encode app, the receiver runs the decode app
(different computers, both offline; only the two PNGs travel).

```bash
cd hidden_in_plain_sight
../.venv/bin/pip install -r requirements.txt      # adds flask + kociemba
../.venv/bin/python cube_encode_app.py            # sender   -> http://127.0.0.1:8771
../.venv/bin/python cube_decode_app.py            # receiver -> http://127.0.0.1:8772
../.venv/bin/python cube_app.py                   # dev only: both tabs on http://127.0.0.1:8770
python pack.py                                    # builds cube_encoder_app/ and cube_decoder_app/ to copy to each computer
```

Encode site: type three words (or Random) -> the cube animates the scramble -> **Export two images** saves
`cube_<time>_A.png` and `cube_<time>_B.png` (fixed cameras at opposite corners, so all six faces are covered).
Decode site: choose those two files -> Decode -> the cube animates the solve and the words appear one by one.
Drag the cube to look around, double-click to reset the view.

## Pipeline

```
3 words --(word list index, 15 bits each)--> 45 bits
45 bits + 16 check bits (SHA-256) --> 61-bit payload
payload --(mixed radix over the legal cube states)--> corner perm / corner twist / edge flip / edge perm
cubies --> 54 facelets --> Kociemba solver --> solution; scramble = inverse(solution)
3D cube: solved --animate scramble--> state --export--> two PNGs
two PNGs --sample 54 sticker centres (6 centres = colour reference)--> facelets --> validity + check bits --> 45 bits --> words
```

The legal cube states number 8!·3^7·12!/2·2^11 ≈ 4.3·10^19 ≈ 2^65.2, so every 61-bit payload has its own state and the
map is a bijection on that range. A misread sticker is almost always caught: it breaks a cubie (impossible colour
pair), the orientation/parity laws, or the 16 check bits.

## Files

| file | role |
| --- | --- |
| `cube.py` | facelet geometry, move tables, facelets <-> cubies, integer <-> state, solver wrapper |
| `cube_codec.py` | words <-> 45 bits <-> 61-bit payload (check bits) <-> state |
| `cube_vision.py` | fixed-camera projection, sticker sampling, synthetic renders for tests |
| `cube_app.py` | Flask: `/`, `POST /encode`, `POST /decode`, `/random`, `/render` (test harness); `MODE` picks which half is live |
| `cube_encode_app.py`, `cube_decode_app.py` | the two entry points (sender / receiver) |
| `templates/cube.html`, `static/cube/cube.js` | Three.js cube (r128, vendored), drag view, move animation, export |
| `test_cube.py`, `test_cube_vision.py` | move/solver agreement, round trips, synthetic image round trip |

The 3D geometry (U=+y, R=+x, F=+z; Kociemba facelet numbering) is written once in `cube.py` and copied verbatim into
`cube.js`; the export camera (orthographic, half-width 2.8, 600 px, eye at ±(1,1,1), up (0,1,0)) is defined in
`cube_vision.py` and passed to the page as `CUBE_CONFIG`, so Python and the browser agree on where every sticker lands.
`/render?f=<facelets>&view=A|B` draws one export view full-page; screenshotting it with headless Chrome and posting
the result to `/decode` is the end-to-end test (done 2026-11-14: exact match, colour distance 0).

## Tests

```bash
../.venv/bin/python test_cube.py            # move tables agree with the solver, 61-bit round trips, invalid cubes refused
../.venv/bin/python test_cube_vision.py     # synthetic A/B renders -> stickers -> words, 30 random phrases
```
