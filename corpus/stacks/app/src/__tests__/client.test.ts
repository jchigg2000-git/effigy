import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  buildSearchUrl,
  dcExportUrl,
  getHolding,
  hasAnyFilter,
  patchHolding,
  searchHoldings,
  type Holding,
} from "../api/client";

const HOLDING: Holding = {
  holdingId: "STK00000001",
  branchId: "BR-CENTRAL",
  author: "DICKENS, CHARLES",
  title: "A TALE OF TWO CITIES",
  published: "1859",
  language: "EN",
  materialCode: "BK",
  circStatus: "SHELVED",
  collectionCode: "GEN",
  isbn: "978-0-00-000001-9",
  deskPhone: "15550101",
  shelf: { callNumber: "823.8 D548d", room: "R2", wing: "NW", bin: "01420" },
  branch: {
    branchId: "BR-CENTRAL",
    name: "Central Branch",
    registrySymbol: "ocm00000001",
    systemId: "lcc00000001",
  },
  loans: [
    {
      type: "STANDARD",
      level: "REGULAR",
      policyCode: "LOAN-21",
      effectiveStart: "2026-01-05",
      effectiveEnd: "2026-01-26",
    },
  ],
};

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function errorResponse(status: number, code: string, message: string) {
  return jsonResponse(status, { error: { code, message } });
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("buildSearchUrl", () => {
  it("puts every supplied filter on the query string", () => {
    const url = buildSearchUrl({
      title: "walden",
      author: "thoreau",
      holdingId: "STK00000010",
      published: "1854",
      branchId: "BR-NORTHGATE",
      shelfBin: "01420",
      limit: 25,
    });
    expect(url.startsWith("/api/holdings/search?")).toBe(true);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("title")).toBe("walden");
    expect(params.get("author")).toBe("thoreau");
    expect(params.get("holdingId")).toBe("STK00000010");
    expect(params.get("published")).toBe("1854");
    expect(params.get("branchId")).toBe("BR-NORTHGATE");
    expect(params.get("shelfBin")).toBe("01420");
    expect(params.get("limit")).toBe("25");
  });

  it("omits absent filters entirely", () => {
    expect(buildSearchUrl({ title: "dracula" })).toBe(
      "/api/holdings/search?title=dracula",
    );
  });

  it("escapes values that need escaping", () => {
    expect(buildSearchUrl({ author: "verne, jules" })).toContain(
      "author=verne%2C+jules",
    );
  });
});

describe("hasAnyFilter", () => {
  it("is false for an empty filter set", () => {
    expect(hasAnyFilter({})).toBe(false);
  });

  it("is false when only limit is set", () => {
    expect(hasAnyFilter({ limit: 50 })).toBe(false);
  });

  it("is true for any single filter", () => {
    expect(hasAnyFilter({ shelfBin: "01420" })).toBe(true);
    expect(hasAnyFilter({ branchId: "BR-EASTSIDE" })).toBe(true);
  });
});

describe("searchHoldings", () => {
  it("refuses to call the server with no filters", async () => {
    await expect(searchHoldings({})).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("carries the server-side message on the thrown error", async () => {
    await expect(searchHoldings({})).rejects.toThrow(
      "at least one filter required (title, author, holdingId, published, branchId, shelfBin)",
    );
  });

  it("returns the parsed response envelope", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { count: 1, holdings: [{ holdingId: "STK00000001" }] }),
    );
    const res = await searchHoldings({ title: "tale" });
    expect(res.count).toBe(1);
    expect(res.holdings[0].holdingId).toBe("STK00000001");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/holdings/search?title=tale");
  });
});

describe("getHolding", () => {
  it("encodes the id into the path", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, HOLDING));
    const holding = await getHolding("STK00000001");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/holdings/STK00000001");
    expect(holding.title).toBe("A TALE OF TWO CITIES");
    expect(holding.shelf.bin).toBe("01420");
  });

  it("turns the error envelope into an ApiError", async () => {
    fetchMock.mockResolvedValue(
      errorResponse(404, "not_found", "holding not found"),
    );
    await expect(getHolding("STK00009999")).rejects.toMatchObject({
      status: 404,
      code: "not_found",
      message: "holding not found",
    });
  });

  it("falls back when the body is not the envelope", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("body was not json");
      },
    });
    await expect(getHolding("STK00000001")).rejects.toMatchObject({
      status: 500,
      code: "internal",
    });
  });
});

describe("patchHolding", () => {
  it("sends PATCH with a json content type and a serialised body", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, HOLDING));
    await patchHolding("STK00000001", {
      title: "WALDEN",
      shelf: { bin: "01421" },
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/holdings/STK00000001");
    expect(init.method).toBe("PATCH");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({
      title: "WALDEN",
      shelf: { bin: "01421" },
    });
  });
});

describe("dcExportUrl", () => {
  it("builds the download path without fetching it", () => {
    expect(dcExportUrl("STK00000001")).toBe(
      "/api/holdings/STK00000001/export/dc",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
