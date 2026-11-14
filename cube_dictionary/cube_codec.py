"""cube_codec.py - 3 words <-> cube state, with a tiered word table.

  word table = hackathon list (durhack_word_list.csv, indices 0..29999, the base)
             + extra_words.txt (a ~370k English dictionary minus the list), appended after it
  3 words -> 3 x 19-bit indices = 57 bits
  57 bits + 8-bit check (SHA-256 of the data) = 65-bit payload   (cube capacity is 2^65.23)
  payload -> cube state via cube.int_to_facelets (mixed radix over the legal states)

The check bits mean a misread cube is refused rather than decoded into wrong words.
"""
import hashlib
import os

import codec
import cube

N_WORDS = 3
BITS_PER_WORD = 19
DATA_BITS = BITS_PER_WORD * N_WORDS   # 57
CHECK_BITS = 8
PAYLOAD_BITS = DATA_BITS + CHECK_BITS # 65
assert (1 << PAYLOAD_BITS) <= cube.CAPACITY, "payload must fit in the cube"

HERE = os.path.dirname(os.path.abspath(__file__))
TIER_LIST, TIER_DICT = "list", "dictionary"


class WordTable:
    """base list first, dictionary extras after it; index -> word and word -> index"""

    def __init__(self, base, extra=()):
        seen = set(base)
        extra = [w for w in extra if w not in seen]
        self.words = list(base) + list(extra)
        self.n_base = len(base)
        if len(self.words) > 1 << BITS_PER_WORD:
            raise ValueError(f"word table too big for {BITS_PER_WORD} bits: {len(self.words)}")
        self.index = {w: i for i, w in enumerate(self.words)}

    def __len__(self):
        return len(self.words)

    @property
    def n_extra(self):
        return len(self.words) - self.n_base

    def lookup(self, word):
        w = word.strip().lower()
        if w not in self.index:
            raise ValueError(f"{w!r} is not in the list ({self.n_base:,} words) or the dictionary ({self.n_extra:,} words)")
        return self.index[w]

    def tier(self, idx):
        return TIER_LIST if idx < self.n_base else TIER_DICT

    def word(self, idx):
        if idx >= len(self.words):
            raise ValueError(f"decoded index {idx} outside the word table")
        return self.words[idx]


def load_table(folder=None, words_csv=None):
    folder = folder or HERE
    base = codec.load_words(words_csv or codec.default_word_list_path(folder))
    extra_path = os.path.join(folder, "extra_words.txt")
    extra = []
    if os.path.exists(extra_path):
        with open(extra_path, encoding="utf-8") as f:
            extra = [line.strip() for line in f if line.strip()]
    return WordTable(base, extra)


def words_to_bits(words, table):
    if len(words) != N_WORDS:
        raise ValueError(f"need exactly {N_WORDS} words")
    value = 0
    for w in words:
        value = (value << BITS_PER_WORD) | table.lookup(w)
    return value


def bits_to_words(value, table):
    """-> (words, tiers)"""
    mask = (1 << BITS_PER_WORD) - 1
    idxs = [(value >> (BITS_PER_WORD * (N_WORDS - 1 - i))) & mask for i in range(N_WORDS)]
    return [table.word(i) for i in idxs], [table.tier(i) for i in idxs]


def tiers(words, table):
    return [table.tier(table.lookup(w)) for w in words]


def checksum(data):
    h = hashlib.sha256(data.to_bytes(8, "big")).digest()
    return int.from_bytes(h[:2], "big") & ((1 << CHECK_BITS) - 1)


def bits_to_payload(data):
    return (data << CHECK_BITS) | checksum(data)


def payload_to_bits(payload):
    if payload >= 1 << PAYLOAD_BITS:
        raise ValueError("not an encoded cube (payload out of range)")
    data, chk = payload >> CHECK_BITS, payload & ((1 << CHECK_BITS) - 1)
    if chk != checksum(data):
        raise ValueError("not an encoded cube (check bits do not match)")
    return data


def words_to_state(words, table):
    """-> (facelets, data_bits_int)"""
    data = words_to_bits(words, table)
    return cube.int_to_facelets(bits_to_payload(data)), data


def state_to_words(facelets, table):
    """-> (words, data_bits_int, tiers). Raises ValueError for an illegal or non-encoded cube."""
    payload = cube.facelets_to_int(facelets)
    data = payload_to_bits(payload)
    words, tier = bits_to_words(data, table)
    return words, data, tier
