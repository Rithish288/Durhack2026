"""Build extra_words.txt: the big English dictionary minus the words already in the hackathon list.

usage: python build_wordtable.py path/to/words_alpha.txt
The hackathon list (durhack_word_list.csv) stays the base: indices 0..29999. The extra words follow it.
Source dictionary: https://github.com/dwyl/english-words (words_alpha.txt, ~370k words).
"""
import sys

import codec

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))


def main(src):
    base = codec.load_words(codec.default_word_list_path(HERE))
    base_set = set(base)
    extra = set()
    with open(src, encoding="utf-8", errors="ignore") as f:
        for line in f:
            w = line.strip().lower()
            if w and w.isascii() and w.isalpha() and w not in base_set:
                extra.add(w)
    extra = sorted(extra)
    with open(f"{HERE}/extra_words.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(extra) + "\n")
    total = len(base) + len(extra)
    print(f"list {len(base)} + dictionary {len(extra)} = {total} words -> {total.bit_length()} bits per word")


if __name__ == "__main__":
    main(sys.argv[1])
