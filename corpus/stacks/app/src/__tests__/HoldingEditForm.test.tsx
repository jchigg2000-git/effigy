import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { HoldingEditForm } from "../components/HoldingEditForm";
import type { Holding } from "../api/client";

const HOLDING: Holding = {
  holdingId: "STK00000003",
  branchId: "BR-NORTHGATE",
  author: "MELVILLE, HERMAN",
  title: "MOBY-DICK",
  published: "1851",
  language: "EN",
  deskPhone: "15550102",
  shelf: { callNumber: "PR4571 .A1 1851", room: "R3", wing: "SW", bin: "01430" },
  loans: [],
};

function renderForm() {
  const onSave = vi.fn();
  render(
    <HoldingEditForm
      holding={HOLDING}
      saving={false}
      onCancel={() => {}}
      onSave={onSave}
    />,
  );
  return onSave;
}

function typeInto(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function save() {
  fireEvent.click(screen.getByText("Save changes"));
}

function valueOf(label: string) {
  return (screen.getByLabelText(label) as HTMLInputElement).value;
}

describe("HoldingEditForm", () => {
  it("seeds every field from the holding", () => {
    renderForm();
    expect(valueOf("Author")).toBe("MELVILLE, HERMAN");
    expect(valueOf("Call number")).toBe("PR4571 .A1 1851");
    expect(valueOf("Wing")).toBe("SW");
    expect(valueOf("Bin")).toBe("01430");
  });

  it("rejects a wing that is not two letters", () => {
    const onSave = renderForm();
    typeInto("Wing", "SWX");
    save();
    expect(screen.getByText("wing must be a 2-letter code or empty")).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("rejects a bin that is not five digits", () => {
    const onSave = renderForm();
    typeInto("Bin", "142");
    save();
    expect(screen.getByText("bin must be 5 digits or empty")).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("rejects a language outside the accepted set", () => {
    const onSave = renderForm();
    typeInto("Language", "DE");
    save();
    expect(
      screen.getByText("language must be one of EN, ES, FR, UND, or empty"),
    ).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("rejects a desk phone that is not digits only", () => {
    const onSave = renderForm();
    typeInto("Desk phone", "+1-555-0102");
    save();
    expect(screen.getByText("deskPhone must be digits only")).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("treats a lowercase retype of the stored title as unchanged", () => {
    const onSave = renderForm();
    typeInto("Title", "moby-dick");
    typeInto("Room", "R4");
    save();
    expect(onSave).toHaveBeenCalledWith({ shelf: { room: "R4" } });
  });

  it("sends only the fields that actually moved", () => {
    const onSave = renderForm();
    typeInto("Author", "melville, herman jr");
    typeInto("Bin", "01431");
    save();
    expect(onSave).toHaveBeenCalledWith({
      author: "MELVILLE, HERMAN JR",
      shelf: { bin: "01431" },
    });
  });
});
