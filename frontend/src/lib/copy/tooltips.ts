// Thin re-export layer. The copy itself now lives in `lib/i18n/en.ts`.
//
// `TOOLTIPS` / `GLOSSARY` stay exported so existing imports don't churn; new
// code should call `t("tooltips.address")` / `t("glossary.identity")` instead.
//
// Rule: no Reticulum jargon appears on screen without an explanation nearby.

import { en } from "../i18n/en";

export const TOOLTIPS = en.tooltips;

export const GLOSSARY = en.glossary;
