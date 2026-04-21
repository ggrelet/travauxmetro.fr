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
  [/Google-Calendar|GoogleOther|Feedfetcher-Google/i, "gcal"],
  [/Outlook|Microsoft|MSOffice/i, "outlook"],
  [/CalendarAgent|CalendarStore|iCal\/|dataaccessd|Mac OS X|iPhone|iPad|Darwin/i, "apple"],
  [/Thunderbird|Lightning/i, "thunderbird"],
  [/Fastmail/i, "fastmail"],
  [/Proton/i, "proton"],
  [/Nextcloud|DAViCal|SOGo|CalDAV/i, "caldav"],
  [/Evolution/i, "evolution"],
  [/curl|wget|python|Go-http|okhttp|libwww/i, "bot"],
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

        // Temporary: log raw UA for unmatched clients so we can identify
        // them in Umami and add proper patterns above.
        const data = client === "other" ? { client, line, ua: ua.slice(0, 200) } : { client, line };

        fetch(UMAMI_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type: "event",
            payload: {
              website: WEBSITE_ID,
              url: url.pathname,
              name: "ics-refresh",
              data,
            },
          }),
        }).catch(() => {});
      }
    }

    return fetch(req);
  },
};
