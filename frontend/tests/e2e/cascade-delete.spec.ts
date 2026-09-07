import { test, expect } from "@playwright/test";

// FR-001 + FR-027a + FR-027b: end-to-end sanity check of the cascade-delete flow.
// Seeds an organisation with a contact directly against the backend API, then drives
// the UI to open the Organisations list, trigger the row-level Delete action, and
// verify the confirmation dialog shows the correct impact counts before completing
// the cascade.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MASTER_PASSWORD = process.env.PLAYWRIGHT_MASTER_PASSWORD ?? "12345678";

test.describe("cascade delete", () => {
  test("deleting an organisation cascades contacts + shows impact counts", async ({
    page,
    request,
  }) => {
    // 1. Log in against the backend so we can seed via API with a valid session cookie.
    const loginResponse = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { password: MASTER_PASSWORD },
    });
    expect(loginResponse.ok(), await loginResponse.text()).toBeTruthy();

    // 2. Seed an organisation + one contact so the delete-impact dialog has counts to show.
    const orgName = `CascadeCo-${Date.now()}`;
    const orgResp = await request.post(`${API_URL}/api/v1/organisations`, {
      data: { name: orgName },
    });
    expect(orgResp.ok(), await orgResp.text()).toBeTruthy();
    const org = await orgResp.json();

    const contactResp = await request.post(`${API_URL}/api/v1/contacts`, {
      data: {
        organisation_id: org.id,
        first_name: "Cas",
        last_name: "Deletee",
        email: "cas@cascadeco.example",
      },
    });
    expect(contactResp.ok(), await contactResp.text()).toBeTruthy();

    // 3. Drive the UI to log in (the browser context does not share cookies with the
    //    APIRequestContext above).
    await page.goto("/login");
    await page.getByLabel(/password/i).fill(MASTER_PASSWORD);
    await page.getByRole("button", { name: /log in|sign in|submit/i }).click();

    // 4. Open the Organisations list and locate our seeded row.
    await page.goto("/auth/organisations");
    const row = page.getByRole("row", { name: new RegExp(orgName) });
    await expect(row).toBeVisible();

    // 5. Trigger the row-level delete affordance.
    await row.getByRole("button", { name: new RegExp(`Delete ${orgName}`) }).click();

    // 6. The confirmation dialog must be shown with the impact counts fetched from
    //    /organisations/{id}/delete-impact — assert the "1 contact" line renders
    //    before the delete is executed (FR-027a).
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(orgName);
    await expect(dialog).toContainText(/1 contact/i);

    // 7. Confirm the cascade.
    await dialog.getByRole("button", { name: /^delete$/i }).click();

    // 8. The org must be gone from the Organisations list — and the seeded contact
    //    must be gone from the Contacts list (cascade).
    await expect(page.getByRole("row", { name: new RegExp(orgName) })).toHaveCount(0);

    await page.goto("/auth/contacts");
    await expect(page.getByRole("row", { name: /Cas Deletee/ })).toHaveCount(0);
  });
});
