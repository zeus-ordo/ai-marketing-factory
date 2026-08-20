import { fetchWithTimeout, getCampaignApiBase, getInternalApiKeyOrThrow, resolveTraceActorFromRequest } from "@/app/api/campaign-trace/_shared";

type Params = { params: Promise<{ workOrderId: string }> };

export async function GET(request: Request, { params }: Params) {
  const actor =
    resolveTraceActorFromRequest(request) ??
    ({ actorId: process.env.WORK_ORDER_DEFAULT_ACTOR_ID ?? "ui_operator", actorRole: "operator" as const });

  let internalApiKey = "";
  try {
    internalApiKey = getInternalApiKeyOrThrow();
  } catch {
    return Response.json({ detail: "CHATBOT_INTERNAL_API_KEY is not configured" }, { status: 503 });
  }

  const { workOrderId } = await params;
  const response = await fetchWithTimeout(`${getCampaignApiBase()}/api/v1/work-orders/${workOrderId}`, {
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

export async function PATCH(request: Request, { params }: Params) {
  const actor =
    resolveTraceActorFromRequest(request) ??
    ({ actorId: process.env.WORK_ORDER_DEFAULT_ACTOR_ID ?? "ui_operator", actorRole: "operator" as const });

  let internalApiKey = "";
  try {
    internalApiKey = getInternalApiKeyOrThrow();
  } catch {
    return Response.json({ detail: "CHATBOT_INTERNAL_API_KEY is not configured" }, { status: 503 });
  }

  const { workOrderId } = await params;
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return Response.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const response = await fetchWithTimeout(`${getCampaignApiBase()}/api/v1/work-orders/${workOrderId}`, {
    method: "PATCH",
    headers: {
      "x-internal-api-key": internalApiKey,
      "x-actor-id": actor.actorId,
      "x-actor-role": actor.actorRole,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
