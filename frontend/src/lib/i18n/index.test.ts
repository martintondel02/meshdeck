// Unit tests for the i18n layer: nested lookup, interpolation, explicit
// plurals, the missing-key contract, and per-key fallback through a partial
// locale (de.ts is deliberately a three-key fake dictionary).
import { beforeEach, describe, expect, it } from "vitest";
import { get } from "svelte/store";
import { LOCALES, locale, setLocale, t, tList } from "./index";

beforeEach(() => setLocale("en"));

describe("t", () => {
  it("resolves nested dot-separated keys", () => {
    expect(t("settings.title")).toBe("Settings");
    expect(t("tooltips.address")).toContain("Reticulum address");
    expect(t("guides.sections.getting_started.title")).toBe("Getting started");
  });

  it("interpolates {placeholders}", () => {
    expect(t("chats.matches_one", { count: 1 })).toBe("1 match");
    expect(t("chats.matches_other", { count: 3 })).toBe("3 matches");
  });

  it("uses explicit plural keys, not a naive trailing s", () => {
    expect(t("common.unread_messages_one", { count: 1 })).toBe(
      "1 unread message",
    );
    expect(t("common.unread_messages_other", { count: 2 })).toBe(
      "2 unread messages",
    );
  });

  it("returns the key itself when the key is missing", () => {
    expect(t("nope.not.here")).toBe("nope.not.here");
    expect(t("chats.peers_title.nested")).toBe("chats.peers_title.nested");
  });

  it("leaves unknown placeholders untouched", () => {
    expect(t("chats.matches_one", { nope: 1 })).toBe("{count} match");
  });
});

describe("tList", () => {
  it("returns paragraph lists", () => {
    expect(tList("guides.sections.messaging.body")).toHaveLength(2);
  });

  it("returns an empty list for non-list keys", () => {
    expect(tList("settings.title")).toEqual([]);
  });
});

describe("locale store and fallback", () => {
  it("defaults to English", () => {
    expect(get(locale)).toBe("en");
  });

  it("falls back per key from a partial locale", () => {
    setLocale("de");
    expect(get(locale)).toBe("de");
    // present in de.ts
    expect(t("common.starting")).toBe("Startet…");
    expect(t("common.copy")).toBe("Kopieren");
    expect(t("settings.title")).toBe("Einstellungen");
    // missing from de.ts -> English, not a raw key
    expect(t("chats.send")).toBe("Send");
    expect(t("tooltips.address")).toContain("Reticulum address");
    expect(tList("guides.sections.messaging.body")).toHaveLength(2);
  });

  it("falls back to English for unknown locale codes", () => {
    setLocale("xx");
    expect(get(locale)).toBe("en");
    expect(t("chats.send")).toBe("Send");
  });

  it("exposes the locale map", () => {
    expect(Object.keys(LOCALES)).toContain("de");
    expect(LOCALES.de?.complete).toBe(false);
    expect(LOCALES.en?.complete).toBe(true);
  });
});
