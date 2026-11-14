"""Build the two stand-alone app folders from the source files in this directory.

usage: python pack.py
  -> encoder_app/   copy to the SENDER's computer   : python encode_app.py
  -> decoder_app/   copy to the RECEIVER's computer : python decode_app.py
Each folder is self-contained (code + word list + requirements.txt + run instructions).
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
COMMON = ["codec.py", "layout.py", "durhack_word_list.csv", "requirements.txt"]
APPS = {
    "encoder_app": COMMON + ["encoder.py", "encode_app.py"],
    "decoder_app": COMMON + ["decoder.py", "decode_app.py"],
}
RUN = """# {name}

1. Install Python 3 (3.9 or newer).
2. In this folder:  python -m venv .venv  &&  .venv/bin/pip install -r requirements.txt
   (Windows: .venv\\Scripts\\pip install -r requirements.txt)
3. Run:  .venv/bin/python {entry}        (Windows: .venv\\Scripts\\python {entry})
   A browser tab opens automatically. Works fully offline.

CLI alternative:
   {cli}
"""
CLI = {
    "encoder_app": "python encoder.py durhack_word_list.csv out.png apple river garden [theme]",
    "decoder_app": "python decoder.py durhack_word_list.csv in.png overlay.png",
}

for name, files in APPS.items():
    out = os.path.join(HERE, name)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for f in files:
        shutil.copy(os.path.join(HERE, f), out)
    entry = "encode_app.py" if name == "encoder_app" else "decode_app.py"
    with open(os.path.join(out, "RUN.md"), "w") as fh:
        fh.write(RUN.format(name=name, entry=entry, cli=CLI[name]))
    print(f"built {name}/  ({len(files) + 1} files)")
