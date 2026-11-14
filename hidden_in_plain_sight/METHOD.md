# How it works — "Hidden in Plain Sight" entry

**One sentence:** the secret phrase becomes the *geometry* of a fractal: 15 satellite bulbs
around a Mandelbrot-like body, where each bulb's size and distance from the centre spell
one symbol, and the glow around them is a Julia set seeded by the phrase itself.

## Encoding (sender)

1. **Words → number.** The 30,000-word list is sorted; each word is its index (0–29,999),
   which fits in 15 bits. Three words = 45 bits.
2. **Number → 9 symbols.** The 45 bits are cut into 9 symbols of 5 bits (values 0–31).
3. **Error correction.** Reed-Solomon over GF(32) adds 6 parity symbols → 15 symbols.
   Any 3 of the 15 can be destroyed and the phrase still decodes.
4. **Symbol → bulb.** Each symbol (0–31) becomes one black (or bright) satellite bulb:
   - high 2 bits → bulb **size** (4 radii: 0.11, 0.18, 0.25, 0.32 of the main disc)
   - low 3 bits → bulb **distance** from the centre (8 radii: 2.2 … 3.6 of the main disc)
   - the slot number (0–14) → the bulb's **direction** (20° apart, antenna side left free)
5. **Marker.** The big disc + antenna + period-2 bulb (the Mandelbrot silhouette) is the
   reference: its radius gives the scale, its antenna gives the rotation.
6. **Art.** A SHA-256 hash of the phrase seeds a Julia-set texture, which warps a distance
   field around the shapes into the glowing fractal fringe. Decorative "mini-brots" sit
   outside the data zone. Four colour themes (mandelbrot, space, ember, emerald).

## Decoding (receiver)

1. **Find the body.** Threshold very dark (or very bright) pixels; the most disc-like blob
   with the largest inscribed circle is the main body. Its sub-pixel radius = scale.
2. **Find the antenna.** Dark pixels just outside the disc point along the antenna = rotation.
3. **Read the bulbs.** For each of the 15 directions, take the blob sitting there.
   Its radius (sub-pixel edge fit, same method as the main disc) → size → 2 bits;
   its centroid distance → 3 bits.
4. **Correct and translate.** Reed-Solomon fixes up to 3 wrong bulbs; 45 bits → 3 indices → 3 words.
5. An overlay PNG shows every measurement and which bulbs were corrected.

## Why it is different (and easy to say on stage)

- **No colour needed.** The data is pure geometry (size + distance), so the picture can be
  any colour theme, and the same decoder reads all of them without being told which.
- **The art is the fingerprint.** The fractal glow is seeded by the secret, so each phrase has
  its own unique nebula — the picture *is* the message, not a wrapper around it.
- **Robust by design.** Rotation and scale are undone by the marker; JPEG re-saving and
  3 vandalised bulbs are tolerated by the measurement margins and Reed-Solomon.
- **Nothing machine-readable to the eye.** No grid, no modules, no quiet zone — just a
  Mandelbrot-style composition. The bulbs look like what a Mandelbrot set naturally has.

## Numbers (test.py, 200 random phrases per theme, 6 conditions each)

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
