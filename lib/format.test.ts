import { describe, expect, it } from "vitest";
import {
  bpToIndex,
  dayLabel,
  factorLabel,
  minuteLabel,
  percentFromRatio,
  reasonLabel,
  titleCase,
} from "./format";

describe("bpToIndex", () => {
  it("converts basis points to a two-decimal index", () => {
    expect(bpToIndex(0)).toBe("0.00");
    expect(bpToIndex(6000)).toBe("60.00");
    expect(bpToIndex(8764)).toBe("87.64");
    expect(bpToIndex(10000)).toBe("100.00");
  });
});

describe("percentFromRatio", () => {
  it("formats decimal ratio strings as percentages", () => {
    expect(percentFromRatio("1.0000")).toBe("100.0%");
    expect(percentFromRatio("0.5745")).toBe("57.5%");
  });
  it("returns a dash for null", () => {
    expect(percentFromRatio(null)).toBe("—");
  });
});

describe("time helpers", () => {
  it("labels days from Monday", () => {
    expect(dayLabel(0)).toBe("Mon");
    expect(dayLabel(4)).toBe("Fri");
  });
  it("labels minutes as HH:MM", () => {
    expect(minuteLabel(0)).toBe("00:00");
    expect(minuteLabel(13 * 60)).toBe("13:00");
    expect(minuteLabel(9 * 60 + 30)).toBe("09:30");
  });
});

describe("label helpers", () => {
  it("maps reason codes to readable labels", () => {
    expect(reasonLabel("capacity_competition")).toBe("Limited capacity across the cohort");
    expect(reasonLabel("unknown_code")).toBe("Unknown Code");
  });
  it("maps factor keys to readable labels", () => {
    expect(factorLabel("technical_skill")).toBe("Technical skill overlap");
  });
  it("title-cases snake and kebab case", () => {
    expect(titleCase("run_approved")).toBe("Run Approved");
    expect(titleCase("first-time")).toBe("First Time");
  });
});
