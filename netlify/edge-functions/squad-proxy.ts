/**
 * Netlify Edge Function — EA squad proxy
 *
 * Fetches the latest PS4 squad .bin file from EA's CDN and streams it back
 * to the browser. This proxy is necessary because EA's CDN does not serve
 * CORS headers, so a direct browser fetch would be blocked.
 *
 * Runtime: Netlify Edge (Deno / Cloudflare Workers compatible).
 * No external dependencies — only the native fetch API is used.
 */

const CONTENT_URL =
  "https://eafc26.content.easports.com/fc/fltOnlineAssets/26E4D4D6-8DBB-4A9A-BD99-9C47D3AA341D/2026/";

const ROSTER_URL = `${CONTENT_URL}fc/fclive/genxtitle/rosterupdate.xml`;

/** Extract the PS4 dbMajorLoc value from the roster XML using a simple regex. */
function extractPs4BinLoc(xml: string): string | null {
  // Find the <SquadInfo platform="ps4"> block (case-insensitive, attribute order may vary)
  const blockMatch = xml.match(
    /<SquadInfo\s[^>]*platform="ps4"[^>]*>([\s\S]*?)<\/SquadInfo>/i
  );
  if (!blockMatch) return null;

  const locMatch = blockMatch[1].match(/<dbMajorLoc>\s*(.*?)\s*<\/dbMajorLoc>/);
  return locMatch ? locMatch[1] : null;
}

/** Extract all platform values found in the XML (for debug logging). */
function extractAllPlatforms(xml: string): string[] {
  const platforms: string[] = [];
  const re = /<SquadInfo\s[^>]*platform="([^"]+)"/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(xml)) !== null) {
    platforms.push(m[1]);
  }
  return platforms;
}

export default async function handler(request: Request): Promise<Response> {
  // Only allow GET
  if (request.method !== "GET") {
    return new Response("Method not allowed", { status: 405 });
  }

  try {
    // 1. Fetch the roster manifest
    console.log(`[squad-proxy] Fetching roster: ${ROSTER_URL}`);
    const rosterRes = await fetch(ROSTER_URL);
    if (!rosterRes.ok) {
      console.error(`[squad-proxy] Roster fetch failed: ${rosterRes.status}`);
      return new Response(
        JSON.stringify({ error: `Roster fetch failed: ${rosterRes.status}` }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
    const rosterXml = await rosterRes.text();
    console.log(`[squad-proxy] Roster XML length: ${rosterXml.length} bytes`);

    // 2. Parse to find the PS4 compressed squad file path
    const loc = extractPs4BinLoc(rosterXml);
    if (!loc) {
      const platforms = extractAllPlatforms(rosterXml);
      console.error(
        `[squad-proxy] PS4 not found in roster. Platforms found: [${platforms.join(", ")}]`
      );
      // Log first 2000 chars of XML to help diagnose
      console.error(`[squad-proxy] XML snippet:\n${rosterXml.slice(0, 2000)}`);
      return new Response(
        JSON.stringify({
          error: `PS4 platform not found in roster XML. Platforms available: [${platforms.join(", ")}]`,
        }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
    console.log(`[squad-proxy] PS4 bin loc: ${loc}`);

    // 3. Stream the .bin file back to the browser
    const binUrl = `${CONTENT_URL}${loc}`;
    console.log(`[squad-proxy] Fetching bin: ${binUrl}`);
    const binRes = await fetch(binUrl);
    if (!binRes.ok) {
      console.error(`[squad-proxy] Bin fetch failed: ${binRes.status}`);
      return new Response(
        JSON.stringify({ error: `Squad bin fetch failed: ${binRes.status}` }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
    console.log(`[squad-proxy] Streaming bin (Content-Length: ${binRes.headers.get("Content-Length") ?? "unknown"})`);

    return new Response(binRes.body, {
      status: 200,
      headers: {
        "Content-Type": "application/octet-stream",
        // Allow the browser (same Netlify origin) to read this response
        "Access-Control-Allow-Origin": "*",
        // Let the browser know how big the download is (if EA provides it)
        ...(binRes.headers.get("Content-Length")
          ? { "Content-Length": binRes.headers.get("Content-Length")! }
          : {}),
      },
    });
  } catch (err) {
    console.error(`[squad-proxy] Unexpected error:`, err);
    return new Response(
      JSON.stringify({ error: `Unexpected error: ${String(err)}` }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
