import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Download, ImagePlus, Upload, Bug, ChevronDown, Sparkles } from "lucide-react";
import { buildDenseArtwork, buildPacket, calculateColourDistance, DEFAULT_PALETTE, loadDictionary, loadDictionaryCsv, nibbleToSymbol, renderShape, sampleAndQuantiseImage, splitIntoSymbols, type DenseCell, type RGB, type Shape } from "./protocol";
import { decodeSymbolImage, type DecodeResult } from "./decoder";
import "./styles.css";

const demoDictionary = ["amber", "cipher", "dream", "echo", "flux", "garden", "hidden", "light", "pixel", "signal", "symbol", "velvet"];
const PALETTES: Record<string, RGB[]> = {
  "8-colour": DEFAULT_PALETTE,
  "4-colour": [[18, 24, 35], [224, 68, 78], [245, 180, 45], [53, 126, 190]]
};
const rgb = (colour: RGB) => `rgb(${colour.join(",")})`;
function ShapeGlyph({ shape, colour, scale = 1 }: { shape: Shape; colour: string; scale?: number }) {
  const paths = { circle: <circle cx="50" cy="50" r="44" />, triangle: <path d="M50 5 L96 92 L4 92 Z" />, star: <path d="M50 4 L61 36 L96 36 L68 56 L79 91 L50 70 L21 91 L32 56 L4 36 L39 36 Z" />, heart: <path d="M50 91 C42 83 8 62 8 33 C8 10 36 2 50 23 C64 2 92 10 92 33 C92 62 58 83 50 91 Z" /> };
  return <svg className="shape-glyph" viewBox="0 0 100 100" style={{ color: colour, transform: `scale(${scale})` }} aria-hidden="true">{paths[shape]}</svg>;
}

function Artwork({ cells, mode, image, width, height, debug, zoom, symbolSize }: { cells: DenseCell[]; mode: string; image?: string; width: number; height: number; debug: boolean; zoom: number; symbolSize: number }) {
  if (mode === "Original") return <div className="artwork-viewport" style={{ aspectRatio: `${width}/${height}` }}><div className="artboard original" style={image ? { backgroundImage: `url(${image})` } : undefined} /></div>;
  const isDithered = mode === "Dithered";
  return <div className="artwork-viewport" style={{ aspectRatio: `${width}/${height}` }}><div className={`artboard dense ${isDithered ? "dithered" : "symbol-art"}`} style={{ gridTemplateColumns: `repeat(${width}, 1fr)`, transform: `scale(${zoom})` }}>
    {cells.map((cell, index) => <div className="dense-cell" key={index} style={{ backgroundColor: isDithered ? rgb(cell.colour) : "transparent" }}>
      {!isDithered && (cell.anchor ? <span className="anchor-shape">{"•".repeat(cell.anchor)}</span> : <ShapeGlyph shape={cell.shape} colour={rgb(cell.colour)} scale={symbolSize / 100} />)}
      {debug && !isDithered && <small>{cell.payloadGroup !== undefined ? `${cell.payloadGroup + 1} · ${cell.repetition}` : "anchor"}</small>}
    </div>)}
  </div></div>;
}
function MiniGrid({ cells, width, symbols }: { cells: DenseCell[]; width: number; symbols: boolean }) {
  return <div className="mini-grid" style={{ gridTemplateColumns: `repeat(${width}, 1fr)` }}>{cells.map((cell, index) => <div key={index} style={{ backgroundColor: symbols ? "transparent" : rgb(cell.colour) }}>{symbols && (cell.anchor ? <span className="mini-anchor">{"•".repeat(cell.anchor)}</span> : <ShapeGlyph shape={cell.shape} colour={rgb(cell.colour)} scale={.9} />)}</div>)}</div>;
}

function App() {
  const [dictionary, setDictionary] = useState<string[]>(demoDictionary);
  const [image, setImage] = useState<string>();
  const [words, setWords] = useState(["", "", ""]);
  const [mode, setMode] = useState("Encoded Image");
  const [debug, setDebug] = useState(false);
  const [cells, setCells] = useState<DenseCell[]>([]);
  const [resolution, setResolution] = useState(96);
  const [symbolSize, setSymbolSize] = useState(92);
  const [zoom, setZoom] = useState(1);
  const [dither, setDither] = useState(true);
  const [paletteName, setPaletteName] = useState("8-colour");
  const [packet, setPacket] = useState<number[]>();
  const [dimensions, setDimensions] = useState({ width: 96, height: 96 });
  const [similarity, setSimilarity] = useState<number>();
  const [error, setError] = useState("");
  const [howOpen, setHowOpen] = useState(false);
  const [decoderImage, setDecoderImage] = useState<string>();
  const [decoderDictionary, setDecoderDictionary] = useState<string[]>(demoDictionary);
  const [decodeResult, setDecodeResult] = useState<DecodeResult>();
  const [decoderStatus, setDecoderStatus] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const decoderFileRef = useRef<HTMLInputElement>(null);
  const indices = useMemo(() => words.map((word) => dictionary.findIndex((entry) => entry.toLowerCase() === word.trim().toLowerCase())), [words, dictionary]);

  function onImage(file?: File) {
    if (!file || !file.type.match(/^image\/(png|jpeg|webp)$/)) return setError("Please choose a PNG, JPEG, or WebP image.");
    const reader = new FileReader(); reader.onload = () => { setImage(String(reader.result)); setPacket(undefined); setCells([]); setSimilarity(undefined); setError(""); }; reader.readAsDataURL(file);
  }
  function onDictionary(file?: File) {
    if (!file) return;
    const reader = new FileReader(); reader.onload = () => setDictionary(file.name.toLowerCase().endsWith(".csv") ? loadDictionaryCsv(String(reader.result)) : loadDictionary(String(reader.result))); reader.readAsText(file);
  }
  useEffect(() => {
    if (!packet || !image) return;
    const cover = new Image(); cover.src = image;
    cover.onload = () => {
      try {
        const aspect = cover.naturalWidth / cover.naturalHeight;
        const width = aspect >= 1 ? resolution : Math.max(1, Math.round(resolution * aspect));
        const height = aspect >= 1 ? Math.max(1, Math.round(resolution / aspect)) : resolution;
        const colours = sampleAndQuantiseImage(cover, width, height, PALETTES[paletteName], dither);
        const nextCells = buildDenseArtwork(packet, colours, width, height);
        const distance = nextCells.reduce((sum, cell, index) => sum + calculateColourDistance(colours[index], cell.colour), 0) / nextCells.length;
        setDimensions({ width, height }); setCells(nextCells); setSimilarity(Math.max(0, 100 - distance)); setError("");
      }
      catch (e) { setError(e instanceof Error ? e.message : "Unable to render the artwork."); }
    };
    cover.onerror = () => setError("Unable to load the cover image for sampling.");
  }, [packet, image, resolution, dither, paletteName]);
  function encode() {
    try {
      if (!image) throw new Error("Upload a cover image first.");
      if (dictionary.length === 0) throw new Error("Load a dictionary first.");
      if (indices.some((index) => index < 0)) throw new Error("Each secret word must appear in the loaded dictionary.");
      if (indices.length !== 3 || indices.some((index) => index >= 30000)) throw new Error("Exactly three dictionary words with indices below 30000 are required.");
      const nextPacket = buildPacket(indices);
      const symbols = splitIntoSymbols(nextPacket).map(nibbleToSymbol);
      if (nextPacket.length !== 60 || symbols.length !== 15) throw new Error("Encoding protocol validation failed: expected a 60-bit packet and 15 symbols.");
      setPacket(nextPacket); setMode("Encoded Image"); setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to encode message."); }
  }
  function exportPng() {
    if (!cells.length) return setError("Encode a message before exporting.");
    const canvas = document.createElement("canvas"); canvas.width = dimensions.width * 10; canvas.height = dimensions.height * 10;
    const context = canvas.getContext("2d"); if (!context) return;
    const size = 10;
    cells.forEach((cell, index) => {
      const x = (index % dimensions.width) * size, y = Math.floor(index / dimensions.width) * size;
      context.fillStyle = "#f4f0e8"; context.fillRect(x, y, size + 1, size + 1);
      if (cell.anchor) { context.fillStyle = "#11141d"; context.font = `${size * .45}px Arial`; context.textAlign = "center"; context.textBaseline = "middle"; context.fillText("•".repeat(cell.anchor), x + size / 2, y + size / 2); }
      else renderShape(context, cell.shape, x + size * (1 - symbolSize / 100) / 2, y + size * (1 - symbolSize / 100) / 2, size * symbolSize / 100, rgb(cell.colour));
    });
    const link = document.createElement("a"); link.download = "symbol-pixels.png"; link.href = canvas.toDataURL("image/png"); link.click();
  }
  function onDecoderImage(file?: File) {
    if (!file || !file.type.match(/^image\/(png|jpeg|webp)$/)) return setDecoderStatus("Please choose a PNG, JPEG, or WebP image.");
    const reader = new FileReader(); reader.onload = () => { setDecoderImage(String(reader.result)); setDecodeResult(undefined); setDecoderStatus(""); }; reader.readAsDataURL(file);
  }
  function onDecoderDictionary(file?: File) {
    if (!file) return;
    const reader = new FileReader(); reader.onload = () => setDecoderDictionary(file.name.toLowerCase().endsWith(".csv") ? loadDictionaryCsv(String(reader.result)) : loadDictionary(String(reader.result))); reader.readAsText(file);
  }
  function decode() {
    if (!decoderImage) return setDecoderStatus("Upload an encoded Symbol Pixels image first.");
    setDecoderStatus("Analysing artwork pixels...");
    const imageElement = new Image();
    imageElement.onload = () => { try { const result = decodeSymbolImage(imageElement, decoderDictionary); setDecodeResult(result); setDecoderStatus(result.ok ? result.status : result.error ?? result.status); } catch (e) { setDecoderStatus(e instanceof Error ? e.message : "Unable to decode artwork."); } };
    imageElement.onerror = () => setDecoderStatus("Unable to load decoder image.");
    imageElement.src = decoderImage;
  }
  return <main>
    <header><div className="brand"><div className="brand-mark">✦</div><div><h1>Symbol Pixels</h1><p>From far away: an image. Up close: coloured symbols.</p></div></div><div className="status"><span className="dot" /> LOCAL ONLY</div></header>
    <div className="layout">
      <aside className="panel left">
        <section><label className="eyebrow">01 / Cover Image</label><div className="dropzone" onClick={() => fileRef.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); onImage(event.dataTransfer.files[0]); }}><ImagePlus size={27} /><strong>{image ? "Cover loaded" : "Drop an image here"}</strong><span>PNG, JPEG or WebP · auto square crop</span><input ref={fileRef} hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => onImage(event.target.files?.[0])} /></div></section>
        <section><label className="eyebrow">02 / Dictionary</label><label className="upload-row"><Upload size={15} /> Upload .txt or .csv<input hidden type="file" accept=".txt,.csv,text/plain,text/csv" onChange={(event) => onDictionary(event.target.files?.[0])} /></label><div className="stat"><strong>{dictionary.length.toLocaleString()}</strong><span>words loaded</span></div><button className="text-button" onClick={() => setDictionary(demoDictionary)}>Use synthetic demo dictionary</button></section>
        <section><label className="eyebrow">03 / Secret Message</label>{words.map((word, index) => <div className="word-input" key={index}><span>0{index + 1}</span><input value={word} placeholder={`Word ${index + 1}`} onChange={(event) => setWords((current) => current.map((value, item) => item === index ? event.target.value : value))} /><b className={word && indices[index] >= 0 ? "valid" : ""}>{word ? indices[index] >= 0 ? "✓" : "?" : ""}</b></div>)}</section>
        <section className="controls"><label className="eyebrow">04 / Rendering</label><label>Grid resolution<select value={resolution} onChange={(event) => setResolution(Number(event.target.value))}><option value="64">64 px long edge</option><option value="96">96 px long edge</option><option value="128">128 px long edge</option></select></label><label>Palette<select value={paletteName} onChange={(event) => setPaletteName(event.target.value)}><option>8-colour</option><option>4-colour</option></select></label><label className="range-label">Symbol fill <span>{symbolSize}%</span><input type="range" min="70" max="100" value={symbolSize} onChange={(event) => setSymbolSize(Number(event.target.value))} /></label><label className="range-label">Zoom <span>{zoom.toFixed(1)}×</span><input type="range" min="0.7" max="3" step="0.1" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} /></label><label className="check"><input type="checkbox" checked={dither} onChange={(event) => setDither(event.target.checked)} /> Floyd-Steinberg dithering</label></section>
        <button className="primary" onClick={encode}><Sparkles size={17} /> Hide Message in Image</button>{error && <div className="error">{error}</div>}
        <details open={howOpen} onToggle={(event) => setHowOpen((event.target as HTMLDetailsElement).open)}><summary>How was this encoded? <ChevronDown size={16} /></summary><p>Words → dictionary indices → 45 message bits → CRC → 60-bit packet → redundant shape groups across a dense image grid.</p></details>
      </aside>
      <section className="panel stage"><div className="stage-head"><div><label className="eyebrow">ARTWORK PREVIEW</label><h2>{packet ? "Your message is hidden in the image." : "Make something impossible to read at a glance."}</h2></div><div className="actions"><button className={debug ? "active" : ""} onClick={() => setDebug(!debug)}><Bug size={15} /> Debug Grid</button><button onClick={exportPng}><Download size={15} /> Export PNG</button></div></div>
        <nav className="tabs">{["Original", "Dithered", "Symbol Image", "Encoded Image"].map((tab) => <button key={tab} className={mode === tab ? "selected" : ""} onClick={() => setMode(tab)}>{tab}</button>)}</nav>
        <Artwork cells={cells} mode={mode} image={image} width={dimensions.width} height={dimensions.height} debug={debug} zoom={zoom} symbolSize={symbolSize} />
        {cells.length > 0 && <div className="comparison-strip"><div><span>ORIGINAL</span><div className="mini-original" style={{ backgroundImage: image ? `url(${image})` : undefined }} /></div><div><span>DITHERED</span><MiniGrid cells={cells} width={dimensions.width} symbols={false} /></div><div><span>SYMBOLS</span><MiniGrid cells={cells} width={dimensions.width} symbols /></div></div>}
        <div className="stage-foot"><div><span className="mini-dot" /> {packet ? `${dimensions.width * dimensions.height} tiny coloured symbols · redundant shape payload` : "Ready for a cover image"}</div><div className="similarity">{similarity === undefined ? "Visual similarity —" : `Dithered → symbols ${similarity.toFixed(1)}%`}</div></div>
      </section>
    </div>
    <section className="decoder-live panel"><div className="stage-head"><div><label className="eyebrow">DECODER</label><h2>Recover a phrase from the physical artwork.</h2></div><div className="status">IMAGE PIXELS ONLY</div></div><div className="decoder-controls"><div className="dropzone decoder-drop" onClick={() => decoderFileRef.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); onDecoderImage(event.dataTransfer.files[0]); }}><ImagePlus size={22} /><strong>{decoderImage ? "Encoded image loaded" : "Drop encoded PNG or photograph"}</strong><span>PNG, JPEG or WebP · no encoder state used</span><input ref={decoderFileRef} hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => onDecoderImage(event.target.files?.[0])} /></div><label className="upload-row decoder-dictionary"><Upload size={15} /> Load matching .txt or .csv dictionary<input hidden type="file" accept=".txt,.csv,text/plain,text/csv" onChange={(event) => onDecoderDictionary(event.target.files?.[0])} /></label><button className="primary decode-button" onClick={decode}>Decode Symbol Image</button></div>{decoderStatus && <div className={`decode-status ${decodeResult?.ok ? "success" : "failure"}`}>{decoderStatus}</div>}{decodeResult && <div className="decode-report"><div><span>Grid</span><strong>{decodeResult.width} × {decodeResult.height}</strong></div><div><span>Confidence</span><strong>{(decodeResult.confidence * 100).toFixed(1)}%</strong></div><div><span>CRC</span><strong>{decodeResult.crcValid ? "VALID" : "FAILED"}</strong></div>{decodeResult.ok && <div className="decoded-words"><span>Recovered phrase</span><strong>{decodeResult.words?.join(" · ")}</strong></div>}<div className="bit-report"><span>Recovered bits</span><code>{decodeResult.bits.join("")}</code></div></div>}</section>
  </main>;
}
createRoot(document.getElementById("root")!).render(<App />);
