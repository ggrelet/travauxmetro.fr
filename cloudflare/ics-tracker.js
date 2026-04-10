/**
 * Cloudflare Worker — ICS refresh tracker
 *
 * Intercepts *.ics requests, classifies the calendar client from User-Agent,
 * sends a fire-and-forget event to Umami, then proxies to origin.
 *
 * Route: travauxmetro.fr/*.ics
 */

const UMAMI_URL = "https://cloud.umami.is/api/send";
const WEBSITE_ID = "ef00b128-53c5-49eb-a0e9-e4da83748a67"; // Public Umami site ID — also embedded in the page's data-website-id

const UA_CLIENTS = [
  [/Google-Calendar|CalDAV|GoogleOther/i, "gcal"],
  [/Outlook|Microsoft/i, "outlook"],
  [/Apple|Darwin|iPhone|iPad/i, "apple"],
  [/Thunderbird/i, "thunderbird"],
  [/curl|python|wget/i, "bot"],
];

export default {
  async fetch(req) {
    const url = new URL(req.url);

    if (url.pathname.endsWith(".ics")) {
      const ua = req.headers.get("User-Agent");

      // Skip Umami for raw scanners with no User-Agent
      if (ua) {
        const client = UA_CLIENTS.find(([re]) => re.test(ua))?.[1] ?? "other";
        const line = url.pathname.match(/ligne-(.+)\.ics$/)?.[1] ?? "all";

        fetch(UMAMI_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type: "event",
            payload: {
              website: WEBSITE_ID,
              url: url.pathname,
              name: "ics-refresh",
              data: { client, line },
            },
          }),
        }).catch(() => {});
      }
    }

    return fetch(req);
  },
};
