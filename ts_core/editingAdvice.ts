import { EditingAdvice, PhotoReviewRecord } from "./types";
import { isCurrentConcreteQwenReview } from "./qwenReview";

const BASE_PARAMETERS: Record<string, string> = {
  exposure: "+0.15",
  contrast: "+6",
  highlights: "-18",
  shadows: "+24",
  whites: "+2",
  blacks: "-6",
  texture: "0",
  clarity: "+2",
  dehaze: "0",
  vibrance: "+4",
  saturation: "-2",
  temperature: "0K",
  tint: "0"
};

export function hasVisionRead(record: PhotoReviewRecord): boolean {
  if (!isCurrentConcreteQwenReview(record)) return false;
  const evidence = Array.isArray(record.visible_evidence) ? record.visible_evidence : [];
  if (evidence.length < 3) return false;
  if (!record.editorial_verdict?.one_line_reason) return false;
  if (isRejectReview(record)) return true;
  const plan = record.editing_plan;
  return Boolean(plan?.crop_plan?.keep?.length && plan.crop_plan.remove_or_reduce?.length && plan.local_masks?.length);
}

export function isRejectReview(record: PhotoReviewRecord): boolean {
  return String(record.editorial_verdict?.action ?? "").toLowerCase() === "reject" || String(record.category ?? "").toLowerCase().includes("reject");
}

export function buildEditingAdvice(record: PhotoReviewRecord, language: "zh" | "en" = "zh"): EditingAdvice {
  const hasVision = hasVisionRead(record);
  const rejected = hasVision && isRejectReview(record);
  if (rejected) {
    return {
      filename: record.filename ?? "",
      editing_advice_source: "rejected_by_vision",
      blocked_reason:
        language === "zh"
          ? "深评结论是淘汰片：不建议继续生成 Lightroom 参数或裁切方案。"
          : "Vision review rejected this frame: no Lightroom recipe or crop plan is recommended.",
      editing_intent: language === "zh" ? "不建议修图；保留深评证据作为淘汰原因。" : "Do not edit this frame; keep the review evidence only as rejection rationale.",
      lightroom_parameters: {},
      crop_plan: {
        aspect_ratio: "original",
        keep: [],
        remove_or_reduce: [],
        reason: language === "zh" ? "深评已判定淘汰；裁切无法挽救主体、瞬间或遮挡问题。" : "Rejected by vision review; cropping cannot rescue the subject, timing, or obstruction issue."
      },
      local_masks: []
    };
  }

  if (!hasVision) {
    return {
      filename: record.filename ?? "",
      editing_advice_source: "technical_draft",
      blocked_reason:
        language === "zh"
          ? "未完成有效深评；这里只给技术草案，不复用旧 Qwen 裁切或参数。"
          : "No current valid deep review; this is a technical draft and does not reuse stale Qwen crop or parameters.",
      editing_intent: language === "zh" ? "技术草案：只处理曝光、明暗和可读性。" : "Technical draft only: adjust exposure, tone, and readability.",
      lightroom_parameters: { ...BASE_PARAMETERS },
      crop_plan: {
        aspect_ratio: "original",
        keep: [language === "zh" ? "深评前保留原始画面信息" : "Keep original context until valid vision review."],
        remove_or_reduce: [language === "zh" ? "只轻微裁掉明显边缘干扰" : "Trim only obvious edge clutter."],
        reason: language === "zh" ? "缺少有效视觉深评，裁切只能作为技术草案。" : "Technical draft only because no valid vision review is available."
      },
      local_masks: []
    };
  }

  const crop = record.editing_plan?.crop_plan;
  return {
    filename: record.filename ?? "",
    editing_advice_source: "vision_evidence",
    blocked_reason: "",
    editing_intent: record.editing_plan?.edit_intent ?? record.story_interpretation ?? "",
    lightroom_parameters: Object.fromEntries(Object.entries(record.specific_edit_parameters ?? BASE_PARAMETERS).map(([key, value]) => [key, String(value)])),
    crop_plan: {
      aspect_ratio: crop?.aspect_ratio ?? "original",
      keep: crop?.keep ?? [],
      remove_or_reduce: crop?.remove_or_reduce ?? [],
      reason: crop?.crop_box?.reason ?? crop?.reason ?? ""
    },
    local_masks: record.editing_plan?.local_masks ?? []
  };
}
