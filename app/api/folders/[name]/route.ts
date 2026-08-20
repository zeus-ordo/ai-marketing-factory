import { getFolders, saveFolders } from "@/lib/server/folders-store";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ name: string }> },
) {
  try {
    const { name } = await params;
    const decodedName = decodeURIComponent(name);
    const folders = getFolders();
    const index = folders.indexOf(decodedName);

    if (index === -1) {
      return Response.json({ detail: "Folder not found" }, { status: 404 });
    }

    folders.splice(index, 1);
    saveFolders(folders);

    return Response.json({ deleted: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return Response.json({ detail: message }, { status: 500 });
  }
}
