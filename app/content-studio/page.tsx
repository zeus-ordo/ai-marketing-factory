"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createKnowledgeItem,
  createReferencePack,
  createFolder,
  deleteReferencePack,
  deleteReferencePackItem,
  deleteFolder,
  deleteKnowledgeItem,
  fetchCampaignContent,
  getCampaignUploadPolicy,
  listKnowledgeItems,
  listReferencePackItems,
  listReferencePacks,
  listFolders,
  updateKnowledgeItem,
  updateReferencePack,
  uploadKnowledgeItem,
  uploadReferencePackItems,
  type FolderRecord,
  type KnowledgeItemRecord,
  type ReferencePackItemRecord,
  type ReferencePackRecord,
  type ReferencePackRole,
  type UploadPolicy,
} from "@/lib/api/campaigns";
import { useAuth } from "@/lib/auth/context";
import { isPlatformAdmin } from "@/lib/auth/permissions";
import { useI18n } from "@/lib/i18n/context";
import { formatDateTime } from "@/lib/i18n/format";
import { mergeBatchUploadStates, preflightCampaignReferenceFiles, uploadBatchItems, type BatchUploadFileState } from "@/lib/api/batch-upload";
import { FilePreviewModal } from "@/components/files/file-preview-modal";

type KnowledgeTab = "all" | "ai" | "manual";
const MAX_BATCH_UPLOAD_FILES = 20;

export default function ContentStudioPage() {
  const { t, locale } = useI18n();
  const { user } = useAuth();
  const canManageReferencePacks = user ? isPlatformAdmin(user.permissions) : false;
  const [items, setItems] = useState<KnowledgeItemRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [filePreview, setFilePreview] = useState<{ source: File | string; fileName: string } | null>(null);
  const [tab, setTab] = useState<KnowledgeTab>("all");
  const [query, setQuery] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [assetType, setAssetType] = useState<"copy" | "image" | "video">("copy");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadStates, setUploadStates] = useState<BatchUploadFileState<File>[]>([]);
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState(false);

  // Folder state
  const [folders, setFolders] = useState<FolderRecord[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [showNewFolderInput, setShowNewFolderInput] = useState(false);

  const loadItems = useCallback(async function loadItems() {
    setLoading(true);
    try {
      const rows = await listKnowledgeItems();
      setItems(rows);
      setMessage(null);
    } catch {
      setItems([]);
      setMessage(t("knowledge.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const loadFolders = useCallback(async function loadFolders() {
    try {
      setFolders(await listFolders());
    } catch {
      // folders not critical, ignore errors
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadItems();
      void loadFolders();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadItems, loadFolders]);

  const availableFolders = useMemo(() => folders, [folders]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      if (tab === "ai" && item.source !== "ai") return false;
      if (tab === "manual" && item.source !== "manual") return false;
      if (selectedFolderId && item.folder_id !== selectedFolderId) return false;
      if (!normalized) return true;
      return `${item.title} ${item.description} ${String(item.metadata.file_name ?? "")} ${String(item.metadata.category ?? "")}`.toLowerCase().includes(normalized);
    });
  }, [items, query, tab, selectedFolderId]);

  async function handleCreateFolder() {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      await createFolder(name);
      setNewFolderName("");
      setShowNewFolderInput(false);
      void loadFolders();
    } catch {
      // ignore errors
    }
  }

  async function handleDeleteFolder(folder: FolderRecord) {
    if (!window.confirm(t("knowledge.deleteConfirm"))) return;
    try {
      await deleteFolder(folder.folder_id);
      if (selectedFolderId === folder.folder_id) setSelectedFolderId(null);
      await loadItems();
      void loadFolders();
    } catch {
      setMessage(t("knowledge.deleteFailed"));
    }
  }

  async function handleCreateText() {
    const cleanTitle = title.trim();
    if (!cleanTitle) return;
    setBusy(true);
    try {
      await createKnowledgeItem({
        title: cleanTitle,
        source: "manual",
        description,
        folder_id: category || null,
        metadata: { category: folders.find((folder) => folder.folder_id === category)?.name || "General", source_label: "manual_copy", asset_type: "copy" },
      });
      setTitle("");
      setDescription("");
      setCategory("");
      await loadItems();
      void loadFolders();
    } catch {
      setMessage(t("knowledge.createFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload() {
    if (files.length === 0 || assetType === "copy") return;
    setBusy(true);
    try {
      const initialStates = files.map((file) => ({ file, status: "pending" as const }));
      setUploadStates(initialStates);
      const results = await uploadBatchItems(initialStates, (file) => uploadKnowledgeItem(file, title.trim() || file.name, description, folders.find((folder) => folder.folder_id === category)?.name || "General", assetType, category || undefined).then((item) => ({ referenceId: item.item_id, folderId: item.folder_id })), 3, (updates) => setUploadStates((current) => mergeBatchUploadStates(current, updates)));
      if (results.every((item) => item.status === "success")) {
        setTitle("");
        setDescription("");
        setCategory("");
        setFiles([]);
        setUploadStates([]);
        setFileKey((prev) => prev + 1);
      } else {
        setMessage(t("knowledge.uploadFailed"));
      }
      await loadItems();
      void loadFolders();
    } catch {
      setMessage(t("knowledge.uploadFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(itemId: string) {
    if (!window.confirm(t("knowledge.deleteConfirm"))) return;
    setBusy(true);
    try {
      await deleteKnowledgeItem(itemId);
      await loadItems();
    } catch {
      setMessage(t("knowledge.deleteFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDownload(item: KnowledgeItemRecord) {
    const contentUrl = item.content_url || (typeof item.metadata.download_url === "string" ? item.metadata.download_url : null);
    if (!contentUrl && !item.description.trim()) return;
    try {
      const blob = contentUrl
        ? await fetchCampaignContent(contentUrl)
        : new Blob([item.description], { type: "text/plain;charset=utf-8" });
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = String(item.metadata.file_name ?? `${item.title}.txt`);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch {
      setMessage(t("campaigns.knowledge.downloadFailed"));
    }
  }

  async function handleMoveItem(item: KnowledgeItemRecord, folderId: string) {
    if (!folderId || folderId === item.folder_id) return;
    const target = folders.find((folder) => folder.folder_id === folderId);
    if (!target || target.scope === "platform") return;
    setBusy(true);
    try {
      await updateKnowledgeItem(item.item_id, { category: target.name, folder_id: target.folder_id });
      setMessage(t("knowledge.moveSuccess"));
      await loadItems();
      void loadFolders();
    } catch {
      setMessage(t("knowledge.moveFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("knowledge.title")}</h1>
        <p className="text-sm text-slate-500">{t("knowledge.subtitle")}</p>
      </header>

      {message ? <p className="rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</p> : null}

      {/* Tab filters */}
      <div className="flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
        {(["all", "ai", "manual"] as KnowledgeTab[]).map((item) => (
          <button
            key={item}
            onClick={() => setTab(item)}
            className={`rounded-xl px-3 py-2 text-sm font-medium ${tab === item ? "bg-slate-900 text-white dark:bg-slate-700" : "border border-slate-200 dark:border-slate-700"}`}
          >
            {t(`knowledge.tabs.${item}`)}
          </button>
        ))}
      </div>

      {/* Folder selector */}
      <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">{t("knowledge.category")}</h2>
          <button
            onClick={() => setShowNewFolderInput(!showNewFolderInput)}
            className="rounded-xl bg-slate-900 px-3 py-1.5 text-xs font-medium text-white dark:bg-slate-700"
          >
            {showNewFolderInput ? t("common.cancel") : t("knowledge.folderNew")}
          </button>
        </div>

        {showNewFolderInput && (
          <div className="flex gap-2">
            <input
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder={t("knowledge.folderName")}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleCreateFolder();
              }}
            />
            <button
              onClick={() => void handleCreateFolder()}
              disabled={!newFolderName.trim()}
              className="rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {t("common.save")}
            </button>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedFolderId(null)}
            className={`rounded-xl px-3 py-1.5 text-sm ${selectedFolderId === null ? "bg-slate-900 text-white dark:bg-slate-700" : "border border-slate-200 dark:border-slate-700"}`}
          >
            {t("knowledge.folderAll")}
          </button>
          {folders.map((folder) => (
            <div key={folder.folder_id} className="group relative">
              <button
                onClick={() => setSelectedFolderId(selectedFolderId === folder.folder_id ? null : folder.folder_id)}
                className={`rounded-xl px-3 py-1.5 text-sm ${selectedFolderId === folder.folder_id ? "bg-slate-900 text-white dark:bg-slate-700" : "border border-slate-200 dark:border-slate-700"}`}
              >
                {folder.name}{folder.scope === "platform" ? " · read-only" : ""}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  void handleDeleteFolder(folder);
                }}
                disabled={folder.scope === "platform"}
                className="absolute -right-1 -top-1 hidden h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-xs text-white group-hover:flex"
                title={t("knowledge.folderDelete")}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Create/upload form */}
      <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="text-sm font-semibold">{t("knowledge.createTitle")}</h2>
        <div className="grid gap-3 md:grid-cols-[0.8fr_1fr_1fr_1fr_1.2fr_auto]">
          <select
            value={assetType}
            onChange={(event) => {
              const next = event.target.value as "copy" | "image" | "video";
              setAssetType(next);
              if (next === "copy") { setFiles([]); setUploadStates([]); }
            }}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="copy">{t("assets.type.copy")}</option>
            <option value="image">{t("assets.type.image")}</option>
            <option value="video">{t("assets.type.video")}</option>
          </select>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={t("knowledge.itemTitle")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder={assetType === "copy" ? "文案內容" : t("knowledge.description")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="">{t("knowledge.folderSelect")}</option>
            {availableFolders.map((f) => (
              <option key={f.folder_id} value={f.folder_id}>{f.name}</option>
            ))}
          </select>
          <div className={`relative flex min-h-10 items-center justify-center rounded-xl border border-slate-200 text-sm dark:border-slate-700 dark:bg-slate-950 ${assetType === "copy" ? "opacity-50" : ""}`}>
            <input
              id={`knowledge-file-input-${fileKey}`}
              key={fileKey}
              type="file"
              multiple
              onChange={(event) => { const selected = Array.from(event.target.files ?? []); if (selected.length > MAX_BATCH_UPLOAD_FILES) { setMessage(t("campaigns.form.maxBatchFiles", { count: MAX_BATCH_UPLOAD_FILES })); setFiles([]); setUploadStates([]); return; } setFiles(selected); setUploadStates(selected.map((file) => ({ file, status: "pending" as const }))); }}
              disabled={assetType === "copy"}
              accept={assetType === "image" ? "image/*" : assetType === "video" ? "video/*" : undefined}
              className="sr-only"
            />
            <label
              htmlFor={`knowledge-file-input-${fileKey}`}
              className="flex h-full min-h-10 w-full cursor-pointer items-center justify-center gap-2 px-3 py-2 text-center leading-none text-slate-600 dark:text-slate-300"
            >
              <span className="font-medium text-slate-800 dark:text-slate-100">{assetType === "copy" ? t("knowledge.copyNoFile") : t("knowledge.chooseFile")}</span>
              <span className="truncate text-slate-500">{assetType === "copy" ? "" : files.length > 0 ? `${files.length} file(s) selected` : t("knowledge.noFileSelected")}</span>
            </label>
          </div>
          <div className="flex min-w-32 flex-col gap-2">
            <button onClick={handleCreateText} disabled={busy || assetType !== "copy" || !title.trim()} className="whitespace-nowrap rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-700">{t("knowledge.createText")}</button>
            <button onClick={handleUpload} disabled={busy || assetType === "copy" || files.length === 0} className="whitespace-nowrap rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{t("knowledge.add", { type: t(`assets.type.${assetType}`) })}</button>
          </div>
        </div>
        {uploadStates.length > 0 ? (
          <ul className="space-y-1 text-xs" aria-label={t("knowledge.uploadFailed")}>
            {uploadStates.map((item) => (
              <li key={`${item.file.name}-${item.file.lastModified}`} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-2 py-1 dark:border-slate-700">
                <span className="truncate">{item.file.name}</span>
                <button type="button" onClick={() => setFilePreview({ source: item.file, fileName: item.file.name })} className="font-medium text-blue-600">{t("campaigns.knowledge.preview")}</button>
                <span>{item.status === "pending" ? t("campaigns.form.uploadPending") : item.status === "uploading" ? t("campaigns.form.uploading") : item.status === "success" ? t("campaigns.form.uploadSuccess") : t("campaigns.form.uploadFailed")}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {/* Search */}
      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-[1fr_auto] dark:border-slate-800 dark:bg-slate-900">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("knowledge.search")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
        <button onClick={() => void loadItems()} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white dark:bg-slate-700">{t("common.apply")}</button>
      </div>

      {/* Items table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">{t("knowledge.table.title")}</th>
              <th className="px-4 py-3">{t("knowledge.table.source")}</th>
              <th className="px-4 py-3">{t("knowledge.table.category")}</th>
              <th className="px-4 py-3">{t("knowledge.table.created")}</th>
              <th className="px-4 py-3">{t("knowledge.table.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={5}>{t("common.loading")}</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={5}>{t("knowledge.empty")}</td></tr>
            ) : filtered.map((item) => (
              <tr key={item.item_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                <td className="px-4 py-3"><div className="font-medium">{item.title}</div><div className="text-xs text-slate-500">{item.description || String(item.metadata.file_name ?? "")}</div></td>
                <td className="px-4 py-3">{item.source === "ai" ? t("knowledge.tabs.ai") : t("knowledge.tabs.manual")}</td>
                <td className="px-4 py-3">{String(item.metadata.category ?? "General")}</td>
                <td className="px-4 py-3">{formatDateTime(locale, item.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    {(item.content_url || typeof item.metadata.download_url === "string" || item.description.trim()) ? <>
                      <button type="button" onClick={() => setFilePreview({ source: item.content_url || (typeof item.metadata.download_url === "string" ? String(item.metadata.download_url) : new File([item.description], `${item.title}.txt`, { type: "text/plain" })), fileName: String(item.metadata.file_name ?? `${item.title}.txt`) })} className="text-xs font-medium text-blue-600 hover:underline">{t("campaigns.knowledge.preview")}</button>
                      <button type="button" onClick={() => void handleDownload(item)} className="text-xs font-medium text-emerald-600 hover:underline">{t("campaigns.knowledge.download")}</button>
                    </> : null}
                    <select
                      value={item.folder_id ?? ""}
                      onChange={(event) => void handleMoveItem(item, event.target.value)}
                      disabled={busy || availableFolders.length === 0}
                      className="rounded-md border border-slate-200 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
                    >
                      <option value="">{t("knowledge.moveTo")}</option>
                      {availableFolders.filter((folder) => folder.scope !== "platform").map((folder) => (
                        <option key={folder.folder_id} value={folder.folder_id}>{folder.name}</option>
                      ))}
                    </select>
                    <button onClick={() => handleDelete(item.item_id)} className="text-xs font-medium text-rose-600 hover:underline">{t("common.delete")}</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FilePreviewModal source={filePreview?.source ?? null} fileName={filePreview?.fileName ?? ""} open={Boolean(filePreview)} onClose={() => setFilePreview(null)} />
      {canManageReferencePacks ? <SystemReferencePacksSection /> : null}
    </section>
  );
}

const PACK_ROLES: ReferencePackRole[] = ["brand_identity", "product", "style", "composition", "campaign_examples"];

function SystemReferencePacksSection() {
  const { t } = useI18n();
  const [packs, setPacks] = useState<ReferencePackRecord[]>([]);
  const [packCounts, setPackCounts] = useState<Record<string, number>>({});
  const [items, setItems] = useState<ReferencePackItemRecord[]>([]);
  const [selectedPackId, setSelectedPackId] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState<ReferencePackRole | "">("");
  const [industryFilter, setIndustryFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState<"" | "true" | "false">("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<ReferencePackRole>("brand_identity");
  const [industry, setIndustry] = useState("");
  const [mode, setMode] = useState<"mandatory" | "optional">("optional");
  const [maxImages, setMaxImages] = useState(1);
  const [priority, setPriority] = useState(0);
  const [isActive, setIsActive] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [uploadStates, setUploadStates] = useState<BatchUploadFileState<File>[]>([]);
  const [fileKey, setFileKey] = useState(0);
  const [uploadPolicy, setUploadPolicy] = useState<UploadPolicy | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ source: string | File; fileName: string } | null>(null);
  const selectedPackRef = useRef<string | null>(null);

  const selectedPack = packs.find((pack) => pack.pack_id === selectedPackId) ?? null;
  const loadPacks = useCallback(async () => {
    setLoading(true);
    try {
      const next = await listReferencePacks({ role: roleFilter || undefined, industry: industryFilter, isActive: activeFilter === "" ? undefined : activeFilter === "true" });
      setPacks(next);
      const counts = await Promise.all(next.map(async (pack) => [pack.pack_id, (await listReferencePackItems(pack.pack_id)).length] as const));
      setPackCounts(Object.fromEntries(counts));
      if (selectedPackId && !next.some((pack) => pack.pack_id === selectedPackId)) selectPack(null);
      setMessage(null);
    } catch { setMessage(t("referencePacks.loadFailed")); } finally { setLoading(false); }
  }, [activeFilter, industryFilter, roleFilter, selectedPackId, t]);

  const loadItems = useCallback(async (packId: string) => {
    try { setItems(await listReferencePackItems(packId)); } catch { setItems([]); setMessage(t("referencePacks.itemsLoadFailed")); }
  }, [t]);

  useEffect(() => { void loadPacks(); }, [loadPacks]);
  useEffect(() => {
    selectedPackRef.current = selectedPackId;
  }, [selectedPackId]);
  useEffect(() => {
    void getCampaignUploadPolicy().then(setUploadPolicy).catch(() => setMessage(t("referencePacks.policyLoadFailed")));
  }, [t]);
  useEffect(() => { if (selectedPackId) void loadItems(selectedPackId); else setItems([]); }, [loadItems, selectedPackId]);
  useEffect(() => {
    if (!selectedPack) return;
    setName(selectedPack.name); setRole(selectedPack.role); setIndustry(selectedPack.industry ?? ""); setMode(selectedPack.selection_mode);
    setMaxImages(selectedPack.max_images); setPriority(selectedPack.priority); setIsActive(selectedPack.is_active);
  }, [selectedPack]);

  async function savePack() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const payload = { name: name.trim(), role, industry: industry.trim() || null, selection_mode: mode, max_images: Math.max(1, maxImages), priority, is_active: isActive };
      const saved = selectedPackId ? await updateReferencePack(selectedPackId, payload) : await createReferencePack(payload);
      setSelectedPackId(saved.pack_id); setMessage(t("referencePacks.saved")); await loadPacks();
    } catch { setMessage(t("referencePacks.saveFailed")); } finally { setBusy(false); }
  }

  function clearPackUploadState() {
    setFiles([]);
    setUploadStates([]);
    setPreview(null);
    setFileKey((value) => value + 1);
  }

  function selectPack(packId: string | null) {
    clearPackUploadState();
    setSelectedPackId(packId);
    if (!packId) {
      setName(""); setRole("brand_identity"); setIndustry(""); setMode("optional"); setMaxImages(1); setPriority(0); setIsActive(true);
    }
  }

  async function removePack(pack: ReferencePackRecord) {
    if (!window.confirm(t("referencePacks.deleteConfirm"))) return;
    setBusy(true);
    try { await deleteReferencePack(pack.pack_id); if (selectedPackId === pack.pack_id) setSelectedPackId(null); setMessage(t("referencePacks.deleted")); await loadPacks(); }
    catch { setMessage(t("referencePacks.deleteFailed")); } finally { setBusy(false); }
  }

  async function uploadFiles() {
    const uploadPackId = selectedPackId;
    if (!uploadPackId || !uploadPolicy || uploadStates.length === 0) return;
    setBusy(true);
    try {
      const result = await uploadReferencePackItems(uploadPackId, uploadStates, 3, (updates) => {
        if (selectedPackRef.current === uploadPackId) setUploadStates((current) => mergeBatchUploadStates(current, updates));
      });
      if (selectedPackRef.current !== uploadPackId) return;
      setUploadStates(result);
      if (result.every((item) => item.status === "success")) { clearPackUploadState(); setMessage(t("referencePacks.uploaded")); }
      else setMessage(t("referencePacks.uploadFailed"));
      await loadItems(uploadPackId); await loadPacks();
    } catch { setMessage(t("referencePacks.uploadFailed")); } finally { setBusy(false); }
  }

  async function removeItem(item: ReferencePackItemRecord) {
    if (!selectedPackId || !window.confirm(t("referencePacks.deleteItemConfirm"))) return;
    setBusy(true);
    try { await deleteReferencePackItem(selectedPackId, item.item_id); await loadItems(selectedPackId); await loadPacks(); }
    catch { setMessage(t("referencePacks.deleteItemFailed")); } finally { setBusy(false); }
  }

  return <section className="space-y-4 rounded-2xl border border-indigo-200 bg-indigo-50/40 p-4 dark:border-indigo-900 dark:bg-indigo-950/20">
    <header><h2 className="text-lg font-semibold">{t("referencePacks.title")}</h2><p className="text-sm text-slate-500">{t("referencePacks.subtitle")}</p></header>
    {message ? <p role="alert" className="rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</p> : null}
    <div className="grid gap-2 md:grid-cols-3">
      <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value as ReferencePackRole | "")} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"><option value="">{t("referencePacks.allRoles")}</option>{PACK_ROLES.map((value) => <option key={value} value={value}>{t(`referencePacks.roles.${value}`)}</option>)}</select>
      <input value={industryFilter} onChange={(event) => setIndustryFilter(event.target.value)} placeholder={t("referencePacks.industryFilter")} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
      <select value={activeFilter} onChange={(event) => setActiveFilter(event.target.value as "" | "true" | "false")} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"><option value="">{t("referencePacks.allStatus")}</option><option value="true">{t("referencePacks.active")}</option><option value="false">{t("referencePacks.inactive")}</option></select>
    </div>
    <div className="grid gap-4 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <div className="space-y-2">
        <button type="button" onClick={() => { selectPack(null); setItems([]); }} className="w-full rounded-xl bg-indigo-600 px-3 py-2 text-sm font-medium text-white">{t("referencePacks.new")}</button>
        {loading ? <p className="text-sm text-slate-500">{t("common.loading")}</p> : packs.length === 0 ? <p className="text-sm text-slate-500">{t("referencePacks.empty")}</p> : packs.map((pack) => <button type="button" key={pack.pack_id} onClick={() => { selectPack(pack.pack_id); setItems([]); }} className={`w-full rounded-xl border p-3 text-left ${selectedPackId === pack.pack_id ? "border-indigo-500 bg-white" : "border-slate-200 bg-white/70"}`}><span className="flex items-center justify-between gap-2 font-medium"><span className="truncate">{pack.name}</span><span className="text-xs text-slate-500">{pack.is_active ? t("referencePacks.active") : t("referencePacks.inactive")}</span></span><span className="mt-1 block text-xs text-slate-500">{t(`referencePacks.roles.${pack.role}`)} · {pack.industry || t("referencePacks.global")} · {t("referencePacks.imageCount", { count: packCounts[pack.pack_id] ?? 0 })}</span></button>) }
      </div>
      <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-3">
        <div className="grid gap-2 sm:grid-cols-2"><input value={name} onChange={(event) => setName(event.target.value)} placeholder={t("referencePacks.name")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" /><select value={role} onChange={(event) => setRole(event.target.value as ReferencePackRole)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">{PACK_ROLES.map((value) => <option key={value} value={value}>{t(`referencePacks.roles.${value}`)}</option>)}</select><input value={industry} onChange={(event) => setIndustry(event.target.value)} placeholder={t("referencePacks.industry")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" /><select value={mode} onChange={(event) => setMode(event.target.value as "mandatory" | "optional")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm"><option value="mandatory">{t("referencePacks.mandatory")}</option><option value="optional">{t("referencePacks.optional")}</option></select><label className="text-sm"><span className="mb-1 block text-slate-500">{t("referencePacks.maxImages")}</span><input type="number" min={1} value={maxImages} onChange={(event) => setMaxImages(Number(event.target.value))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" /></label><label className="text-sm"><span className="mb-1 block text-slate-500">{t("referencePacks.priority")}</span><input type="number" value={priority} onChange={(event) => setPriority(Number(event.target.value))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" /></label></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />{t("referencePacks.active")}</label>
        <div className="flex flex-wrap gap-2"><button type="button" onClick={() => void savePack()} disabled={busy || !name.trim()} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{t("common.save")}</button>{selectedPack ? <button type="button" onClick={() => void removePack(selectedPack)} disabled={busy} className="rounded-xl border border-rose-200 px-3 py-2 text-sm text-rose-600 disabled:opacity-50">{t("common.delete")}</button> : null}</div>
        {selectedPackId ? <><div className="border-t border-slate-200 pt-3"><div className="flex flex-wrap items-center gap-2"><input id={`pack-file-input-${fileKey}`} key={fileKey} type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif" onChange={(event) => { const selected = Array.from(event.target.files ?? []); if (selected.length > MAX_BATCH_UPLOAD_FILES) { setMessage(t("campaigns.form.maxBatchFiles", { count: MAX_BATCH_UPLOAD_FILES })); clearPackUploadState(); return; } if (!uploadPolicy) { setMessage(t("referencePacks.policyLoadFailed")); return; } const imageFiles = selected.map((file) => { const state = preflightCampaignReferenceFiles([file], uploadPolicy)[0]; const isImage = /\.((png|jpe?g|webp|gif))$/i.test(file.name) && file.type.startsWith("image/"); return isImage ? state : { ...state, status: "failed" as const, errorCode: "UNSUPPORTED_FILE_TYPE" }; }); setFiles(selected); setUploadStates(imageFiles); }} className="sr-only" /><label htmlFor={`pack-file-input-${fileKey}`} className="cursor-pointer rounded-xl border border-slate-200 px-3 py-2 text-sm">{t("referencePacks.chooseImages")}</label><span className="text-xs text-slate-500">{files.length ? t("referencePacks.selectedFiles", { count: files.length }) : t("referencePacks.noFiles")}</span><button type="button" onClick={() => void uploadFiles()} disabled={busy || uploadStates.length === 0 || !uploadStates.some((item) => item.status === "pending")} className="rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{t("referencePacks.upload")}</button></div>{uploadStates.length ? <ul className="mt-2 space-y-1 text-xs">{uploadStates.map((item) => <li key={`${item.file.name}-${item.file.lastModified}`} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-2 py-1"><span className="truncate">{item.file.name}</span><span>{item.status === "pending" ? t("campaigns.form.uploadPending") : item.status === "uploading" ? t("campaigns.form.uploading") : item.status === "success" ? t("campaigns.form.uploadSuccess") : `${t("campaigns.form.uploadFailed")}${item.errorCode ? ` (${item.errorCode})` : ""}`}</span></li>)}</ul> : null}</div><ul className="grid gap-2 sm:grid-cols-2">{items.map((item) => <li key={item.item_id} className="rounded-xl border border-slate-200 p-2"><div className="flex h-28 items-center justify-center rounded-lg bg-slate-50 text-sm text-slate-500">{item.file_name}</div><div className="mt-2 flex items-center justify-between gap-2 text-xs"><button type="button" onClick={() => setPreview({ source: item.content_url, fileName: item.file_name })} className="truncate text-blue-600">{t("campaigns.knowledge.preview")}</button><button type="button" onClick={() => void removeItem(item)} className="text-rose-600">{t("common.delete")}</button></div></li>)}</ul></> : <p className="text-sm text-slate-500">{t("referencePacks.selectPack")}</p>}
      </div>
    </div>
    <FilePreviewModal source={preview?.source ?? null} fileName={preview?.fileName ?? ""} open={Boolean(preview)} onClose={() => setPreview(null)} />
  </section>;
}
