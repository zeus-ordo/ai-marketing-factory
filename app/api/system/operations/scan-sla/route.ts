import {
  fetchWithTimeout,
  getCampaignApiBase,
  getInternalApiKeyOrThrow,
  resolveTraceActorFromRequest,
} from "@/app/api/campaign-trace/_shared";

export async function POST(request: Request) {
  const actor = resolveTraceActorFromRequest(request);
  if (!actor || actor.actorRole !== "admin") {
    return Response.json({ detail: "Unauthorized" }, { status: 401 });
  }

  let internalApiKey = "";
  try {
    internalApiKey = getInternalApiKeyOrThrow();
  } catch {
    return Response.json({ detail: "CHATBOT_INTERNAL_API_KEY is not configured" }, { status: 503 });
  }

  const payload = { operator: actor.actorId, limit: 500 };
  const response = await fetchWithTimeout(`${getCampaignApiBase()}/api/v1/system/operations/scan-sla`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-internal-api-key": internalApiKey,
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
