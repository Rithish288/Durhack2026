import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const initialWords = ["", "", ""];

function App() {
  const [csv, setCsv] = useState(null);
  const [dictionaryWords, setDictionaryWords] = useState([]);
  const [activeWord, setActiveWord] = useState(null);
  const [words, setWords] = useState(initialWords);
  const [result, setResult] = useState(null);
  const [decodeImage, setDecodeImage] = useState(null);
  const [decodedWords, setDecodedWords] = useState(null);
  const [decodeError, setDecodeError] = useState("");
  const [decoding, setDecoding] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const updateWord = (index, value) => {
    setWords((current) => current.map((word, i) => (i === index ? value : word)));
    setActiveWord(index);
  };

  const handleCsv = async (file) => {
    setCsv(file || null);
    setResult(null);
    setError("");
    setWords(initialWords);
    if (!file) {
      setDictionaryWords([]);
      return;
    }

    const rows = (await file.text()).split(/\r?\n/);
    const parsedWords = rows
      .slice(1)
      .map((row) => row.split(",")[0].trim())
      .filter(Boolean);
    setDictionaryWords([...new Set(parsedWords)]);
  };

  const chooseSuggestion = (index, word) => {
    updateWord(index, word);
    setActiveWord(null);
  };

  const generate = async (event) => {
    event.preventDefault();
    setError("");
    setResult(null);

    if (!csv) {
      setError("Choose a CSV word list first.");
      return;
    }

    const enteredWords = words.map((word) => word.trim()).filter(Boolean);
    if (enteredWords.length !== 0 && enteredWords.length !== 3) {
      setError("Enter all three words, or leave all three blank for random words.");
      return;
    }
    const invalidWord = enteredWords.find((word) => !dictionaryWords.includes(word));
    if (invalidWord) {
      setError(`“${invalidWord}” is not in the uploaded dictionary. Choose an autofill suggestion.`);
      return;
    }

    const formData = new FormData();
    formData.append("csv", csv);
    enteredWords.forEach((word) => formData.append("words", word));

    setLoading(true);
    try {
      const response = await fetch("/api/generate", { method: "POST", body: formData });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Could not generate artwork.");
      setResult(payload);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const decode = async (event) => {
    event.preventDefault();
    setDecodeError("");
    setDecodedWords(null);
    if (!decodeImage) {
      setDecodeError("Choose an artwork image first.");
      return;
    }

    const formData = new FormData();
    formData.append("image", decodeImage);
    if (csv) formData.append("csv", csv);

    setDecoding(true);
    try {
      const response = await fetch("/api/decode", { method: "POST", body: formData });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Could not decode artwork.");
      setDecodedWords(payload.words);
    } catch (requestError) {
      setDecodeError(requestError.message);
    } finally {
      setDecoding(false);
    }
  };

  return (
    <main className="page-shell">
      <header className="topbar">
        <div className="brand-mark" aria-label="Metro">
         {" M E  T R O"}
        </div>
        <div className="status"><span /> WORD ENCODER</div>
      </header>

      <section className="hero">
        <h1>Turn three words<br />into a masterpiece.</h1>
        <p className="intro">
          Upload your word list, choose three wrods, and create a one-of-one encoded artwork.
          Leave the words blank and three words will be chosen at random.
        </p>
      </section>

      <form className="generator-card" onSubmit={generate}>
        <div className="card-heading">
          <div>
            <p className="eyebrow">01 / CSV File</p>
            <h2>Upload Here</h2>
          </div>
          <span className="card-number">A</span>
        </div>

        <label className={`upload-zone ${csv ? "has-file" : ""}`}>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => handleCsv(event.target.files?.[0] || null)}
          />
          <span className="upload-icon">↑</span>
          <strong>{csv ? csv.name : "Drop your CSV here"}</strong>
          <small>{csv ? "Ready to encode" : "or click to browse · CSV only"}</small>
        </label>

        <div className="card-heading words-heading">
          <div>
            <p className="eyebrow">02 / INPUT</p>
            <h2>Choose your three words<span>(optional)</span></h2>
          </div>
          <span className="random-note">Blank = random</span>
        </div>

        <div className="word-grid">
          {words.map((word, index) => (
            <label className="word-field" key={index}>
              <span>0{index + 1}</span>
              <input
                value={word}
                onChange={(event) => updateWord(index, event.target.value)}
                onFocus={() => setActiveWord(index)}
                onBlur={() => setTimeout(() => setActiveWord(null), 120)}
                placeholder={`Word ${index + 1}`}
                autoComplete="off"
              />
              {activeWord === index && word && (
                <div className="suggestions">
                  {dictionaryWords
                    .filter((candidate) => candidate.startsWith(word.toLowerCase()))
                    .slice(0, 6)
                    .map((candidate) => (
                      <button type="button" key={candidate} onMouseDown={() => chooseSuggestion(index, candidate)}>
                        {candidate}
                      </button>
                    ))}
                </div>
              )}
            </label>
          ))}
        </div>

        {error && <p className="error-message">{error}</p>}
        <button className="generate-button" disabled={loading}>
          <span>{loading ? "Encoding..." : "Generate artwork"}</span>
          <span className="button-arrow">↗</span>
        </button>
      </form>

      {result && (
        <section className="result-card">
          <div className="result-copy">
            <p className="eyebrow">YOUR GENERATED MARK</p>
            <h2>Made from<br />{result.words.join(" · ")}</h2>
            <a className="download-link" href={result.image} download="durhack-artwork.png">
              Download PNG <span>↓</span>
            </a>
          </div>
          <img className="artwork" src={result.image} alt={`Generated artwork for ${result.words.join(", ")}`} />
        </section>
      )}

      <section className="decoder-card">
        <div className="card-heading">
          <div>
            <p className="eyebrow">03 / DECODE</p>
            <h2>Decode the masterpiece</h2>
          </div>
          <span className="card-number">B</span>
        </div>
        <p className="decode-copy">
          Upload a generated artwork image via a photograph or the image export.
        </p>
        <form onSubmit={decode}>
          <label className={`upload-zone decoder-upload ${decodeImage ? "has-file" : ""}`}>
            <input
              type="file"
              accept="image/png,image/jpeg"
              onChange={(event) => {
                setDecodeImage(event.target.files?.[0] || null);
                setDecodeError("");
              }}
            />
            <span className="upload-icon">⌁</span>
            <strong>{decodeImage ? decodeImage.name : "Drop artwork here"}</strong>
            <small>{decodeImage ? "Ready to decode" : "PNG or JPEG"}</small>
          </label>
          {decodeError && <p className="error-message">{decodeError}</p>}
          <button className="generate-button decode-button" disabled={decoding}>
            <span>{decoding ? "Decoding..." : "Decode artwork"}</span>
            <span className="button-arrow">↘</span>
          </button>
        </form>
        {decodedWords && (
          <div className="decoded-result">
            <p className="eyebrow">RECOVERED WORDS</p>
            <p>{decodedWords.join(" · ")}</p>
          </div>
        )}
      </section>

      <footer>BUILT FOR THE SAKE OF IT <span>✦</span> DURHACK</footer>
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode><App /></StrictMode>,
);
