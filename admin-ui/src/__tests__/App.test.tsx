import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { App } from "../App";

// Stub global fetch — the views all call through `api/client.ts`, which
// uses `fetch` under the hood. Returning a benign empty payload for every
// endpoint keeps the views happy without spinning up the real Admin API.

const okJson = (body: unknown): Response =>
  ({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
    text: async () => JSON.stringify(body),
  }) as unknown as Response;

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem("vestigo.admin.token");
  vi.spyOn(window, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    if (url.endsWith("/v1/api-keys")) return okJson({ results: [] });
    if (url.endsWith("/v1/config"))
      return okJson({
        embedding: {
          endpoint: "http://e",
          api_type: "openai-compatible",
          model_name: "e",
          parameters: {},
        },
        reranker: { type: "cross_encoder", endpoint: null, model_name: "r", parameters: {} },
        generation: {
          endpoint: "http://g",
          api_type: "openai-compatible",
          model_name: "g",
          parameters: {},
        },
        chunking: { method: "recursive", size: 1000, overlap: 200, parameters: {} },
        rag_prompt_template: "template",
        default_collection: "default",
      });
    if (url.includes("/v1/audit")) return okJson({ results: [], offset: 0, limit: 100 });
    return okJson({});
  });
});

describe("App", () => {
  it("renders header and tab nav", () => {
    render(<App />);
    expect(screen.getByText("Vestigo Admin")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "API keys" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Configuration" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Audit log" })).toBeInTheDocument();
  });

  it("switches to the Configuration tab on click", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Configuration" }));
    expect(screen.getByRole("heading", { name: "Configuration" })).toBeInTheDocument();
    // Default collection input renders after the GET resolves.
    await waitFor(() => {
      const input = screen.getByLabelText("Default collection") as HTMLInputElement;
      expect(input.value).toBe("default");
    });
  });

  it("switches to the Audit log tab and runs the initial query", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Audit log" }));
    expect(screen.getByRole("heading", { name: "Audit log" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("No events match the current filters.")).toBeInTheDocument();
    });
  });

  it("persists the admin key to localStorage", async () => {
    render(<App />);
    const input = screen.getByPlaceholderText("ADMIN_API_KEY") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "secret" } });
    await waitFor(() => {
      expect(window.localStorage.getItem("vestigo.admin.token")).toBe("secret");
    });
  });

  it("attaches the admin key to authenticated requests", async () => {
    window.localStorage.setItem("vestigo.admin.token", "test-bearer");
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Configuration" }));
    await waitFor(() => {
      const fetchMock = vi.mocked(window.fetch);
      const configCall = fetchMock.mock.calls.find(
        (args) =>
          typeof args[0] === "string" && (args[0] as string).endsWith("/v1/config"),
      );
      expect(configCall).toBeDefined();
      const init = configCall![1] as RequestInit;
      const headers = new Headers(init.headers);
      expect(headers.get("Authorization")).toBe("Bearer test-bearer");
    });
  });
});
