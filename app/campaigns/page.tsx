"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import {
  attachKnowledgeItemToCampaign,
  getCampaignBundle,
  generateSingleAsset,
  createCampaign,
  deleteCampaign,
  deleteKnowledgeItem,
  deleteCampaignReference,
  listCampaigns,
  listKnowledgeItems,
  listCampaignReferences,
  listReviewQueue,
  regenerateAsset,
  runCampaign,
  updateCampaign,
  updateCampaignReference,
  updateKnowledgeItem,
  uploadCampaignReference,
  uploadKnowledgeItem,
  type CampaignBrief,
  type CampaignReferenceRecord,
  type KnowledgeItemRecord,
  type CampaignRecord,
  type CampaignStatus,
  type ReviewItem,
  type ReviewStatus,
} from "@/lib/api/campaigns";
import { ReviewAssetPreviewModal } from "@/components/review/review-asset-preview-modal";
import { useI18n } from "@/lib/i18n/context";
import { formatCurrencyUSD, formatDateTime } from "@/lib/i18n/format";
import type { TranslationKey } from "@/lib/i18n/translations";

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value, delayMs]);

  return debounced;
}

type UiCampaign = {
  id: string;
  name: string;
  platforms: string;
  status: CampaignStatus;
  budget: string;
  createdAt: string;
};

type EditAssetType = "copy" | "image" | "video";
type EditAssetRow = { id: string; name: string; type: EditAssetType; content: string; status: ReviewStatus; rejectReason?: string };
type PendingRunWorkOrder = {
  mode: "run" | "save-and-rerun";
  campaignId: string;
  campaignName: string;
  productName: string;
  objective: string;
  platforms: string[];
  industryCategory: string;
  projectDescription: string;
  audiencePersona: string;
  brandTone: string[];
  budget: number;
  deliverables: {
    copyVariants: number;
    imageAssets: number;
    shortVideoAssets: number;
    adsStrategy: number;
  };
};
type CreateCampaignDraft = {
  campaignName: string;
  productName: string;
  objective: string;
  industryCategory: string;
  projectDescription: string;
  audiencePersona: string;
  platforms: string[];
  budget: number;
  brandTone: string[];
  deliverables: {
    copyVariants: number;
    imageAssets: number;
    shortVideoAssets: number;
    adsStrategy: number;
  };
  deadline: string;
  referenceFiles: File[];
  knowledgeItemIds: string[];
};

const fallbackCampaigns: UiCampaign[] = [
  {
    id: "fallback-1",
    name: "Q2 B2B Lead Magnet",
    platforms: "LinkedIn",
    status: "running",
    budget: "12400",
    createdAt: "N/A",
  },
  {
    id: "fallback-2",
    name: "UGC Summer Push",
    platforms: "Instagram",
    status: "running",
    budget: "9200",
    createdAt: "N/A",
  },
  {
    id: "fallback-3",
    name: "Global Webinar Funnel",
    platforms: "YouTube",
    status: "failed",
    budget: "18100",
    createdAt: "N/A",
  },
];

function statusClasses(status: CampaignStatus) {
  if (status === "draft") return "bg-emerald-100 text-emerald-700";
  if (status === "running") return "bg-emerald-100 text-emerald-700";
  if (status === "completed") return "bg-blue-100 text-blue-700";
  return "bg-rose-100 text-rose-700";
}

function statusKey(status: CampaignStatus): TranslationKey {
  if (status === "draft") return "status.running";
  if (status === "running") return "status.running";
  if (status === "completed") return "status.completed";
  return "status.failed";
}

function reviewStatusBadge(status: ReviewStatus, t: ReturnType<typeof useI18n>["t"]) {
  if (status === "approved") return { label: t("review.status.passed"), className: "bg-emerald-100 text-emerald-700" };
  if (status === "rejected") return { label: t("review.status.rejected"), className: "bg-rose-100 text-rose-700" };
  return { label: t("review.status.inReview"), className: "bg-amber-100 text-amber-700" };
}

function editAssetTypeLabel(type: EditAssetType, t: ReturnType<typeof useI18n>["t"]) {
  if (type === "copy") return t("assets.type.copy");
  if (type === "image") return t("assets.type.image");
  return t("assets.type.video");
}

function clampDeliverableCount(value: string, max: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.min(max, Math.max(0, Math.floor(parsed)));
}

function toUiCampaign(record: CampaignRecord): UiCampaign {
  return {
    id: record.campaign_id,
    name: record.brief.campaign_name,
    platforms: record.brief.platforms.join(", "),
    status: record.status === "draft" ? "running" : record.status,
    budget: String(record.brief.budget),
    createdAt: record.created_at,
  };
}

function getBriefString(brief: CampaignBrief, snakeKey: keyof CampaignBrief, camelKey: string): string {
  const value = brief[snakeKey] ?? (brief as unknown as Record<string, unknown>)[camelKey];
  return typeof value === "string" ? value : "";
}

export default function CampaignCenterPage() {
  const { t, locale } = useI18n();
  const actorToken = typeof document === "undefined" ? "" : getCookieValue("chat_actor_token");
  const actorRole = readActorRoleFromToken(actorToken);
  const canUsePrivilegedTransitions = actorRole === "admin";
  const [campaigns, setCampaigns] = useState<UiCampaign[]>([]);
  const [campaignRecords, setCampaignRecords] = useState<CampaignRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiMode, setApiMode] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [campaignSearchDraft, setCampaignSearchDraft] = useState("");
  const [campaignPlatformDraft, setCampaignPlatformDraft] = useState("");
  const [campaignStatusDraft, setCampaignStatusDraft] = useState("");
  const [campaignCreatedFromDraft, setCampaignCreatedFromDraft] = useState("");
  const [campaignCreatedToDraft, setCampaignCreatedToDraft] = useState("");
  const [campaignSearch, setCampaignSearch] = useState("");
  const [campaignPlatformFilter, setCampaignPlatformFilter] = useState("");
  const [campaignStatusFilter, setCampaignStatusFilter] = useState("");
  const [campaignCreatedFromFilter, setCampaignCreatedFromFilter] = useState("");
  const [campaignCreatedToFilter, setCampaignCreatedToFilter] = useState("");
  const [selectedDeliverables, setSelectedDeliverables] = useState<string[]>([]);
  const [editTarget, setEditTarget] = useState<CampaignRecord | null>(null);
  const [editAssets, setEditAssets] = useState<EditAssetRow[]>([]);
  const [editAssetsLoading, setEditAssetsLoading] = useState(false);
  const [regenerateTarget, setRegenerateTarget] = useState<EditAssetRow | null>(null);
  const [regenerateReason, setRegenerateReason] = useState("");
  const [regenerateInstruction, setRegenerateInstruction] = useState("");
  const [regenerateBusy, setRegenerateBusy] = useState(false);
  const [previewAssetId, setPreviewAssetId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({
    campaignName: "",
    productName: "",
    objective: "awareness",
    language: "zh-TW",
    industryCategory: "",
    projectDescription: "",
    audiencePersona: "",
    platforms: "社群平台",
    budget: "",
    brandTone: "professional, clear",
    copyVariants: "",
    imageAssets: "",
    shortVideoAssets: "",
    adsStrategy: false,
  });
  const [createReferenceFiles, setCreateReferenceFiles] = useState<File[]>([]);
  const [createReferenceInputKey, setCreateReferenceInputKey] = useState(0);
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItemRecord[]>([]);
  const [selectedKnowledgeItemIds, setSelectedKnowledgeItemIds] = useState<string[]>([]);
  const [selectedKnowledgeFolderNames, setSelectedKnowledgeFolderNames] = useState<string[]>([]);
  const [expandedKnowledgeFolderNames, setExpandedKnowledgeFolderNames] = useState<string[]>([]);
  const [expandedKnowledgeListFolderNames, setExpandedKnowledgeListFolderNames] = useState<string[]>([]);
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null);
  const [knowledgeTitle, setKnowledgeTitle] = useState("");
  const [knowledgeDescription, setKnowledgeDescription] = useState("");
  const [knowledgeCategory, setKnowledgeCategory] = useState("General");
  const [knowledgeSearchDraft, setKnowledgeSearchDraft] = useState("");
  const [knowledgeCategoryDraft, setKnowledgeCategoryDraft] = useState("");
  const [knowledgeSearch, setKnowledgeSearch] = useState("");
  const [knowledgeCategoryFilter, setKnowledgeCategoryFilter] = useState("");
  const [knowledgeBusy, setKnowledgeBusy] = useState(false);
  const [knowledgeMessage, setKnowledgeMessage] = useState<string | null>(null);
  const [knowledgeInputKey, setKnowledgeInputKey] = useState(0);
  const [folders, setFolders] = useState<string[]>([]);
  const [campaignForm, setCampaignForm] = useState({
    campaignName: "",
    productName: "",
    objective: "awareness",
    industryCategory: "",
    projectDescription: "",
    audiencePersona: "",
    platforms: "社群平台",
    budget: "",
    brandTone: "",
    copyVariants: "",
    imageAssets: "",
    shortVideoAssets: "",
    deadline: "",
  });
  const [selectedReferenceCampaignId, setSelectedReferenceCampaignId] = useState("");
  const [manualAssetType, setManualAssetType] = useState<EditAssetType>("image");
  const [manualAssetPrompt, setManualAssetPrompt] = useState("");
  const [references, setReferences] = useState<CampaignReferenceRecord[]>([]);
  const [referencesLoading, setReferencesLoading] = useState(false);
  const [referencesBusy, setReferencesBusy] = useState(false);
  const [referencesMessage, setReferencesMessage] = useState<string | null>(null);
  const [expandedReferenceFolderNames, setExpandedReferenceFolderNames] = useState<string[]>([]);
  const [pendingCreateDraft, setPendingCreateDraft] = useState<CreateCampaignDraft | null>(null);
  const [creatingCampaign, setCreatingCampaign] = useState(false);
  const [pendingRunWorkOrder, setPendingRunWorkOrder] = useState<PendingRunWorkOrder | null>(null);
  const [runningCampaign, setRunningCampaign] = useState(false);

  useEffect(() => {
    if (!editTarget) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" && event.key !== "Esc" && event.code !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();

      if (previewAssetId) {
        setPreviewAssetId(null);
        return;
      }
      if (regenerateTarget) {
        if (!regenerateBusy) setRegenerateTarget(null);
        return;
      }
      if (pendingRunWorkOrder) {
        if (!runningCampaign) setPendingRunWorkOrder(null);
        return;
      }
      if (pendingCreateDraft) {
        if (!creatingCampaign) setPendingCreateDraft(null);
        return;
      }
      setEditTarget(null);
    }

    document.addEventListener("keydown", handleKeyDown, { capture: true });
    return () => document.removeEventListener("keydown", handleKeyDown, { capture: true });
  }, [creatingCampaign, editTarget, pendingCreateDraft, pendingRunWorkOrder, previewAssetId, regenerateBusy, regenerateTarget, runningCampaign]);

  useEffect(() => {
    let mounted = true;

    async function loadCampaigns() {
      setLoading(true);
      try {
        const rows = await listCampaigns();
        if (!mounted) return;
        setCampaignRecords(rows);
        setCampaigns(rows.map(toUiCampaign));
        setApiMode(true);
        setMessage(null);
      } catch {
        if (!mounted) return;
        setCampaigns(fallbackCampaigns);
        setCampaignRecords([]);
        setApiMode(false);
        setMessage(t("campaigns.fallbackMessage"));
      } finally {
        if (mounted) setLoading(false);
      }
    }

    loadCampaigns();
    return () => {
      mounted = false;
    };
  }, [t]);

  useEffect(() => {
    let mounted = true;

    async function loadKnowledgeItems() {
      try {
        const rows = await listKnowledgeItems();
        if (!mounted) return;
        setKnowledgeItems(rows);
      } catch {
        if (!mounted) return;
        setKnowledgeItems([]);
      }
    }

    async function loadFolders() {
      try {
        const res = await fetch("/api/folders");
        if (res.ok) {
          const data = (await res.json()) as { items: { name: string }[] };
          if (mounted) setFolders(data.items.map((f) => f.name));
        }
      } catch {
        // folders not critical
      }
    }

    void loadKnowledgeItems();
    void loadFolders();
    return () => {
      mounted = false;
    };
  }, []);

  const isFallback = useMemo(() => !apiMode, [apiMode]);
  const realCampaigns = useMemo(() => campaigns.filter((item) => !item.id.startsWith("fallback")), [campaigns]);
  const campaignPlatformOptions = useMemo(() => {
    const values = campaignRecords.flatMap((record) => record.brief.platforms);
    return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b));
  }, [campaignRecords]);
  const filteredCampaigns = useMemo(() => {
    const query = campaignSearch.trim().toLowerCase();
    const fromMs = campaignCreatedFromFilter ? new Date(campaignCreatedFromFilter).getTime() : null;
    const toMs = campaignCreatedToFilter ? new Date(campaignCreatedToFilter).getTime() + 86_399_999 : null;
    return campaigns.filter((campaign) => {
      const record = campaignRecords.find((item) => item.campaign_id === campaign.id);
      if (query && !`${campaign.name} ${campaign.id}`.toLowerCase().includes(query)) return false;
      if (campaignPlatformFilter && !campaign.platforms.toLowerCase().includes(campaignPlatformFilter.toLowerCase())) return false;
      if (campaignStatusFilter && campaign.status !== campaignStatusFilter) return false;
      if (record) {
        const createdMs = new Date(record.created_at).getTime();
        if (fromMs !== null && createdMs < fromMs) return false;
        if (toMs !== null && createdMs > toMs) return false;
      }
      return true;
    });
  }, [campaignCreatedFromFilter, campaignCreatedToFilter, campaignPlatformFilter, campaignRecords, campaigns, campaignSearch, campaignStatusFilter]);
  const activeCampaignId = useMemo(() => {
    if (realCampaigns.length === 0) return "";
    if (selectedReferenceCampaignId && realCampaigns.some((item) => item.id === selectedReferenceCampaignId)) {
      return selectedReferenceCampaignId;
    }
    return realCampaigns[0].id;
  }, [realCampaigns, selectedReferenceCampaignId]);

  const knowledgeCategories = useMemo(() => {
    const categories = knowledgeItems
      .map((item) => getKnowledgeFolder(item))
      .filter(Boolean);
    return Array.from(new Set(categories)).sort((a, b) => a.localeCompare(b));
  }, [knowledgeItems]);

  const filteredKnowledgeItems = useMemo(() => {
    const query = knowledgeSearch.trim().toLowerCase();
    return knowledgeItems.filter((item) => {
      const category = getKnowledgeFolder(item);
      if (knowledgeCategoryFilter && category !== knowledgeCategoryFilter) return false;
      if (!query) return true;
      const fileName = String(item.metadata.file_name ?? "");
      return `${item.title} ${item.description} ${fileName} ${category}`.toLowerCase().includes(query);
    });
  }, [knowledgeCategoryFilter, knowledgeItems, knowledgeSearch]);

  const groupedKnowledgeItems = useMemo(() => {
    return filteredKnowledgeItems.reduce<Record<string, KnowledgeItemRecord[]>>((groups, item) => {
      const category = getKnowledgeFolder(item);
      groups[category] = [...(groups[category] ?? []), item];
      return groups;
    }, {});
  }, [filteredKnowledgeItems]);

  const selectedReferenceItemIds = useMemo(() => {
    const ids = new Set(selectedKnowledgeItemIds.filter((itemId) => {
      const item = knowledgeItems.find((candidate) => candidate.item_id === itemId);
      return item ? isKnowledgeItemAttachable(item) : false;
    }));
    for (const item of knowledgeItems) {
      if (isKnowledgeItemAttachable(item) && selectedKnowledgeFolderNames.includes(getKnowledgeFolder(item))) {
        ids.add(item.item_id);
      }
    }
    return Array.from(ids);
  }, [knowledgeItems, selectedKnowledgeFolderNames, selectedKnowledgeItemIds]);

  const groupedReferences = useMemo(() => {
    return references.reduce<Record<string, CampaignReferenceRecord[]>>((groups, item) => {
      const folder = getReferenceFolder(item);
      groups[folder] = [...(groups[folder] ?? []), item];
      return groups;
    }, {});
  }, [references]);

  useEffect(() => {
    let mounted = true;

    async function loadReferences() {
      if (!activeCampaignId) {
        setReferences([]);
        return;
      }

      setReferencesLoading(true);
      try {
        const rows = await listCampaignReferences(activeCampaignId);
        if (!mounted) return;
        setReferences(rows);
        setReferencesMessage(null);
      } catch {
        if (!mounted) return;
        setReferences([]);
        setReferencesMessage(t("campaigns.references.uploadFailed"));
      } finally {
        if (mounted) setReferencesLoading(false);
      }
    }

    void loadReferences();
    return () => {
      mounted = false;
    };
  }, [activeCampaignId, t]);

  async function handleCreateSample() {
    try {
      const created = await createCampaign({
        campaign_name: "Spring Coffee Conversion",
        product_name: "Yirgacheffe Hand Drip",
        objective: "conversion",
        target_audience: {
          age_range: "25-35",
          gender: "all",
          persona: "Style-conscious coffee lovers",
        },
        platforms: ["facebook", "instagram"],
        budget: 100000,
        brand_tone: ["premium", "minimal", "clean"],
        deliverables: {
          copy_variants: 3,
          image_assets: 2,
          short_video_assets: 1,
          ads_strategy: 1,
        },
        mandatory_elements: ["Brand Logo", "Product Hero"],
        forbidden_elements: ["Overclaim", "Off-brand tone"],
        deadline: new Date(Date.now() + 86_400_000).toISOString(),
      });

      setMessage(t("campaigns.created", { id: created.campaign_id }));

      const rows = await listCampaigns();
      setCampaignRecords(rows);
      setCampaigns(rows.map(toUiCampaign));
      setApiMode(true);
    } catch {
      setMessage(t("campaigns.createFailed"));
    }
  }

  async function handleCreateFromForm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const campaignName = campaignForm.campaignName.trim();
    const productName = campaignForm.productName.trim();
    const objective = campaignForm.objective.trim();
    const industryCategory = campaignForm.industryCategory.trim();
    const projectDescription = campaignForm.projectDescription.trim();
    const adsSelected = selectedDeliverables.includes("ads");
    const budget = campaignForm.budget.trim() ? Number(campaignForm.budget.replace(/,/g, "")) : 0;
    const copyVariants = clampDeliverableCount(campaignForm.copyVariants, 7);
    const imageAssets = clampDeliverableCount(campaignForm.imageAssets, 5);
    const shortVideoAssets = clampDeliverableCount(campaignForm.shortVideoAssets, 3);
    const adsStrategy = adsSelected ? 1 : 0;
    const platforms = [campaignForm.platforms.trim() || "社群平台"];
    const brandTone = campaignForm.brandTone
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const deadline = campaignForm.deadline ? new Date(campaignForm.deadline).toISOString() : new Date(Date.now() + 7 * 86_400_000).toISOString();

    const missingFields: string[] = [];
    if (!campaignName) missingFields.push("專案名稱");
    if (!productName) missingFields.push("品牌/產品名稱");
    if (!objective) missingFields.push("活動目標");
    if (!industryCategory) missingFields.push("產業類別");
    if (!projectDescription) missingFields.push("專案需求");
    if (adsSelected && (!Number.isFinite(budget) || budget <= 0)) missingFields.push("美金預算（勾選投放策略時必填）");

    if (missingFields.length > 0) {
      const warning = `請先填寫以下必填欄位：\n${missingFields.map((field) => `・${field}`).join("\n")}`;
      window.alert(warning);
      setMessage(warning);
      return;
    }

    setPendingCreateDraft({
      campaignName,
      productName,
      objective,
      industryCategory,
      projectDescription,
      audiencePersona: campaignForm.audiencePersona.trim() || "所有受眾",
      platforms,
      budget,
      brandTone,
      deliverables: {
        copyVariants,
        imageAssets,
        shortVideoAssets,
        adsStrategy,
      },
      deadline,
      referenceFiles: createReferenceFiles,
      knowledgeItemIds: selectedReferenceItemIds,
    });
  }

  async function handleConfirmCreateCampaign() {
    if (!pendingCreateDraft) return;

    const draft = pendingCreateDraft;
    setCreatingCampaign(true);
    try {
      const created = await createCampaign({
        campaign_name: draft.campaignName,
        product_name: draft.productName,
        description: draft.projectDescription,
        objective: draft.objective,
        industry_category: draft.industryCategory,
        project_description: draft.projectDescription,
        target_audience: {
          age_range: "all",
          gender: "all",
          persona: draft.audiencePersona,
        },
        platforms: draft.platforms,
        budget: draft.budget,
        brand_tone: draft.brandTone,
        deliverables: {
          copy_variants: draft.deliverables.copyVariants,
          image_assets: draft.deliverables.imageAssets,
          short_video_assets: draft.deliverables.shortVideoAssets,
          ads_strategy: draft.deliverables.adsStrategy,
        },
        mandatory_elements: [],
        forbidden_elements: [],
        deadline: draft.deadline,
      });

      let createdMessage = t("campaigns.created", { id: created.campaign_id });

      const selectedKnowledgeItems = knowledgeItems.filter((item) => draft.knowledgeItemIds.includes(item.item_id));
      if (draft.referenceFiles.length > 0 || selectedKnowledgeItems.length > 0) {
        const uploadResults = await Promise.allSettled([
          ...selectedKnowledgeItems.map((item) => attachKnowledgeItemToCampaign(created.campaign_id, item)),
          ...draft.referenceFiles.map((file) => uploadCampaignReference(created.campaign_id, file, "admin")),
        ]);
        
      }

      await runCampaign(created.campaign_id);
      createdMessage = `${createdMessage} ${t("campaigns.started", { id: created.campaign_id })}`;

      setCampaignForm((prev) => ({ ...prev, campaignName: "", productName: "", industryCategory: "", projectDescription: "", audiencePersona: "", budget: "", brandTone: "", copyVariants: "", imageAssets: "", shortVideoAssets: "" }));
      setSelectedDeliverables([]);
      setCreateReferenceFiles([]);
      setSelectedKnowledgeItemIds([]);
      setSelectedKnowledgeFolderNames([]);
      setExpandedKnowledgeFolderNames([]);
      setCreateReferenceInputKey((prev) => prev + 1);
      setPendingCreateDraft(null);
      setSelectedReferenceCampaignId(created.campaign_id);
      const rows = await listCampaigns();
      setCampaignRecords(rows);
      setCampaigns(rows.map(toUiCampaign));
      setApiMode(true);
      if (draft.referenceFiles.length > 0 || selectedKnowledgeItems.length > 0) {
        try {
          const uploadedReferences = await listCampaignReferences(created.campaign_id);
          setReferences(uploadedReferences);
          setReferencesMessage(t("campaigns.references.createdCampaignSelected"));
        } catch {
          setReferencesMessage(null);
        }
      }
      setMessage(createdMessage);
    } catch {
      setMessage(t("campaigns.createFailed"));
    } finally {
      setCreatingCampaign(false);
    }
  }

  function openRunWorkOrder(campaignId: string) {
    const record = campaignRecords.find((item) => item.campaign_id === campaignId);
    if (!record) return;
    setPendingRunWorkOrder({
      mode: "run",
      campaignId,
      campaignName: record.brief.campaign_name,
      productName: record.brief.product_name,
      objective: record.brief.objective,
      platforms: record.brief.platforms,
      industryCategory: getBriefString(record.brief, "industry_category", "industryCategory"),
      projectDescription: getBriefString(record.brief, "project_description", "projectDescription") || (record.brief as CampaignBrief & { description?: string }).description || "",
      audiencePersona: record.brief.target_audience.persona,
      brandTone: record.brief.brand_tone,
      budget: Number(record.brief.budget || 0),
      deliverables: {
        copyVariants: Number(record.brief.deliverables.copy_variants || 0),
        imageAssets: Number(record.brief.deliverables.image_assets || 0),
        shortVideoAssets: Number(record.brief.deliverables.short_video_assets || 0),
        adsStrategy: Number(record.brief.deliverables.ads_strategy || 0),
      },
    });
  }

  function openSaveAndRerunWorkOrder() {
    if (!editTarget) return;
    setPendingRunWorkOrder({
      mode: "save-and-rerun",
      campaignId: editTarget.campaign_id,
      campaignName: editForm.campaignName.trim() || editTarget.brief.campaign_name,
      productName: editForm.productName.trim() || editTarget.brief.product_name,
      objective: editForm.objective.trim() || "awareness",
      platforms: [editForm.platforms.trim() || "社群平台"],
      industryCategory: editForm.industryCategory.trim(),
      projectDescription: editForm.projectDescription.trim(),
      audiencePersona: editForm.audiencePersona.trim() || "所有受眾",
      brandTone: editForm.brandTone.split(",").map((item) => item.trim()).filter(Boolean),
      budget: editForm.budget.trim() ? Number(editForm.budget.replace(/,/g, "")) : 0,
      deliverables: {
        copyVariants: clampDeliverableCount(editForm.copyVariants, 7),
        imageAssets: clampDeliverableCount(editForm.imageAssets, 5),
        shortVideoAssets: clampDeliverableCount(editForm.shortVideoAssets, 3),
        adsStrategy: editForm.adsStrategy ? 1 : 0,
      },
    });
  }

  async function executeRun(campaignId: string) {
    try {
      setRunningCampaign(true);
      await runCampaign(campaignId);
      const rows = await listCampaigns();
      setCampaignRecords(rows);
      setCampaigns(rows.map(toUiCampaign));
      setMessage(t("campaigns.started", { id: campaignId }));
    } catch {
      setMessage(t("campaigns.runFailed"));
    } finally {
      setRunningCampaign(false);
    }
  }

  async function handleConfirmRunWorkOrder() {
    if (!pendingRunWorkOrder) return;
    const order = pendingRunWorkOrder;
    if (order.mode === "save-and-rerun") {
      setRunningCampaign(true);
      try {
        await handleSaveCampaignEdit(true);
      } finally {
        setRunningCampaign(false);
      }
    } else {
      await executeRun(order.campaignId);
    }
    setPendingRunWorkOrder(null);
  }

  function applyCampaignFilters() {
    setCampaignSearch(campaignSearchDraft);
    setCampaignPlatformFilter(campaignPlatformDraft);
    setCampaignStatusFilter(campaignStatusDraft);
    setCampaignCreatedFromFilter(campaignCreatedFromDraft);
    setCampaignCreatedToFilter(campaignCreatedToDraft);
  }

  function resetCampaignFilters() {
    setCampaignSearchDraft("");
    setCampaignPlatformDraft("");
    setCampaignStatusDraft("");
    setCampaignCreatedFromDraft("");
    setCampaignCreatedToDraft("");
    setCampaignSearch("");
    setCampaignPlatformFilter("");
    setCampaignStatusFilter("");
    setCampaignCreatedFromFilter("");
    setCampaignCreatedToFilter("");
  }

  function openEditCampaign(campaignId: string) {
    const record = campaignRecords.find((item) => item.campaign_id === campaignId);
    if (!record) return;
    const extraBrief = record.brief as CampaignBrief & { description?: string };
    setEditTarget(record);
    setEditForm({
      campaignName: record.brief.campaign_name,
      productName: record.brief.product_name,
      objective: record.brief.objective,
      language: record.brief.language || "zh-TW",
      industryCategory: getBriefString(record.brief, "industry_category", "industryCategory"),
      projectDescription: getBriefString(record.brief, "project_description", "projectDescription") || extraBrief.description || "",
      audiencePersona: record.brief.target_audience.persona,
      platforms: normalizeCampaignPlatform(record.brief.platforms[0]),
      budget: formatNumberInput(record.brief.budget),
      brandTone: record.brief.brand_tone.join(", "),
      copyVariants: String(record.brief.deliverables.copy_variants ?? 0),
      imageAssets: String(record.brief.deliverables.image_assets ?? 0),
      shortVideoAssets: String(record.brief.deliverables.short_video_assets ?? 0),
      adsStrategy: Boolean(record.brief.deliverables.ads_strategy),
    });
    void loadEditAssets(campaignId);
  }

  async function loadEditAssets(campaignId: string) {
    setEditAssets([]);
    setEditAssetsLoading(true);
    try {
      const [bundle, reviewQueue] = await Promise.all([
        getCampaignBundle(campaignId),
        listReviewQueue({ campaignId, pageSize: 500 }),
      ]);
      const reviewByAssetId = new Map(reviewQueue.items.map((item) => [item.asset_id, item]));
      const toStatus = (assetId: string) => reviewByAssetId.get(assetId)?.status ?? "review_pending";
      const toRejectReason = (assetId: string) => getReviewRejectReason(reviewByAssetId.get(assetId));
      setEditAssets([
        ...bundle.copy_assets.map((item, index) => ({ id: item.variant_id, name: item.asset_name?.trim() || `Copy ${index + 1}`, type: "copy" as const, content: item.text, status: toStatus(item.variant_id), rejectReason: toRejectReason(item.variant_id) })),
        ...bundle.image_assets.map((item, index) => ({ id: item.asset_id, name: item.asset_name?.trim() || `Image ${index + 1}`, type: "image" as const, content: item.url, status: toStatus(item.asset_id), rejectReason: toRejectReason(item.asset_id) })),
        ...bundle.video_assets.map((item, index) => ({ id: item.asset_id, name: item.asset_name?.trim() || `Video ${index + 1}`, type: "video" as const, content: item.url, status: toStatus(item.asset_id), rejectReason: toRejectReason(item.asset_id) })),
      ]);
    } catch {
      setEditAssets([]);
    } finally {
      setEditAssetsLoading(false);
    }
  }

  function openRegenerateWorkOrder(asset: EditAssetRow) {
    setRegenerateTarget(asset);
    setRegenerateReason(asset.rejectReason || "");
    setRegenerateInstruction("");
  }

  async function handleRegenerateSubmit() {
    if (!editTarget || !regenerateTarget) return;
    const reason = regenerateReason.trim();
    if (!reason) {
      setMessage("請先填寫退件原因或重新生成要求。");
      return;
    }
    setRegenerateBusy(true);
    try {
      await regenerateAsset(regenerateTarget.id, {
        reject_reason: reason,
        user_instruction: regenerateInstruction.trim(),
        operator: "operator",
      });
      setMessage("重新生成工單已送出，新的素材會進入審核。");
      setRegenerateReason("");
      setRegenerateInstruction("");
      await loadEditAssets(editTarget.campaign_id);
      const rows = await listCampaigns();
      setCampaignRecords(rows);
      setCampaigns(rows.map(toUiCampaign));
      setApiMode(true);
    } catch {
      setMessage("重新生成失敗，請稍後再試。");
    } finally {
      setRegenerateBusy(false);
      setRegenerateTarget(null);
    }
  }

  function downloadEditAsset(asset: EditAssetRow) {
    if (asset.type === "copy") {
      const blob = new Blob([asset.content || ""], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${asset.id}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      return;
    }
    if (!asset.content) return;
    const link = document.createElement("a");
    link.href = asset.content;
    link.download = asset.id;
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  async function handleSaveCampaignEdit(rerunAfterSave = false) {
    if (!editTarget) return;
    const updatedBrief = {
      ...editTarget.brief,
      campaign_name: editForm.campaignName.trim() || editTarget.brief.campaign_name,
      product_name: editForm.productName.trim() || editTarget.brief.product_name,
      description: editForm.projectDescription.trim(),
      objective: editForm.objective.trim() || "awareness",
      language: editForm.language,
      industry_category: editForm.industryCategory.trim(),
      project_description: editForm.projectDescription.trim(),
      target_audience: {
        age_range: "all",
        gender: "all",
        persona: editForm.audiencePersona.trim() || "所有受眾",
      },
      platforms: [editForm.platforms.trim() || "社群平台"],
      budget: editForm.budget.trim() ? Number(editForm.budget.replace(/,/g, "")) : 0,
      brand_tone: editForm.brandTone.split(",").map((item) => item.trim()).filter(Boolean),
      deliverables: {
        copy_variants: clampDeliverableCount(editForm.copyVariants, 7),
        image_assets: clampDeliverableCount(editForm.imageAssets, 5),
        short_video_assets: clampDeliverableCount(editForm.shortVideoAssets, 3),
        ads_strategy: editForm.adsStrategy ? 1 : 0,
      },
      mandatory_elements: [],
      forbidden_elements: [],
    };
    try {
      setMessage(rerunAfterSave ? "正在儲存並重新執行..." : "正在儲存活動...");
      await updateCampaign(editTarget.campaign_id, updatedBrief);
      if (rerunAfterSave) await runCampaign(editTarget.campaign_id);
      const rows = await listCampaigns();
      setCampaignRecords(rows);
      setCampaigns(rows.map(toUiCampaign));
      setEditTarget(null);
      setMessage(rerunAfterSave ? t("campaigns.started", { id: editTarget.campaign_id }) : t("campaigns.updated"));
    } catch {
      setMessage(t("campaigns.updateFailed"));
    }
  }

  async function handleDeleteCampaign(campaignId: string) {
    if (!window.confirm(t("campaigns.deleteConfirm"))) return;
    try {
      await deleteCampaign(campaignId);
      const rows = await listCampaigns();
      setCampaignRecords(rows);
      setCampaigns(rows.map(toUiCampaign));
      setMessage(t("campaigns.deleted"));
    } catch {
      setMessage(t("campaigns.deleteFailed"));
    }
  }

  async function handleGenerateSingleCampaignAsset() {
    if (!activeCampaignId || !manualAssetPrompt.trim()) return;
    setReferencesBusy(true);
    try {
      await generateSingleAsset({
        campaignId: activeCampaignId,
        assetType: manualAssetType,
        prompt: manualAssetPrompt.trim(),
      });
      setManualAssetPrompt("");
      setReferencesMessage(t("campaigns.references.assetGenerationQueued"));
    } catch {
      setReferencesMessage(t("campaigns.references.assetGenerationFailed"));
    } finally {
      setReferencesBusy(false);
    }
  }

  async function handleUploadKnowledgeItem() {
    if (!knowledgeFile) {
      setKnowledgeMessage(t("campaigns.knowledge.selectFileFirst"));
      return;
    }

    setKnowledgeBusy(true);
    try {
      await uploadKnowledgeItem(knowledgeFile, knowledgeTitle || knowledgeFile.name, knowledgeDescription, knowledgeCategory || "General");
      const rows = await listKnowledgeItems();
      setKnowledgeItems(rows);
      setKnowledgeFile(null);
      setKnowledgeTitle("");
      setKnowledgeDescription("");
      setKnowledgeCategory("General");
      setKnowledgeInputKey((prev) => prev + 1);
      setKnowledgeMessage(t("campaigns.knowledge.uploadSuccess"));
    } catch {
      setKnowledgeMessage(t("campaigns.knowledge.uploadFailed"));
    } finally {
      setKnowledgeBusy(false);
    }
  }

  async function handleDeleteKnowledgeItem(itemId: string) {
    setKnowledgeBusy(true);
    try {
      await deleteKnowledgeItem(itemId);
      setSelectedKnowledgeItemIds((prev) => prev.filter((id) => id !== itemId));
      const rows = await listKnowledgeItems();
      setKnowledgeItems(rows);
      setKnowledgeMessage(t("campaigns.knowledge.deleteSuccess"));
    } catch {
      setKnowledgeMessage(t("campaigns.knowledge.deleteFailed"));
    } finally {
      setKnowledgeBusy(false);
    }
  }

  async function handleMoveKnowledgeItem(itemId: string, newFolder: string) {
    setKnowledgeBusy(true);
    try {
      await updateKnowledgeItem(itemId, { category: newFolder });
      const rows = await listKnowledgeItems();
      setKnowledgeItems(rows);
      setKnowledgeMessage(t("knowledge.moveSuccess"));
    } catch {
      setKnowledgeMessage(t("knowledge.moveFailed"));
    } finally {
      setKnowledgeBusy(false);
    }
  }

  function toggleKnowledgeItem(itemId: string) {
    const item = knowledgeItems.find((candidate) => candidate.item_id === itemId);
    if (!item || !isKnowledgeItemAttachable(item)) return;
    setSelectedKnowledgeItemIds((prev) => (
      prev.includes(itemId) ? prev.filter((id) => id !== itemId) : [...prev, itemId]
    ));
  }

  function toggleKnowledgeFolder(folderName: string) {
    const folderItemIds = new Set(knowledgeItems.filter((item) => getKnowledgeFolder(item) === folderName && isKnowledgeItemAttachable(item)).map((item) => item.item_id));
    if (folderItemIds.size === 0) return;
    setSelectedKnowledgeFolderNames((prev) => (
      prev.includes(folderName) ? prev.filter((name) => name !== folderName) : [...prev, folderName]
    ));
    setSelectedKnowledgeItemIds((prev) => prev.filter((id) => !folderItemIds.has(id)));
  }

  function toggleKnowledgeFolderExpanded(folderName: string) {
    setExpandedKnowledgeFolderNames((prev) => (
      prev.includes(folderName) ? prev.filter((name) => name !== folderName) : [...prev, folderName]
    ));
  }

  function toggleKnowledgeListFolderExpanded(folderName: string) {
    setExpandedKnowledgeListFolderNames((prev) => (
      prev.includes(folderName) ? prev.filter((name) => name !== folderName) : [...prev, folderName]
    ));
  }

  function toggleReferenceFolderExpanded(folderName: string) {
    setExpandedReferenceFolderNames((prev) => (
      prev.includes(folderName) ? prev.filter((name) => name !== folderName) : [...prev, folderName]
    ));
  }

  function applyKnowledgeFilters() {
    setKnowledgeSearch(knowledgeSearchDraft);
    setKnowledgeCategoryFilter(knowledgeCategoryDraft);
  }

  async function handleDeleteReference(referenceId: string) {
    if (!activeCampaignId) return;

    setReferencesBusy(true);
    try {
      await deleteCampaignReference(activeCampaignId, referenceId);
      const rows = await listCampaignReferences(activeCampaignId);
      setReferences(rows);
      setReferencesMessage(t("campaigns.references.deleteSuccess"));
    } catch {
      setReferencesMessage(t("campaigns.references.deleteFailed"));
    } finally {
      setReferencesBusy(false);
    }
  }

  async function handleMoveReference(referenceId: string, newFolder: string) {
    if (!activeCampaignId) return;

    setReferencesBusy(true);
    try {
      await updateCampaignReference(activeCampaignId, referenceId, { folder: newFolder });
      const rows = await listCampaignReferences(activeCampaignId);
      setReferences(rows);
      setReferencesMessage(t("campaigns.references.moveSuccess"));
    } catch {
      setReferencesMessage(t("campaigns.references.moveFailed"));
    } finally {
      setReferencesBusy(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("campaigns.title")}</h1>
        <p className="text-sm text-slate-500">{t("campaigns.subtitle")}</p>
      </header>

      {message ? (
        <p className={`rounded-xl px-3 py-2 text-sm ${isFallback ? "bg-amber-50 text-amber-700" : "bg-blue-50 text-blue-700"}`}>
          {message}
        </p>
      ) : null}

      <form id="create-campaign" onSubmit={handleCreateFromForm} noValidate className="scroll-mt-24 space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div>
          <h2 className="text-sm font-semibold">{t("campaigns.form.title")}</h2>
          <p className="text-xs text-slate-500">{t("campaigns.form.subtitle")}</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 xl:max-w-3xl">
          <input
            value={campaignForm.campaignName}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, campaignName: event.target.value }))}
            aria-label={t("campaigns.form.campaignName")}
            placeholder={t("campaigns.form.campaignName")}
            required
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <input
            value={campaignForm.productName}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, productName: event.target.value }))}
            aria-label={t("campaigns.form.productName")}
            placeholder={t("campaigns.form.productName")}
            required
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <select
            value={campaignForm.objective}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, objective: event.target.value }))}
            aria-label={t("campaigns.form.objective")}
            required
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="awareness">品牌曝光</option>
            <option value="engagement">互動</option>
            <option value="conversion">導購</option>
          </select>
          <input
            value={campaignForm.industryCategory}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, industryCategory: event.target.value }))}
            aria-label="industryCategory"
            placeholder="產業別"
            required
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <select
            value={campaignForm.platforms}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, platforms: event.target.value }))}
            aria-label={t("campaigns.form.platforms")}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="社群平台">社群平台</option>
            <option value="廣告素材">廣告素材</option>
            <option value="網站版位">網站版位</option>
          </select>
          <input
            value={campaignForm.brandTone}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, brandTone: event.target.value }))}
            aria-label={t("campaigns.form.brandTone")}
            placeholder={t("campaigns.form.brandTone")}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <input type="number" min={0} max={7} value={campaignForm.copyVariants} onChange={(event) => setCampaignForm((prev) => ({ ...prev, copyVariants: event.target.value }))} aria-label="文案數量" placeholder="文案數量" className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" />
          <input type="number" min={0} max={5} value={campaignForm.imageAssets} onChange={(event) => setCampaignForm((prev) => ({ ...prev, imageAssets: event.target.value }))} aria-label="圖檔數量" placeholder="圖檔數量" className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" />
          <input type="number" min={0} max={3} value={campaignForm.shortVideoAssets} onChange={(event) => setCampaignForm((prev) => ({ ...prev, shortVideoAssets: event.target.value }))} aria-label="影片數量" placeholder="影片數量" className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" />
          <input
            value={campaignForm.budget}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, budget: formatNumberInput(event.target.value) }))}
            aria-label={t("campaigns.form.budget")}
            placeholder="美金預算（勾選投廣策略時必填）"
            required={selectedDeliverables.includes("ads")}
            inputMode="numeric"
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <label className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700">
            <input
              type="checkbox"
              checked={selectedDeliverables.includes("ads")}
              onChange={() => setSelectedDeliverables((prev) => prev.includes("ads") ? prev.filter((v) => v !== "ads") : [...prev, "ads"])}
            />
            投廣策略
          </label>
          <div className="hidden xl:block" aria-hidden />
          <input
            value={campaignForm.audiencePersona}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, audiencePersona: event.target.value }))}
            aria-label={t("campaigns.form.audience")}
            placeholder="受眾目標"
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 md:col-span-2"
          />
          <textarea
            value={campaignForm.projectDescription}
            onChange={(event) => setCampaignForm((prev) => ({ ...prev, projectDescription: event.target.value }))}
            aria-label="projectDescription"
            placeholder="專案需求描述"
            required
            rows={2}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 md:col-span-2"
          />
          <div className="space-y-1 md:col-span-2 xl:col-span-3">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-300" htmlFor="create-reference-files">
              {t("campaigns.form.referenceFiles")}
            </label>
            <input
              key={createReferenceInputKey}
              id="create-reference-files"
              type="file"
              multiple
              onChange={(event) => setCreateReferenceFiles(Array.from(event.target.files ?? []))}
              aria-label={t("campaigns.form.referenceFiles")}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <p className="text-xs text-slate-500">
              {createReferenceFiles.length > 0
                ? t("campaigns.form.referenceFilesSelected", { count: createReferenceFiles.length })
                : t("campaigns.form.referenceFilesHelp")}
            </p>
          </div>
          <div className="space-y-2 xl:col-span-3">
            <div className="flex items-center justify-between gap-3">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-300">
                {t("campaigns.form.referenceLibrary")}
              </label>
              <span className="text-xs text-slate-500">
                {t("campaigns.form.referenceLibrarySelected", { count: selectedReferenceItemIds.length })}
              </span>
            </div>
            <p className="text-xs text-slate-500">先勾選資料夾可套用該資料夾內全部素材；展開資料夾可改選特定檔案。</p>
            <div className="max-h-64 overflow-y-auto rounded-xl border border-slate-200 p-2 dark:border-slate-700">
              {knowledgeItems.length === 0 ? (
                <p className="px-2 py-3 text-xs text-slate-500">{t("campaigns.form.referenceLibraryEmpty")}</p>
              ) : Object.entries(groupedKnowledgeItems).length === 0 ? (
                <p className="px-2 py-3 text-xs text-slate-500">沒有符合篩選的內容資料庫素材。</p>
              ) : Object.entries(groupedKnowledgeItems).map(([folderName, items]) => {
                const folderSelected = selectedKnowledgeFolderNames.includes(folderName);
                const expanded = expandedKnowledgeFolderNames.includes(folderName);
                const selectedFileCount = items.filter((item) => isKnowledgeItemAttachable(item) && selectedKnowledgeItemIds.includes(item.item_id)).length;
                const attachableItems = items.filter(isKnowledgeItemAttachable);
                return (
                  <div key={folderName} className="rounded-lg border border-slate-200/70 p-2 dark:border-slate-800">
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => toggleKnowledgeFolderExpanded(folderName)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          toggleKnowledgeFolderExpanded(folderName);
                        }
                      }}
                      className="flex cursor-pointer items-center justify-between gap-2 rounded-md px-1 py-1 hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-xs">
                        <input
                          type="checkbox"
                          checked={folderSelected}
                          disabled={attachableItems.length === 0}
                          onClick={(event) => event.stopPropagation()}
                          onChange={() => toggleKnowledgeFolder(folderName)}
                        />
                        <span className="truncate font-semibold text-slate-800 dark:text-slate-100">📁 {folderName}</span>
                        <span className="shrink-0 text-slate-500">{items.length} 個檔案{attachableItems.length < items.length ? `，${t("campaigns.form.attachableCount", { count: attachableItems.length })}` : ""}{selectedFileCount > 0 && !folderSelected ? `，已選 ${selectedFileCount}` : ""}</span>
                      </label>
                      <span className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium dark:border-slate-700">
                        {expanded ? "收合" : "展開"}
                      </span>
                    </div>
                    {expanded ? (
                      <div className="mt-2 space-y-1 border-t border-slate-200 pt-2 dark:border-slate-800">
                        {items.map((item) => (
                          <label key={item.item_id} className={`flex items-start gap-2 rounded-lg px-2 py-1.5 text-xs ${isKnowledgeItemAttachable(item) ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800" : "cursor-not-allowed opacity-50"} ${folderSelected ? "opacity-60" : ""}`}>
                            <input
                              type="checkbox"
                              checked={folderSelected || selectedKnowledgeItemIds.includes(item.item_id)}
                              disabled={folderSelected || !isKnowledgeItemAttachable(item)}
                              onChange={() => toggleKnowledgeItem(item.item_id)}
                              className="mt-0.5"
                            />
                            <span>
                              <span className="block font-medium text-slate-800 dark:text-slate-100">{item.title}</span>
                              <span className="text-slate-500">{isKnowledgeItemAttachable(item) ? (item.description || String(item.metadata.file_name ?? item.item_id)) : t("campaigns.form.notAttachable")}</span>
                            </span>
                          </label>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <button type="submit" className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white dark:bg-slate-700">{t("campaigns.form.submit")}</button>
        </div>
      </form>

      {pendingCreateDraft ? (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4">
          <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl bg-white p-5 shadow-2xl dark:bg-slate-900">
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-3 dark:border-slate-800">
              <div>
                <h2 className="text-lg font-semibold">建立活動工單確認</h2>
              </div>
              <button
                type="button"
                onClick={() => setPendingCreateDraft(null)}
                disabled={creatingCampaign}
                className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium disabled:opacity-50 dark:border-slate-700"
              >
                關閉
              </button>
            </div>

            <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
              <ReviewField label="活動名稱" value={pendingCreateDraft.campaignName} />
              <ReviewField label="產品名稱" value={pendingCreateDraft.productName} />
              <ReviewField
                label="活動目標"
                value={pendingCreateDraft.objective === "conversion" ? "導購" : pendingCreateDraft.objective === "engagement" ? "互動" : "品牌曝光"}
              />
              <ReviewField label="投放平台" value={pendingCreateDraft.platforms.join(", ")} />
              <ReviewField label="產業類別" value={pendingCreateDraft.industryCategory} />
              <ReviewField label="目標受眾" value={pendingCreateDraft.audiencePersona} />
              <ReviewField label="品牌語氣" value={pendingCreateDraft.brandTone.length > 0 ? pendingCreateDraft.brandTone.join(", ") : "—"} />
              <ReviewField label="預算" value={pendingCreateDraft.budget > 0 ? formatCurrencyUSD(locale, pendingCreateDraft.budget) : "—"} />
              <ReviewField label="文案數量" value={String(pendingCreateDraft.deliverables.copyVariants)} />
              <ReviewField label="圖片數量" value={String(pendingCreateDraft.deliverables.imageAssets)} />
              <ReviewField label="影片數量" value={String(pendingCreateDraft.deliverables.shortVideoAssets)} />
              <ReviewField label="投廣策略" value={pendingCreateDraft.deliverables.adsStrategy > 0 ? "是" : "否"} />
              <ReviewField label="期限" value={formatDateTime(locale, pendingCreateDraft.deadline)} />
              <ReviewField label="上傳參考素材" value={pendingCreateDraft.referenceFiles.length > 0 ? `${pendingCreateDraft.referenceFiles.length} 個檔案` : "—"} />
              <div className="md:col-span-2">
                <p className="text-xs font-medium text-slate-500">專案需求描述</p>
                <p className="mt-1 whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-slate-800 dark:bg-slate-950 dark:text-slate-100">
                  {pendingCreateDraft.projectDescription}
                </p>
              </div>
              <div className="md:col-span-2">
                <p className="text-xs font-medium text-slate-500">內容資料庫</p>
                <p className="mt-1 rounded-xl bg-slate-50 p-3 text-slate-800 dark:bg-slate-950 dark:text-slate-100">
                  {pendingCreateDraft.knowledgeItemIds.length > 0
                    ? knowledgeItems
                        .filter((item) => pendingCreateDraft.knowledgeItemIds.includes(item.item_id))
                        .map((item) => item.title)
                        .join(", ")
                    : "—"}
                </p>
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-3 border-t border-slate-200 pt-4 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setPendingCreateDraft(null)}
                disabled={creatingCampaign}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
              >
                返回修改
              </button>
              <button
                type="button"
                onClick={() => { void handleConfirmCreateCampaign(); }}
                disabled={creatingCampaign}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-700"
              >
                {creatingCampaign ? "建立中..." : "確認工單內容"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {pendingRunWorkOrder ? (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4">
          <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl bg-white p-5 shadow-2xl dark:bg-slate-900">
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-3 dark:border-slate-800">
              <div>
                <h2 className="text-lg font-semibold">{pendingRunWorkOrder.mode === "save-and-rerun" ? "儲存並重新執行工單確認" : "執行活動工單確認"}</h2>
              </div>
              <button
                type="button"
                onClick={() => setPendingRunWorkOrder(null)}
                disabled={runningCampaign}
                className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium disabled:opacity-50 dark:border-slate-700"
              >
                關閉
              </button>
            </div>

            <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
              <ReviewField label="活動編號" value={pendingRunWorkOrder.campaignId} />
              <ReviewField label="執行類型" value={pendingRunWorkOrder.mode === "save-and-rerun" ? "儲存並重新執行" : "重新執行"} />
              <ReviewField label="活動名稱" value={pendingRunWorkOrder.campaignName} />
              <ReviewField label="產品名稱" value={pendingRunWorkOrder.productName} />
              <ReviewField
                label="活動目標"
                value={pendingRunWorkOrder.objective === "conversion" ? "導購" : pendingRunWorkOrder.objective === "engagement" ? "互動" : "品牌曝光"}
              />
              <ReviewField label="投放平台" value={pendingRunWorkOrder.platforms.join(", ")} />
              <ReviewField label="產業類別" value={pendingRunWorkOrder.industryCategory || "—"} />
              <ReviewField label="目標受眾" value={pendingRunWorkOrder.audiencePersona || "—"} />
              <ReviewField label="品牌語氣" value={pendingRunWorkOrder.brandTone.length > 0 ? pendingRunWorkOrder.brandTone.join(", ") : "—"} />
              <ReviewField label="預算" value={pendingRunWorkOrder.budget > 0 ? formatCurrencyUSD(locale, pendingRunWorkOrder.budget) : "—"} />
              <ReviewField label="文案數量" value={String(pendingRunWorkOrder.deliverables.copyVariants)} />
              <ReviewField label="圖片數量" value={String(pendingRunWorkOrder.deliverables.imageAssets)} />
              <ReviewField label="影片數量" value={String(pendingRunWorkOrder.deliverables.shortVideoAssets)} />
              <ReviewField label="投廣策略" value={pendingRunWorkOrder.deliverables.adsStrategy > 0 ? "是" : "否"} />
              <div className="md:col-span-2">
                <p className="text-xs font-medium text-slate-500">專案需求描述</p>
                <p className="mt-1 whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-slate-800 dark:bg-slate-950 dark:text-slate-100">
                  {pendingRunWorkOrder.projectDescription || "—"}
                </p>
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-3 border-t border-slate-200 pt-4 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setPendingRunWorkOrder(null)}
                disabled={runningCampaign}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
              >
                返回修改
              </button>
              <button
                type="button"
                onClick={() => { void handleConfirmRunWorkOrder(); }}
                disabled={runningCampaign}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-700"
              >
                {runningCampaign ? "執行中..." : "確認工單內容"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <header>
          <h2 className="text-sm font-semibold">{t("campaigns.knowledge.title")}</h2>
          <p className="text-xs text-slate-500">{t("campaigns.knowledge.subtitle")}</p>
        </header>

        {knowledgeMessage ? (
          <p className="rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-700">{knowledgeMessage}</p>
        ) : null}

        <div className="grid items-center gap-2 md:grid-cols-[minmax(120px,1fr)_minmax(120px,1fr)_minmax(110px,0.8fr)_minmax(170px,1fr)_auto]">
          <input
            value={knowledgeTitle}
            onChange={(event) => setKnowledgeTitle(event.target.value)}
            aria-label={t("campaigns.knowledge.itemTitle")}
            placeholder={t("campaigns.knowledge.itemTitle")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <input
            value={knowledgeDescription}
            onChange={(event) => setKnowledgeDescription(event.target.value)}
            aria-label={t("campaigns.knowledge.description")}
            placeholder={t("campaigns.knowledge.description")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <input
            value={knowledgeCategory}
            onChange={(event) => setKnowledgeCategory(event.target.value)}
            aria-label={t("campaigns.knowledge.category")}
            placeholder={t("campaigns.knowledge.category")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <input
            key={knowledgeInputKey}
            type="file"
            onChange={(event) => setKnowledgeFile(event.target.files?.[0] ?? null)}
            aria-label={t("campaigns.knowledge.chooseFile")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-xs file:font-medium dark:border-slate-700 dark:bg-slate-950 dark:file:bg-slate-800"
          />
          <button
            type="button"
            onClick={handleUploadKnowledgeItem}
            disabled={knowledgeBusy || !knowledgeFile}
            className="h-9 whitespace-nowrap rounded-xl bg-slate-900 px-3 py-1 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-700"
          >
            {t("campaigns.knowledge.upload")}
          </button>
        </div>

        <div className="grid items-center gap-2 md:grid-cols-[minmax(150px,1fr)_minmax(140px,0.8fr)_auto]">
          <input
            value={knowledgeSearchDraft}
            onChange={(event) => setKnowledgeSearchDraft(event.target.value)}
            aria-label={t("campaigns.knowledge.search")}
            placeholder={t("campaigns.knowledge.search")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <select
            value={knowledgeCategoryDraft}
            onChange={(event) => setKnowledgeCategoryDraft(event.target.value)}
            aria-label={t("campaigns.knowledge.categoryFilter")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="">{t("campaigns.knowledge.allCategories")}</option>
            {knowledgeCategories.map((category) => (
              <option key={category} value={category}>{category}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={applyKnowledgeFilters}
            className="h-9 whitespace-nowrap rounded-xl bg-slate-900 px-3 py-1 text-sm font-medium text-white dark:bg-slate-700"
          >
            {t("common.apply")}
          </button>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="min-w-[1180px] table-auto text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">{t("campaigns.knowledge.table.title")}</th>
                <th className="px-3 py-2">{t("campaigns.knowledge.table.category")}</th>
                <th className="px-3 py-2">{t("campaigns.knowledge.table.file")}</th>
                <th className="px-3 py-2">{t("campaigns.knowledge.table.created")}</th>
                <th className="px-3 py-2">{t("campaigns.knowledge.table.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {filteredKnowledgeItems.length === 0 ? (
                <tr>
                  <td className="px-3 py-3 text-slate-500" colSpan={5}>{t("campaigns.knowledge.empty")}</td>
                </tr>
              ) : Object.entries(groupedKnowledgeItems).map(([category, itemsInCategory]) => {
                const expanded = expandedKnowledgeListFolderNames.includes(category);
                return (
                <Fragment key={category}>
                  <tr className="bg-slate-50 dark:bg-slate-950">
                    <td className="px-3 py-2 font-semibold text-slate-600 dark:text-slate-300" colSpan={5}>
                      <button
                        type="button"
                        onClick={() => toggleKnowledgeListFolderExpanded(category)}
                        aria-expanded={expanded}
                        className="flex w-full cursor-pointer items-center justify-between rounded-md px-2 py-1 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                      >
                        <span>📁 {category}</span>
                        <span className="text-xs font-normal text-slate-500">{itemsInCategory.length} 個檔案 · {expanded ? "收合" : "展開"}</span>
                      </button>
                    </td>
                  </tr>
                  {expanded ? itemsInCategory.map((item) => (
                    <tr key={item.item_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                      <td className="px-3 py-2">
                        <div className="font-medium">{item.title}</div>
                        {item.description ? <div className="text-slate-500">{item.description}</div> : null}
                      </td>
                      <td className="px-3 py-2">{category}</td>
                      <td className="px-3 py-2">{String(item.metadata.file_name ?? item.content_url ?? item.item_id)}</td>
                      <td className="px-3 py-2">{formatDateTime(locale, item.created_at)}</td>
                      <td className="px-3 py-2">
                        <div className="flex gap-2">
                          {item.content_url ? (
                            <a href={item.content_url} target="_blank" rel="noreferrer" className="rounded-md bg-blue-600 px-2 py-1 font-medium text-white">
                              {t("campaigns.knowledge.download")}
                            </a>
                          ) : null}
                          <select
                            value={category}
                            onChange={(e) => {
                              if (e.target.value && e.target.value !== category) {
                                void handleMoveKnowledgeItem(item.item_id, e.target.value);
                              }
                            }}
                            disabled={knowledgeBusy || folders.length === 0}
                            className="rounded-md border border-slate-200 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
                          >
                            <option value="">{t("knowledge.moveTo")}</option>
                            {folders
                              .filter((f) => f !== category)
                              .map((folder) => (
                                <option key={folder} value={folder}>{folder}</option>
                              ))}
                          </select>
                          <button
                            type="button"
                            onClick={() => handleDeleteKnowledgeItem(item.item_id)}
                            disabled={knowledgeBusy}
                            className="rounded-md bg-rose-600 px-2 py-1 font-medium text-white disabled:opacity-50"
                          >
                            {t("campaigns.knowledge.remove")}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )) : null}
                </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-3 xl:grid-cols-7 dark:border-slate-800 dark:bg-slate-900">
        <input
          value={campaignSearchDraft}
          onChange={(event) => setCampaignSearchDraft(event.target.value)}
          aria-label={t("campaigns.searchPlaceholder")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          placeholder={t("campaigns.searchPlaceholder")}
        />
        <select value={campaignPlatformDraft} onChange={(event) => setCampaignPlatformDraft(event.target.value)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
          <option value="">{t("common.allPlatforms")}</option>
          {campaignPlatformOptions.map((platform) => <option key={platform} value={platform}>{platform}</option>)}
        </select>
        <select value={campaignStatusDraft} onChange={(event) => setCampaignStatusDraft(event.target.value)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
          <option value="">{t("common.allStatus")}</option>
          <option value="running">{t("status.running")}</option>
          <option value="completed">{t("status.completed")}</option>
          <option value="failed">{t("status.failed")}</option>
        </select>
        <input type="date" value={campaignCreatedFromDraft} onChange={(event) => setCampaignCreatedFromDraft(event.target.value)} aria-label={t("campaigns.filter.createdFrom")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
        <input type="date" value={campaignCreatedToDraft} onChange={(event) => setCampaignCreatedToDraft(event.target.value)} aria-label={t("campaigns.filter.createdTo")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
        <div className="flex gap-2">
          <button type="button" onClick={applyCampaignFilters} className="flex-1 rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white dark:bg-slate-700">{t("common.apply")}</button>
          <button type="button" onClick={resetCampaignFilters} className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium dark:border-slate-700">{t("common.reset")}</button>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">{t("campaigns.table.campaign")}</th>
              <th className="px-4 py-3">{t("campaigns.table.platforms")}</th>
              <th className="px-4 py-3">{t("campaigns.table.status")}</th>
              <th className="px-4 py-3">{t("campaigns.table.budget")}</th>
              <th className="px-4 py-3">{t("campaigns.table.created")}</th>
              <th className="px-4 py-3">{t("campaigns.table.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  {t("campaigns.loading")}
                </td>
              </tr>
            ) : filteredCampaigns.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  {t("campaigns.noCampaigns")}
                </td>
              </tr>
            ) : filteredCampaigns.map((campaign) => (
              <tr key={campaign.id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                <td className="px-4 py-3 font-medium">{campaign.name}</td>
                <td className="px-4 py-3">{campaign.platforms}</td>
                  <td className="px-4 py-3">
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusClasses(campaign.status)}`}>
                    {t(statusKey(campaign.status))}
                  </span>
                </td>
                  <td className="px-4 py-3">
                    {campaign.id.startsWith("fallback")
                      ? t("common.notAvailable")
                      : formatCurrencyUSD(locale, Number(campaign.budget))}
                  </td>
                  <td className="px-4 py-3">
                    {campaign.id.startsWith("fallback") ? t("common.notAvailable") : formatDateTime(locale, campaign.createdAt)}
                  </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => openEditCampaign(campaign.id)}
                    disabled={isFallback || campaign.id.startsWith("fallback")}
                    className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700"
                  >
                    {t("common.edit")}
                  </button>
                  <button
                    onClick={() => openRunWorkOrder(campaign.id)}
                    disabled={isFallback || campaign.id.startsWith("fallback")}
                    className="rounded-lg bg-slate-900 px-2.5 py-1 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-slate-700"
                  >
                    {t("common.run")}
                  </button>
                  <button
                    onClick={() => handleDeleteCampaign(campaign.id)}
                    disabled={isFallback || campaign.id.startsWith("fallback")}
                    className="rounded-lg bg-rose-600 px-2.5 py-1 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {t("common.delete")}
                  </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <header>
          <h2 className="text-sm font-semibold">{t("campaigns.references.title")}</h2>
          <p className="text-xs text-slate-500">{t("campaigns.references.subtitle")}</p>
        </header>

        {referencesMessage ? (
          <p className="rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-700">{referencesMessage}</p>
        ) : null}

        <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-200">{t("campaigns.references.addAssetTitle")}</h3>
        <div className="grid items-center gap-2 md:grid-cols-[minmax(170px,1fr)_minmax(130px,auto)_minmax(240px,1fr)_auto]">
          <select
            value={activeCampaignId}
            onChange={(event) => setSelectedReferenceCampaignId(event.target.value)}
            aria-label={t("campaigns.references.selectCampaign")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            {realCampaigns.length === 0 ? (
              <option value="">{t("campaigns.references.noCampaign")}</option>
            ) : realCampaigns.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
          <label className="sr-only" htmlFor="campaign-asset-type">{t("campaigns.references.assetType")}</label>
          <select
            id="campaign-asset-type"
            value={manualAssetType}
            onChange={(event) => setManualAssetType(event.target.value as EditAssetType)}
            aria-label={t("campaigns.references.assetType")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="copy">{t("assets.type.copy")}</option>
            <option value="image">{t("assets.type.image")}</option>
            <option value="video">{t("assets.type.video")}</option>
          </select>
          <input
            value={manualAssetPrompt}
            onChange={(event) => setManualAssetPrompt(event.target.value)}
            placeholder={t("campaigns.references.assetDescription")}
            aria-label={t("campaigns.references.assetDescription")}
            className="h-9 rounded-xl border border-slate-200 px-3 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <button
            type="button"
            onClick={handleGenerateSingleCampaignAsset}
            disabled={referencesBusy || !activeCampaignId || !manualAssetPrompt.trim()}
            className="h-9 whitespace-nowrap rounded-xl bg-blue-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
          >
            {t("campaigns.references.generateAsset")}
          </button>
        </div>

      </section>

      {editTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="flex h-[90vh] w-full max-w-4xl flex-col rounded-2xl bg-white p-5 shadow-xl dark:bg-slate-900">
            <div className="flex shrink-0 items-center justify-between border-b border-slate-200 pb-3 dark:border-slate-800">
              <h2 className="text-lg font-semibold">{t("campaigns.editTitle")}</h2>
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto py-4 pr-1">
            <div className="grid gap-3 md:grid-cols-2">
              <input value={editForm.campaignName} onChange={(e) => setEditForm((p) => ({ ...p, campaignName: e.target.value }))} placeholder={t("campaigns.form.campaignName")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
              <input value={editForm.productName} onChange={(e) => setEditForm((p) => ({ ...p, productName: e.target.value }))} placeholder={t("campaigns.form.productName")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
              <select value={editForm.objective} onChange={(e) => setEditForm((p) => ({ ...p, objective: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
                <option value="awareness">品牌曝光</option>
                <option value="engagement">互動</option>
                <option value="conversion">導購</option>
              </select>
              <label className="space-y-1 text-xs font-medium text-slate-600 dark:text-slate-300">
                <span>產業類別</span>
                <input value={editForm.industryCategory} onChange={(e) => setEditForm((p) => ({ ...p, industryCategory: e.target.value }))} placeholder="產業類別" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-normal text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" />
              </label>
              <label className="space-y-1 text-xs font-medium text-slate-600 dark:text-slate-300 md:col-span-2">
                <span>專案需求描述</span>
                <textarea value={editForm.projectDescription} onChange={(e) => setEditForm((p) => ({ ...p, projectDescription: e.target.value }))} placeholder="專案需求描述" rows={2} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-normal text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" />
              </label>
              <input value={editForm.budget} onChange={(e) => setEditForm((p) => ({ ...p, budget: formatNumberInput(e.target.value) }))} placeholder="美金預算（勾選投廣策略時必填）" required={editForm.adsStrategy} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
              <select value={editForm.platforms} onChange={(e) => setEditForm((p) => ({ ...p, platforms: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
                <option value="社群平台">社群平台</option>
                <option value="廣告素材">廣告素材</option>
                <option value="網站版位">網站版位</option>
              </select>
              <label className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700">
                <input type="checkbox" checked={editForm.adsStrategy} onChange={() => setEditForm((p) => ({ ...p, adsStrategy: !p.adsStrategy }))} />
                投廣策略
              </label>
              <input value={editForm.brandTone} onChange={(e) => setEditForm((p) => ({ ...p, brandTone: e.target.value }))} placeholder={t("campaigns.form.brandTone")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
              <textarea value={editForm.audiencePersona} onChange={(e) => setEditForm((p) => ({ ...p, audiencePersona: e.target.value }))} placeholder="目標受眾（例如：25-45歲女性、都會上班族、所有受眾）" className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 md:col-span-2" />
              <label className="space-y-1 text-xs font-medium text-slate-600 dark:text-slate-300"><span>文案數量（最多7）</span><input type="number" min={0} max={7} value={editForm.copyVariants} onChange={(e) => setEditForm((p) => ({ ...p, copyVariants: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-normal text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" /></label>
              <label className="space-y-1 text-xs font-medium text-slate-600 dark:text-slate-300"><span>圖片數量（最多5）</span><input type="number" min={0} max={5} value={editForm.imageAssets} onChange={(e) => setEditForm((p) => ({ ...p, imageAssets: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-normal text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" /></label>
              <label className="space-y-1 text-xs font-medium text-slate-600 dark:text-slate-300"><span>影片數量（最多3）</span><input type="number" min={0} max={3} value={editForm.shortVideoAssets} onChange={(e) => setEditForm((p) => ({ ...p, shortVideoAssets: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-normal text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" /></label>
            </div>
            <div className="space-y-2 rounded-2xl border border-slate-200 p-3 dark:border-slate-800">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">Assets</h3>
                <span className="text-xs text-slate-500">已併入 Edit Campaign</span>
              </div>
              <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
                <table className="min-w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
                    <tr>
                      <th className="px-3 py-2">Asset 名稱</th>
                      <th className="px-3 py-2">Asset 編號</th>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {editAssetsLoading ? (
                      <tr><td className="px-3 py-3 text-slate-500" colSpan={5}>Loading assets...</td></tr>
                    ) : editAssets.length === 0 ? (
                      <tr><td className="px-3 py-3 text-slate-500" colSpan={5}>No assets yet.</td></tr>
                    ) : editAssets.map((asset) => {
                      const badge = reviewStatusBadge(asset.status, t);
                      return (
                        <tr key={asset.id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                          <td className="px-3 py-2 font-medium">{asset.name}</td>
                          <td className="px-3 py-2 font-mono text-xs">{asset.id}</td>
                          <td className="px-3 py-2">{editAssetTypeLabel(asset.type, t)}</td>
                          <td className="px-3 py-2"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${badge.className}`}>{badge.label}</span></td>
                          <td className="px-3 py-2">
                            <div className="flex flex-wrap gap-2 whitespace-nowrap">
                              <button
                                type="button"
                                onClick={() => setPreviewAssetId(asset.id)}
                                className="rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-700 dark:bg-slate-700"
                              >
                                預覽
                              </button>
                              <button
                                type="button"
                                onClick={() => downloadEditAsset(asset)}
                                className="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700"
                              >
                                下載
                              </button>
                              {asset.status === "rejected" && isLatestEditAsset(asset, editAssets) ? (
                              <button
                                type="button"
                                onClick={() => openRegenerateWorkOrder(asset)}
                                className="rounded-md bg-blue-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-700"
                              >
                                重新生成
                              </button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            </div>
            <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-slate-200 pt-3 dark:border-slate-800">
              <button onClick={() => setEditTarget(null)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium dark:border-slate-700">{t("common.cancel")}</button>
              <button onClick={openSaveAndRerunWorkOrder} className="rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white">{t("campaigns.saveAndRerun")}</button>
            </div>
          </div>
        </div>
      ) : null}
      {regenerateTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-2xl space-y-4 rounded-2xl bg-white p-5 shadow-2xl dark:bg-slate-900">
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-3 dark:border-slate-800">
              <div>
                <h2 className="text-lg font-semibold">重新生成工單</h2>
                <p className="mt-1 text-sm text-slate-500">只會重新生成此 Asset，送出後新素材會回到審核流程。</p>
              </div>
              <button
                type="button"
                onClick={() => setRegenerateTarget(null)}
                disabled={regenerateBusy}
                className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium disabled:opacity-50 dark:border-slate-700"
              >
                關閉
              </button>
            </div>
            <div className="grid gap-3 text-sm md:grid-cols-2">
              <ReviewField label="Asset 編號" value={regenerateTarget.id} />
              <ReviewField label="Asset 名稱" value={regenerateTarget.name} />
              <ReviewField label={t("review.table.type")} value={editAssetTypeLabel(regenerateTarget.type, t)} />
              <ReviewField label={t("review.table.status")} value={t("review.status.rejected")} />
            </div>
            <label className="block space-y-1 text-sm font-medium">
              <span>退件原因 / 重新生成重點</span>
              <textarea
                value={regenerateReason}
                onChange={(event) => setRegenerateReason(event.target.value)}
                rows={3}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-normal dark:border-slate-700 dark:bg-slate-950"
              />
            </label>
            <label className="block space-y-1 text-sm font-medium">
              <span>使用者補充修改內容（可選）</span>
              <textarea
                value={regenerateInstruction}
                onChange={(event) => setRegenerateInstruction(event.target.value)}
                placeholder="例如：文案必須提到16強優惠、語氣更有急迫感、避免保證獲利等"
                rows={4}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-normal dark:border-slate-700 dark:bg-slate-950"
              />
            </label>
            <div className="flex justify-end gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setRegenerateTarget(null)}
                disabled={regenerateBusy}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => { void handleRegenerateSubmit(); }}
                disabled={regenerateBusy}
                className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                送出重新生成
              </button>
            </div>
          </div>
        </div>
      ) : null}
      <ReviewAssetPreviewModal
        assetId={previewAssetId}
        open={Boolean(previewAssetId)}
        onClose={() => setPreviewAssetId(null)}
        showRegenerate={false}
      />
    </section>
  );
}

function ReviewField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 rounded-xl bg-slate-50 p-3 text-slate-800 dark:bg-slate-950 dark:text-slate-100">{value}</p>
    </div>
  );
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function getReferenceFolder(item: CampaignReferenceRecord): string {
  const folder = item.folder ?? item.metadata?.folder ?? item.metadata?.category;
  return typeof folder === "string" && folder.trim() ? folder : "General";
}

function getKnowledgeFolder(item: KnowledgeItemRecord): string {
  const folder = item.metadata?.folder ?? item.metadata?.category;
  return typeof folder === "string" && folder.trim() ? folder : "General";
}

function isKnowledgeItemAttachable(item: KnowledgeItemRecord): boolean {
  return (typeof item.content_url === "string" && item.content_url.trim().length > 0)
    || (item.metadata?.source_label === "review_approved" && Boolean(item.description.trim()));
}

function normalizeCampaignPlatform(value: string | undefined): string {
  if (value === "廣告素材" || value === "網站版位" || value === "社群平台") return value;
  return "社群平台";
}

function getReviewRejectReason(item: ReviewItem | undefined) {
  return item?.reject_reason || item?.rejected_reason || item?.reason || "";
}

function editAssetVersion(name: string): number {
  const match = name.trim().match(/(?:_|\s)V(\d+)$/i);
  return match ? Number(match[1]) : 1;
}

function editAssetBaseName(name: string): string {
  return name.trim().replace(/(?:_|\s)V\d+$/i, "");
}

function isLatestEditAsset(asset: EditAssetRow, assets: EditAssetRow[]): boolean {
  const baseName = editAssetBaseName(asset.name);
  const version = editAssetVersion(asset.name);
  return assets
    .filter((candidate) => editAssetBaseName(candidate.name) === baseName)
    .every((candidate) => editAssetVersion(candidate.name) <= version);
}

function formatNumberInput(value: string | number): string {
  const raw = String(value).replace(/,/g, "").replace(/[^0-9.]/g, "");
  if (!raw) return "";
  const [integer, decimal] = raw.split(".");
  const formatted = Number(integer || "0").toLocaleString("en-US");
  return decimal !== undefined ? `${formatted}.${decimal.slice(0, 2)}` : formatted;
}

function getCookieValue(name: string): string {
  if (typeof document === "undefined") return "";
  const target = `${name}=`;
  for (const rawPart of document.cookie.split(";")) {
    const part = rawPart.trim();
    if (part.startsWith(target)) {
      return decodeURIComponent(part.slice(target.length));
    }
  }
  return "";
}

function readActorRoleFromToken(token: string): "admin" | "operator" | null {
  if (!token) return null;
  const [payload] = token.split(".");
  if (!payload) return null;
  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(atob(normalized)) as { actor_role?: string };
    if (decoded.actor_role === "admin") return "admin";
    if (decoded.actor_role === "operator") return "operator";
    return null;
  } catch {
    return null;
  }
}
