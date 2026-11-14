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

type Grid = { width: number; height: number; cellWidth: number; cellHeight: number };
type Point = { x: number; y: number };

function rotateImageData(source: ImageData, turns: number): ImageData {
  const canvas = document.createElement("canvas");
  canvas.width = turns % 2 ? source.height : source.width; canvas.height = turns % 2 ? source.width : source.height;
  const context = canvas.getContext("2d"); if (!context) throw new Error("Unable to orient artwork.");
  const sourceCanvas = document.createElement("canvas"); sourceCanvas.width = source.width; sourceCanvas.height = source.height;
  sourceCanvas.getContext("2d")?.putImageData(source, 0, 0);
  context.translate(canvas.width / 2, canvas.height / 2); context.rotate(turns * Math.PI / 2);
  context.drawImage(sourceCanvas, -source.width / 2, -source.height / 2);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

function anchorScore(data: ImageData, grid: Grid, column: number, row: number): number {
  const x = Math.floor(column * grid.cellWidth + grid.cellWidth * .2);
  const y = Math.floor(row * grid.cellHeight + grid.cellHeight * .2);
  const width = Math.max(1, Math.floor(grid.cellWidth * .6));
  const height = Math.max(1, Math.floor(grid.cellHeight * .6));
  let dark = 0;
  for (let currentY = y; currentY < y + height; currentY++) for (let currentX = x; currentX < x + width; currentX++) {
    const offset = (currentY * data.width + currentX) * 4;
    if ((data.data[offset] * 3 + data.data[offset + 1] * 6 + data.data[offset + 2]) / 10 < 150) dark++;
  }
  return dark;
}

function orientByAnchors(source: ImageData, grid: Grid): { data: ImageData; grid: Grid; confidence: number } {
  let best = { data: source, grid, score: Number.POSITIVE_INFINITY, confidence: 0 };
  for (let turns = 0; turns < 4; turns++) {
    const data = rotateImageData(source, turns);
    const candidateGrid = turns % 2 ? { width: grid.height, height: grid.width, cellWidth: grid.cellHeight, cellHeight: grid.cellWidth } : grid;
    const scores = [
      anchorScore(data, candidateGrid, 0, 0),
      anchorScore(data, candidateGrid, candidateGrid.width - 1, 0),
      anchorScore(data, candidateGrid, candidateGrid.width - 1, candidateGrid.height - 1),
      anchorScore(data, candidateGrid, 0, candidateGrid.height - 1)
    ];
    const expected = [1, 2, 3, 4];
    const average = scores.reduce((sum, value) => sum + value, 0) / 4;
    const scale = Math.max(1, average / 2);
    const score = scores.reduce((sum, value, index) => sum + Math.abs(value / scale - expected[index]), 0);
    const confidence = Math.max(0, 1 - score / 16);
    if (score < best.score) best = { data, grid: candidateGrid, score, confidence };
  }
  return best;
}

function solveLinear(matrix: number[][]): number[] {
  const rows = matrix.map((row) => [...row]);
  for (let column = 0; column < 8; column++) {
    let pivot = column;
    for (let row = column + 1; row < 8; row++) if (Math.abs(rows[row][column]) > Math.abs(rows[pivot][column])) pivot = row;
    if (Math.abs(rows[pivot][column]) < 1e-8) throw new Error("Perspective correction failed.");
    [rows[column], rows[pivot]] = [rows[pivot], rows[column]];
    const divisor = rows[column][column];
    for (let value = column; value <= 8; value++) rows[column][value] /= divisor;
    for (let row = 0; row < 8; row++) if (row !== column) {
      const factor = rows[row][column];
      for (let value = column; value <= 8; value++) rows[row][value] -= factor * rows[column][value];
    }
  }
  return rows.map((row) => row[8]);
}

function homography(from: Point[], to: Point[]): number[] {
  const equations: number[][] = [];
  from.forEach((point, index) => {
    const target = to[index];
    equations.push([point.x, point.y, 1, 0, 0, 0, -target.x * point.x, -target.x * point.y, target.x]);
    equations.push([0, 0, 0, point.x, point.y, 1, -target.y * point.x, -target.y * point.y, target.y]);
  });
  return solveLinear(equations);
}

function detectCorners(data: ImageData): Point[] {
  const points: Point[] = [];
  for (let y = 0; y < data.height; y += 3) for (let x = 0; x < data.width; x += 3) {
    const offset = (y * data.width + x) * 4;
    const red = data.data[offset], green = data.data[offset + 1], blue = data.data[offset + 2];
    const luminance = (red * 3 + green * 6 + blue) / 10;
    if (luminance < 185 || Math.max(red, green, blue) - Math.min(red, green, blue) > 55) points.push({ x, y });
  }
  if (points.length < 100) throw new Error("Artwork not detected.");
  const sums = points.map((point) => point.x + point.y), differences = points.map((point) => point.x - point.y);
  const corners = [
    points[sums.indexOf(Math.min(...sums))],
    points[differences.indexOf(Math.max(...differences))],
    points[sums.indexOf(Math.max(...sums))],
    points[differences.indexOf(Math.min(...differences))]
  ];
  const area = Math.abs(corners.reduce((sum, point, index) => {
    const next = corners[(index + 1) % corners.length]; return sum + point.x * next.y - next.x * point.y;
  }, 0)) / 2;
  if (area < data.width * data.height * .03) throw new Error("Artwork not detected.");
  return corners;
}

function warpToCanonical(source: ImageData, corners: Point[], width: number, height: number): ImageData {
  const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
  const context = canvas.getContext("2d"); if (!context) throw new Error("Perspective correction failed.");
  const destination = [{ x: 0, y: 0 }, { x: width, y: 0 }, { x: width, y: height }, { x: 0, y: height }];
  const transform = homography(destination, corners);
  const output = context.createImageData(width, height);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const denominator = transform[6] * x + transform[7] * y + 1;
    const sourceX = (transform[0] * x + transform[1] * y + transform[2]) / denominator;
    const sourceY = (transform[3] * x + transform[4] * y + transform[5]) / denominator;
    const sourceXInt = Math.max(0, Math.min(source.width - 1, Math.round(sourceX)));
    const sourceYInt = Math.max(0, Math.min(source.height - 1, Math.round(sourceY)));
    const targetOffset = (y * width + x) * 4, sourceOffset = (sourceYInt * source.width + sourceXInt) * 4;
    for (let channel = 0; channel < 4; channel++) output.data[targetOffset + channel] = source.data[sourceOffset + channel];
  }
  return output;
}

function decodeGrid(data: ImageData, grid: Grid, dictionary: string[]): DecodeResult {
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

export function decodeSymbolImage(image: HTMLImageElement, dictionary: string[]): DecodeResult {
  const sourceCanvas = document.createElement("canvas"); sourceCanvas.width = image.naturalWidth; sourceCanvas.height = image.naturalHeight;
  const sourceContext = sourceCanvas.getContext("2d");
  if (!sourceContext) return { ok: false, status: "Unable to process artwork.", confidence: 0, width: 0, height: 0, bits: [], crcValid: false, error: "Canvas is unavailable." };
  sourceContext.drawImage(image, 0, 0);
  const source = sourceContext.getImageData(0, 0, sourceCanvas.width, sourceCanvas.height);
  try {
    const cleanGrid = inferGrid(image);
    const oriented = orientByAnchors(source, cleanGrid);
    return decodeGrid(oriented.data, oriented.grid, dictionary);
  } catch {
    try {
      const corners = detectCorners(source);
      const edgeWidth = Math.hypot(corners[1].x - corners[0].x, corners[1].y - corners[0].y);
      const edgeHeight = Math.hypot(corners[3].x - corners[0].x, corners[3].y - corners[0].y);
      const aspect = edgeWidth / Math.max(1, edgeHeight);
      const longEdge = 96;
      const width = aspect >= 1 ? longEdge : Math.max(1, Math.round(longEdge * aspect));
      const height = aspect >= 1 ? Math.max(1, Math.round(longEdge / aspect)) : longEdge;
      const canonical = warpToCanonical(source, corners, width * 10, height * 10);
      return decodeGrid(canonical, { width, height, cellWidth: 10, cellHeight: 10 }, dictionary);
    } catch (error) {
      return { ok: false, status: "Unable to detect artwork", confidence: 0, width: 0, height: 0, bits: [], crcValid: false, error: error instanceof Error ? error.message : "Unable to locate or orient the Symbol Pixels artwork." };
    }
  }
}
