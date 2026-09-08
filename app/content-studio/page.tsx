"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createKnowledgeItem,
  createFolder,
  deleteFolder,
  deleteKnowledgeItem,
  listKnowledgeItems,
  listFolders,
  updateKnowledgeItem,
  uploadKnowledgeItem,
  type FolderRecord,
  type KnowledgeItemRecord,
} from "@/lib/api/campaigns";
import { useI18n } from "@/lib/i18n/context";
import { formatDateTime } from "@/lib/i18n/format";
import { mergeBatchUploadStates, uploadBatchItems, type BatchUploadFileState } from "@/lib/api/batch-upload";

type KnowledgeTab = "all" | "ai" | "manual";
const MAX_BATCH_UPLOAD_FILES = 20;

export default function ContentStudioPage() {
  const { t, locale } = useI18n();
  const [items, setItems] = useState<KnowledgeItemRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
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
      void loadFolders();
    } catch {
      // ignore errors
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
                    {item.content_url ? <a href={item.content_url} target="_blank" rel="noreferrer" className="text-xs font-medium text-blue-600 hover:underline">{t("knowledge.download")}</a> : null}
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
    </section>
  );
}
