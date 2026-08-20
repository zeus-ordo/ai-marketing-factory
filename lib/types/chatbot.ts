import type { SupportedLocale } from "@/lib/i18n/translations";

export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
};

export type ChatContext = {
  activeCampaignId?: string;
  lastCampaignId?: string;
  pendingActionToken?: string;
  pendingAction?: {
    type: "delete_reference" | "approve_review" | "create_campaign" | "run_campaign";
    nonce?: string;
    campaignId?: string;
    referenceId?: string;
    reviewId?: string;
    draftBrief?: CampaignBriefDraft;
    createdAt: string;
  };
  pendingActionTokenExpired?: boolean;
  draftBrief?: CampaignBriefDraft;
  awaitingBriefFields?: string[];
  briefConfidence?: number;
};

export type CampaignBriefDraft = {
  campaign_name: string;
  product_name: string;
  description?: string;
  objective: string;
  target_audience: {
    age_range: string;
    gender: string;
    persona: string;
  };
  platforms: string[];
  budget: number;
  brand_tone: string[];
  deliverables: {
    copy_variants: number;
    image_assets: number;
    short_video_assets: number;
    ads_strategy: number;
  };
  mandatory_elements: string[];
  forbidden_elements: string[];
  deadline: string;
};

export type ChatIntent =
  | "create_campaign"
  | "run_campaign"
  | "list_campaigns"
  | "list_tasks"
  | "list_references"
  | "list_review_queue"
  | "list_validation_results"
  | "delete_reference"
  | "approve_review"
  | "regenerate_asset"
  | "confirm_pending_action"
  | "cancel_pending_action"
  | "modify_work_order"
  | "unknown";

export type IntentDetectionResult = {
  intent: ChatIntent;
  slots: {
    campaignName?: string;
    budget?: number;
    campaignId?: string;
    referenceId?: string;
    reviewId?: string;
    assetId?: string;
    confirmationCode?: string;
    modificationInstruction?: string;
  };
};

export type ChatActionResult = {
  ok: boolean;
  detail?: string;
  campaign_id?: string;
  status?: string;
  campaigns?: Array<{ campaign_id: string; status: string; created_at: string; name: string }>;
  tasks?: Array<{ task_id: string; task_type: string; status: string; priority: number }>;
  references?: Array<{
    reference_id: string;
    file_name: string;
    file_type: string;
    file_size: number;
    uploaded_at: string;
  }>;
  reviewItems?: Array<{
    review_id: string;
    campaign_id: string;
    asset_id: string;
    score: number;
    status: string;
  }>;
  validationResults?: Array<{
    validation_id: string;
    asset_id: string;
    validator: string;
    score: number;
    result: string;
  }>;
  workOrder?: CampaignBriefDraft;
  missing_fields?: string[];
  confidence?: number;
};

export type ChatExecuteRequest = {
  message: string;
  locale?: SupportedLocale;
  context?: ChatContext;
};

export type ChatExecuteResponse = {
  reply: string;
  intent: ChatIntent;
  actionResult: ChatActionResult;
  context: ChatContext;
  followUp: string[];
};
