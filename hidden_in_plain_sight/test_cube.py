"""Round-trip tests for cube.py"""
import random
import cube

# moves: 4x a face = identity, X X' = identity, X2 = X X
for f in cube.FACES:
    s = cube.SOLVED
    for _ in range(4):
        s = cube.apply_move(s, f)
    assert s == cube.SOLVED, f
    assert cube.apply_moves(cube.SOLVED, [f, f + "'"]) == cube.SOLVED
    assert cube.apply_move(cube.SOLVED, f + "2") == cube.apply_moves(cube.SOLVED, [f, f])
    # each quarter turn moves exactly 20 stickers (8 on the face + 12 around it)
    moved = sum(1 for i, j in enumerate(cube.MOVES[f]) if i != j)
    assert moved == 20, (f, moved)
    # the solver must agree with our move tables on every single move
    assert cube.solve(cube.apply_move(cube.SOLVED, f)) == [f + "'"], (f, cube.solve(cube.apply_move(cube.SOLVED, f)))
print("move tables ok")

# cubie <-> facelet round trip on random scrambles + solver agreement
rng = random.Random(1)
moves = list(cube.MOVES)
for _ in range(50):
    scr = [rng.choice(moves) for _ in range(rng.randint(1, 30))]
    s = cube.apply_moves(cube.SOLVED, scr)
    assert cube.cubies_to_facelets(*cube.facelets_to_cubies(s)) == s
    n = cube.facelets_to_int(s)
    assert cube.int_to_facelets(n) == s
    assert cube.apply_moves(s, cube.solve(s)) == cube.SOLVED
print("facelet/cubie/int round trip ok")

# integer -> state -> integer for random 61-bit payloads, plus scramble reproduces state
for _ in range(50):
    n = rng.getrandbits(61)
    s = cube.int_to_facelets(n)
    assert cube.facelets_to_int(s) == n
    scr = cube.scramble(s)
    assert cube.apply_moves(cube.SOLVED, scr) == s
print("61-bit payload round trip + scramble ok; sample scramble:", " ".join(scr), f"({len(scr)} moves)")

# invalid states are rejected
bad = list(cube.SOLVED); bad[0], bad[9] = bad[9], bad[0]       # swap two stickers of one corner -> twist
try:
    cube.facelets_to_cubies("".join(bad)); raise SystemExit("twisted corner accepted")
except ValueError as e:
    print("rejects twisted corner:", e)
bad = list(cube.SOLVED); bad[1], bad[46] = bad[46], bad[1]      # flip the UB edge
try:
    cube.facelets_to_cubies("".join(bad)); raise SystemExit("flipped edge accepted")
except ValueError as e:
    print("rejects flipped edge:", e)
print("ALL OK")
