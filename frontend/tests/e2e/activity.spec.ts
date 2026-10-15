import { test, expect, request as pwRequest, type APIRequestContext } from "@playwright/test";

// Feature 002: per-contact Activity tab (US1) + save-to-mailbox (US3).
// Covers spec § US1 acceptance scenarios 1–4 and § US3 acceptance scenarios 1–5.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MASTER_PASSWORD = process.env.PLAYWRIGHT_MASTER_PASSWORD ?? "12345678";

async function apiLogin(): Promise<APIRequestContext> {
  const api = await pwRequest.newContext({ baseURL: API_URL });
  const resp = await api.post("/api/v1/auth/login", {
    data: { password: MASTER_PASSWORD },
  });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  return api;
}

async function uiLogin(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/password/i).fill(MASTER_PASSWORD);
  await page.getByRole("button", { name: /log in|sign in|submit/i }).click();
}

async function seedContact(
  api: APIRequestContext,
  suffix: string,
): Promise<{ contactId: number; orgId: number }> {
  const orgResp = await api.post("/api/v1/organisations", {
    data: { name: `ActivityOrg-${suffix}` },
  });
  expect(orgResp.ok(), await orgResp.text()).toBeTruthy();
  const org = await orgResp.json();
  const contactResp = await api.post("/api/v1/contacts", {
    data: {
      organisation_id: org.id,
      first_name: "Max",
      last_name: `Activity-${suffix}`,
      email: `max+${suffix}@activity.example`,
    },
  });
  expect(contactResp.ok(), await contactResp.text()).toBeTruthy();
  const contact = await contactResp.json();
  return { contactId: contact.id, orgId: org.id };
}

test.describe("us1 per-contact activity timeline", () => {
  test("fresh contact shows a lead_created event (US1 acceptance scenario 4)", async ({
    page,
  }) => {
    const api = await apiLogin();
    const { contactId } = await seedContact(api, `${Date.now()}`);

    await uiLogin(page);
    await page.goto(`/auth/leads/${contactId}`);

    await page.getByRole("button", { name: /^activity$/i }).click();
    // Empty-state text should NOT appear because lead_created is auto-recorded.
    await expect(page.getByText(/no activity yet/i)).toHaveCount(0);
    await expect(page.getByText(/lead created/i).first()).toBeVisible();
  });

  test("status change surfaces as a status_changed event (US1 acceptance scenarios 1–2)", async ({
    page,
  }) => {
    const api = await apiLogin();
    const suffix = `${Date.now()}-status`;
    const { contactId } = await seedContact(api, suffix);

    const patchResp = await api.patch(`/api/v1/contacts/${contactId}`, {
      data: { status: "not_interested" },
    });
    expect(patchResp.ok(), await patchResp.text()).toBeTruthy();

    await uiLogin(page);
    await page.goto(`/auth/leads/${contactId}`);
    await page.getByRole("button", { name: /^activity$/i }).click();

    // Newest-first default — status_changed should appear at or near the top.
    await expect(page.getByText(/status changed/i).first()).toBeVisible();
    await expect(page.getByText(/lead created/i)).toBeVisible();

    // Order toggle re-orders the list.
    await page.getByRole("button", { name: /oldest first/i }).click();
    const firstLabel = page.locator("li").first();
    await expect(firstLabel).toContainText(/lead created/i);
  });
});

// -----------------------------------------------------------------------------
// US2 — Global cross-contact activity timeline.
// -----------------------------------------------------------------------------

test.describe("us2 global activity timeline", () => {
  test("interleaves events across contacts and event-type filter narrows them", async ({
    page,
  }) => {
    const api = await apiLogin();
    const suffix = `${Date.now()}`;

    // Seed two contacts under separate orgs so the timeline mixes them.
    const a = await seedContact(api, `${suffix}-A`);
    const b = await seedContact(api, `${suffix}-B`);

    await uiLogin(page);
    await page.goto("/auth/activity");

    await expect(page.getByRole("heading", { name: /^activity$/i })).toBeVisible();

    // Both freshly-created contacts have a lead_created event; both should be visible
    // on the unfiltered timeline.
    await expect(page.getByText(new RegExp(`Max Activity-${suffix}-A`))).toBeVisible();
    await expect(page.getByText(new RegExp(`Max Activity-${suffix}-B`))).toBeVisible();

    // Apply event_type filter — pick email_sent (no seed data has it) → the list empties.
    await page.getByRole("button", { name: "email_sent", exact: true }).click();
    await expect(page.getByText(/no activity matches/i)).toBeVisible();

    // Toggle it off → both are back.
    await page.getByRole("button", { name: "email_sent", exact: true }).click();
    await expect(page.getByText(new RegExp(`Max Activity-${suffix}-A`))).toBeVisible();

    // Clicking a contact row on the global timeline navigates to the contact detail
    // with the Activity tab focused (US2 acceptance scenario 3).
    await page.getByText(new RegExp(`Max Activity-${suffix}-A`)).first().click();
    await expect(page).toHaveURL(new RegExp(`/auth/leads/${a.contactId}\\?tab=activity`));
    await expect(page.getByRole("button", { name: /^activity$/i })).toBeVisible();

    // Reference both ids to prevent unused-variable warnings.
    expect(b.contactId).toBeGreaterThan(0);
  });
});

// -----------------------------------------------------------------------------
// US3 — Save draft to mailbox (quickstart § 5).
// This suite requires IMAP to be configured against a test mailbox. Skipped
// unless the operator sets PLAYWRIGHT_IMAP_CONFIGURED=1 in the environment
// (Constitution V — no live-integration when creds absent).
// -----------------------------------------------------------------------------

const runUs3 = process.env.PLAYWRIGHT_IMAP_CONFIGURED === "1";

test.describe("us3 save-to-mailbox", () => {
  test.skip(!runUs3, "PLAYWRIGHT_IMAP_CONFIGURED not set — no IMAP fixture in this env");

  test("send-now, save-to-mailbox, and discard render with equal prominence", async ({ page }) => {
    // Preflight: verify Settings has IMAP configured — otherwise the button is hidden.
    const api = await apiLogin();
    const view = await api.get("/api/v1/settings").then((r) => r.json());
    expect(view.imap?.host, "IMAP host must be configured before running this test").not.toBeNull();

    await uiLogin(page);
    await page.goto("/auth/todos");
    // Click the first send-todo in the list; if none exists the test is
    // inconclusive — the operator seeds the fixture.
    const firstSend = page.getByRole("row").filter({ hasText: /send/i }).first();
    await expect(firstSend).toBeVisible();
    await firstSend.click();

    await expect(page.getByRole("button", { name: /send now/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /save to mailbox/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /discard/i })).toBeVisible();

    await page.getByRole("button", { name: /save to mailbox/i }).click();

    // A success toast naming the destination folder should appear (SC-013 / SC-014).
    await expect(page.getByText(/saved to .*drafts/i)).toBeVisible({ timeout: 15_000 });
    // Todo state renders as completed (via mailbox).
    await expect(page.getByText(/completed \(saved to mailbox\)/i)).toBeVisible();
  });
});
