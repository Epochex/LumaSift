import { PhotoReviewRecord } from "./types";

export const QWEN_STORY_PROMPT_VERSION = "qwen-story-v13";

const METADATA_TERMS = [
  "brightness",
  "contrast",
  "highlight_clipping",
  "shadow_clipping",
  "technical_quality_score",
  "local_final_selection_score",
  "final_selection_score",
  "group_rank",
  "group_size",
  "rank=1",
  "moment_risk",
  "clipping",
  "category",
  "预筛",
  "技术参数",
  "参数",
  "分数",
  "组内",
  "评分"
];

const SPECIFIC_VISUAL_TERMS = [
  "红色",
  "黄色",
  "绿色",
  "蓝色",
  "白色",
  "黑色",
  "灰色",
  "米色",
  "背包",
  "帽子",
  "耳机",
  "眼镜",
  "头发",
  "短发",
  "背影",
  "面部",
  "后脑",
  "脸",
  "手",
  "微笑",
  "标牌",
  "标识",
  "标语",
  "招牌",
  "文字",
  "和平符号",
  "玻璃",
  "栏杆",
  "立柱",
  "柱子",
  "钢梁",
  "车站",
  "站台",
  "售票机",
  "路口",
  "斑马线",
  "树",
  "天空",
  "灰白色",
  "砖墙",
  "塔楼",
  "教堂",
  "脚手架",
  "垃圾桶",
  "军装",
  "海报",
  "拱门",
  "楼梯",
  "雕像",
  "雕塑",
  "模型",
  "人形",
  "四马战车",
  "地标",
  "勃兰登堡",
  "建筑",
  "网格",
  "顶棚",
  "玻璃顶棚",
  "窗户",
  "门",
  "面包车",
  "自行车",
  "奔驰",
  "裁切",
  "遮挡",
  "反光",
  "高光",
  "阴影",
  "边缘",
  "red",
  "yellow",
  "green",
  "blue",
  "white",
  "black",
  "gray",
  "grey",
  "beige",
  "backpack",
  "earphone",
  "glasses",
  "hair",
  "head",
  "face",
  "hand",
  "smile",
  "sign",
  "glass",
  "railing",
  "pillar",
  "station",
  "platform",
  "sky",
  "landmark",
  "building",
  "gate",
  "crop",
  "cropped",
  "occlud",
  "reflection",
  "highlight",
  "shadow",
  "edge"
];

const TEMPLATE_TERMS = [
  "形成关系",
  "形成层次",
  "关系清晰",
  "空间关系",
  "主体关系",
  "故事感",
  "现场感",
  "画面成立",
  "值得保留",
  "human relationship",
  "subject relationship",
  "street relationship",
  "visual layer",
  "layered context",
  "story signal",
  "worth keeping"
];

export function isCurrentConcreteQwenReview(record: PhotoReviewRecord): boolean {
  return (
    ["done", "cache-hit"].includes(String(record.qwen_status ?? "").toLowerCase()) &&
    record.analysis_source === "qwen_vision" &&
    record.analysis_quality === "concrete" &&
    record.qwen_prompt_version === QWEN_STORY_PROMPT_VERSION
  );
}

export function looksConcrete(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed || mostlyMetadataClaim(trimmed)) return false;
  if (!hasSpecificVisualDetail(trimmed)) return false;
  if (isTemplateVisualClaim(trimmed)) return false;
  return hasVisualAnchor(trimmed);
}

export function analysisQuality(data: PhotoReviewRecord): "concrete" | "weak" | "generic" | "missing" {
  const evidence = Array.isArray(data.visible_evidence) ? data.visible_evidence : [];
  if (!Array.isArray(data.visible_evidence)) return "missing";
  const concreteEvidence = evidence.filter((item) => looksConcrete(String(item)));
  const hasVerdict = validEditorialVerdict(data);
  const hasReview = validProfessionalReview(data.professional_review);
  if (
    concreteEvidence.length >= 4 &&
    validRelationshipRead(String(data.subject_relationship ?? "")) &&
    validMomentRead(String(data.decisive_moment_read ?? "")) &&
    hasVerdict &&
    hasReview
  ) {
    return "concrete";
  }
  if (concreteEvidence.length >= 3 && hasVerdict && hasReview) return "concrete";
  if (hasVerdict && hasReview) return "concrete";
  return concreteEvidence.length ? "weak" : "generic";
}

export function validateQwenStoryData(data: PhotoReviewRecord): void {
  const quality = analysisQuality(data);
  if (quality !== "concrete") {
    throw new Error(`LLM Deep Analysis response was too generic for professional review: ${quality}`);
  }
  if (!validCriticalFlaws(data)) {
    throw new Error("LLM Deep Analysis response did not include concrete critical flaws");
  }
  if (tooPraiseHeavyReview(data)) {
    throw new Error("LLM Deep Analysis response was too praise-heavy for professional review");
  }
  if (unsupportedPersonOrMotionClaims(data)) {
    throw new Error("LLM Deep Analysis response contains unsupported person or motion claims");
  }
  if (overstatedStoryOrHumanValue(data)) {
    throw new Error("LLM Deep Analysis response overstated story or human value without readable human evidence");
  }
}

function validCriticalFlaws(data: PhotoReviewRecord): boolean {
  const flaws = textList(data.critical_flaws);
  let count = flaws.filter((item) => validCriticalFlawText(item)).length;
  count += textList(data.why_deprioritize).filter((item) => validCriticalFlawText(item)).length;
  count += textList(data.frame_failure_reasons).filter((item) => validCriticalFlawText(item)).length;
  count += textList(data.visible_evidence).filter((item) => validCriticalFlawText(item)).length;
  if (data.professional_review && typeof data.professional_review === "object") {
    count += Object.values(data.professional_review).filter((item) => validCriticalFlawText(String(item))).length;
  }
  for (const value of [data.selection_risk, data.edit_vs_select_warning, data.subject_identity_uncertainty]) {
    if (validCriticalFlawText(String(value ?? ""))) count += 1;
  }
  return count >= 2;
}

function validCriticalFlawText(text: string): boolean {
  const lower = text.trim().toLowerCase();
  if (lower.length < 6 || mostlyMetadataClaim(lower)) return false;
  if (["暂无", "没有明显", "轻微", "可修", "不影响整体", "瑕不掩瑜", "仍有潜力"].some((term) => lower.includes(term))) return false;
  const flawTerms = ["不可见", "看不清", "不可读", "缺少", "缺乏", "没有", "遮挡", "截断", "分散", "干扰", "压过", "抢眼", "过曝", "模糊", "弱", "平淡", "不成立", "无互动", "无视线", "无手势", "无表情", "普通", "形式", "结构", "不能靠修图", "unclear", "not readable", "missing", "blocked", "occluded", "weak", "flat", "ordinary"];
  return flawTerms.some((term) => lower.includes(term.toLowerCase())) && hasVisualAnchor(text);
}

function tooPraiseHeavyReview(data: PhotoReviewRecord): boolean {
  const text = combinedReviewText(data).toLowerCase();
  const praiseTerms = ["非常成功", "优秀", "没有明显", "最平衡", "最能体现", "强烈形式感", "强烈作品候选", "非常完整", "构图严谨", "成功", "独特", "丰富", "稳定", "excellent", "successful", "strong candidate"];
  const praiseHits = praiseTerms.reduce((sum, term) => sum + countOccurrences(text, term.toLowerCase()), 0);
  const flawCount =
    textList(data.critical_flaws).filter((item) => validCriticalFlawText(item)).length +
    textList(data.why_deprioritize).filter((item) => validCriticalFlawText(item)).length;
  return praiseHits >= 3 && flawCount < 2;
}

function unsupportedPersonOrMotionClaims(data: PhotoReviewRecord): boolean {
  const checks = data.hallucination_checks;
  if (checks?.unsupported_claims?.some((item) => String(item).trim())) return true;
  const text = combinedReviewText(data);
  const personClaim = hasPersonClaim(text);
  const motionClaim = hasMotionClaim(text);
  if (!personClaim && !motionClaim) return false;
  const people = inventoryPeople(data);
  if (!people.length) return true;
  if (motionClaim && !people.some((person) => person.visibility === "clear") && !uncertainText(text)) return true;
  const lower = text.toLowerCase();
  if (["下方人物", "底部人物", "下方行人", "底部行人", "画面下方有人", "下方走", "底部走"].some((term) => lower.includes(term)) && !negatedBottomPersonClaim(lower)) {
    return !people.some((person) => person.region.includes("下") || person.region.includes("底"));
  }
  return false;
}

function negatedBottomPersonClaim(text: string): boolean {
  return ["没有确认画面下方行人", "没有确认下方行人", "未确认画面下方行人", "未确认下方人物", "没有画面下方人物证据", "不能确认下方人物", "no confirmed lower person", "no bottom person"].some((term) => text.includes(term));
}

function overstatedStoryOrHumanValue(data: PhotoReviewRecord): boolean {
  const readablePeople = inventoryPeople(data).filter((person) => person.visibility === "clear");
  const storyScore = Number(data.storytelling_score ?? 0);
  const humanScore = Number(data.human_documentary_value_score ?? 0);
  const decisiveScore = Number(data.decisive_moment_score ?? 0);
  const action = String(data.editorial_verdict?.action ?? "");
  const category = String(data.category ?? "");
  const momentStatus = String(data.moment_status ?? "").toLowerCase();
  if (!readablePeople.length && (storyScore >= 72 || humanScore >= 72 || decisiveScore >= 68)) return true;
  if (!readablePeople.length && action === "keep" && ["portfolio_candidate", "strong_edit_candidate", "story_candidate"].includes(category)) return true;
  if (["weak", "missed", "ambiguous"].includes(momentStatus) && decisiveScore >= 72) return true;
  if (["missed", "ambiguous"].includes(momentStatus) && ["portfolio_candidate", "strong_edit_candidate"].includes(category)) return true;
  return false;
}

function inventoryPeople(data: PhotoReviewRecord): Array<{ region: string; visibility: string; motion: string }> {
  const inventory = data.visible_inventory;
  const people = Array.isArray(inventory?.people)
    ? inventory.people.map((person) => ({
        region: String(person.region ?? ""),
        visibility: normalVisibility(person.visibility),
        motion: String(person.pose_or_motion ?? person.motion ?? "")
      }))
    : [];
  if (!people.length && hasPersonClaim(String(inventory?.main_subject ?? ""))) {
    const motion = Array.isArray(inventory?.gesture_expression_motion) ? inventory.gesture_expression_motion.join(" ") : "";
    people.push({
      region: String(inventory?.main_subject ?? ""),
      visibility: uncertainText(`${inventory?.main_subject ?? ""} ${motion}`) ? "uncertain" : "clear",
      motion
    });
  }
  return people;
}

function normalVisibility(value: unknown): string {
  const text = String(value ?? "").trim().toLowerCase();
  if (["clear", "visible", "readable", "清楚", "可见", "清晰"].includes(text)) return "clear";
  if (["partial", "obscured", "uncertain", "blurred", "blocked", "部分", "遮挡", "不确定", "看不清"].includes(text)) return "uncertain";
  return text ? "uncertain" : "";
}

function hasPersonClaim(text: string): boolean {
  const lower = text.toLowerCase();
  return ["人物", "行人", "游客", "旅人", "男子", "女性", "人群", "工人", "person", "pedestrian", "tourist", "man", "woman"].some((term) => lower.includes(term.toLowerCase()));
}

function hasMotionClaim(text: string): boolean {
  const lower = text.toLowerCase();
  return ["行走", "走向", "经过", "跨越", "手势", "表情", "视线", "看向", "互动", "站立", "蹲伏", "俯视", "walking", "gesture", "expression", "looking"].some((term) => lower.includes(term.toLowerCase()));
}

function uncertainText(text: string): boolean {
  const lower = text.toLowerCase();
  return ["疑似", "可能", "看不清", "不可辨", "不确定", "模糊", "遮挡", "uncertain", "unclear", "possible"].some((term) => lower.includes(term.toLowerCase()));
}

function combinedReviewText(data: PhotoReviewRecord): string {
  const parts: string[] = [];
  if (data.professional_review && typeof data.professional_review === "object") {
    parts.push(...Object.values(data.professional_review).map(String));
  }
  for (const value of [data.story_interpretation, data.subject_relationship, data.decisive_moment_read, data.selection_risk, data.edit_vs_select_warning, data.subject_identity_uncertainty]) {
    if (value) parts.push(String(value));
  }
  parts.push(...textList(data.visible_evidence));
  parts.push(...textList(data.critical_flaws));
  parts.push(...textList(data.frame_failure_reasons));
  parts.push(...textList(data.why_deprioritize));
  if (data.hallucination_checks) {
    parts.push(...textList(data.hallucination_checks.unsupported_claims));
    parts.push(...textList(data.hallucination_checks.uncertain_objects));
    if (data.hallucination_checks.spatial_sanity_check) parts.push(String(data.hallucination_checks.spatial_sanity_check));
  }
  return parts.filter(Boolean).join("\n");
}

function textList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter((item) => item.trim());
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function countOccurrences(text: string, term: string): number {
  if (!term) return 0;
  return text.split(term).length - 1;
}

function validEditorialVerdict(data: PhotoReviewRecord): boolean {
  const verdict = data.editorial_verdict;
  if (!verdict) return false;
  return ["keep", "maybe", "reject"].includes(String(verdict.action ?? "")) && looksConcrete(String(verdict.one_line_reason ?? ""));
}

function validProfessionalReview(review: PhotoReviewRecord["professional_review"]): boolean {
  if (!review || typeof review !== "object") return false;
  const keys = ["editorial_summary", "story_read", "composition_read", "selection_logic", "editing_logic"];
  return keys.filter((key) => looksConcrete(String(review[key] ?? "")) && String(review[key] ?? "").trim().length >= 24).length >= 3;
}

function mostlyMetadataClaim(text: string): boolean {
  const lower = text.toLowerCase();
  const hits = METADATA_TERMS.filter((term) => lower.includes(term.toLowerCase())).length;
  if (hits >= 2) return true;
  return /\b(?:brightness|contrast|rank|score|category|clipping|delta)\b\s*[=:]?\s*\d/i.test(text);
}

function hasSpecificVisualDetail(text: string): boolean {
  const lower = text.toLowerCase();
  if (/\b(?:db|kfc|u-?bahn|s-?bahn|airpods)\b|[A-Z]{2,}|\b[A-Z]?\d+[A-Z]?\b/.test(text)) return true;
  return SPECIFIC_VISUAL_TERMS.some((term) => lower.includes(term.toLowerCase()));
}

function isTemplateVisualClaim(text: string): boolean {
  if (hasSpecificVisualDetail(text)) return false;
  const lower = text.toLowerCase();
  const objectTerms = ["人物", "主体", "前景", "背景", "街道", "环境", "车辆", "person", "subject", "foreground", "background", "street", "environment", "vehicle"];
  const objectHits = objectTerms.filter((term) => lower.includes(term.toLowerCase())).length;
  return objectHits >= 2 && TEMPLATE_TERMS.some((term) => lower.includes(term.toLowerCase()));
}

function hasVisualAnchor(text: string): boolean {
  const lower = text.toLowerCase();
  const subjects = ["人物", "游客", "行人", "男子", "女性", "人群", "面部", "表情", "微笑", "手势", "背影", "person", "tourist", "pedestrian", "face", "hand"];
  const environments = ["车辆", "车流", "招牌", "标识", "文字", "db", "街道", "站台", "地标", "天空", "路口", "建筑", "钢梁", "网格", "顶棚", "玻璃顶棚", "雕像", "雕塑", "模型", "人形", "背包", "sign", "street", "station", "building", "sky"];
  const relations = ["遮挡", "视线", "动作", "互动", "合影", "裁剪", "裁切", "反射", "形成", "突出", "关系", "层次", "不可读", "看不清", "缺少", "缺乏", "压过", "抢眼", "模糊", "occlud", "crop", "relationship", "reflection", "unreadable", "unclear", "missing"];
  const buckets = [subjects, environments, relations].map((bucket) => bucket.some((term) => lower.includes(term.toLowerCase())));
  return buckets.filter(Boolean).length >= 2;
}

function validRelationshipRead(text: string): boolean {
  const lower = text.toLowerCase();
  if (looksConcrete(text)) return true;
  return ["割裂", "无互动", "没有互动", "缺乏互动", "无法形成", "未形成", "no interaction", "disconnected", "no usable relationship"].some((term) => lower.includes(term.toLowerCase()));
}

function validMomentRead(text: string): boolean {
  const lower = text.toLowerCase();
  if (looksConcrete(text)) return true;
  return ["瞬间未成立", "未捕捉", "没有", "无", "缺乏", "静止", "no readable", "no decisive", "does not survive"].some((term) => lower.includes(term.toLowerCase()));
}
