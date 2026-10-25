/**
 * uploadForm — multipart upload that works on web AND on real phones.
 * On native the global fetch is expo/fetch, which rejects RN's
 * `{ uri, name, type }` FormData parts, so files are read into a Blob first.
 */
import { Platform } from "react-native";

type FilePart = { uri: string; name: string; mimeType?: string | null };
type Opts = { headers?: Record<string, string>; fields?: Record<string, string>; files?: Record<string, FilePart> };

export async function uploadForm(url: string, { headers = {}, fields = {}, files = {} }: Opts): Promise<Response> {
  const form = new FormData();
  Object.entries(fields).forEach(([k, v]) => form.append(k, v));
  for (const [k, f] of Object.entries(files)) {
    let blob: Blob;
    if (Platform.OS === "web") {
      blob = await (await fetch(f.uri)).blob();
    } else {
      const { fetch: expoFetch } = await import("expo/fetch");
      blob = await (await expoFetch(f.uri)).blob();
    }
    form.append(k, blob as any, f.name);
  }
  // No Content-Type: the runtime adds the multipart boundary.
  return fetch(url, { method: "POST", headers, body: form });
}
