import { describe, expect, it } from "vitest";
import {
  formatCurrency,
  formatDuration,
  formatGallons,
  formatMiles,
  formatPricePerGal,
} from "../shared/lib/format";

describe("Formatting Library", () => {
  it("formats currency to exactly 2 decimal places with $ prefix", () => {
    expect(formatCurrency(245.5)).toBe("$245.50");
    expect(formatCurrency(0)).toBe("$0.00");
    expect(formatCurrency(1234.567)).toBe("$1,234.57");
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency(undefined)).toBe("—");
  });

  it("formats price per gallon to 3 decimal places with $ prefix", () => {
    expect(formatPricePerGal(3.299)).toBe("$3.299/gal");
    expect(formatPricePerGal(3.5)).toBe("$3.500/gal");
    expect(formatPricePerGal(null)).toBe("—");
  });

  it("formats miles with 1 decimal place and unit", () => {
    expect(formatMiles(789.24)).toBe("789.2 mi");
    expect(formatMiles(1200)).toBe("1200.0 mi");
    expect(formatMiles(null)).toBe("—");
  });

  it("formats gallons with 2 decimal places and unit", () => {
    expect(formatGallons(45.2)).toBe("45.20 gal");
    expect(formatGallons(0)).toBe("0.00 gal");
    expect(formatGallons(null)).toBe("—");
  });

  it("formats duration minutes to human-readable hours and minutes", () => {
    expect(formatDuration(45)).toBe("45 min");
    expect(formatDuration(60)).toBe("1h 0m");
    expect(formatDuration(125)).toBe("2h 5m");
    expect(formatDuration(null)).toBe("—");
  });
});
