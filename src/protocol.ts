export const GRID_SIZE = 8;
export const ANCHOR_CELLS = [0, 7, 63, 56] as const;
export const SYMBOL_COUNT = 15;
export const REPEAT_COUNT = 4;
export const PAYLOAD_CELLS = 60;
export const MAX_WORDS = 30000;

export type Shape = "circle" | "triangle" | "star" | "heart";
export type Colour = "red" | "yellow" | "blue" | "black";
export type Symbol = { value: number; shape: Shape; colour: Colour };
export type Cell = { anchor?: number; symbol?: Symbol; payload?: number; copy?: number; targetColour?: RGB };
export type RGB = [number, number, number];
export type DenseCell = { colour: RGB; shape: Shape; payloadGroup?: number; repetition?: number; anchor?: number };
export const DEFAULT_PALETTE: RGB[] = [[18, 24, 35], [224, 68, 78], [245, 180, 45], [53, 126, 190], [52, 164, 111], [132, 82, 176], [231, 112, 52], [226, 226, 214]];

export function renderShape(context: CanvasRenderingContext2D, shape: Shape, x: number, y: number, size: number, colour: string): void {
  context.save(); context.translate(x, y); context.scale(size / 100, size / 100); context.fillStyle = colour; context.beginPath();
  if (shape === "circle") context.arc(50, 50, 44, 0, Math.PI * 2);
  if (shape === "triangle") { context.moveTo(50, 5); context.lineTo(96, 92); context.lineTo(4, 92); context.closePath(); }
  if (shape === "star") { context.moveTo(50, 4); context.lineTo(61, 36); context.lineTo(96, 36); context.lineTo(68, 56); context.lineTo(79, 91); context.lineTo(50, 70); context.lineTo(21, 91); context.lineTo(32, 56); context.lineTo(4, 36); context.lineTo(39, 36); context.closePath(); }
  if (shape === "heart") { context.moveTo(50, 91); context.bezierCurveTo(42, 83, 8, 62, 8, 33); context.bezierCurveTo(8, 10, 36, 2, 50, 23); context.bezierCurveTo(64, 2, 92, 10, 92, 33); context.bezierCurveTo(92, 62, 58, 83, 50, 91); context.closePath(); }
  context.fill(); context.restore();
}

export function loadDictionary(text: string): string[] {
  return text.split(/\r?\n/).map((word) => word.trim()).filter(Boolean).slice(0, MAX_WORDS);
}
export function loadDictionaryCsv(text: string): string[] {
  const rows: string[][] = [];
  let row: string[] = [], field = "", quoted = false;
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (character === '"') {
      if (quoted && text[index + 1] === '"') { field += '"'; index++; }
      else quoted = !quoted;
    } else if (character === "," && !quoted) { row.push(field.trim()); field = ""; }
    else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && text[index + 1] === "\n") index++;
      row.push(field.trim()); if (row.some(Boolean)) rows.push(row);
      row = []; field = "";
    } else field += character;
  }
  row.push(field.trim()); if (row.some(Boolean)) rows.push(row);
  const firstValues = rows.map((fields) => fields.find(Boolean) ?? "").filter(Boolean);
  const first = firstValues[0]?.toLowerCase();
  return first && ["word", "words", "dictionary", "term"].includes(first) ? firstValues.slice(1, MAX_WORDS + 1) : firstValues.slice(0, MAX_WORDS);
}
export function wordToIndex(word: string, dictionary: string[]): number {
  return dictionary.findIndex((entry) => entry.toLowerCase() === word.trim().toLowerCase());
}
export function indexTo15Bits(index: number): number[] {
  if (!Number.isInteger(index) || index < 0 || index >= MAX_WORDS) throw new Error("Dictionary index must be between 0 and 29999.");
  return Array.from({ length: 15 }, (_, bit) => (index >> (14 - bit)) & 1);
}
export function calculateCRC8(bits: number[]): number[] {
  let crc = 0;
  for (const bit of bits) {
    const mix = ((crc >> 7) & 1) ^ bit;
    crc = (crc << 1) & 0xff;
    if (mix) crc ^= 0x07;
  }
  return Array.from({ length: 8 }, (_, bit) => (crc >> (7 - bit)) & 1);
}
export function buildPacket(indices: number[]): number[] {
  if (indices.length !== 3) throw new Error("Exactly three dictionary indices are required.");
  const message = indices.flatMap(indexTo15Bits);
  return [...message, ...calculateCRC8(message), ...Array(7).fill(0)];
}
export function splitIntoSymbols(packet: number[]): number[] {
  if (packet.length !== 60) throw new Error("Packet must contain exactly 60 bits.");
  return Array.from({ length: 15 }, (_, i) => packet.slice(i * 4, i * 4 + 4).reduce((n, bit) => (n << 1) | bit, 0));
}
export function nibbleToSymbol(value: number): Symbol {
  const shapes: Shape[] = ["circle", "triangle", "star", "heart"];
  const colours: Colour[] = ["red", "yellow", "blue", "black"];
  return { value, shape: shapes[value >> 2], colour: colours[value & 3] };
}
export function calculateColourDistance(a: RGB, b: RGB): number {
  const toLab = ([r, g, bl]: RGB) => {
    const linear = (v: number) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    const [x, y, z] = [linear(r) * 0.4124 + linear(g) * 0.3576 + linear(bl) * 0.1805, linear(r) * 0.2126 + linear(g) * 0.7152 + linear(bl) * 0.0722, linear(r) * 0.0193 + linear(g) * 0.1192 + linear(bl) * 0.9505];
    const f = (v: number) => v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116;
    return [116 * f(y) - 16, 500 * (f(x / 0.95047) - f(y)), 200 * (f(y) - f(z / 1.08883))];
  };
  const [l1, a1, b1] = toLab(a), [l2, a2, b2] = toLab(b);
  return Math.hypot(l1 - l2, a1 - a2, b1 - b2);
}
export function sampleCoverImage(image: HTMLImageElement, size = GRID_SIZE): RGB[] {
  const canvas = document.createElement("canvas"); canvas.width = canvas.height = size;
  const context = canvas.getContext("2d"); if (!context) throw new Error("Unable to sample cover image.");
  context.drawImage(image, 0, 0, size, size);
  const data = context.getImageData(0, 0, size, size).data;
  return Array.from({ length: size * size }, (_, i) => [data[i * 4], data[i * 4 + 1], data[i * 4 + 2]] as RGB);
}
export function quantiseImage(pixels: RGB[], palette: RGB[] = DEFAULT_PALETTE, dither = true, width = 8): RGB[] {
  const output = pixels.map((pixel) => [...pixel] as RGB);
  const nearest = (pixel: RGB) => palette.reduce((best, candidate, index) => calculateColourDistance(pixel, candidate) < calculateColourDistance(pixel, palette[best]) ? index : best, 0);
  for (let index = 0; index < output.length; index++) {
    const colour = palette[nearest(output[index])];
    const source = output[index];
    output[index] = [...colour] as RGB;
    if (!dither) continue;
    const error = source.map((channel, i) => channel - colour[i]);
    const diffuse = (offset: number, weight: number) => {
      const target = index + offset;
      const row = Math.floor(index / width), column = index % width;
      const targetRow = Math.floor(target / width), targetColumn = target % width;
      if (target >= 0 && target < output.length && targetRow >= row && targetColumn >= 0 && targetColumn < width && Math.abs(targetColumn - column) <= 1) output[target] = output[target].map((channel, i) => Math.max(0, Math.min(255, channel + error[i] * weight))) as RGB;
    };
    diffuse(1, 7 / 16); diffuse(width - 1, 3 / 16); diffuse(width, 5 / 16); diffuse(width + 1, 1 / 16);
  }
  return output;
}
export function sampleAndQuantiseImage(image: HTMLImageElement, width: number, height = width, palette: RGB[] = DEFAULT_PALETTE, dither = true): RGB[] {
  const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
  const context = canvas.getContext("2d"); if (!context) throw new Error("Unable to sample cover image.");
  context.drawImage(image, 0, 0, width, height);
  const data = context.getImageData(0, 0, width, height).data;
  const pixels = Array.from({ length: width * height }, (_, i) => [data[i * 4], data[i * 4 + 1], data[i * 4 + 2]] as RGB);
  return quantiseImage(pixels, palette, dither, width);
}
export function buildDenseArtwork(packet: number[], colours: RGB[], width: number, height = width): DenseCell[] {
  if (packet.length !== 60 || colours.length !== width * height) throw new Error("Dense artwork requires a 60-bit packet and one colour per cell.");
  const shapeValues = Array.from({ length: 30 }, (_, i) => (packet[i * 2] << 1) | packet[i * 2 + 1]);
  const repeat = Math.max(1, Math.floor(colours.length / shapeValues.length));
  let dataIndex = 0;
  const cells = colours.map((colour, index) => {
    const row = Math.floor(index / width), column = index % width;
    const anchor = row === 0 && column === 0 ? 1 : row === 0 && column === width - 1 ? 2 : row === height - 1 && column === width - 1 ? 3 : row === height - 1 && column === 0 ? 4 : undefined;
    if (anchor) return { colour, shape: "circle" as Shape, anchor };
    const payloadGroup = Math.floor(dataIndex / repeat);
    const value = shapeValues[payloadGroup % shapeValues.length];
    dataIndex++;
    return { colour, shape: (["circle", "triangle", "star", "heart"] as Shape[])[value], payloadGroup: payloadGroup % shapeValues.length, repetition: Math.floor(dataIndex / shapeValues.length) + 1 };
  });
  return cells;
}
export function optimisePlacement(symbols: Symbol[], targetColours?: RGB[]): Symbol[] {
  if (!targetColours) return symbols.flatMap((symbol) => Array(REPEAT_COUNT).fill(symbol));
  const colour: Record<Colour, RGB> = { red: [232, 77, 93], yellow: [232, 172, 39], blue: [57, 126, 183], black: [22, 26, 36] };
  const remaining: Symbol[] = symbols.flatMap((symbol) => Array.from({ length: REPEAT_COUNT }, () => symbol));
  return targetColours.slice(0, PAYLOAD_CELLS).map((target) => {
    let best = 0;
    remaining.forEach((candidate, i) => { if (calculateColourDistance(colour[candidate.colour], target) < calculateColourDistance(colour[remaining[best].colour], target)) best = i; });
    return remaining.splice(best, 1)[0];
  });
}
export function buildGrid(symbols: Symbol[], targetColours?: RGB[]): Cell[] {
  if (symbols.length !== SYMBOL_COUNT) throw new Error("Exactly 15 symbols are required.");
  const grid: Cell[] = Array.from({ length: 64 }, () => ({}));
  [1, 2, 3, 4].forEach((dots, i) => { grid[ANCHOR_CELLS[i]] = { anchor: dots }; });
  const placed = optimisePlacement(symbols, targetColours);
  let cursor = 0;
  for (let cell = 0; cell < 64; cell++) if (!ANCHOR_CELLS.includes(cell as typeof ANCHOR_CELLS[number])) {
    const payload = (cursor * 17) % 60;
    const symbol = placed[payload];
    grid[cell] = { symbol, payload: symbols.indexOf(symbol), copy: Math.floor(payload / SYMBOL_COUNT) + 1, targetColour: targetColours?.[cursor] };
    cursor++;
  }
  return grid;
}
export function validateEncoding(indices: number[], packet: number[], symbols: number[], grid: Cell[]): string[] {
  const errors: string[] = [];
  if (indices.length !== 3 || indices.some((n) => n < 0 || n >= MAX_WORDS)) errors.push("Exactly 3 valid words with indices below 30000 are required.");
  if (packet.length !== 60) errors.push("Packet must be 60 bits (45 message + 8 CRC + 7 padding).");
  if (symbols.length !== 15) errors.push("Packet must split into 15 four-bit symbols.");
  if (grid.filter((cell) => cell.symbol).length !== PAYLOAD_CELLS) errors.push("All 60 payload cells must be populated.");
  if (grid.filter((cell) => cell.anchor).length !== 4) errors.push("All 4 orientation anchors are required.");
  return errors;
}
