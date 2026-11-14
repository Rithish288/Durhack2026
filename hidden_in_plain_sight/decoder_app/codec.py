"""Codec: 3 words <-> 15 symbols (0..31), each symbol = bulb size (2 bits) + bulb distance (3 bits).

Scheme
  * word list sorted, word -> index (0..29999) fits in 15 bits, 3 words = 45 bits
  * 45 bits -> 9 symbols of 5 bits (MSB first)
  * + 6 Reed-Solomon parity symbols over GF(32)  -> 15 symbols, corrects up to 3 bad symbols
  * symbol -> bulb size = sym >> 3 (4 sizes), bulb distance = sym & 7 (8 distances)
"""
import csv
import hashlib
import os
import random

from reedsolo import RSCodec, ReedSolomonError

BITS_PER_WORD = 15
N_WORDS = 3
N_DATA_SYMBOLS = 9          # 45 bits / 5
N_PARITY_SYMBOLS = 6
N_SYMBOLS = N_DATA_SYMBOLS + N_PARITY_SYMBOLS   # 15
SYMBOL_BITS = 5

# symbol = (size_idx << 3) | dist_idx : 4 bulb sizes x 8 bulb distances (see layout.py)
N_SIZES = 4
N_DISTS = 8

# GF(2^5): reedsolo picks a prime polynomial and nsize=31 for us when c_exp=5.
_rs = RSCodec(N_PARITY_SYMBOLS, c_exp=SYMBOL_BITS)


# ---------------------------------------------------------------- word list
def load_words(path):
    """Return the sorted, de-duplicated word list."""
    words = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            w = row[0].strip().lower()
            if w and w != "word":
                words.add(w)
    words = sorted(words)
    if len(words) > 2 ** BITS_PER_WORD:
        raise ValueError(f"word list too big for {BITS_PER_WORD} bits: {len(words)}")
    return words


def generate_fake_word_list(path, n=30000, seed=1234):
    """Write a deterministic fake word list (pronounceable nonsense) for testing."""
    rng = random.Random(seed)
    cons = "bcdfghjklmnprstvwz"
    vow = "aeiou"
    words = set()
    while len(words) < n:
        w = "".join(rng.choice(cons) + rng.choice(vow) for _ in range(rng.randint(2, 4)))
        if rng.random() < 0.4:
            w += rng.choice("nrst")
        words.add(w)
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["word"])
        for w in sorted(words):
            wr.writerow([w])
    return path


def default_word_list_path(folder=None):
    """durhack_word_list.csv if present, else a generated fake list."""
    folder = folder or os.path.dirname(os.path.abspath(__file__))
    real = os.path.join(folder, "durhack_word_list.csv")
    if os.path.exists(real):
        return real
    fake = os.path.join(folder, "fake_word_list.csv")
    if not os.path.exists(fake):
        generate_fake_word_list(fake)
    return fake


# ---------------------------------------------------------------- bits <-> symbols
def words_to_symbols(words, wordlist):
    """3 words -> 15 RS-coded symbols (ints 0..31)."""
    if len(words) != N_WORDS:
        raise ValueError(f"need exactly {N_WORDS} words")
    index = {w: i for i, w in enumerate(wordlist)}
    value = 0
    for w in words:
        w = w.strip().lower()
        if w not in index:
            raise ValueError(f"word not in list: {w!r}")
        value = (value << BITS_PER_WORD) | index[w]
    total_bits = BITS_PER_WORD * N_WORDS  # 45
    data = [(value >> (total_bits - SYMBOL_BITS * (k + 1))) & 31 for k in range(N_DATA_SYMBOLS)]
    coded = _rs.encode(bytearray(data))
    return [int(s) for s in coded]


def symbols_to_words(symbols, wordlist):
    """15 read symbols -> (words, errata_positions). Raises ValueError if unrecoverable."""
    if len(symbols) != N_SYMBOLS:
        raise ValueError(f"need {N_SYMBOLS} symbols")
    try:
        res = _rs.decode(bytearray(int(s) & 31 for s in symbols))
    except ReedSolomonError as e:
        raise ValueError(f"Reed-Solomon decode failed: {e}")
    if isinstance(res, tuple):          # reedsolo >= 1.5: (msg, msg+ecc, errata_pos)
        msg = res[0]
        errata = sorted(int(p) for p in res[2]) if len(res) > 2 else []
    else:
        msg, errata = res, []
    value = 0
    for s in msg:
        value = (value << SYMBOL_BITS) | int(s)
    mask = (1 << BITS_PER_WORD) - 1
    idxs = [(value >> (BITS_PER_WORD * (N_WORDS - 1 - i))) & mask for i in range(N_WORDS)]
    words = []
    for i in idxs:
        if i >= len(wordlist):
            raise ValueError(f"decoded index {i} outside word list")
        words.append(wordlist[i])
    return words, errata


# ---------------------------------------------------------------- symbol <-> glyph
def symbol_to_glyph(sym):
    """symbol -> (size_index 0..3, dist_index 0..7)"""
    return (sym >> 3) & 3, sym & 7


def glyph_to_symbol(size_idx, dist_idx):
    return ((size_idx & 3) << 3) | (dist_idx & 7)


def message_seed(words):
    """Deterministic seed for the decorative art, derived from the words."""
    h = hashlib.sha256(" ".join(w.strip().lower() for w in words).encode()).digest()
    return int.from_bytes(h[:8], "big")
