import { getFolders, saveFolders } from "@/lib/server/folders-store";

export async function GET() {
  try {
    const folders = getFolders();
    return Response.json({ items: folders.map((name) => ({ name })) });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return Response.json({ detail: message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { name } = body as { name?: string };

    if (!name || typeof name !== "string" || !name.trim()) {
      return Response.json({ detail: "Folder name is required" }, { status: 400 });
    }

    const trimmedName = name.trim();
    const folders = getFolders();

    if (folders.includes(trimmedName)) {
      return Response.json({ detail: "Folder already exists" }, { status: 409 });
    }

    folders.push(trimmedName);
    folders.sort();
    saveFolders(folders);

    return Response.json({ name: trimmedName }, { status: 201 });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return Response.json({ detail: message }, { status: 500 });
  }
}
