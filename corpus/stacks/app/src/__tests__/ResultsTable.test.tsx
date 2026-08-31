import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ResultsTable } from "../components/ResultsTable";
import type { HoldingSummary } from "../api/client";

const ROWS: HoldingSummary[] = [
  {
    holdingId: "STK00000001",
    branchId: "BR-CENTRAL",
    author: "DICKENS, CHARLES",
    title: "A TALE OF TWO CITIES",
    published: "1859",
    room: "R2",
    wing: "NW",
    bin: "01420",
  },
  {
    holdingId: "STK00000002",
    branchId: "BR-EASTSIDE",
    author: "AUSTEN, JANE",
    title: "PRIDE AND PREJUDICE",
    published: "1813",
    room: "R1",
    wing: "SE",
  },
];

describe("ResultsTable", () => {
  it("shows an empty note when there is nothing to list", () => {
    render(<ResultsTable rows={[]} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText("No holdings matched those filters.")).toBeDefined();
  });

  it("renders one row per holding with a dash for absent shelf parts", () => {
    render(<ResultsTable rows={ROWS} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText("A TALE OF TWO CITIES")).toBeDefined();
    expect(screen.getByText("PRIDE AND PREJUDICE")).toBeDefined();
    expect(screen.getByText("01420")).toBeDefined();
    expect(screen.getAllByText("—").length).toBe(1);
  });

  it("reports the clicked holding id", () => {
    const onSelect = vi.fn();
    render(<ResultsTable rows={ROWS} selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("AUSTEN, JANE"));
    expect(onSelect).toHaveBeenCalledWith("STK00000002");
  });

  it("marks the selected row", () => {
    const { container } = render(
      <ResultsTable rows={ROWS} selectedId="STK00000001" onSelect={() => {}} />,
    );
    const selected = container.querySelectorAll("tr.row-selected");
    expect(selected.length).toBe(1);
    expect(selected[0].textContent).toContain("STK00000001");
  });
});
