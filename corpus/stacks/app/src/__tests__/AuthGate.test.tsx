import { beforeEach, describe, expect, it } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { AuthGate } from "../components/AuthGate";
import { AUTH_KEY, logout } from "../auth";

function Protected() {
  return <p>catalog is open</p>;
}

function renderGate() {
  render(
    <AuthGate>
      <Protected />
    </AuthGate>,
  );
}

function signIn(user: string, pass: string) {
  fireEvent.change(screen.getByLabelText("User"), { target: { value: user } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: pass } });
  fireEvent.click(screen.getByText("Sign in"));
}

beforeEach(() => {
  window.sessionStorage.clear();
});

describe("AuthGate", () => {
  it("shows the login card when the session flag is absent", () => {
    renderGate();
    expect(screen.getByLabelText("User")).toBeDefined();
    expect(screen.queryByText("catalog is open")).toBeNull();
  });

  it("renders children when the session flag is already set", () => {
    window.sessionStorage.setItem(AUTH_KEY, "1");
    renderGate();
    expect(screen.getByText("catalog is open")).toBeDefined();
  });

  it("keeps the curtain closed on the wrong password", () => {
    renderGate();
    signIn("dev", "not-the-password");
    expect(screen.getByText("Those credentials were not accepted.")).toBeDefined();
    expect(window.sessionStorage.getItem(AUTH_KEY)).toBeNull();
    expect(screen.queryByText("catalog is open")).toBeNull();
  });

  it("opens on dev / dev and closes again on logout", () => {
    renderGate();
    signIn("dev", "dev");
    expect(window.sessionStorage.getItem(AUTH_KEY)).toBe("1");
    expect(screen.getByText("catalog is open")).toBeDefined();
    act(() => {
      logout();
    });
    expect(screen.queryByText("catalog is open")).toBeNull();
    expect(screen.getByLabelText("User")).toBeDefined();
  });
});
