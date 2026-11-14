"""synthetic render -> read back, for random encoded states"""
import random
import cube, cube_codec, cube_vision, codec

table = cube_codec.load_table()
wl = table.words
rng = random.Random(7)
for t in range(30):
    words = [rng.choice(wl) for _ in range(3)]
    f, data = cube_codec.words_to_state(words, table)
    imgs = [cube_vision.render_synthetic(f, "A"), cube_vision.render_synthetic(f, "B")]
    if t % 2:
        imgs.reverse()
    got, info = cube_vision.read_stickers(imgs)
    assert got == f, (words, f, got)
    back, _, tiers = cube_codec.state_to_words(got, table)
    assert back == words, (words, back)
    assert tiers == cube_codec.tiers(words, table)
import cv2
print(f"table: list {table.n_base:,} + dictionary {table.n_extra:,}")
print("synthetic round trip ok; last:", words, tiers, "scramble:", " ".join(cube.scramble(f)))
