import { randomBytes } from "node:crypto";
import type {
  CampaignBriefDraft,
  ChatContext,
  ChatExecuteResponse,
  ChatIntent,
  IntentDetectionResult,
} from "@/lib/types/chatbot";
import type { SupportedLocale } from "@/lib/i18n/translations";
import { createPendingActionToken } from "@/lib/chatbot/pending-action";
import { extractCampaignBrief, modifyCampaignBrief, fillDefaults, identifyMissingFields } from "@/lib/chatbot/llm-parser";

type CampaignListApiResponse = {
  items: Array<{
    campaign_id: string;
    status: string;
    created_at: string;
    brief?: { campaign_name?: string };
  }>;
};

type TaskListApiResponse = {
  campaign_id: string;
  tasks: Array<{ task_id: string; task_type: string; status: string; priority: number }>;
};

type CampaignCreatedApiResponse = {
  campaign_id: string;
  status: string;
};

type CampaignRunApiResponse = {
  campaign_id: string;
  status: string;
};

type CampaignReferenceListApiResponse = {
  items: Array<{
    reference_id: string;
    campaign_id: string;
    file_name: string;
    file_type: string;
    file_size: number;
    uploaded_at: string;
  }>;
};

type ReviewQueueApiResponse = {
  items: Array<{
    review_id: string;
    campaign_id: string;
    asset_id: string;
    score: number;
    status: string;
  }>;
};

type ReviewApproveApiResponse = {
  review_id: string;
  status: string;
  detail: string;
};

type ValidationResultsApiResponse = {
  items: Array<{
    validation_id: string;
    asset_id: string;
    validator: string;
    score: number;
    result: string;
  }>;
};

type DeleteReferenceApiResponse = {
  reference_id: string;
  deleted: boolean;
};

export async function executeChatCommand(params: {
  locale: SupportedLocale;
  detection: IntentDetectionResult;
  context: ChatContext;
  message?: string;
}): Promise<ChatExecuteResponse> {
  const { locale, detection, context, message = "" } = params;

  if (detection.intent === "confirm_pending_action") {
    return executePendingAction(locale, context, detection);
  }

  if (detection.intent === "cancel_pending_action") {
    if (!context.pendingAction) {
      return {
        reply: replyByLocale(locale, {
          "zh-Hant": "目前沒有待確認的高風險操作。",
          en: "There is no pending high-risk action to cancel.",
          ja: "キャンセルする保留中の高リスク操作はありません。",
        }),
        intent: "cancel_pending_action",
        actionResult: { ok: false, detail: "no_pending_action" },
        context,
        followUp: [],
      };
    }

    return {
      reply: replyByLocale(locale, {
        "zh-Hant": "已取消待確認操作。",
        en: "Pending action cancelled.",
        ja: "保留中の操作をキャンセルしました。",
      }),
      intent: "cancel_pending_action",
      actionResult: { ok: true },
      context: {
        ...clearPending(context),
        draftBrief: undefined,
        awaitingBriefFields: undefined,
        briefConfidence: undefined,
      },
      followUp: [],
    };
  }

  // ── Multi-turn: continue filling missing brief fields ─────────────────────
  // Runs when user sends follow-up text while awaiting missing brief fields.
  // (confirm/cancel intents already returned above via early-return.)
  if (context.awaitingBriefFields && context.draftBrief) {
    // Pass full user message so LLM can extract field values from free text
    const fieldResult = await extractCampaignBrief(
      message,
      context.draftBrief,
    );

    // Merge new extraction with existing draft
    const merged = {
      ...context.draftBrief,
      ...fieldResult.brief,
      target_audience: {
        ...(context.draftBrief.target_audience ?? {}),
        ...(fieldResult.brief.target_audience ?? {}),
      },
      deliverables: {
        ...(context.draftBrief.deliverables ?? { copy_variants: 3, image_assets: 2, short_video_assets: 1, ads_strategy: 0 }),
        ...(fieldResult.brief.deliverables ?? {}),
      },
    } as Partial<CampaignBriefDraft>;

    const stillMissing = keepAwaitingUnansweredFields(
      identifyMissingFields(merged),
      context.awaitingBriefFields,
      message,
    );

    if (stillMissing.length > 0) {
      const filledBrief = fillDefaults(merged);
      const followUp = buildFollowUpQuestions(stillMissing, locale);
      return {
        reply: [
          replyByLocale(locale, {
            "zh-Hant": "好的，已更新以下資訊：",
            en: "Updated:",
            ja: "了解、以下を更新しました：",
          }),
          buildWorkOrderConfirmationReply(locale, filledBrief, "INCOMPLETE"),
          replyByLocale(locale, {
            "zh-Hant": `還需要補充：${formatMissingFields(stillMissing, locale)}`,
            en: `Missing: ${stillMissing.join(", ")}`,
            ja: `まだ不足: ${stillMissing.join("、")}`,
          }),
        ].join("\n"),
        intent: "create_campaign",
        actionResult: {
          ok: true,
          detail: "fields_incomplete",
          workOrder: filledBrief,
          missing_fields: stillMissing,
          confidence: fieldResult.confidence,
        },
        context: {
          ...clearPending(context),
          draftBrief: fillDefaults(merged),
          awaitingBriefFields: stillMissing,
          briefConfidence: fieldResult.confidence,
        },
        followUp,
      };
    }

    // All fields filled → show complete work order for confirmation
    const fullBrief = fillDefaults(merged);
    const pendingAction: NonNullable<ChatContext["pendingAction"]> = {
      type: "create_campaign",
      nonce: generateConfirmationNonce(),
      draftBrief: fullBrief,
      createdAt: new Date().toISOString(),
    };
    return {
      reply: [
        replyByLocale(locale, {
          "zh-Hant": "所有欄位已填寫完整，請確認工單：",
          en: "All fields complete. Review:",
          ja: "すべてのフィールドが入力されました。工單を確認してください：",
        }),
        buildWorkOrderConfirmationReply(locale, fullBrief, pendingAction.nonce ?? ""),
      ].join("\n"),
      intent: "create_campaign",
      actionResult: {
        ok: true,
        detail: "confirmation_required",
        workOrder: fullBrief,
        missing_fields: [],
        confidence: 1.0,
      },
      context: {
        ...clearPending(context),
        pendingAction,
        pendingActionToken: createPendingActionToken(pendingAction),
        draftBrief: fullBrief,
      },
        followUp: [
          replyByLocale(locale, {
            "zh-Hant": `確認 ${pendingAction.nonce} 建立，或說「修改...」調整內容。`,
            en: `Confirm ${pendingAction.nonce} to create, or 'modify...' to change.`,
            ja: `${pendingAction.nonce} で作成、または「修改...」で内容を変更してください。`,
          }),
        ],
    };
  }

  if (detection.intent === "delete_reference") {
    return stageDeleteReference(locale, detection, context);
  }

  if (detection.intent === "modify_work_order") {
    const currentBrief = context.draftBrief ?? context.pendingAction?.draftBrief;
    if (!currentBrief) {
      return {
        reply: replyByLocale(locale, {
          "zh-Hant": "目前沒有可修改的工單。請先說「建立活動」建立一個新工單。",
          en: "There is no work order to modify. Please say 'create a campaign' first.",
          ja: "修改する工單がありません。「キャンペーン作成」と食べてください。",
        }),
        intent: "modify_work_order",
        actionResult: { ok: false, detail: "no_work_order_to_modify" },
        context,
        followUp: [],
      };
    }

    const instruction = detection.slots.modificationInstruction ?? "";
    const modResult = await modifyCampaignBrief(currentBrief, instruction);

    if (modResult.error) {
      return {
        reply: replyByLocale(locale, {
          "zh-Hant": `修改失敗：${modResult.error}。請重新描述你要修改的內容。`,
          en: `Modification failed: ${modResult.error}. Please rephrase what you'd like to change.`,
          ja: `修改失敗: ${modResult.error}。再度説明してください。`,
        }),
        intent: "modify_work_order",
        actionResult: { ok: false, detail: modResult.error },
        context,
        followUp: [],
      };
    }

    const updatedBrief = fillDefaults(modResult.brief);
    const pendingAction: NonNullable<ChatContext["pendingAction"]> = {
      type: "create_campaign",
      nonce: generateConfirmationNonce(),
      draftBrief: updatedBrief,
      createdAt: new Date().toISOString(),
    };

    return {
      reply: [
        replyByLocale(locale, {
          "zh-Hant": `已修改欄位：${modResult.modified_fields.join("、")}。更新後的工單：`,
          en: `Modified: ${modResult.modified_fields.join(", ")}. Updated work order:`,
          ja: `更新したフィールド: ${modResult.modified_fields.join("、")}。更新後の工單:`,
        }),
        buildWorkOrderConfirmationReply(locale, updatedBrief, pendingAction.nonce ?? ""),
      ].join("\n"),
      intent: "modify_work_order",
      actionResult: {
        ok: true,
        detail: "work_order_modified",
        workOrder: updatedBrief,
      },
      context: {
        ...clearPending(context),
        pendingAction,
        pendingActionToken: createPendingActionToken(pendingAction),
        draftBrief: updatedBrief,
      },
      followUp: [
        replyByLocale(locale, {
          "zh-Hant": `確認 ${pendingAction.nonce} 建立，或繼續修改其他內容。`,
          en: `Confirm ${pendingAction.nonce} to create, or modify more.`,
          ja: `${pendingAction.nonce} で作成、または繼續修改してください。`,
        }),
      ],
    };
  }

  if (detection.intent === "approve_review") {
    return stageApproveReview(locale, detection, context);
  }

  if (detection.intent === "regenerate_asset") {
    return handleRegenerateAsset(locale, detection);
  }

  if (detection.intent === "unknown") {
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": "可以，我可以協助你建立或管理活動。請提供活動名稱、預算、目標受眾和投放平台。",
        en: "Sure — I can help create or manage a campaign. Please share the campaign name, budget, target audience, and platforms.",
        ja: "承知しました。キャンペーン作成や管理をお手伝いできます。キャンペーン名、予算、対象ユーザー、配信プラットフォームを教えてください。",
      }),
      intent: "unknown",
      actionResult: { ok: false, detail: "unsupported_intent" },
      context,
      followUp: [
        replyByLocale(locale, {
          "zh-Hant": "例如：建立一個新品上市活動，預算 50000，目標 25-40 歲上班族，平台 LinkedIn 和 Instagram。",
          en: "Example: Create a product launch campaign, budget 50000, audience professionals aged 25-40, platforms LinkedIn and Instagram.",
          ja: "例：新商品ローンチキャンペーン、予算50000、対象25〜40歳の会社員、LinkedInとInstagram。",
        }),
      ],
    };
  }

  if (detection.intent === "create_campaign") {
    const briefSource = message.trim() || (detection.slots.campaignName ? `${detection.slots.campaignName} budget ${detection.slots.budget ?? ""}` : detection.slots.campaignName ?? "");
    const result = await extractCampaignBrief(briefSource);
    const existingBrief = context.draftBrief ? { ...context.draftBrief, ...result.brief } : result.brief;
    const missing = result.missing_fields;

    if (missing.length > 0) {
      const filledBrief = fillDefaults(existingBrief);
      const followUp = buildFollowUpQuestions(missing, locale);
      return {
        reply: [
          replyByLocale(locale, {
            "zh-Hant": "我已從你的描述中提取了以下工單資訊，但需要確認一些細節：",
            en: "I've extracted the following from your description, but need to confirm a few details:",
            ja: "描述から以下の情報を抽出しましたが、いくつか確認が必要です：",
          }),
          buildWorkOrderConfirmationReply(locale, filledBrief, "INCOMPLETE"),
          replyByLocale(locale, {
            "zh-Hant": `缺少欄位：${missing.join("、")}`,
            en: `Missing fields: ${missing.join(", ")}`,
            ja: `不足フィールド: ${missing.join("、")}`,
          }),
        ].join("\n"),
        intent: "create_campaign",
        actionResult: {
          ok: true,
          detail: "fields_incomplete",
          workOrder: filledBrief,
          missing_fields: missing,
          confidence: result.confidence,
        },
        context: {
          ...clearPending(context),
          draftBrief: fillDefaults(existingBrief),
          awaitingBriefFields: missing,
          briefConfidence: result.confidence,
        },
        followUp,
      };
    }

    const fullBrief = fillDefaults(existingBrief);
    const pendingAction: NonNullable<ChatContext["pendingAction"]> = {
      type: "create_campaign",
      nonce: generateConfirmationNonce(),
      draftBrief: fullBrief,
      createdAt: new Date().toISOString(),
    };
    return {
      reply: buildWorkOrderConfirmationReply(locale, fullBrief, pendingAction.nonce ?? ""),
      intent: "create_campaign",
      actionResult: {
        ok: true,
        detail: "confirmation_required",
        workOrder: fullBrief,
        missing_fields: [],
        confidence: result.confidence,
      },
      context: {
        ...clearPending(context),
        pendingAction,
        pendingActionToken: createPendingActionToken(pendingAction),
        draftBrief: fullBrief,
      },
      followUp: [
        replyByLocale(locale, {
          "zh-Hant": `請確認以上工單資訊。若正確，請回覆「確認 ${pendingAction.nonce}」建立活動；若要修改，請直接說明（例如：把預算改為 10 萬）。`,
          en: `Confirm ${pendingAction.nonce} to create, or modify directly (e.g. "budget 100000").`,
          ja: `工單内容を確認してください。「確認 ${pendingAction.nonce}」で作成するか、直接修改してください（例：「予算を10万に変更」）。`,
        }),
      ],
    };
  }

  if (detection.intent === "run_campaign") {
    const campaignId = await resolveCampaignId(detection.slots.campaignId, context);
    if (!campaignId) {
      return missingCampaignReply(locale, "run_campaign", context);
    }

    try {
      const result = await apiRequest<CampaignRunApiResponse>(`/api/v1/campaigns/${campaignId}/run`, {
        method: "POST",
      });

      return {
        reply: replyByLocale(locale, {
          "zh-Hant": `已啟動活動 ${campaignId}，目前狀態 ${result.status}。`,
          en: `Campaign ${campaignId} started. Current status: ${result.status}.`,
          ja: `キャンペーン ${campaignId} を起動しました。現在のステータス: ${result.status}。`,
        }),
        intent: "run_campaign",
        actionResult: {
          ok: true,
          campaign_id: campaignId,
          status: result.status,
        },
        context: {
          ...clearPending(context),
          activeCampaignId: campaignId,
          lastCampaignId: campaignId,
        },
        followUp: [
          replyByLocale(locale, {
            "zh-Hant": "要我幫你查目前任務進度嗎？",
            en: "Want me to check current tasks?",
            ja: "現在のタスク進捗を確認しますか？",
          }),
        ],
      };
    } catch (error) {
      return commandError(locale, "run_campaign", context, error);
    }
  }

  if (detection.intent === "list_campaigns") {
    try {
      const data = await apiRequest<CampaignListApiResponse>("/api/v1/campaigns");
      const campaigns = data.items.slice(0, 10).map((item) => ({
        campaign_id: item.campaign_id,
        status: item.status,
        created_at: item.created_at,
        name: item.brief?.campaign_name ?? item.campaign_id,
      }));

      const reply = campaigns.length
        ? campaigns
            .map((item, index) => `${index + 1}. ${item.name} (${item.campaign_id}) - ${item.status}`)
            .join("\n")
        : replyByLocale(locale, {
            "zh-Hant": "目前沒有活動資料。",
            en: "No campaigns found.",
            ja: "キャンペーンはまだありません。",
          });

      return {
        reply,
        intent: "list_campaigns",
        actionResult: { ok: true, campaigns },
        context,
        followUp: [],
      };
    } catch (error) {
      return commandError(locale, "list_campaigns", context, error);
    }
  }

  if (detection.intent === "list_tasks") {
    const campaignId = await resolveCampaignId(detection.slots.campaignId, context);
    if (!campaignId) {
      return missingCampaignReply(locale, "list_tasks", context);
    }

    try {
      const data = await apiRequest<TaskListApiResponse>(`/api/v1/campaigns/${campaignId}/tasks`);
      const tasks = data.tasks.slice(0, 20);
      const reply = tasks.length
        ? tasks
            .map((task, index) => `${index + 1}. ${task.task_type} - ${task.status} (P${task.priority})`)
            .join("\n")
        : replyByLocale(locale, {
            "zh-Hant": "這個活動目前沒有任務。",
            en: "This campaign currently has no tasks.",
            ja: "このキャンペーンには現在タスクがありません。",
          });

      return {
        reply,
        intent: "list_tasks",
        actionResult: { ok: true, campaign_id: campaignId, tasks },
        context: {
          ...clearPending(context),
          activeCampaignId: campaignId,
          lastCampaignId: campaignId,
        },
        followUp: [],
      };
    } catch (error) {
      return commandError(locale, "list_tasks", context, error);
    }
  }

  if (detection.intent === "list_references") {
    const campaignId = await resolveCampaignId(detection.slots.campaignId, context);
    if (!campaignId) {
      return missingCampaignReply(locale, "list_references", context);
    }

    try {
      const data = await apiRequest<CampaignReferenceListApiResponse>(`/api/v1/campaigns/${campaignId}/references`);
      const references = data.items.slice(0, 20);
      const unitLabel = locale === "zh-Hant" ? "位元組" : locale === "ja" ? "バイト" : "bytes";
      const reply = references.length
        ? references
            .map((item, index) => `${index + 1}. ${item.file_name} (${item.reference_id}, ${item.file_size} ${unitLabel})`)
            .join("\n")
        : replyByLocale(locale, {
            "zh-Hant": "這個活動目前沒有參考資料。",
            en: "This campaign currently has no references.",
            ja: "このキャンペーンには参照資料がありません。",
          });

      return {
        reply,
        intent: "list_references",
        actionResult: { ok: true, campaign_id: campaignId, references },
        context: {
          ...clearPending(context),
          activeCampaignId: campaignId,
          lastCampaignId: campaignId,
        },
        followUp: [],
      };
    } catch (error) {
      return commandError(locale, "list_references", context, error);
    }
  }

  if (detection.intent === "list_review_queue") {
    try {
      const data = await apiRequest<ReviewQueueApiResponse>("/api/v1/review/items?page=1&page_size=20");
      const reviewItems = data.items;
      const scoreLabel = locale === "zh-Hant" ? "分數" : locale === "ja" ? "スコア" : "score";
      const reply = reviewItems.length
        ? reviewItems
            .map((item, index) => `${index + 1}. ${item.review_id} (${item.campaign_id}) - ${item.status}, ${scoreLabel} ${Math.round(item.score * 100)}`)
            .join("\n")
        : replyByLocale(locale, {
            "zh-Hant": "目前沒有待審核項目。",
            en: "No review queue items found.",
            ja: "レビュー待ち項目はありません。",
          });

      return {
        reply,
        intent: "list_review_queue",
        actionResult: { ok: true, reviewItems },
        context,
        followUp: [],
      };
    } catch (error) {
      return commandError(locale, "list_review_queue", context, error);
    }
  }

  if (detection.intent === "list_validation_results") {
    const campaignId = await resolveCampaignId(detection.slots.campaignId, context);
    if (!campaignId) {
      return missingCampaignReply(locale, "list_validation_results", context);
    }

    try {
      const data = await apiRequest<ValidationResultsApiResponse>(`/api/v1/campaigns/${campaignId}/validation-results`);
      const validationResults = data.items.slice(0, 20);
      const scoreLabel = locale === "zh-Hant" ? "分數" : locale === "ja" ? "スコア" : "score";
      const reply = validationResults.length
        ? validationResults
            .map(
              (item, index) =>
                `${index + 1}. ${item.asset_id} - ${item.result} (${item.validator}, ${scoreLabel} ${Math.round(item.score * 100)})`,
            )
            .join("\n")
        : replyByLocale(locale, {
            "zh-Hant": "這個活動目前沒有驗證結果。",
            en: "This campaign currently has no validation results.",
            ja: "このキャンペーンには検証結果がありません。",
          });

      return {
        reply,
        intent: "list_validation_results",
        actionResult: { ok: true, campaign_id: campaignId, validationResults },
        context: {
          ...clearPending(context),
          activeCampaignId: campaignId,
          lastCampaignId: campaignId,
        },
        followUp: [],
      };
    } catch (error) {
      return commandError(locale, "list_validation_results", context, error);
    }
  }

  return {
    reply: "Unsupported intent",
    intent: detection.intent satisfies ChatIntent,
    actionResult: { ok: false, detail: "unsupported_intent" },
    context,
    followUp: [],
  };
}

async function stageDeleteReference(
  locale: SupportedLocale,
  detection: IntentDetectionResult,
  context: ChatContext,
): Promise<ChatExecuteResponse> {
  const campaignId = await resolveCampaignId(detection.slots.campaignId, context);
  if (!campaignId) {
    return missingCampaignReply(locale, "delete_reference", context);
  }

  const candidateId = detection.slots.referenceId;
  if (!candidateId) {
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": "請提供 reference_id 才能刪除參考資料（例如：刪除參考資料 ref_xxx）。",
        en: "Please provide a reference_id to delete a reference (e.g. delete reference ref_xxx).",
        ja: "参照資料を削除するには reference_id が必要です（例: 参照資料 ref_xxx を削除）。",
      }),
      intent: "delete_reference",
      actionResult: { ok: false, detail: "reference_id_required" },
      context,
      followUp: [],
    };
  }

  const pendingAction: NonNullable<ChatContext["pendingAction"]> = {
    type: "delete_reference",
    nonce: generateConfirmationNonce(),
    campaignId,
    referenceId: candidateId,
    createdAt: new Date().toISOString(),
  };

  return {
    reply: replyByLocale(locale, {
      "zh-Hant": `這是高風險操作：即將刪除參考資料 ${candidateId}（活動 ${campaignId}）。`,
      en: `High-risk action: about to delete reference ${candidateId} (campaign ${campaignId}).`,
      ja: `高リスク操作です: 参照資料 ${candidateId}（キャンペーン ${campaignId}）を削除します。`,
    }),
    intent: "delete_reference",
    actionResult: { ok: true, campaign_id: campaignId, detail: "confirmation_required" },
    context: {
      ...context,
      activeCampaignId: campaignId,
      lastCampaignId: campaignId,
      pendingAction,
      pendingActionToken: createPendingActionToken(pendingAction),
    },
    followUp: [
      replyByLocale(locale, {
        "zh-Hant": `請回覆「確認 ${pendingAction.nonce}」執行，或「取消」中止。`,
        en: `Confirm ${pendingAction.nonce} or cancel.`,
        ja: `実行するには「確認 ${pendingAction.nonce}」、中止するには「キャンセル」と入力してください。`,
      }),
    ],
  };
}

async function stageApproveReview(
  locale: SupportedLocale,
  detection: IntentDetectionResult,
  context: ChatContext,
): Promise<ChatExecuteResponse> {
  const candidateId = detection.slots.reviewId;
  if (!candidateId) {
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": "請提供 review_id 才能核准審核項目（例如：核准審核 review_xxx）。",
        en: "Please provide a review_id to approve a review item (e.g. approve review review_xxx).",
        ja: "レビュー承認には review_id が必要です（例: レビュー review_xxx を承認）。",
      }),
      intent: "approve_review",
      actionResult: { ok: false, detail: "review_id_required" },
      context,
      followUp: [],
    };
  }

  const pendingAction: NonNullable<ChatContext["pendingAction"]> = {
    type: "approve_review",
    nonce: generateConfirmationNonce(),
    reviewId: candidateId,
    createdAt: new Date().toISOString(),
  };

  return {
    reply: replyByLocale(locale, {
      "zh-Hant": `這是高風險操作：即將核准審核項目 ${candidateId}。`,
      en: `High-risk action: about to approve review item ${candidateId}.`,
      ja: `高リスク操作です: レビュー項目 ${candidateId} を承認します。`,
    }),
    intent: "approve_review",
    actionResult: { ok: true, detail: "confirmation_required" },
    context: {
      ...context,
      pendingAction,
      pendingActionToken: createPendingActionToken(pendingAction),
    },
    followUp: [
      replyByLocale(locale, {
        "zh-Hant": `請回覆「確認 ${pendingAction.nonce}」執行，或「取消」中止。`,
        en: `Confirm ${pendingAction.nonce} or cancel.`,
        ja: `実行するには「確認 ${pendingAction.nonce}」、中止するには「キャンセル」と入力してください。`,
      }),
    ],
  };
}

async function handleRegenerateAsset(
  locale: SupportedLocale,
  detection: IntentDetectionResult,
): Promise<ChatExecuteResponse> {
  const assetId = detection.slots.assetId;
  if (!assetId) {
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": "請提供素材 ID 才能重新生成（例如：重新生成素材 ast_abc123）。",
        en: "Please provide an asset ID to regenerate (e.g. regenerate asset ast_abc123).",
        ja: "再生成するアセットIDを指定してください（例: アセット ast_abc123 を再生成）。",
      }),
      intent: "regenerate_asset",
      actionResult: { ok: false, detail: "asset_id_required" },
      context: {},
      followUp: [],
    };
  }

  try {
    await apiRequest<{ status: string; asset_id: string }>(`/api/v1/assets/${assetId}/regenerate`, {
      method: "POST",
    });
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": `已提交素材 ${assetId} 的重新生成請求。新版本將在數分鐘後產生。`,
        en: `Regeneration requested for asset ${assetId}. A new version will be available shortly.`,
        ja: `アセット ${assetId} の再生成リクエストを送信しました。新しいバージョンは数分後に利用可能になります。`,
      }),
      intent: "regenerate_asset",
      actionResult: { ok: true, detail: "regenerate_submitted", campaign_id: assetId },
      context: {},
      followUp: [],
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": `重新生成失敗：${message}`,
        en: `Regeneration failed: ${message}`,
        ja: `再生成に失敗しました: ${message}`,
      }),
      intent: "regenerate_asset",
      actionResult: { ok: false, detail: message },
      context: {},
      followUp: [],
    };
  }
}

async function executePendingAction(
  locale: SupportedLocale,
  context: ChatContext,
  detection: IntentDetectionResult,
): Promise<ChatExecuteResponse> {
  const pending = context.pendingAction;
  if (!pending) {
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": "目前沒有待確認的高風險操作。",
        en: "There is no pending high-risk action to confirm.",
        ja: "確認する保留中の高リスク操作はありません。",
      }),
      intent: "confirm_pending_action",
      actionResult: { ok: false, detail: "no_pending_action" },
      context,
      followUp: [],
    };
  }

  if (pending.type === "create_campaign") {
    if (!pending.nonce || detection.slots.confirmationCode !== pending.nonce) {
      return {
        reply: replyByLocale(locale, {
          "zh-Hant": "確認碼不正確，請使用工單顯示的確認碼再試一次。",
          en: "Invalid confirmation code. Please retry with the exact code shown in the work order.",
          ja: "確認コードが一致しません。工單に表示されたコードで再実行してください。",
        }),
        intent: "confirm_pending_action",
        actionResult: { ok: false, detail: "confirmation_code_mismatch" },
        context,
        followUp: [],
      };
    }
    if (!pending.draftBrief) {
      return {
        reply: replyByLocale(locale, {
          "zh-Hant": "待確認工單資訊不完整，已取消。",
          en: "Pending work order is incomplete and has been cancelled.",
          ja: "保留中の工單情報が不完全なためキャンセルしました。",
        }),
        intent: "confirm_pending_action",
        actionResult: { ok: false, detail: "invalid_pending_action" },
        context: clearPending(context),
        followUp: [],
      };
    }
    try {
      const created = await apiRequest<CampaignCreatedApiResponse>("/api/v1/campaigns", {
        method: "POST",
        body: JSON.stringify(pending.draftBrief),
      });
      return {
        reply: replyByLocale(locale, {
          "zh-Hant": `已依確認工單建立活動 ${created.campaign_id}。`,
          en: `Campaign ${created.campaign_id} created from the confirmed work order.`,
          ja: `確認済み工單からキャンペーン ${created.campaign_id} を作成しました。`,
        }),
        intent: "confirm_pending_action",
        actionResult: { ok: true, campaign_id: created.campaign_id, status: created.status, detail: "create_campaign_confirmed" },
        context: {
          ...clearPending(context),
          activeCampaignId: created.campaign_id,
          lastCampaignId: created.campaign_id,
        },
        followUp: [
          replyByLocale(locale, {
            "zh-Hant": "要我直接幫你啟動這個活動嗎？",
            en: "Want me to run this campaign now?",
            ja: "このキャンペーンを今すぐ起動しますか？",
          }),
        ],
      };
    } catch (error) {
      return commandError(locale, "confirm_pending_action", clearPending(context), error);
    }
  }

  if (pending.type === "delete_reference") {
    if (!pending.nonce || detection.slots.confirmationCode !== pending.nonce) {
      return {
        reply: replyByLocale(locale, {
          "zh-Hant": "確認碼不正確，請使用系統顯示的確認碼再試一次。",
          en: "Invalid confirmation code. Please retry with the exact code shown by the system.",
          ja: "確認コードが一致しません。システム表示のコードで再実行してください。",
        }),
        intent: "confirm_pending_action",
        actionResult: { ok: false, detail: "confirmation_code_mismatch" },
        context,
        followUp: [],
      };
    }

    if (!pending.campaignId || !pending.referenceId) {
      return {
        reply: replyByLocale(locale, {
          "zh-Hant": "待確認刪除操作資訊不完整，已取消。",
          en: "Pending delete action is incomplete and has been cancelled.",
          ja: "保留中の削除情報が不完全なためキャンセルしました。",
        }),
        intent: "confirm_pending_action",
        actionResult: { ok: false, detail: "invalid_pending_action" },
        context: clearPending(context),
        followUp: [],
      };
    }

    try {
      const result = await apiRequest<DeleteReferenceApiResponse>(
        `/api/v1/campaigns/${pending.campaignId}/references/${pending.referenceId}`,
        { method: "DELETE" },
      );

      return {
        reply: replyByLocale(locale, {
          "zh-Hant": `已刪除參考資料 ${result.reference_id}。`,
          en: `Reference ${result.reference_id} deleted.`,
          ja: `参照資料 ${result.reference_id} を削除しました。`,
        }),
        intent: "confirm_pending_action",
        actionResult: { ok: true, campaign_id: pending.campaignId, detail: "delete_reference_confirmed" },
        context: {
          ...clearPending(context),
          activeCampaignId: pending.campaignId,
          lastCampaignId: pending.campaignId,
        },
        followUp: [],
      };
    } catch (error) {
      return commandError(locale, "confirm_pending_action", clearPending(context), error);
    }
  }

  if (!pending.reviewId) {
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": "待確認核准操作資訊不完整，已取消。",
        en: "Pending approve action is incomplete and has been cancelled.",
        ja: "保留中の承認情報が不完全なためキャンセルしました。",
      }),
      intent: "confirm_pending_action",
      actionResult: { ok: false, detail: "invalid_pending_action" },
      context: clearPending(context),
      followUp: [],
    };
  }

  if (!pending.nonce || detection.slots.confirmationCode !== pending.nonce) {
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": "確認碼不正確，請使用系統顯示的確認碼再試一次。",
        en: "Invalid confirmation code. Please retry with the exact code shown by the system.",
        ja: "確認コードが一致しません。システム表示のコードで再実行してください。",
      }),
      intent: "confirm_pending_action",
      actionResult: { ok: false, detail: "confirmation_code_mismatch" },
      context,
      followUp: [],
    };
  }

  try {
    const result = await apiRequest<ReviewApproveApiResponse>(`/api/v1/review/items/${pending.reviewId}/approve`, {
      method: "POST",
      body: JSON.stringify({ operator: "chatbot" }),
    });
    return {
      reply: replyByLocale(locale, {
        "zh-Hant": `已核准審核項目 ${result.review_id}。`,
        en: `Review item ${result.review_id} approved.`,
        ja: `レビュー項目 ${result.review_id} を承認しました。`,
      }),
      intent: "confirm_pending_action",
      actionResult: { ok: true, detail: "approve_review_confirmed", status: result.status },
      context: clearPending(context),
      followUp: [],
    };
  } catch (error) {
    return commandError(locale, "confirm_pending_action", clearPending(context), error);
  }
}

function clearPending(context: ChatContext): ChatContext {
  const nextContext: ChatContext = { ...context };
  delete nextContext.pendingAction;
  delete nextContext.pendingActionToken;
  return nextContext;
}

function missingCampaignReply(locale: SupportedLocale, intent: ChatIntent, context: ChatContext): ChatExecuteResponse {
  return {
    reply: replyByLocale(locale, {
      "zh-Hant": "請先指定 campaign_id，或先建立/啟動一個活動。",
      en: "Please provide a campaign_id, or create/run a campaign first.",
      ja: "campaign_id を指定するか、先にキャンペーンを作成/起動してください。",
    }),
    intent,
    actionResult: { ok: false, detail: "campaign_id_required" },
    context,
    followUp: [],
  };
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const apiBase = getCampaignApiBase();
  const internalApiKey = process.env.CHATBOT_INTERNAL_API_KEY ?? "";
  if (!internalApiKey) {
    throw new Error("Missing CHATBOT_INTERNAL_API_KEY for chatbot backend calls");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);

  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(internalApiKey ? { "x-internal-api-key": internalApiKey } : {}),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
    clearTimeout(timeout);
  } catch (err) {
    clearTimeout(timeout);
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error("Campaign API request timed out after 30 seconds");
    }
    throw err;
  }

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        detail = payload.detail;
      }
    } else {
      const text = await response.text();
      if (text.trim()) detail = text;
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

function getCampaignApiBase(): string {
  const base =
    process.env.CAMPAIGN_API_BASE ??
    process.env.NEXT_PUBLIC_CAMPAIGN_API_BASE ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8080";
  if (base === "/") return "http://campaign-service:8080";
  return base.replace(/\/$/, "");
}

async function resolveCampaignId(explicitCampaignId: string | undefined, context: ChatContext): Promise<string | undefined> {
  if (explicitCampaignId) return explicitCampaignId;
  if (context.activeCampaignId) return context.activeCampaignId;
  if (context.lastCampaignId) return context.lastCampaignId;

  try {
    const campaigns = await apiRequest<CampaignListApiResponse>("/api/v1/campaigns");
    return campaigns.items[0]?.campaign_id;
  } catch {
    return undefined;
  }
}

function generateConfirmationNonce(): string {
  return randomBytes(4).toString("hex").toUpperCase();
}

function buildWorkOrderConfirmationReply(locale: SupportedLocale, brief: CampaignBriefDraft, nonce: string): string {
  const deliverables = [
    `文案 ${brief.deliverables.copy_variants}`,
    `圖片 ${brief.deliverables.image_assets}`,
    `短影片 ${brief.deliverables.short_video_assets}`,
    `廣告策略 ${brief.deliverables.ads_strategy}`,
  ].join(" / ");
  if (locale === "en") {
    return [
      `Review before creation (code: ${nonce}):`,
      `${brief.campaign_name} / ${brief.product_name}`,
      `Goal: ${brief.objective}`,
      `Audience: ${brief.target_audience.age_range}, ${brief.target_audience.gender}`,
      `Platforms: ${brief.platforms.join(", ") || "N/A"} | Budget: ${brief.budget}`,
      `Output: copy×${brief.deliverables.copy_variants} / img×${brief.deliverables.image_assets} / vid×${brief.deliverables.short_video_assets} / ads×${brief.deliverables.ads_strategy}`,
      `Tone: ${brief.brand_tone.join(", ") || "N/A"} | Due: ${brief.deadline}`,
    ].join("\n");
  }
  if (locale === "ja") {
    return [
      "作成前にキャンペーン工單を確認してください：",
      `キャンペーン名：${brief.campaign_name}`,
      `商品：${brief.product_name}`,
      `目的：${brief.objective}`,
      `対象：${brief.target_audience.age_range}、${brief.target_audience.gender}、${brief.target_audience.persona}`,
      `プラットフォーム：${brief.platforms.join("、") || "未指定"}`,
      `予算：${brief.budget}`,
      `成果物：${deliverables}`,
      `トーン：${brief.brand_tone.join("、") || "未指定"}`,
      `期限：${brief.deadline}`,
      `確認コード：${nonce}`,
    ].join("\n");
  }
  return [
    "建立前請先確認完整活動工單：",
    `活動名稱：${brief.campaign_name}`,
    `產品/主題：${brief.product_name}`,
    `目標：${brief.objective}`,
    `受眾：${brief.target_audience.age_range}、${brief.target_audience.gender}、${brief.target_audience.persona}`,
    `平台：${brief.platforms.join("、") || "未指定"}`,
    `預算：${brief.budget}`,
    `產出：${deliverables}`,
    `語氣：${brief.brand_tone.join("、") || "未指定"}`,
    `期限：${brief.deadline}`,
    `確認碼：${nonce}`,
  ].join("\n");
}

function replyByLocale(locale: SupportedLocale, textByLocale: Record<SupportedLocale, string>): string {
  return textByLocale[locale];
}

function formatMissingFields(fields: string[], locale: SupportedLocale): string {
  return fields.map((field) => FIELD_LABELS[field]?.[locale] ?? field).join(locale === "en" ? ", " : "、");
}

function keepAwaitingUnansweredFields(currentMissing: string[], previousMissing: string[], message: string): string[] {
  const missing = new Set(currentMissing);
  const text = message.trim();
  for (const field of previousMissing) {
    if (field === "deadline" && !/\b20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?\b|截止|deadline|日期/iu.test(text)) {
      missing.add(field);
    }
    if (field === "deliverables" && !/(\d+)\s*(?:篇|則|copy|copies|文案|張|image|images|圖|圖片|支|個|video|videos|影片)|產出|deliverables/iu.test(text)) {
      missing.add(field);
    }
  }
  return Array.from(missing);
}

function commandError(
  locale: SupportedLocale,
  intent: ChatIntent,
  context: ChatContext,
  error: unknown,
): ChatExecuteResponse {
  const detail = error instanceof Error ? error.message : "Unknown error";
  return {
    reply: replyByLocale(locale, {
      "zh-Hant": `執行失敗：${detail}`,
      en: `Execution failed: ${detail}`,
      ja: `実行に失敗しました: ${detail}`,
    }),
    intent,
    actionResult: { ok: false, detail },
    context,
    followUp: [],
  };
}

const FIELD_LABELS: Record<string, Record<SupportedLocale, string>> = {
  campaign_name: { "zh-Hant": "活動名稱", en: "campaign name", ja: "キャンペーン名" },
  product_name: { "zh-Hant": "產品/主題", en: "product or subject", ja: "商品・テーマ" },
  objective: { "zh-Hant": "目標", en: "campaign objective", ja: "キャンペーン目標" },
  target_audience: { "zh-Hant": "目標受眾", en: "target audience", ja: "対象ユーザー" },
  platforms: { "zh-Hant": "平台", en: "platforms", ja: "プラットフォーム" },
  budget: { "zh-Hant": "預算", en: "budget (TWD)", ja: "予算（TWD）" },
  brand_tone: { "zh-Hant": "品牌語氣", en: "brand tone", ja: "ブランドトーン" },
  deliverables: { "zh-Hant": "產出內容", en: "deliverables (copy/images/video)", ja: "成果物（コピー/画像/動画）" },
  deadline: { "zh-Hant": "截止日期", en: "deadline", ja: "截止日" },
};

function buildFollowUpQuestions(missingFields: string[], locale: SupportedLocale): string[] {
  const label = (field: string) => FIELD_LABELS[field]?.[locale] ?? field;
  const questions = missingFields.map((field) => {
    if (field === "target_audience") {
      return replyByLocale(locale, {
        "zh-Hant": "目標受眾是什麼？（例如：25-44歲、女性、注重健康的專業人士）",
        en: "Target audience? (e.g. 25-44, female)",
        ja: "対象ユーザーは誰ですか？（例：25-44歳、女性、健康志向の-professionals）",
      });
    }
    if (field === "platforms") {
      return replyByLocale(locale, {
        "zh-Hant": "要投放到哪些平台？（例如：LinkedIn、Instagram、Facebook）",
        en: "Platforms? (LinkedIn, Instagram, Facebook)",
        ja: "どのプラットフォームに配信？（例：LinkedIn、Instagram、Facebook）",
      });
    }
    if (field === "budget") {
      return replyByLocale(locale, {
        "zh-Hant": "這次活動的預算是多少？（例如：10萬、50000）",
        en: "Budget? (e.g. 50000)",
        ja: "キャンペーンの予算はいくらですか？（例：10万、50000）",
      });
    }
    if (field === "deadline") {
      return replyByLocale(locale, {
        "zh-Hant": "活動的截止日期是什麼時候？（YYYY-MM-DD）",
        en: "Deadline? (YYYY-MM-DD)",
        ja: "截止日はいつですか？（YYYY-MM-DD）",
      });
    }
    if (field === "brand_tone") {
      return replyByLocale(locale, {
        "zh-Hant": "品牌語氣是什麼？（例如：專業、親切、休閒）",
        en: "Brand tone? (e.g. professional, friendly)",
        ja: "ブランドトーンは？（例：專業、親切、カジュアル）",
      });
    }
    if (field === "deliverables") {
      return replyByLocale(locale, {
        "zh-Hant": "需要哪些產出？（例如：3篇文案、2張圖、1支短影片）",
        en: "Deliverables? (e.g. copy×3, img×2, vid×1)",
        ja: "どの成果物が必要？（例：コピー3本、画像2枚ショート動画1本）",
      });
    }
    return replyByLocale(locale, {
      "zh-Hant": `請提供 ${label(field)} 資訊。`,
      en: `${label(field)}?`,
      ja: `${label(field)}を入力してください。`,
    });
  });
  return questions;
}
