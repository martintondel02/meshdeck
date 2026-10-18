// Token handling: the daemon prints the UI URL with ?token=…; we capture it
// once into sessionStorage and scrub it from the address bar.

const KEY = "meshdeck_token";

export function captureTokenFromUrl(): void {
  const url = new URL(window.location.href);
  const token = url.searchParams.get("token");
  if (token) {
    sessionStorage.setItem(KEY, token);
    url.searchParams.delete("token");
    window.history.replaceState({}, "", url.toString());
  }
}

export function getToken(): string {
  return sessionStorage.getItem(KEY) ?? "";
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${getToken()}`,
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (res.status === 401) throw new Error("unauthorized");
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body?.error?.code ?? detail;
    } catch {
      /* non-JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws?token=${getToken()}`;
}

/** Multipart file upload (no JSON content-type). Returns the 202 body. */
export async function uploadFile<T = unknown>(
  path: string,
  form: FormData,
): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  });
  if (!res.ok) {
    let code = `${res.status}`;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
    } catch {
      /* non-JSON */
    }
    throw new Error(code);
  }
  return (await res.json()) as T;
}
