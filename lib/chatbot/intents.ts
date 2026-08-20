import type { ChatContext, IntentDetectionResult } from "@/lib/types/chatbot";

const CAMPAIGN_ID_PATTERN = /(cmp_[a-zA-Z0-9]+)/;
const REFERENCE_ID_PATTERN = /(ref_[a-zA-Z0-9]+)/;
const REVIEW_ID_PATTERN = /(review[-_][a-zA-Z0-9_-]+|rvw[-_][a-zA-Z0-9_-]+|rev[-_][a-zA-Z0-9_-]+)/;
const ASSET_ID_PATTERN = /(ast_[a-zA-Z0-9_-]+)/i;
const BUDGET_PATTERN = /(?:預算|budget|予算)\s*[:：]?\s*([0-9][0-9,]*)/i;

// ─── Public API (sync, rule-based — kept for backwards compatibility) ──────────

export function detectIntent(message: string): IntentDetectionResult {
  return ruleBasedDetect(message);
}

// ─── LLM-based detection (async) ─────────────────────────────────────────────

const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY ?? "";
const DEEPSEEK_BASE_URL = (process.env.DEEPSEEK_BASE_URL ?? "https://api.deepseek.com/v1").replace(/\/$/, "");
const DEEPSEEK_MODEL = process.env.DEEPSEEK_MODEL ?? "deepseek-v4-flash";

const INTENT_DESCRIPTIONS: Array<{ intent: string; description: string; examples: string[] }> = [
  {
    intent: "create_campaign",
    description: "User wants to create a new marketing campaign.",
    examples: ["建立活動", "新建活動", "2026年可爾必思行銷圖", "可爾必思行銷 預算50000 平台IG", "create a campaign named Q2 launch"],
  },
  {
    intent: "run_campaign",
    description: "User wants to launch or execute a campaign.",
    examples: ["啟動活動", "執行這個活動", "run campaign cmp_abc123", "launch it"],
  },
  {
    intent: "list_campaigns",
    description: "User wants to see their campaign list.",
    examples: ["列出活動", "活動列表", "show my campaigns", "有哪些活動"],
  },
  {
    intent: "list_tasks",
    description: "User wants to check workflow tasks or progress.",
    examples: ["任務進度", "tasks", "工單狀態", "what tasks are pending"],
  },
  {
    intent: "list_references",
    description: "User wants to list reference materials or files.",
    examples: ["列出參考資料", "list references", "有哪些參照文件"],
  },
  {
    intent: "list_review_queue",
    description: "User wants to see items awaiting review/approval.",
    examples: ["審核待辦", "review queue", "待審核的項目", "レビュー待ち"],
  },
  {
    intent: "list_validation_results",
    description: "User wants to see validation or QA results.",
    examples: ["驗證結果", "validation results", "検証結果"],
  },
  {
    intent: "delete_reference",
    description: "User wants to delete a reference file or document.",
    examples: ["刪除參考資料", "刪掉這個文件", "delete reference ref_xyz"],
  },
  {
    intent: "approve_review",
    description: "User wants to approve or pass a review item.",
    examples: ["核准審核", "approve review", "通過這個審核", "承認"],
  },
  {
    intent: "confirm_pending_action",
    description: "User is confirming a pending action that requires explicit yes/code confirmation.",
    examples: ["confirm", "確認", "yes", "実行", "確認する"],
  },
  {
    intent: "cancel_pending_action",
    description: "User is cancelling or rejecting a pending action.",
    examples: ["cancel", "取消", "no", "やめる", "不要"],
  },
  {
    intent: "modify_work_order",
    description: "User wants to modify a campaign, work order, brief, budget, deadline, or platform settings.",
    examples: ["修改預算", "change deadline", "更新brief", "改一下活動名稱", "修改平台", "set budget to 50000"],
  },
  {
    intent: "regenerate_asset",
    description: "User wants to regenerate or re-generate an existing asset (image, video, copy, or ad) to produce a new version.",
    examples: ["重新生成這個素材", "regenerate asset ast_abc123", "再生成一張圖", "再產生一次這個影片", "重新產生這段文案", "再生成一張圖", "やり直して"],
  },
  {
    intent: "unknown",
    description: "The message does not match any known intent.",
    examples: ["hello", "thank you", "how are you"],
  },
];

/**
 * LLM-based intent detection using DeepSeek.
 * Falls back to rule-based detection on error.
 */
export async function detectIntentLLM(
  message: string,
  context?: ChatContext,
): Promise<IntentDetectionResult> {
  if (!DEEPSEEK_API_KEY) {
    return ruleBasedDetect(message);
  }

  const pendingType = context?.pendingAction?.type;
  const pendingContext = pendingType
    ? `\nCurrently there is a PENDING ACTION of type "${pendingType}" awaiting confirmation.`
    : "";

  const systemPrompt = `You are a marketing campaign assistant intent classifier.
Classify the user's message into ONE of the supported intents based on natural language understanding.

Supported intents:
${INTENT_DESCRIPTIONS.map((i) => `  - ${i.intent}: ${i.description}`).join("\n")}

${pendingContext}

Return a JSON object with the following shape (no markdown, no explanation):
{
  "intent": "<the classified intent>",
  "campaignId": "<cmp_xxx if found in message, else null>",
  "referenceId": "<ref_xxx if found in message, else null>",
  "reviewId": "<review_xxx/rvw_xxx/rev_xxx if found in message, else null>",
  "confirmationCode": "<any confirmation code like confirm ABC123, else null>",
  "campaignName": "<any campaign name found, else null>",
  "budget": <numeric budget if mentioned, else null>,
  "modificationInstruction": "<the full user message if intent is modify_work_order, else null>"
}`;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);

    const response = await fetch(`${DEEPSEEK_BASE_URL}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${DEEPSEEK_API_KEY}`,
      },
      signal: controller.signal,
      body: JSON.stringify({
        model: DEEPSEEK_MODEL,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: message },
        ],
        temperature: 0.1,
        max_tokens: 400,
      }),
    });

    clearTimeout(timeout);

    if (!response.ok) {
      throw new Error(`DeepSeek API error: ${response.status}`);
    }

    const data = (await response.json()) as {
      choices: Array<{ message: { content: string } }>;
    };
    const raw = data.choices?.[0]?.message?.content ?? "";

    const jsonStr = raw.replace(/^```(?:json)?\n?/i, "").replace(/\n?```$/i, "").trim();
    const parsed = JSON.parse(jsonStr) as {
      intent?: string;
      campaignId?: string | null;
      referenceId?: string | null;
      reviewId?: string | null;
      assetId?: string | null;
      confirmationCode?: string | null;
      campaignName?: string | null;
      budget?: number | null;
      modificationInstruction?: string | null;
    };

    // Validate intent
    const validIntents = INTENT_DESCRIPTIONS.map((i) => i.intent);
    const intent = parsed.intent && validIntents.includes(parsed.intent) ? parsed.intent : "unknown";
    const fallbackDetection = intent === "unknown" ? ruleBasedDetect(message) : null;

    if (fallbackDetection && fallbackDetection.intent !== "unknown") {
      return fallbackDetection;
    }

    return {
      intent: intent as IntentDetectionResult["intent"],
      slots: {
        campaignId: parsed.campaignId ?? extractCampaignId(message),
        referenceId: parsed.referenceId ?? extractReferenceId(message),
        reviewId: parsed.reviewId ?? extractReviewId(message),
        assetId: parsed.assetId ?? extractAssetId(message),
        confirmationCode: parsed.confirmationCode ?? extractConfirmationCode(message),
        campaignName: parsed.campaignName ?? undefined,
        budget: parsed.budget ?? extractBudget(message),
        modificationInstruction: intent === "modify_work_order" ? (parsed.modificationInstruction ?? message) : undefined,
      },
    };
  } catch (err) {
    console.error("[intents] LLM detection failed, falling back to rule-based:", err instanceof Error ? err.message : "Unknown error");
    return ruleBasedDetect(message);
  }
}

// ─── Rule-based detection (original logic, exported for reuse/fallback) ────────

export function ruleBasedDetect(message: string): IntentDetectionResult {
  const text = message.trim();
  const lower = text.toLowerCase();
  const campaignId = extractCampaignId(text);
  const referenceId = extractReferenceId(text);
  const reviewId = extractReviewId(text);
  const confirmationCode = extractConfirmationCode(text);

  if (isConfirmAck(text)) {
    return { intent: "confirm_pending_action", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (isCancelAck(text)) {
    return { intent: "cancel_pending_action", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (
    (containsAny(lower, ["delete", "remove", "刪除", "移除", "削除"]) &&
      containsAny(lower, ["reference", "references", "參考資料", "参照資料"])) ||
    (containsAny(lower, ["delete", "remove", "刪除", "移除", "削除"]) && !!referenceId)
  ) {
    return { intent: "delete_reference", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (
    (containsAny(lower, ["approve", "核准", "通過", "承認"]) &&
      containsAny(lower, ["review", "審核", "レビュー"])) ||
    (containsAny(lower, ["approve", "核准", "承認"]) && !!reviewId)
  ) {
    return { intent: "approve_review", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (
    containsAny(lower, ["任務", "tasks", "進度", "workflow status", "タスク"]) ||
    (containsAny(lower, ["show", "list", "表示"]) && containsAny(lower, ["task", "tasks", "タスク"]))
  ) {
    return { intent: "list_tasks", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (
    containsAny(lower, ["reference", "references", "參考資料", "参照資料"]) ||
    (containsAny(lower, ["list", "show", "列出", "顯示", "表示"]) &&
      containsAny(lower, ["reference", "references", "參考資料", "参照資料"]))
  ) {
    return { intent: "list_references", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (
    containsAny(lower, ["review queue", "待審核", "審核待辦", "レビュー待ち", "review items"]) ||
    (containsAny(lower, ["review", "審核", "レビュー"]) && containsAny(lower, ["list", "show", "列出", "表示"]))
  ) {
    return { intent: "list_review_queue", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (
    containsAny(lower, ["validation", "驗證結果", "検証結果", "validation results"]) ||
    (containsAny(lower, ["list", "show", "查", "列出", "表示"]) &&
      containsAny(lower, ["validation", "驗證結果", "検証結果"]))
  ) {
    return { intent: "list_validation_results", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (isLikelyCreateCampaignRequest(lower)) {
    return {
      intent: "create_campaign",
      slots: {
        campaignName: extractCampaignName(text),
        budget: extractBudget(text),
        campaignId,
        referenceId,
        reviewId,
        confirmationCode,
      },
    };
  }

  if (
    containsAny(lower, ["啟動", "執行", "run", "start", "起動"]) &&
    containsAny(lower, ["活動", "campaign", "キャンペーン"])
  ) {
    return { intent: "run_campaign", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (
    containsAny(lower, ["列出活動", "活動列表", "campaign list", "list campaigns", "活動有哪些", "キャンペーン一覧"]) ||
    (containsAny(lower, ["list", "show", "表示"]) && containsAny(lower, ["campaign", "活動", "キャンペーン"]))
  ) {
    return { intent: "list_campaigns", slots: { campaignId, referenceId, reviewId, confirmationCode } };
  }

  if (
    (containsAny(lower, ["修改", "改", "change", "update"]) &&
      containsAny(lower, ["工單", "brief", "campaign", "活動", "預算", "deadline", "期限", "名稱", "name", "平台", "platform"])) ||
    /預算.*?(改|設|為)/i.test(text) ||
    /deadline.*?(改|設|為)/i.test(text) ||
    /budget.*?(change|update|set)/i.test(text)
  ) {
    return {
      intent: "modify_work_order",
      slots: {
        campaignId,
        referenceId,
        reviewId,
        confirmationCode,
        modificationInstruction: text,
      },
    };
  }

  if (
    (containsAny(lower, ["重新生成", "regenerate", "再生成", "再產生", "再生成", "やり直す", " regenerate"]) &&
      containsAny(lower, ["素材", "asset", "アセット", "圖", "動画", "影片", "文案", "コピー", "画像", "image", "video", "copy", "ad", "廣告"])) ||
    (containsAny(lower, ["regenerate", "re-generate", "regenerate asset", " regenerate"]) && !!extractAssetId(text))
  ) {
    return {
      intent: "regenerate_asset",
      slots: {
        campaignId,
        referenceId,
        reviewId,
        assetId: extractAssetId(text),
        confirmationCode,
      },
    };
  }

  return { intent: "unknown", slots: { campaignId, referenceId, reviewId, assetId: extractAssetId(text), confirmationCode } };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function containsAny(text: string, tokens: string[]): boolean {
  return tokens.some((token) => text.includes(token));
}

function isLikelyCreateCampaignRequest(lower: string): boolean {
  const explicitCreate =
    containsAny(lower, ["建立", "新建", "新增", "創建", "開新", "create", "幫我建立", "幫我做"]) &&
    containsAny(lower, ["活動", "campaign", "キャンペーン", "行銷", "营销", "廣告", "広告", "圖", "圖片", "image", "visual", "作成"]);

  const marketingBrief =
    containsAny(lower, ["行銷", "营销", "campaign", "廣告", "広告", "宣傳", "推廣", "圖", "圖片", "image", "visual", "海報", "素材"]) &&
    containsAny(lower, ["預算", "budget", "受眾", "audience", "平台", "platform", "ig", "instagram", "linkedin", "facebook", "tiktok"]);

  const visualMarketingRequest =
    containsAny(lower, ["行銷圖", "行銷圖片", "廣告圖", "宣傳圖", "marketing image", "marketing visual", "海報"]) &&
    !containsAny(lower, ["查", "列出", "list", "show", "刪除", "delete", "核准", "approve"]);

  return explicitCreate || marketingBrief || visualMarketingRequest;
}

function isConfirmAck(text: string): boolean {
  return /^(confirm|yes|ok|確認|確定|はい|実行)(\s+[a-zA-Z0-9]{4,12})?$/i.test(normalizeAckText(text));
}

function isCancelAck(text: string): boolean {
  return /^(cancel|no|取消|不用|やめる|キャンセル)$/i.test(normalizeAckText(text));
}

function normalizeAckText(text: string): string {
  return text.replace(/[.!?。！？]/g, "").trim();
}

function extractConfirmationCode(text: string): string | undefined {
  const normalized = normalizeAckText(text);
  const match = normalized.match(/^(?:confirm|yes|ok|確認|確定|はい|実行)\s+([a-zA-Z0-9]{4,12})$/i);
  return match?.[1];
}

function extractCampaignId(text: string): string | undefined {
  const match = text.match(CAMPAIGN_ID_PATTERN);
  return match?.[1];
}

function extractReferenceId(text: string): string | undefined {
  const match = text.match(REFERENCE_ID_PATTERN);
  return match?.[1];
}

function extractReviewId(text: string): string | undefined {
  const match = text.match(REVIEW_ID_PATTERN);
  return match?.[1];
}

function extractAssetId(text: string): string | undefined {
  const match = text.match(ASSET_ID_PATTERN);
  return match?.[1];
}

function extractBudget(text: string): number | undefined {
  const match = text.match(BUDGET_PATTERN);
  if (!match) return undefined;
  const numeric = Number(match[1].replaceAll(",", ""));
  if (!Number.isFinite(numeric) || numeric <= 0) return undefined;
  return numeric;
}

function extractCampaignName(text: string): string | undefined {
  const quoted = text.match(/["「『](.+?)["」』]/);
  if (quoted?.[1]) return quoted[1].trim();

  const named = text.match(/(?:named|called|名為|名稱|名前)\s*[:：]?\s*(.+)$/i);
  if (named?.[1]) {
    const candidate = named[1].trim();
    return candidate ? candidate.slice(0, 40) : undefined;
  }

  return undefined;
}
