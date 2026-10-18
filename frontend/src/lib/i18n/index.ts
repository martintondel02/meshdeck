// Minimal, dependency-free i18n for MeshDeck.
//
// - `t(key, vars?)` resolves a dot-separated key in the active locale, falling
//   back to English per key, then to the key itself.
// - `locale` is a plain Svelte store, so `$locale` works in components.
// - `setLocale()` validates the code and falls back to "en".
//
// Limitation (documented in docs/i18n.md): `t()` calls `get(locale)`, which
// does not register a reactive dependency from Svelte markup. Switching the
// locale at runtime therefore needs a reload to show up. That is fine while
// there is no language picker in the UI; a future picker should either force
// a reload or switch components to a `$derived` locale read.

import { get, writable } from "svelte/store";
import { de } from "./de";
import { en } from "./en";

/** A messages dictionary is nested plain objects whose leaves are strings. */
export type Messages = { readonly [key: string]: unknown };

export interface LocaleInfo {
  /** Endonym, for a future language picker ("English", "Deutsch", …). */
  readonly label: string;
  readonly messages: Messages;
  /** False for deliberately partial dictionaries (used to prove fallback). */
  readonly complete: boolean;
}

export const DEFAULT_LOCALE = "en";

export const LOCALES: Record<string, LocaleInfo> = {
  en: { label: "English", messages: en, complete: true },
  de: { label: "Deutsch", messages: de, complete: false },
};

/** Active locale code. Read it as `$locale` in components. */
export const locale = writable<string>(DEFAULT_LOCALE);

/** Switch locale; unknown codes fall back to English instead of throwing. */
export function setLocale(code: string): void {
  locale.set(Object.hasOwn(LOCALES, code) ? code : DEFAULT_LOCALE);
}

const DEV: boolean = (() => {
  try {
    return Boolean(import.meta.env?.DEV);
  } catch {
    return false;
  }
})();

/** Walk a dot-separated key through a nested dictionary. */
function lookup(messages: Messages, key: string): unknown {
  let node: unknown = messages;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    if (!Object.hasOwn(node, part)) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

function resolve(key: string): unknown {
  const active = LOCALES[get(locale)] ?? LOCALES[DEFAULT_LOCALE];
  const raw = lookup(active?.messages ?? en, key);
  if (raw !== undefined) return raw;
  // Per-key fallback: a partial locale falls through to English, not to "key".
  return lookup(en, key);
}

function warnMissing(key: string, kind: string): void {
  if (DEV) console.warn(`[i18n] missing ${kind}: ${key}`);
}

const PLACEHOLDER = /\{(\w+)\}/g;

/** Replace `{name}` placeholders; unknown placeholders are left untouched. */
function interpolate(
  message: string,
  vars: Record<string, string | number>,
): string {
  return message.replace(PLACEHOLDER, (match, name: string) =>
    Object.hasOwn(vars, name) ? String(vars[name]) : match,
  );
}

/**
 * Translate a dot-separated key, e.g. `t("chats.matches_other", { count: 3 })`.
 * Returns the key itself when it is missing (and warns in dev only).
 */
export function t(key: string, vars?: Record<string, string | number>): string {
  const raw = resolve(key);
  if (typeof raw !== "string") {
    warnMissing(key, "key");
    return key;
  }
  return vars ? interpolate(raw, vars) : raw;
}

/**
 * Translate a list-valued key (arrays of paragraphs, e.g. the Guides bodies).
 * Returns `[]` for a missing key so `{#each}` degrades to nothing.
 */
export function tList(key: string): string[] {
  const raw = resolve(key);
  if (!Array.isArray(raw)) {
    warnMissing(key, "list");
    return [];
  }
  return raw.filter((item): item is string => typeof item === "string");
}
