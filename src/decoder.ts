import { calculateCRC8, renderShape, type Shape } from "./protocol";

export type DecodeResult = {
  ok: boolean;
  status: string;
  confidence: number;
  width: number;
  height: number;
  bits: number[];
  crcValid: boolean;
  indices?: number[];
  words?: string[];
  error?: string;
};

const shapeBits: Record<Shape, number[]> = { circle: [0, 0], triangle: [0, 1], star: [1, 0], heart: [1, 1] };

function foregroundMask(data: ImageData, x: number, y: number, width: number, height: number): boolean[][] {
  const mask: boolean[][] = [];
  for (let row = 0; row < height; row++) {
    const line: boolean[] = [];
    for (let column = 0; column < width; column++) {
      const offset = ((y + row) * data.width + x + column) * 4;
      const distance = Math.hypot(data.data[offset] - 244, data.data[offset + 1] - 240, data.data[offset + 2] - 232);
      line.push(distance > 24);
    }
    mask.push(line);
  }
  return mask;
}

function template(shape: Shape, width: number, height: number): boolean[][] {
  const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
  const context = canvas.getContext("2d"); if (!context) throw new Error("Unable to create shape template.");
  context.fillStyle = "#f4f0e8"; context.fillRect(0, 0, width, height);
  renderShape(context, shape, width * .04, height * .04, Math.min(width, height) * .92, "#11141d");
  const innerX = Math.floor(width * .08), innerY = Math.floor(height * .08);
  return foregroundMask(context.getImageData(0, 0, width, height), innerX, innerY, Math.max(2, Math.floor(width * .84)), Math.max(2, Math.floor(height * .84)));
}

function mismatch(actual: boolean[][], expected: boolean[][]): number {
  let different = 0;
  for (let row = 0; row < actual.length; row++) for (let column = 0; column < actual[row].length; column++) if (actual[row][column] !== expected[row][column]) different++;
  return different / (actual.length * actual[0].length);
}

function classifyCell(data: ImageData, x: number, y: number, width: number, height: number): { shape: Shape; confidence: number } {
  const innerX = x + Math.floor(width * .08), innerY = y + Math.floor(height * .08);
  const innerWidth = Math.max(2, Math.floor(width * .84)), innerHeight = Math.max(2, Math.floor(height * .84));
  const actual = foregroundMask(data, innerX, innerY, innerWidth, innerHeight);
  const shapes: Shape[] = ["circle", "triangle", "star", "heart"];
  const scores = shapes.map((shape) => mismatch(actual, template(shape, width, height)));
  const best = scores.indexOf(Math.min(...scores));
  return { shape: shapes[best], confidence: Math.max(0, 1 - scores[best] * 2.5) };
}

function inferGrid(image: HTMLImageElement): { width: number; height: number; cellWidth: number; cellHeight: number } {
  const cleanWidth = image.naturalWidth / 10, cleanHeight = image.naturalHeight / 10;
  if ([64, 96, 128].includes(cleanWidth) && Number.isInteger(cleanHeight)) return { width: cleanWidth, height: cleanHeight, cellWidth: 10, cellHeight: 10 };
  if ([64, 96, 128].includes(cleanHeight) && Number.isInteger(cleanWidth)) return { width: cleanWidth, height: cleanHeight, cellWidth: 10, cellHeight: 10 };
  throw new Error("Unable to locate or orient the Symbol Pixels artwork.");
}

export function decodeSymbolImage(image: HTMLImageElement, dictionary: string[]): DecodeResult {
  let grid: { width: number; height: number; cellWidth: number; cellHeight: number };
  try { grid = inferGrid(image); } catch (error) {
    return { ok: false, status: "Unable to detect artwork", confidence: 0, width: 0, height: 0, bits: [], crcValid: false, error: error instanceof Error ? error.message : "Unable to locate or orient the Symbol Pixels artwork." };
  }
  const canvas = document.createElement("canvas"); canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d"); if (!context) return { ok: false, status: "Unable to process artwork.", confidence: 0, width: grid.width, height: grid.height, bits: [], crcValid: false, error: "Canvas is unavailable." };
  context.drawImage(image, 0, 0);
  const data = context.getImageData(0, 0, canvas.width, canvas.height);
  const totalCells = grid.width * grid.height - 4;
  const repeat = Math.max(1, Math.floor(totalCells / 30));
  const votes = Array.from({ length: 30 }, () => new Map<Shape, number>());
  let dataIndex = 0;
  let confidenceTotal = 0;
  for (let row = 0; row < grid.height; row++) for (let column = 0; column < grid.width; column++) {
    if ((row === 0 || row === grid.height - 1) && (column === 0 || column === grid.width - 1)) continue;
    const result = classifyCell(data, Math.floor(column * grid.cellWidth), Math.floor(row * grid.cellHeight), Math.ceil(grid.cellWidth), Math.ceil(grid.cellHeight));
    const group = Math.min(29, Math.floor(dataIndex / repeat));
    votes[group].set(result.shape, (votes[group].get(result.shape) ?? 0) + result.confidence);
    confidenceTotal += result.confidence; dataIndex++;
  }
  const bits = votes.flatMap((vote) => {
    const shape = [...vote.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "circle";
    return shapeBits[shape];
  });
  const messageBits = bits.slice(0, 45), recoveredCrc = bits.slice(45, 53), padding = bits.slice(53, 60);
  const calculatedCrc = calculateCRC8(messageBits);
  const crcValid = recoveredCrc.length === 8 && calculatedCrc.every((bit, index) => bit === recoveredCrc[index]);
  const paddingValid = padding.length === 7 && padding.every((bit) => bit === 0);
  const confidence = confidenceTotal / Math.max(1, dataIndex);
  if (!crcValid || !paddingValid) return { ok: false, status: "CRC failed", confidence, width: grid.width, height: grid.height, bits, crcValid, error: "Decode failed integrity checks. Retake the photograph or use a clearer image." };
  const indices = [0, 1, 2].map((word) => messageBits.slice(word * 15, word * 15 + 15).reduce((value, bit) => (value << 1) | bit, 0));
  if (indices.some((index) => index < 0 || index >= 30000 || index >= dictionary.length)) return { ok: false, status: "Dictionary mismatch", confidence, width: grid.width, height: grid.height, bits, crcValid, error: "Recovered indices do not exist in the loaded dictionary." };
  return { ok: true, status: confidence < .55 ? "Decoded with low visual confidence but valid CRC" : "Decoded successfully", confidence, width: grid.width, height: grid.height, bits, crcValid, indices, words: indices.map((index) => dictionary[index]) };
}
