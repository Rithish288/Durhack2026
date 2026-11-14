import { describe, expect, it } from "vitest";
import { buildDenseArtwork, buildPacket, calculateCRC8, nibbleToSymbol, splitIntoSymbols } from "./protocol";
describe("Symbol Pixels protocol", () => {
  it("maps nibbles without changing the alphabet", () => {
    expect(nibbleToSymbol(0)).toMatchObject({ shape: "circle", colour: "red" });
    expect(nibbleToSymbol(14)).toMatchObject({ shape: "heart", colour: "blue" });
  });
  it("creates a 60-bit packet and 15 symbols", () => {
    const packet = buildPacket([0, 1, 29999]);
    expect(packet).toHaveLength(60);
    expect(splitIntoSymbols(packet)).toHaveLength(15);
  });
  it("calculates CRC MSB-first", () => expect(calculateCRC8([0, 0, 0, 0, 0, 0, 0, 1])).toHaveLength(8));
  it("repeats shape payloads across dense artwork without changing colours", () => {
    const packet = buildPacket([0, 1, 2]);
    const colours = Array.from({ length: 32 * 32 }, () => [10, 20, 30] as [number, number, number]);
    const artwork = buildDenseArtwork(packet, colours, 32);
    expect(artwork).toHaveLength(1024);
    expect(artwork[0].colour).toEqual([10, 20, 30]);
  });
});
