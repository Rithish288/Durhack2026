"""synthetic render -> read back, for random encoded states"""
import random
import cube, cube_codec, cube_vision, codec

wl = codec.load_words(codec.default_word_list_path())
rng = random.Random(7)
for t in range(30):
    words = [rng.choice(wl) for _ in range(3)]
    f, data = cube_codec.words_to_state(words, wl)
    imgs = [cube_vision.render_synthetic(f, "A"), cube_vision.render_synthetic(f, "B")]
    if t % 2:
        imgs.reverse()
    got, info = cube_vision.read_stickers(imgs)
    assert got == f, (words, f, got)
    back, _ = cube_codec.state_to_words(got, wl)
    assert back == words, (words, back)
import cv2
cv2.imwrite("gallery/cube_synthetic_A.png", cv2.cvtColor(imgs[0], cv2.COLOR_RGB2BGR))
print("synthetic round trip ok; last:", words, "scramble:", " ".join(cube.scramble(f)))
