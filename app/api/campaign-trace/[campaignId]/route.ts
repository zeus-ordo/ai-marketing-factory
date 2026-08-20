import { fetchWithTimeout, getCampaignApiBase, getInternalApiKeyOrThrow, resolveTraceActorFromRequest } from "../_shared";

export async function GET(
  request: Request,
  context: { params: Promise<{ campaignId: string }> },
) {
  const { campaignId } = await context.params;
  const actor =
    resolveTraceActorFromRequest(request) ??
    ({ actorId: process.env.WORK_ORDER_DEFAULT_ACTOR_ID ?? "ui_operator", actorRole: "operator" as const });

  let internalApiKey = "";
  try {
    internalApiKey = getInternalApiKeyOrThrow();
  } catch {
    return Response.json({ detail: "CHATBOT_INTERNAL_API_KEY is not configured" }, { status: 503 });
  }

  const response = await fetchWithTimeout(`${getCampaignApiBase()}/api/v1/campaigns/${campaignId}/trace`, {
    method: "GET",
    headers: {
      "x-internal-api-key": internalApiKey,
      "x-actor-id": actor.actorId,
      "x-actor-role": actor.actorRole,
    },
    cache: "no-store",
  });

  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
