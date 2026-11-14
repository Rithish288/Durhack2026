# How it works — "Hidden in Plain Sight" entry

**One sentence:** a mother Mandelbrot set with 15 baby Mandelbrots orbiting it. The mother is
the ruler and the compass; each baby's size and orbit radius spell one symbol of the message;
everything else in the picture (colours, fractal texture, motion) is seeded by the phrase itself.

## Encoding (sender)

1. **Words → number.** The 30,000-word list is sorted; each word is its index (0–29,999),
   which fits in 15 bits. Three words = 45 bits.
2. **Number → 9 symbols.** The 45 bits are cut into 9 symbols of 5 bits (values 0–31).
3. **Error correction.** Reed-Solomon over GF(32) adds 6 parity symbols → 15 symbols.
   Any 3 of the 15 can be destroyed and the phrase still decodes.
4. **Symbol → baby.** Each symbol (0–31) becomes one baby Mandelbrot (a real, iterated
   silhouette, rotated any way the art likes):
   - high 2 bits → the baby's **size** (area-equivalent radius: 0.06, 0.095, 0.13, 0.165 units)
   - low 3 bits → the baby's **orbit radius**, centroid distance from the origin (1.60 … 2.65 units)
   - the slot number (0–14) → the baby's **direction** (20° apart, antenna side left free)
5. **Marker.** The centre of the picture is a *real* Mandelbrot set, rendered by iteration
   with its antenna pointing up. It is the reference: the main cardioid and the period-2
   bulb are two blobs whose centroids are exactly 0.825 units apart along the antenna axis,
   so their distance gives the scale and their direction gives the rotation. No artificial
   disc, no needle: the fractal itself is the ruler and the compass.
6. **Art.** A SHA-256 hash of the phrase seeds everything decorative, so each phrase has its
   own picture. The seed picks:
   - the **palette**: dark or bright bodies, a deep / mid / light background, and a colour
     scheme (analogous, complementary, triadic, split or mono) that builds the glow ramp;
   - the **fractal formula**: Julia, Burning Ship, cubic Multibrot, Tricorn, Phoenix, Celtic,
     Lambda, Sine or Newton basins, plus its constant, zoom and band period;
   - a **kaleidoscope fold** (1- to 12-fold mirror symmetry), a **swirl**, optional **rays** and
     **cloud** modulation of the glow, and how far the glow reaches;
   - the **decoration style**: mini-brots, spirals, orbit rings, star polygons or comets, and
     sometimes a star field or a large orbit ring;
   - the **pose**: the whole family is tilted by a phrase-chosen angle and zoomed a little,
     since the decoder reads any rotation and scale anyway;
   - the **fill**: the mother and the babies are usually not flat; they carry a very dark
     (or very bright) contour-band pattern inside, kept within the decoder's body range;
   - the **motion**: the satellites trail comet-tail motion blur along an orbit, a vortex, an
     outward burst or a wind direction, with gradient light streaks and sparks aligned to it,
     and the Mandelbrot fringe can be domain-warped so it flickers like electricity.
   The texture warps a distance field around the shapes into the glowing fringe, and is
   re-rolled from the same seed stream until it has visible structure near the shapes.
   Four fixed presets (mandelbrot, space, ember, emerald) are also available.
   None of this touches the data shapes, and every colour is kept out of the decoder's
   "body" range automatically.

## Decoding (receiver)

1. **Find the Mandelbrot.** Threshold very dark (or very bright) pixels and take the big
   blobs. Erode a candidate a little: the main cardioid and the period-2 bulb fall apart
   into two pieces (they only touch at a point). Their centroid distance = scale, their
   direction = rotation, and the complex origin is a fixed offset from the cardioid centroid.
2. **(Candidates.)** The three biggest blobs are tried and the one that yields the most
   satellites wins, so a large black region of the background fractal can never fool it.
3. **Read the babies.** For each of the 15 directions, take the blob sitting there.
   Its area → area-equivalent radius → size → 2 bits; its centroid distance → orbit → 3 bits.
   Both are independent of the baby's rotation, and the four size levels differ by 2.5x in
   area, so JPEG softening of the babies' fine bulbs does not matter.
4. **Correct and translate.** Babies that could not be found are passed to Reed-Solomon as
   *erasures* (known positions, cost 1 each); misread babies are *errors* (cost 2). The budget
   is 6, so 3 misread babies, or up to 6 missing ones, are repaired; 45 bits → 3 indices → 3 words.
5. **Photographs.** If a baby is missing or the babies' directions deviate from their slots,
   the read is treated as a photo: a full homography is fitted from the mother's two landmarks
   plus the known slot directions of the found babies (their angles are a built-in calibration
   grid), and every baby is re-measured through it, which undoes camera keystone. In that mode a
   correction is only accepted if the corrected symbol is a neighbouring cell of what was
   measured, so a bad photo says "unreadable" instead of returning a wrong phrase.
6. An overlay PNG shows every measurement and which babies were corrected.

## Why it is different (and easy to say on stage)

- **No colour needed.** The data is pure geometry (size + distance), so the picture can be
  any colour theme, and the same decoder reads all of them without being told which.
- **The art is the fingerprint.** The fractal glow is seeded by the secret, so each phrase has
  its own unique nebula — the picture *is* the message, not a wrapper around it.
- **Robust by design.** Rotation and scale are undone by the marker; JPEG re-saving, blur,
  mild camera keystone and 3 destroyed babies are tolerated by the measurement margins,
  the homography refinement and Reed-Solomon with erasures.
- **Nothing machine-readable to the eye.** No grid, no modules, no quiet zone — a Mandelbrot
  family portrait. Nobody expects the babies' sizes and orbits to be a sentence.
- **Why not hide the data in the fractal itself?** Because fractals are chaotic: a tiny
  parameter change rewrites the whole shape, and recovering parameters from a rotated,
  resized, re-compressed picture is hopeless. So the data lives in robust geometry
  (areas and centroids) and the fractal is the disguise.

## Numbers (test.py, 200 random phrases per theme, 6 conditions each)

| condition | **auto** (per-phrase style) | space preset |
|---|---|---|
| clean | 200/200 | 200/200 |
| rotated (any angle) + scaled 0.7–1.0 | 200/200 | 200/200 |
| re-saved as JPEG (quality 60) | 200/200 | 200/200 |
| converted to grayscale | 182/200 | **200/200** |
| 3 of 15 babies tampered | 200/200 | 200/200 |
| rotated + scaled + JPEG + 3 babies tampered | 200/200 | 200/200 |

Final design (baby Mandelbrots, in-body fill, tilt + zoom), 200 random phrases per column.
Grayscale survives whenever the background is not near-black in luminance: always in the
**space** preset, in most auto styles. Outside the deliberately tampered babies, at most one
baby was misread in any run, and Reed-Solomon absorbed it. About 0.25 s per encode + decode.

