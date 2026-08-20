/**
 * DeepSeek LLM-based campaign brief extraction.
 * Parses natural language into a structured CampaignBriefDraft,
 * identifies missing required fields, and supports in-place modifications.
 */

import type { CampaignBriefDraft } from "@/lib/types/chatbot";

const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY ?? "";
const DEEPSEEK_BASE_URL = (process.env.DEEPSEEK_BASE_URL ?? "https://api.deepseek.com/v1").replace(/\/$/, "");
const DEEPSEEK_MODEL = process.env.DEEPSEEK_MODEL ?? "deepseek-v4-flash";

export interface ExtractionResult {
  brief: Partial<CampaignBriefDraft>;
  missing_fields: string[];
  raw: string;
  confidence: number; // 0-1
}

export interface ModificationResult {
  brief: Partial<CampaignBriefDraft>;
  modified_fields: string[];
  error?: string;
}

const REQUIRED_FIELDS: (keyof CampaignBriefDraft)[] = [
  "campaign_name",
  "product_name",
  "objective",
  "target_audience",
  "platforms",
  "budget",
  "brand_tone",
  "deliverables",
  "deadline",
];

const BRIEF_SCHEMA = {
  type: "object",
  properties: {
    campaign_name: { type: "string", description: "Campaign name, max 80 chars" },
    product_name: { type: "string", description: "Product or subject name, max 80 chars" },
    description: { type: "string", description: "Optional campaign description" },
    objective: { type: "string", description: "Campaign objective, e.g. 'Increase brand awareness'" },
    target_audience: {
      type: "object",
      properties: {
        age_range: { type: "string", description: "e.g. '25-44'" },
        gender: { type: "string", description: "e.g. 'all', 'male', 'female'" },
        persona: { type: "string", description: "Brief persona description, max 60 chars" },
      },
      required: ["age_range", "gender", "persona"],
    },
    platforms: {
      type: "array",
      items: { type: "string" },
      description: "List of platforms: LinkedIn, Instagram, Facebook, TikTok, Google Ads, etc.",
    },
    budget: { type: "number", description: "Budget in TWD, minimum 1000" },
    brand_tone: {
      type: "array",
      items: { type: "string" },
      description: "Brand tone keywords: Professional, Friendly, Casual, Luxury, etc.",
    },
    deliverables: {
      type: "object",
      properties: {
        copy_variants: { type: "integer", minimum: 0, description: "Number of copy variants" },
        image_assets: { type: "integer", minimum: 0, description: "Number of image assets" },
        short_video_assets: { type: "integer", minimum: 0, description: "Number of short video assets" },
        ads_strategy: { type: "integer", minimum: 0, description: "0 = no ads strategy, 1 = include ads strategy" },
      },
    },
    mandatory_elements: {
      type: "array",
      items: { type: "string" },
      description: "Must-have elements in all assets",
    },
    forbidden_elements: {
      type: "array",
      items: { type: "string" },
      description: "Elements to avoid",
    },
    deadline: {
      type: "string",
      description: "ISO 8601 deadline date (YYYY-MM-DD), must be at least 3 days from now",
    },
  },
  required: ["campaign_name", "product_name", "objective", "target_audience", "platforms", "budget", "brand_tone", "deliverables", "deadline"],
};

const SYSTEM_PROMPT = `You are an expert marketing campaign brief extractor. Given a user's natural language description of a campaign, extract a structured campaign brief.

Extract the most detailed brief possible from the user's message. If a required field is not mentioned, leave it null but mark it as missing.

Output ONLY valid JSON matching this schema:
${JSON.stringify(BRIEF_SCHEMA, null, 2)}

Rules:
- campaign_name: extract or infer from context, max 80 chars
- product_name: extract or infer, max 80 chars
- objective: infer from context if not stated, e.g. "Increase brand awareness"
- target_audience: infer reasonable defaults if not stated
- platforms: infer from context or use common defaults (LinkedIn, Instagram)
- budget: extract number or infer reasonable default (50000 TWD if unclear)
- brand_tone: infer from message tone and keywords
- deliverables: infer from message (comparison/infographic → image_assets=1, copy_variants=0; else defaults copy=3, images=2, video=1, ads=0)
- deadline: must be at least 3 days from today; if not stated, set to 14 days from now
- If the user mentions "comparison", "vs", "對比", "比較", "infographic" → set copy_variants=0, image_assets=1, short_video_assets=0, ads_strategy=0

Return null for any field that cannot be reasonably inferred.`;

function buildUserPrompt(message: string, existingBrief?: Partial<CampaignBriefDraft>): string {
  let prompt = `Extract a campaign brief from this user message:\n\n"${message}"`;
  if (existingBrief) {
    prompt += `\n\nThe user has an existing draft brief. Update it based on the new message. Only include fields that are explicitly mentioned or clearly implied:\n${JSON.stringify(existingBrief, null, 2)}`;
  }
  return prompt;
}

function identifyMissingFields(brief: Partial<CampaignBriefDraft>): string[] {
  const missing: string[] = [];

  if (!brief.campaign_name) missing.push("campaign_name");
  if (!brief.product_name) missing.push("product_name");
  if (!brief.objective) missing.push("objective");
  if (!brief.target_audience?.age_range || !brief.target_audience?.gender || !brief.target_audience?.persona) {
    missing.push("target_audience");
  }
  if (!brief.platforms || brief.platforms.length === 0) missing.push("platforms");
  if (brief.budget === undefined || brief.budget === null) missing.push("budget");
  if (!brief.brand_tone || brief.brand_tone.length === 0) missing.push("brand_tone");
  if (!brief.deliverables) missing.push("deliverables");
  if (!brief.deadline) missing.push("deadline");

  return missing;
}

function compactBrief(brief: Partial<CampaignBriefDraft>): Partial<CampaignBriefDraft> {
  const next: Partial<CampaignBriefDraft> = {};
  for (const [key, value] of Object.entries(brief) as Array<[keyof CampaignBriefDraft, unknown]>) {
    if (value === null || value === undefined) continue;
    if (typeof value === "string" && !value.trim()) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    next[key] = value as never;
  }
  return next;
}

function extractLabeledValue(message: string, labels: string[]): string | undefined {
  const labelPattern = labels.map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const stopLabels = [
    "名稱", "活動名稱", "name", "named", "產品", "product", "目標", "objective", "受眾", "audience", "平台", "platform", "platforms",
    "預算", "budget", "品牌語氣", "語氣", "tone", "截止日期", "deadline", "產出", "deliverables",
  ];
  const stopPattern = stopLabels.map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const regex = new RegExp(`(?:${labelPattern})\\s*[:：]?\\s*(.+?)(?=\\s+(?:${stopPattern})\\s*[:：]?|$)`, "iu");
  return message.match(regex)?.[1]?.trim();
}

function heuristicBriefFromMessage(message: string): Partial<CampaignBriefDraft> {
  const brief: Partial<CampaignBriefDraft> = {};
  const campaignName = extractLabeledValue(message, ["活動名稱", "名稱", "campaign name", "name", "named"]);
  const productName = extractLabeledValue(message, ["產品", "product", "product name"]);
  const objective = extractLabeledValue(message, ["目標", "objective", "goal"]);
  const audience = extractLabeledValue(message, ["受眾", "audience", "target audience"]);
  const platforms = extractLabeledValue(message, ["平台", "platforms", "platform"]);
  const tone = extractLabeledValue(message, ["品牌語氣", "語氣", "tone", "brand tone"]);
  const deadline = extractLabeledValue(message, ["截止日期", "截止日", "日期", "deadline"]);
  const budgetRaw = extractLabeledValue(message, ["預算", "budget"]) ?? message.match(/(?:預算|budget)\s*[:：]?\s*([0-9][0-9,]*)/iu)?.[1];
  const hasMarketingIntent = /行銷|营销|廣告|広告|宣傳|推廣|campaign|marketing|海報|圖|圖片|image|visual/iu.test(message);

  if (campaignName) brief.campaign_name = campaignName;
  if (productName) brief.product_name = productName;
  if (!brief.campaign_name && hasMarketingIntent) brief.campaign_name = inferCampaignName(message);
  if (!brief.product_name && brief.campaign_name) brief.product_name = inferProductName(brief.campaign_name) ?? brief.campaign_name;
  if (objective) brief.objective = objective;
  if (!brief.objective && hasMarketingIntent) brief.objective = "提升品牌曝光與互動";
  if (audience) {
    brief.target_audience = {
      age_range: audience.match(/\d{2}\s*[-~到至]\s*\d{2}/)?.[0]?.replace(/\s/g, "") ?? "25-44",
      gender: /女性|female|女/i.test(audience) ? "female" : /男性|male|男/i.test(audience) ? "male" : "all",
      persona: /不限|all|general/i.test(audience) ? "不限受眾" : audience,
    };
  }
  if (!brief.target_audience && /目標受眾\s*[:：]?\s*不限|受眾\s*[:：]?\s*不限|audience\s*[:：]?\s*all/iu.test(message)) {
    brief.target_audience = { age_range: "all", gender: "all", persona: "不限受眾" };
  }
  if (platforms) brief.platforms = normalizePlatforms(platforms, true);
  if (!brief.platforms?.length) brief.platforms = normalizePlatforms(message, false);
  if (budgetRaw) {
    const budget = Number(String(budgetRaw).replace(/,/g, ""));
    if (Number.isFinite(budget) && budget > 0) brief.budget = budget;
  }
  if (tone) brief.brand_tone = tone.split(/[,，、/]/).map((item) => item.trim()).filter(Boolean);
  if (!brief.brand_tone && hasMarketingIntent) brief.brand_tone = ["清爽", "親切", "年輕"];
  if (deadline) brief.deadline = deadline.match(/\d{4}-\d{1,2}-\d{1,2}/)?.[0] ?? deadline;

  const deliverablesText = extractLabeledValue(message, ["產出", "deliverables"]);
  if (deliverablesText) {
    brief.deliverables = {
      copy_variants: Number(deliverablesText.match(/(\d+)\s*(?:篇|則|copy|copies|文案)/i)?.[1] ?? 3),
      image_assets: Number(deliverablesText.match(/(\d+)\s*(?:張|image|images|圖|圖片)/i)?.[1] ?? 2),
      short_video_assets: Number(deliverablesText.match(/(\d+)\s*(?:支|個|video|videos|影片)/i)?.[1] ?? 1),
      ads_strategy: /ads|廣告策略|投放策略/i.test(deliverablesText) ? 1 : 0,
    };
  } else if (/(\d+)\s*(?:篇|則|copy|copies|文案|張|image|images|圖|圖片|支|個|video|videos|影片)/iu.test(message)) {
    brief.deliverables = {
      copy_variants: Number(message.match(/(\d+)\s*(?:篇|則|copy|copies|文案)/iu)?.[1] ?? 0),
      image_assets: Number(message.match(/(\d+)\s*(?:張|image|images|圖|圖片)/iu)?.[1] ?? 0),
      short_video_assets: Number(message.match(/(\d+)\s*(?:支|個|video|videos|影片)/iu)?.[1] ?? 0),
      ads_strategy: /ads|廣告策略|投放策略/iu.test(message) ? 1 : 0,
    };
  } else if (/行銷圖|行銷圖片|廣告圖|宣傳圖|海報|圖片|image|visual/iu.test(message)) {
    brief.deliverables = {
      copy_variants: 1,
      image_assets: 1,
      short_video_assets: 0,
      ads_strategy: 0,
    };
  }

  if (!brief.deadline) {
    const dateMatch = message.match(/\b(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?\b/u);
    if (dateMatch) {
      const [, year, month, day] = dateMatch;
      brief.deadline = `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
    }
  }

  return compactBrief(brief);
}

function inferCampaignName(message: string): string {
  const cleaned = message
    .replace(/<[^>]+>/g, " ")
    .replace(/(?:預算|budget)\s*[:：]?\s*[0-9][0-9,]*/giu, " ")
    .replace(/(?:目標受眾|受眾|audience)\s*[:：]?\s*[^\s,，、]+/giu, " ")
    .replace(/(?:平台|platforms?|投放平台)\s*[:：]?\s*[^\s,，、]+/giu, " ")
    .replace(/\s+/g, " ")
    .trim();
  return (cleaned || message.trim()).slice(0, 80);
}

function inferProductName(campaignName: string): string | undefined {
  const match = campaignName.match(/^(.+?)(?:行銷|营销|廣告|広告|宣傳|推廣|campaign|marketing|圖|圖片|海報)/iu);
  return match?.[1]?.trim() || undefined;
}

function messageMentionsPlatforms(message: string): boolean {
  return /平台|投放平台|platforms?|\big\b|instagram|linkedin|facebook|\bfb\b|tiktok|youtube|抖音/iu.test(message);
}

function messageMentionsDeliverables(message: string): boolean {
  return /(\d+)\s*(?:篇|則|copy|copies|文案|張|image|images|圖|圖片|支|個|video|videos|影片)|產出|deliverables/iu.test(message);
}

function normalizePlatforms(value: string, allowFreeText: boolean): string[] {
  const platforms = new Set<string>();
  const lower = value.toLowerCase();
  if (/\big\b|instagram|instagram/i.test(lower)) platforms.add("Instagram");
  if (/linkedin|linked\s*in/i.test(lower)) platforms.add("LinkedIn");
  if (/facebook|\bfb\b/i.test(lower)) platforms.add("Facebook");
  if (/tiktok|抖音/i.test(lower)) platforms.add("TikTok");
  if (/youtube|yt/i.test(lower)) platforms.add("YouTube");

  if (platforms.size === 0 && allowFreeText) {
    for (const item of value.split(/[,，、/]/)) {
      const cleaned = item.trim();
      if (cleaned) platforms.add(cleaned);
    }
  }

  return Array.from(platforms);
}

function heuristicModifyBrief(
  brief: Partial<CampaignBriefDraft>,
  instruction: string,
): { brief: Partial<CampaignBriefDraft>; modified_fields: string[] } {
  const patch = heuristicBriefFromMessage(instruction);
  const budgetMatch = instruction.match(/(?:預算|budget|改成|set\s+to|change\s+to)\s*[:：]?\s*([0-9][0-9,]*)/iu);
  if (budgetMatch) {
    const budget = Number(budgetMatch[1].replace(/,/g, ""));
    if (Number.isFinite(budget) && budget > 0) patch.budget = budget;
  }

  const deadlineMatch = instruction.match(/(?:截止日期|deadline|日期).*?(\d{4}-\d{1,2}-\d{1,2})/iu) ?? instruction.match(/\d{4}-\d{1,2}-\d{1,2}/u);
  if (deadlineMatch) patch.deadline = deadlineMatch[1] ?? deadlineMatch[0];

  const merged: Partial<CampaignBriefDraft> = {
    ...brief,
    ...patch,
    target_audience: patch.target_audience ? { ...(brief.target_audience ?? {}), ...patch.target_audience } : brief.target_audience,
    deliverables: patch.deliverables ? { ...(brief.deliverables ?? {}), ...patch.deliverables } : brief.deliverables,
  };

  const modifiedFields = Object.keys(patch).filter((key) => {
    const typedKey = key as keyof CampaignBriefDraft;
    return JSON.stringify(merged[typedKey]) !== JSON.stringify(brief[typedKey]);
  });

  return {
    brief: merged,
    modified_fields: modifiedFields.length > 0 ? modifiedFields : ["no_change"],
  };
}

function computeConfidence(brief: Partial<CampaignBriefDraft>): number {
  const total = REQUIRED_FIELDS.length;
  let filled = 0;

  if (brief.campaign_name) filled++;
  if (brief.product_name) filled++;
  if (brief.objective) filled++;
  if (brief.target_audience?.age_range && brief.target_audience?.gender && brief.target_audience?.persona) filled++;
  if (brief.platforms && brief.platforms.length > 0) filled++;
  if (brief.budget !== undefined && brief.budget !== null) filled++;
  if (brief.brand_tone && brief.brand_tone.length > 0) filled++;
  if (brief.deliverables) filled++;
  if (brief.deadline) filled++;

  return Math.round((filled / total) * 100) / 100;
}

function fillDefaults(brief: Partial<CampaignBriefDraft>): CampaignBriefDraft {
  const now = new Date();
  const defaultDeadline = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000).toISOString().split("T")[0];
  const normalizedName = (brief.campaign_name ?? "").toLowerCase();
  const isComparisonVisual = ["比較", "對比", "comparison", "compare", "vs", "versus", "排行", "排名"].some(
    (term) => normalizedName.includes(term),
  ) && ["圖", "圖片", "照片", "image", "visual", "infographic", "資訊圖"].some((term) => normalizedName.includes(term));

  return {
    campaign_name: brief.campaign_name ?? "Untitled Campaign",
    product_name: brief.product_name ?? brief.campaign_name ?? "Untitled Campaign",
    description: brief.description,
    objective: brief.objective ?? "Increase awareness and conversion",
    target_audience: {
      age_range: brief.target_audience?.age_range ?? "25-44",
      gender: brief.target_audience?.gender ?? "all",
      persona: brief.target_audience?.persona ?? "Digital-savvy professionals",
    },
    platforms: brief.platforms?.length ? brief.platforms : ["LinkedIn", "Instagram"],
    budget: brief.budget ?? 50000,
    brand_tone: brief.brand_tone?.length ? brief.brand_tone : ["Professional", "Friendly"],
    deliverables: {
      copy_variants: brief.deliverables?.copy_variants ?? (isComparisonVisual ? 0 : 3),
      image_assets: brief.deliverables?.image_assets ?? (isComparisonVisual ? 1 : 2),
      short_video_assets: brief.deliverables?.short_video_assets ?? (isComparisonVisual ? 0 : 1),
      ads_strategy: brief.deliverables?.ads_strategy ?? 0,
    },
    mandatory_elements: brief.mandatory_elements ?? [],
    forbidden_elements: brief.forbidden_elements ?? [],
    deadline: brief.deadline ?? defaultDeadline,
  };
}

export async function extractCampaignBrief(
  message: string,
  existingBrief?: Partial<CampaignBriefDraft>,
): Promise<ExtractionResult> {
  const heuristic = heuristicBriefFromMessage(message);
  if (!DEEPSEEK_API_KEY) {
    const fallback = compactBrief({ ...(existingBrief ?? {}), ...heuristic });
    const full = fillDefaults(fallback);
    return {
      brief: full,
      missing_fields: identifyMissingFields(fallback),
      raw: "",
      confidence: computeConfidence(fallback),
    };
  }

  const userPrompt = buildUserPrompt(message, existingBrief);

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

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
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: userPrompt },
        ],
        temperature: 0.2,
        max_tokens: 1200,
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

    // Strip markdown code fences if present
    const jsonStr = raw.replace(/^```(?:json)?\n?/i, "").replace(/\n?```$/i, "").trim();
    const parsed = compactBrief(JSON.parse(jsonStr) as Partial<CampaignBriefDraft>);
    if (existingBrief && !messageMentionsPlatforms(message)) delete parsed.platforms;
    if (existingBrief && !messageMentionsDeliverables(message)) delete parsed.deliverables;

    // Merge with existing brief if provided
    // Cast through `unknown` to handle null-vs-undefined differences from JSON.parse
    const merged = (existingBrief
      ? {
          ...existingBrief,
          ...heuristic,
          ...(parsed as Partial<CampaignBriefDraft>),
          target_audience: {
            ...(existingBrief.target_audience ?? {}),
            ...(heuristic.target_audience ?? {}),
            ...((parsed as Partial<CampaignBriefDraft>).target_audience ?? {}),
          },
          deliverables: {
            ...(existingBrief.deliverables ?? {}),
            ...(heuristic.deliverables ?? {}),
            ...((parsed as Partial<CampaignBriefDraft>).deliverables ?? {}),
          },
        }
      : { ...heuristic, ...(parsed as Partial<CampaignBriefDraft>) }) as Partial<CampaignBriefDraft>;

    const missing = identifyMissingFields(merged);
    const confidence = computeConfidence(merged);

    return { brief: merged, missing_fields: missing, raw, confidence };
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : "Unknown error";
    console.error("[llm-parser] DeepSeek extraction failed:", errorMsg);

    // Fallback: return existing brief with defaults
    const fallback = compactBrief({ ...(existingBrief ?? {}), ...heuristic });
    const full = fillDefaults(fallback);
    return {
      brief: full,
      missing_fields: identifyMissingFields(fallback),
      raw: "",
      confidence: computeConfidence(fallback) * 0.5, // penalize for failure
    };
  }
}

/**
 * Modify an existing draft brief based on a natural language instruction.
 * e.g. "change budget to 100000", "set deadline to 2026-07-15"
 */
export async function modifyCampaignBrief(
  brief: Partial<CampaignBriefDraft>,
  instruction: string,
): Promise<ModificationResult> {
  if (!DEEPSEEK_API_KEY) {
    return heuristicModifyBrief(brief, instruction);
  }

  const modifyPrompt = `You are a campaign brief modifier. Given an existing brief and a modification instruction, apply the change.

Existing brief:
${JSON.stringify(brief, null, 2)}

Instruction: "${instruction}"

Apply ONLY the changes explicitly requested. Return the updated brief as JSON.
If the instruction is ambiguous or cannot be applied, return the original brief unchanged and list "no_change" in modified_fields.`;

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
          { role: "system", content: "You are a campaign brief modifier. Apply changes precisely." },
          { role: "user", content: modifyPrompt },
        ],
        temperature: 0.1,
        max_tokens: 800,
      }),
    });

    clearTimeout(timeout);

    if (!response.ok) {
      return { brief, modified_fields: [], error: `DeepSeek API error: ${response.status}` };
    }

    const data = (await response.json()) as {
      choices: Array<{ message: { content: string } }>;
    };
    const raw = data.choices?.[0]?.message?.content ?? "";
    const jsonStr = raw.replace(/^```(?:json)?\n?/i, "").replace(/\n?```$/i, "").trim();
    const updated = JSON.parse(jsonStr) as Partial<CampaignBriefDraft>;

    // Detect which top-level fields changed
    const modifiedFields: string[] = [];
    for (const key of Object.keys(updated) as Array<keyof CampaignBriefDraft>) {
      if (JSON.stringify(updated[key]) !== JSON.stringify(brief[key])) {
        modifiedFields.push(key);
      }
    }

    return {
      brief: updated,
      modified_fields: modifiedFields.length > 0 ? modifiedFields : ["no_change"],
    };
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : "Unknown error";
    const fallback = heuristicModifyBrief(brief, instruction);
    return fallback.modified_fields.includes("no_change") ? { ...fallback, error: errorMsg } : fallback;
  }
}

export { fillDefaults, identifyMissingFields };
