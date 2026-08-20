import {
  fetchWithTimeout,
  getCampaignApiBase,
  getInternalApiKeyOrThrow,
  resolveTraceActorFromRequest,
} from "@/app/api/campaign-trace/_shared";

export async function GET(request: Request) {
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

  const response = await fetchWithTimeout(`${getCampaignApiBase()}/api/v1/system/trace/health`, {
    method: "GET",
    headers: {
      "x-internal-api-key": internalApiKey,
    },
    cache: "no-store",
  });

  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
