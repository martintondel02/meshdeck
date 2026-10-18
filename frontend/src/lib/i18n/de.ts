// INTENTIONALLY INCOMPLETE: three keys, not a translation.
//
// This file exists to prove the per-key fallback chain in `index.ts`:
// `t("common.starting")` returns German, while every other key falls through
// to `en` instead of showing a raw key. Tests in `index.test.ts` assert both.

export const de = {
  common: {
    starting: "Startet…",
    copy: "Kopieren",
  },
  settings: {
    title: "Einstellungen",
  },
};
