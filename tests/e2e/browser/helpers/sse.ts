import { Page } from "@playwright/test";
import { API_BASE } from "../fixtures/constants";

export async function waitForSseEvent(
  page: Page,
  endpoint: string,
  eventType: string,
  timeoutMs: number = 300_000
): Promise<Record<string, unknown>> {
  return page.evaluate(
    ({ url, targetEvent, timeout }) => {
      return new Promise<Record<string, unknown>>((resolve, reject) => {
        const es = new EventSource(url, { withCredentials: true });
        const timer = setTimeout(() => {
          es.close();
          reject(new Error(`Timeout waiting for SSE event: ${targetEvent}`));
        }, timeout);

        es.onmessage = (msg) => {
          try {
            const event = JSON.parse(msg.data);
            if (event.event_type === targetEvent) {
              clearTimeout(timer);
              es.close();
              resolve(event);
            }
          } catch {
            // skip non-JSON messages (heartbeats)
          }
        };

        es.onerror = () => {
          clearTimeout(timer);
          es.close();
          reject(new Error("SSE connection error"));
        };
      });
    },
    { url: `${API_BASE}${endpoint}`, targetEvent: eventType, timeout: timeoutMs }
  );
}
