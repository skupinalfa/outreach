import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, test, expect, vi, beforeEach } from "vitest";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const apiGetMock = vi.fn();
const apiPostMock = vi.fn();
const apiPatchMock = vi.fn();

vi.mock("@/lib/api", () => ({
  apiGet: (path: string) => apiGetMock(path),
  apiPost: (path: string, body?: unknown) => apiPostMock(path, body),
  apiPatch: (path: string, body: unknown) => apiPatchMock(path, body),
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, body: { code: string; message: string }) {
      super(body.message);
      this.status = status;
      this.code = body.code;
    }
  },
}));

import LeadsPage from "@/app/auth/leads/page";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LeadsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apiGetMock.mockResolvedValue({ items: [], total: 0 });
  apiPostMock.mockResolvedValue({});
  apiPatchMock.mockResolvedValue({});
});

function domainLookupCalls() {
  return apiPostMock.mock.calls.filter(
    ([path]) => path === "/hunter/domain-lookup",
  );
}

describe("Leads form domain gate (FR-004a/b/c/d)", () => {
  test("name/salutation/manual-email inputs are disabled while domain is empty", () => {
    renderPage();
    expect(screen.getByLabelText(/first name/i)).toBeDisabled();
    expect(screen.getByLabelText(/last name/i)).toBeDisabled();
    expect(screen.getByLabelText(/salutation/i)).toBeDisabled();
    expect(screen.getByLabelText(/^email/i)).toBeDisabled();
  });

  test("typing a domain by hand unlocks the gated inputs (manual-domain fallback)", () => {
    renderPage();
    const domainInput = screen.getByLabelText(/^domain$/i);
    fireEvent.change(domainInput, { target: { value: "acme.com" } });
    expect(screen.getByLabelText(/first name/i)).toBeEnabled();
    expect(screen.getByLabelText(/last name/i)).toBeEnabled();
    expect(screen.getByLabelText(/salutation/i)).toBeEnabled();
    expect(screen.getByLabelText(/^email/i)).toBeEnabled();
  });

  test("clearing the domain re-disables the gated inputs", () => {
    renderPage();
    const domainInput = screen.getByLabelText(/^domain$/i);
    fireEvent.change(domainInput, { target: { value: "acme.com" } });
    expect(screen.getByLabelText(/first name/i)).toBeEnabled();

    fireEvent.change(domainInput, { target: { value: "" } });
    expect(screen.getByLabelText(/first name/i)).toBeDisabled();
    expect(screen.getByLabelText(/last name/i)).toBeDisabled();
    expect(screen.getByLabelText(/^email/i)).toBeDisabled();
  });

  test("blur / Enter on company name does NOT auto-trigger domain lookup", async () => {
    renderPage();
    const nameInput = screen.getByLabelText(/company name/i);
    fireEvent.change(nameInput, { target: { value: "Stripe" } });
    fireEvent.blur(nameInput);
    fireEvent.keyDown(nameInput, { key: "Enter", code: "Enter" });

    // Give effects / autocomplete queries time to settle before we assert.
    await waitFor(() => {
      // The org-autocomplete `apiGet` may have fired for /organisations — that's fine.
      // What must NOT happen is a Hunter Domain-lookup POST.
      expect(domainLookupCalls()).toHaveLength(0);
    });
  });

  test("clicking 'Look up domain' issues exactly one /hunter/domain-lookup call and unlocks the gate", async () => {
    apiPostMock.mockResolvedValueOnce({
      domain: "stripe.com",
      confidence: null,
      source: "hunter",
      message: null,
    });
    renderPage();

    fireEvent.change(screen.getByLabelText(/company name/i), {
      target: { value: "Stripe" },
    });
    fireEvent.click(screen.getByRole("button", { name: /look up domain/i }));

    await waitFor(() => {
      expect(domainLookupCalls()).toHaveLength(1);
      expect(domainLookupCalls()[0][1]).toEqual({ company_name: "Stripe" });
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/^domain$/i)).toHaveValue("stripe.com");
      expect(screen.getByLabelText(/first name/i)).toBeEnabled();
    });
  });

  test("picking an existing organisation opens the gate without a domain-lookup call (FR-004c)", async () => {
    apiGetMock.mockResolvedValue({
      items: [
        {
          id: 42,
          name: "Stripe",
          domain: "stripe.com",
          notes: "",
          created_at: "",
          updated_at: "",
        },
      ],
      total: 1,
    });
    renderPage();

    fireEvent.change(screen.getByLabelText(/company name/i), {
      target: { value: "Stripe" },
    });

    // Wait for the suggestion listbox to render and pick the existing org.
    const pickOption = await screen.findByRole("option", { name: /stripe/i });
    fireEvent.click(pickOption);

    // Gate opens immediately, domain pre-filled from the org record.
    expect(screen.getByLabelText(/^domain$/i)).toHaveValue("stripe.com");
    expect(screen.getByLabelText(/first name/i)).toBeEnabled();
    expect(screen.getByLabelText(/last name/i)).toBeEnabled();
    expect(screen.getByLabelText(/^email/i)).toBeEnabled();

    // No Hunter Domain-lookup call was issued (FR-004c bypass).
    expect(domainLookupCalls()).toHaveLength(0);

    // "Look up domain" is also disabled while an existing-org binding is active.
    expect(screen.getByRole("button", { name: /look up domain/i })).toBeDisabled();
  });
});
