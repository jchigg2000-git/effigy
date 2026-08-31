import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { SearchForm } from "../components/SearchForm";
import type { SearchFilters } from "../api/client";

const EMPTY: SearchFilters = { limit: 50 };

function renderForm(filters: SearchFilters, onChange = vi.fn()) {
  render(
    <SearchForm
      filters={filters}
      busy={false}
      onChange={onChange}
      onSubmit={() => {}}
      onReset={() => {}}
    />,
  );
  return onChange;
}

describe("SearchForm", () => {
  it("keeps submit disabled until a filter is present", () => {
    renderForm(EMPTY);
    const submit = screen.getByText("Search") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    expect(screen.getByText(/At least one filter is required/)).toBeDefined();
  });

  it("enables submit once any filter is set", () => {
    renderForm({ ...EMPTY, shelfBin: "01420" });
    expect((screen.getByText("Search") as HTMLButtonElement).disabled).toBe(false);
  });

  it("reports typed text back to the caller", () => {
    const onChange = renderForm(EMPTY);
    fireEvent.change(screen.getByLabelText("Title contains"), {
      target: { value: "moby" },
    });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ title: "moby", limit: 50 }),
    );
  });

  it("offers exactly the three branch ids plus any", () => {
    renderForm(EMPTY);
    const select = screen.getByLabelText("Branch") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(["", "BR-CENTRAL", "BR-EASTSIDE", "BR-NORTHGATE"]);
  });
});
