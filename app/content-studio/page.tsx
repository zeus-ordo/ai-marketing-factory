"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createKnowledgeItem,
  deleteKnowledgeItem,
  listKnowledgeItems,
  updateKnowledgeItem,
  uploadKnowledgeItem,
  type KnowledgeItemRecord,
} from "@/lib/api/campaigns";
import { useI18n } from "@/lib/i18n/context";
import { formatDateTime } from "@/lib/i18n/format";

type KnowledgeTab = "all" | "ai" | "manual";

type Folder = { name: string };

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
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState(false);

  // Folder state
  const [folders, setFolders] = useState<Folder[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
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
      const res = await fetch("/api/folders");
      if (res.ok) {
        const data = (await res.json()) as { items: Folder[] };
        setFolders(data.items);
      }
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

  const allCategories = useMemo(() => {
    const cats = new Set<string>();
    for (const item of items) {
      const cat = String(item.metadata.category ?? "General");
      cats.add(cat);
    }
    return Array.from(cats).sort();
  }, [items]);

  const availableFolders = useMemo(() => {
    // Combine user-created folders with categories from items
    const combined = new Set([...folders.map((f) => f.name), ...allCategories]);
    return Array.from(combined).sort();
  }, [folders, allCategories]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      if (tab === "ai" && item.source !== "ai") return false;
      if (tab === "manual" && item.source !== "manual") return false;
      if (selectedFolder && String(item.metadata.category ?? "General") !== selectedFolder) return false;
      if (!normalized) return true;
      return `${item.title} ${item.description} ${String(item.metadata.file_name ?? "")} ${String(item.metadata.category ?? "")}`.toLowerCase().includes(normalized);
    });
  }, [items, query, tab, selectedFolder]);

  async function handleCreateFolder() {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      const res = await fetch("/api/folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (res.ok) {
        setNewFolderName("");
        setShowNewFolderInput(false);
        void loadFolders();
      }
    } catch {
      // ignore errors
    }
  }

  async function handleDeleteFolder(folderName: string) {
    if (!window.confirm(t("knowledge.deleteConfirm"))) return;
    try {
      const res = await fetch(`/api/folders/${encodeURIComponent(folderName)}`, {
        method: "DELETE",
      });
      if (res.ok) {
        if (selectedFolder === folderName) setSelectedFolder(null);
        void loadFolders();
      }
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
        metadata: { category: category || "General", source_label: "manual_copy", asset_type: "copy" },
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
    if (!file || assetType === "copy") return;
    setBusy(true);
    try {
      await uploadKnowledgeItem(file, title || file.name, description, category || "General", assetType);
      setTitle("");
      setDescription("");
      setCategory("");
      setFile(null);
      setFileKey((prev) => prev + 1);
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

  async function handleMoveItem(item: KnowledgeItemRecord, folderName: string) {
    const currentFolder = String(item.metadata.category ?? "General");
    if (!folderName || folderName === currentFolder) return;
    setBusy(true);
    try {
      await updateKnowledgeItem(item.item_id, { category: folderName });
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
            onClick={() => setSelectedFolder(null)}
            className={`rounded-xl px-3 py-1.5 text-sm ${selectedFolder === null ? "bg-slate-900 text-white dark:bg-slate-700" : "border border-slate-200 dark:border-slate-700"}`}
          >
            {t("knowledge.folderAll")}
          </button>
          {availableFolders.map((folder) => (
            <div key={folder} className="group relative">
              <button
                onClick={() => setSelectedFolder(selectedFolder === folder ? null : folder)}
                className={`rounded-xl px-3 py-1.5 text-sm ${selectedFolder === folder ? "bg-slate-900 text-white dark:bg-slate-700" : "border border-slate-200 dark:border-slate-700"}`}
              >
                {folder}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  void handleDeleteFolder(folder);
                }}
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
        <h2 className="text-sm font-semibold">新增素材</h2>
        <div className="grid gap-3 md:grid-cols-[0.8fr_1fr_1fr_1fr_1.2fr_auto]">
          <select
            value={assetType}
            onChange={(event) => {
              const next = event.target.value as "copy" | "image" | "video";
              setAssetType(next);
              if (next === "copy") setFile(null);
            }}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="copy">文案</option>
            <option value="image">圖片</option>
            <option value="video">影片</option>
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
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
          <div className={`relative flex min-h-10 items-center justify-center rounded-xl border border-slate-200 text-sm dark:border-slate-700 dark:bg-slate-950 ${assetType === "copy" ? "opacity-50" : ""}`}>
            <input
              id={`knowledge-file-input-${fileKey}`}
              key={fileKey}
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              disabled={assetType === "copy"}
              accept={assetType === "image" ? "image/*" : assetType === "video" ? "video/*" : undefined}
              className="sr-only"
            />
            <label
              htmlFor={`knowledge-file-input-${fileKey}`}
              className="flex h-full min-h-10 w-full cursor-pointer items-center justify-center gap-2 px-3 py-2 text-center leading-none text-slate-600 dark:text-slate-300"
            >
              <span className="font-medium text-slate-800 dark:text-slate-100">{assetType === "copy" ? "文案不需檔案" : t("knowledge.chooseFile")}</span>
              <span className="truncate text-slate-500">{assetType === "copy" ? "" : file ? file.name : t("knowledge.noFileSelected")}</span>
            </label>
          </div>
          <div className="flex min-w-32 flex-col gap-2">
            <button onClick={handleCreateText} disabled={busy || assetType !== "copy" || !title.trim()} className="whitespace-nowrap rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-700">新增文案</button>
            <button onClick={handleUpload} disabled={busy || assetType === "copy" || !file} className="whitespace-nowrap rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">新增{assetType === "video" ? "影片" : "圖片"}</button>
          </div>
        </div>
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
                      value={String(item.metadata.category ?? "General")}
                      onChange={(event) => void handleMoveItem(item, event.target.value)}
                      disabled={busy || availableFolders.length === 0}
                      className="rounded-md border border-slate-200 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
                    >
                      <option value="">{t("knowledge.moveTo")}</option>
                      {availableFolders.map((folder) => (
                        <option key={folder} value={folder}>{folder}</option>
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
